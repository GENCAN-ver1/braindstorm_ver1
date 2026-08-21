#!/usr/bin/env python3
"""P3 single-agent Blindspot, Assumption Audit, and Pressure Test engine."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from p0_runtime import (
    ContractError,
    KnowledgeItem,
    KnowledgeStatus,
    RuntimeState,
    Stage,
    state_from_dict,
    state_to_dict,
    validate_state,
)


DEFAULT_UNKNOWN_DENSITY_THRESHOLD = 0.35
DEFAULT_HIGH_IMPORTANCE_THRESHOLD = 0.70
DEFAULT_LOW_CONFIDENCE_THRESHOLD = 0.40


class BlindspotCategory(str, Enum):
    STAKEHOLDERS = "STAKEHOLDERS"
    INCENTIVE_MISMATCH = "INCENTIVE_MISMATCH"
    ONBOARDING_VS_LONG_TERM_USE = "ONBOARDING_VS_LONG_TERM_USE"
    ADOPTION_MIGRATION_EXIT_COST = "ADOPTION_MIGRATION_EXIT_COST"
    OPERATOR_BURDEN = "OPERATOR_BURDEN"
    SECOND_ORDER_EFFECTS = "SECOND_ORDER_EFFECTS"
    LEGAL_SECURITY_PRIVACY_REPUTATION = "LEGAL_SECURITY_PRIVACY_REPUTATION"
    EXTERNAL_DEPENDENCIES = "EXTERNAL_DEPENDENCIES"


class AssumptionType(str, Enum):
    DESIRABILITY = "DESIRABILITY"
    FEASIBILITY = "FEASIBILITY"
    VIABILITY = "VIABILITY"
    ADOPTION = "ADOPTION"
    DISTRIBUTION = "DISTRIBUTION"
    OPERATIONS = "OPERATIONS"
    TIMING = "TIMING"


class FailureImpact(str, Enum):
    FATAL = "FATAL"
    REPAIRABLE = "REPAIRABLE"


class PressureTestType(str, Enum):
    PRE_MORTEM = "PRE_MORTEM"
    COUNTEREXAMPLE = "COUNTEREXAMPLE"
    BOUNDARY_TEST = "BOUNDARY_TEST"
    DEPENDENCY_FAILURE = "DEPENDENCY_FAILURE"
    ADOPTION_FRICTION = "ADOPTION_FRICTION"
    SUSTAINABILITY = "SUSTAINABILITY"
    SUBSTITUTE_TEST = "SUBSTITUTE_TEST"
    STEELMAN = "STEELMAN"


class RiskClass(str, Enum):
    NONE = "NONE"
    REPAIRABLE = "REPAIRABLE"
    FATAL = "FATAL"


@dataclass(frozen=True)
class PreDivergenceSignals:
    unfamiliar_domain: bool = False
    hidden_norm_risk: bool = False
    stakeholder_or_incentive_risk: bool = False
    technical_constraint_risk: bool = False
    explicit_requested: bool = False
    unknown_density_threshold: float = DEFAULT_UNKNOWN_DENSITY_THRESHOLD


@dataclass(frozen=True)
class PreDivergenceContent:
    landmines: list[str]
    hidden_context: list[str]
    what_good_looks_like: list[str]
    expert_questions: list[str]


@dataclass(frozen=True)
class PreDivergenceResult:
    triggered: bool
    trigger_reasons: list[str]
    unknown_density: float
    landmines: list[str]
    hidden_context: list[str]
    what_good_looks_like: list[str]
    expert_questions: list[str]


@dataclass(frozen=True)
class BlindspotCheck:
    category: BlindspotCategory
    finding: KnowledgeItem | None
    evidence: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AssumptionRecord:
    id: str
    candidate_id: str
    claim: KnowledgeItem
    type: AssumptionType
    importance: float
    confidence: float
    evidence: list[str]
    failure_impact: FailureImpact
    cheapest_test: str


@dataclass(frozen=True)
class PressureTest:
    type: PressureTestType
    scenario: str
    result: str
    risk_class: RiskClass
    related_assumption_ids: list[str] = field(default_factory=list)
    repair_action: str | None = None


@dataclass(frozen=True)
class CandidateChallengeInput:
    candidate_id: str
    blindspot_checks: list[BlindspotCheck]
    assumption_register: list[AssumptionRecord]
    pressure_tests: list[PressureTest]


@dataclass(frozen=True)
class RiskFinding:
    candidate_id: str
    severity: FailureImpact
    source: str
    statement: str
    related_assumption_ids: list[str]
    repair_action: str | None = None


@dataclass(frozen=True)
class CandidateChallengeResult:
    candidate_id: str
    blindspots: list[BlindspotCheck]
    assumption_register: list[AssumptionRecord]
    knowledge_summary: dict[str, list[str]]
    pressure_tests: list[PressureTest]
    prioritized_assumption_ids: list[str]
    fatal_risks: list[RiskFinding]
    repairable_risks: list[RiskFinding]
    evidence_gaps: list[str]


@dataclass(frozen=True)
class ChallengeEngineOutput:
    reports: list[CandidateChallengeResult]
    prioritized_assumption_ids: list[str]
    fatal_risks: list[RiskFinding]
    repairable_risks: list[RiskFinding]
    evidence_gaps: list[str]
    frame_unchanged: bool


def run_pre_divergence_blindspot(
    state: RuntimeState,
    signals: PreDivergenceSignals,
    content: PreDivergenceContent | None = None,
) -> PreDivergenceResult:
    """Conditionally expose missing context before Divergence without judging ideas."""
    validate_state(state)
    if state.run.stage not in {Stage.CONTEXT, Stage.FRAME}:
        raise ContractError(
            "pre-divergence Blindspot can run only during CONTEXT or FRAME"
        )
    _validate_pre_signals(signals)
    density = _unknown_density(state)
    reasons: list[str] = []
    if signals.unfamiliar_domain:
        reasons.append("unfamiliar_domain")
    if density >= signals.unknown_density_threshold:
        reasons.append("high_unknown_density")
    if signals.hidden_norm_risk:
        reasons.append("hidden_norm_risk")
    if signals.stakeholder_or_incentive_risk:
        reasons.append("stakeholder_or_incentive_risk")
    if signals.technical_constraint_risk:
        reasons.append("technical_constraint_risk")
    if signals.explicit_requested:
        reasons.append("explicit_requested")

    triggered = bool(reasons)
    if not triggered:
        if content is not None and _pre_content_has_values(content):
            raise ContractError(
                "pre-divergence Blindspot content is not allowed when no trigger fires"
            )
        return PreDivergenceResult(False, [], density, [], [], [], [])

    if content is None:
        raise ContractError("triggered pre-divergence Blindspot requires content")
    _validate_pre_content(content)
    return PreDivergenceResult(
        triggered=True,
        trigger_reasons=reasons,
        unknown_density=density,
        landmines=copy.deepcopy(content.landmines),
        hidden_context=copy.deepcopy(content.hidden_context),
        what_good_looks_like=copy.deepcopy(content.what_good_looks_like),
        expert_questions=copy.deepcopy(content.expert_questions),
    )


def run_challenge_engine(
    state: RuntimeState,
    candidate_ids: Sequence[str],
    challenges: Sequence[CandidateChallengeInput],
    *,
    high_importance_threshold: float = DEFAULT_HIGH_IMPORTANCE_THRESHOLD,
    low_confidence_threshold: float = DEFAULT_LOW_CONFIDENCE_THRESHOLD,
) -> ChallengeEngineOutput:
    """Run the three isolated P3 passes after Normalize without mutating the frame."""
    validate_state(state)
    if state.run.stage not in {Stage.NORMALIZE, Stage.CHALLENGE}:
        raise ContractError("Challenge cannot run before Divergence and Normalize")
    _validate_threshold(high_importance_threshold, "high_importance_threshold")
    _validate_threshold(low_confidence_threshold, "low_confidence_threshold")
    expected_ids = _unique_nonempty(candidate_ids, "candidate_ids")
    if not expected_ids:
        raise ContractError("candidate_ids must not be empty")
    if not isinstance(challenges, Sequence) or isinstance(challenges, (str, bytes)):
        raise ContractError("challenges must be a sequence")
    challenge_items = list(challenges)
    for index, item in enumerate(challenge_items):
        if not isinstance(item, CandidateChallengeInput):
            raise ContractError(f"challenges[{index}] must be CandidateChallengeInput")
    actual_ids = [item.candidate_id for item in challenge_items]
    if len(actual_ids) != len(set(actual_ids)):
        raise ContractError("challenge candidate ids must be unique")
    if set(actual_ids) != set(expected_ids):
        raise ContractError("every normalized candidate requires exactly one challenge")

    frame_before = copy.deepcopy(state_to_dict(state)["frame"])
    reports: list[CandidateChallengeResult] = []
    for challenge in challenge_items:
        _validate_candidate_challenge(challenge)
        reports.append(
            _build_candidate_result(
                challenge,
                high_importance_threshold=high_importance_threshold,
                low_confidence_threshold=low_confidence_threshold,
            )
        )
    by_id = {item.candidate_id: item for item in reports}
    ordered_reports = [by_id[item] for item in expected_ids]
    frame_unchanged = state_to_dict(state)["frame"] == frame_before
    if not frame_unchanged:
        raise ContractError("Challenge must not modify the confirmed Problem Frame")

    prioritized_ids = [
        assumption_id
        for report in ordered_reports
        for assumption_id in report.prioritized_assumption_ids
    ]
    fatal_risks = [risk for report in ordered_reports for risk in report.fatal_risks]
    repairable_risks = [
        risk for report in ordered_reports for risk in report.repairable_risks
    ]
    evidence_gaps = _dedupe(
        [gap for report in ordered_reports for gap in report.evidence_gaps]
    )
    return ChallengeEngineOutput(
        reports=ordered_reports,
        prioritized_assumption_ids=prioritized_ids,
        fatal_risks=fatal_risks,
        repairable_risks=repairable_risks,
        evidence_gaps=evidence_gaps,
        frame_unchanged=frame_unchanged,
    )


def _build_candidate_result(
    challenge: CandidateChallengeInput,
    *,
    high_importance_threshold: float,
    low_confidence_threshold: float,
) -> CandidateChallengeResult:
    ordered_assumptions = sorted(
        challenge.assumption_register,
        key=lambda item: (-item.importance, item.confidence, item.id),
    )
    priority = [
        item
        for item in ordered_assumptions
        if item.importance >= high_importance_threshold
        and item.confidence <= low_confidence_threshold
    ]
    knowledge_summary = {item.value: [] for item in KnowledgeStatus}
    for item in ordered_assumptions:
        knowledge_summary[item.claim.classification.value].append(item.id)

    fatal: list[RiskFinding] = []
    repairable: list[RiskFinding] = []
    for item in priority:
        risk = RiskFinding(
            candidate_id=challenge.candidate_id,
            severity=item.failure_impact,
            source=f"assumption:{item.id}",
            statement=item.claim.statement,
            related_assumption_ids=[item.id],
            repair_action=(item.cheapest_test if item.failure_impact is FailureImpact.REPAIRABLE else None),
        )
        (fatal if item.failure_impact is FailureImpact.FATAL else repairable).append(risk)

    for item in challenge.pressure_tests:
        if item.risk_class is RiskClass.NONE:
            continue
        severity = (
            FailureImpact.FATAL
            if item.risk_class is RiskClass.FATAL
            else FailureImpact.REPAIRABLE
        )
        risk = RiskFinding(
            candidate_id=challenge.candidate_id,
            severity=severity,
            source=f"pressure_test:{item.type.value}",
            statement=item.result,
            related_assumption_ids=copy.deepcopy(item.related_assumption_ids),
            repair_action=item.repair_action,
        )
        (fatal if severity is FailureImpact.FATAL else repairable).append(risk)

    evidence_gaps: list[str] = []
    for item in [*priority, *ordered_assumptions]:
        if item.claim.classification is not KnowledgeStatus.KNOWN:
            evidence_gaps.append(f"assumption:{item.id}")
    for item in challenge.blindspot_checks:
        if item.finding is not None and item.finding.classification is not KnowledgeStatus.KNOWN:
            evidence_gaps.append(f"blindspot:{item.category.value}")

    return CandidateChallengeResult(
        candidate_id=challenge.candidate_id,
        blindspots=[item for item in challenge.blindspot_checks if item.finding is not None],
        assumption_register=ordered_assumptions,
        knowledge_summary=knowledge_summary,
        pressure_tests=copy.deepcopy(challenge.pressure_tests),
        prioritized_assumption_ids=[item.id for item in priority],
        fatal_risks=fatal,
        repairable_risks=repairable,
        evidence_gaps=_dedupe(evidence_gaps),
    )


def _validate_candidate_challenge(challenge: CandidateChallengeInput) -> None:
    if not isinstance(challenge, CandidateChallengeInput):
        raise ContractError("challenge must be CandidateChallengeInput")
    _required_string(challenge.candidate_id, "challenge.candidate_id")
    _validate_blindspot_checks(challenge.blindspot_checks)
    _validate_assumption_register(
        challenge.assumption_register, challenge.candidate_id
    )
    _validate_pressure_tests(
        challenge.pressure_tests,
        {item.id for item in challenge.assumption_register},
    )


def _validate_blindspot_checks(checks: list[BlindspotCheck]) -> None:
    if not isinstance(checks, list):
        raise ContractError("blindspot_checks must be a list")
    expected = set(BlindspotCategory)
    actual: list[BlindspotCategory] = []
    for index, check in enumerate(checks):
        path = f"blindspot_checks[{index}]"
        if not isinstance(check, BlindspotCheck):
            raise ContractError(f"{path} must be BlindspotCheck")
        if not isinstance(check.category, BlindspotCategory):
            raise ContractError(f"{path}.category must be BlindspotCategory")
        actual.append(check.category)
        evidence = _string_list(check.evidence, f"{path}.evidence")
        if check.finding is None:
            if evidence:
                raise ContractError(f"{path}.evidence requires a finding")
            continue
        _validate_knowledge_item(check.finding, f"{path}.finding")
        if check.finding.classification is KnowledgeStatus.KNOWN and not evidence:
            raise ContractError(f"{path} KNOWN finding requires evidence")
    if len(actual) != len(set(actual)):
        raise ContractError("blindspot categories must be unique")
    if set(actual) != expected:
        missing = sorted(item.value for item in expected - set(actual))
        raise ContractError(f"blindspot checklist is incomplete; missing {missing}")


def _validate_assumption_register(
    assumptions: list[AssumptionRecord], candidate_id: str
) -> None:
    if not isinstance(assumptions, list) or not assumptions:
        raise ContractError("assumption_register must not be empty")
    ids: set[str] = set()
    for index, item in enumerate(assumptions):
        path = f"assumption_register[{index}]"
        if not isinstance(item, AssumptionRecord):
            raise ContractError(f"{path} must be AssumptionRecord")
        _required_string(item.id, f"{path}.id")
        if item.id in ids:
            raise ContractError(f"duplicate assumption id {item.id!r}")
        ids.add(item.id)
        if item.candidate_id != candidate_id:
            raise ContractError(f"{path}.candidate_id does not match challenge")
        _validate_knowledge_item(item.claim, f"{path}.claim")
        if not isinstance(item.type, AssumptionType):
            raise ContractError(f"{path}.type must be AssumptionType")
        _validate_threshold(item.importance, f"{path}.importance")
        _validate_threshold(item.confidence, f"{path}.confidence")
        evidence = _string_list(item.evidence, f"{path}.evidence")
        if item.claim.classification is KnowledgeStatus.KNOWN and not evidence:
            raise ContractError(f"{path} KNOWN claim requires evidence")
        if not isinstance(item.failure_impact, FailureImpact):
            raise ContractError(f"{path}.failure_impact must be FailureImpact")
        _required_string(item.cheapest_test, f"{path}.cheapest_test")


def _validate_pressure_tests(
    tests: list[PressureTest], assumption_ids: set[str]
) -> None:
    if not isinstance(tests, list):
        raise ContractError("pressure_tests must be a list")
    expected = set(PressureTestType)
    actual: list[PressureTestType] = []
    steelman_index: int | None = None
    fatal_indexes: list[int] = []
    for index, item in enumerate(tests):
        path = f"pressure_tests[{index}]"
        if not isinstance(item, PressureTest):
            raise ContractError(f"{path} must be PressureTest")
        if not isinstance(item.type, PressureTestType):
            raise ContractError(f"{path}.type must be PressureTestType")
        actual.append(item.type)
        _required_string(item.scenario, f"{path}.scenario")
        _required_string(item.result, f"{path}.result")
        if not isinstance(item.risk_class, RiskClass):
            raise ContractError(f"{path}.risk_class must be RiskClass")
        related = _unique_nonempty(
            item.related_assumption_ids, f"{path}.related_assumption_ids"
        )
        unknown = set(related) - assumption_ids
        if unknown:
            raise ContractError(f"{path} references unknown assumptions {sorted(unknown)}")
        if item.risk_class is RiskClass.REPAIRABLE:
            _required_string(item.repair_action, f"{path}.repair_action")
        elif item.repair_action is not None:
            _required_string(item.repair_action, f"{path}.repair_action")
        if item.type is PressureTestType.STEELMAN:
            steelman_index = index
            if item.risk_class is not RiskClass.NONE:
                raise ContractError("STEELMAN cannot itself classify a candidate risk")
        if item.risk_class is RiskClass.FATAL:
            fatal_indexes.append(index)
    if len(actual) != len(set(actual)):
        raise ContractError("pressure test types must be unique")
    if set(actual) != expected:
        missing = sorted(item.value for item in expected - set(actual))
        raise ContractError(f"pressure test suite is incomplete; missing {missing}")
    if fatal_indexes and (
        steelman_index is None or steelman_index > min(fatal_indexes)
    ):
        raise ContractError("STEELMAN must run before a FATAL risk is classified")


def _validate_pre_signals(signals: PreDivergenceSignals) -> None:
    if not isinstance(signals, PreDivergenceSignals):
        raise ContractError("signals must be PreDivergenceSignals")
    for name in (
        "unfamiliar_domain",
        "hidden_norm_risk",
        "stakeholder_or_incentive_risk",
        "technical_constraint_risk",
        "explicit_requested",
    ):
        if type(getattr(signals, name)) is not bool:
            raise ContractError(f"signals.{name} must be boolean")
    _validate_threshold(
        signals.unknown_density_threshold, "signals.unknown_density_threshold"
    )


def _validate_pre_content(content: PreDivergenceContent) -> None:
    if not isinstance(content, PreDivergenceContent):
        raise ContractError("content must be PreDivergenceContent")
    for name in (
        "landmines",
        "hidden_context",
        "what_good_looks_like",
        "expert_questions",
    ):
        if not _string_list(getattr(content, name), f"content.{name}"):
            raise ContractError(f"content.{name} must not be empty")


def _pre_content_has_values(content: PreDivergenceContent) -> bool:
    _validate_pre_content_type_only(content)
    return any(
        getattr(content, name)
        for name in (
            "landmines",
            "hidden_context",
            "what_good_looks_like",
            "expert_questions",
        )
    )


def _validate_pre_content_type_only(content: PreDivergenceContent) -> None:
    if not isinstance(content, PreDivergenceContent):
        raise ContractError("content must be PreDivergenceContent")
    for name in (
        "landmines",
        "hidden_context",
        "what_good_looks_like",
        "expert_questions",
    ):
        _string_list(getattr(content, name), f"content.{name}")


def _unknown_density(state: RuntimeState) -> float:
    frame_items = [
        state.frame.problem,
        state.frame.user,
        state.frame.success,
        state.frame.kill,
        *state.frame.constraints,
        *state.frame.non_goals,
    ]
    denominator = (
        len([item for item in frame_items if item is not None])
        + len(state.assumptions)
        + len(state.unknowns)
        + len(state.evidence)
    )
    return 0.0 if denominator == 0 else len(state.unknowns) / denominator


def _validate_knowledge_item(item: KnowledgeItem, path: str) -> None:
    if not isinstance(item, KnowledgeItem):
        raise ContractError(f"{path} must be KnowledgeItem")
    _required_string(item.statement, f"{path}.statement")
    if not isinstance(item.classification, KnowledgeStatus):
        raise ContractError(f"{path}.classification must be KnowledgeStatus")


def _validate_threshold(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{path} must be numeric")
    if not 0 <= float(value) <= 1:
        raise ContractError(f"{path} must be between 0 and 1")


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise ContractError(f"{path} must contain non-empty strings")
    return list(value)


def _unique_nonempty(values: Sequence[str], path: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ContractError(f"{path} must be a sequence of strings")
    result = _string_list(list(values), path)
    if len(result) != len(set(result)):
        raise ContractError(f"{path} must contain unique values")
    return result


def _dedupe(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in values:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _knowledge_from_dict(value: Any, path: str) -> KnowledgeItem:
    data = _require_exact_keys(value, {"statement", "classification"}, path)
    return KnowledgeItem(
        statement=data["statement"],
        classification=_enum_value(
            KnowledgeStatus, data["classification"], f"{path}.classification"
        ),
    )


def _blindspot_check_from_dict(value: Any, path: str) -> BlindspotCheck:
    data = _require_exact_keys(value, {"category", "finding", "evidence"}, path)
    return BlindspotCheck(
        category=_enum_value(BlindspotCategory, data["category"], f"{path}.category"),
        finding=(
            None
            if data["finding"] is None
            else _knowledge_from_dict(data["finding"], f"{path}.finding")
        ),
        evidence=_string_list(data["evidence"], f"{path}.evidence"),
    )


def _assumption_from_dict(value: Any, path: str) -> AssumptionRecord:
    data = _require_exact_keys(
        value,
        {
            "id",
            "candidate_id",
            "claim",
            "type",
            "importance",
            "confidence",
            "evidence",
            "failure_impact",
            "cheapest_test",
        },
        path,
    )
    return AssumptionRecord(
        id=data["id"],
        candidate_id=data["candidate_id"],
        claim=_knowledge_from_dict(data["claim"], f"{path}.claim"),
        type=_enum_value(AssumptionType, data["type"], f"{path}.type"),
        importance=data["importance"],
        confidence=data["confidence"],
        evidence=_string_list(data["evidence"], f"{path}.evidence"),
        failure_impact=_enum_value(
            FailureImpact, data["failure_impact"], f"{path}.failure_impact"
        ),
        cheapest_test=data["cheapest_test"],
    )


def _pressure_test_from_dict(value: Any, path: str) -> PressureTest:
    data = _require_exact_keys(
        value,
        {
            "type",
            "scenario",
            "result",
            "risk_class",
            "related_assumption_ids",
            "repair_action",
        },
        path,
    )
    return PressureTest(
        type=_enum_value(PressureTestType, data["type"], f"{path}.type"),
        scenario=data["scenario"],
        result=data["result"],
        risk_class=_enum_value(RiskClass, data["risk_class"], f"{path}.risk_class"),
        related_assumption_ids=_string_list(
            data["related_assumption_ids"], f"{path}.related_assumption_ids"
        ),
        repair_action=data["repair_action"],
    )


def challenge_request_from_dict(
    value: Mapping[str, Any]
) -> tuple[RuntimeState, list[str], list[CandidateChallengeInput], float, float]:
    data = _require_exact_keys(
        value,
        {
            "state",
            "candidate_ids",
            "challenges",
            "high_importance_threshold",
            "low_confidence_threshold",
        },
        "request",
    )
    candidate_ids = _string_list(data["candidate_ids"], "request.candidate_ids")
    raw_challenges = _mapping_list(data["challenges"], "request.challenges")
    challenges: list[CandidateChallengeInput] = []
    for index, raw in enumerate(raw_challenges):
        path = f"request.challenges[{index}]"
        item = _require_exact_keys(
            raw,
            {
                "candidate_id",
                "blindspot_checks",
                "assumption_register",
                "pressure_tests",
            },
            path,
        )
        challenges.append(
            CandidateChallengeInput(
                candidate_id=item["candidate_id"],
                blindspot_checks=[
                    _blindspot_check_from_dict(check, f"{path}.blindspot_checks[{i}]")
                    for i, check in enumerate(
                        _mapping_list(item["blindspot_checks"], f"{path}.blindspot_checks")
                    )
                ],
                assumption_register=[
                    _assumption_from_dict(record, f"{path}.assumption_register[{i}]")
                    for i, record in enumerate(
                        _mapping_list(
                            item["assumption_register"], f"{path}.assumption_register"
                        )
                    )
                ],
                pressure_tests=[
                    _pressure_test_from_dict(test, f"{path}.pressure_tests[{i}]")
                    for i, test in enumerate(
                        _mapping_list(item["pressure_tests"], f"{path}.pressure_tests")
                    )
                ],
            )
        )
    return (
        state_from_dict(_require_mapping(data["state"], "request.state")),
        candidate_ids,
        challenges,
        data["high_importance_threshold"],
        data["low_confidence_threshold"],
    )


def pre_request_from_dict(
    value: Mapping[str, Any]
) -> tuple[RuntimeState, PreDivergenceSignals, PreDivergenceContent | None]:
    data = _require_exact_keys(value, {"state", "signals", "content"}, "request")
    signals_data = _require_exact_keys(
        data["signals"],
        {
            "unfamiliar_domain",
            "hidden_norm_risk",
            "stakeholder_or_incentive_risk",
            "technical_constraint_risk",
            "explicit_requested",
            "unknown_density_threshold",
        },
        "request.signals",
    )
    signals = PreDivergenceSignals(**dict(signals_data))
    content = None
    if data["content"] is not None:
        content_data = _require_exact_keys(
            data["content"],
            {"landmines", "hidden_context", "what_good_looks_like", "expert_questions"},
            "request.content",
        )
        content = PreDivergenceContent(
            landmines=_string_list(content_data["landmines"], "request.content.landmines"),
            hidden_context=_string_list(
                content_data["hidden_context"], "request.content.hidden_context"
            ),
            what_good_looks_like=_string_list(
                content_data["what_good_looks_like"],
                "request.content.what_good_looks_like",
            ),
            expert_questions=_string_list(
                content_data["expert_questions"], "request.content.expert_questions"
            ),
        )
    return (
        state_from_dict(_require_mapping(data["state"], "request.state")),
        signals,
        content,
    )


def _mapping_list(value: Any, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be a list")
    return [_require_mapping(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _require_exact_keys(
    value: Any, expected: set[str], path: str
) -> Mapping[str, Any]:
    data = _require_mapping(value, path)
    missing = expected - set(data)
    unknown = set(data) - expected
    if missing:
        raise ContractError(f"{path} is missing keys: {sorted(missing)}")
    if unknown:
        raise ContractError(f"{path} has unknown keys: {sorted(unknown)}")
    return data


def _enum_value(enum_type: type[Enum], value: Any, path: str) -> Any:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        for member in enum_type:
            if value.casefold() in {member.name.casefold(), str(member.value).casefold()}:
                return member
    raise ContractError(f"{path} must be one of {[item.value for item in enum_type]}")


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
        raise ContractError(f"invalid JSON: {exc}") from exc


def _emit(value: Any) -> None:
    json.dump(_json_ready(value), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    pre = subparsers.add_parser("pre-blindspot", help="run the conditional pre-pass")
    pre.add_argument("--json", help="request JSON; defaults to stdin")
    challenge = subparsers.add_parser("challenge", help="run candidate challenges")
    challenge.add_argument("--json", help="request JSON; defaults to stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "pre-blindspot":
            state, signals, content = pre_request_from_dict(
                _require_mapping(_load_json(args.json), "request")
            )
            _emit(run_pre_divergence_blindspot(state, signals, content))
        elif args.command == "challenge":
            state, candidate_ids, challenges, high_threshold, low_threshold = (
                challenge_request_from_dict(
                    _require_mapping(_load_json(args.json), "request")
                )
            )
            _emit(
                run_challenge_engine(
                    state,
                    candidate_ids,
                    challenges,
                    high_importance_threshold=high_threshold,
                    low_confidence_threshold=low_threshold,
                )
            )
        return 0
    except ContractError as exc:
        _emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
