"""FV-01 one-command lifecycle runner over the existing P0/P1/P2 contracts."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from observability.trace_sink import TraceSink
from observability.usage_ledger import PriceTable, UsageLedger
from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.checkpoint import CheckpointSession, CheckpointStore
from runtime.config_loader import GovernorConfig
from runtime.fault_injection import FaultInjector, FaultPoint, Stage as FaultStage
from runtime.governor_modules import p0, p1, p2
from runtime.lifecycle_errors import BudgetExhausted, coerce_budget_exhausted
from runtime.p1_stage_program import P1_STAGES, P1StageProgram
from runtime.reentry import DurableStageRunner


LEGAL_EXIT_STATUSES = frozenset(item.value for item in p0.ExitStatus)
DEFAULT_PRICING_PATH = Path(__file__).parents[1] / "config" / "provider-pricing.json"


class RequestError(p0.ContractError):
    """Raised when the full-cycle request envelope is invalid."""


@dataclass(frozen=True)
class FullCycleRequest:
    text: str
    request_id: str | None
    routing: dict[str, Any]
    core: dict[str, Any] | None


@dataclass(frozen=True)
class RunSummary:
    run_id: str
    mode: str
    exit_status: str
    brief_path: str
    next_action: str
    resumed: bool
    reentry_conflicts: list[dict[str, Any]]
    stage_history: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "mode": self.mode,
            "exit_status": self.exit_status,
            "brief_path": self.brief_path,
            "next_action": self.next_action,
            "resumed": self.resumed,
            "reentry_conflicts": copy.deepcopy(self.reentry_conflicts),
            "stage_history": list(self.stage_history),
        }


CoreRunner = Callable[[p1.CoreLoopRequest], p1.CoreLoopOutput]


class FullCycleRunner:
    """Run one request to a legal terminal state and persist its Living Brief.

    FV-01 delegates deterministic routing, the core loop, and persistence to
    P0/P1/P2. P4/P5/P6 feature switches are retained in configuration but do
    not activate without later gate/adaptor modules.
    """

    def __init__(
        self,
        config: GovernorConfig,
        *,
        config_base_dir: str | Path | None = None,
        core_runner: CoreRunner | None = None,
        fault_injector: FaultInjector | None = None,
        checkpoint_store: CheckpointStore | None = None,
        budget_guard: BudgetGuard | None = None,
        pricing_path: str | Path | None = None,
    ) -> None:
        self.config = config
        self.config_base_dir = Path(config_base_dir or Path.cwd()).resolve()
        self.core_runner = core_runner
        self.fault_injector = fault_injector or FaultInjector.disabled()
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.budget_guard = budget_guard or BudgetGuard()
        self.pricing_path = Path(pricing_path or DEFAULT_PRICING_PATH).resolve()

    def run(
        self,
        request: FullCycleRequest | Mapping[str, Any],
        *,
        brief_path: str | Path | None = None,
    ) -> RunSummary:
        envelope = (
            request
            if isinstance(request, FullCycleRequest)
            else request_from_dict(request)
        )
        target_brief = self._resolve_brief_path(brief_path)

        routing_input = self._routing_input(envelope)
        initial_state = p0.new_state(routing_input, run_id=envelope.request_id)
        trace_sink = self.checkpoint_store.trace_sink or TraceSink(
            target_brief.with_name(f"{target_brief.name}.trace.json")
        )
        usage_ledger = self.checkpoint_store.usage_ledger or UsageLedger(
            PriceTable.load(self.pricing_path)
        )
        session = self.checkpoint_store.open(
            target_brief,
            initial_state,
            initial_next_stage=FaultStage.INITIALIZE,
            trace_sink=trace_sink,
            usage_ledger=usage_ledger,
        )
        resumed = not session.created
        conflicts = (
            p2.detect_reentry_conflicts(session.state, initial_state)
            if resumed
            else []
        )
        if resumed:
            session.mark_recovered()
            if (
                _is_budget_park(session.state)
                and self.config.runtime.budget.max_steps
                > session.state.run.budget.max_steps
            ):
                session.resume_park(
                    self.budget_guard,
                    self.config.runtime.budget.max_steps,
                )
        state = session.state

        if _is_terminal(state):
            return self._summary(
                state,
                target_brief,
                resumed=resumed,
                conflicts=conflicts,
                stage_history=[state.run.stage.value],
                next_action=session.brief.next_action,
            )

        if session.envelope.next_stage == FaultStage.INITIALIZE.value:
            completed = self._run_checkpoint_only_stage(
                session,
                FaultStage.INITIALIZE,
                FaultStage.ROUTE,
                context={"brief_path": str(target_brief)},
            )
            if not completed:
                return self._summary(
                    session.state,
                    target_brief,
                    resumed=resumed,
                    conflicts=conflicts,
                    stage_history=[FaultStage.INITIALIZE.value, p0.Stage.STOPPED.value],
                    next_action=session.brief.next_action,
                )

        route_completed_here = False
        if session.envelope.next_stage == FaultStage.ROUTE.value:
            route_completed_here = self._run_checkpoint_only_stage(
                session,
                FaultStage.ROUTE,
                FaultStage.CONTEXT,
                context={"created": session.created},
            )
            if not route_completed_here:
                return self._summary(
                    session.state,
                    target_brief,
                    resumed=resumed,
                    conflicts=conflicts,
                    stage_history=[FaultStage.ROUTE.value, p0.Stage.STOPPED.value],
                    next_action=session.brief.next_action,
                )
        elif session.envelope.next_stage not in {stage.value for stage in P1_STAGES}:
            raise p0.ContractError(
                "FullCycleRunner checkpoint does not match an enabled stage adapter"
            )

        core_payload = self._core_payload(envelope, session.state)
        core_request = p1.core_loop_request_from_dict(core_payload)
        if self.core_runner is None:
            durable = DurableStageRunner(
                P1StageProgram(core_request),
                checkpoint_store=self.checkpoint_store,
                fault_injector=self.fault_injector,
                budget_guard=self.budget_guard,
                stages=P1_STAGES,
            ).run_session(session, resumed=resumed)
            final_state = durable.state
            stage_history = (
                ([FaultStage.ROUTE.value] if route_completed_here else [])
                + durable.stage_history
                + ([p0.Stage.STOPPED.value] if _is_terminal(final_state) else [])
            )
        else:
            self.fault_injector.check(FaultStage.CONTEXT, FaultPoint.BEFORE_ENTER)
            session.enter_stage(FaultStage.CONTEXT, preserve_runtime_stage=True)
            self.fault_injector.check(
                FaultStage.CONTEXT,
                FaultPoint.AFTER_CHECKPOINT,
                context={"revision": session.envelope.revision},
            )
            try:
                session.consume_budget(
                    self.budget_guard,
                    FaultStage.CONTEXT,
                    "stage",
                    BudgetChargeKind.STAGE,
                )
                output = self.core_runner(core_request)
                p0.validate_state(output.state)
                completed_stage = _last_lifecycle_stage(output.stage_history)
                self.fault_injector.check(completed_stage, FaultPoint.BEFORE_COMMIT)
                session.commit_stage(
                    output.state,
                    completed_stage,
                    None,
                    terminal_exit=output.state.result.exit_status,
                    preserve_runtime_stage=True,
                    next_action=_next_action(output.state.result.exit_status),
                )
                stage_history = [item.value for item in output.stage_history]
            except Exception as error:
                exhausted = coerce_budget_exhausted(
                    error,
                    state=session.state,
                    stage=FaultStage.CONTEXT,
                )
                if exhausted is None:
                    raise
                session.park(exhausted)
                stage_history = [FaultStage.CONTEXT.value, p0.Stage.STOPPED.value]
            final_state = session.state

        p0.validate_state(final_state)
        if not _is_terminal(final_state):
            raise p0.ContractError("FullCycleRunner core returned a non-terminal state")
        if final_state.result.exit_status.value not in LEGAL_EXIT_STATUSES:
            raise p0.ContractError("FullCycleRunner core returned an illegal exit status")
        return self._summary(
            final_state,
            target_brief,
            resumed=resumed,
            conflicts=conflicts,
            stage_history=stage_history,
            next_action=session.brief.next_action,
        )

    def _run_checkpoint_only_stage(
        self,
        session: CheckpointSession,
        stage: FaultStage,
        next_stage: FaultStage,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> bool:
        self.fault_injector.check(
            stage,
            FaultPoint.BEFORE_ENTER,
            context={} if context is None else context,
        )
        session.enter_stage(stage)
        self.fault_injector.check(
            stage,
            FaultPoint.AFTER_CHECKPOINT,
            context={"revision": session.envelope.revision},
        )
        try:
            session.consume_budget(
                self.budget_guard,
                stage,
                "stage",
                BudgetChargeKind.STAGE,
            )
        except BudgetExhausted as exhausted:
            session.park(exhausted)
            return False
        self.fault_injector.check(stage, FaultPoint.BEFORE_COMMIT)
        session.commit_stage(session.state, stage, next_stage)
        return True

    def _routing_input(self, request: FullCycleRequest) -> p0.RoutingInput:
        routing = copy.deepcopy(request.routing)
        forbidden = {
            "current_mode",
            "research_allowed",
            "requested_parallelism",
            "budget",
        }
        overlap = forbidden & set(routing)
        if overlap:
            raise RequestError(
                f"request.routing fields are controlled by config or Brief: {sorted(overlap)}"
            )
        if self.config.runtime.mode != "auto":
            routing["explicit_mode"] = self.config.runtime.mode
        routing["research_allowed"] = self.config.features.research
        routing["requested_parallelism"] = self.config.runtime.parallelism
        routing["budget"] = {
            "max_steps": self.config.runtime.budget.max_steps,
            "used_steps": 0,
            "max_parallelism": self.config.runtime.budget.max_parallelism,
        }
        return p0.routing_input_from_dict(routing)

    def _core_payload(
        self, request: FullCycleRequest, state: p0.RuntimeState
    ) -> dict[str, Any]:
        payload = (
            _minimal_core_payload(request.text)
            if request.core is None
            else copy.deepcopy(request.core)
        )
        if "state" in payload:
            raise RequestError(
                "request.core.state is forbidden; Runner injects canonical state"
            )
        payload["state"] = p0.state_to_dict(state)
        return payload

    def _resolve_brief_path(self, override: str | Path | None) -> Path:
        if override is not None:
            target = Path(override)
            return (Path.cwd() / target).resolve() if not target.is_absolute() else target.resolve()
        target = Path(self.config.persistence.brief_path)
        if not target.is_absolute():
            target = self.config_base_dir / target
        return target.resolve()

    def _summary(
        self,
        state: p0.RuntimeState,
        brief_path: Path,
        *,
        resumed: bool,
        conflicts: list[p2.ReentryConflict],
        stage_history: list[str],
        next_action: str | None = None,
    ) -> RunSummary:
        if state.result.exit_status is None:
            raise p0.ContractError("terminal summary requires exit_status")
        return RunSummary(
            run_id=state.run.id,
            mode=state.run.mode.value,
            exit_status=state.result.exit_status.value,
            brief_path=str(brief_path),
            next_action=next_action or _next_action(state.result.exit_status),
            resumed=resumed,
            reentry_conflicts=[
                {
                    "field": item.field,
                    "persisted_value": _json_value(item.persisted_value),
                    "incoming_value": _json_value(item.incoming_value),
                    "reason": item.reason,
                }
                for item in conflicts
            ],
            stage_history=stage_history,
        )


def request_from_dict(value: Mapping[str, Any]) -> FullCycleRequest:
    if not isinstance(value, Mapping):
        raise RequestError("request must be an object")
    allowed = {"request_id", "text", "routing", "core"}
    unknown = set(value) - allowed
    if unknown:
        raise RequestError(f"request has unknown keys: {sorted(unknown)}")
    if "text" not in value:
        raise RequestError("request is missing key: text")
    text = value["text"]
    if not isinstance(text, str) or not text.strip():
        raise RequestError("request.text must be a non-empty string")
    request_id = value.get("request_id")
    if request_id is not None and (
        not isinstance(request_id, str) or not request_id.strip()
    ):
        raise RequestError("request.request_id must be null or a non-empty string")
    routing = value.get("routing", {})
    if not isinstance(routing, Mapping):
        raise RequestError("request.routing must be an object")
    core = value.get("core")
    if core is not None and not isinstance(core, Mapping):
        raise RequestError("request.core must be null or an object")
    return FullCycleRequest(
        text=text.strip(),
        request_id=request_id,
        routing=copy.deepcopy(dict(routing)),
        core=None if core is None else copy.deepcopy(dict(core)),
    )


def _minimal_core_payload(text: str) -> dict[str, Any]:
    known = lambda statement: {"statement": statement, "classification": "KNOWN"}
    unknown = lambda statement: {
        "statement": statement,
        "classification": "UNKNOWN",
    }
    return {
        "context": {
            "requested_outcome": known(text),
            "current_idea": None,
            "target_user": None,
            "constraints": [],
            "questions": [],
            "alternatives": [],
            "assets": [],
        },
        "problem_frame": {
            "problem_statement": known(text),
            "target_user": unknown("target user requires clarification"),
            "job_to_be_done": unknown("job to be done requires clarification"),
            "desired_change": unknown("desired change requires clarification"),
            "hard_constraints": [],
            "soft_preferences": [],
            "success_metric": unknown("success metric requires clarification"),
            "kill_criterion": unknown("kill criterion requires clarification"),
            "non_goals": [],
            "time_horizon": unknown("time horizon requires clarification"),
        },
        "candidates": [],
        "challenges": [],
        "assessments": [],
        "recommended_candidate_id": None,
        "confidence": None,
        "cheapest_test": None,
        "supplemental_candidates": [],
        "supplemental_rounds": 0,
    }


def _is_terminal(state: p0.RuntimeState) -> bool:
    return state.run.status in {p0.RunStatus.COMPLETED, p0.RunStatus.STOPPED}


def _is_budget_park(state: p0.RuntimeState) -> bool:
    return (
        state.run.status is p0.RunStatus.STOPPED
        and state.result.exit_status is p0.ExitStatus.PARK
    )


def _next_action(exit_status: p0.ExitStatus) -> str:
    return {
        p0.ExitStatus.EXPLORE: "choose or refine one viable direction",
        p0.ExitStatus.RESEARCH_REQUIRED: "authorize or provide required evidence",
        p0.ExitStatus.ITERATE: "repair constraints and generate another candidate set",
        p0.ExitStatus.COMMIT: "produce the restricted approved handoff",
        p0.ExitStatus.PARK: "resume from the Living Brief checkpoint",
        p0.ExitStatus.NEEDS_INPUT: "provide the missing Problem Frame information",
    }[exit_status]


def _json_value(value: Any) -> Any:
    return value.value if hasattr(value, "value") else copy.deepcopy(value)


def _last_lifecycle_stage(history: list[p0.Stage]) -> FaultStage:
    for stage in reversed(history):
        try:
            return FaultStage(stage.value)
        except ValueError:
            continue
    raise p0.ContractError("core stage history has no checkpointable lifecycle stage")
