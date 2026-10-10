#!/usr/bin/env python3
"""P2 Living Brief persistence, Decision Log, and Brief-first re-entry."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from p0_runtime import (
    ContractError,
    DecisionStatus,
    ExitStatus,
    RuntimeState,
    state_from_dict,
    state_to_dict,
    validate_state,
)


SCHEMA_VERSION = 1
START_MARKER = "<!-- BRAINSTORM_GOVERNOR_STATE_V1_START -->"
END_MARKER = "<!-- BRAINSTORM_GOVERNOR_STATE_V1_END -->"
TEMPLATE_PATH = Path(__file__).parents[1] / "assets" / "CONCEPT_BRIEF.template.md"


class BriefValidationError(ContractError):
    """Raised when a Living Brief is missing, corrupt, or internally inconsistent."""


@dataclass(frozen=True)
class DecisionLogEntry:
    sequence: int
    decision_id: str
    old_value: Any
    new_value: Any
    reason: str
    evidence: list[str]


@dataclass(frozen=True)
class EliminatedCandidate:
    candidate_id: str
    title: str
    reason: str


@dataclass
class ConceptBrief:
    runtime_state: RuntimeState
    problem: str | None = None
    target_user: str | None = None
    success_metric: str | None = None
    kill_criterion: str | None = None
    constraints: list[str] = field(default_factory=list)
    locked_concept: str | None = None
    scope_in: list[str] = field(default_factory=list)
    scope_out: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    decision_log: list[DecisionLogEntry] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    cheapest_test: str | None = None
    exit_status: ExitStatus | None = None
    open_questions: list[str] = field(default_factory=list)
    validated_assumptions: list[str] = field(default_factory=list)
    unvalidated_assumptions: list[str] = field(default_factory=list)
    previous_stop_reason: str | None = None
    eliminated_candidates: list[EliminatedCandidate] = field(default_factory=list)
    next_action: str | None = None


@dataclass(frozen=True)
class ReentryConflict:
    field: str
    persisted_value: Any
    incoming_value: Any
    reason: str


@dataclass
class ReentryResult:
    brief: ConceptBrief
    state: RuntimeState
    created: bool
    changed: bool
    conflicts: list[ReentryConflict]


REQUIRED_BRIEF_KEYS = {
    "schema_version",
    "runtime_state",
    "current_stage",
    "status",
    "next_action",
    "problem",
    "target_user",
    "success_metric",
    "kill_criterion",
    "constraints",
    "locked_concept",
    "scope_in",
    "scope_out",
    "assumptions",
    "unknowns",
    "evidence",
    "decision_log",
    "risks",
    "cheapest_test",
    "exit_status",
    "open_questions",
    "validated_assumptions",
    "unvalidated_assumptions",
    "previous_stop_reason",
    "eliminated_candidates",
}


def brief_from_state(
    state: RuntimeState,
    *,
    scope_in: Sequence[str] = (),
    scope_out: Sequence[str] = (),
    risks: Sequence[str] = (),
    previous_stop_reason: str | None = None,
    next_action: str | None = None,
) -> ConceptBrief:
    """Create the first Living Brief snapshot from a validated P0/P1 state."""
    validate_state(state)
    assumptions = [item.statement for item in state.assumptions]
    unknowns = [item.statement for item in state.unknowns]
    return ConceptBrief(
        runtime_state=copy.deepcopy(state),
        problem=_statement(state.frame.problem),
        target_user=_statement(state.frame.user),
        success_metric=_statement(state.frame.success),
        kill_criterion=_statement(state.frame.kill),
        constraints=[item.statement for item in state.frame.constraints],
        locked_concept=_locked_concept_from_state(state),
        scope_in=_clean_strings(scope_in, "scope_in"),
        scope_out=_clean_strings(scope_out, "scope_out"),
        assumptions=assumptions,
        unknowns=unknowns,
        evidence=copy.deepcopy(state_to_dict(state)["evidence"]),
        risks=_clean_strings(risks, "risks"),
        cheapest_test=state.result.cheapest_test,
        exit_status=state.result.exit_status,
        open_questions=copy.deepcopy(unknowns),
        unvalidated_assumptions=copy.deepcopy(assumptions),
        previous_stop_reason=_optional_nonempty(previous_stop_reason, "previous_stop_reason"),
        next_action=_optional_nonempty(next_action, "next_action"),
    )


def initialize_or_restore(
    path: str | Path,
    initial_state: RuntimeState,
    *,
    next_action: str | None = None,
) -> ReentryResult:
    """Load an existing Brief before doing any work, or create the first Brief."""
    validate_state(initial_state)
    brief_path = Path(path)
    if brief_path.exists():
        brief = load_brief(brief_path)
        conflicts = detect_reentry_conflicts(brief.runtime_state, initial_state)
        return ReentryResult(
            brief=brief,
            state=copy.deepcopy(brief.runtime_state),
            created=False,
            changed=False,
            conflicts=conflicts,
        )

    brief = brief_from_state(initial_state, next_action=next_action)
    changed = save_brief(brief_path, brief)
    return ReentryResult(
        brief=brief,
        state=copy.deepcopy(brief.runtime_state),
        created=True,
        changed=changed,
        conflicts=[],
    )


def save_round(
    path: str | Path,
    brief: ConceptBrief,
    state: RuntimeState,
    *,
    next_action: str,
    previous_stop_reason: str | None = None,
) -> bool:
    """Persist stage, status, next action, and the latest validated runtime state."""
    validate_state(state)
    brief.runtime_state = copy.deepcopy(state)
    brief.next_action = _required_nonempty(next_action, "next_action")
    brief.previous_stop_reason = _optional_nonempty(
        previous_stop_reason, "previous_stop_reason"
    )
    _refresh_derived_fields(brief)
    return save_brief(path, brief)


def update_locked_decision(
    brief: ConceptBrief,
    decision_id: str,
    new_value: Any,
    *,
    reason: str,
    evidence: Sequence[str],
) -> bool:
    """Explicitly change a LOCKED decision and append the mandatory audit entry."""
    decision_id = _required_nonempty(decision_id, "decision_id")
    reason = _required_nonempty(reason, "reason")
    evidence_items = _clean_strings(evidence, "evidence")
    if not evidence_items:
        raise ContractError("evidence must contain at least one non-empty reference")

    state = copy.deepcopy(brief.runtime_state)
    for decision in state.decisions:
        if decision.id != decision_id:
            continue
        if decision.status is not DecisionStatus.LOCKED:
            raise ContractError(f"decision {decision_id!r} is not LOCKED")
        if _canonical(decision.value) == _canonical(new_value):
            return False

        entry = DecisionLogEntry(
            sequence=len(brief.decision_log) + 1,
            decision_id=decision_id,
            old_value=copy.deepcopy(decision.value),
            new_value=copy.deepcopy(new_value),
            reason=reason,
            evidence=evidence_items,
        )
        decision.value = copy.deepcopy(new_value)
        decision.rationale = reason
        validate_state(state)
        brief.runtime_state = state
        brief.decision_log.append(entry)
        if decision.topic.casefold() in {"concept", "locked concept", "locked_concept"}:
            brief.locked_concept = str(new_value)
        return True

    raise ContractError(f"LOCKED decision {decision_id!r} was not found")


def record_elimination(
    brief: ConceptBrief,
    candidate_id: str,
    title: str,
    reason: str,
) -> bool:
    """Keep a concise, idempotent record for a removed candidate."""
    entry = EliminatedCandidate(
        candidate_id=_required_nonempty(candidate_id, "candidate_id"),
        title=_required_nonempty(title, "title"),
        reason=_required_nonempty(reason, "reason"),
    )
    for existing in brief.eliminated_candidates:
        if existing.candidate_id == entry.candidate_id:
            if existing == entry:
                return False
            raise ContractError(
                f"elimination for candidate {entry.candidate_id!r} already exists"
            )
    brief.eliminated_candidates.append(entry)
    return True


def detect_reentry_conflicts(
    persisted: RuntimeState, incoming: RuntimeState
) -> list[ReentryConflict]:
    """Report overlapping state conflicts; persisted state always remains authoritative."""
    validate_state(persisted)
    validate_state(incoming)
    conflicts: list[ReentryConflict] = []
    incoming_decisions = {item.id: item for item in incoming.decisions}
    for decision in persisted.decisions:
        other = incoming_decisions.get(decision.id)
        if (
            decision.status is DecisionStatus.LOCKED
            and other is not None
            and _canonical(decision.value) != _canonical(other.value)
        ):
            conflicts.append(
                ReentryConflict(
                    field=f"decisions.{decision.id}.value",
                    persisted_value=copy.deepcopy(decision.value),
                    incoming_value=copy.deepcopy(other.value),
                    reason="incoming value conflicts with persisted LOCKED decision",
                )
            )

    if persisted.run.id == incoming.run.id:
        for name in ("stage", "status"):
            left = getattr(persisted.run, name)
            right = getattr(incoming.run, name)
            if left != right:
                conflicts.append(
                    ReentryConflict(
                        field=f"run.{name}",
                        persisted_value=left.value,
                        incoming_value=right.value,
                        reason="incoming run snapshot differs from persisted resume point",
                    )
                )
    return conflicts


def _replace_with_retry(source, target):
    """Bound temporary Windows sharing failures; preserve atomic replacement."""
    for attempt in range(6):
        try:
            os.replace(source, target)
            return
        except PermissionError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32, 33) or attempt == 5:
                raise
            time.sleep(0.05 * (2 ** attempt))


def save_brief(path: str | Path, brief: ConceptBrief) -> bool:
    """Atomically write a canonical Brief; return false when bytes are unchanged."""
    target = Path(path)
    document = render_brief(brief)
    if target.exists() and target.read_text(encoding="utf-8") == document:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=target.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(document)
            handle.flush()
            os.fsync(handle.fileno())
        _replace_with_retry(temporary_name, target)
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise
    return True


def load_brief(path: str | Path) -> ConceptBrief:
    """Restore and strictly validate the canonical JSON embedded in a Brief."""
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BriefValidationError(f"cannot read Brief: {exc}") from exc
    payload = _extract_payload(text)
    return brief_from_dict(payload)


def render_brief(brief: ConceptBrief) -> str:
    validate_brief(brief)
    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    payload = json.dumps(
        brief_to_dict(brief), ensure_ascii=False, indent=2, sort_keys=True
    )
    canonical_block = f"{START_MARKER}\n```json\n{payload}\n```\n{END_MARKER}"
    start = template.find(START_MARKER)
    end = template.find(END_MARKER)
    if start < 0 or end <= start:
        raise BriefValidationError("Concept Brief template has invalid state markers")
    rendered = template[:start] + canonical_block + template[end + len(END_MARKER) :]
    replacements = {
        "- Problem: —": f"- Problem: {_display(brief.problem)}",
        "- Target user: —": f"- Target user: {_display(brief.target_user)}",
        "- Success metric: —": f"- Success metric: {_display(brief.success_metric)}",
        "- Kill criterion: —": f"- Kill criterion: {_display(brief.kill_criterion)}",
        "- Constraints: —": f"- Constraints: {_display_list(brief.constraints)}",
        "- Scope in: —": f"- Scope in: {_display_list(brief.scope_in)}",
        "- Scope out: —": f"- Scope out: {_display_list(brief.scope_out)}",
        "## Locked concept\n\n—": f"## Locked concept\n\n{_display(brief.locked_concept)}",
        "- Assumptions: —": f"- Assumptions: {_display_list(brief.assumptions)}",
        "- Unknowns / open questions: —": (
            f"- Unknowns / open questions: {_display_list(brief.open_questions)}"
        ),
        "- Evidence: —": f"- Evidence: {len(brief.evidence)} record(s)",
        "- Decision log: —": f"- Decision log: {len(brief.decision_log)} change(s)",
        "- Risks: —": f"- Risks: {_display_list(brief.risks)}",
        "- Cheapest test: —": f"- Cheapest test: {_display(brief.cheapest_test)}",
        "- Exit status: —": f"- Exit status: {_display(_enum_or_none(brief.exit_status))}",
        "- Stage: —": f"- Stage: {brief.runtime_state.run.stage.value}",
        "- Status: —": f"- Status: {brief.runtime_state.run.status.value}",
        "- Previous stop reason: —": (
            f"- Previous stop reason: {_display(brief.previous_stop_reason)}"
        ),
        "- Next action: —": f"- Next action: {_display(brief.next_action)}",
    }
    for old, new in replacements.items():
        rendered = rendered.replace(old, new, 1)
    return rendered.rstrip() + "\n"


def brief_to_dict(brief: ConceptBrief) -> dict[str, Any]:
    validate_brief(brief)
    return {
        "schema_version": SCHEMA_VERSION,
        "runtime_state": state_to_dict(brief.runtime_state),
        "current_stage": brief.runtime_state.run.stage.value,
        "status": brief.runtime_state.run.status.value,
        "next_action": brief.next_action,
        "problem": brief.problem,
        "target_user": brief.target_user,
        "success_metric": brief.success_metric,
        "kill_criterion": brief.kill_criterion,
        "constraints": copy.deepcopy(brief.constraints),
        "locked_concept": brief.locked_concept,
        "scope_in": copy.deepcopy(brief.scope_in),
        "scope_out": copy.deepcopy(brief.scope_out),
        "assumptions": copy.deepcopy(brief.assumptions),
        "unknowns": copy.deepcopy(brief.unknowns),
        "evidence": copy.deepcopy(brief.evidence),
        "decision_log": [
            {
                "sequence": item.sequence,
                "decision_id": item.decision_id,
                "old_value": copy.deepcopy(item.old_value),
                "new_value": copy.deepcopy(item.new_value),
                "reason": item.reason,
                "evidence": copy.deepcopy(item.evidence),
            }
            for item in brief.decision_log
        ],
        "risks": copy.deepcopy(brief.risks),
        "cheapest_test": brief.cheapest_test,
        "exit_status": _enum_or_none(brief.exit_status),
        "open_questions": copy.deepcopy(brief.open_questions),
        "validated_assumptions": copy.deepcopy(brief.validated_assumptions),
        "unvalidated_assumptions": copy.deepcopy(brief.unvalidated_assumptions),
        "previous_stop_reason": brief.previous_stop_reason,
        "eliminated_candidates": [
            {
                "candidate_id": item.candidate_id,
                "title": item.title,
                "reason": item.reason,
            }
            for item in brief.eliminated_candidates
        ],
    }


def brief_from_dict(value: Mapping[str, Any]) -> ConceptBrief:
    data = _require_mapping(value, "brief")
    missing = REQUIRED_BRIEF_KEYS - set(data)
    unknown = set(data) - REQUIRED_BRIEF_KEYS
    if missing:
        raise BriefValidationError(f"brief is missing keys: {sorted(missing)}")
    if unknown:
        raise BriefValidationError(f"brief has unknown keys: {sorted(unknown)}")
    if data["schema_version"] != SCHEMA_VERSION:
        raise BriefValidationError(
            f"unsupported schema_version {data['schema_version']!r}"
        )

    try:
        state = state_from_dict(_require_mapping(data["runtime_state"], "runtime_state"))
    except ContractError as exc:
        raise BriefValidationError(f"invalid runtime_state: {exc}") from exc
    if data["current_stage"] != state.run.stage.value:
        raise BriefValidationError("current_stage conflicts with runtime_state.run.stage")
    if data["status"] != state.run.status.value:
        raise BriefValidationError("status conflicts with runtime_state.run.status")
    state_exit = _enum_or_none(state.result.exit_status)
    if data["exit_status"] != state_exit:
        raise BriefValidationError("exit_status conflicts with runtime_state.result")

    brief = ConceptBrief(
        runtime_state=state,
        problem=_optional_text(data["problem"], "problem"),
        target_user=_optional_text(data["target_user"], "target_user"),
        success_metric=_optional_text(data["success_metric"], "success_metric"),
        kill_criterion=_optional_text(data["kill_criterion"], "kill_criterion"),
        constraints=_string_list(data["constraints"], "constraints"),
        locked_concept=_optional_text(data["locked_concept"], "locked_concept"),
        scope_in=_string_list(data["scope_in"], "scope_in"),
        scope_out=_string_list(data["scope_out"], "scope_out"),
        assumptions=_string_list(data["assumptions"], "assumptions"),
        unknowns=_string_list(data["unknowns"], "unknowns"),
        evidence=_normalized_evidence_list(data["evidence"]),
        decision_log=_decision_log_from_list(data["decision_log"]),
        risks=_string_list(data["risks"], "risks"),
        cheapest_test=_optional_text(data["cheapest_test"], "cheapest_test"),
        exit_status=_exit_status_from_value(data["exit_status"]),
        open_questions=_string_list(data["open_questions"], "open_questions"),
        validated_assumptions=_string_list(
            data["validated_assumptions"], "validated_assumptions"
        ),
        unvalidated_assumptions=_string_list(
            data["unvalidated_assumptions"], "unvalidated_assumptions"
        ),
        previous_stop_reason=_optional_text(
            data["previous_stop_reason"], "previous_stop_reason"
        ),
        eliminated_candidates=_eliminations_from_list(data["eliminated_candidates"]),
        next_action=_optional_text(data["next_action"], "next_action"),
    )
    validate_brief(brief)
    return brief


def validate_brief(brief: ConceptBrief) -> None:
    if not isinstance(brief, ConceptBrief):
        raise BriefValidationError("brief must be ConceptBrief")
    validate_state(brief.runtime_state)
    for name in (
        "problem",
        "target_user",
        "success_metric",
        "kill_criterion",
        "locked_concept",
        "cheapest_test",
        "previous_stop_reason",
        "next_action",
    ):
        _optional_text(getattr(brief, name), name)
    for name in (
        "constraints",
        "scope_in",
        "scope_out",
        "assumptions",
        "unknowns",
        "risks",
        "open_questions",
        "validated_assumptions",
        "unvalidated_assumptions",
    ):
        _string_list(getattr(brief, name), name)
    _mapping_list(brief.evidence, "evidence")
    _validate_log(brief.decision_log)
    _validate_eliminations(brief.eliminated_candidates)
    if brief.exit_status != brief.runtime_state.result.exit_status:
        raise BriefValidationError("exit_status conflicts with runtime_state.result")

    expected = {
        "problem": _statement(brief.runtime_state.frame.problem),
        "target_user": _statement(brief.runtime_state.frame.user),
        "success_metric": _statement(brief.runtime_state.frame.success),
        "kill_criterion": _statement(brief.runtime_state.frame.kill),
        "constraints": [item.statement for item in brief.runtime_state.frame.constraints],
        "locked_concept": _locked_concept_from_state(brief.runtime_state),
        "assumptions": [item.statement for item in brief.runtime_state.assumptions],
        "unknowns": [item.statement for item in brief.runtime_state.unknowns],
        "evidence": state_to_dict(brief.runtime_state)["evidence"],
        "cheapest_test": brief.runtime_state.result.cheapest_test,
    }
    for name, expected_value in expected.items():
        if getattr(brief, name) != expected_value:
            raise BriefValidationError(f"{name} conflicts with runtime_state")

    validated = set(brief.validated_assumptions)
    unvalidated = set(brief.unvalidated_assumptions)
    assumptions = set(brief.assumptions)
    if validated & unvalidated:
        raise BriefValidationError(
            "validated_assumptions and unvalidated_assumptions must not overlap"
        )
    if validated | unvalidated != assumptions:
        raise BriefValidationError(
            "validated/unvalidated assumptions must partition assumptions"
        )

    decisions = {item.id: item for item in brief.runtime_state.decisions}
    latest_by_decision: dict[str, DecisionLogEntry] = {}
    for entry in brief.decision_log:
        previous = latest_by_decision.get(entry.decision_id)
        if previous is not None and _canonical(previous.new_value) != _canonical(
            entry.old_value
        ):
            raise BriefValidationError(
                f"decision_log chain is broken for {entry.decision_id!r}"
            )
        latest_by_decision[entry.decision_id] = entry
    for decision_id, entry in latest_by_decision.items():
        decision = decisions.get(decision_id)
        if decision is None or decision.status is not DecisionStatus.LOCKED:
            raise BriefValidationError(
                f"decision_log references missing or unlocked decision {decision_id!r}"
            )
        if _canonical(entry.new_value) != _canonical(decision.value):
            raise BriefValidationError(
                f"decision_log latest value conflicts with decision {decision_id!r}"
            )


def _refresh_derived_fields(brief: ConceptBrief) -> None:
    state = brief.runtime_state
    brief.problem = _statement(state.frame.problem)
    brief.target_user = _statement(state.frame.user)
    brief.success_metric = _statement(state.frame.success)
    brief.kill_criterion = _statement(state.frame.kill)
    brief.constraints = [item.statement for item in state.frame.constraints]
    brief.assumptions = [item.statement for item in state.assumptions]
    validated = set(brief.validated_assumptions)
    brief.validated_assumptions = [
        item for item in brief.assumptions if item in validated
    ]
    brief.unvalidated_assumptions = [
        item for item in brief.assumptions if item not in validated
    ]
    brief.unknowns = [item.statement for item in state.unknowns]
    brief.open_questions = copy.deepcopy(brief.unknowns)
    brief.evidence = copy.deepcopy(state_to_dict(state)["evidence"])
    brief.cheapest_test = state.result.cheapest_test
    brief.exit_status = state.result.exit_status
    concept = _locked_concept_from_state(state)
    if concept is not None:
        brief.locked_concept = concept


def _extract_payload(text: str) -> Mapping[str, Any]:
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end <= start:
        raise BriefValidationError("Brief is missing canonical state markers")
    body = text[start + len(START_MARKER) : end].strip()
    if not body.startswith("```json") or not body.endswith("```"):
        raise BriefValidationError("Brief canonical state must be a fenced JSON block")
    raw_json = body[len("```json") : -len("```")].strip()
    try:
        value = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise BriefValidationError(f"Brief contains invalid JSON: {exc}") from exc
    return _require_mapping(value, "brief")


def _decision_log_from_list(value: Any) -> list[DecisionLogEntry]:
    if not isinstance(value, list):
        raise BriefValidationError("decision_log must be a list")
    result: list[DecisionLogEntry] = []
    for index, item in enumerate(value):
        data = _require_exact_keys(
            item,
            {"sequence", "decision_id", "old_value", "new_value", "reason", "evidence"},
            f"decision_log[{index}]",
        )
        result.append(
            DecisionLogEntry(
                sequence=data["sequence"],
                decision_id=data["decision_id"],
                old_value=copy.deepcopy(data["old_value"]),
                new_value=copy.deepcopy(data["new_value"]),
                reason=data["reason"],
                evidence=_string_list(data["evidence"], f"decision_log[{index}].evidence"),
            )
        )
    _validate_log(result)
    return result


def _eliminations_from_list(value: Any) -> list[EliminatedCandidate]:
    if not isinstance(value, list):
        raise BriefValidationError("eliminated_candidates must be a list")
    result: list[EliminatedCandidate] = []
    for index, item in enumerate(value):
        data = _require_exact_keys(
            item, {"candidate_id", "title", "reason"}, f"eliminated_candidates[{index}]"
        )
        result.append(
            EliminatedCandidate(data["candidate_id"], data["title"], data["reason"])
        )
    _validate_eliminations(result)
    return result


def _validate_log(items: list[DecisionLogEntry]) -> None:
    if not isinstance(items, list):
        raise BriefValidationError("decision_log must be a list")
    for index, item in enumerate(items, start=1):
        if not isinstance(item, DecisionLogEntry):
            raise BriefValidationError(f"decision_log[{index - 1}] is invalid")
        if item.sequence != index:
            raise BriefValidationError("decision_log sequence must be contiguous from 1")
        _required_nonempty(item.decision_id, "decision_log.decision_id")
        _required_nonempty(item.reason, "decision_log.reason")
        if not _clean_strings(item.evidence, "decision_log.evidence"):
            raise BriefValidationError("decision_log evidence cannot be empty")


def _validate_eliminations(items: list[EliminatedCandidate]) -> None:
    if not isinstance(items, list):
        raise BriefValidationError("eliminated_candidates must be a list")
    ids: set[str] = set()
    for item in items:
        if not isinstance(item, EliminatedCandidate):
            raise BriefValidationError("eliminated_candidates contains invalid entry")
        _required_nonempty(item.candidate_id, "candidate_id")
        _required_nonempty(item.title, "title")
        _required_nonempty(item.reason, "reason")
        if item.candidate_id in ids:
            raise BriefValidationError(f"duplicate eliminated candidate {item.candidate_id!r}")
        ids.add(item.candidate_id)


def _require_mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BriefValidationError(f"{path} must be an object")
    return value


def _require_exact_keys(value: Any, keys: set[str], path: str) -> Mapping[str, Any]:
    data = _require_mapping(value, path)
    missing = keys - set(data)
    unknown = set(data) - keys
    if missing:
        raise BriefValidationError(f"{path} is missing keys: {sorted(missing)}")
    if unknown:
        raise BriefValidationError(f"{path} has unknown keys: {sorted(unknown)}")
    return data


def _mapping_list(value: Any, path: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise BriefValidationError(f"{path} must be a list")
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        result.append(dict(_require_mapping(item, f"{path}[{index}]")))
    return result


def _normalized_evidence_list(value: Any) -> list[dict[str, Any]]:
    result = _mapping_list(value, "evidence")
    for item in result:
        item.setdefault("metadata", {})
    return result


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        raise BriefValidationError(f"{path} must contain non-empty strings")
    return list(value)


def _clean_strings(values: Sequence[str], path: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ContractError(f"{path} must be a sequence of strings")
    return _string_list(list(values), path) if values else []


def _required_nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value


def _optional_nonempty(value: str | None, path: str) -> str | None:
    return None if value is None else _required_nonempty(value, path)


def _optional_text(value: Any, path: str) -> str | None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise BriefValidationError(f"{path} must be a non-empty string or null")
    return value


def _statement(item: Any) -> str | None:
    return None if item is None else item.statement


def _locked_concept_from_state(state: RuntimeState) -> str | None:
    for decision in state.decisions:
        if (
            decision.status is DecisionStatus.LOCKED
            and decision.topic.casefold() in {"concept", "locked concept", "locked_concept"}
        ):
            return str(decision.value)
    return state.result.recommendation


def _exit_status_from_value(value: Any) -> ExitStatus | None:
    if value is None:
        return None
    try:
        return ExitStatus(value)
    except (TypeError, ValueError) as exc:
        raise BriefValidationError(
            f"exit_status must be one of {[item.value for item in ExitStatus]} or null"
        ) from exc


def _enum_or_none(value: ExitStatus | None) -> str | None:
    return None if value is None else value.value


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ContractError(f"decision value must be JSON-compatible: {exc}") from exc


def _display(value: str | None) -> str:
    return "—" if value is None else value.replace("\n", " ")


def _display_list(values: Sequence[str]) -> str:
    return "—" if not values else "; ".join(item.replace("\n", " ") for item in values)


def _conflict_to_dict(conflict: ReentryConflict) -> dict[str, Any]:
    return {
        "field": conflict.field,
        "persisted_value": conflict.persisted_value,
        "incoming_value": conflict.incoming_value,
        "reason": conflict.reason,
    }


def _load_json(value: str | None) -> Any:
    try:
        return json.loads(value) if value is not None else json.load(sys.stdin)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def _emit(value: Any) -> None:
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create or restore a Living Brief")
    init_parser.add_argument("--brief", required=True, help="Concept Brief Markdown path")
    init_parser.add_argument("--json", help="P0 state JSON; defaults to stdin")
    init_parser.add_argument("--next-action")

    restore_parser = subparsers.add_parser("restore", help="restore a Living Brief")
    restore_parser.add_argument("--brief", required=True, help="Concept Brief Markdown path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "init":
            result = initialize_or_restore(
                args.brief,
                state_from_dict(_require_mapping(_load_json(args.json), "state")),
                next_action=args.next_action,
            )
            _emit(
                {
                    "created": result.created,
                    "changed": result.changed,
                    "conflicts": [_conflict_to_dict(item) for item in result.conflicts],
                    "state": state_to_dict(result.state),
                }
            )
        elif args.command == "restore":
            brief = load_brief(args.brief)
            _emit({"brief": brief_to_dict(brief)})
        return 0
    except ContractError as exc:
        _emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
