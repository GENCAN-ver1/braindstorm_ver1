from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from runtime.budget_guard import (
    BudgetChargeKind,
    BudgetGuard,
    BudgetIncreaseError,
)
from runtime.checkpoint import CheckpointStore
from runtime.config_loader import config_from_dict
from runtime.fault_injection import Stage
from runtime.full_cycle import FullCycleRunner
from runtime.governor_modules import p0, p2
from runtime.lifecycle_errors import BudgetExhausted, coerce_budget_exhausted
from runtime.reentry import DurableStageRunner


class Fv03Mixin:
    def temp_path(self, name="CONCEPT_BRIEF.md"):
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-{name}"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(
            path.with_name(f".{path.name}.cas.lock").unlink,
            missing_ok=True,
        )
        return path

    def state(self, run_id="run-fv03", *, max_steps=4, used_steps=0):
        return p0.new_state(
            p0.RoutingInput(
                explicit_mode=p0.Mode.SHAPE,
                research_allowed=True,
                budget=p0.Budget(
                    max_steps=max_steps,
                    used_steps=used_steps,
                    max_parallelism=1,
                ),
            ),
            run_id=run_id,
        )

    def config(self, max_steps):
        return config_from_dict(
            {
                "schema_version": 1,
                "runtime": {
                    "mode": "auto",
                    "parallelism": 1,
                    "budget": {"max_steps": max_steps, "max_parallelism": 1},
                },
                "persistence": {"brief_path": "./CONCEPT_BRIEF.md"},
                "features": {
                    "research": False,
                    "workers": False,
                    "council": False,
                    "evaluator": False,
                },
                "evaluation": {"max_rounds": 2},
            }
        )


class BudgetGuardTests(Fv03Mixin, unittest.TestCase):
    def test_guard_consumes_exactly_once_and_does_not_overrun(self):
        state = self.state(max_steps=1)
        guard = BudgetGuard()
        guard.consume(state, Stage.INITIALIZE, "stage", BudgetChargeKind.STAGE)
        self.assertEqual(state.run.budget.used_steps, 1)
        with self.assertRaises(BudgetExhausted) as raised:
            guard.consume(state, Stage.ROUTE, "stage", BudgetChargeKind.STAGE)
        self.assertEqual(state.run.budget.used_steps, 1)
        self.assertEqual(raised.exception.stage, Stage.ROUTE)

    def test_checkpointed_charge_is_idempotent_across_restore(self):
        path = self.temp_path()
        store = CheckpointStore()
        session = store.open(path, self.state(max_steps=2))
        session.enter_stage(Stage.INITIALIZE)
        self.assertTrue(
            session.consume_budget(
                BudgetGuard(),
                Stage.INITIALIZE,
                "stage",
                BudgetChargeKind.STAGE,
            )
        )
        restored = store.open(path, self.state("ignored", max_steps=99))
        self.assertFalse(
            restored.consume_budget(
                BudgetGuard(),
                Stage.INITIALIZE,
                "stage",
                BudgetChargeKind.STAGE,
            )
        )
        self.assertEqual(restored.state.run.budget.used_steps, 1)
        self.assertEqual(len(restored.envelope.budget_charges), 1)

    def test_fv02_envelope_without_budget_charges_is_migrated_on_next_save(self):
        path = self.temp_path()
        store = CheckpointStore()
        store.open(path, self.state())
        brief = p2.load_brief(path)
        checkpoint_record = next(
            item
            for item in brief.runtime_state.deferred
            if item.get("type") == "brainstorm-governor-checkpoint-v1"
        )
        checkpoint_record["envelope"].pop("budget_charges")
        p2.save_round(
            path,
            brief,
            brief.runtime_state,
            next_action="simulate FV-02 envelope",
        )

        restored = store.open(path, self.state("ignored"))
        self.assertEqual(restored.envelope.budget_charges, {})
        restored.mark_recovered()
        saved = p2.load_brief(path)
        saved_record = next(
            item
            for item in saved.runtime_state.deferred
            if item.get("type") == "brainstorm-governor-checkpoint-v1"
        )
        self.assertIn("budget_charges", saved_record["envelope"])

    def test_park_preserves_checkpoint_trace_and_usage_progress(self):
        path = self.temp_path()
        session = CheckpointStore().open(
            path, self.state(max_steps=1, used_steps=1)
        )
        session.update_progress(
            trace_cursor=17,
            usage_totals={"prompt_tokens": 21, "cost": 0.04},
        )
        result = DurableStageRunner(
            lambda stage, state, context: state,
            stages=(Stage.INITIALIZE,),
        ).run_session(session, resumed=False)
        self.assertEqual(result.state.result.exit_status, p0.ExitStatus.PARK)
        self.assertEqual(result.envelope.trace_cursor, 17)
        self.assertEqual(result.envelope.usage_totals["prompt_tokens"], 21)
        self.assertEqual(result.envelope.usage_totals["cost"], 0.04)

    def test_external_budget_exhaustion_prevents_call_and_can_resume_after_increase(self):
        path = self.temp_path()
        calls = []

        def handler(stage, state, context):
            context.run_external(
                "research-1",
                lambda key: calls.append(key) or {"ok": True},
            )
            return state

        parked = DurableStageRunner(handler, stages=(Stage.RESEARCH,)).run(
            str(path), self.state(max_steps=1)
        )
        self.assertEqual(parked.state.result.exit_status, p0.ExitStatus.PARK)
        self.assertEqual(calls, [])
        self.assertIsNone(parked.envelope.in_flight_operation)

        unchanged = DurableStageRunner(handler, stages=(Stage.RESEARCH,)).run(
            str(path), self.state("ignored", max_steps=99)
        )
        self.assertEqual(unchanged.state.result.exit_status, p0.ExitStatus.PARK)
        self.assertEqual(unchanged.state.run.budget.used_steps, 1)
        self.assertEqual(calls, [])

        session = CheckpointStore().open(path, self.state("ignored-again"))
        session.resume_park(BudgetGuard(), 2)
        resumed = DurableStageRunner(handler, stages=(Stage.RESEARCH,)).run_session(
            session, resumed=True
        )
        self.assertEqual(resumed.state.result.exit_status, p0.ExitStatus.COMMIT)
        self.assertEqual(resumed.state.run.budget.used_steps, 2)
        self.assertEqual(len(calls), 1)

    def test_resume_requires_strict_budget_increase(self):
        path = self.temp_path()
        parked = DurableStageRunner(lambda stage, state, context: state).run(
            str(path), self.state(max_steps=1, used_steps=1)
        )
        self.assertEqual(parked.state.result.exit_status, p0.ExitStatus.PARK)
        session = CheckpointStore().open(path, self.state("ignored"))
        with self.assertRaises(BudgetIncreaseError):
            session.resume_park(BudgetGuard(), 1)

    def test_legacy_budget_validation_error_is_translated(self):
        state = self.state(max_steps=1, used_steps=1)
        translated = coerce_budget_exhausted(
            p0.StateValidationError(["run budget exhausted before safe stop"]),
            state=state,
            stage=Stage.CONVERGE,
        )
        self.assertIsInstance(translated, BudgetExhausted)
        self.assertEqual(translated.stage, Stage.CONVERGE)

    def test_full_cycle_preserves_used_steps_until_config_explicitly_increases_limit(self):
        path = self.temp_path()
        request = {
            "request_id": "run-fv03-full-cycle",
            "text": "Shape a budget-safe concept.",
            "routing": {"ambiguous_concept": True},
        }
        initial = self.state(
            "run-fv03-full-cycle", max_steps=4, used_steps=4
        )
        parked = DurableStageRunner(
            lambda stage, state, context: state,
            stages=(Stage.INITIALIZE,),
        ).run(str(path), initial)
        self.assertEqual(parked.state.result.exit_status, p0.ExitStatus.PARK)

        second = FullCycleRunner(self.config(4)).run(request, brief_path=path)
        self.assertEqual(second.exit_status, "PARK")
        self.assertIn("INITIALIZE", second.next_action)
        self.assertEqual(p2.load_brief(path).runtime_state.run.budget.used_steps, 4)

        resumed = FullCycleRunner(self.config(8)).run(request, brief_path=path)
        self.assertTrue(resumed.resumed)
        self.assertEqual(resumed.exit_status, "NEEDS_INPUT")
        budget = p2.load_brief(path).runtime_state.run.budget
        self.assertEqual((budget.used_steps, budget.max_steps), (8, 8))


if __name__ == "__main__":
    unittest.main()
