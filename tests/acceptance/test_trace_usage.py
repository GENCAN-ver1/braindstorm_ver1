from __future__ import annotations

import copy
import json
import unittest
import uuid
from pathlib import Path

from adapters.evaluator_runtime import TracedEvaluator
from adapters.research_runtime import ResearchRuntime
from adapters.worker_runtime import WorkerRuntime
from observability.events import ActivationKind, EventKind
from observability.trace_sink import TraceSink
from observability.usage_ledger import (
    ObservedExternalError,
    ObservedExternalResult,
    PriceTable,
    ProviderUsage,
    UsageLedger,
)
from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.checkpoint import CheckpointStore
from runtime.fault_injection import FaultInjector, Stage
from runtime.governor_modules import p4, p6
from runtime.reentry import StageContext
from tests.fv04_support import (
    MockExecutor,
    StaticCitationChecker,
    evidence,
    question,
    signals,
    state,
    worker_success,
    worker_tasks,
)


PROJECT_ROOT = Path(__file__).parents[2]


class SequencedResearchProvider:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)

    def research(self, item):
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return copy.deepcopy(outcome)


class UsageExecutor(MockExecutor):
    def usage_receipt(self):
        return ProviderUsage("worker-request-1", 700, 300, 100, 3, 40)


class ObservedEvaluator:
    def evaluate(self, request):
        del request
        invocation = p6.EvaluatorInvocation(
            p6.EvaluationReport([]), p6.RuntimeUsage(token_usage=600, tool_usage=1)
        )
        return ObservedExternalResult(
            invocation,
            ProviderUsage("evaluator-request-1", 500, 100, 0, 1, 25),
        )


class TraceUsageAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(
            (PROJECT_ROOT / "tests/acceptance/fixtures/ac06_trace_usage.json")
            .read_text(encoding="utf-8")
        )
        self.root = PROJECT_ROOT / "tests" / "acceptance"
        self.prefix = f".fv05-{uuid.uuid4().hex}"
        self.ledger = UsageLedger(
            PriceTable.load(PROJECT_ROOT / "config/provider-pricing.json")
        )

    def context(self, run_id, stage):
        path = self.root / f"{self.prefix}-{run_id}.md"
        trace_path = self.root / f"{self.prefix}-{run_id}.trace.json"
        for target in (path, trace_path):
            self.addCleanup(target.unlink, missing_ok=True)
            self.addCleanup(
                target.with_name(f".{target.name}.cas.lock").unlink,
                missing_ok=True,
            )
            self.addCleanup(
                target.with_name(f".{target.name}.lock").unlink,
                missing_ok=True,
            )
        sink = TraceSink(trace_path)
        session = CheckpointStore(
            trace_sink=sink, usage_ledger=self.ledger
        ).open(path, state(run_id), initial_next_stage=stage)
        session.enter_stage(stage)
        session.consume_budget(BudgetGuard(), stage, "stage", BudgetChargeKind.STAGE)
        return session, StageContext(
            session, stage, FaultInjector.disabled(), BudgetGuard()
        ), sink

    def test_ac_06_automatic_activation_and_real_usage_cost_trace(self):
        traces = []

        research_session, research_context, research_sink = self.context(
            "run-ac06-research", Stage.RESEARCH
        )
        first_usage = ProviderUsage("research-request-1", 1000, 200, 100, 2, 30)
        second_usage = ProviderUsage("research-request-2", 800, 150, 50, 1, 20)
        provider = SequencedResearchProvider(
            [
                ObservedExternalError("provider timeout", first_usage),
                ObservedExternalResult(
                    p4.ProviderResearchResult([evidence("q1")], []), second_usage
                ),
            ]
        )
        runtime = ResearchRuntime(
            provider_name="fixture-research", model_name="fixture-model"
        )
        failed = runtime.execute(
            research_session.state,
            [question("q1")],
            provider,
            StaticCitationChecker(),
            research_context,
        )
        self.assertTrue(failed.failures)
        recovered = runtime.execute(
            research_session.state,
            [question("q1")],
            provider,
            StaticCitationChecker(),
            research_context,
        )
        self.assertEqual(recovered.validated_question_ids, ["q1"])
        research_session.mark_recovered()
        traces.append((research_session, research_sink.read()))

        worker_session, worker_context, worker_sink = self.context(
            "run-ac06-worker", Stage.DIVERGE
        )
        tasks = worker_tasks(worker_session.state)[:2]
        executor = UsageExecutor(
            {
                "worker-1": worker_success(
                    "worker-1", tasks[0].payload.assigned_lens, "c1", "guided interview"
                ),
                "worker-2": worker_success(
                    "worker-2", tasks[1].payload.assigned_lens, "c2", "design studio"
                ),
            }
        )
        WorkerRuntime(
            executor_name="fixture-workers", model_name="fixture-model"
        ).execute(
            worker_session.state,
            signals(),
            tasks,
            executor,
            worker_context,
        )
        traces.append((worker_session, worker_sink.read()))

        evaluator_session, evaluator_context, evaluator_sink = self.context(
            "run-ac06-evaluator", Stage.EVALUATE
        )
        evaluator = TracedEvaluator(
            ObservedEvaluator(),
            evaluator_context,
            provider_name="fixture-evaluator",
            model_name="fixture-model",
        )
        evaluator.evaluate(
            p6.EvaluatorInput(
                confirmed_frame={},
                candidates=[],
                recommendation=None,
                evaluation_criteria=list(p6.EvaluationCheck),
                evidence_summary=[],
                output_contract={},
            )
        )
        traces.append((evaluator_session, evaluator_sink.read()))

        activation_values = {
            event["details"]["activation"]
            for _, trace in traces
            for event in trace["events"]
            if event["kind"] == EventKind.ACTIVATION.value
        }
        self.assertEqual(
            activation_values,
            {
                ActivationKind.P4_RESEARCH.value,
                ActivationKind.P5_WORKER.value,
                ActivationKind.P6_EVALUATOR.value,
            },
        )
        self.assertNotIn(ActivationKind.COUNCIL.value, activation_values)

        research_kinds = [item["kind"] for item in traces[0][1]["events"]]
        self.assertIn(EventKind.GATE_DECISION.value, research_kinds)
        self.assertIn(EventKind.EXTERNAL_CALL_RETRY.value, research_kinds)
        self.assertIn(EventKind.EXTERNAL_CALL_FAILED.value, research_kinds)
        self.assertIn(EventKind.CHECKPOINT_SAVED.value, research_kinds)
        self.assertIn(EventKind.RECOVERY.value, research_kinds)

        for session, trace in traces:
            receipts = trace["usage_receipts"]
            self.assertTrue(receipts)
            self.assertTrue(
                all(
                    set(item) == set(self.fixture["provider_receipt_fields"])
                    for item in receipts
                )
            )
            summary = trace["summary"]
            self.assertEqual(
                summary["prompt_tokens"],
                sum(item["prompt_tokens"] or 0 for item in receipts),
            )
            self.assertEqual(
                summary["tool_calls"],
                sum(item["tool_calls"] or 0 for item in receipts),
            )
            self.assertEqual(
                summary["calculated_cost"],
                round(sum(item["calculated_cost"] or 0 for item in receipts), 12),
            )
            self.assertEqual(
                session.envelope.usage_totals["prompt_tokens"],
                summary["prompt_tokens"],
            )
            self.assertEqual(session.envelope.trace_cursor, trace["events"][-1]["trace_cursor"])

        research_receipts = traces[0][1]["usage_receipts"]
        self.assertEqual(len(research_receipts), 2)
        self.assertEqual(
            {item["request_id"] for item in research_receipts},
            {"research-request-1", "research-request-2"},
        )


if __name__ == "__main__":
    unittest.main()
