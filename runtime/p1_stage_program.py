"""Resumable stage adapter over the unchanged P1 deterministic contracts."""

from __future__ import annotations

import copy

from runtime.fault_injection import Stage
from runtime.governor_modules import p0, p1
from runtime.reentry import StageContext, StageOutcome


P1_STAGES = (
    Stage.CONTEXT,
    Stage.FRAME,
    Stage.DIVERGE,
    Stage.NORMALIZE,
    Stage.CHALLENGE,
    Stage.CONVERGE,
)


class P1StageProgram:
    """Execute one P1 stage at a time so every boundary can be checkpointed."""

    def __init__(self, request: p1.CoreLoopRequest) -> None:
        self.request = request

    def __call__(
        self,
        stage: Stage,
        state: p0.RuntimeState,
        context: StageContext,
    ) -> p0.RuntimeState | StageOutcome:
        del context

        if stage is Stage.CONTEXT:
            p1.validate_context(self.request.context)
            p1._apply_context(state, self.request.context)
            return state

        if stage is Stage.FRAME:
            p1.validate_problem_frame(self.request.problem_frame)
            p1._validate_context_frame_consistency(
                self.request.context, self.request.problem_frame
            )
            p1._apply_problem_frame(state, self.request.problem_frame)
            critical_unknowns = p1._critical_frame_unknowns(self.request.problem_frame)
            if critical_unknowns:
                for item in critical_unknowns:
                    p1._append_knowledge(state.unknowns, item)
                return StageOutcome(
                    state,
                    p0.ExitStatus.NEEDS_INPUT,
                    _next_action(p0.ExitStatus.NEEDS_INPUT),
                )
            return state

        lenses = p1.select_exploration_lenses(
            self.request.problem_frame, state.run.mode
        )

        if stage is Stage.DIVERGE:
            p1.validate_candidates(self.request.candidates, lenses)
            if self.request.supplemental_candidates:
                p1.validate_candidates(
                    self.request.supplemental_candidates,
                    lenses,
                    require_diversity_guards=False,
                )
            p1._apply_candidate_knowledge(
                state,
                [*self.request.candidates, *self.request.supplemental_candidates],
            )
            return state

        normalization = p1.normalize_candidates(
            self.request.candidates,
            lenses,
            supplemental_candidates=self.request.supplemental_candidates,
            supplemental_rounds=self.request.supplemental_rounds,
        )

        if stage is Stage.NORMALIZE:
            state.candidates = [
                p1._candidate_to_dict(item) for item in normalization.candidates
            ]
            p0.validate_state(state)
            return state

        if stage is Stage.CHALLENGE:
            frame_snapshot = copy.deepcopy(state.frame)
            p1.validate_challenges(
                state, normalization.candidates, self.request.challenges
            )
            p1._apply_challenge_knowledge(state, self.request.challenges)
            if state.frame != frame_snapshot:
                raise p0.ContractError(
                    "Challenge cannot modify the confirmed Problem Frame"
                )
            return state

        if stage is Stage.CONVERGE:
            convergence = p1.converge_candidates(
                normalization.candidates,
                self.request.challenges,
                self.request.assessments,
                recommended_candidate_id=self.request.recommended_candidate_id,
                confidence=self.request.confidence,
                cheapest_test=self.request.cheapest_test,
            )
            state.result.shortlist = list(convergence.shortlist)
            state.result.recommendation = convergence.recommendation
            state.result.confidence = convergence.confidence
            state.result.cheapest_test = convergence.cheapest_test
            p0.validate_state(state)
            return StageOutcome(
                state,
                convergence.exit_status,
                _next_action(convergence.exit_status),
            )

        raise p0.ContractError(f"P1StageProgram does not support {stage.value}")

def _next_action(exit_status: p0.ExitStatus) -> str:
    return {
        p0.ExitStatus.EXPLORE: "choose or refine one viable direction",
        p0.ExitStatus.RESEARCH_REQUIRED: "authorize or provide required evidence",
        p0.ExitStatus.ITERATE: "repair constraints and generate another candidate set",
        p0.ExitStatus.COMMIT: "produce the restricted approved handoff",
        p0.ExitStatus.PARK: "resume from the Living Brief checkpoint",
        p0.ExitStatus.NEEDS_INPUT: "provide the missing Problem Frame information",
    }[exit_status]
