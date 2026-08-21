"""FV-05 traced P6 Evaluator wrapper over the durable external boundary."""

from __future__ import annotations

import copy
from typing import Any, Mapping

from observability.events import ActivationKind
from observability.usage_ledger import ObservedExternalResult
from runtime.evaluator_guard import (
    MAX_EVALUATOR_ROUNDS,
    EvaluatorGuard,
    EvaluatorRoundLimitReached,
)
from runtime.governor_modules import p0, p6
from runtime.idempotency import RetryPolicy
from runtime.reentry import StageContext


class EvaluatorRuntimeError(p0.ContractError):
    """Raised when a durable evaluator receipt violates the P6 contract."""


class TracedEvaluator:
    """Adapt a P6 Evaluator so activation and provider usage are automatic."""

    def __init__(
        self,
        evaluator: p6.Evaluator,
        context: StageContext,
        *,
        provider_name: str = "evaluator-provider",
        model_name: str = "UNSPECIFIED",
        max_rounds: int = MAX_EVALUATOR_ROUNDS,
    ) -> None:
        if not hasattr(evaluator, "evaluate"):
            raise EvaluatorRuntimeError("evaluator must implement evaluate")
        self.evaluator = evaluator
        self.context = context
        self.provider_name = _nonempty(provider_name, "provider_name")
        self.model_name = _nonempty(model_name, "model_name")
        self.guard = EvaluatorGuard(context.session, max_rounds=max_rounds)

    def evaluate(self, request: p6.EvaluatorInput) -> p6.EvaluatorInvocation:
        try:
            reservation = self.guard.reserve_next()
        except EvaluatorRoundLimitReached:
            self.context.record_gate_decision(
                "evaluation", False, "P6 evaluator hard cap reached"
            )
            raise
        self.context.record_gate_decision(
            "evaluation",
            True,
            f"P6 requested evaluator round {reservation.round_number}",
        )
        value = self.context.run_external(
            reservation.operation_id,
            lambda key: _observed_invocation(
                self.evaluator.evaluate(copy.deepcopy(request))
            ),
            retry_policy=RetryPolicy.RETRY,
            provider=self.provider_name,
            model=self.model_name,
            activation=ActivationKind.P6_EVALUATOR,
        )
        self.guard.mark_consumed(reservation)
        return evaluator_invocation_from_value(value)


def evaluator_invocation_to_dict(
    invocation: p6.EvaluatorInvocation,
) -> dict[str, Any]:
    if not isinstance(invocation, p6.EvaluatorInvocation):
        raise EvaluatorRuntimeError("evaluator must return EvaluatorInvocation")
    p6.validate_evaluation_report(invocation.report)
    return {
        "report": {
            "corrections": [
                p6._json_ready(item) for item in invocation.report.corrections
            ]
        },
        "runtime_usage": {
            "token_usage": invocation.usage.token_usage,
            "tool_usage": invocation.usage.tool_usage,
        },
    }


def evaluator_invocation_from_value(value: Any) -> p6.EvaluatorInvocation:
    if isinstance(value, p6.EvaluatorInvocation):
        return copy.deepcopy(value)
    if not isinstance(value, Mapping) or set(value) != {"report", "runtime_usage"}:
        raise EvaluatorRuntimeError("evaluator receipt has invalid keys")
    report = value["report"]
    usage = value["runtime_usage"]
    if not isinstance(report, Mapping) or set(report) != {"corrections"}:
        raise EvaluatorRuntimeError("evaluator report has invalid keys")
    if not isinstance(usage, Mapping) or set(usage) != {"token_usage", "tool_usage"}:
        raise EvaluatorRuntimeError("evaluator runtime_usage has invalid keys")
    corrections_value = report["corrections"]
    if not isinstance(corrections_value, list):
        raise EvaluatorRuntimeError("evaluator corrections must be an array")
    corrections: list[p6.ActionableCorrection] = []
    expected = {
        "id",
        "check",
        "target",
        "issue",
        "required_change",
        "severity",
        "high_impact",
        "wording_only",
        "requires_external_information",
        "requires_user_information",
    }
    for item in corrections_value:
        if not isinstance(item, Mapping) or set(item) != expected:
            raise EvaluatorRuntimeError("evaluator correction has invalid keys")
        try:
            correction = p6.ActionableCorrection(
                id=item["id"],
                check=p6.EvaluationCheck(item["check"]),
                target=item["target"],
                issue=item["issue"],
                required_change=item["required_change"],
                severity=p6.CorrectionSeverity(item["severity"]),
                high_impact=item["high_impact"],
                wording_only=item["wording_only"],
                requires_external_information=item[
                    "requires_external_information"
                ],
                requires_user_information=item["requires_user_information"],
            )
        except (TypeError, ValueError) as exc:
            raise EvaluatorRuntimeError("evaluator correction enum is invalid") from exc
        p6._validate_correction(correction, "correction")
        corrections.append(correction)
    invocation = p6.EvaluatorInvocation(
        p6.EvaluationReport(corrections),
        p6.RuntimeUsage(
            token_usage=usage["token_usage"],
            tool_usage=usage["tool_usage"],
        ),
    )
    p6._validate_invocation(invocation)
    return invocation


def _observed_invocation(value: Any) -> Any:
    if isinstance(value, ObservedExternalResult):
        return ObservedExternalResult(
            evaluator_invocation_to_dict(value.payload), value.usage
        )
    return evaluator_invocation_to_dict(value)


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvaluatorRuntimeError(f"{path} must be a non-empty string")
    return value.strip()
