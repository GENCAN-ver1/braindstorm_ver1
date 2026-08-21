from __future__ import annotations

import copy
import json
import unittest
import uuid
from dataclasses import replace
from pathlib import Path

from adapters.evaluator_runtime import TracedEvaluator
from artifacts.manifest import MANIFEST_FIELDS, QualityStatus, save_manifest
from artifacts.writer import ArtifactWriter
from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.checkpoint import CheckpointStore
from runtime.evaluator_guard import EvaluatorRoundLimitReached
from runtime.fault_injection import (
    FaultAction,
    FaultInjector,
    FaultPoint,
    FaultRule,
    InjectedInterruption,
    Stage,
)
from runtime.governor_modules import p0, p6
from runtime.handoff_gate import HandoffGate, HandoffGateError
from runtime.reentry import StageContext
from tests.fv04_support import state


PROJECT_ROOT = Path(__file__).parents[2]


class CountingEvaluator:
    def __init__(self) -> None:
        self.calls = 0

    def evaluate(self, request):
        del request
        self.calls += 1
        correction = p6.ActionableCorrection(
            id=f"correction-{self.calls}",
            check=p6.EvaluationCheck.WEIGHT_SENSITIVITY,
            target="recommendation.tradeoffs",
            issue="the preferred option changes under a plausible risk weight",
            required_change="record the crossover weight and alternate winner",
            severity=p6.CorrectionSeverity.HIGH,
            high_impact=True,
        )
        return p6.EvaluatorInvocation(p6.EvaluationReport([correction]))


class Fv06AcceptanceMixin:
    def setUp(self) -> None:
        self.root = PROJECT_ROOT / "tests" / "acceptance"
        self.prefix = f".fv06-{uuid.uuid4().hex}"

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

    def evaluate_context(self, run_id, injector):
        brief_path = self.path(f"{run_id}.md")
        session = CheckpointStore().open(
            brief_path,
            state(run_id),
            initial_next_stage=Stage.EVALUATE,
        )
        if session.created:
            session.enter_stage(Stage.EVALUATE)
            session.consume_budget(
                BudgetGuard(),
                Stage.EVALUATE,
                "stage",
                BudgetChargeKind.STAGE,
            )
        return session, StageContext(
            session, Stage.EVALUATE, injector, BudgetGuard()
        )

    def committed_session(self, run_id):
        brief_path = self.path(f"{run_id}.md")
        session = CheckpointStore().open(
            brief_path,
            state(run_id),
            initial_next_stage=Stage.EVALUATE,
        )
        session.commit_stage(
            copy.deepcopy(session.state),
            Stage.EVALUATE,
            None,
            terminal_exit=p0.ExitStatus.COMMIT,
        )
        artifact = p6.artifact_from_state(
            session.state,
            output_contract={"required": ["recommendation"]},
        )
        outcome = p6.QualityGateOutcome(
            state=copy.deepcopy(session.state),
            artifact=copy.deepcopy(artifact),
            reports=[],
            remaining_corrections=[],
            stop_reason=p6.QualityStopReason.QUALITY_PASS,
            trace=p6.QualityTrace(mode=session.state.run.mode),
            approved=True,
        )
        return session, artifact, outcome


class EvaluatorCapAcceptanceTests(Fv06AcceptanceMixin, unittest.TestCase):
    def test_ac_04_evaluator_calls_never_exceed_two_across_resume(self):
        fixture = json.loads(
            (PROJECT_ROOT / "tests/acceptance/fixtures/ac04_evaluator_cap.json")
            .read_text(encoding="utf-8")
        )
        provider = CountingEvaluator()
        interrupted_session, interrupted_context = self.evaluate_context(
            "run-ac04",
            FaultInjector(
                [
                    FaultRule(
                        Stage.EVALUATE,
                        FaultPoint.AFTER_EXTERNAL_CALL,
                        FaultAction.INTERRUPT,
                    )
                ]
            ),
        )
        with self.assertRaises(InjectedInterruption):
            TracedEvaluator(provider, interrupted_context).evaluate(
                self.evaluator_input()
            )
        self.assertEqual(interrupted_session.envelope.evaluator_rounds_used, 1)
        self.assertEqual(provider.calls, 1)

        resumed_session, resumed_context = self.evaluate_context(
            "run-ac04", FaultInjector.disabled()
        )
        resumed_session.mark_recovered()
        evaluator = TracedEvaluator(provider, resumed_context)
        evaluator.evaluate(self.evaluator_input())  # reuse round-1 receipt
        self.assertEqual(provider.calls, 1)
        evaluator.evaluate(self.evaluator_input())  # real round 2
        self.assertEqual(provider.calls, 2)
        with self.assertRaises(EvaluatorRoundLimitReached):
            evaluator.evaluate(self.evaluator_input())

        restored = CheckpointStore().open(
            resumed_session.path, state("ignored-ac04")
        )
        self.assertEqual(
            restored.envelope.evaluator_rounds_used,
            fixture["configured_max_rounds"],
        )
        self.assertEqual(
            provider.calls, fixture["assertions"]["provider_calls"]
        )


class ArtifactGateAcceptanceTests(Fv06AcceptanceMixin, unittest.TestCase):
    def write_case(self, case_name, status=QualityStatus.APPROVED):
        session, artifact, outcome = self.committed_session(f"run-ac08-{case_name}")
        result = ArtifactWriter().write_for_session(
            session,
            self.path(f"{case_name}.json"),
            p6._json_ready(artifact),
            quality_gate_id=f"quality:{case_name}",
            quality_status=status,
        )
        self.addCleanup(result.manifest_path.unlink, missing_ok=True)
        return session, outcome, result

    def handoff(self, session, outcome, manifest_path):
        return HandoffGate().build(
            session,
            outcome,
            manifest_path,
            acceptance_criteria=["artifact remains integrity checked"],
            risks=["provider variance"],
            next_validation="run the cheapest reversible test",
        )

    def test_ac_08_only_current_hash_matched_approved_artifact_can_handoff(self):
        fixture = json.loads(
            (PROJECT_ROOT / "tests/acceptance/fixtures/ac08_artifact_gate.json")
            .read_text(encoding="utf-8")
        )
        success_count = 0
        rejection_count = 0

        session, outcome, result = self.write_case(
            "approved_existing_hash_match"
        )
        self.assertEqual(
            set(result.manifest.to_dict()), set(fixture["required_manifest_fields"])
        )
        self.assertEqual(tuple(result.manifest.to_dict()), MANIFEST_FIELDS)
        handoff = self.handoff(session, outcome, result.manifest_path)
        self.assertEqual(
            set(p6.handoff_to_dict(handoff)),
            {
                "approved_artifact_path",
                "locked_decisions",
                "open_questions",
                "non_goals",
                "acceptance_criteria",
                "risks",
                "next_validation",
            },
        )
        success_count += 1

        session, outcome, result = self.write_case(
            "quality_gate_failed", QualityStatus.REJECTED
        )
        with self.assertRaises(HandoffGateError):
            self.handoff(session, outcome, result.manifest_path)
        rejection_count += 1

        session, outcome, result = self.write_case("artifact_missing")
        Path(result.manifest.artifact_path).unlink()
        with self.assertRaises(HandoffGateError):
            self.handoff(session, outcome, result.manifest_path)
        rejection_count += 1

        session, outcome, result = self.write_case("artifact_tampered")
        Path(result.manifest.artifact_path).write_text(
            "tampered", encoding="utf-8"
        )
        with self.assertRaises(HandoffGateError):
            self.handoff(session, outcome, result.manifest_path)
        rejection_count += 1

        session, outcome, result = self.write_case("artifact_from_other_run")
        save_manifest(
            result.manifest_path,
            replace(result.manifest, run_id="run-other"),
        )
        with self.assertRaises(HandoffGateError):
            self.handoff(session, outcome, result.manifest_path)
        rejection_count += 1

        session, outcome, result = self.write_case("artifact_from_other_revision")
        save_manifest(
            result.manifest_path,
            replace(
                result.manifest,
                brief_revision=result.manifest.brief_revision + 1,
            ),
        )
        with self.assertRaises(HandoffGateError):
            self.handoff(session, outcome, result.manifest_path)
        rejection_count += 1

        self.assertEqual(
            success_count, fixture["assertions"]["handoff_success_cases"]
        )
        self.assertEqual(
            rejection_count, fixture["assertions"]["handoff_rejected_cases"]
        )


if __name__ == "__main__":
    unittest.main()
