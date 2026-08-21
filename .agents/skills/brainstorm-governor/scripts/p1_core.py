#!/usr/bin/env python3
"""Provider-neutral P1 single-agent brainstorming core loop.

The single agent supplies structured context, candidates, challenges, and
trade-off assessments. This module deterministically enforces the stage order
and P1 invariants without performing research or calling other agents.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from p0_runtime import (
    ContractError,
    ExitStatus,
    Frame,
    KnowledgeItem,
    KnowledgeStatus,
    Mode,
    RunStatus,
    RuntimeState,
    Stage,
    StateValidationError,
    state_from_dict,
    state_to_dict,
    validate_state,
)


class ExplorationLens(str, Enum):
    BASELINE = "BASELINE"
    ANALOGY = "ANALOGY"
    INVERSION = "INVERSION"
    CONSTRAINT_REMOVAL = "CONSTRAINT_REMOVAL"
    CONSTRAINT_ADDITION = "CONSTRAINT_ADDITION"
    SCALE_SHIFT = "SCALE_SHIFT"
    TIME_SHIFT = "TIME_SHIFT"
    STAKEHOLDER_SHIFT = "STAKEHOLDER_SHIFT"
    SUBSTITUTION = "SUBSTITUTION"


class CandidateComplexity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class ContextIntake:
    requested_outcome: KnowledgeItem | None = None
    current_idea: KnowledgeItem | None = None
    target_user: KnowledgeItem | None = None
    constraints: list[KnowledgeItem] = field(default_factory=list)
    questions: list[KnowledgeItem] = field(default_factory=list)
    alternatives: list[KnowledgeItem] = field(default_factory=list)
    assets: list[KnowledgeItem] = field(default_factory=list)


@dataclass
class ProblemFrame:
    problem_statement: KnowledgeItem
    target_user: KnowledgeItem
    job_to_be_done: KnowledgeItem
    desired_change: KnowledgeItem
    hard_constraints: list[KnowledgeItem]
    soft_preferences: list[KnowledgeItem]
    success_metric: KnowledgeItem
    kill_criterion: KnowledgeItem
    non_goals: list[KnowledgeItem]
    time_horizon: KnowledgeItem


@dataclass
class Candidate:
    id: str
    title: str
    one_liner: str
    core_mechanism: str
    target_user: KnowledgeItem
    value_created: str
    why_distinct: str
    key_assumptions: list[KnowledgeItem]
    main_dependency: KnowledgeItem
    exploration_lens: ExplorationLens
    complexity: CandidateComplexity


@dataclass
class CandidateChallenge:
    candidate_id: str
    blindspots: list[str]
    assumption_audit: list[KnowledgeItem]
    pressure_test: list[str]


@dataclass
class TradeoffAssessment:
    candidate_id: str
    hard_constraint_violations: list[str]
    user_value: float
    feasibility: float
    evidence_confidence: float
    reversibility: float
    risk: float


@dataclass
class NormalizationResult:
    candidates: list[Candidate]
    eliminated_duplicates: dict[str, str]
    clusters: dict[str, list[str]]
    outliers: list[str]
    coverage_gaps: list[ExplorationLens]
    supplemental_divergence_allowed: bool
    supplemental_rounds: int


@dataclass
class ConvergenceResult:
    shortlist: list[str]
    recommendation: str | None
    confidence: float | None
    decisive_assumptions: list[KnowledgeItem]
    risks: list[str]
    cheapest_test: str | None
    exit_status: ExitStatus
    eliminated_for_constraints: dict[str, list[str]]
    dominated_by: dict[str, list[str]]


@dataclass
class HumanGate:
    recommendation: str | None
    risks: list[str]
    decisive_assumptions: list[KnowledgeItem]
    cheapest_test: str | None
    exit_status: ExitStatus


@dataclass
class CoreLoopRequest:
    state: RuntimeState
    context: ContextIntake
    problem_frame: ProblemFrame
    candidates: list[Candidate]
    challenges: list[CandidateChallenge]
    assessments: list[TradeoffAssessment]
    recommended_candidate_id: str | None = None
    confidence: float | None = None
    cheapest_test: str | None = None
    supplemental_candidates: list[Candidate] = field(default_factory=list)
    supplemental_rounds: int = 0


@dataclass
class CoreLoopOutput:
    state: RuntimeState
    stage_history: list[Stage]
    selected_lenses: list[ExplorationLens]
    normalization: NormalizationResult | None
    convergence: ConvergenceResult | None
    human_gate: HumanGate


def run_core_loop(request: CoreLoopRequest) -> CoreLoopOutput:
    """Run the P1 state machine without network or sub-agent calls."""
    validate_state(request.state)
    state = copy.deepcopy(request.state)
    stage_history = [state.run.stage]

    _advance(state, Stage.CONTEXT, stage_history)
    validate_context(request.context)
    _apply_context(state, request.context)

    _advance(state, Stage.FRAME, stage_history)
    validate_problem_frame(request.problem_frame)
    _validate_context_frame_consistency(request.context, request.problem_frame)
    _apply_problem_frame(state, request.problem_frame)

    critical_unknowns = _critical_frame_unknowns(request.problem_frame)
    if critical_unknowns:
        for item in critical_unknowns:
            _append_knowledge(state.unknowns, item)
        gate = HumanGate(
            recommendation=None,
            risks=[],
            decisive_assumptions=[],
            cheapest_test=None,
            exit_status=ExitStatus.NEEDS_INPUT,
        )
        _stop(state, gate.exit_status, stage_history)
        return CoreLoopOutput(
            state=state,
            stage_history=stage_history,
            selected_lenses=[],
            normalization=None,
            convergence=None,
            human_gate=gate,
        )

    selected_lenses = select_exploration_lenses(
        request.problem_frame, state.run.mode
    )

    _advance(state, Stage.DIVERGE, stage_history)
    validate_candidates(request.candidates, selected_lenses)
    if request.supplemental_candidates:
        validate_candidates(
            request.supplemental_candidates,
            selected_lenses,
            require_diversity_guards=False,
        )
    _apply_candidate_knowledge(
        state, [*request.candidates, *request.supplemental_candidates]
    )

    _advance(state, Stage.NORMALIZE, stage_history)
    normalization = normalize_candidates(
        request.candidates,
        selected_lenses,
        supplemental_candidates=request.supplemental_candidates,
        supplemental_rounds=request.supplemental_rounds,
    )
    state.candidates = [_candidate_to_dict(item) for item in normalization.candidates]

    frame_snapshot = copy.deepcopy(state.frame)
    _advance(state, Stage.CHALLENGE, stage_history)
    validate_challenges(state, normalization.candidates, request.challenges)
    _apply_challenge_knowledge(state, request.challenges)
    if state.frame != frame_snapshot:
        raise ContractError("Challenge cannot modify the confirmed Problem Frame")

    _advance(state, Stage.CONVERGE, stage_history)
    convergence = converge_candidates(
        normalization.candidates,
        request.challenges,
        request.assessments,
        recommended_candidate_id=request.recommended_candidate_id,
        confidence=request.confidence,
        cheapest_test=request.cheapest_test,
    )
    state.result.shortlist = list(convergence.shortlist)
    state.result.recommendation = convergence.recommendation
    state.result.confidence = convergence.confidence
    state.result.cheapest_test = convergence.cheapest_test

    gate = HumanGate(
        recommendation=convergence.recommendation,
        risks=list(convergence.risks),
        decisive_assumptions=copy.deepcopy(convergence.decisive_assumptions),
        cheapest_test=convergence.cheapest_test,
        exit_status=convergence.exit_status,
    )
    _stop(state, gate.exit_status, stage_history)
    return CoreLoopOutput(
        state=state,
        stage_history=stage_history,
        selected_lenses=selected_lenses,
        normalization=normalization,
        convergence=convergence,
        human_gate=gate,
    )


def select_exploration_lenses(
    problem_frame: ProblemFrame, mode: Mode
) -> list[ExplorationLens]:
    """Choose three to five complementary lenses without ranking ideas."""
    validate_problem_frame(problem_frame)
    if not isinstance(mode, Mode):
        raise ContractError("mode must be a valid Mode")

    if mode is Mode.SPARK:
        return [
            ExplorationLens.BASELINE,
            ExplorationLens.INVERSION,
            ExplorationLens.SUBSTITUTION,
        ]
    if mode is Mode.STRESS:
        return [
            ExplorationLens.BASELINE,
            ExplorationLens.INVERSION,
            ExplorationLens.STAKEHOLDER_SHIFT,
            ExplorationLens.SUBSTITUTION,
        ]
    if mode is Mode.DECIDE:
        return [
            ExplorationLens.BASELINE,
            ExplorationLens.ANALOGY,
            ExplorationLens.STAKEHOLDER_SHIFT,
            ExplorationLens.SCALE_SHIFT,
            ExplorationLens.SUBSTITUTION,
        ]

    lenses = [ExplorationLens.BASELINE, ExplorationLens.ANALOGY]
    if problem_frame.hard_constraints:
        lenses.append(ExplorationLens.CONSTRAINT_REMOVAL)
    else:
        lenses.append(ExplorationLens.INVERSION)
    lenses.extend(
        [ExplorationLens.STAKEHOLDER_SHIFT, ExplorationLens.SUBSTITUTION]
    )
    return lenses[:5]


def normalize_candidates(
    candidates: list[Candidate],
    selected_lenses: list[ExplorationLens],
    *,
    supplemental_candidates: list[Candidate] | None = None,
    supplemental_rounds: int = 0,
) -> NormalizationResult:
    """Deduplicate by mechanism, cluster by lens, and expose coverage gaps."""
    supplemental = list(supplemental_candidates or [])
    validate_candidates(candidates, selected_lenses)
    if supplemental:
        validate_candidates(
            supplemental,
            selected_lenses,
            require_diversity_guards=False,
        )
    if supplemental_rounds not in {0, 1}:
        raise ContractError("targeted supplemental divergence is limited to one round")
    if supplemental and supplemental_rounds != 1:
        raise ContractError(
            "supplemental_candidates require supplemental_rounds=1"
        )
    if not supplemental and supplemental_rounds != 0:
        raise ContractError(
            "supplemental_rounds must be 0 when no supplemental candidates exist"
        )

    kept: list[Candidate] = []
    seen_mechanisms: dict[str, str] = {}
    eliminated: dict[str, str] = {}
    for candidate in [*candidates, *supplemental]:
        key = _canonical_mechanism(candidate.core_mechanism)
        if key in seen_mechanisms:
            eliminated[candidate.id] = (
                f"duplicate core mechanism of {seen_mechanisms[key]}"
            )
            continue
        seen_mechanisms[key] = candidate.id
        kept.append(copy.deepcopy(candidate))

    clusters: dict[str, list[str]] = {}
    for candidate in kept:
        clusters.setdefault(candidate.exploration_lens.value, []).append(candidate.id)
    outliers = [
        candidate_ids[0]
        for candidate_ids in clusters.values()
        if len(candidate_ids) == 1
    ]
    present_lenses = {item.exploration_lens for item in kept}
    gaps = [lens for lens in selected_lenses if lens not in present_lenses]

    return NormalizationResult(
        candidates=kept,
        eliminated_duplicates=eliminated,
        clusters=clusters,
        outliers=outliers,
        coverage_gaps=gaps,
        supplemental_divergence_allowed=bool(gaps and supplemental_rounds == 0),
        supplemental_rounds=supplemental_rounds,
    )


def converge_candidates(
    candidates: list[Candidate],
    challenges: list[CandidateChallenge],
    assessments: list[TradeoffAssessment],
    *,
    recommended_candidate_id: str | None,
    confidence: float | None,
    cheapest_test: str | None,
) -> ConvergenceResult:
    """Apply hard constraints, Pareto dominance, and a Human Gate."""
    candidate_by_id = {item.id: item for item in candidates}
    if len(candidate_by_id) != len(candidates):
        raise ContractError("candidate ids must be unique before convergence")
    challenge_by_id = {item.candidate_id: item for item in challenges}
    assessment_by_id = {item.candidate_id: item for item in assessments}
    expected = set(candidate_by_id)
    if len(challenge_by_id) != len(challenges):
        raise ContractError("challenge candidate ids must be unique")
    if len(assessment_by_id) != len(assessments):
        raise ContractError("assessment candidate ids must be unique")
    if set(challenge_by_id) != expected:
        raise ContractError("every normalized candidate requires exactly one challenge")
    if set(assessment_by_id) != expected:
        raise ContractError("every normalized candidate requires exactly one assessment")
    for assessment in assessments:
        _validate_assessment(assessment)

    eliminated_for_constraints = {
        item.candidate_id: list(item.hard_constraint_violations)
        for item in assessments
        if item.hard_constraint_violations
    }
    feasible = [
        item.candidate_id
        for item in assessments
        if not item.hard_constraint_violations
    ]

    dominated_by: dict[str, list[str]] = {}
    for candidate_id in feasible:
        dominators = [
            other_id
            for other_id in feasible
            if other_id != candidate_id
            and _dominates(
                assessment_by_id[other_id], assessment_by_id[candidate_id]
            )
        ]
        if dominators:
            dominated_by[candidate_id] = sorted(dominators)

    pareto = [item for item in feasible if item not in dominated_by]
    pareto.sort(key=lambda item: _comparison_key(assessment_by_id[item]))
    shortlist = pareto[:3]

    recommendation = recommended_candidate_id
    if recommendation is not None and recommendation not in shortlist:
        raise ContractError(
            "recommended candidate must survive hard constraints and dominance"
        )
    if recommendation is None and len(shortlist) == 1:
        recommendation = shortlist[0]

    if recommendation is not None:
        if confidence is None:
            raise ContractError("confidence is required with a recommendation")
        if not isinstance(cheapest_test, str) or not cheapest_test.strip():
            raise ContractError("cheapest_test is required with a recommendation")
    _validate_confidence(confidence)

    decisive_assumptions: list[KnowledgeItem] = []
    risks: list[str] = []
    if recommendation is not None:
        challenge = challenge_by_id[recommendation]
        decisive_assumptions = copy.deepcopy(challenge.assumption_audit)
        risks = _dedupe_strings([*challenge.blindspots, *challenge.pressure_test])

    if not shortlist:
        exit_status = ExitStatus.ITERATE
    elif recommendation is None:
        exit_status = ExitStatus.EXPLORE
    else:
        exit_status = ExitStatus.NEEDS_INPUT

    return ConvergenceResult(
        shortlist=shortlist,
        recommendation=recommendation,
        confidence=confidence,
        decisive_assumptions=decisive_assumptions,
        risks=risks,
        cheapest_test=cheapest_test,
        exit_status=exit_status,
        eliminated_for_constraints=eliminated_for_constraints,
        dominated_by=dominated_by,
    )


def validate_context(context: ContextIntake) -> None:
    if not isinstance(context, ContextIntake):
        raise ContractError("context must be ContextIntake")
    for name in ("requested_outcome", "current_idea", "target_user"):
        item = getattr(context, name)
        if item is not None:
            _validate_knowledge_item(item, f"context.{name}")
    for name in ("constraints", "questions", "alternatives", "assets"):
        items = getattr(context, name)
        if not isinstance(items, list):
            raise ContractError(f"context.{name} must be a list")
        for index, item in enumerate(items):
            _validate_knowledge_item(item, f"context.{name}[{index}]")


def validate_problem_frame(problem_frame: ProblemFrame) -> None:
    if not isinstance(problem_frame, ProblemFrame):
        raise ContractError("problem_frame must be ProblemFrame")
    for name in (
        "problem_statement",
        "target_user",
        "job_to_be_done",
        "desired_change",
        "success_metric",
        "kill_criterion",
        "time_horizon",
    ):
        _validate_knowledge_item(getattr(problem_frame, name), f"problem_frame.{name}")
    for name in ("hard_constraints", "soft_preferences", "non_goals"):
        items = getattr(problem_frame, name)
        if not isinstance(items, list):
            raise ContractError(f"problem_frame.{name} must be a list")
        for index, item in enumerate(items):
            _validate_knowledge_item(item, f"problem_frame.{name}[{index}]")


def validate_candidates(
    candidates: list[Candidate],
    selected_lenses: list[ExplorationLens],
    *,
    require_diversity_guards: bool = True,
) -> None:
    if not isinstance(candidates, list) or not candidates:
        raise ContractError("divergence must produce at least one candidate")
    if not 3 <= len(selected_lenses) <= 5:
        raise ContractError("divergence must select three to five lenses")
    if len(set(selected_lenses)) != len(selected_lenses):
        raise ContractError("selected lenses must be unique")

    ids: set[str] = set()
    for index, candidate in enumerate(candidates):
        _validate_candidate(candidate, f"candidates[{index}]")
        if candidate.id in ids:
            raise ContractError(f"duplicate candidate id {candidate.id!r}")
        ids.add(candidate.id)
        if candidate.exploration_lens not in selected_lenses:
            raise ContractError(
                f"candidate {candidate.id!r} uses an unselected exploration lens"
            )

    if require_diversity_guards:
        if not any(item.complexity is CandidateComplexity.LOW for item in candidates):
            raise ContractError("divergence requires at least one low-complexity option")
        if not any(
            item.exploration_lens
            in {ExplorationLens.INVERSION, ExplorationLens.SUBSTITUTION}
            for item in candidates
        ):
            raise ContractError(
                "divergence requires an inversion or substitution option"
            )


def validate_challenges(
    state: RuntimeState,
    candidates: list[Candidate],
    challenges: list[CandidateChallenge],
) -> None:
    if state.run.stage not in {Stage.NORMALIZE, Stage.CHALLENGE}:
        raise ContractError("Challenge cannot run before Divergence and Normalize")
    expected = {item.id for item in candidates}
    actual = {item.candidate_id for item in challenges}
    if len(actual) != len(challenges):
        raise ContractError("challenge candidate ids must be unique")
    if actual != expected:
        raise ContractError("every normalized candidate requires exactly one challenge")

    for index, challenge in enumerate(challenges):
        path = f"challenges[{index}]"
        if not isinstance(challenge, CandidateChallenge):
            raise ContractError(f"{path} must be CandidateChallenge")
        if not isinstance(challenge.candidate_id, str) or not challenge.candidate_id.strip():
            raise ContractError(f"{path}.candidate_id must be a non-empty string")
        if not isinstance(challenge.blindspots, list) or not challenge.blindspots or not all(
            isinstance(item, str) and item.strip() for item in challenge.blindspots
        ):
            raise ContractError(f"{path}.blindspots must contain non-empty strings")
        if not isinstance(challenge.pressure_test, list) or not challenge.pressure_test or not all(
            isinstance(item, str) and item.strip()
            for item in challenge.pressure_test
        ):
            raise ContractError(
                f"{path}.pressure_test must contain non-empty strings"
            )
        if not isinstance(challenge.assumption_audit, list) or not challenge.assumption_audit:
            raise ContractError(f"{path}.assumption_audit must not be empty")
        for assumption_index, item in enumerate(challenge.assumption_audit):
            _validate_knowledge_item(
                item, f"{path}.assumption_audit[{assumption_index}]"
            )
            if item.classification not in {
                KnowledgeStatus.ASSUMPTION,
                KnowledgeStatus.UNKNOWN,
            }:
                raise ContractError(
                    f"{path}.assumption_audit only accepts ASSUMPTION or UNKNOWN"
                )


def candidate_from_dict(value: Mapping[str, Any]) -> Candidate:
    data = _require_mapping(value, "candidate")
    expected = {
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
    }
    _require_keys(data, expected, "candidate")
    return Candidate(
        id=data["id"],
        title=data["title"],
        one_liner=data["one_liner"],
        core_mechanism=data["core_mechanism"],
        target_user=_knowledge_from_dict(data["target_user"], "candidate.target_user"),
        value_created=data["value_created"],
        why_distinct=data["why_distinct"],
        key_assumptions=_knowledge_list(
            data["key_assumptions"], "candidate.key_assumptions"
        ),
        main_dependency=_knowledge_from_dict(
            data["main_dependency"], "candidate.main_dependency"
        ),
        exploration_lens=_enum_value(
            ExplorationLens, data["exploration_lens"], "candidate.exploration_lens"
        ),
        complexity=_enum_value(
            CandidateComplexity, data["complexity"], "candidate.complexity"
        ),
    )


def validate_candidate(candidate: Candidate, path: str = "candidate") -> None:
    """Validate one P1 candidate for downstream worker adapters."""
    _validate_candidate(candidate, path)


def core_loop_request_from_dict(value: Mapping[str, Any]) -> CoreLoopRequest:
    data = _require_mapping(value, "request")
    expected = {
        "state",
        "context",
        "problem_frame",
        "candidates",
        "challenges",
        "assessments",
        "recommended_candidate_id",
        "confidence",
        "cheapest_test",
        "supplemental_candidates",
        "supplemental_rounds",
    }
    _require_keys(data, expected, "request")
    return CoreLoopRequest(
        state=state_from_dict(data["state"]),
        context=_context_from_dict(data["context"]),
        problem_frame=_problem_frame_from_dict(data["problem_frame"]),
        candidates=[
            candidate_from_dict(item)
            for item in _mapping_sequence(data["candidates"], "request.candidates")
        ],
        challenges=[
            _challenge_from_dict(item)
            for item in _mapping_sequence(data["challenges"], "request.challenges")
        ],
        assessments=[
            _assessment_from_dict(item)
            for item in _mapping_sequence(data["assessments"], "request.assessments")
        ],
        recommended_candidate_id=data["recommended_candidate_id"],
        confidence=data["confidence"],
        cheapest_test=data["cheapest_test"],
        supplemental_candidates=[
            candidate_from_dict(item)
            for item in _mapping_sequence(
                data["supplemental_candidates"], "request.supplemental_candidates"
            )
        ],
        supplemental_rounds=data["supplemental_rounds"],
    )


def output_to_dict(output: CoreLoopOutput) -> dict[str, Any]:
    return {
        "state": state_to_dict(output.state),
        "stage_history": [item.value for item in output.stage_history],
        "selected_lenses": [item.value for item in output.selected_lenses],
        "normalization": _json_ready(output.normalization),
        "convergence": _json_ready(output.convergence),
        "human_gate": _json_ready(output.human_gate),
    }


def _advance(state: RuntimeState, stage: Stage, history: list[Stage]) -> None:
    if state.run.budget.used_steps >= state.run.budget.max_steps:
        raise StateValidationError(["run budget exhausted before stage transition"])
    state.run.budget.used_steps += 1
    state.run.stage = stage
    state.run.status = RunStatus.ACTIVE
    history.append(stage)
    validate_state(state)


def _stop(
    state: RuntimeState, exit_status: ExitStatus, history: list[Stage]
) -> None:
    if state.run.budget.used_steps >= state.run.budget.max_steps:
        raise StateValidationError(["run budget exhausted before safe stop"])
    state.run.budget.used_steps += 1
    state.run.stage = Stage.STOPPED
    state.run.status = RunStatus.STOPPED
    state.result.exit_status = exit_status
    history.append(Stage.STOPPED)
    validate_state(state)


def _apply_context(state: RuntimeState, context: ContextIntake) -> None:
    for item in _context_items(context):
        _classify_into_state(state, item)


def _apply_problem_frame(state: RuntimeState, problem_frame: ProblemFrame) -> None:
    state.frame = Frame(
        problem=copy.deepcopy(problem_frame.problem_statement),
        user=copy.deepcopy(problem_frame.target_user),
        constraints=copy.deepcopy(
            [*problem_frame.hard_constraints, *problem_frame.soft_preferences]
        ),
        success=copy.deepcopy(problem_frame.success_metric),
        kill=copy.deepcopy(problem_frame.kill_criterion),
        non_goals=copy.deepcopy(problem_frame.non_goals),
    )
    for item in _problem_frame_items(problem_frame):
        _classify_into_state(state, item)
    validate_state(state)


def _apply_challenge_knowledge(
    state: RuntimeState, challenges: list[CandidateChallenge]
) -> None:
    for challenge in challenges:
        for item in challenge.assumption_audit:
            _classify_into_state(state, item)
    validate_state(state)


def _apply_candidate_knowledge(
    state: RuntimeState, candidates: list[Candidate]
) -> None:
    for candidate in candidates:
        _classify_into_state(state, candidate.target_user)
        _classify_into_state(state, candidate.main_dependency)
        for item in candidate.key_assumptions:
            _classify_into_state(state, item)
    validate_state(state)


def _classify_into_state(state: RuntimeState, item: KnowledgeItem) -> None:
    if item.classification is KnowledgeStatus.ASSUMPTION:
        _append_knowledge(state.assumptions, item)
    elif item.classification is KnowledgeStatus.UNKNOWN:
        _append_knowledge(state.unknowns, item)


def _append_knowledge(items: list[KnowledgeItem], item: KnowledgeItem) -> None:
    key = (_normalize(item.statement), item.classification)
    if all((_normalize(existing.statement), existing.classification) != key for existing in items):
        items.append(copy.deepcopy(item))


def _context_items(context: ContextIntake) -> list[KnowledgeItem]:
    values: list[KnowledgeItem] = []
    for item in (context.requested_outcome, context.current_idea, context.target_user):
        if item is not None:
            values.append(item)
    values.extend(context.constraints)
    values.extend(context.questions)
    values.extend(context.alternatives)
    values.extend(context.assets)
    return values


def _problem_frame_items(problem_frame: ProblemFrame) -> list[KnowledgeItem]:
    return [
        problem_frame.problem_statement,
        problem_frame.target_user,
        problem_frame.job_to_be_done,
        problem_frame.desired_change,
        *problem_frame.hard_constraints,
        *problem_frame.soft_preferences,
        problem_frame.success_metric,
        problem_frame.kill_criterion,
        *problem_frame.non_goals,
        problem_frame.time_horizon,
    ]


def _critical_frame_unknowns(problem_frame: ProblemFrame) -> list[KnowledgeItem]:
    critical = [
        problem_frame.problem_statement,
        problem_frame.target_user,
        problem_frame.job_to_be_done,
        problem_frame.desired_change,
        problem_frame.success_metric,
        problem_frame.kill_criterion,
        *problem_frame.hard_constraints,
    ]
    return [item for item in critical if item.classification is KnowledgeStatus.UNKNOWN]


def _validate_context_frame_consistency(
    context: ContextIntake, problem_frame: ProblemFrame
) -> None:
    by_statement: dict[str, set[KnowledgeStatus]] = {}
    for item in [*_context_items(context), *_problem_frame_items(problem_frame)]:
        by_statement.setdefault(_normalize(item.statement), set()).add(
            item.classification
        )
    for statement, statuses in by_statement.items():
        if KnowledgeStatus.UNKNOWN in statuses and KnowledgeStatus.KNOWN in statuses:
            raise ContractError(
                f"claim {statement!r} cannot change from UNKNOWN to KNOWN without evidence"
            )


def _validate_candidate(candidate: Candidate, path: str) -> None:
    if not isinstance(candidate, Candidate):
        raise ContractError(f"{path} must be Candidate")
    for name in (
        "id",
        "title",
        "one_liner",
        "core_mechanism",
        "value_created",
        "why_distinct",
    ):
        value = getattr(candidate, name)
        if not isinstance(value, str) or not value.strip():
            raise ContractError(f"{path}.{name} must be a non-empty string")
    _validate_knowledge_item(candidate.target_user, f"{path}.target_user")
    _validate_knowledge_item(candidate.main_dependency, f"{path}.main_dependency")
    if not isinstance(candidate.key_assumptions, list):
        raise ContractError(f"{path}.key_assumptions must be a list")
    for index, item in enumerate(candidate.key_assumptions):
        _validate_knowledge_item(item, f"{path}.key_assumptions[{index}]")
        if item.classification not in {
            KnowledgeStatus.ASSUMPTION,
            KnowledgeStatus.UNKNOWN,
        }:
            raise ContractError(
                f"{path}.key_assumptions only accepts ASSUMPTION or UNKNOWN"
            )
    if not isinstance(candidate.exploration_lens, ExplorationLens):
        raise ContractError(f"{path}.exploration_lens must be ExplorationLens")
    if not isinstance(candidate.complexity, CandidateComplexity):
        raise ContractError(f"{path}.complexity must be CandidateComplexity")


def _validate_assessment(assessment: TradeoffAssessment) -> None:
    if not isinstance(assessment, TradeoffAssessment):
        raise ContractError("assessment must be TradeoffAssessment")
    if not isinstance(assessment.candidate_id, str) or not assessment.candidate_id.strip():
        raise ContractError("assessment.candidate_id must be a non-empty string")
    if not isinstance(assessment.hard_constraint_violations, list) or not all(
        isinstance(item, str) and item.strip()
        for item in assessment.hard_constraint_violations
    ):
        raise ContractError(
            "assessment.hard_constraint_violations must contain non-empty strings"
        )
    for name in (
        "user_value",
        "feasibility",
        "evidence_confidence",
        "reversibility",
        "risk",
    ):
        value = getattr(assessment, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ContractError(f"assessment.{name} must be numeric")
        if not 0 <= float(value) <= 1:
            raise ContractError(f"assessment.{name} must be between 0 and 1")


def _dominates(left: TradeoffAssessment, right: TradeoffAssessment) -> bool:
    left_quality = (
        left.user_value,
        left.feasibility,
        left.evidence_confidence,
        left.reversibility,
    )
    right_quality = (
        right.user_value,
        right.feasibility,
        right.evidence_confidence,
        right.reversibility,
    )
    no_worse = all(a >= b for a, b in zip(left_quality, right_quality)) and (
        left.risk <= right.risk
    )
    strictly_better = any(a > b for a, b in zip(left_quality, right_quality)) or (
        left.risk < right.risk
    )
    return no_worse and strictly_better


def _comparison_key(assessment: TradeoffAssessment) -> tuple[Any, ...]:
    return (
        -assessment.user_value,
        -assessment.feasibility,
        -assessment.evidence_confidence,
        -assessment.reversibility,
        assessment.risk,
        assessment.candidate_id,
    )


def _validate_confidence(confidence: float | None) -> None:
    if confidence is None:
        return
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ContractError("confidence must be numeric or null")
    if not 0 <= float(confidence) <= 1:
        raise ContractError("confidence must be between 0 and 1")


def _canonical_mechanism(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _normalize(value)
        if normalized not in seen:
            seen.add(normalized)
            result.append(value)
    return result


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _candidate_to_dict(candidate: Candidate) -> dict[str, Any]:
    return _json_ready(candidate)


def _validate_knowledge_item(item: KnowledgeItem, path: str) -> None:
    if not isinstance(item, KnowledgeItem):
        raise ContractError(f"{path} must be KnowledgeItem")
    if not isinstance(item.statement, str) or not item.statement.strip():
        raise ContractError(f"{path}.statement must be a non-empty string")
    if not isinstance(item.classification, KnowledgeStatus):
        raise ContractError(f"{path}.classification must be KnowledgeStatus")


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
    return [
        _knowledge_from_dict(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    ]


def _context_from_dict(value: Any) -> ContextIntake:
    data = _require_mapping(value, "context")
    expected = {
        "requested_outcome",
        "current_idea",
        "target_user",
        "constraints",
        "questions",
        "alternatives",
        "assets",
    }
    _require_keys(data, expected, "context")
    return ContextIntake(
        requested_outcome=_optional_knowledge(
            data["requested_outcome"], "context.requested_outcome"
        ),
        current_idea=_optional_knowledge(data["current_idea"], "context.current_idea"),
        target_user=_optional_knowledge(data["target_user"], "context.target_user"),
        constraints=_knowledge_list(data["constraints"], "context.constraints"),
        questions=_knowledge_list(data["questions"], "context.questions"),
        alternatives=_knowledge_list(data["alternatives"], "context.alternatives"),
        assets=_knowledge_list(data["assets"], "context.assets"),
    )


def _problem_frame_from_dict(value: Any) -> ProblemFrame:
    data = _require_mapping(value, "problem_frame")
    expected = {
        "problem_statement",
        "target_user",
        "job_to_be_done",
        "desired_change",
        "hard_constraints",
        "soft_preferences",
        "success_metric",
        "kill_criterion",
        "non_goals",
        "time_horizon",
    }
    _require_keys(data, expected, "problem_frame")
    return ProblemFrame(
        problem_statement=_knowledge_from_dict(
            data["problem_statement"], "problem_frame.problem_statement"
        ),
        target_user=_knowledge_from_dict(
            data["target_user"], "problem_frame.target_user"
        ),
        job_to_be_done=_knowledge_from_dict(
            data["job_to_be_done"], "problem_frame.job_to_be_done"
        ),
        desired_change=_knowledge_from_dict(
            data["desired_change"], "problem_frame.desired_change"
        ),
        hard_constraints=_knowledge_list(
            data["hard_constraints"], "problem_frame.hard_constraints"
        ),
        soft_preferences=_knowledge_list(
            data["soft_preferences"], "problem_frame.soft_preferences"
        ),
        success_metric=_knowledge_from_dict(
            data["success_metric"], "problem_frame.success_metric"
        ),
        kill_criterion=_knowledge_from_dict(
            data["kill_criterion"], "problem_frame.kill_criterion"
        ),
        non_goals=_knowledge_list(data["non_goals"], "problem_frame.non_goals"),
        time_horizon=_knowledge_from_dict(
            data["time_horizon"], "problem_frame.time_horizon"
        ),
    )


def _challenge_from_dict(value: Any) -> CandidateChallenge:
    data = _require_mapping(value, "challenge")
    _require_keys(
        data,
        {"candidate_id", "blindspots", "assumption_audit", "pressure_test"},
        "challenge",
    )
    return CandidateChallenge(
        candidate_id=data["candidate_id"],
        blindspots=_string_list(data["blindspots"], "challenge.blindspots"),
        assumption_audit=_knowledge_list(
            data["assumption_audit"], "challenge.assumption_audit"
        ),
        pressure_test=_string_list(
            data["pressure_test"], "challenge.pressure_test"
        ),
    )


def _assessment_from_dict(value: Any) -> TradeoffAssessment:
    data = _require_mapping(value, "assessment")
    expected = {
        "candidate_id",
        "hard_constraint_violations",
        "user_value",
        "feasibility",
        "evidence_confidence",
        "reversibility",
        "risk",
    }
    _require_keys(data, expected, "assessment")
    return TradeoffAssessment(
        candidate_id=data["candidate_id"],
        hard_constraint_violations=_string_list(
            data["hard_constraint_violations"],
            "assessment.hard_constraint_violations",
        ),
        user_value=data["user_value"],
        feasibility=data["feasibility"],
        evidence_confidence=data["evidence_confidence"],
        reversibility=data["reversibility"],
        risk=data["risk"],
    )


def _string_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ContractError(f"{path} must be a list of strings")
    return list(value)


def _mapping_sequence(value: Any, path: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be a list")
    result: list[Mapping[str, Any]] = []
    for index, item in enumerate(value):
        result.append(_require_mapping(item, f"{path}[{index}]"))
    return result


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
    json.dump(value, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="run the P1 core loop")
    run_parser.add_argument("--json", help="request JSON; defaults to stdin")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "run":
            request = core_loop_request_from_dict(_load_json(args.json))
            _emit(output_to_dict(run_core_loop(request)))
        return 0
    except ContractError as exc:
        _emit({"valid": False, "error": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
