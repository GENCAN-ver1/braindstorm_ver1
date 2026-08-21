"""Stable operation identities and recovery decisions for durable stages."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping


class RetryPolicy(str, Enum):
    RETRY = "RETRY"
    COLLECT = "COLLECT"
    PARK = "PARK"


class OperationStatus(str, Enum):
    STARTED = "STARTED"


class RecoveryAction(str, Enum):
    REUSE_RECEIPT = "REUSE_RECEIPT"
    RETRY = "RETRY"
    COLLECT = "COLLECT"
    PARK = "PARK"


@dataclass(frozen=True)
class InFlightOperation:
    operation_id: str
    stage: str
    idempotency_key: str
    status: OperationStatus
    retry_policy: RetryPolicy

    def to_dict(self) -> dict[str, str]:
        return {
            "operation_id": self.operation_id,
            "stage": self.stage,
            "idempotency_key": self.idempotency_key,
            "status": self.status.value,
            "retry_policy": self.retry_policy.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "InFlightOperation":
        expected = {
            "operation_id",
            "stage",
            "idempotency_key",
            "status",
            "retry_policy",
        }
        missing = expected - set(value)
        unknown = set(value) - expected
        if missing or unknown:
            raise ValueError(
                f"invalid in-flight operation keys; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        operation_id = _nonempty(value["operation_id"], "operation_id")
        stage = _nonempty(value["stage"], "stage")
        key = _nonempty(value["idempotency_key"], "idempotency_key")
        try:
            status = OperationStatus(value["status"])
            retry_policy = RetryPolicy(value["retry_policy"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid in-flight operation enum: {exc}") from exc
        return cls(operation_id, stage, key, status, retry_policy)


def stable_idempotency_key(run_id: str, stage: str, operation_id: str) -> str:
    identity = "\x1f".join(
        (
            _nonempty(run_id, "run_id"),
            _nonempty(stage, "stage"),
            _nonempty(operation_id, "operation_id"),
        )
    )
    return "idem:v1:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()


def recovery_action(
    operation: InFlightOperation,
    receipts: Mapping[str, Any],
) -> RecoveryAction:
    if operation.idempotency_key in receipts:
        return RecoveryAction.REUSE_RECEIPT
    return {
        RetryPolicy.RETRY: RecoveryAction.RETRY,
        RetryPolicy.COLLECT: RecoveryAction.COLLECT,
        RetryPolicy.PARK: RecoveryAction.PARK,
    }[operation.retry_policy]


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path} must be a non-empty string")
    return value

