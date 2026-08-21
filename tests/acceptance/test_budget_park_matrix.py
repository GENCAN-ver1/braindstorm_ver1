from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from runtime.checkpoint import CheckpointStore
from runtime.fault_injection import Stage
from runtime.governor_modules import p0, p2
from runtime.reentry import DurableStageRunner


class BudgetParkMatrixAcceptanceTests(unittest.TestCase):
    def temp_path(self):
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-ac05.md"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(
            path.with_name(f".{path.name}.cas.lock").unlink,
            missing_ok=True,
        )
        return path

    def state(self, stage_index):
        max_steps = max(1, stage_index)
        used_steps = 1 if stage_index == 0 else 0
        return p0.new_state(
            p0.RoutingInput(
                explicit_mode=p0.Mode.DECIDE,
                research_allowed=True,
                budget=p0.Budget(
                    max_steps=max_steps,
                    used_steps=used_steps,
                    max_parallelism=1,
                ),
            ),
            run_id=f"run-ac05-{stage_index}",
        )

    def test_ac_05_every_stage_parks_before_work(self):
        for stage_index, blocked_stage in enumerate(Stage):
            with self.subTest(stage=blocked_stage.value):
                path = self.temp_path()
                executed = []

                def handler(stage, state, context):
                    del context
                    executed.append(stage.value)
                    return state

                result = DurableStageRunner(handler).run(
                    str(path), self.state(stage_index)
                )
                self.assertEqual(result.state.run.stage, p0.Stage.STOPPED)
                self.assertEqual(result.state.run.status, p0.RunStatus.STOPPED)
                self.assertEqual(result.state.result.exit_status, p0.ExitStatus.PARK)
                self.assertNotIn(blocked_stage.value, executed)
                self.assertEqual(result.envelope.next_stage, blocked_stage.value)
                self.assertIn(blocked_stage.value, result.stage_history)
                self.assertEqual(
                    result.state.run.budget.used_steps,
                    result.state.run.budget.max_steps,
                )

                brief = p2.load_brief(path)
                p0.validate_state(brief.runtime_state)
                self.assertEqual(brief.exit_status, p0.ExitStatus.PARK.value)
                self.assertIn(blocked_stage.value, brief.next_action)
                self.assertIn("increase budget", brief.next_action)
                restored = CheckpointStore().open(path, self.state(stage_index))
                self.assertEqual(restored.envelope.next_stage, blocked_stage.value)

    def test_external_call_count_does_not_increase_after_exhaustion(self):
        path = self.temp_path()
        calls = []

        def handler(stage, state, context):
            context.run_external(
                "provider-call",
                lambda key: calls.append(key) or {"ok": True},
            )
            return state

        state = p0.new_state(
            p0.RoutingInput(
                explicit_mode=p0.Mode.DECIDE,
                research_allowed=True,
                budget=p0.Budget(max_steps=1, max_parallelism=1),
            ),
            run_id="run-ac05-external",
        )
        result = DurableStageRunner(handler, stages=(Stage.RESEARCH,)).run(
            str(path), state
        )
        self.assertEqual(result.state.result.exit_status, p0.ExitStatus.PARK)
        self.assertEqual(result.envelope.next_stage, Stage.RESEARCH.value)
        self.assertEqual(calls, [])
        self.assertEqual(result.envelope.operation_receipts, {})
        self.assertIsNone(result.envelope.in_flight_operation)


if __name__ == "__main__":
    unittest.main()

