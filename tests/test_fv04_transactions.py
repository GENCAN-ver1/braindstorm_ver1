from __future__ import annotations

import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from adapters.research_runtime import ResearchRuntime
from adapters.worker_runtime import WorkerRuntime
from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.checkpoint import CheckpointStore
from runtime.failure_ledger import (
    FailureCategory,
    FailureEntry,
    FailureLedger,
    classify_exception,
)
from runtime.fault_injection import (
    FaultAction,
    FaultInjector,
    FaultPoint,
    FaultRule,
    InjectedInterruption,
    Stage,
)
from runtime.governor_modules import p0, p1, p2, p4, p5
from runtime.reentry import DurableStageRunner, StageContext
from runtime.state_fingerprint import fingerprint_state
from runtime.transaction import (
    CommitPolicy,
    ConcurrentMainStateError,
    StateTransaction,
    TransactionKind,
    TransactionStatus,
)
from tests.fv04_support import (
    MockExecutor,
    ResearchProvider,
    StaticCitationChecker,
    candidate,
    evidence,
    question,
    signals,
    state,
    worker_success,
    worker_tasks,
)


class Fv04Mixin:
    def temp_path(self):
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-fv04.md"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(
            path.with_name(f".{path.name}.cas.lock").unlink,
            missing_ok=True,
        )
        return path

    def context(self, value, stage):
        path = self.temp_path()
        session = CheckpointStore().open(path, value, initial_next_stage=stage)
        session.enter_stage(stage)
        session.consume_budget(
            BudgetGuard(), stage, "stage", BudgetChargeKind.STAGE
        )
        return path, session, StageContext(
            session, stage, FaultInjector.disabled(), BudgetGuard()
        )


class TransactionTests(Fv04Mixin, unittest.TestCase):
    def test_snapshot_and_commit_are_copy_on_write(self):
        original = state()
        transaction = StateTransaction(
            original, kind=TransactionKind.WORKER, operation_id="workers"
        )
        snapshot = transaction.snapshot()
        snapshot.frame.problem.statement = "mutated worker copy"
        self.assertNotEqual(snapshot.frame.problem, original.frame.problem)
        transaction.stage_candidate(
            candidate("c1", p1.ExplorationLens.BASELINE, "guided interview")
        )
        result = transaction.commit(original)
        self.assertEqual(result.status, TransactionStatus.COMMITTED)
        self.assertEqual(original.candidates, [])
        self.assertEqual([item["id"] for item in result.state.candidates], ["c1"])
        self.assertEqual(result.state.decisions, original.decisions)

    def test_concurrent_main_state_change_rejects_commit(self):
        original = state()
        transaction = StateTransaction(
            original, kind=TransactionKind.WORKER, operation_id="workers"
        )
        transaction.stage_candidate(
            candidate("c1", p1.ExplorationLens.BASELINE, "guided interview")
        )
        changed = copy.deepcopy(original)
        changed.candidates.append({"id": "other", "core_mechanism": "other"})
        with self.assertRaises(ConcurrentMainStateError):
            transaction.commit(changed)

    def test_failure_ledger_is_strict_append_only_and_checkpointed(self):
        value = state()
        path, session, context = self.context(value, Stage.DIVERGE)
        del path, context
        entry = FailureEntry.create(
            run_id=value.run.id,
            stage=Stage.DIVERGE,
            operation_id="worker-1",
            provider="fixture",
            category=FailureCategory.TIMEOUT,
            message="worker timed out",
            idempotency_key="idem:fixture",
        )
        self.assertTrue(session.record_failure(entry))
        self.assertFalse(session.record_failure(entry))
        restored = CheckpointStore().open(session.path, state("ignored"))
        ledger = FailureLedger.from_records(restored.envelope.failure_ledger)
        self.assertEqual(len(ledger.entries), 1)
        self.assertEqual(ledger.entries[0].category, FailureCategory.TIMEOUT)
        self.assertEqual(restored.envelope.trace_cursor, 1)

    def test_failure_taxonomy_distinguishes_required_categories(self):
        class HttpError(RuntimeError):
            def __init__(self, status_code):
                self.status_code = status_code
                super().__init__(f"provider status {status_code}")

        self.assertEqual(
            classify_exception(TimeoutError(), default=FailureCategory.PROVIDER_ERROR),
            FailureCategory.TIMEOUT,
        )
        self.assertEqual(
            classify_exception(HttpError(429), default=FailureCategory.PROVIDER_ERROR),
            FailureCategory.RATE_LIMIT,
        )
        self.assertEqual(
            classify_exception(HttpError(503), default=FailureCategory.PROVIDER_ERROR),
            FailureCategory.PROVIDER_5XX,
        )
        self.assertEqual(
            classify_exception(
                json.JSONDecodeError("bad", "{", 0),
                default=FailureCategory.PROVIDER_ERROR,
            ),
            FailureCategory.INVALID_JSON,
        )

    def test_fv03_envelope_without_failure_ledger_is_migrated_on_save(self):
        path = self.temp_path()
        CheckpointStore().open(path, state())
        brief = p2.load_brief(path)
        record = next(
            item
            for item in brief.runtime_state.deferred
            if item.get("type") == "brainstorm-governor-checkpoint-v1"
        )
        record["envelope"].pop("failure_ledger")
        p2.save_round(path, brief, brief.runtime_state, next_action="legacy FV-03")
        restored = CheckpointStore().open(path, state("ignored"))
        self.assertEqual(restored.envelope.failure_ledger, [])
        restored.mark_recovered()
        saved = p2.load_brief(path)
        saved_record = next(
            item
            for item in saved.runtime_state.deferred
            if item.get("type") == "brainstorm-governor-checkpoint-v1"
        )
        self.assertIn("failure_ledger", saved_record["envelope"])


class AdapterBehaviorTests(Fv04Mixin, unittest.TestCase):
    def test_research_invalid_json_is_discarded_and_recorded(self):
        value = state()
        _, session, context = self.context(value, Stage.RESEARCH)
        provider = ResearchProvider({"q1": "{invalid"})
        outcome = ResearchRuntime(provider_name="fixture-research").execute(
            value,
            [question("q1")],
            provider,
            StaticCitationChecker(),
            context,
            policy=CommitPolicy.ALL_OR_NOTHING,
        )
        self.assertEqual(outcome.transaction.status, TransactionStatus.DISCARDED)
        self.assertEqual(outcome.state.evidence, value.evidence)
        self.assertEqual(outcome.failures[0].category, FailureCategory.INVALID_JSON)
        self.assertEqual(len(session.envelope.failure_ledger), 1)
        self.assertIsNone(session.envelope.in_flight_operation)

    def test_research_citation_failure_never_becomes_known_evidence(self):
        value = state()
        _, session, context = self.context(value, Stage.RESEARCH)
        provider = ResearchProvider(
            {"q1": p4.ProviderResearchResult([evidence("q1")], [])}
        )
        outcome = ResearchRuntime(provider_name="fixture-research").execute(
            value,
            [question("q1")],
            provider,
            StaticCitationChecker(False),
            context,
            policy=CommitPolicy.ALL_OR_NOTHING,
        )
        self.assertEqual(outcome.transaction.status, TransactionStatus.DISCARDED)
        self.assertEqual(outcome.state.evidence, value.evidence)
        self.assertEqual(outcome.failures[0].category, FailureCategory.CITATION_ERROR)
        self.assertEqual(
            FailureLedger.from_records(session.envelope.failure_ledger)
            .entries[0]
            .category,
            FailureCategory.CITATION_ERROR,
        )

    def test_worker_default_validated_partial_commits_only_valid_results(self):
        value = state()
        _, session, context = self.context(value, Stage.DIVERGE)
        tasks = worker_tasks(value)[:2]
        executor = MockExecutor(
            {
                "worker-1": worker_success(
                    "worker-1", p1.ExplorationLens.BASELINE, "c1", "guided interview"
                ),
                "worker-2": p5.WorkerExecutionResult(
                    "worker-2",
                    p5.WorkerKind.EXPLORATION,
                    False,
                    error="worker timeout",
                ),
            }
        )
        before_frame = copy.deepcopy(value.frame)
        before_decisions = copy.deepcopy(value.decisions)
        before_evidence = copy.deepcopy(value.evidence)
        outcome = WorkerRuntime(executor_name="fixture-workers").execute(
            value,
            signals(),
            tasks,
            executor,
            context,
        )
        self.assertEqual(outcome.transaction.status, TransactionStatus.COMMITTED)
        self.assertEqual([item["id"] for item in outcome.state.candidates], ["c1"])
        self.assertEqual(outcome.state.frame, before_frame)
        self.assertEqual(outcome.state.decisions, before_decisions)
        self.assertEqual(outcome.state.evidence, before_evidence)
        self.assertEqual(outcome.failures[0].category, FailureCategory.TIMEOUT)
        self.assertEqual(len(session.envelope.failure_ledger), 1)

    def test_duplicate_worker_candidate_is_ledgered_and_not_duplicated(self):
        value = state()
        _, session, context = self.context(value, Stage.DIVERGE)
        tasks = worker_tasks(value)[:2]
        executor = MockExecutor(
            {
                "worker-1": worker_success(
                    "worker-1", p1.ExplorationLens.BASELINE, "c1", "guided interview"
                ),
                "worker-2": worker_success(
                    "worker-2", p1.ExplorationLens.ANALOGY, "c2", "Guided interview!!!"
                ),
            }
        )
        outcome = WorkerRuntime(executor_name="fixture-workers").execute(
            value, signals(), tasks, executor, context
        )
        self.assertEqual([item["id"] for item in outcome.state.candidates], ["c1"])
        self.assertTrue(
            any(
                item.category is FailureCategory.DUPLICATE_CANDIDATE
                for item in outcome.failures
            )
        )
        categories = {
            item.category
            for item in FailureLedger.from_records(
                session.envelope.failure_ledger
            ).entries
        }
        self.assertIn(FailureCategory.DUPLICATE_CANDIDATE, categories)

    def test_worker_receipt_recovery_does_not_repeat_executor_or_candidate(self):
        path = self.temp_path()
        value = state("run-fv04-resume")
        tasks = worker_tasks(value)[:2]
        executor = MockExecutor(
            {
                "worker-1": worker_success(
                    "worker-1", p1.ExplorationLens.BASELINE, "c1", "guided interview"
                ),
                "worker-2": worker_success(
                    "worker-2", p1.ExplorationLens.ANALOGY, "c2", "design studio"
                ),
            }
        )
        runtime = WorkerRuntime(executor_name="fixture-workers")

        def handler(stage, working, context):
            return runtime.execute(
                working, signals(), tasks, executor, context
            ).state

        interrupted = DurableStageRunner(
            handler,
            stages=(Stage.DIVERGE,),
            fault_injector=FaultInjector(
                [
                    FaultRule(
                        Stage.DIVERGE,
                        FaultPoint.BEFORE_COMMIT,
                        FaultAction.INTERRUPT,
                    )
                ]
            ),
        )
        with self.assertRaises(InjectedInterruption):
            interrupted.run(str(path), value)
        self.assertEqual(executor.open_calls, 1)

        resumed = DurableStageRunner(handler, stages=(Stage.DIVERGE,)).run(
            str(path), state("ignored")
        )
        self.assertEqual(executor.open_calls, 1)
        self.assertEqual(
            [item["id"] for item in resumed.state.candidates], ["c1", "c2"]
        )
        self.assertEqual(len({item["id"] for item in resumed.state.candidates}), 2)


if __name__ == "__main__":
    unittest.main()
