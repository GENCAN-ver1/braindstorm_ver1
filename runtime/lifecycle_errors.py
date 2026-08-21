"""Domain errors owned by the full-cycle lifecycle runner."""

from __future__ import annotations

from runtime.fault_injection import Stage
from runtime.governor_modules import p0


class LifecycleError(p0.ContractError):
    """Base class for lifecycle events that require runner-level handling."""


class BudgetExhausted(LifecycleError):
    """Raised before work when the next budget charge cannot be reserved."""

    def __init__(
        self,
        *,
        stage: Stage,
        operation_id: str,
        charge_kind: str,
        used_steps: int,
        max_steps: int,
        required_steps: int = 1,
    ) -> None:
        self.stage = stage
        self.operation_id = operation_id
        self.charge_kind = charge_kind
        self.used_steps = used_steps
        self.max_steps = max_steps
        self.required_steps = required_steps
        super().__init__(
            f"budget exhausted before {charge_kind.casefold()} {operation_id!r} "
            f"at {stage.value}: used={used_steps}, max={max_steps}, "
            f"required={required_steps}"
        )

    @property
    def next_action(self) -> str:
        if self.charge_kind == "EXTERNAL":
            detail = f"external operation {self.operation_id}"
        else:
            detail = f"stage {self.stage.value}"
        return (
            f"increase budget above {self.max_steps} and resume {detail} "
            f"at {self.stage.value}"
        )


def coerce_budget_exhausted(
    error: Exception,
    *,
    state: p0.RuntimeState,
    stage: Stage,
    operation_id: str = "legacy-stage-work",
) -> BudgetExhausted | None:
    """Translate legacy P0-P5 budget validation failures into one domain event."""
    if isinstance(error, BudgetExhausted):
        return error
    if not isinstance(error, p0.StateValidationError):
        return None
    messages = [str(item).casefold() for item in error.errors]
    if not any("budget" in item and "exhaust" in item for item in messages):
        return None
    budget = state.run.budget
    return BudgetExhausted(
        stage=stage,
        operation_id=operation_id,
        charge_kind="STAGE",
        used_steps=budget.used_steps,
        max_steps=budget.max_steps,
    )

