from __future__ import annotations

import copy
import tempfile
import unittest
import uuid
from pathlib import Path

from adapters.research_runtime import ResearchRuntime
from adapters.worker_runtime import WorkerRuntime
from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.checkpoint import CheckpointStore
from runtime.failure_ledger import FailureCategory, FailureLedger
from runtime.fault_injection import FaultInjector, Stage
from runtime.governor_modules import p0, p1, p4, p5
from runtime.reentry import StageContext
from runtime.state_fingerprint import fingerprint_state
from runtime.transaction import CommitPolicy, TransactionStatus
from tests.fv04_support import (
    MockExecutor,
    ResearchProvider,
    StaticCitationChecker,
    evidence,
    question,
    signals,
    state,
    worker_success,
    worker_tasks,
)


class ResearchWorkerIsolationAcceptanceTests(unittest.TestCase):
    def temp_path(self):
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-ac03.md"
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
        context = StageContext(
            session, stage, FaultInjector.disabled(), BudgetGuard()
        )
        return path, session, context

    def test_ac_03_research_and_worker_failures_do_not_pollute_main_state(self):
        research_state = state("run-ac03-research")
        research_before = fingerprint_state(p0.state_to_dict(research_state))
        _, research_session, research_context = self.context(
            research_state, Stage.RESEARCH
        )
        questions = [question("q1"), question("q2"), question("q3")]
        provider = ResearchProvider(
            {
                "q1": p4.ProviderResearchResult([evidence("q1")], []),
                "q2": p4.ProviderResearchResult([evidence("q2")], []),
                "q3": TimeoutError("provider timeout"),
            }
        )
        research = ResearchRuntime(provider_name="fixture-research").execute(
            research_state,
            questions,
            provider,
            StaticCitationChecker(),
            research_context,
            policy=CommitPolicy.ALL_OR_NOTHING,
        )
        self.assertEqual(research.transaction.status, TransactionStatus.DISCARDED)
        self.assertEqual(
            fingerprint_state(p0.state_to_dict(research.state)), research_before
        )
        self.assertFalse(
            any(item.claim == question("q3").claim for item in research.state.evidence)
        )
        self.assertEqual(research.failures[0].category, FailureCategory.TIMEOUT)
        self.assertEqual(len(research_session.envelope.failure_ledger), 1)

        worker_state = state("run-ac03-worker")
        worker_before = fingerprint_state(p0.state_to_dict(worker_state))
        frame_before = copy.deepcopy(worker_state.frame)
        decisions_before = copy.deepcopy(worker_state.decisions)
        evidence_before = copy.deepcopy(worker_state.evidence)
        _, worker_session, worker_context = self.context(
            worker_state, Stage.DIVERGE
        )
        tasks = worker_tasks(worker_state)
        executor = MockExecutor(
            {
                "worker-1": worker_success(
                    "worker-1", p1.ExplorationLens.BASELINE, "c1", "guided interview"
                ),
                "worker-2": worker_success(
                    "worker-2", p1.ExplorationLens.ANALOGY, "c2", "design studio"
                ),
                "worker-3": p5.WorkerExecutionResult(
                    "worker-3",
                    p5.WorkerKind.EXPLORATION,
                    False,
                    error="worker timeout",
                ),
            }
        )
        workers = WorkerRuntime(executor_name="fixture-workers").execute(
            worker_state,
            signals(),
            tasks,
            executor,
            worker_context,
            policy=CommitPolicy.ALL_OR_NOTHING,
        )
        self.assertEqual(workers.transaction.status, TransactionStatus.DISCARDED)
        self.assertEqual(
            fingerprint_state(p0.state_to_dict(workers.state)), worker_before
        )
        self.assertEqual(workers.state.frame, frame_before)
        self.assertEqual(workers.state.decisions, decisions_before)
        self.assertEqual(workers.state.evidence, evidence_before)
        ledger = FailureLedger.from_records(worker_session.envelope.failure_ledger)
        self.assertEqual(len(ledger.entries), 1)
        self.assertEqual(ledger.entries[0].category, FailureCategory.TIMEOUT)

    def test_invalid_worker_output_cannot_create_half_write(self):
        value = state("run-ac03-invalid")
        before = fingerprint_state(p0.state_to_dict(value))
        _, session, context = self.context(value, Stage.DIVERGE)
        tasks = worker_tasks(value)[:2]
        executor = MockExecutor(
            {
                "worker-1": p5.WorkerExecutionResult(
                    "worker-1",
                    p5.WorkerKind.EXPLORATION,
                    True,
                    output=p5.ExplorationWorkerOutput([{"id": "invalid"}]),
                ),
                "worker-2": worker_success(
                    "worker-2", p1.ExplorationLens.ANALOGY, "c2", "design studio"
                ),
            }
        )
        outcome = WorkerRuntime(executor_name="fixture-workers").execute(
            value,
            signals(),
            tasks,
            executor,
            context,
            policy=CommitPolicy.ALL_OR_NOTHING,
        )
        self.assertEqual(outcome.transaction.status, TransactionStatus.DISCARDED)
        self.assertEqual(fingerprint_state(p0.state_to_dict(outcome.state)), before)
        self.assertEqual(outcome.state.candidates, [])
        self.assertTrue(session.envelope.failure_ledger)


if __name__ == "__main__":
    unittest.main()

