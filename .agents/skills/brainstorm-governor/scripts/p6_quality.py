#!/usr/bin/env python3
"""P6 evaluator/optimizer boundary, tracing, metrics, and final handoff."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from p0_runtime import (
    ContractError,
    DecisionStatus,
    ExitStatus,
    Mode,
    RunStatus,
    RuntimeState,
    Stage,
    validate_state,
)
from p2_persistence import ConceptBrief, save_round
from p4_research import ResearchEvidenceRecord


class EvaluationCheck(str, Enum):
    HARD_CONSTRAINTS = "HARD_CONSTRAINTS"
    OBVIOUS_ALTERNATIVES = "OBVIOUS_ALTERNATIVES"
    EVIDENCE_SUPPORT = "EVIDENCE_SUPPORT"
    FACT_ASSUMPTION_LABELING = "FACT_ASSUMPTION_LABELING"
    TRADEOFF_FAIRNESS = "TRADEOFF_FAIRNESS"
    WEIGHT_SENSITIVITY = "WEIGHT_SENSITIVITY"
    CHEAPEST_TEST_FALSIFIABILITY = "CHEAPEST_TEST_FALSIFIABILITY"


class CorrectionSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class QualityStopReason(str, Enum):
    QUALITY_PASS = "QUALITY_PASS"
    WORDING_ONLY = "WORDING_ONLY"
    INFORMATION_REQUIRED = "INFORMATION_REQUIRED"
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    MAX_EVALUATOR_ROUNDS = "MAX_EVALUATOR_ROUNDS"
    OPTIMIZER_UNAVAILABLE = "OPTIMIZER_UNAVAILABLE"


class ExternalContentTreatment(str, Enum):
    DATA_ONLY = "DATA_ONLY"


REQUIRED_EVALUATION_CRITERIA = tuple(EvaluationCheck)
MAX_EVALUATOR_ROUNDS = 2
_TARGET_PATTERN = re.compile(
    r"^(confirmed_frame|candidates\[[^\]]+\]|recommendation|evidence_summary|"
    r"output_contract)(?:\.[A-Za-z0-9_-]+|\[[^\]]+\])+$"
)
_VAGUE_CORRECTIONS = {
    "continue improving",
    "continue to improve",
    "improve further",
    "keep refining",
    "make it better",
    "继续完善",
    "继续优化",
    "进一步完善",
    "进一步优化",
}


@dataclass(frozen=True)
class EvidenceSummaryItem:
    id: str
    claim: str
    source: str | None
    evidence_strength: str | None
    contradictions: list[str]
    treatment: ExternalContentTreatment = ExternalContentTreatment.DATA_ONLY


@dataclass(frozen=True)
class EvaluatorInput:
    confirmed_frame: dict[str, Any]
    candidates: list[dict[str, Any]]
    recommendation: dict[str, Any] | None
    evaluation_criteria: list[EvaluationCheck]
    evidence_summary: list[EvidenceSummaryItem]
    output_contract: dict[str, Any]


@dataclass(frozen=True)
class ActionableCorrection:
    id: str
    check: EvaluationCheck
    target: str
    issue: str
    required_change: str
    severity: CorrectionSeverity
    high_impact: bool = False
    wording_only: bool = False
    requires_external_information: bool = False
    requires_user_information: bool = False


@dataclass(frozen=True)
class EvaluationReport:
    """Evaluator output contains corrections only; never a regenerated artifact."""

    corrections: list[ActionableCorrection]


@dataclass(frozen=True)
class RuntimeUsage:
    token_usage: int | None = None
    tool_usage: int | None = None


@dataclass(frozen=True)
class EvaluatorInvocation:
    report: EvaluationReport
    usage: RuntimeUsage = RuntimeUsage()


@dataclass
class QualityArtifact:
    confirmed_frame: dict[str, Any]
    candidates: list[dict[str, Any]]
    recommendation: dict[str, Any] | None
    evidence_summary: list[EvidenceSummaryItem]
    output_contract: dict[str, Any]


@dataclass(frozen=True)
class OptimizerResult:
    artifact: QualityArtifact
    applied_correction_ids: list[str]


class Evaluator(Protocol):
    def evaluate(self, request: EvaluatorInput) -> EvaluatorInvocation:
        ...


class Optimizer(Protocol):
    def apply(
        self,
        artifact: QualityArtifact,
        corrections: Sequence[ActionableCorrection],
    ) -> OptimizerResult:
        ...


@dataclass(frozen=True)
class EvaluatorConfig:
    evaluator_rounds: int = 1


@dataclass(frozen=True)
class StageTransitionTrace:
    from_stage: Stage
    to_stage: Stage
    reason: str


@dataclass(frozen=True)
class GateDecisionTrace:
    gate: str
    enabled: bool
    reason: str


@dataclass
class QualityTrace:
    mode: Mode
    stage_transitions: list[StageTransitionTrace] = field(default_factory=list)
    gate_decisions: list[GateDecisionTrace] = field(default_factory=list)
    reframe_count: int = 0
    evaluator_count: int = 0
    research_activated: bool = False
    subagent_activated: bool = False
    exit_status: ExitStatus | None = None
    token_usage: int | None = None
    tool_usage: int | None = None

    def transition(self, from_stage: Stage, to_stage: Stage, reason: str) -> None:
        self.stage_transitions.append(
            StageTransitionTrace(from_stage, to_stage, _required_string(reason, "reason"))
        )

    def gate(self, name: str, enabled: bool, reason: str) -> None:
        if type(enabled) is not bool:
            raise ContractError("gate enabled must be boolean")
        self.gate_decisions.append(
            GateDecisionTrace(
                _required_string(name, "gate"),
                enabled,
                _required_string(reason, "gate reason"),
            )
        )

    def activation(self, *, research: bool = False, subagents: bool = False) -> None:
        if type(research) is not bool or type(subagents) is not bool:
            raise ContractError("activation flags must be boolean")
        self.research_activated = self.research_activated or research
        self.subagent_activated = self.subagent_activated or subagents

    def usage(self, value: RuntimeUsage) -> None:
        _validate_usage(value)
        if value.token_usage is not None:
            self.token_usage = (self.token_usage or 0) + value.token_usage
        if value.tool_usage is not None:
            self.tool_usage = (self.tool_usage or 0) + value.tool_usage


@dataclass
class QualityGateOutcome:
    state: RuntimeState
    artifact: QualityArtifact
    reports: list[EvaluationReport]
    remaining_corrections: list[ActionableCorrection]
    stop_reason: QualityStopReason
    trace: QualityTrace
    approved: bool


class QualityCheckpoint(Protocol):
    def save(self, outcome: QualityGateOutcome) -> None:
        ...


@dataclass
class P2QualityCheckpoint:
    brief_path: str | Path
    brief: ConceptBrief
    trace_path: str | Path

    def save(self, outcome: QualityGateOutcome) -> None:
        next_action = (
            "produce the restricted final handoff"
            if outcome.approved
            else "resume from the saved quality-gate state"
        )
        save_round(
            self.brief_path,
            self.brief,
            outcome.state,
            next_action=next_action,
            previous_stop_reason=outcome.stop_reason.value,
        )
        save_trace(self.trace_path, outcome.trace)


@dataclass(frozen=True)
class FinalHandoff:
    approved_artifact_path: str
    locked_decisions: list[dict[str, Any]]
    open_questions: list[str]
    non_goals: list[str]
    acceptance_criteria: list[str]
    risks: list[str]
    next_validation: str


@dataclass(frozen=True)
class MetricSample:
    case_id: str
    hard_constraints_total: int
    hard_constraints_passed: int
    candidate_count: int
    duplicate_candidate_count: int
    exploration_dimensions_expected: int
    exploration_dimensions_covered: int
    critical_assumptions_expected: int
    critical_assumptions_discovered: int
    fact_inference_labels_total: int
    fact_inference_mislabels: int
    evaluator_rounds: int
    token_usage: int | None = None
    tool_usage: int | None = None


@dataclass(frozen=True)
class CoreMetrics:
    constraint_adherence: float
    candidate_duplication: float
    exploration_coverage: float
    critical_assumption_discovery: float
    fact_inference_mislabel_rate: float
    average_rounds: float
    average_token_cost: float | None
    average_tool_cost: float | None


def evidence_summary_from_records(
    records: Sequence[ResearchEvidenceRecord],
) -> list[EvidenceSummaryItem]:
    """Reduce P4 evidence to DATA_ONLY summaries; omit excerpts and raw payloads."""
    result: list[EvidenceSummaryItem] = []
    seen: set[str] = set()
    for index, item in enumerate(records):
        if not isinstance(item, ResearchEvidenceRecord):
            raise ContractError(f"evidence[{index}] must be ResearchEvidenceRecord")
        if item.id in seen:
            raise ContractError(f"duplicate evidence id {item.id!r}")
        seen.add(item.id)
        result.append(
            EvidenceSummaryItem(
                id=_required_string(item.id, f"evidence[{index}].id"),
                claim=_required_string(item.claim, f"evidence[{index}].claim"),
                source=_optional_string(item.source, f"evidence[{index}].source"),
                evidence_strength=item.evidence_strength.value,
                contradictions=_unique_strings(
                    item.contradictions, f"evidence[{index}].contradictions"
                ),
            )
        )
    return result


def artifact_from_state(
    state: RuntimeState,
    *,
    evidence_summary: Sequence[EvidenceSummaryItem] = (),
    output_contract: Mapping[str, Any],
) -> QualityArtifact:
    validate_state(state)
    recommendation = (
        None
        if state.result.recommendation is None
        else {
            "candidate_id": state.result.recommendation,
            "confidence": state.result.confidence,
            "cheapest_test": state.result.cheapest_test,
        }
    )
    artifact = QualityArtifact(
        confirmed_frame=_frame_to_dict(state),
        candidates=copy.deepcopy(state.candidates),
        recommendation=recommendation,
        evidence_summary=copy.deepcopy(list(evidence_summary)),
        output_contract=copy.deepcopy(dict(output_contract)),
    )
    validate_quality_artifact(artifact)
    return artifact


def build_evaluator_input(artifact: QualityArtifact) -> EvaluatorInput:
    validate_quality_artifact(artifact)
    return EvaluatorInput(
        confirmed_frame=copy.deepcopy(artifact.confirmed_frame),
        candidates=copy.deepcopy(artifact.candidates),
        recommendation=copy.deepcopy(artifact.recommendation),
        evaluation_criteria=list(REQUIRED_EVALUATION_CRITERIA),
        evidence_summary=copy.deepcopy(artifact.evidence_summary),
        output_contract=copy.deepcopy(artifact.output_contract),
    )


def run_evaluator_optimizer(
    state: RuntimeState,
    artifact: QualityArtifact,
    evaluator: Evaluator,
    optimizer: Optimizer | None = None,
    *,
    config: EvaluatorConfig = EvaluatorConfig(),
    trace: QualityTrace | None = None,
    checkpoint: QualityCheckpoint | None = None,
) -> QualityGateOutcome:
    """Run at most two targeted evaluation rounds and stop deterministically."""
    validate_state(state)
    validate_quality_artifact(artifact)
    _validate_config(config)
    if not hasattr(evaluator, "evaluate"):
        raise ContractError("evaluator must implement evaluate")
    if optimizer is not None and not hasattr(optimizer, "apply"):
        raise ContractError("optimizer must implement apply")
    working_state = copy.deepcopy(state)
    working_artifact = copy.deepcopy(artifact)
    working_trace = copy.deepcopy(trace or QualityTrace(mode=state.run.mode))
    if working_trace.mode is not state.run.mode:
        raise ContractError("trace mode must match state mode")
    reports: list[EvaluationReport] = []

    for round_index in range(config.evaluator_rounds):
        if working_state.run.budget.used_steps >= working_state.run.budget.max_steps:
            working_trace.gate("evaluation_budget", False, "run budget is exhausted")
            return _finish(
                working_state,
                working_artifact,
                reports,
                [],
                QualityStopReason.BUDGET_EXHAUSTED,
                ExitStatus.PARK,
                working_trace,
                checkpoint,
            )

        working_trace.gate(
            "evaluation_budget",
            True,
            f"budget permits evaluator round {round_index + 1}",
        )
        _enter_evaluation(working_state, working_trace, round_index + 1)
        request = build_evaluator_input(working_artifact)
        invocation = evaluator.evaluate(copy.deepcopy(request))
        _validate_invocation(invocation)
        working_trace.evaluator_count += 1
        working_trace.usage(invocation.usage)
        report = copy.deepcopy(invocation.report)
        reports.append(report)
        corrections = report.corrections

        if any(
            item.requires_external_information or item.requires_user_information
            for item in corrections
        ):
            return _finish(
                working_state,
                working_artifact,
                reports,
                corrections,
                QualityStopReason.INFORMATION_REQUIRED,
                ExitStatus.NEEDS_INPUT,
                working_trace,
                checkpoint,
            )

        if _quality_passes(corrections):
            reason = (
                QualityStopReason.WORDING_ONLY
                if corrections
                else QualityStopReason.QUALITY_PASS
            )
            return _finish(
                working_state,
                working_artifact,
                reports,
                corrections,
                reason,
                ExitStatus.COMMIT,
                working_trace,
                checkpoint,
            )

        if round_index + 1 >= config.evaluator_rounds:
            return _finish(
                working_state,
                working_artifact,
                reports,
                corrections,
                QualityStopReason.MAX_EVALUATOR_ROUNDS,
                ExitStatus.ITERATE,
                working_trace,
                checkpoint,
            )

        if optimizer is None:
            return _finish(
                working_state,
                working_artifact,
                reports,
                corrections,
                QualityStopReason.OPTIMIZER_UNAVAILABLE,
                ExitStatus.ITERATE,
                working_trace,
                checkpoint,
            )

        result = optimizer.apply(
            copy.deepcopy(working_artifact), copy.deepcopy(corrections)
        )
        _validate_optimizer_result(result, corrections)
        if any(item.target.startswith("confirmed_frame.") for item in corrections):
            working_trace.reframe_count += 1
        working_artifact = copy.deepcopy(result.artifact)

    raise AssertionError("evaluator loop ended without a terminal outcome")


def validate_quality_artifact(artifact: QualityArtifact) -> None:
    if not isinstance(artifact, QualityArtifact):
        raise ContractError("artifact must be QualityArtifact")
    if not isinstance(artifact.confirmed_frame, dict):
        raise ContractError("confirmed_frame must be an object")
    if not isinstance(artifact.candidates, list) or any(
        not isinstance(item, dict) for item in artifact.candidates
    ):
        raise ContractError("candidates must be a list of objects")
    if artifact.recommendation is not None and not isinstance(
        artifact.recommendation, dict
    ):
        raise ContractError("recommendation must be an object or null")
    if not isinstance(artifact.evidence_summary, list):
        raise ContractError("evidence_summary must be a list")
    for index, item in enumerate(artifact.evidence_summary):
        _validate_evidence_summary(item, f"evidence_summary[{index}]")
    if not isinstance(artifact.output_contract, dict) or not artifact.output_contract:
        raise ContractError("output_contract must be a non-empty object")


def validate_evaluation_report(report: EvaluationReport) -> None:
    if not isinstance(report, EvaluationReport):
        raise ContractError("evaluator report must be EvaluationReport")
    if not isinstance(report.corrections, list):
        raise ContractError("evaluator corrections must be a list")
    ids: set[str] = set()
    for index, item in enumerate(report.corrections):
        _validate_correction(item, f"corrections[{index}]")
        if item.id in ids:
            raise ContractError(f"duplicate correction id {item.id!r}")
        ids.add(item.id)


def build_final_handoff(
    outcome: QualityGateOutcome,
    *,
    approved_artifact_path: str | Path,
    acceptance_criteria: Sequence[str],
    risks: Sequence[str],
    next_validation: str,
) -> FinalHandoff:
    if not isinstance(outcome, QualityGateOutcome) or not outcome.approved:
        raise ContractError("final handoff requires an approved quality outcome")
    if outcome.state.result.exit_status is not ExitStatus.COMMIT:
        raise ContractError("final handoff requires COMMIT exit status")
    path = Path(approved_artifact_path)
    if not path.is_absolute() or not path.exists():
        raise ContractError("approved_artifact_path must be an existing absolute path")
    criteria = _unique_strings(acceptance_criteria, "acceptance_criteria")
    if outcome.state.frame.success is not None:
        criteria = _dedupe(
            [outcome.state.frame.success.statement, *criteria]
        )
    return FinalHandoff(
        approved_artifact_path=str(path),
        locked_decisions=[
            {
                "id": item.id,
                "topic": item.topic,
                "value": copy.deepcopy(item.value),
            }
            for item in outcome.state.decisions
            if item.status is DecisionStatus.LOCKED
        ],
        open_questions=[item.statement for item in outcome.state.unknowns],
        non_goals=[item.statement for item in outcome.state.frame.non_goals],
        acceptance_criteria=criteria,
        risks=_unique_strings(risks, "risks"),
        next_validation=_required_string(next_validation, "next_validation"),
    )


def handoff_to_dict(handoff: FinalHandoff) -> dict[str, Any]:
    if not isinstance(handoff, FinalHandoff):
        raise ContractError("handoff must be FinalHandoff")
    return _json_ready(handoff)


def aggregate_metrics(samples: Sequence[MetricSample]) -> CoreMetrics:
    items = list(samples)
    if not items:
        raise ContractError("at least one metric sample is required")
    for index, item in enumerate(items):
        _validate_metric_sample(item, f"samples[{index}]")
    return CoreMetrics(
        constraint_adherence=_ratio(
            sum(item.hard_constraints_passed for item in items),
            sum(item.hard_constraints_total for item in items),
            empty=1.0,
        ),
        candidate_duplication=_ratio(
            sum(item.duplicate_candidate_count for item in items),
            sum(item.candidate_count for item in items),
            empty=0.0,
        ),
        exploration_coverage=_ratio(
            sum(item.exploration_dimensions_covered for item in items),
            sum(item.exploration_dimensions_expected for item in items),
            empty=1.0,
        ),
        critical_assumption_discovery=_ratio(
            sum(item.critical_assumptions_discovered for item in items),
            sum(item.critical_assumptions_expected for item in items),
            empty=1.0,
        ),
        fact_inference_mislabel_rate=_ratio(
            sum(item.fact_inference_mislabels for item in items),
            sum(item.fact_inference_labels_total for item in items),
            empty=0.0,
        ),
        average_rounds=sum(item.evaluator_rounds for item in items) / len(items),
        average_token_cost=_optional_average(
            [item.token_usage for item in items if item.token_usage is not None]
        ),
        average_tool_cost=_optional_average(
            [item.tool_usage for item in items if item.tool_usage is not None]
        ),
    )


def trace_to_dict(trace: QualityTrace) -> dict[str, Any]:
    _validate_trace(trace)
    return _json_ready(trace)


def save_trace(path: str | Path, trace: QualityTrace) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        trace_to_dict(trace), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(destination)


def _enter_evaluation(
    state: RuntimeState, trace: QualityTrace, round_number: int
) -> None:
    previous = state.run.stage
    state.result.exit_status = None
    state.run.status = RunStatus.ACTIVE
    state.run.stage = Stage.EVALUATE
    state.run.budget.used_steps += 1
    validate_state(state)
    trace.transition(previous, Stage.EVALUATE, f"evaluator round {round_number}")


def _finish(
    state: RuntimeState,
    artifact: QualityArtifact,
    reports: list[EvaluationReport],
    corrections: list[ActionableCorrection],
    reason: QualityStopReason,
    exit_status: ExitStatus,
    trace: QualityTrace,
    checkpoint: QualityCheckpoint | None,
) -> QualityGateOutcome:
    previous = state.run.stage
    approved = exit_status is ExitStatus.COMMIT
    state.run.stage = Stage.COMPLETE if approved else Stage.STOPPED
    state.run.status = RunStatus.COMPLETED if approved else RunStatus.STOPPED
    state.result.exit_status = exit_status
    validate_state(state)
    if previous is not state.run.stage:
        trace.transition(previous, state.run.stage, reason.value)
    trace.exit_status = exit_status
    outcome = QualityGateOutcome(
        state=copy.deepcopy(state),
        artifact=copy.deepcopy(artifact),
        reports=copy.deepcopy(reports),
        remaining_corrections=copy.deepcopy(corrections),
        stop_reason=reason,
        trace=copy.deepcopy(trace),
        approved=approved,
    )
    if checkpoint is not None:
        if not hasattr(checkpoint, "save"):
            raise ContractError("checkpoint must implement save")
        checkpoint.save(copy.deepcopy(outcome))
    return outcome


def _quality_passes(corrections: Sequence[ActionableCorrection]) -> bool:
    hard_violation = any(
        item.check is EvaluationCheck.HARD_CONSTRAINTS for item in corrections
    )
    high_impact_gap = any(item.high_impact for item in corrections)
    substantive_change = any(not item.wording_only for item in corrections)
    return not hard_violation and not high_impact_gap and not substantive_change


def _validate_invocation(invocation: EvaluatorInvocation) -> None:
    if not isinstance(invocation, EvaluatorInvocation):
        raise ContractError("evaluator must return EvaluatorInvocation")
    validate_evaluation_report(invocation.report)
    _validate_usage(invocation.usage)


def _validate_optimizer_result(
    result: OptimizerResult, corrections: Sequence[ActionableCorrection]
) -> None:
    if not isinstance(result, OptimizerResult):
        raise ContractError("optimizer must return OptimizerResult")
    validate_quality_artifact(result.artifact)
    applied = _unique_strings(result.applied_correction_ids, "applied_correction_ids")
    expected = {item.id for item in corrections}
    if set(applied) != expected:
        raise ContractError("optimizer must acknowledge every requested correction")


def _validate_correction(item: ActionableCorrection, path: str) -> None:
    if not isinstance(item, ActionableCorrection):
        raise ContractError(f"{path} must be ActionableCorrection")
    _required_string(item.id, f"{path}.id")
    if not isinstance(item.check, EvaluationCheck):
        raise ContractError(f"{path}.check must be EvaluationCheck")
    target = _required_string(item.target, f"{path}.target")
    if not _TARGET_PATTERN.fullmatch(target):
        raise ContractError(f"{path}.target must identify a specific output field")
    _required_string(item.issue, f"{path}.issue")
    change = _required_string(item.required_change, f"{path}.required_change")
    if change.casefold() in _VAGUE_CORRECTIONS:
        raise ContractError(f"{path}.required_change is not actionable")
    if not isinstance(item.severity, CorrectionSeverity):
        raise ContractError(f"{path}.severity must be CorrectionSeverity")
    for name in (
        "high_impact",
        "wording_only",
        "requires_external_information",
        "requires_user_information",
    ):
        if type(getattr(item, name)) is not bool:
            raise ContractError(f"{path}.{name} must be boolean")
    if item.wording_only and item.high_impact:
        raise ContractError(f"{path} cannot be wording-only and high-impact")
    if item.check is EvaluationCheck.HARD_CONSTRAINTS:
        if item.wording_only or not item.high_impact or item.severity is not CorrectionSeverity.HIGH:
            raise ContractError(
                f"{path} hard-constraint correction must be HIGH and high-impact"
            )


def _validate_evidence_summary(item: EvidenceSummaryItem, path: str) -> None:
    if not isinstance(item, EvidenceSummaryItem):
        raise ContractError(f"{path} must be EvidenceSummaryItem")
    _required_string(item.id, f"{path}.id")
    _required_string(item.claim, f"{path}.claim")
    _optional_string(item.source, f"{path}.source")
    _optional_string(item.evidence_strength, f"{path}.evidence_strength")
    _unique_strings(item.contradictions, f"{path}.contradictions")
    if item.treatment is not ExternalContentTreatment.DATA_ONLY:
        raise ContractError(f"{path} external content must remain DATA_ONLY")


def _validate_config(config: EvaluatorConfig) -> None:
    if not isinstance(config, EvaluatorConfig):
        raise ContractError("config must be EvaluatorConfig")
    if type(config.evaluator_rounds) is not int or not (
        1 <= config.evaluator_rounds <= MAX_EVALUATOR_ROUNDS
    ):
        raise ContractError("evaluator_rounds must be between 1 and 2")


def _validate_usage(value: RuntimeUsage) -> None:
    if not isinstance(value, RuntimeUsage):
        raise ContractError("usage must be RuntimeUsage")
    for name in ("token_usage", "tool_usage"):
        amount = getattr(value, name)
        if amount is not None and (type(amount) is not int or amount < 0):
            raise ContractError(f"{name} must be an integer >= 0 or null")


def _validate_trace(trace: QualityTrace) -> None:
    if not isinstance(trace, QualityTrace) or not isinstance(trace.mode, Mode):
        raise ContractError("trace must have a valid mode")
    for name in ("reframe_count", "evaluator_count"):
        value = getattr(trace, name)
        if type(value) is not int or value < 0:
            raise ContractError(f"trace.{name} must be an integer >= 0")
    _validate_usage(RuntimeUsage(trace.token_usage, trace.tool_usage))


def _validate_metric_sample(item: MetricSample, path: str) -> None:
    if not isinstance(item, MetricSample):
        raise ContractError(f"{path} must be MetricSample")
    _required_string(item.case_id, f"{path}.case_id")
    pairs = (
        (item.hard_constraints_passed, item.hard_constraints_total, "hard_constraints"),
        (item.duplicate_candidate_count, item.candidate_count, "candidate_duplicates"),
        (
            item.exploration_dimensions_covered,
            item.exploration_dimensions_expected,
            "exploration_dimensions",
        ),
        (
            item.critical_assumptions_discovered,
            item.critical_assumptions_expected,
            "critical_assumptions",
        ),
        (
            item.fact_inference_mislabels,
            item.fact_inference_labels_total,
            "fact_inference_labels",
        ),
    )
    for numerator, denominator, name in pairs:
        if type(numerator) is not int or type(denominator) is not int:
            raise ContractError(f"{path}.{name} counts must be integers")
        if numerator < 0 or denominator < 0 or numerator > denominator:
            raise ContractError(f"{path}.{name} counts are inconsistent")
    if type(item.evaluator_rounds) is not int or not (
        0 <= item.evaluator_rounds <= MAX_EVALUATOR_ROUNDS
    ):
        raise ContractError(f"{path}.evaluator_rounds must be between 0 and 2")
    _validate_usage(RuntimeUsage(item.token_usage, item.tool_usage))


def _frame_to_dict(state: RuntimeState) -> dict[str, Any]:
    return {
        "problem": _json_ready(state.frame.problem),
        "user": _json_ready(state.frame.user),
        "constraints": _json_ready(state.frame.constraints),
        "success": _json_ready(state.frame.success),
        "kill": _json_ready(state.frame.kill),
        "non_goals": _json_ready(state.frame.non_goals),
    }


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, path)


def _unique_strings(values: Sequence[str], path: str) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ContractError(f"{path} must be a sequence of strings")
    result: list[str] = []
    for index, item in enumerate(values):
        cleaned = _required_string(item, f"{path}[{index}]")
        if cleaned in result:
            raise ContractError(f"{path} must not contain duplicates")
        result.append(cleaned)
    return result


def _dedupe(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _ratio(numerator: int, denominator: int, *, empty: float) -> float:
    return empty if denominator == 0 else numerator / denominator


def _optional_average(values: Sequence[int]) -> float | None:
    return None if not values else sum(values) / len(values)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _json_ready(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return copy.deepcopy(value)
