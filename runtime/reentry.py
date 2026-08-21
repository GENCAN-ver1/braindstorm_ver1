"""Stage-level durable execution and Brief-first recovery planning."""

from __future__ import annotations

import copy
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from observability.events import ActivationKind
from observability.usage_ledger import (
    ObservedExternalError,
    ObservedExternalResult,
    ProviderUsage,
)
from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.checkpoint import CheckpointEnvelope, CheckpointSession, CheckpointStore
from runtime.failure_ledger import FailureLedger
from runtime.fault_injection import FaultInjector, FaultPoint, Stage
from runtime.governor_modules import p0
from runtime.idempotency import (
    RecoveryAction,
    RetryPolicy,
    recovery_action,
    stable_idempotency_key,
)
from runtime.lifecycle_errors import coerce_budget_exhausted


STAGE_SEQUENCE = tuple(Stage)


class RecoveryBlocked(p0.ContractError):
    """Raised when an in-flight operation cannot be retried safely."""


class StageHandler(Protocol):
    def __call__(
        self,
        stage: Stage,
        state: p0.RuntimeState,
        context: "StageContext",
    ) -> p0.RuntimeState | "StageOutcome": ...


ExternalCall = Callable[[str], Any]


@dataclass(frozen=True)
class RecoveryPlan:
    next_stage: Stage | None
    external_action: RecoveryAction | None
    idempotency_key: str | None


@dataclass(frozen=True)
class DurableRunResult:
    state: p0.RuntimeState
    envelope: CheckpointEnvelope
    stage_history: list[str]
    resumed: bool


@dataclass(frozen=True)
class StageOutcome:
    state: p0.RuntimeState
    terminal_exit: p0.ExitStatus | None = None
    next_action: str | None = None


class StageContext:
    def __init__(
        self,
        session: CheckpointSession,
        stage: Stage,
        fault_injector: FaultInjector,
        budget_guard: BudgetGuard,
    ) -> None:
        self.session = session
        self.stage = stage
        self.fault_injector = fault_injector
        self.budget_guard = budget_guard

    def run_external(
        self,
        operation_id: str,
        call: ExternalCall,
        *,
        retry_policy: RetryPolicy = RetryPolicy.RETRY,
        provider: str | None = None,
        model: str | None = None,
        activation: ActivationKind | None = None,
    ) -> Any:
        key = stable_idempotency_key(
            self.session.state.run.id, self.stage.value, operation_id
        )
        receipts = self.session.envelope.operation_receipts
        if key in receipts:
            return copy.deepcopy(receipts[key])

        if activation is not None:
            self.session.record_activation(self.stage, activation)

        operation = self.session.envelope.in_flight_operation
        if operation is not None:
            if operation.idempotency_key != key:
                raise RecoveryBlocked(
                    "another external operation is already in flight for this stage"
                )
            action = recovery_action(operation, receipts)
            if action is RecoveryAction.COLLECT:
                raise RecoveryBlocked(
                    f"operation {operation_id!r} requires provider-side collection"
                )
            if action is RecoveryAction.PARK:
                raise RecoveryBlocked(
                    f"operation {operation_id!r} is not safe to retry automatically"
                )
        else:
            retry = any(
                item.operation_id == operation_id
                for item in FailureLedger.from_records(
                    self.session.envelope.failure_ledger
                ).entries
            )
            prepared_key = self.session.prepare_external(
                self.stage,
                operation_id,
                retry_policy,
                provider=provider,
                model=model,
                retry=retry,
            )
            if prepared_key != key:
                raise RecoveryBlocked("prepared idempotency key is inconsistent")

        self.session.consume_budget(
            self.budget_guard,
            self.stage,
            operation_id,
            BudgetChargeKind.EXTERNAL,
        )

        self.fault_injector.check(
            self.stage,
            FaultPoint.BEFORE_EXTERNAL_CALL,
            context={"operation_id": operation_id, "idempotency_key": key},
        )
        started = time.perf_counter()
        try:
            observed = call(key)
        except Exception as error:
            latency_ms = round((time.perf_counter() - started) * 1000, 3)
            usage = (
                error.usage
                if isinstance(error, ObservedExternalError)
                else ProviderUsage.unavailable(
                    f"local:{uuid.uuid4().hex}", latency_ms=latency_ms
                )
            )
            usage_receipt = self._usage_receipt(provider, model, usage)
            self.session.abort_external(
                key,
                provider=provider,
                model=model,
                error_type=type(error).__name__,
                usage_receipt=usage_receipt,
            )
            raise
        latency_ms = round((time.perf_counter() - started) * 1000, 3)
        if isinstance(observed, ObservedExternalResult):
            receipt = observed.payload
            usage = observed.usage
        else:
            receipt = observed
            usage = ProviderUsage.unavailable(
                f"local:{uuid.uuid4().hex}", latency_ms=latency_ms
            )
        usage_receipt = self._usage_receipt(provider, model, usage)
        self.session.complete_external(
            key,
            receipt,
            provider=provider,
            model=model,
            usage_receipt=usage_receipt,
        )
        self.fault_injector.check(
            self.stage,
            FaultPoint.AFTER_EXTERNAL_CALL,
            context={"operation_id": operation_id, "idempotency_key": key},
        )
        return copy.deepcopy(receipt)

    def record_gate_decision(
        self, gate: str, enabled: bool, reason: str
    ) -> bool:
        return self.session.record_gate_decision(
            self.stage, gate, enabled, reason
        )

    def _usage_receipt(
        self,
        provider: str | None,
        model: str | None,
        usage: ProviderUsage,
    ):
        ledger = self.session.usage_ledger
        if ledger is None:
            return None
        return ledger.create_receipt(
            run_id=self.session.state.run.id,
            stage=self.stage.value,
            provider=provider or "UNSPECIFIED",
            model=model or "UNSPECIFIED",
            usage=usage,
        )


class DurableStageRunner:
    """Execute the complete lifecycle with a checkpoint before every stage."""

    def __init__(
        self,
        handler: StageHandler,
        *,
        checkpoint_store: CheckpointStore | None = None,
        fault_injector: FaultInjector | None = None,
        budget_guard: BudgetGuard | None = None,
        stages: tuple[Stage, ...] = STAGE_SEQUENCE,
    ) -> None:
        if not stages or len(set(stages)) != len(stages):
            raise ValueError("stages must be unique and non-empty")
        self.handler = handler
        self.checkpoint_store = checkpoint_store or CheckpointStore()
        self.fault_injector = fault_injector or FaultInjector.disabled()
        self.budget_guard = budget_guard or BudgetGuard()
        self.stages = stages

    def run(self, brief_path: str, initial_state: p0.RuntimeState) -> DurableRunResult:
        session = self.checkpoint_store.open(
            brief_path,
            initial_state,
            initial_next_stage=self.stages[0],
        )
        resumed = not session.created
        return self.run_session(session, resumed=resumed, record_recovery=resumed)

    def run_session(
        self,
        session: CheckpointSession,
        *,
        resumed: bool,
        record_recovery: bool = False,
    ) -> DurableRunResult:
        plan = recovery_plan(session.envelope)
        if record_recovery:
            session.mark_recovered()
            plan = recovery_plan(session.envelope)
        if _terminal(session.state):
            return DurableRunResult(
                copy.deepcopy(session.state),
                session.envelope,
                [],
                resumed,
            )
        if plan.next_stage is None:
            return DurableRunResult(
                copy.deepcopy(session.state),
                session.envelope,
                [],
                resumed,
            )
        if plan.external_action is RecoveryAction.COLLECT:
            raise RecoveryBlocked(
                "checkpoint requires provider-side collection before stage recovery"
            )
        if plan.external_action is RecoveryAction.PARK:
            raise RecoveryBlocked(
                "checkpointed external operation is not safe to retry automatically"
            )
        try:
            start_index = self.stages.index(plan.next_stage)
        except ValueError as exc:
            raise RecoveryBlocked(
                f"checkpoint next stage {plan.next_stage.value} is not in this runner"
            ) from exc

        history: list[str] = []
        for index in range(start_index, len(self.stages)):
            stage = self.stages[index]
            self.fault_injector.check(stage, FaultPoint.BEFORE_ENTER)
            session.enter_stage(stage)
            self.fault_injector.check(
                stage,
                FaultPoint.AFTER_CHECKPOINT,
                context={"revision": session.envelope.revision},
            )
            working = copy.deepcopy(session.state)
            try:
                session.consume_budget(
                    self.budget_guard,
                    stage,
                    "stage",
                    BudgetChargeKind.STAGE,
                )
                working = copy.deepcopy(session.state)
                context = StageContext(
                    session, stage, self.fault_injector, self.budget_guard
                )
                handled = self.handler(stage, working, context)
                outcome = (
                    handled
                    if isinstance(handled, StageOutcome)
                    else StageOutcome(handled)
                )
                result_state = outcome.state
                # External charges are persisted through the session while the
                # handler works on a copy. Never let that copy roll counters back.
                result_state.run.budget.used_steps = max(
                    result_state.run.budget.used_steps,
                    session.state.run.budget.used_steps,
                )
                p0.validate_state(result_state)
                self.fault_injector.check(stage, FaultPoint.BEFORE_COMMIT)
            except Exception as error:
                exhausted = coerce_budget_exhausted(
                    error,
                    state=working,
                    stage=stage,
                )
                if exhausted is None:
                    raise
                session.park(exhausted)
                history.append(stage.value)
                break

            next_stage = None if outcome.terminal_exit is not None else (
                None if index + 1 == len(self.stages) else self.stages[index + 1]
            )
            terminal_exit = outcome.terminal_exit or (
                p0.ExitStatus.COMMIT if next_stage is None else None
            )
            session.commit_stage(
                result_state,
                stage,
                next_stage,
                terminal_exit=terminal_exit,
                next_action=outcome.next_action,
            )
            history.append(stage.value)
            if outcome.terminal_exit is not None:
                break

        return DurableRunResult(
            copy.deepcopy(session.state),
            session.envelope,
            history,
            resumed,
        )


def recovery_plan(envelope: CheckpointEnvelope) -> RecoveryPlan:
    next_stage = None if envelope.next_stage is None else Stage(envelope.next_stage)
    operation = envelope.in_flight_operation
    return RecoveryPlan(
        next_stage=next_stage,
        external_action=(
            None
            if operation is None
            else recovery_action(operation, envelope.operation_receipts)
        ),
        idempotency_key=(
            envelope.idempotency_key if operation is not None else None
        ),
    )


def _terminal(state: p0.RuntimeState) -> bool:
    return state.run.status in {p0.RunStatus.COMPLETED, p0.RunStatus.STOPPED}
