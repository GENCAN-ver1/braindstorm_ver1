from __future__ import annotations

import copy
import json
import unittest
import uuid
from pathlib import Path

from adapters.evaluator_runtime import TracedEvaluator
from artifacts.manifest import ArtifactManifest, ArtifactManifestError, QualityStatus
from artifacts.writer import ArtifactWriter, ArtifactWriterError
from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.checkpoint import CheckpointStore
from runtime.fault_injection import (
    FaultAction,
    FaultInjector,
    FaultPoint,
    FaultRule,
    InjectedInterruption,
    Stage,
)
from runtime.governor_modules import p0, p2, p6
from runtime.handoff_gate import HandoffGate, HandoffGateError
from runtime.reentry import StageContext
from tests.fv04_support import state


class CountingEvaluator:
    def __init__(self):
        self.calls = 0

    def evaluate(self, request):
        del request
        self.calls += 1
        return p6.EvaluatorInvocation(p6.EvaluationReport([]))


class AcknowledgingOptimizer:
    def apply(self, artifact, corrections):
        return p6.OptimizerResult(
            copy.deepcopy(artifact), [item.id for item in corrections]
        )


class Fv06UnitTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).parent
        self.prefix = f".fv06-unit-{uuid.uuid4().hex}"

    def path(self, name):
        target = self.root / f"{self.prefix}-{name}"
        self.addCleanup(target.unlink, missing_ok=True)
        self.addCleanup(
            target.with_name(f".{target.name}.cas.lock").unlink,
            missing_ok=True,
        )
        self.addCleanup(
            target.with_name(f".{target.name}.lock").unlink,
            missing_ok=True,
        )
        self.addCleanup(
            target.with_name(f".{target.name}.tmp").unlink,
            missing_ok=True,
        )
        return target

    def evaluator_input(self):
        return p6.EvaluatorInput(
            confirmed_frame={},
            candidates=[],
            recommendation=None,
            evaluation_criteria=list(p6.EvaluationCheck),
            evidence_summary=[],
            output_contract={"required": ["recommendation"]},
        )

    def test_retry_before_provider_reuses_reserved_round(self):
        path = self.path("retry.md")
        session = CheckpointStore().open(
            path, state("run-fv06-retry"), initial_next_stage=Stage.EVALUATE
        )
        session.enter_stage(Stage.EVALUATE)
        session.consume_budget(
            BudgetGuard(), Stage.EVALUATE, "stage", BudgetChargeKind.STAGE
        )
        provider = CountingEvaluator()
        context = StageContext(
            session,
            Stage.EVALUATE,
            FaultInjector(
                [
                    FaultRule(
                        Stage.EVALUATE,
                        FaultPoint.BEFORE_EXTERNAL_CALL,
                        FaultAction.INTERRUPT,
                    )
                ]
            ),
            BudgetGuard(),
        )
        with self.assertRaises(InjectedInterruption):
            TracedEvaluator(provider, context).evaluate(self.evaluator_input())
        self.assertEqual(session.envelope.evaluator_rounds_used, 1)
        self.assertEqual(provider.calls, 0)

        restored = CheckpointStore().open(path, state("ignored"))
        TracedEvaluator(
            provider,
            StageContext(
                restored,
                Stage.EVALUATE,
                FaultInjector.disabled(),
                BudgetGuard(),
            ),
        ).evaluate(self.evaluator_input())
        self.assertEqual(restored.envelope.evaluator_rounds_used, 1)
        self.assertEqual(provider.calls, 1)

    def test_legacy_checkpoint_migrates_evaluator_tracking_fields(self):
        path = self.path("legacy.md")
        session = CheckpointStore().open(path, state("run-fv06-legacy"))
        session.update_progress(evaluator_rounds_used=1)
        stored = p2.load_brief(path)
        record = next(
            item
            for item in stored.runtime_state.deferred
            if item.get("type") == "brainstorm-governor-checkpoint-v1"
        )
        for field in (
            "evaluator_request_keys",
            "evaluator_consumed_keys",
            "quality_gate_id",
        ):
            record["envelope"].pop(field)
        p2.save_round(path, stored, stored.runtime_state, next_action="legacy FV-05")
        restored = CheckpointStore().open(path, state("ignored"))
        self.assertEqual(restored.envelope.evaluator_rounds_used, 1)
        self.assertEqual(
            restored.envelope.evaluator_request_keys, ["legacy:evaluator:1"]
        )
        self.assertEqual(
            restored.envelope.evaluator_consumed_keys, ["legacy:evaluator:1"]
        )

    def test_second_substantive_report_stops_with_iterate(self):
        path = self.path("iterate.md")
        session = CheckpointStore().open(
            path, state("run-fv06-iterate"), initial_next_stage=Stage.EVALUATE
        )
        session.enter_stage(Stage.EVALUATE)
        session.consume_budget(
            BudgetGuard(), Stage.EVALUATE, "stage", BudgetChargeKind.STAGE
        )

        class SubstantiveEvaluator:
            def __init__(self):
                self.calls = 0

            def evaluate(self, request):
                del request
                self.calls += 1
                correction = p6.ActionableCorrection(
                    id=f"gap-{self.calls}",
                    check=p6.EvaluationCheck.WEIGHT_SENSITIVITY,
                    target="recommendation.tradeoffs",
                    issue="the choice remains sensitive to a plausible weight",
                    required_change="record the crossover weight and alternate winner",
                    severity=p6.CorrectionSeverity.HIGH,
                    high_impact=True,
                )
                return p6.EvaluatorInvocation(p6.EvaluationReport([correction]))

        provider = SubstantiveEvaluator()
        evaluator = TracedEvaluator(
            provider,
            StageContext(
                session,
                Stage.EVALUATE,
                FaultInjector.disabled(),
                BudgetGuard(),
            ),
        )
        artifact = p6.artifact_from_state(
            session.state,
            output_contract={"required": ["recommendation"]},
        )
        outcome = p6.run_evaluator_optimizer(
            session.state,
            artifact,
            evaluator,
            AcknowledgingOptimizer(),
            config=p6.EvaluatorConfig(2),
        )
        self.assertEqual(provider.calls, 2)
        self.assertEqual(session.envelope.evaluator_rounds_used, 2)
        self.assertEqual(outcome.state.result.exit_status, p0.ExitStatus.ITERATE)
        self.assertEqual(
            outcome.stop_reason, p6.QualityStopReason.MAX_EVALUATOR_ROUNDS
        )

    def test_manifest_rejects_unknown_fields_and_empty_artifact(self):
        value = {
            "artifact_path": str(self.path("artifact.json").resolve()),
            "sha256": "0" * 64,
            "run_id": "run-manifest",
            "brief_revision": 1,
            "quality_gate_id": "quality:1",
            "quality_status": "APPROVED",
            "created_at": "2026-08-21T00:00:00Z",
            "unknown": True,
        }
        with self.assertRaises(ArtifactManifestError):
            ArtifactManifest.from_dict(value)

        session = CheckpointStore().open(
            self.path("commit.md"),
            state("run-empty"),
            initial_next_stage=Stage.EVALUATE,
        )
        session.commit_stage(
            copy.deepcopy(session.state),
            Stage.EVALUATE,
            None,
            terminal_exit=p0.ExitStatus.COMMIT,
        )
        with self.assertRaises(ArtifactWriterError):
            ArtifactWriter().write_for_session(
                session,
                self.path("empty.json"),
                b"",
                quality_gate_id="quality:empty",
                quality_status=QualityStatus.APPROVED,
            )
        self.assertEqual(session.envelope.artifact_status, "NONE")

    def test_non_commit_cannot_write_approved_artifact(self):
        session = CheckpointStore().open(
            self.path("park.md"), state("run-not-commit")
        )
        with self.assertRaises(ArtifactWriterError):
            ArtifactWriter().write_for_session(
                session,
                self.path("invalid.json"),
                json.dumps({"value": 1}),
                quality_gate_id="quality:invalid",
            )

    def test_handoff_rejects_every_non_commit_exit(self):
        for exit_status in p0.ExitStatus:
            if exit_status is p0.ExitStatus.COMMIT:
                continue
            with self.subTest(exit_status=exit_status.value):
                session = CheckpointStore().open(
                    self.path(f"{exit_status.value}.md"),
                    state(f"run-{exit_status.value.lower()}"),
                    initial_next_stage=Stage.EVALUATE,
                )
                session.commit_stage(
                    copy.deepcopy(session.state),
                    Stage.EVALUATE,
                    None,
                    terminal_exit=exit_status,
                )
                artifact = p6.artifact_from_state(
                    session.state,
                    output_contract={"required": ["recommendation"]},
                )
                outcome = p6.QualityGateOutcome(
                    state=copy.deepcopy(session.state),
                    artifact=artifact,
                    reports=[],
                    remaining_corrections=[],
                    stop_reason=p6.QualityStopReason.MAX_EVALUATOR_ROUNDS,
                    trace=p6.QualityTrace(mode=session.state.run.mode),
                    approved=True,
                )
                with self.assertRaises(HandoffGateError):
                    HandoffGate().build(
                        session,
                        outcome,
                        self.path(f"{exit_status.value}.manifest.json"),
                        acceptance_criteria=["must commit"],
                        risks=["not approved"],
                        next_validation="return to convergence",
                    )


if __name__ == "__main__":
    unittest.main()
