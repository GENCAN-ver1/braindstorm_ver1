"""Transactional P4 Research adapter over the durable external-call boundary."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from adapters._runtime_common import record_operational_failure
from observability.events import ActivationKind
from observability.usage_ledger import ObservedExternalResult
from runtime.failure_ledger import FailureCategory, FailureEntry, classify_exception
from runtime.governor_modules import p0, p4
from runtime.idempotency import RetryPolicy
from runtime.reentry import StageContext
from runtime.transaction import (
    CommitPolicy,
    StateTransaction,
    TransactionKind,
    TransactionResult,
)


class ResearchRuntimeError(p0.ContractError):
    """Raised when the runtime adapter itself receives an invalid contract."""


@dataclass(frozen=True)
class ResearchRuntimeOutcome:
    state: p0.RuntimeState
    gate: p4.ResearchGateDecision
    validated_question_ids: list[str]
    unresolved_question_ids: list[str]
    failures: list[FailureEntry]
    transaction: TransactionResult
    exit_status: p0.ExitStatus | None


class ResearchRuntime:
    def __init__(
        self,
        *,
        provider_name: str = "research-provider",
        model_name: str = "UNSPECIFIED",
    ) -> None:
        if not isinstance(provider_name, str) or not provider_name.strip():
            raise ValueError("provider_name must be a non-empty string")
        self.provider_name = provider_name.strip()
        if not isinstance(model_name, str) or not model_name.strip():
            raise ValueError("model_name must be a non-empty string")
        self.model_name = model_name.strip()

    def execute(
        self,
        state: p0.RuntimeState,
        questions: Sequence[p4.ResearchQuestion],
        provider: p4.ResearchProvider,
        citation_checker: p4.CitationSupportChecker,
        context: StageContext,
        *,
        policy: CommitPolicy = CommitPolicy.VALIDATED_PARTIAL,
    ) -> ResearchRuntimeOutcome:
        p0.validate_state(state)
        question_items = list(questions)
        for question in question_items:
            p4.validate_research_question(question)
        gate = p4.research_gate(question_items)
        gate_enabled = gate.required and state.research_allowed
        context.record_gate_decision(
            "research",
            gate_enabled,
            _research_gate_reason(gate, state.research_allowed),
        )
        transaction = StateTransaction(
            state,
            kind=TransactionKind.RESEARCH,
            operation_id="research-batch",
        )
        failures: list[FailureEntry] = []
        validated_ids: list[str] = []
        staged_evidence_ids: set[str] = set()
        staged_numeric_ids: set[str] = set()

        if gate.required and not state.research_allowed:
            entry = record_operational_failure(
                context,
                operation_id="research-gate",
                provider=self.provider_name,
                category=FailureCategory.RESEARCH_DISABLED,
                message="research is required but research_allowed=false",
            )
            failures.append(entry)
            transaction.register_failure(entry.failure_id)

        required = set(gate.required_question_ids)
        for question in question_items:
            if question.id not in required or not state.research_allowed:
                continue
            operation_id = f"research:{question.id}"
            try:
                receipt = context.run_external(
                    operation_id,
                    lambda key, item=copy.deepcopy(question): _observed_provider_result(
                        provider.research(item)
                    ),
                    retry_policy=RetryPolicy.RETRY,
                    provider=self.provider_name,
                    model=self.model_name,
                    activation=ActivationKind.P4_RESEARCH,
                )
                result = provider_result_from_value(receipt)
                validated = p4.validate_provider_result(
                    question, result, citation_checker
                )
                evidence_ids = {item.id for item in validated.evidence}
                numeric_ids = {item.id for item in validated.numeric_claims}
                if evidence_ids & staged_evidence_ids:
                    raise ResearchRuntimeError("duplicate global evidence id")
                if numeric_ids & staged_numeric_ids:
                    raise ResearchRuntimeError("duplicate global numeric claim id")
                records = runtime_evidence_records(validated)
                resolved = [question.claim] if question_is_resolved(question, validated) else []
                transaction.stage_batch(
                    evidence=records,
                    resolved_claims=resolved,
                )
                staged_evidence_ids.update(evidence_ids)
                staged_numeric_ids.update(numeric_ids)
                conflict_ids = sorted(
                    {
                        item.id
                        for item in validated.evidence
                        if item.contradictions
                    }
                )
                if conflict_ids:
                    entry = record_operational_failure(
                        context,
                        operation_id=f"research-conflict:{question.id}",
                        provider=self.provider_name,
                        category=FailureCategory.SOURCE_CONFLICT,
                        message="conflicting evidence: " + ", ".join(conflict_ids),
                    )
                    failures.append(entry)
                    transaction.register_failure(entry.failure_id)
                if resolved:
                    validated_ids.append(question.id)
            except Exception as error:
                entry = record_operational_failure(
                    context,
                    operation_id=operation_id,
                    provider=self.provider_name,
                    category=classify_exception(
                        error, default=FailureCategory.PROVIDER_ERROR
                    ),
                    message=str(error),
                )
                failures.append(entry)
                transaction.register_failure(entry.failure_id)

        unresolved = [
            question_id
            for question_id in gate.required_question_ids
            if question_id not in validated_ids
        ]
        if failures and not (
            transaction.staging.evidence or transaction.staging.resolved_claims
        ):
            transaction_result = transaction.discard(
                state, reason="research produced no validated staging records"
            )
        else:
            transaction_result = transaction.commit(state, policy=policy)
        return ResearchRuntimeOutcome(
            state=transaction_result.state,
            gate=gate,
            validated_question_ids=validated_ids,
            unresolved_question_ids=unresolved,
            failures=failures,
            transaction=transaction_result,
            exit_status=(
                p0.ExitStatus.RESEARCH_REQUIRED if unresolved else None
            ),
        )


def provider_result_to_dict(result: p4.ProviderResearchResult) -> dict[str, Any]:
    return p4.provider_result_to_dict(result)


def _observed_provider_result(value: Any) -> Any:
    if isinstance(value, ObservedExternalResult):
        return ObservedExternalResult(
            provider_result_to_dict(provider_result_from_value(value.payload)),
            value.usage,
        )
    return provider_result_to_dict(provider_result_from_value(value))


def _research_gate_reason(
    gate: p4.ResearchGateDecision, research_allowed: bool
) -> str:
    if gate.required and not research_allowed:
        return "research is required but research_allowed=false"
    if gate.required:
        return "required questions: " + ", ".join(gate.required_question_ids)
    return "no unresolved external claim requires research"


def provider_result_from_value(value: Any) -> p4.ProviderResearchResult:
    if isinstance(value, p4.ProviderResearchResult):
        return copy.deepcopy(value)
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, Mapping):
        raise ResearchRuntimeError("provider receipt must be an object")
    return p4.provider_result_from_dict(value)


def runtime_evidence_records(
    result: p4.ProviderResearchResult,
) -> list[p0.EvidenceRecord]:
    evidence_by_id = {item.id: item for item in result.evidence}
    records = [
        p0.EvidenceRecord(
            id=f"p4:{item.id}",
            claim=item.claim,
            classification=(
                p0.KnowledgeStatus.CONFLICT
                if item.contradictions
                else p0.KnowledgeStatus.KNOWN
            ),
            source=item.source,
            metadata={"p4_kind": "evidence_summary", **_json_ready(item)},
        )
        for item in result.evidence
    ]
    for item in result.numeric_claims:
        source = None
        if item.status is p4.NumericStatus.CITED and item.citation_ids:
            source = evidence_by_id[item.citation_ids[0]].source
        rendered = (
            "UNKNOWN"
            if item.value is None
            else f"{item.value}{' ' + item.unit if item.unit else ''}"
        )
        records.append(
            p0.EvidenceRecord(
                id=f"p4:numeric:{item.id}",
                claim=f"{item.label}: {rendered}",
                classification={
                    p4.NumericStatus.CITED: p0.KnowledgeStatus.KNOWN,
                    p4.NumericStatus.ESTIMATE: p0.KnowledgeStatus.ASSUMPTION,
                    p4.NumericStatus.UNKNOWN: p0.KnowledgeStatus.UNKNOWN,
                }[item.status],
                source=source,
                metadata={"p4_kind": "numeric_claim", **_json_ready(item)},
            )
        )
    return records


def question_is_resolved(
    question: p4.ResearchQuestion,
    result: p4.ProviderResearchResult,
) -> bool:
    if any(item.contradictions for item in result.evidence):
        return False
    if question.time_sensitive and not any(
        item.source_date is not None for item in result.evidence
    ):
        return False
    if question.numeric_required:
        return any(
            item.status is not p4.NumericStatus.UNKNOWN
            for item in result.numeric_claims
        )
    return bool(result.evidence)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _json_ready(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return copy.deepcopy(value)
