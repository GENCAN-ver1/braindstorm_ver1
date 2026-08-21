"""Transactional P5 Worker adapter over one isolated durable batch call."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from adapters._runtime_common import record_operational_failure
from adapters.research_runtime import (
    provider_result_from_value,
    provider_result_to_dict,
    runtime_evidence_records,
)
from observability.events import ActivationKind
from observability.usage_ledger import ObservedExternalResult, ProviderUsage
from runtime.failure_ledger import FailureCategory, FailureEntry, classify_exception
from runtime.governor_modules import p0, p1, p4, p5
from runtime.idempotency import RetryPolicy
from runtime.reentry import StageContext
from runtime.transaction import (
    CommitPolicy,
    DuplicateCandidateError,
    StateTransaction,
    TransactionKind,
    TransactionResult,
)


class WorkerRuntimeError(p0.ContractError):
    """Raised when a normalized Worker batch receipt violates its contract."""


@dataclass(frozen=True)
class WorkerRuntimeOutcome:
    state: p0.RuntimeState
    successful_worker_ids: list[str]
    failed_worker_ids: list[str]
    failures: list[FailureEntry]
    transaction: TransactionResult
    synthesis_ready: bool


class WorkerRuntime:
    def __init__(
        self,
        *,
        executor_name: str = "isolated-worker-executor",
        model_name: str = "UNSPECIFIED",
    ) -> None:
        if not isinstance(executor_name, str) or not executor_name.strip():
            raise ValueError("executor_name must be a non-empty string")
        self.executor_name = executor_name.strip()
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        self.model_name = model_name.strip()

    def execute(
        self,
        state: p0.RuntimeState,
        signals: p5.ParallelGateSignals,
        tasks: Sequence[p5.WorkerTask],
        executor: p5.IsolatedWorkerExecutor,
        context: StageContext,
        *,
        citation_checker: p4.CitationSupportChecker | None = None,
        policy: CommitPolicy = CommitPolicy.VALIDATED_PARTIAL,
    ) -> WorkerRuntimeOutcome:
        p0.validate_state(state)
        task_items = copy.deepcopy(list(tasks))
        gate = p5.parallel_gate(state, signals)
        context.record_gate_decision(
            "parallel",
            gate.enabled,
            "; ".join(gate.reasons),
        )
        transaction = StateTransaction(
            state,
            kind=TransactionKind.WORKER,
            operation_id="worker-batch",
        )
        failures: list[FailureEntry] = []
        successful: list[str] = []
        failed: list[str] = []
        receipt: Mapping[str, Any] | None = None

        try:
            if not gate.enabled:
                raise _GateClosed()
            receipt_value = context.run_external(
                "worker-batch",
                lambda key: _observed_worker_outcome(
                    p5.orchestrate_workers(
                        transaction.snapshot(),
                        signals,
                        task_items,
                        executor,
                        citation_checker=citation_checker,
                    ),
                    executor,
                ),
                retry_policy=RetryPolicy.PARK,
                provider=self.executor_name,
                model=self.model_name,
                activation=ActivationKind.P5_WORKER,
            )
            receipt = worker_receipt_from_value(receipt_value)
        except _GateClosed:
            pass
        except Exception as error:
            entry = record_operational_failure(
                context,
                operation_id="worker-batch",
                provider=self.executor_name,
                category=classify_exception(
                    error, default=FailureCategory.WORKER_ERROR
                ),
                message=str(error),
            )
            failures.append(entry)
            transaction.register_failure(entry.failure_id)

        if receipt is not None:
            successful = list(receipt["successful_worker_ids"])
            for worker_id, message in receipt["failed_workers"].items():
                entry = self._record(
                    context,
                    transaction,
                    operation_id=worker_id,
                    category=classify_exception(
                        RuntimeError(message), default=FailureCategory.WORKER_ERROR
                    ),
                    message=message,
                )
                failures.append(entry)
                failed.append(worker_id)

            for item in receipt["eliminated_duplicates"]:
                entry = self._record(
                    context,
                    transaction,
                    operation_id=item["worker_id"],
                    category=FailureCategory.DUPLICATE_CANDIDATE,
                    message=item["reason"],
                )
                failures.append(entry)

            for group in receipt["source_conflicts"]:
                entry = self._record(
                    context,
                    transaction,
                    operation_id="source-conflict:" + ",".join(group),
                    category=FailureCategory.SOURCE_CONFLICT,
                    message="conflicting evidence sources: " + ", ".join(group),
                )
                failures.append(entry)

            for candidate_value in receipt["candidates"]:
                try:
                    candidate = p1.candidate_from_dict(candidate_value)
                    p1.validate_candidate(candidate, "worker.candidate")
                    transaction.stage_candidate(p1._json_ready(candidate))
                except Exception as error:
                    entry = self._record(
                        context,
                        transaction,
                        operation_id=f"candidate:{candidate_value.get('id', 'unknown')}",
                        category=(
                            FailureCategory.DUPLICATE_CANDIDATE
                            if isinstance(error, DuplicateCandidateError)
                            else classify_exception(
                                error, default=FailureCategory.SCHEMA_ERROR
                            )
                        ),
                        message=str(error),
                    )
                    failures.append(entry)

            self._stage_research_results(
                state,
                task_items,
                receipt,
                citation_checker,
                context,
                transaction,
                failures,
            )

        if failures and not (
            transaction.staging.candidates or transaction.staging.evidence
        ):
            transaction_result = transaction.discard(
                state, reason="worker batch produced no validated staging records"
            )
        else:
            transaction_result = transaction.commit(state, policy=policy)
        return WorkerRuntimeOutcome(
            state=transaction_result.state,
            successful_worker_ids=successful,
            failed_worker_ids=failed,
            failures=failures,
            transaction=transaction_result,
            synthesis_ready=(
                receipt is not None
                and bool(receipt["synthesis_ready"])
                and transaction_result.discarded_reason is None
            ),
        )

    def _stage_research_results(
        self,
        state: p0.RuntimeState,
        tasks: list[p5.WorkerTask],
        receipt: Mapping[str, Any],
        citation_checker: p4.CitationSupportChecker | None,
        context: StageContext,
        transaction: StateTransaction,
        failures: list[FailureEntry],
    ) -> None:
        payload = provider_result_from_value(receipt["research_result"])
        if not payload.evidence and not payload.numeric_claims:
            return
        if citation_checker is None:
            entry = self._record(
                context,
                transaction,
                operation_id="research-results",
                category=FailureCategory.CITATION_ERROR,
                message="research worker results require citation checker",
            )
            failures.append(entry)
            return
        questions = {
            task.payload.question.id: task.payload.question
            for task in tasks
            if task.kind is p5.WorkerKind.RESEARCH
            and isinstance(task.payload, p5.ResearchWorkerInput)
        }
        evidence_by_question: dict[str, list[p4.ResearchEvidenceRecord]] = {}
        numeric_by_question: dict[str, list[p4.NumericClaim]] = {}
        for item in payload.evidence:
            evidence_by_question.setdefault(item.question_id, []).append(item)
        for item in payload.numeric_claims:
            numeric_by_question.setdefault(item.question_id, []).append(item)
        for question_id in sorted(set(evidence_by_question) | set(numeric_by_question)):
            try:
                question = questions[question_id]
                validated = p4.validate_provider_result(
                    question,
                    p4.ProviderResearchResult(
                        evidence_by_question.get(question_id, []),
                        numeric_by_question.get(question_id, []),
                    ),
                    citation_checker,
                )
                transaction.stage_batch(evidence=runtime_evidence_records(validated))
            except Exception as error:
                entry = self._record(
                    context,
                    transaction,
                    operation_id=f"research:{question_id}",
                    category=classify_exception(
                        error, default=FailureCategory.SCHEMA_ERROR
                    ),
                    message=str(error),
                )
                failures.append(entry)

    def _record(
        self,
        context: StageContext,
        transaction: StateTransaction,
        *,
        operation_id: str,
        category: FailureCategory,
        message: str,
    ) -> FailureEntry:
        entry = record_operational_failure(
            context,
            operation_id=operation_id,
            provider=self.executor_name,
            category=category,
            message=message,
        )
        transaction.register_failure(entry.failure_id)
        return entry


def worker_outcome_to_dict(outcome: p5.OrchestrationOutcome) -> dict[str, Any]:
    if not isinstance(outcome, p5.OrchestrationOutcome):
        raise WorkerRuntimeError("worker outcome must be OrchestrationOutcome")
    return {
        "successful_worker_ids": list(outcome.successful_worker_ids),
        "failed_workers": copy.deepcopy(outcome.failed_workers),
        "candidates": [p1._json_ready(item) for item in outcome.normalized_candidates],
        "eliminated_duplicates": [
            {
                "worker_id": item.worker_id,
                "candidate_id": item.candidate_id,
                "reason": item.reason,
            }
            for item in outcome.eliminated_duplicates
        ],
        "research_result": provider_result_to_dict(
            p4.ProviderResearchResult(outcome.evidence, outcome.numeric_claims)
        ),
        "source_conflicts": copy.deepcopy(outcome.source_conflicts),
        "synthesis_ready": outcome.synthesis_ready,
    }


class _GateClosed(Exception):
    pass


def _observed_worker_outcome(
    outcome: p5.OrchestrationOutcome,
    executor: p5.IsolatedWorkerExecutor,
) -> Any:
    payload = worker_outcome_to_dict(outcome)
    usage_method = getattr(executor, "usage_receipt", None)
    if not callable(usage_method):
        return payload
    usage = usage_method()
    if not isinstance(usage, ProviderUsage):
        raise WorkerRuntimeError("executor usage_receipt() must return ProviderUsage")
    return ObservedExternalResult(payload, usage)


def worker_receipt_from_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise WorkerRuntimeError("worker receipt must be an object")
    expected = {
        "successful_worker_ids",
        "failed_workers",
        "candidates",
        "eliminated_duplicates",
        "research_result",
        "source_conflicts",
        "synthesis_ready",
    }
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing or unknown:
        raise WorkerRuntimeError(
            f"invalid worker receipt keys; missing={sorted(missing)}, "
            f"unknown={sorted(unknown)}"
        )
    successful = _strings(value["successful_worker_ids"], "successful_worker_ids")
    failed_value = value["failed_workers"]
    if not isinstance(failed_value, Mapping):
        raise WorkerRuntimeError("failed_workers must be an object")
    failed = {
        _nonempty(key, "failed_workers key"): _nonempty(item, "failed_workers value")
        for key, item in failed_value.items()
    }
    candidates = _objects(value["candidates"], "candidates")
    eliminated = _objects(value["eliminated_duplicates"], "eliminated_duplicates")
    for item in eliminated:
        if set(item) != {"worker_id", "candidate_id", "reason"}:
            raise WorkerRuntimeError("eliminated duplicate record has invalid keys")
        for key in item:
            _nonempty(item[key], f"eliminated_duplicates.{key}")
    source_conflicts = value["source_conflicts"]
    if not isinstance(source_conflicts, list):
        raise WorkerRuntimeError("source_conflicts must be an array")
    conflicts = [
        _strings(item, f"source_conflicts[{index}]")
        for index, item in enumerate(source_conflicts)
    ]
    if type(value["synthesis_ready"]) is not bool:
        raise WorkerRuntimeError("synthesis_ready must be boolean")
    research_result = provider_result_to_dict(
        provider_result_from_value(value["research_result"])
    )
    return {
        "successful_worker_ids": successful,
        "failed_workers": failed,
        "candidates": candidates,
        "eliminated_duplicates": eliminated,
        "research_result": research_result,
        "source_conflicts": conflicts,
        "synthesis_ready": value["synthesis_ready"],
    }


def _objects(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        raise WorkerRuntimeError(f"{path} must be an array of objects")
    return [copy.deepcopy(dict(item)) for item in value]


def _strings(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise WorkerRuntimeError(f"{path} must be an array")
    result = [_nonempty(item, path) for item in value]
    if len(result) != len(set(result)):
        raise WorkerRuntimeError(f"{path} must contain unique strings")
    return result


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerRuntimeError(f"{path} must be a non-empty string")
    return value.strip()
