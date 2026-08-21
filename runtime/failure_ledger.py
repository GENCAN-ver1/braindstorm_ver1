"""Append-only operational failures for isolated external work."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Sequence

from runtime.fault_injection import Stage


FAILURE_SCHEMA_VERSION = 1


class FailureCategory(str, Enum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    PROVIDER_5XX = "PROVIDER_5XX"
    INVALID_JSON = "INVALID_JSON"
    CITATION_ERROR = "CITATION_ERROR"
    DUPLICATE_CANDIDATE = "DUPLICATE_CANDIDATE"
    SCHEMA_ERROR = "SCHEMA_ERROR"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    WORKER_ERROR = "WORKER_ERROR"
    RESEARCH_DISABLED = "RESEARCH_DISABLED"


RETRYABLE_CATEGORIES = {
    FailureCategory.TIMEOUT,
    FailureCategory.RATE_LIMIT,
    FailureCategory.PROVIDER_5XX,
    FailureCategory.PROVIDER_ERROR,
    FailureCategory.WORKER_ERROR,
}


class FailureLedgerError(ValueError):
    """Raised when failure metadata is invalid or would be overwritten."""


@dataclass(frozen=True)
class FailureEntry:
    schema_version: int
    failure_id: str
    run_id: str
    stage: str
    operation_id: str
    provider: str
    category: FailureCategory
    message: str
    retryable: bool
    idempotency_key: str

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        stage: Stage,
        operation_id: str,
        provider: str,
        category: FailureCategory,
        message: str,
        idempotency_key: str,
        retryable: bool | None = None,
    ) -> "FailureEntry":
        normalized = {
            "run_id": _nonempty(run_id, "run_id"),
            "stage": stage.value,
            "operation_id": _nonempty(operation_id, "operation_id"),
            "provider": _nonempty(provider, "provider"),
            "category": category.value,
            "message": sanitize_message(message),
            "idempotency_key": _nonempty(idempotency_key, "idempotency_key"),
        }
        digest = hashlib.sha256(
            json.dumps(
                normalized,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        entry = cls(
            schema_version=FAILURE_SCHEMA_VERSION,
            failure_id=f"failure:v1:{digest}",
            run_id=normalized["run_id"],
            stage=normalized["stage"],
            operation_id=normalized["operation_id"],
            provider=normalized["provider"],
            category=category,
            message=normalized["message"],
            retryable=(
                category in RETRYABLE_CATEGORIES
                if retryable is None
                else retryable
            ),
            idempotency_key=normalized["idempotency_key"],
        )
        validate_failure_entry(entry)
        return entry

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "failure_id": self.failure_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "operation_id": self.operation_id,
            "provider": self.provider,
            "category": self.category.value,
            "message": self.message,
            "retryable": self.retryable,
            "idempotency_key": self.idempotency_key,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "FailureEntry":
        expected = {
            "schema_version",
            "failure_id",
            "run_id",
            "stage",
            "operation_id",
            "provider",
            "category",
            "message",
            "retryable",
            "idempotency_key",
        }
        missing = expected - set(value)
        unknown = set(value) - expected
        if missing or unknown:
            raise FailureLedgerError(
                f"invalid failure keys; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        try:
            category = FailureCategory(value["category"])
        except (TypeError, ValueError) as exc:
            raise FailureLedgerError("failure category is invalid") from exc
        entry = cls(
            schema_version=value["schema_version"],
            failure_id=value["failure_id"],
            run_id=value["run_id"],
            stage=value["stage"],
            operation_id=value["operation_id"],
            provider=value["provider"],
            category=category,
            message=value["message"],
            retryable=value["retryable"],
            idempotency_key=value["idempotency_key"],
        )
        validate_failure_entry(entry)
        return entry


class FailureLedger:
    """Validated append-only collection with idempotent failure IDs."""

    def __init__(self, entries: Sequence[FailureEntry] = ()) -> None:
        self._entries: list[FailureEntry] = []
        for entry in entries:
            self.append(entry)

    @classmethod
    def from_records(cls, records: Sequence[Mapping[str, Any]]) -> "FailureLedger":
        if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
            raise FailureLedgerError("failure ledger must be a sequence")
        return cls([FailureEntry.from_dict(item) for item in records])

    @property
    def entries(self) -> tuple[FailureEntry, ...]:
        return tuple(copy.deepcopy(self._entries))

    def append(self, entry: FailureEntry) -> bool:
        validate_failure_entry(entry)
        for existing in self._entries:
            if existing.failure_id != entry.failure_id:
                continue
            if existing != entry:
                raise FailureLedgerError("failure_id cannot be overwritten")
            return False
        self._entries.append(copy.deepcopy(entry))
        return True

    def to_records(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self._entries]


def validate_failure_entry(entry: FailureEntry) -> None:
    if not isinstance(entry, FailureEntry):
        raise FailureLedgerError("entry must be FailureEntry")
    if entry.schema_version != FAILURE_SCHEMA_VERSION:
        raise FailureLedgerError("unsupported failure schema_version")
    for name in (
        "failure_id",
        "run_id",
        "stage",
        "operation_id",
        "provider",
        "message",
        "idempotency_key",
    ):
        _nonempty(getattr(entry, name), name)
    if not entry.failure_id.startswith("failure:v1:"):
        raise FailureLedgerError("failure_id must use failure:v1 format")
    try:
        Stage(entry.stage)
    except (TypeError, ValueError) as exc:
        raise FailureLedgerError("failure stage is invalid") from exc
    if not isinstance(entry.category, FailureCategory):
        raise FailureLedgerError("failure category is invalid")
    if type(entry.retryable) is not bool:
        raise FailureLedgerError("failure retryable must be boolean")


def classify_exception(
    error: Exception,
    *,
    default: FailureCategory,
) -> FailureCategory:
    name = type(error).__name__.casefold()
    message = str(error).casefold()
    status = getattr(error, "status_code", None)
    if (
        isinstance(error, TimeoutError)
        or "timeout" in name
        or "timeout" in message
        or "timed out" in message
    ):
        return FailureCategory.TIMEOUT
    if status == 429 or "ratelimit" in name or "rate limit" in message or " 429" in message:
        return FailureCategory.RATE_LIMIT
    if isinstance(status, int) and 500 <= status <= 599:
        return FailureCategory.PROVIDER_5XX
    if (
        "jsondecode" in name
        or "invalid json" in message
        or "malformed json" in message
        or "expecting value" in message
        or "expecting property name" in message
    ):
        return FailureCategory.INVALID_JSON
    if "citationsupport" in name or (
        "citation" in message and ("support" in message or "source" in message)
    ):
        return FailureCategory.CITATION_ERROR
    if "duplicate" in message and "candidate" in message:
        return FailureCategory.DUPLICATE_CANDIDATE
    if "conflict" in message or "contradict" in message:
        return FailureCategory.SOURCE_CONFLICT
    if "schema" in message or "wrong output type" in message:
        return FailureCategory.SCHEMA_ERROR
    if " 5" in message and "provider" in message:
        return FailureCategory.PROVIDER_5XX
    return default


def sanitize_message(value: Any) -> str:
    if not isinstance(value, str):
        value = str(value)
    normalized = " ".join(value.split()).strip()
    if not normalized:
        normalized = "unspecified operational failure"
    return normalized[:512]


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FailureLedgerError(f"{path} must be a non-empty string")
    return value.strip()
