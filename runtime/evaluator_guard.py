"""Durable, idempotent hard cap for P6 evaluator provider calls."""

from __future__ import annotations

from dataclasses import dataclass

from runtime.checkpoint import CheckpointError, CheckpointSession
from runtime.governor_modules import p0


MAX_EVALUATOR_ROUNDS = 2


class EvaluatorGuardError(p0.ContractError):
    """Base error for invalid durable evaluator operations."""


class EvaluatorRoundLimitReached(EvaluatorGuardError):
    """Raised before provider execution when both rounds are reserved."""


@dataclass(frozen=True)
class EvaluatorRoundReservation:
    operation_id: str
    round_number: int
    reused: bool


class EvaluatorGuard:
    """Own evaluator round identity and count across Brief-first recovery."""

    def __init__(
        self,
        session: CheckpointSession,
        *,
        max_rounds: int = MAX_EVALUATOR_ROUNDS,
    ) -> None:
        if not isinstance(session, CheckpointSession):
            raise EvaluatorGuardError("session must be CheckpointSession")
        if type(max_rounds) is not int or not 1 <= max_rounds <= MAX_EVALUATOR_ROUNDS:
            raise EvaluatorGuardError("max_rounds must be between 1 and 2")
        self.session = session
        self.max_rounds = max_rounds

    @property
    def rounds_used(self) -> int:
        return self.session.envelope.evaluator_rounds_used

    @property
    def remaining_rounds(self) -> int:
        return max(0, self.max_rounds - self.rounds_used)

    def reserve_next(self) -> EvaluatorRoundReservation:
        """Reserve or recover the next logical evaluator request."""
        request_keys = self.session.envelope.evaluator_request_keys
        consumed = set(self.session.envelope.evaluator_consumed_keys)
        for index, key in enumerate(request_keys, start=1):
            if key not in consumed:
                operation_id = f"evaluator:{index}"
                try:
                    round_number = self.session.reserve_evaluator_round(
                        operation_id, max_rounds=self.max_rounds
                    )
                except CheckpointError as exc:
                    raise EvaluatorGuardError(str(exc)) from exc
                if round_number is None:
                    raise EvaluatorRoundLimitReached(
                        "evaluator round cap reached before provider call"
                    )
                return EvaluatorRoundReservation(
                    operation_id, round_number, reused=True
                )

        if self.rounds_used >= self.max_rounds:
            raise EvaluatorRoundLimitReached(
                "evaluator round cap reached before provider call"
            )
        operation_id = f"evaluator:{self.rounds_used + 1}"
        try:
            round_number = self.session.reserve_evaluator_round(
                operation_id, max_rounds=self.max_rounds
            )
        except CheckpointError as exc:
            raise EvaluatorGuardError(str(exc)) from exc
        if round_number is None:
            raise EvaluatorRoundLimitReached(
                "evaluator round cap reached before provider call"
            )
        return EvaluatorRoundReservation(operation_id, round_number, reused=False)

    def mark_consumed(self, reservation: EvaluatorRoundReservation) -> bool:
        if not isinstance(reservation, EvaluatorRoundReservation):
            raise EvaluatorGuardError(
                "reservation must be EvaluatorRoundReservation"
            )
        try:
            return self.session.mark_evaluator_result_consumed(
                reservation.operation_id
            )
        except CheckpointError as exc:
            raise EvaluatorGuardError(str(exc)) from exc


__all__ = [
    "MAX_EVALUATOR_ROUNDS",
    "EvaluatorGuard",
    "EvaluatorGuardError",
    "EvaluatorRoundLimitReached",
    "EvaluatorRoundReservation",
]
