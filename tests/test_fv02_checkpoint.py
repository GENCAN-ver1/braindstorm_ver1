from __future__ import annotations

import copy
import tempfile
import unittest
import uuid
from pathlib import Path

from persistence.migrations.add_checkpoint_envelope_v1 import migrate_brief
from runtime.checkpoint import (
    CheckpointStore,
    CheckpointValidationError,
    ConcurrentCheckpointError,
    checkpoint_from_state,
)
from runtime.config_loader import config_from_dict
from runtime.fault_injection import (
    FaultAction,
    FaultInjector,
    FaultPoint,
    FaultRule,
    InjectedInterruption,
    Stage,
)
from runtime.governor_modules import p0, p1, p2
from runtime.full_cycle import FullCycleRunner
from runtime.idempotency import (
    InFlightOperation,
    OperationStatus,
    RecoveryAction,
    RetryPolicy,
    recovery_action,
    stable_idempotency_key,
)
from runtime.reentry import DurableStageRunner
from runtime.state_fingerprint import fingerprint_state


class Fv02Mixin:
    def temp_path(self, name="CONCEPT_BRIEF.md"):
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-{name}"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(
            path.with_name(f".{path.name}.cas.lock").unlink,
            missing_ok=True,
        )
        return path

    def state(self, run_id="run-fv02"):
        state = p0.new_state(
            p0.RoutingInput(
                explicit_mode=p0.Mode.DECIDE,
                research_allowed=True,
                budget=p0.Budget(max_steps=64, max_parallelism=1),
            ),
            run_id=run_id,
        )
        state.decisions = [
            p0.Decision(
                id="locked-concept",
                topic="locked_concept",
                value="durable lifecycle",
                status=p0.DecisionStatus.LOCKED,
                rationale="fixture invariant",
            )
        ]
        p0.validate_state(state)
        return state


class CheckpointStoreTests(Fv02Mixin, unittest.TestCase):
    def test_checkpoint_envelope_round_trips_all_required_fields(self):
        path = self.temp_path()
        session = CheckpointStore().open(path, self.state())
        session.update_progress(
            trace_cursor=7,
            evaluator_rounds_used=1,
            usage_totals={"prompt_tokens": 12, "cost": 0.02},
            artifact_status="PENDING",
        )
        restored = CheckpointStore().open(path, self.state())
        envelope = restored.envelope
        self.assertEqual(envelope.schema_version, 1)
        self.assertEqual(envelope.run_id, "run-fv02")
        self.assertEqual(envelope.trace_cursor, 7)
        self.assertEqual(envelope.evaluator_rounds_used, 1)
        self.assertEqual(envelope.usage_totals["prompt_tokens"], 12)
        self.assertEqual(envelope.artifact_status, "PENDING")
        self.assertTrue(envelope.state_hash.startswith("v1:sha256:"))

    def test_stale_revision_and_out_of_band_write_are_rejected(self):
        path = self.temp_path()
        first = CheckpointStore().open(path, self.state())
        stale = CheckpointStore().open(path, self.state())
        first.enter_stage(Stage.INITIALIZE)
        with self.assertRaises(ConcurrentCheckpointError):
            stale.enter_stage(Stage.INITIALIZE)

    def test_state_hash_tampering_is_rejected(self):
        path = self.temp_path()
        CheckpointStore().open(path, self.state())
        brief = p2.load_brief(path)
        brief.runtime_state.candidates.append({"id": "tampered"})
        p2.save_round(
            path,
            brief,
            brief.runtime_state,
            next_action="tampered out-of-band write",
        )
        with self.assertRaises(CheckpointValidationError):
            CheckpointStore().open(path, self.state())

    def test_legacy_brief_migration_adds_envelope_without_changing_locked_decision(self):
        path = self.temp_path()
        state = self.state()
        p2.save_brief(path, p2.brief_from_state(state, next_action="continue"))
        self.assertIsNone(checkpoint_from_state(p2.load_brief(path).runtime_state))
        migrated = migrate_brief(path)
        self.assertTrue(migrated.migrated)
        self.assertEqual(migrated.envelope.revision, 0)
        self.assertEqual(
            migrated.state.decisions[0].value,
            "durable lifecycle",
        )


class ExternalIdempotencyTests(Fv02Mixin, unittest.TestCase):
    def test_recovery_decision_covers_retry_collect_park_and_receipt_reuse(self):
        for policy, expected in (
            (RetryPolicy.RETRY, RecoveryAction.RETRY),
            (RetryPolicy.COLLECT, RecoveryAction.COLLECT),
            (RetryPolicy.PARK, RecoveryAction.PARK),
        ):
            operation = InFlightOperation(
                operation_id="op",
                stage="RESEARCH",
                idempotency_key="idem:key",
                status=OperationStatus.STARTED,
                retry_policy=policy,
            )
            self.assertEqual(recovery_action(operation, {}), expected)
            self.assertEqual(
                recovery_action(operation, {"idem:key": {"done": True}}),
                RecoveryAction.REUSE_RECEIPT,
            )

    def test_external_receipt_prevents_duplicate_call_after_interruption(self):
        path = self.temp_path()
        calls = []

        def handler(stage, state, context):
            receipt = context.run_external(
                "research-question-1",
                lambda key: calls.append(key) or {"answer": "validated"},
                retry_policy=RetryPolicy.RETRY,
            )
            state.evidence = [
                p0.EvidenceRecord(
                    id="e1",
                    claim=receipt["answer"],
                    classification=p0.KnowledgeStatus.KNOWN,
                    source="fixture",
                )
            ]
            p0.validate_state(state)
            return state

        interrupted = DurableStageRunner(
            handler,
            stages=(Stage.RESEARCH,),
            fault_injector=FaultInjector(
                [
                    FaultRule(
                        Stage.RESEARCH,
                        FaultPoint.AFTER_EXTERNAL_CALL,
                        FaultAction.INTERRUPT,
                    )
                ]
            ),
        )
        with self.assertRaises(InjectedInterruption):
            interrupted.run(str(path), self.state("run-external-idempotency"))
        self.assertEqual(len(calls), 1)

        resumed = DurableStageRunner(handler, stages=(Stage.RESEARCH,)).run(
            str(path), self.state("ignored-incoming-run")
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(resumed.state.evidence[0].claim, "validated")
        key = stable_idempotency_key(
            "run-external-idempotency", "RESEARCH", "research-question-1"
        )
        self.assertIn(key, resumed.envelope.operation_receipts)

    def test_retry_policy_retries_once_after_interruption_before_external_call(self):
        path = self.temp_path()
        calls = []

        def handler(stage, state, context):
            context.run_external(
                "worker-call-1",
                lambda key: calls.append(key) or {"ok": True},
                retry_policy=RetryPolicy.RETRY,
            )
            return state

        interrupted = DurableStageRunner(
            handler,
            stages=(Stage.RESEARCH,),
            fault_injector=FaultInjector(
                [
                    FaultRule(
                        Stage.RESEARCH,
                        FaultPoint.BEFORE_EXTERNAL_CALL,
                        FaultAction.INTERRUPT,
                    )
                ]
            ),
        )
        with self.assertRaises(InjectedInterruption):
            interrupted.run(str(path), self.state("run-before-external"))
        self.assertEqual(calls, [])
        DurableStageRunner(handler, stages=(Stage.RESEARCH,)).run(
            str(path), self.state("ignored")
        )
        self.assertEqual(len(calls), 1)


class FullCycleCheckpointIntegrationTests(Fv02Mixin, unittest.TestCase):
    def config(self):
        return config_from_dict(
            {
                "schema_version": 1,
                "runtime": {
                    "mode": "auto",
                    "parallelism": 1,
                    "budget": {"max_steps": 32, "max_parallelism": 1},
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

    def test_full_cycle_resumes_after_context_checkpoint_interruption(self):
        path = self.temp_path()
        request = {
            "request_id": "run-fv02-full-cycle",
            "text": "Shape a durable concept.",
            "routing": {"ambiguous_concept": True},
        }
        interrupted = FullCycleRunner(
            self.config(),
            fault_injector=FaultInjector(
                [
                    FaultRule(
                        Stage.CONTEXT,
                        FaultPoint.AFTER_CHECKPOINT,
                        FaultAction.INTERRUPT,
                    )
                ]
            ),
        )
        with self.assertRaises(InjectedInterruption):
            interrupted.run(request, brief_path=path)

        summary = FullCycleRunner(self.config()).run(request, brief_path=path)
        self.assertTrue(summary.resumed)
        self.assertEqual(summary.exit_status, "NEEDS_INPUT")
        restored = CheckpointStore().open(path, self.state("ignored"))
        self.assertIsNone(restored.envelope.next_stage)
        self.assertEqual(restored.envelope.last_completed_stage, "FRAME")
        self.assertGreaterEqual(restored.envelope.recovery_count, 1)

    def full_core(self):
        known = lambda text: p0.KnowledgeItem(text, p0.KnowledgeStatus.KNOWN)
        assumption = lambda text: p0.KnowledgeItem(
            text, p0.KnowledgeStatus.ASSUMPTION
        )
        unknown = lambda text: p0.KnowledgeItem(text, p0.KnowledgeStatus.UNKNOWN)
        context = p1.ContextIntake(
            requested_outcome=known("shape a durable concept"),
            current_idea=assumption("staged recovery improves reliability"),
            target_user=known("product team"),
            constraints=[known("must remain reversible")],
            questions=[unknown("preferred interaction")],
        )
        frame = p1.ProblemFrame(
            problem_statement=known("brainstorm runs lose intermediate progress"),
            target_user=known("product team"),
            job_to_be_done=known("resume a concept decision safely"),
            desired_change=known("make every stage recoverable"),
            hard_constraints=[known("must remain reversible")],
            soft_preferences=[known("keep operations lightweight")],
            success_metric=known("resume without duplicate side effects"),
            kill_criterion=known("recovered state differs from baseline"),
            non_goals=[known("implementation execution")],
            time_horizon=known("one working session"),
        )
        definitions = [
            ("c1", p1.ExplorationLens.BASELINE, p1.CandidateComplexity.LOW),
            ("c2", p1.ExplorationLens.ANALOGY, p1.CandidateComplexity.MEDIUM),
            (
                "c3",
                p1.ExplorationLens.CONSTRAINT_REMOVAL,
                p1.CandidateComplexity.HIGH,
            ),
            (
                "c4",
                p1.ExplorationLens.STAKEHOLDER_SHIFT,
                p1.CandidateComplexity.MEDIUM,
            ),
            ("c5", p1.ExplorationLens.SUBSTITUTION, p1.CandidateComplexity.LOW),
        ]
        candidates = [
            p1.Candidate(
                id=candidate_id,
                title=f"Option {candidate_id}",
                one_liner=f"Direction {candidate_id}",
                core_mechanism=f"mechanism-{candidate_id}",
                target_user=known("product team"),
                value_created=f"value-{candidate_id}",
                why_distinct=f"distinct-{candidate_id}",
                key_assumptions=[assumption(f"assumption-{candidate_id}")],
                main_dependency=unknown(f"dependency-{candidate_id}"),
                exploration_lens=lens,
                complexity=complexity,
            )
            for candidate_id, lens, complexity in definitions
        ]
        challenges = [
            p1.CandidateChallenge(
                candidate_id=item.id,
                blindspots=[f"blindspot-{item.id}"],
                assumption_audit=[assumption(f"assumption-{item.id}")],
                pressure_test=[f"pressure-{item.id}"],
            )
            for item in candidates
        ]
        assessments = [
            p1.TradeoffAssessment(
                candidate_id=item.id,
                hard_constraint_violations=[],
                user_value=0.9 if item.id == "c1" else 0.7,
                feasibility=0.9 if item.id == "c1" else 0.6,
                evidence_confidence=0.8 if item.id == "c1" else 0.5,
                reversibility=0.9 if item.id == "c1" else 0.7,
                risk=0.1 if item.id == "c1" else 0.3,
            )
            for item in candidates
        ]
        request = p1.CoreLoopRequest(
            state=self.state("placeholder"),
            context=context,
            problem_frame=frame,
            candidates=candidates,
            challenges=challenges,
            assessments=assessments,
            recommended_candidate_id="c1",
            confidence=0.85,
            cheapest_test="interrupt and resume one fixture run",
        )
        payload = p1._json_ready(request)
        del payload["state"]
        return payload

    def test_staged_full_cycle_matches_p1_and_resumes_every_p1_stage(self):
        request = {
            "request_id": "run-fv02-p1-stages",
            "text": "Shape a durable concept.",
            "routing": {"ambiguous_concept": True},
            "core": self.full_core(),
        }
        baseline_path = self.temp_path("p1-baseline.md")
        baseline = FullCycleRunner(self.config()).run(request, brief_path=baseline_path)
        baseline_state = p2.load_brief(baseline_path).runtime_state
        baseline_hash = fingerprint_state(p0.state_to_dict(baseline_state))
        self.assertEqual(baseline.exit_status, "NEEDS_INPUT")
        legacy_state = p0.new_state(
            p0.RoutingInput(
                ambiguous_concept=True,
                budget=p0.Budget(max_steps=32, max_parallelism=1),
            ),
            run_id="run-fv02-p1-stages",
        )
        legacy_payload = copy.deepcopy(request["core"])
        legacy_payload["state"] = p0.state_to_dict(legacy_state)
        legacy_output = p1.run_core_loop(
            p1.core_loop_request_from_dict(legacy_payload)
        )
        self.assertEqual(
            baseline_hash,
            fingerprint_state(p0.state_to_dict(legacy_output.state)),
        )

        for stage in (
            Stage.CONTEXT,
            Stage.FRAME,
            Stage.DIVERGE,
            Stage.NORMALIZE,
            Stage.CHALLENGE,
            Stage.CONVERGE,
        ):
            with self.subTest(stage=stage.value):
                path = self.temp_path(f"p1-{stage.value}.md")
                interrupted = FullCycleRunner(
                    self.config(),
                    fault_injector=FaultInjector(
                        [
                            FaultRule(
                                stage,
                                FaultPoint.AFTER_CHECKPOINT,
                                FaultAction.INTERRUPT,
                            )
                        ]
                    ),
                )
                with self.assertRaises(InjectedInterruption):
                    interrupted.run(request, brief_path=path)
                resumed = FullCycleRunner(self.config()).run(
                    request, brief_path=path
                )
                self.assertTrue(resumed.resumed)
                restored = p2.load_brief(path).runtime_state
                self.assertEqual(
                    fingerprint_state(p0.state_to_dict(restored)), baseline_hash
                )


if __name__ == "__main__":
    unittest.main()
