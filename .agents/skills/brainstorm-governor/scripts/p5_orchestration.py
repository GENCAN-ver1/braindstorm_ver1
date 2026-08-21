#!/usr/bin/env python3
"""P5 gated isolated workers and optional Council adapter boundary."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping, Protocol, Sequence

from p0_runtime import (
    ContractError,
    Mode,
    RuntimeState,
    state_from_dict,
    state_to_dict,
    validate_state,
)
from p1_core import (
    Candidate,
    ExplorationLens,
    candidate_from_dict,
    validate_candidate,
)
from p4_research import (
    CitationSupportChecker,
    NumericClaim,
    ProviderResearchResult,
    ResearchEvidenceRecord,
    ResearchQuestion,
    validate_provider_result,
    validate_research_question,
)


class WorkerKind(str, Enum):
    EXPLORATION = "EXPLORATION"
    RESEARCH = "RESEARCH"


class SecondRoundStatus(str, Enum):
    NOT_NEEDED = "NOT_NEEDED"
    ALLOWED = "ALLOWED"
    DENIED_ALREADY_USED = "DENIED_ALREADY_USED"
    DENIED_BUDGET = "DENIED_BUDGET"


CANDIDATE_FIELDS = (
    "id",
    "title",
    "one_liner",
    "core_mechanism",
    "target_user",
    "value_created",
    "why_distinct",
    "key_assumptions",
    "main_dependency",
    "exploration_lens",
    "complexity",
)
CANDIDATE_OUTPUT_SCHEMA = {name: "required" for name in CANDIDATE_FIELDS}


@dataclass(frozen=True)
class ParallelGateSignals:
    independent_dimensions: int
    outputs_independently_generatable: bool
    synthesis_cost: float
    duplicated_context_cost: float
    explicit_parallel_request: bool = False


@dataclass(frozen=True)
class ParallelGateDecision:
    enabled: bool
    effective_parallelism: int
    reasons: list[str]


@dataclass(frozen=True)
class ExplorationAssignment:
    worker_id: str
    assigned_lens: ExplorationLens


@dataclass(frozen=True)
class ExplorationWorkerInput:
    shared_frame: dict[str, Any]
    assigned_lens: ExplorationLens
    hard_constraints: list[str]
    candidate_output_schema: dict[str, str]


@dataclass(frozen=True)
class ResearchWorkerInput:
    question: ResearchQuestion


@dataclass(frozen=True)
class WorkerTask:
    id: str
    kind: WorkerKind
    payload: ExplorationWorkerInput | ResearchWorkerInput


@dataclass(frozen=True)
class ExplorationWorkerOutput:
    candidates: list[dict[str, Any]]


@dataclass(frozen=True)
class ResearchWorkerOutput:
    result: ProviderResearchResult


@dataclass(frozen=True)
class WorkerExecutionResult:
    worker_id: str
    kind: WorkerKind
    success: bool
    output: ExplorationWorkerOutput | ResearchWorkerOutput | None = None
    error: str | None = None


class IsolatedWorkerExecutor(Protocol):
    """Runtime adapter; every submit receives one isolated task payload."""

    def open(self, max_parallelism: int) -> None:
        ...

    def submit(self, task: WorkerTask) -> str:
        ...

    def collect(self, handle: str) -> WorkerExecutionResult:
        ...


@dataclass(frozen=True)
class EliminatedWorkerCandidate:
    worker_id: str
    candidate_id: str
    reason: str


@dataclass(frozen=True)
class CouncilConfig:
    requested: bool = False
    adapter_name: str | None = None


@dataclass(frozen=True)
class CouncilDecision:
    enabled: bool
    label: str
    adapter_name: str | None
    reason: str


@dataclass(frozen=True)
class SecondRoundDecision:
    status: SecondRoundStatus
    reason: str


@dataclass
class OrchestrationOutcome:
    routing_decision: ParallelGateDecision
    state: RuntimeState
    submitted_worker_ids: list[str]
    successful_worker_ids: list[str]
    failed_workers: dict[str, str]
    normalized_candidates: list[Candidate]
    eliminated_duplicates: list[EliminatedWorkerCandidate]
    coverage_gaps: list[str]
    evidence: list[ResearchEvidenceRecord]
    numeric_claims: list[NumericClaim]
    source_conflicts: list[list[str]]
    second_round: SecondRoundDecision
    council: CouncilDecision
    synthesis_ready: bool
    state_unchanged: bool


def parallel_gate(
    state: RuntimeState, signals: ParallelGateSignals
) -> ParallelGateDecision:
    """Enable workers only when every P5 gate condition is satisfied."""
    validate_state(state)
    _validate_gate_signals(signals)
    reasons: list[str] = []
    if state.parallelism <= 1:
        reasons.append("parallelism defaults to 1 or no parallel capacity was requested")
    if signals.independent_dimensions < 2:
        reasons.append("independent_dimensions must be at least 2")
    if not signals.outputs_independently_generatable:
        reasons.append("outputs are not independently generatable")
    if not signals.synthesis_cost < signals.duplicated_context_cost:
        reasons.append("synthesis_cost must be lower than duplicated_context_cost")
    if (
        state.run.mode in {Mode.SPARK, Mode.SHAPE}
        and not signals.explicit_parallel_request
    ):
        reasons.append(
            f"{state.run.mode.value} remains single-agent without explicit parallel request"
        )

    enabled = not reasons
    effective = (
        min(
            state.parallelism,
            state.run.budget.max_parallelism,
            signals.independent_dimensions,
        )
        if enabled
        else 1
    )
    if enabled and effective < 2:
        return ParallelGateDecision(
            False, 1, ["effective parallelism is below 2"]
        )
    return ParallelGateDecision(enabled, effective, reasons or ["all parallel gates passed"])


def build_exploration_tasks(
    state: RuntimeState,
    assignments: Sequence[ExplorationAssignment],
    *,
    hard_constraints: Sequence[str],
) -> list[WorkerTask]:
    """Build minimal exploration payloads with no peer outputs or full chat context."""
    validate_state(state)
    constraint_items = _unique_strings(hard_constraints, "hard_constraints")
    assignment_items = list(assignments)
    ids: set[str] = set()
    tasks: list[WorkerTask] = []
    shared_frame = copy.deepcopy(state_to_dict(state)["frame"])
    for index, assignment in enumerate(assignment_items):
        if not isinstance(assignment, ExplorationAssignment):
            raise ContractError(
                f"assignments[{index}] must be ExplorationAssignment"
            )
        _required_string(assignment.worker_id, f"assignments[{index}].worker_id")
        if assignment.worker_id in ids:
            raise ContractError(f"duplicate worker id {assignment.worker_id!r}")
        ids.add(assignment.worker_id)
        if not isinstance(assignment.assigned_lens, ExplorationLens):
            raise ContractError(f"assignments[{index}].assigned_lens is invalid")
        tasks.append(
            WorkerTask(
                id=assignment.worker_id,
                kind=WorkerKind.EXPLORATION,
                payload=ExplorationWorkerInput(
                    shared_frame=copy.deepcopy(shared_frame),
                    assigned_lens=assignment.assigned_lens,
                    hard_constraints=copy.deepcopy(constraint_items),
                    candidate_output_schema=copy.deepcopy(CANDIDATE_OUTPUT_SCHEMA),
                ),
            )
        )
    return tasks


def build_research_tasks(
    questions: Sequence[ResearchQuestion],
) -> list[WorkerTask]:
    """Build one isolated research task per explicit research question."""
    question_items = list(questions)
    ids: set[str] = set()
    tasks: list[WorkerTask] = []
    for index, question in enumerate(question_items):
        if not isinstance(question, ResearchQuestion):
            raise ContractError(f"questions[{index}] must be ResearchQuestion")
        validate_research_question(question)
        if question.id in ids:
            raise ContractError(f"duplicate research question {question.id!r}")
        ids.add(question.id)
        tasks.append(
            WorkerTask(
                id=f"research:{question.id}",
                kind=WorkerKind.RESEARCH,
                payload=ResearchWorkerInput(question=copy.deepcopy(question)),
            )
        )
    return tasks


def council_gate(
    config: CouncilConfig, *, independent_agent_count: int
) -> CouncilDecision:
    """Expose Council as an adapter decision, never as a governor-core behavior."""
    if not isinstance(config, CouncilConfig):
        raise ContractError("council config must be CouncilConfig")
    if type(config.requested) is not bool:
        raise ContractError("council.requested must be boolean")
    if type(independent_agent_count) is not int or independent_agent_count < 0:
        raise ContractError("independent_agent_count must be an integer >= 0")
    if not config.requested:
        return CouncilDecision(
            False,
            "PERSPECTIVE_LENSES",
            None,
            "Council disabled; perspective lenses are not independent-agent Council",
        )
    if independent_agent_count < 2:
        return CouncilDecision(
            False,
            "PERSPECTIVE_LENSES",
            None,
            "Council requires at least two successful independent agents",
        )
    if not isinstance(config.adapter_name, str) or not config.adapter_name.strip():
        return CouncilDecision(
            False,
            "INDEPENDENT_AGENTS",
            None,
            "Council requested but no external adapter was configured",
        )
    return CouncilDecision(
        True,
        "COUNCIL",
        config.adapter_name,
        "external Council adapter may synthesize independent agent outputs",
    )


def orchestrate_workers(
    state: RuntimeState,
    signals: ParallelGateSignals,
    tasks: Sequence[WorkerTask],
    executor: IsolatedWorkerExecutor,
    *,
    citation_checker: CitationSupportChecker | None = None,
    council_config: CouncilConfig = CouncilConfig(),
    supplemental_rounds_used: int = 0,
) -> OrchestrationOutcome:
    """Submit isolated tasks, then validate and normalize results in the main layer."""
    validate_state(state)
    before = state_to_dict(state)
    decision = parallel_gate(state, signals)
    task_items = _validate_tasks(tasks)
    expected_frame = state_to_dict(state)["frame"]
    for task in task_items:
        if (
            task.kind is WorkerKind.EXPLORATION
            and isinstance(task.payload, ExplorationWorkerInput)
            and task.payload.shared_frame != expected_frame
        ):
            raise ContractError(
                f"worker {task.id!r} shared_frame differs from main state"
            )
    if not decision.enabled:
        return _empty_outcome(state, decision, council_config, before)
    if len(task_items) < 2:
        raise ContractError("enabled parallel orchestration requires at least two tasks")
    if any(item.kind is WorkerKind.RESEARCH for item in task_items) and citation_checker is None:
        raise ContractError("research workers require a citation_support_checker")

    submitted: list[str] = []
    handles: dict[str, str] = {}
    failures: dict[str, str] = {}
    try:
        executor.open(decision.effective_parallelism)
    except Exception as exc:
        failures["__executor__"] = f"executor open failed: {exc}"
        return _outcome_after_processing(
            state,
            before,
            decision,
            task_items,
            submitted,
            [],
            failures,
            citation_checker,
            council_config,
            supplemental_rounds_used,
        )

    for task in task_items:
        try:
            handle = executor.submit(copy.deepcopy(task))
            _required_string(handle, f"executor handle for {task.id}")
            handles[task.id] = handle
            submitted.append(task.id)
        except Exception as exc:
            failures[task.id] = f"submit failed: {exc}"

    collected: list[tuple[WorkerTask, WorkerExecutionResult]] = []
    task_by_id = {item.id: item for item in task_items}
    for task_id in submitted:
        try:
            result = executor.collect(handles[task_id])
            _validate_execution_result(task_by_id[task_id], result)
            collected.append((task_by_id[task_id], result))
        except Exception as exc:
            failures[task_id] = f"collect failed: {exc}"

    return _outcome_after_processing(
        state,
        before,
        decision,
        task_items,
        submitted,
        collected,
        failures,
        citation_checker,
        council_config,
        supplemental_rounds_used,
    )


def _outcome_after_processing(
    state: RuntimeState,
    before: dict[str, Any],
    decision: ParallelGateDecision,
    tasks: list[WorkerTask],
    submitted: list[str],
    collected: list[tuple[WorkerTask, WorkerExecutionResult]],
    failures: dict[str, str],
    citation_checker: CitationSupportChecker | None,
    council_config: CouncilConfig,
    supplemental_rounds_used: int,
) -> OrchestrationOutcome:
    successful: list[str] = []
    candidate_sources: list[tuple[str, Candidate]] = []
    evidence: list[ResearchEvidenceRecord] = []
    numeric_claims: list[NumericClaim] = []

    for task, result in collected:
        if not result.success:
            failures[task.id] = result.error or "worker failed without an error"
            continue
        try:
            if task.kind is WorkerKind.EXPLORATION:
                output = result.output
                if not isinstance(output, ExplorationWorkerOutput):
                    raise ContractError("exploration worker returned wrong output type")
                payload = task.payload
                assert isinstance(payload, ExplorationWorkerInput)
                worker_candidates = _parse_worker_candidates(
                    task.id, payload.assigned_lens, output.candidates
                )
                candidate_sources.extend((task.id, item) for item in worker_candidates)
            else:
                output = result.output
                if not isinstance(output, ResearchWorkerOutput):
                    raise ContractError("research worker returned wrong output type")
                payload = task.payload
                assert isinstance(payload, ResearchWorkerInput)
                if citation_checker is None:
                    raise ContractError("citation checker is missing")
                validated = validate_provider_result(
                    payload.question, output.result, citation_checker
                )
                _ensure_unique_research_ids(evidence, numeric_claims, validated)
                evidence.extend(validated.evidence)
                numeric_claims.extend(validated.numeric_claims)
            successful.append(task.id)
        except Exception as exc:
            failures[task.id] = f"main-agent validation failed: {exc}"

    normalized, eliminated = _dedupe_worker_candidates(candidate_sources)
    exploration_tasks = [item for item in tasks if item.kind is WorkerKind.EXPLORATION]
    assigned_lenses = {
        item.payload.assigned_lens.value
        for item in exploration_tasks
        if isinstance(item.payload, ExplorationWorkerInput)
    }
    present_lenses = {item.exploration_lens.value for item in normalized}
    gaps = sorted(assigned_lenses - present_lenses)
    second_round = _second_round_decision(
        state,
        needs_followup=bool(gaps or failures),
        supplemental_rounds_used=supplemental_rounds_used,
    )
    source_conflicts = _source_conflict_groups(evidence)
    council = council_gate(
        council_config,
        independent_agent_count=len(successful),
    )
    synthesis_ready = bool(successful) and not source_conflicts and not failures and not gaps
    return OrchestrationOutcome(
        routing_decision=decision,
        state=copy.deepcopy(state),
        submitted_worker_ids=copy.deepcopy(submitted),
        successful_worker_ids=successful,
        failed_workers=copy.deepcopy(failures),
        normalized_candidates=normalized,
        eliminated_duplicates=eliminated,
        coverage_gaps=gaps,
        evidence=evidence,
        numeric_claims=numeric_claims,
        source_conflicts=source_conflicts,
        second_round=second_round,
        council=council,
        synthesis_ready=synthesis_ready,
        state_unchanged=state_to_dict(state) == before,
    )


def _empty_outcome(
    state: RuntimeState,
    decision: ParallelGateDecision,
    council_config: CouncilConfig,
    before: dict[str, Any],
) -> OrchestrationOutcome:
    return OrchestrationOutcome(
        routing_decision=decision,
        state=copy.deepcopy(state),
        submitted_worker_ids=[],
        successful_worker_ids=[],
        failed_workers={},
        normalized_candidates=[],
        eliminated_duplicates=[],
        coverage_gaps=[],
        evidence=[],
        numeric_claims=[],
        source_conflicts=[],
        second_round=SecondRoundDecision(
            SecondRoundStatus.NOT_NEEDED, "parallel gate stayed closed"
        ),
        council=council_gate(council_config, independent_agent_count=0),
        synthesis_ready=False,
        state_unchanged=state_to_dict(state) == before,
    )


def _parse_worker_candidates(
    worker_id: str,
    assigned_lens: ExplorationLens,
    values: list[dict[str, Any]],
) -> list[Candidate]:
    if not isinstance(values, list):
        raise ContractError("exploration output candidates must be a list")
    result: list[Candidate] = []
    for index, value in enumerate(values):
        if not isinstance(value, Mapping):
            raise ContractError(f"candidate[{index}] must be an object")
        candidate = candidate_from_dict(value)
        validate_candidate(candidate, f"{worker_id}.candidates[{index}]")
        if candidate.exploration_lens is not assigned_lens:
            raise ContractError(
                f"worker {worker_id!r} returned a candidate outside assigned_lens"
            )
        result.append(candidate)
    if not result:
        raise ContractError(f"worker {worker_id!r} returned no candidates")
    return result


def _dedupe_worker_candidates(
    values: Sequence[tuple[str, Candidate]],
) -> tuple[list[Candidate], list[EliminatedWorkerCandidate]]:
    kept: list[Candidate] = []
    eliminated: list[EliminatedWorkerCandidate] = []
    seen_ids: dict[str, tuple[str, Candidate]] = {}
    seen_mechanisms: dict[str, tuple[str, Candidate]] = {}
    for worker_id, candidate in values:
        existing_id = seen_ids.get(candidate.id)
        if existing_id is not None:
            eliminated.append(
                EliminatedWorkerCandidate(
                    worker_id,
                    candidate.id,
                    f"duplicate candidate id from worker {existing_id[0]}",
                )
            )
            continue
        mechanism = _canonical_mechanism(candidate.core_mechanism)
        existing_mechanism = seen_mechanisms.get(mechanism)
        if existing_mechanism is not None:
            eliminated.append(
                EliminatedWorkerCandidate(
                    worker_id,
                    candidate.id,
                    f"duplicate core mechanism of {existing_mechanism[1].id} "
                    f"from worker {existing_mechanism[0]}",
                )
            )
            seen_ids[candidate.id] = (worker_id, candidate)
            continue
        seen_ids[candidate.id] = (worker_id, candidate)
        seen_mechanisms[mechanism] = (worker_id, candidate)
        kept.append(copy.deepcopy(candidate))
    return kept, eliminated


def _second_round_decision(
    state: RuntimeState,
    *,
    needs_followup: bool,
    supplemental_rounds_used: int,
) -> SecondRoundDecision:
    if type(supplemental_rounds_used) is not int or supplemental_rounds_used < 0:
        raise ContractError("supplemental_rounds_used must be an integer >= 0")
    if not needs_followup:
        return SecondRoundDecision(
            SecondRoundStatus.NOT_NEEDED,
            "no worker failure or exploration coverage gap remains",
        )
    if supplemental_rounds_used >= 1:
        return SecondRoundDecision(
            SecondRoundStatus.DENIED_ALREADY_USED,
            "the single targeted supplemental round was already used",
        )
    if state.run.budget.used_steps >= state.run.budget.max_steps:
        return SecondRoundDecision(
            SecondRoundStatus.DENIED_BUDGET,
            "run budget is exhausted",
        )
    return SecondRoundDecision(
        SecondRoundStatus.ALLOWED,
        "main agent may choose one targeted supplemental round",
    )


def _validate_tasks(tasks: Sequence[WorkerTask]) -> list[WorkerTask]:
    if isinstance(tasks, (str, bytes)) or not isinstance(tasks, Sequence):
        raise ContractError("tasks must be a sequence")
    result = list(tasks)
    ids: set[str] = set()
    research_questions: set[str] = set()
    for index, task in enumerate(result):
        if not isinstance(task, WorkerTask):
            raise ContractError(f"tasks[{index}] must be WorkerTask")
        _required_string(task.id, f"tasks[{index}].id")
        if task.id in ids:
            raise ContractError(f"duplicate worker id {task.id!r}")
        ids.add(task.id)
        if not isinstance(task.kind, WorkerKind):
            raise ContractError(f"tasks[{index}].kind is invalid")
        if task.kind is WorkerKind.EXPLORATION:
            _validate_exploration_payload(task.payload, f"tasks[{index}].payload")
        else:
            if not isinstance(task.payload, ResearchWorkerInput):
                raise ContractError(
                    f"tasks[{index}].payload must be ResearchWorkerInput"
                )
            validate_research_question(task.payload.question)
            question_id = task.payload.question.id
            if question_id in research_questions:
                raise ContractError(
                    f"research question {question_id!r} has multiple workers"
                )
            research_questions.add(question_id)
    return result


def _validate_exploration_payload(value: Any, path: str) -> None:
    if not isinstance(value, ExplorationWorkerInput):
        raise ContractError(f"{path} must be ExplorationWorkerInput")
    if set(value.shared_frame) != {
        "problem",
        "user",
        "constraints",
        "success",
        "kill",
        "non_goals",
    }:
        raise ContractError(f"{path}.shared_frame must match the P0 Frame schema")
    if not isinstance(value.assigned_lens, ExplorationLens):
        raise ContractError(f"{path}.assigned_lens is invalid")
    _unique_strings(value.hard_constraints, f"{path}.hard_constraints")
    if value.candidate_output_schema != CANDIDATE_OUTPUT_SCHEMA:
        raise ContractError(f"{path}.candidate_output_schema must be canonical")


def _validate_execution_result(
    task: WorkerTask, result: WorkerExecutionResult
) -> None:
    if not isinstance(result, WorkerExecutionResult):
        raise ContractError("executor result must be WorkerExecutionResult")
    if result.worker_id != task.id or result.kind is not task.kind:
        raise ContractError("executor result identity does not match submitted task")
    if type(result.success) is not bool:
        raise ContractError("executor result success must be boolean")
    if result.success:
        if result.output is None or result.error is not None:
            raise ContractError("successful worker requires output and no error")
    else:
        if result.output is not None:
            raise ContractError("failed worker cannot return output")
        _required_string(result.error, "worker error")


def _ensure_unique_research_ids(
    evidence: Sequence[ResearchEvidenceRecord],
    numeric_claims: Sequence[NumericClaim],
    incoming: ProviderResearchResult,
) -> None:
    duplicate_evidence = {item.id for item in evidence} & {
        item.id for item in incoming.evidence
    }
    duplicate_numeric = {item.id for item in numeric_claims} & {
        item.id for item in incoming.numeric_claims
    }
    if duplicate_evidence:
        raise ContractError(f"duplicate evidence ids {sorted(duplicate_evidence)}")
    if duplicate_numeric:
        raise ContractError(f"duplicate numeric ids {sorted(duplicate_numeric)}")


def _source_conflict_groups(
    evidence: Sequence[ResearchEvidenceRecord],
) -> list[list[str]]:
    by_id = {item.id: item for item in evidence}
    groups: list[list[str]] = []
    visited: set[str] = set()
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
            if current in by_id:
                stack.extend(by_id[current].contradictions)
        visited.update(group)
        groups.append(sorted(group))
    return sorted(groups)


def _validate_gate_signals(signals: ParallelGateSignals) -> None:
    if not isinstance(signals, ParallelGateSignals):
        raise ContractError("signals must be ParallelGateSignals")
    if type(signals.independent_dimensions) is not int or signals.independent_dimensions < 0:
        raise ContractError("independent_dimensions must be an integer >= 0")
    for name in ("outputs_independently_generatable", "explicit_parallel_request"):
        if type(getattr(signals, name)) is not bool:
            raise ContractError(f"signals.{name} must be boolean")
    for name in ("synthesis_cost", "duplicated_context_cost"):
        value = getattr(signals, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ContractError(f"signals.{name} must be numeric and >= 0")


def _canonical_mechanism(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value


def _unique_strings(values: Sequence[str], path: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ContractError(f"{path} must be a sequence of strings")
    result = list(values)
    if not all(isinstance(item, str) and item.strip() for item in result):
        raise ContractError(f"{path} must contain non-empty strings")
    if len(result) != len(set(result)):
        raise ContractError(f"{path} must contain unique values")
    return result


def _signals_from_dict(value: Any) -> ParallelGateSignals:
    data = _require_exact_keys(
        value,
        {
            "independent_dimensions",
            "outputs_independently_generatable",
            "synthesis_cost",
            "duplicated_context_cost",
            "explicit_parallel_request",
        },
        "signals",
    )
    return ParallelGateSignals(**dict(data))


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
    gate = subparsers.add_parser("gate", help="evaluate the parallel worker gate")
    gate.add_argument("--json", help="request JSON; defaults to stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "gate":
            data = _require_exact_keys(
                _load_json(args.json), {"state", "signals"}, "request"
            )
            _emit(
                parallel_gate(
                    state_from_dict(_require_mapping(data["state"], "request.state")),
                    _signals_from_dict(data["signals"]),
                )
            )
        return 0
    except ContractError as exc:
        _emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
