#!/usr/bin/env python3
"""Deterministic P0 state, routing, validation, and decision-lock contracts."""

from __future__ import annotations

import argparse
import copy
import json
import sys
import uuid
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class Mode(str, Enum):
    SPARK = "Spark"
    SHAPE = "Shape"
    STRESS = "Stress"
    DECIDE = "Decide"


class Stage(str, Enum):
    INITIALIZE = "INITIALIZE"
    ROUTE = "ROUTE"
    CONTEXT = "CONTEXT"
    FRAME = "FRAME"
    DIVERGE = "DIVERGE"
    NORMALIZE = "NORMALIZE"
    CHALLENGE = "CHALLENGE"
    RESEARCH = "RESEARCH"
    CONVERGE = "CONVERGE"
    EVALUATE = "EVALUATE"
    COMMIT = "COMMIT"
    COMPLETE = "COMPLETE"
    STOPPED = "STOPPED"


class RunStatus(str, Enum):
    READY = "READY"
    ACTIVE = "ACTIVE"
    WAITING = "WAITING"
    COMPLETED = "COMPLETED"
    STOPPED = "STOPPED"


class ExitStatus(str, Enum):
    EXPLORE = "EXPLORE"
    RESEARCH_REQUIRED = "RESEARCH_REQUIRED"
    ITERATE = "ITERATE"
    COMMIT = "COMMIT"
    PARK = "PARK"
    NEEDS_INPUT = "NEEDS_INPUT"


class KnowledgeStatus(str, Enum):
    KNOWN = "KNOWN"
    ASSUMPTION = "ASSUMPTION"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


class DecisionStatus(str, Enum):
    OPEN = "OPEN"
    LOCKED = "LOCKED"


class ContractError(ValueError):
    """Base error for invalid routing or state contracts."""


class StateValidationError(ContractError):
    def __init__(self, errors: Sequence[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


class LockedDecisionConflict(ContractError):
    """Raised when an update would silently overwrite a locked decision."""


@dataclass
class Budget:
    max_steps: int = 32
    used_steps: int = 0
    max_parallelism: int = 1


@dataclass
class Run:
    id: str
    mode: Mode
    stage: Stage
    status: RunStatus
    budget: Budget


@dataclass
class KnowledgeItem:
    statement: str
    classification: KnowledgeStatus


@dataclass
class Frame:
    problem: KnowledgeItem | None = None
    user: KnowledgeItem | None = None
    constraints: list[KnowledgeItem] = field(default_factory=list)
    success: KnowledgeItem | None = None
    kill: KnowledgeItem | None = None
    non_goals: list[KnowledgeItem] = field(default_factory=list)


@dataclass
class EvidenceRecord:
    id: str
    claim: str
    classification: KnowledgeStatus
    source: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class Decision:
    id: str
    topic: str
    value: Any
    status: DecisionStatus = DecisionStatus.OPEN
    rationale: str | None = None


@dataclass
class Result:
    shortlist: list[str] = field(default_factory=list)
    recommendation: str | None = None
    confidence: float | None = None
    cheapest_test: str | None = None
    exit_status: ExitStatus | None = None


@dataclass
class RuntimeState:
    run: Run
    frame: Frame
    candidates: list[dict[str, Any]]
    assumptions: list[KnowledgeItem]
    unknowns: list[KnowledgeItem]
    evidence: list[EvidenceRecord]
    decisions: list[Decision]
    deferred: list[dict[str, Any]]
    result: Result
    routing_reason: str
    research_allowed: bool
    parallelism: int


@dataclass
class RoutingInput:
    explicit_mode: Mode | None = None
    has_existing_solution: bool = False
    validation_requested: bool = False
    high_cost: bool = False
    low_reversibility: bool = False
    multi_option_decision: bool = False
    ambiguous_concept: bool = False
    low_risk: bool = False
    rapid_ideation: bool = False
    current_mode: Mode | None = None
    research_allowed: bool = False
    requested_parallelism: int = 1
    budget: Budget = field(default_factory=Budget)


@dataclass(frozen=True)
class RoutingResult:
    mode: Mode
    routing_reason: str
    research_allowed: bool
    parallelism: int
    budget: Budget


MODE_COMPLEXITY = {
    Mode.SPARK: 0,
    Mode.SHAPE: 1,
    Mode.STRESS: 2,
    Mode.DECIDE: 3,
}


def route_mode(request: RoutingInput) -> RoutingResult:
    """Route deterministically and prevent automatic silent downgrade."""
    _validate_routing_input(request)

    if request.explicit_mode is not None:
        selected = request.explicit_mode
        reason = f"explicit mode override: {selected.value}"
        explicit = True
    elif request.has_existing_solution and request.validation_requested:
        selected = Mode.STRESS
        reason = "existing solution plus validation request"
        explicit = False
    elif request.multi_option_decision and (
        request.high_cost or request.low_reversibility
    ):
        selected = Mode.DECIDE
        reason = "high-cost or low-reversibility multi-option decision"
        explicit = False
    elif request.ambiguous_concept:
        selected = Mode.SHAPE
        reason = "ambiguous concept shaping"
        explicit = False
    elif request.low_risk and request.rapid_ideation:
        selected = Mode.SPARK
        reason = "low-risk rapid ideation"
        explicit = False
    else:
        selected = Mode.SHAPE
        reason = "insufficient routing signals; conservative Shape default"
        explicit = False

    if (
        not explicit
        and request.current_mode is not None
        and MODE_COMPLEXITY[selected] < MODE_COMPLEXITY[request.current_mode]
    ):
        reason = (
            f"preserved current {request.current_mode.value} mode; "
            f"automatic {selected.value} would silently downgrade complexity"
        )
        selected = request.current_mode

    return RoutingResult(
        mode=selected,
        routing_reason=reason,
        research_allowed=request.research_allowed,
        parallelism=request.requested_parallelism,
        budget=copy.deepcopy(request.budget),
    )


def new_state(request: RoutingInput, run_id: str | None = None) -> RuntimeState:
    """Create a validated empty P0 state from a routing request."""
    routing = route_mode(request)
    state = RuntimeState(
        run=Run(
            id=run_id or f"run-{uuid.uuid4().hex}",
            mode=routing.mode,
            stage=Stage.ROUTE,
            status=RunStatus.READY,
            budget=routing.budget,
        ),
        frame=Frame(),
        candidates=[],
        assumptions=[],
        unknowns=[],
        evidence=[],
        decisions=[],
        deferred=[],
        result=Result(),
        routing_reason=routing.routing_reason,
        research_allowed=routing.research_allowed,
        parallelism=routing.parallelism,
    )
    validate_state(state)
    return state


def upsert_decision(state: RuntimeState, decision: Decision) -> RuntimeState:
    """Return a copy with a decision applied, rejecting locked conflicts."""
    validate_state(state)
    updated = copy.deepcopy(state)

    for index, existing in enumerate(updated.decisions):
        if existing.id != decision.id:
            continue
        if existing.status is DecisionStatus.LOCKED:
            if _json_ready(existing) != _json_ready(decision):
                raise LockedDecisionConflict(
                    f"decision {decision.id!r} is LOCKED and cannot be overwritten"
                )
            return updated
        updated.decisions[index] = copy.deepcopy(decision)
        validate_state(updated)
        return updated

    updated.decisions.append(copy.deepcopy(decision))
    validate_state(updated)
    return updated


def validate_state(state: RuntimeState) -> None:
    """Validate cross-field P0 invariants and raise all detected errors."""
    errors: list[str] = []

    if not isinstance(state, RuntimeState):
        raise StateValidationError(["state must be RuntimeState"])

    if not isinstance(state.run.id, str) or not state.run.id.strip():
        errors.append("run.id must be a non-empty string")
    if not isinstance(state.run.mode, Mode):
        errors.append("run.mode must be a valid Mode")
    if not isinstance(state.run.stage, Stage):
        errors.append("run.stage must be a valid Stage")
    if not isinstance(state.run.status, RunStatus):
        errors.append("run.status must be a valid RunStatus")

    _validate_budget(state.run.budget, errors, "run.budget")

    if type(state.research_allowed) is not bool:
        errors.append("research_allowed must be boolean")
    if type(state.parallelism) is not int or state.parallelism < 1:
        errors.append("parallelism must be an integer >= 1")
    elif state.parallelism > state.run.budget.max_parallelism:
        errors.append("parallelism cannot exceed run.budget.max_parallelism")
    if state.run.stage is Stage.RESEARCH and not state.research_allowed:
        errors.append("RESEARCH stage requires research_allowed=true")
    if not isinstance(state.routing_reason, str) or not state.routing_reason.strip():
        errors.append("routing_reason must be a non-empty string")

    _validate_frame(state.frame, errors)
    _validate_mapping_list(state.candidates, errors, "candidates")
    _validate_mapping_list(state.deferred, errors, "deferred")
    _validate_knowledge_list(
        state.assumptions, KnowledgeStatus.ASSUMPTION, errors, "assumptions"
    )
    _validate_knowledge_list(
        state.unknowns, KnowledgeStatus.UNKNOWN, errors, "unknowns"
    )
    _validate_evidence(state.evidence, errors)
    _validate_decisions(state.decisions, errors)
    _validate_result(state.result, errors)

    unknown_claims = {_normalize(item.statement) for item in state.unknowns}
    assumption_claims = {_normalize(item.statement) for item in state.assumptions}
    known_evidence = {
        _normalize(item.claim)
        for item in state.evidence
        if item.classification is KnowledgeStatus.KNOWN
    }
    for claim in sorted((unknown_claims | assumption_claims) & known_evidence):
        errors.append(
            f"claim {claim!r} cannot be both UNKNOWN/ASSUMPTION and KNOWN evidence"
        )

    terminal = state.run.status in {RunStatus.COMPLETED, RunStatus.STOPPED}
    if terminal and state.result.exit_status is None:
        errors.append("terminal run status requires result.exit_status")
    if not terminal and state.result.exit_status is not None:
        errors.append("non-terminal run status cannot set result.exit_status")

    if errors:
        raise StateValidationError(errors)


def state_from_dict(data: Mapping[str, Any]) -> RuntimeState:
    """Parse a strict JSON-compatible mapping into a validated state."""
    _require_mapping(data, "state")
    _require_keys(
        data,
        {
            "run",
            "frame",
            "candidates",
            "assumptions",
            "unknowns",
            "evidence",
            "decisions",
            "deferred",
            "result",
            "routing_reason",
            "research_allowed",
            "parallelism",
        },
        "state",
    )

    run_data = _require_mapping(data["run"], "run")
    _require_keys(run_data, {"id", "mode", "stage", "status", "budget"}, "run")
    frame_data = _require_mapping(data["frame"], "frame")
    _require_keys(
        frame_data,
        {"problem", "user", "constraints", "success", "kill", "non_goals"},
        "frame",
    )
    result_data = _require_mapping(data["result"], "result")
    _require_keys(
        result_data,
        {"shortlist", "recommendation", "confidence", "cheapest_test", "exit_status"},
        "result",
    )

    state = RuntimeState(
        run=Run(
            id=run_data["id"],
            mode=_enum_value(Mode, run_data["mode"], "run.mode"),
            stage=_enum_value(Stage, run_data["stage"], "run.stage"),
            status=_enum_value(RunStatus, run_data["status"], "run.status"),
            budget=_budget_from_dict(run_data["budget"]),
        ),
        frame=Frame(
            problem=_optional_knowledge(frame_data["problem"], "frame.problem"),
            user=_optional_knowledge(frame_data["user"], "frame.user"),
            constraints=_knowledge_list(frame_data["constraints"], "frame.constraints"),
            success=_optional_knowledge(frame_data["success"], "frame.success"),
            kill=_optional_knowledge(frame_data["kill"], "frame.kill"),
            non_goals=_knowledge_list(frame_data["non_goals"], "frame.non_goals"),
        ),
        candidates=_mapping_list(data["candidates"], "candidates"),
        assumptions=_knowledge_list(data["assumptions"], "assumptions"),
        unknowns=_knowledge_list(data["unknowns"], "unknowns"),
        evidence=_evidence_list(data["evidence"]),
        decisions=_decision_list(data["decisions"]),
        deferred=_mapping_list(data["deferred"], "deferred"),
        result=Result(
            shortlist=_string_list(result_data["shortlist"], "result.shortlist"),
            recommendation=_optional_string(
                result_data["recommendation"], "result.recommendation"
            ),
            confidence=result_data["confidence"],
            cheapest_test=_optional_string(
                result_data["cheapest_test"], "result.cheapest_test"
            ),
            exit_status=(
                None
                if result_data["exit_status"] is None
                else _enum_value(
                    ExitStatus, result_data["exit_status"], "result.exit_status"
                )
            ),
        ),
        routing_reason=data["routing_reason"],
        research_allowed=data["research_allowed"],
        parallelism=data["parallelism"],
    )
    validate_state(state)
    return state


def routing_input_from_dict(data: Mapping[str, Any]) -> RoutingInput:
    _require_mapping(data, "routing_input")
    allowed = {
        "explicit_mode",
        "has_existing_solution",
        "validation_requested",
        "high_cost",
        "low_reversibility",
        "multi_option_decision",
        "ambiguous_concept",
        "low_risk",
        "rapid_ideation",
        "current_mode",
        "research_allowed",
        "requested_parallelism",
        "budget",
    }
    unknown = set(data) - allowed
    if unknown:
        raise ContractError(f"routing_input has unknown keys: {sorted(unknown)}")

    boolean_fields = {
        "has_existing_solution",
        "validation_requested",
        "high_cost",
        "low_reversibility",
        "multi_option_decision",
        "ambiguous_concept",
        "low_risk",
        "rapid_ideation",
        "research_allowed",
    }
    for key in boolean_fields & set(data):
        if type(data[key]) is not bool:
            raise ContractError(f"routing_input.{key} must be boolean")

    return RoutingInput(
        explicit_mode=(
            None
            if data.get("explicit_mode") is None
            else _enum_value(Mode, data["explicit_mode"], "explicit_mode")
        ),
        has_existing_solution=data.get("has_existing_solution", False),
        validation_requested=data.get("validation_requested", False),
        high_cost=data.get("high_cost", False),
        low_reversibility=data.get("low_reversibility", False),
        multi_option_decision=data.get("multi_option_decision", False),
        ambiguous_concept=data.get("ambiguous_concept", False),
        low_risk=data.get("low_risk", False),
        rapid_ideation=data.get("rapid_ideation", False),
        current_mode=(
            None
            if data.get("current_mode") is None
            else _enum_value(Mode, data["current_mode"], "current_mode")
        ),
        research_allowed=data.get("research_allowed", False),
        requested_parallelism=data.get("requested_parallelism", 1),
        budget=_budget_from_dict(data.get("budget", {}), allow_defaults=True),
    )


def state_to_dict(state: RuntimeState) -> dict[str, Any]:
    validate_state(state)
    return _json_ready(state)


def _validate_routing_input(request: RoutingInput) -> None:
    errors: list[str] = []
    _validate_budget(request.budget, errors, "budget")
    if request.explicit_mode is not None and not isinstance(request.explicit_mode, Mode):
        errors.append("explicit_mode must be a valid Mode")
    if request.current_mode is not None and not isinstance(request.current_mode, Mode):
        errors.append("current_mode must be a valid Mode")
    for name in (
        "has_existing_solution",
        "validation_requested",
        "high_cost",
        "low_reversibility",
        "multi_option_decision",
        "ambiguous_concept",
        "low_risk",
        "rapid_ideation",
        "research_allowed",
    ):
        if type(getattr(request, name)) is not bool:
            errors.append(f"{name} must be boolean")
    if type(request.requested_parallelism) is not int or request.requested_parallelism < 1:
        errors.append("requested_parallelism must be an integer >= 1")
    elif request.requested_parallelism > request.budget.max_parallelism:
        errors.append("requested_parallelism cannot exceed budget.max_parallelism")
    if errors:
        raise StateValidationError(errors)


def _validate_budget(budget: Budget, errors: list[str], path: str) -> None:
    if not isinstance(budget, Budget):
        errors.append(f"{path} must be Budget")
        return
    for name in ("max_steps", "used_steps", "max_parallelism"):
        value = getattr(budget, name)
        if type(value) is not int:
            errors.append(f"{path}.{name} must be an integer")
    if type(budget.max_steps) is int and budget.max_steps < 1:
        errors.append(f"{path}.max_steps must be >= 1")
    if type(budget.used_steps) is int and budget.used_steps < 0:
        errors.append(f"{path}.used_steps must be >= 0")
    if (
        type(budget.max_steps) is int
        and type(budget.used_steps) is int
        and budget.used_steps > budget.max_steps
    ):
        errors.append(f"{path}.used_steps cannot exceed max_steps")
    if type(budget.max_parallelism) is int and budget.max_parallelism < 1:
        errors.append(f"{path}.max_parallelism must be >= 1")


def _validate_frame(frame: Frame, errors: list[str]) -> None:
    if not isinstance(frame, Frame):
        errors.append("frame must be Frame")
        return
    for name in ("problem", "user", "success", "kill"):
        item = getattr(frame, name)
        if item is not None:
            _validate_knowledge_item(item, errors, f"frame.{name}")
    for name in ("constraints", "non_goals"):
        items = getattr(frame, name)
        if not isinstance(items, list):
            errors.append(f"frame.{name} must be a list")
            continue
        for index, item in enumerate(items):
            _validate_knowledge_item(item, errors, f"frame.{name}[{index}]")


def _validate_knowledge_item(
    item: KnowledgeItem, errors: list[str], path: str
) -> None:
    if not isinstance(item, KnowledgeItem):
        errors.append(f"{path} must be KnowledgeItem")
        return
    if not isinstance(item.statement, str) or not item.statement.strip():
        errors.append(f"{path}.statement must be a non-empty string")
    if not isinstance(item.classification, KnowledgeStatus):
        errors.append(f"{path}.classification must be a KnowledgeStatus")


def _validate_knowledge_list(
    items: list[KnowledgeItem],
    expected: KnowledgeStatus,
    errors: list[str],
    path: str,
) -> None:
    if not isinstance(items, list):
        errors.append(f"{path} must be a list")
        return
    for index, item in enumerate(items):
        _validate_knowledge_item(item, errors, f"{path}[{index}]")
        if isinstance(item, KnowledgeItem) and item.classification is not expected:
            errors.append(f"{path}[{index}] must be classified {expected.value}")


def _validate_evidence(items: list[EvidenceRecord], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("evidence must be a list")
        return
    ids: set[str] = set()
    for index, item in enumerate(items):
        path = f"evidence[{index}]"
        if not isinstance(item, EvidenceRecord):
            errors.append(f"{path} must be EvidenceRecord")
            continue
        if not isinstance(item.id, str) or not item.id.strip():
            errors.append(f"{path}.id must be a non-empty string")
        elif item.id in ids:
            errors.append(f"duplicate evidence id {item.id!r}")
        ids.add(item.id)
        if not isinstance(item.claim, str) or not item.claim.strip():
            errors.append(f"{path}.claim must be a non-empty string")
        if item.classification is KnowledgeStatus.KNOWN and (
            not isinstance(item.source, str) or not item.source.strip()
        ):
            errors.append(f"{path}.source is required for KNOWN evidence")
        if not isinstance(item.metadata, dict):
            errors.append(f"{path}.metadata must be an object")


def _validate_decisions(items: list[Decision], errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append("decisions must be a list")
        return
    ids: set[str] = set()
    for index, item in enumerate(items):
        path = f"decisions[{index}]"
        if not isinstance(item, Decision):
            errors.append(f"{path} must be Decision")
            continue
        if not isinstance(item.id, str) or not item.id.strip():
            errors.append(f"{path}.id must be a non-empty string")
        elif item.id in ids:
            errors.append(f"duplicate decision id {item.id!r}")
        ids.add(item.id)
        if not isinstance(item.topic, str) or not item.topic.strip():
            errors.append(f"{path}.topic must be a non-empty string")
        if not isinstance(item.status, DecisionStatus):
            errors.append(f"{path}.status must be a DecisionStatus")
        if item.rationale is not None and not isinstance(item.rationale, str):
            errors.append(f"{path}.rationale must be a string or null")


def _validate_result(result: Result, errors: list[str]) -> None:
    if not isinstance(result, Result):
        errors.append("result must be Result")
        return
    if not isinstance(result.shortlist, list) or not all(
        isinstance(item, str) and item.strip() for item in result.shortlist
    ):
        errors.append("result.shortlist must contain non-empty strings")
    for name in ("recommendation", "cheapest_test"):
        value = getattr(result, name)
        if value is not None and not isinstance(value, str):
            errors.append(f"result.{name} must be a string or null")
    if result.confidence is not None:
        if isinstance(result.confidence, bool) or not isinstance(
            result.confidence, (int, float)
        ):
            errors.append("result.confidence must be numeric or null")
        elif not 0 <= float(result.confidence) <= 1:
            errors.append("result.confidence must be between 0 and 1")
    if result.exit_status is not None and not isinstance(result.exit_status, ExitStatus):
        errors.append("result.exit_status must be an ExitStatus or null")


def _validate_mapping_list(
    items: list[dict[str, Any]], errors: list[str], path: str
) -> None:
    if not isinstance(items, list):
        errors.append(f"{path} must be a list")
        return
    ids: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"{path}[{index}] must be an object")
            continue
        item_id = item.get("id")
        if item_id is not None:
            if not isinstance(item_id, str) or not item_id.strip():
                errors.append(f"{path}[{index}].id must be a non-empty string")
            elif item_id in ids:
                errors.append(f"duplicate {path} id {item_id!r}")
            ids.add(item_id)


def _budget_from_dict(value: Any, allow_defaults: bool = False) -> Budget:
    data = _require_mapping(value, "budget")
    expected = {"max_steps", "used_steps", "max_parallelism"}
    unknown = set(data) - expected
    if unknown:
        raise ContractError(f"budget has unknown keys: {sorted(unknown)}")
    if not allow_defaults:
        missing = expected - set(data)
        if missing:
            raise ContractError(f"budget is missing keys: {sorted(missing)}")
    return Budget(
        max_steps=data.get("max_steps", 32),
        used_steps=data.get("used_steps", 0),
        max_parallelism=data.get("max_parallelism", 1),
    )


def _knowledge_from_dict(value: Any, path: str) -> KnowledgeItem:
    data = _require_mapping(value, path)
    _require_keys(data, {"statement", "classification"}, path)
    return KnowledgeItem(
        statement=data["statement"],
        classification=_enum_value(
            KnowledgeStatus, data["classification"], f"{path}.classification"
        ),
    )


def _optional_knowledge(value: Any, path: str) -> KnowledgeItem | None:
    return None if value is None else _knowledge_from_dict(value, path)


def _knowledge_list(value: Any, path: str) -> list[KnowledgeItem]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be a list")
    return [_knowledge_from_dict(item, f"{path}[{index}]") for index, item in enumerate(value)]


def _evidence_list(value: Any) -> list[EvidenceRecord]:
    if not isinstance(value, list):
        raise ContractError("evidence must be a list")
    result: list[EvidenceRecord] = []
    for index, item in enumerate(value):
        path = f"evidence[{index}]"
        data = _require_mapping(item, path)
        required = {"id", "claim", "classification", "source"}
        missing = required - set(data)
        unknown = set(data) - (required | {"metadata"})
        if missing:
            raise ContractError(f"{path} is missing keys: {sorted(missing)}")
        if unknown:
            raise ContractError(f"{path} has unknown keys: {sorted(unknown)}")
        result.append(
            EvidenceRecord(
                id=data["id"],
                claim=data["claim"],
                classification=_enum_value(
                    KnowledgeStatus, data["classification"], f"{path}.classification"
                ),
                source=data["source"],
                metadata=copy.deepcopy(data.get("metadata", {})),
            )
        )
    return result


def _decision_from_dict(value: Any, path: str) -> Decision:
    data = _require_mapping(value, path)
    _require_keys(data, {"id", "topic", "value", "status", "rationale"}, path)
    return Decision(
        id=data["id"],
        topic=data["topic"],
        value=data["value"],
        status=_enum_value(DecisionStatus, data["status"], f"{path}.status"),
        rationale=data["rationale"],
    )


def _decision_list(value: Any) -> list[Decision]:
    if not isinstance(value, list):
        raise ContractError("decisions must be a list")
    return [_decision_from_dict(item, f"decisions[{index}]") for index, item in enumerate(value)]


def _mapping_list(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ContractError(f"{path}[{index}] must be an object")
        result.append(copy.deepcopy(item))
    return result


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractError(f"{path} must be a list of strings")
    return list(value)


def _optional_string(value: Any, path: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ContractError(f"{path} must be a string or null")
    return value


def _enum_value(enum_type: type[Enum], value: Any, path: str) -> Any:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        for member in enum_type:
            if value.casefold() in {member.name.casefold(), str(member.value).casefold()}:
                return member
    allowed = [member.value for member in enum_type]
    raise ContractError(f"{path} must be one of {allowed}")


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _require_keys(data: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(data)
    unknown = set(data) - expected
    if missing:
        raise ContractError(f"{path} is missing keys: {sorted(missing)}")
    if unknown:
        raise ContractError(f"{path} has unknown keys: {sorted(unknown)}")


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _json_ready(value: Any) -> Any:
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

    route_parser = subparsers.add_parser("route", help="route a JSON request")
    route_parser.add_argument("--json", help="routing input JSON; defaults to stdin")

    state_parser = subparsers.add_parser("new-state", help="create a P0 state")
    state_parser.add_argument("--json", help="routing input JSON; defaults to stdin")
    state_parser.add_argument("--run-id", help="optional stable run id")

    validate_parser = subparsers.add_parser("validate", help="validate state JSON")
    validate_parser.add_argument("--json", help="state JSON; defaults to stdin")

    decision_parser = subparsers.add_parser(
        "upsert-decision", help="apply a decision with LOCKED protection"
    )
    decision_parser.add_argument("--state-json", required=True)
    decision_parser.add_argument("--decision-json", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "route":
            request = routing_input_from_dict(_load_json(args.json))
            _emit(route_mode(request))
        elif args.command == "new-state":
            request = routing_input_from_dict(_load_json(args.json))
            _emit(state_to_dict(new_state(request, args.run_id)))
        elif args.command == "validate":
            state = state_from_dict(_load_json(args.json))
            _emit({"valid": True, "run_id": state.run.id})
        elif args.command == "upsert-decision":
            state = state_from_dict(_load_json(args.state_json))
            decision = _decision_from_dict(
                _load_json(args.decision_json), "decision"
            )
            _emit(state_to_dict(upsert_decision(state, decision)))
        else:
            parser.error(f"unknown command: {args.command}")
        return 0
    except ContractError as exc:
        _emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
