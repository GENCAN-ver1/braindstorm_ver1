"""Global, provider-neutral step budget guard for lifecycle work."""

from __future__ import annotations

from enum import Enum

from runtime.fault_injection import Stage
from runtime.governor_modules import p0
from runtime.idempotency import stable_idempotency_key
from runtime.lifecycle_errors import BudgetExhausted, LifecycleError


class BudgetChargeKind(str, Enum):
    STAGE = "STAGE"
    EXTERNAL = "EXTERNAL"


class BudgetIncreaseError(LifecycleError):
    """Raised when a PARK resume does not explicitly increase the limit."""


class BudgetGuard:
    """Reserve deterministic step charges before stage or external work."""

    def __init__(self, *, step_cost: int = 1) -> None:
        if type(step_cost) is not int or step_cost < 1:
            raise ValueError("step_cost must be an integer >= 1")
        self.step_cost = step_cost

    def charge_key(
        self,
        state: p0.RuntimeState,
        stage: Stage,
        operation_id: str,
        kind: BudgetChargeKind,
    ) -> str:
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise ValueError("operation_id must be a non-empty string")
        return stable_idempotency_key(
            state.run.id,
            stage.value,
            f"budget:{kind.value}:{operation_id.strip()}",
        )

    def consume(
        self,
        state: p0.RuntimeState,
        stage: Stage,
        operation_id: str,
        kind: BudgetChargeKind,
    ) -> None:
        p0.validate_state(state)
        budget = state.run.budget
        if budget.used_steps + self.step_cost > budget.max_steps:
            raise BudgetExhausted(
                stage=stage,
                operation_id=operation_id,
                charge_kind=kind.value,
                used_steps=budget.used_steps,
                max_steps=budget.max_steps,
                required_steps=self.step_cost,
            )
        budget.used_steps += self.step_cost
        p0.validate_state(state)

    def increase_limit(self, state: p0.RuntimeState, new_max_steps: int) -> None:
        if type(new_max_steps) is not int:
            raise BudgetIncreaseError("new_max_steps must be an integer")
        current = state.run.budget.max_steps
        if new_max_steps <= current:
            raise BudgetIncreaseError(
                f"budget resume requires an explicit increase above {current}"
            )
        if new_max_steps < state.run.budget.used_steps:
            raise BudgetIncreaseError("new budget cannot be below used_steps")
        state.run.budget.max_steps = new_max_steps
        p0.validate_state(state)

