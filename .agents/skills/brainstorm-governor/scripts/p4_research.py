#!/usr/bin/env python3
"""P4 provider-neutral Research Gate, evidence, and citation validation."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from p0_runtime import (
    ContractError,
    EvidenceRecord as RuntimeEvidenceRecord,
    ExitStatus,
    KnowledgeStatus,
    RunStatus,
    RuntimeState,
    Stage,
    state_from_dict,
    state_to_dict,
    validate_state,
)


class ResearchCategory(str, Enum):
    MARKET = "MARKET"
    COMPETITOR = "COMPETITOR"
    PRICE = "PRICE"
    LAW = "LAW"
    POLICY = "POLICY"
    STANDARD = "STANDARD"
    CURRENT_API = "CURRENT_API"
    PRODUCT_CAPABILITY = "PRODUCT_CAPABILITY"
    USER_DATA = "USER_DATA"
    GROWTH_DATA = "GROWTH_DATA"
    BEHAVIOR_DATA = "BEHAVIOR_DATA"
    DECISIVE_EXTERNAL_CLAIM = "DECISIVE_EXTERNAL_CLAIM"
    LOCAL_OR_SUBJECTIVE = "LOCAL_OR_SUBJECTIVE"


class EvidenceStrength(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class NumericStatus(str, Enum):
    CITED = "CITED"
    ESTIMATE = "ESTIMATE"
    UNKNOWN = "UNKNOWN"


TRIGGER_CATEGORIES = set(ResearchCategory) - {ResearchCategory.LOCAL_OR_SUBJECTIVE}


class ResearchContractError(ContractError):
    """Base error for the P4 research boundary."""


class CitationSupportError(ResearchContractError):
    """Raised when a citation does not support its corresponding claim."""


class ResearchProviderError(ResearchContractError):
    """Provider failure that must lead to a safe RESEARCH_REQUIRED stop."""


@dataclass(frozen=True)
class ResearchQuestion:
    id: str
    claim: str
    category: ResearchCategory
    time_sensitive: bool = False
    numeric_required: bool = False


@dataclass(frozen=True)
class ResearchGateDecision:
    required: bool
    required_question_ids: list[str]
    skipped_question_ids: list[str]
    reasons: dict[str, str]


@dataclass(frozen=True)
class ResearchEvidenceRecord:
    id: str
    question_id: str
    claim: str
    source: str
    source_date: str | None
    retrieved_at: str
    evidence_strength: EvidenceStrength
    contradictions: list[str]
    confidence: float
    supporting_excerpt: str
    numeric_claim_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NumericClaim:
    id: str
    question_id: str
    label: str
    value: int | float | None
    unit: str | None
    status: NumericStatus
    citation_ids: list[str] = field(default_factory=list)
    estimate_basis: str | None = None


@dataclass(frozen=True)
class ProviderResearchResult:
    evidence: list[ResearchEvidenceRecord]
    numeric_claims: list[NumericClaim]


@dataclass
class ResearchOutcome:
    state: RuntimeState
    gate: ResearchGateDecision
    evidence: list[ResearchEvidenceRecord]
    numeric_claims: list[NumericClaim]
    conflict_groups: list[list[str]]
    unresolved_question_ids: list[str]
    provider_failures: list[str]
    exit_status: ExitStatus | None


class ResearchProvider(Protocol):
    """Provider owns retrieval and summarization; raw results stay behind this boundary."""

    def research(self, question: ResearchQuestion) -> ProviderResearchResult:
        ...


class CitationSupportChecker(Protocol):
    """Semantic checker kept separate from retrieval and the governor state machine."""

    def supports(self, claim: str, source: str, supporting_excerpt: str) -> bool:
        ...


def research_gate(
    questions: Sequence[ResearchQuestion],
    *,
    existing_evidence: Sequence[ResearchEvidenceRecord] = (),
    existing_numeric_claims: Sequence[NumericClaim] = (),
) -> ResearchGateDecision:
    """Require research only for the P4 external-claim categories."""
    question_items = _validate_questions(questions)
    evidence_items = list(existing_evidence)
    numeric_items = list(existing_numeric_claims)
    for item in evidence_items:
        _validate_evidence_shape(item)
    for item in numeric_items:
        _validate_numeric_shape(item)

    required: list[str] = []
    skipped: list[str] = []
    reasons: dict[str, str] = {}
    for question in question_items:
        if question.category not in TRIGGER_CATEGORIES:
            skipped.append(question.id)
            reasons[question.id] = "local or subjective claim does not require external research"
            continue
        if _question_is_resolved(question, evidence_items, numeric_items):
            skipped.append(question.id)
            reasons[question.id] = "validated evidence summary already covers the claim"
            continue
        required.append(question.id)
        reasons[question.id] = f"external verification required: {question.category.value}"
    return ResearchGateDecision(bool(required), required, skipped, reasons)


def validate_research_question(question: ResearchQuestion) -> None:
    """Validate one P4 question for downstream worker adapters."""
    _validate_question(question)


def validate_provider_result(
    question: ResearchQuestion,
    result: ProviderResearchResult,
    citation_checker: CitationSupportChecker,
) -> ProviderResearchResult:
    """Validate summaries, citation support, conflicts, and numeric provenance."""
    _validate_question(question)
    if not isinstance(result, ProviderResearchResult):
        raise ResearchContractError("provider result must be ProviderResearchResult")
    if not hasattr(citation_checker, "supports"):
        raise ResearchContractError("citation_checker must implement supports")

    evidence = copy.deepcopy(result.evidence)
    numeric_claims = copy.deepcopy(result.numeric_claims)
    evidence_by_id: dict[str, ResearchEvidenceRecord] = {}
    for index, item in enumerate(evidence):
        _validate_evidence_shape(item, f"evidence[{index}]")
        if item.id in evidence_by_id:
            raise ResearchContractError(f"duplicate evidence id {item.id!r}")
        if item.question_id != question.id:
            raise ResearchContractError(
                f"evidence {item.id!r} belongs to a different question"
            )
        if question.time_sensitive and item.source_date is None:
            raise ResearchContractError(
                f"time-sensitive evidence {item.id!r} requires source_date"
            )
        try:
            supported = citation_checker.supports(
                item.claim, item.source, item.supporting_excerpt
            )
        except Exception as exc:
            raise CitationSupportError(
                f"citation support checker failed for evidence {item.id!r}: {exc}"
            ) from exc
        if supported is not True:
            raise CitationSupportError(
                f"citation {item.source!r} does not support claim {item.claim!r}"
            )
        evidence_by_id[item.id] = item

    numeric_by_id: dict[str, NumericClaim] = {}
    for index, item in enumerate(numeric_claims):
        _validate_numeric_shape(item, f"numeric_claims[{index}]")
        if item.id in numeric_by_id:
            raise ResearchContractError(f"duplicate numeric claim id {item.id!r}")
        if item.question_id != question.id:
            raise ResearchContractError(
                f"numeric claim {item.id!r} belongs to a different question"
            )
        unknown_citations = set(item.citation_ids) - set(evidence_by_id)
        if unknown_citations:
            raise ResearchContractError(
                f"numeric claim {item.id!r} references unknown citations "
                f"{sorted(unknown_citations)}"
            )
        numeric_by_id[item.id] = item

    for item in evidence:
        unknown_numeric = set(item.numeric_claim_ids) - set(numeric_by_id)
        if unknown_numeric:
            raise ResearchContractError(
                f"evidence {item.id!r} references unknown numeric claims "
                f"{sorted(unknown_numeric)}"
            )
        if _contains_numeric_value(item.claim) and not item.numeric_claim_ids:
            raise ResearchContractError(
                f"evidence {item.id!r} contains a numeric value without NumericClaim"
            )
        for other_id in item.contradictions:
            other = evidence_by_id.get(other_id)
            if other is None:
                raise ResearchContractError(
                    f"evidence {item.id!r} contradicts unknown evidence {other_id!r}"
                )
            if item.id not in other.contradictions:
                raise ResearchContractError(
                    f"contradiction {item.id!r} ↔ {other_id!r} must be reciprocal"
                )

    if question.numeric_required and not numeric_claims:
        raise ResearchContractError(
            f"question {question.id!r} requires an explicit NumericClaim"
        )
    return ProviderResearchResult(evidence, numeric_claims)


def provider_result_to_dict(result: ProviderResearchResult) -> dict[str, Any]:
    """Serialize the normalized provider boundary without private payloads."""
    if not isinstance(result, ProviderResearchResult):
        raise ResearchContractError("provider result must be ProviderResearchResult")
    for index, item in enumerate(result.evidence):
        _validate_evidence_shape(item, f"evidence[{index}]")
    for index, item in enumerate(result.numeric_claims):
        _validate_numeric_shape(item, f"numeric_claims[{index}]")
    return _json_ready(result)


def provider_result_from_dict(value: Mapping[str, Any]) -> ProviderResearchResult:
    """Parse one strict normalized provider receipt for durable replay."""
    data = _require_exact_keys(value, {"evidence", "numeric_claims"}, "provider_result")
    evidence_values = _require_sequence(data["evidence"], "provider_result.evidence")
    numeric_values = _require_sequence(
        data["numeric_claims"], "provider_result.numeric_claims"
    )
    result = ProviderResearchResult(
        evidence=[
            _evidence_from_dict(item, f"provider_result.evidence[{index}]")
            for index, item in enumerate(evidence_values)
        ],
        numeric_claims=[
            _numeric_from_dict(item, f"provider_result.numeric_claims[{index}]")
            for index, item in enumerate(numeric_values)
        ],
    )
    return result


def run_research(
    state: RuntimeState,
    questions: Sequence[ResearchQuestion],
    provider: ResearchProvider,
    citation_checker: CitationSupportChecker,
    *,
    existing_evidence: Sequence[ResearchEvidenceRecord] = (),
    existing_numeric_claims: Sequence[NumericClaim] = (),
) -> ResearchOutcome:
    """Execute gated research sequentially and safely stop on unresolved claims."""
    validate_state(state)
    question_items = _validate_questions(questions)
    existing_evidence_items = copy.deepcopy(list(existing_evidence))
    existing_numeric_items = copy.deepcopy(list(existing_numeric_claims))
    gate = research_gate(
        question_items,
        existing_evidence=existing_evidence_items,
        existing_numeric_claims=existing_numeric_items,
    )
    updated_state = copy.deepcopy(state)
    if not gate.required:
        return ResearchOutcome(
            state=updated_state,
            gate=gate,
            evidence=existing_evidence_items,
            numeric_claims=existing_numeric_items,
            conflict_groups=_conflict_groups(existing_evidence_items),
            unresolved_question_ids=[],
            provider_failures=[],
            exit_status=None,
        )

    if not state.research_allowed:
        _stop_research_required(updated_state)
        return ResearchOutcome(
            state=updated_state,
            gate=gate,
            evidence=existing_evidence_items,
            numeric_claims=existing_numeric_items,
            conflict_groups=_conflict_groups(existing_evidence_items),
            unresolved_question_ids=copy.deepcopy(gate.required_question_ids),
            provider_failures=["research is required but research_allowed=false"],
            exit_status=ExitStatus.RESEARCH_REQUIRED,
        )

    updated_state.run.stage = Stage.RESEARCH
    updated_state.run.status = RunStatus.ACTIVE
    updated_state.result.exit_status = None
    validate_state(updated_state)

    required = set(gate.required_question_ids)
    evidence = existing_evidence_items
    numeric_claims = existing_numeric_items
    failures: list[str] = []
    validated_question_ids: set[str] = set()
    for question in question_items:
        if question.id not in required:
            continue
        try:
            result = provider.research(copy.deepcopy(question))
            validated = validate_provider_result(question, result, citation_checker)
            _ensure_global_ids_do_not_conflict(evidence, numeric_claims, validated)
            evidence.extend(validated.evidence)
            numeric_claims.extend(validated.numeric_claims)
            validated_question_ids.add(question.id)
        except Exception as exc:
            failures.append(f"{question.id}: {exc}")

    unresolved: list[str] = []
    by_question = {item.id: item for item in question_items}
    for question_id in gate.required_question_ids:
        question = by_question[question_id]
        if question_id not in validated_question_ids or not _question_is_resolved(
            question, evidence, numeric_claims
        ):
            unresolved.append(question_id)

    _apply_summaries_to_state(updated_state, evidence, numeric_claims)
    resolved_claims = {
        by_question[item].claim
        for item in gate.required_question_ids
        if item not in unresolved
    }
    _remove_resolved_uncertainty(updated_state, resolved_claims)
    if unresolved:
        _stop_research_required(updated_state)
        exit_status: ExitStatus | None = ExitStatus.RESEARCH_REQUIRED
    else:
        validate_state(updated_state)
        exit_status = None

    return ResearchOutcome(
        state=updated_state,
        gate=gate,
        evidence=evidence,
        numeric_claims=numeric_claims,
        conflict_groups=_conflict_groups(evidence),
        unresolved_question_ids=unresolved,
        provider_failures=failures,
        exit_status=exit_status,
    )


def validate_downstream_usage(
    outcome: ResearchOutcome,
    *,
    evidence_ids: Sequence[str] = (),
    numeric_claim_ids: Sequence[str] = (),
) -> None:
    """Reject unsupported/conflicted evidence and UNKNOWN numbers as downstream facts."""
    evidence_by_id = {item.id: item for item in outcome.evidence}
    numeric_by_id = {item.id: item for item in outcome.numeric_claims}
    for evidence_id in _unique_strings(evidence_ids, "evidence_ids"):
        item = evidence_by_id.get(evidence_id)
        if item is None:
            raise ResearchContractError(f"unknown downstream evidence {evidence_id!r}")
        if item.contradictions:
            raise ResearchContractError(
                f"conflicted evidence {evidence_id!r} cannot be used as fact"
            )
    for numeric_id in _unique_strings(numeric_claim_ids, "numeric_claim_ids"):
        item = numeric_by_id.get(numeric_id)
        if item is None:
            raise ResearchContractError(f"unknown numeric claim {numeric_id!r}")
        if item.status is NumericStatus.UNKNOWN:
            raise ResearchContractError(
                f"UNKNOWN numeric claim {numeric_id!r} cannot be used as fact"
            )


def downstream_view(outcome: ResearchOutcome) -> dict[str, list[dict[str, Any]]]:
    """Return only non-conflicted evidence and non-UNKNOWN numeric claims."""
    return {
        "evidence": [
            _json_ready(item) for item in outcome.evidence if not item.contradictions
        ],
        "numeric_claims": [
            _json_ready(item)
            for item in outcome.numeric_claims
            if item.status is not NumericStatus.UNKNOWN
        ],
    }


def _question_is_resolved(
    question: ResearchQuestion,
    evidence: Sequence[ResearchEvidenceRecord],
    numeric_claims: Sequence[NumericClaim],
) -> bool:
    matching_evidence = [item for item in evidence if item.question_id == question.id]
    matching_numeric = [item for item in numeric_claims if item.question_id == question.id]
    if any(item.contradictions for item in matching_evidence):
        return False
    if question.time_sensitive and not any(
        item.source_date is not None for item in matching_evidence
    ):
        return False
    if question.numeric_required:
        return any(item.status is not NumericStatus.UNKNOWN for item in matching_numeric)
    return bool(matching_evidence)


def _apply_summaries_to_state(
    state: RuntimeState,
    evidence: Sequence[ResearchEvidenceRecord],
    numeric_claims: Sequence[NumericClaim],
) -> None:
    evidence_by_id = {item.id: item for item in evidence}
    for item in evidence:
        record = RuntimeEvidenceRecord(
            id=f"p4:{item.id}",
            claim=item.claim,
            classification=(
                KnowledgeStatus.CONFLICT
                if item.contradictions
                else KnowledgeStatus.KNOWN
            ),
            source=item.source,
            metadata={"p4_kind": "evidence_summary", **_json_ready(item)},
        )
        _upsert_runtime_evidence(state, record)

    for item in numeric_claims:
        source = None
        if item.status is NumericStatus.CITED and item.citation_ids:
            source = evidence_by_id[item.citation_ids[0]].source
        classification = {
            NumericStatus.CITED: KnowledgeStatus.KNOWN,
            NumericStatus.ESTIMATE: KnowledgeStatus.ASSUMPTION,
            NumericStatus.UNKNOWN: KnowledgeStatus.UNKNOWN,
        }[item.status]
        rendered_value = (
            "UNKNOWN"
            if item.value is None
            else f"{item.value}{' ' + item.unit if item.unit else ''}"
        )
        record = RuntimeEvidenceRecord(
            id=f"p4:numeric:{item.id}",
            claim=f"{item.label}: {rendered_value}",
            classification=classification,
            source=source,
            metadata={"p4_kind": "numeric_claim", **_json_ready(item)},
        )
        _upsert_runtime_evidence(state, record)


def _upsert_runtime_evidence(
    state: RuntimeState, record: RuntimeEvidenceRecord
) -> None:
    serialized = _json_ready(record)
    for existing in state.evidence:
        if existing.id != record.id:
            continue
        if _json_ready(existing) != serialized:
            raise ResearchContractError(
                f"runtime evidence id {record.id!r} has conflicting content"
            )
        return
    state.evidence.append(record)


def _remove_resolved_uncertainty(
    state: RuntimeState, resolved_claims: set[str]
) -> None:
    normalized = {_normalize(item) for item in resolved_claims}
    state.assumptions = [
        item for item in state.assumptions if _normalize(item.statement) not in normalized
    ]
    state.unknowns = [
        item for item in state.unknowns if _normalize(item.statement) not in normalized
    ]


def _stop_research_required(state: RuntimeState) -> None:
    state.run.stage = Stage.STOPPED
    state.run.status = RunStatus.STOPPED
    state.result.exit_status = ExitStatus.RESEARCH_REQUIRED
    validate_state(state)


def _ensure_global_ids_do_not_conflict(
    evidence: Sequence[ResearchEvidenceRecord],
    numeric_claims: Sequence[NumericClaim],
    incoming: ProviderResearchResult,
) -> None:
    evidence_ids = {item.id for item in evidence}
    numeric_ids = {item.id for item in numeric_claims}
    duplicate_evidence = evidence_ids & {item.id for item in incoming.evidence}
    duplicate_numeric = numeric_ids & {item.id for item in incoming.numeric_claims}
    if duplicate_evidence:
        raise ResearchContractError(
            f"duplicate global evidence ids {sorted(duplicate_evidence)}"
        )
    if duplicate_numeric:
        raise ResearchContractError(
            f"duplicate global numeric ids {sorted(duplicate_numeric)}"
        )


def _conflict_groups(
    evidence: Sequence[ResearchEvidenceRecord],
) -> list[list[str]]:
    by_id = {item.id: item for item in evidence}
    visited: set[str] = set()
    groups: list[list[str]] = []
    for item in evidence:
        if item.id in visited or not item.contradictions:
            continue
        stack = [item.id]
        group: set[str] = set()
        while stack:
            current = stack.pop()
            if current in group:
                continue
            group.add(current)
            other = by_id.get(current)
            if other is not None:
                stack.extend(other.contradictions)
        visited.update(group)
        groups.append(sorted(group))
    return sorted(groups)


def _validate_questions(
    questions: Sequence[ResearchQuestion],
) -> list[ResearchQuestion]:
    if isinstance(questions, (str, bytes)) or not isinstance(questions, Sequence):
        raise ResearchContractError("questions must be a sequence")
    result = list(questions)
    ids: set[str] = set()
    for item in result:
        _validate_question(item)
        if item.id in ids:
            raise ResearchContractError(f"duplicate research question {item.id!r}")
        ids.add(item.id)
    return result


def _validate_question(question: ResearchQuestion) -> None:
    if not isinstance(question, ResearchQuestion):
        raise ResearchContractError("question must be ResearchQuestion")
    _required_string(question.id, "question.id")
    _required_string(question.claim, "question.claim")
    if not isinstance(question.category, ResearchCategory):
        raise ResearchContractError("question.category must be ResearchCategory")
    if type(question.time_sensitive) is not bool:
        raise ResearchContractError("question.time_sensitive must be boolean")
    if type(question.numeric_required) is not bool:
        raise ResearchContractError("question.numeric_required must be boolean")


def _validate_evidence_shape(
    item: ResearchEvidenceRecord, path: str = "evidence"
) -> None:
    if not isinstance(item, ResearchEvidenceRecord):
        raise ResearchContractError(f"{path} must be ResearchEvidenceRecord")
    for name in ("id", "question_id", "claim", "source", "supporting_excerpt"):
        _required_string(getattr(item, name), f"{path}.{name}")
    if item.source_date is not None:
        _validate_date(item.source_date, f"{path}.source_date")
    _validate_timestamp(item.retrieved_at, f"{path}.retrieved_at")
    if not isinstance(item.evidence_strength, EvidenceStrength):
        raise ResearchContractError(f"{path}.evidence_strength is invalid")
    contradictions = _unique_strings(item.contradictions, f"{path}.contradictions")
    if item.id in contradictions:
        raise ResearchContractError(f"{path} cannot contradict itself")
    _validate_confidence(item.confidence, f"{path}.confidence")
    _unique_strings(item.numeric_claim_ids, f"{path}.numeric_claim_ids")


def _validate_numeric_shape(item: NumericClaim, path: str = "numeric_claim") -> None:
    if not isinstance(item, NumericClaim):
        raise ResearchContractError(f"{path} must be NumericClaim")
    for name in ("id", "question_id", "label"):
        _required_string(getattr(item, name), f"{path}.{name}")
    if item.unit is not None:
        _required_string(item.unit, f"{path}.unit")
    if not isinstance(item.status, NumericStatus):
        raise ResearchContractError(f"{path}.status must be NumericStatus")
    citations = _unique_strings(item.citation_ids, f"{path}.citation_ids")
    if item.status is NumericStatus.CITED:
        _required_number(item.value, f"{path}.value")
        if not citations:
            raise ResearchContractError(f"{path} CITED value requires citation_ids")
        if item.estimate_basis is not None:
            raise ResearchContractError(f"{path} CITED value cannot set estimate_basis")
    elif item.status is NumericStatus.ESTIMATE:
        _required_number(item.value, f"{path}.value")
        _required_string(item.estimate_basis, f"{path}.estimate_basis")
    else:
        if item.value is not None:
            raise ResearchContractError(f"{path} UNKNOWN value must be null")
        if item.estimate_basis is not None:
            raise ResearchContractError(f"{path} UNKNOWN cannot set estimate_basis")


def _validate_date(value: str, path: str) -> None:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ResearchContractError(f"{path} must be an ISO date") from exc


def _validate_timestamp(value: str, path: str) -> None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ResearchContractError(f"{path} must be an ISO timestamp") from exc
    if parsed.tzinfo is None:
        raise ResearchContractError(f"{path} must include a timezone")


def _validate_confidence(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchContractError(f"{path} must be numeric")
    if not 0 <= float(value) <= 1:
        raise ResearchContractError(f"{path} must be between 0 and 1")


def _required_number(value: Any, path: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ResearchContractError(f"{path} must be numeric")
    return value


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchContractError(f"{path} must be a non-empty string")
    return value


def _unique_strings(value: Sequence[str], path: str) -> list[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ResearchContractError(f"{path} must be a sequence of strings")
    result = list(value)
    if not all(isinstance(item, str) and item.strip() for item in result):
        raise ResearchContractError(f"{path} must contain non-empty strings")
    if len(result) != len(set(result)):
        raise ResearchContractError(f"{path} must contain unique values")
    return result


def _contains_numeric_value(value: str) -> bool:
    return bool(re.search(r"(?<![A-Za-z])\d+(?:[.,]\d+)?", value))


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _question_from_dict(value: Any, path: str) -> ResearchQuestion:
    data = _require_exact_keys(
        value,
        {"id", "claim", "category", "time_sensitive", "numeric_required"},
        path,
    )
    return ResearchQuestion(
        id=data["id"],
        claim=data["claim"],
        category=_enum_value(ResearchCategory, data["category"], f"{path}.category"),
        time_sensitive=data["time_sensitive"],
        numeric_required=data["numeric_required"],
    )


def _evidence_from_dict(value: Any, path: str) -> ResearchEvidenceRecord:
    data = _require_exact_keys(
        value,
        {
            "id",
            "question_id",
            "claim",
            "source",
            "source_date",
            "retrieved_at",
            "evidence_strength",
            "contradictions",
            "confidence",
            "supporting_excerpt",
            "numeric_claim_ids",
        },
        path,
    )
    return ResearchEvidenceRecord(
        id=data["id"],
        question_id=data["question_id"],
        claim=data["claim"],
        source=data["source"],
        source_date=data["source_date"],
        retrieved_at=data["retrieved_at"],
        evidence_strength=_enum_value(
            EvidenceStrength, data["evidence_strength"], f"{path}.evidence_strength"
        ),
        contradictions=_string_list(data["contradictions"], f"{path}.contradictions"),
        confidence=data["confidence"],
        supporting_excerpt=data["supporting_excerpt"],
        numeric_claim_ids=_string_list(
            data["numeric_claim_ids"], f"{path}.numeric_claim_ids"
        ),
    )


def _numeric_from_dict(value: Any, path: str) -> NumericClaim:
    data = _require_exact_keys(
        value,
        {
            "id",
            "question_id",
            "label",
            "value",
            "unit",
            "status",
            "citation_ids",
            "estimate_basis",
        },
        path,
    )
    return NumericClaim(
        id=data["id"],
        question_id=data["question_id"],
        label=data["label"],
        value=data["value"],
        unit=data["unit"],
        status=_enum_value(NumericStatus, data["status"], f"{path}.status"),
        citation_ids=_string_list(data["citation_ids"], f"{path}.citation_ids"),
        estimate_basis=data["estimate_basis"],
    )


def gate_request_from_dict(
    value: Mapping[str, Any]
) -> tuple[list[ResearchQuestion], list[ResearchEvidenceRecord], list[NumericClaim]]:
    data = _require_exact_keys(
        value, {"questions", "existing_evidence", "existing_numeric_claims"}, "request"
    )
    questions = [
        _question_from_dict(item, f"request.questions[{index}]")
        for index, item in enumerate(_mapping_list(data["questions"], "request.questions"))
    ]
    evidence = [
        _evidence_from_dict(item, f"request.existing_evidence[{index}]")
        for index, item in enumerate(
            _mapping_list(data["existing_evidence"], "request.existing_evidence")
        )
    ]
    numeric = [
        _numeric_from_dict(item, f"request.existing_numeric_claims[{index}]")
        for index, item in enumerate(
            _mapping_list(
                data["existing_numeric_claims"], "request.existing_numeric_claims"
            )
        )
    ]
    return questions, evidence, numeric


def _mapping_list(value: Any, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ResearchContractError(f"{path} must be a list")
    return [_require_mapping(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ResearchContractError(f"{path} must be a list")
    return _unique_strings(value, path)


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchContractError(f"{path} must be an object")
    return value


def _require_sequence(value: Any, path: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ResearchContractError(f"{path} must be an array")
    return list(value)


def _require_exact_keys(
    value: Any, expected: set[str], path: str
) -> Mapping[str, Any]:
    data = _require_mapping(value, path)
    missing = expected - set(data)
    unknown = set(data) - expected
    if missing:
        raise ResearchContractError(f"{path} is missing keys: {sorted(missing)}")
    if unknown:
        raise ResearchContractError(f"{path} has unknown keys: {sorted(unknown)}")
    return data


def _enum_value(enum_type: type[Enum], value: Any, path: str) -> Any:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        for member in enum_type:
            if value.casefold() in {member.name.casefold(), str(member.value).casefold()}:
                return member
    raise ResearchContractError(
        f"{path} must be one of {[item.value for item in enum_type]}"
    )


def _json_ready(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _json_ready(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _load_json(value: str | None) -> Any:
    try:
        return json.loads(value) if value is not None else json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ResearchContractError(f"invalid JSON: {exc}") from exc


def _emit(value: Any) -> None:
    json.dump(_json_ready(value), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    gate = subparsers.add_parser("gate", help="evaluate the provider-neutral Research Gate")
    gate.add_argument("--json", help="request JSON; defaults to stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "gate":
            questions, evidence, numeric = gate_request_from_dict(
                _require_mapping(_load_json(args.json), "request")
            )
            _emit(
                research_gate(
                    questions,
                    existing_evidence=evidence,
                    existing_numeric_claims=numeric,
                )
            )
        return 0
    except ContractError as exc:
        _emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
