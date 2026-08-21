"""Strict event records for the FV-05 append-only trace."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping


TRACE_EVENT_SCHEMA_VERSION = 1


class EventValidationError(ValueError):
    """Raised when a trace event violates the durable event contract."""


class EventKind(str, Enum):
    STAGE_TRANSITION = "STAGE_TRANSITION"
    GATE_DECISION = "GATE_DECISION"
    ACTIVATION = "ACTIVATION"
    EXTERNAL_CALL_STARTED = "EXTERNAL_CALL_STARTED"
    EXTERNAL_CALL_RETRY = "EXTERNAL_CALL_RETRY"
    EXTERNAL_CALL_SUCCEEDED = "EXTERNAL_CALL_SUCCEEDED"
    EXTERNAL_CALL_FAILED = "EXTERNAL_CALL_FAILED"
    FAILURE_RECORDED = "FAILURE_RECORDED"
    CHECKPOINT_SAVED = "CHECKPOINT_SAVED"
    RECOVERY = "RECOVERY"
    EXIT_STATUS = "EXIT_STATUS"


class ActivationKind(str, Enum):
    P4_RESEARCH = "P4_RESEARCH"
    P5_WORKER = "P5_WORKER"
    P6_EVALUATOR = "P6_EVALUATOR"
    COUNCIL = "COUNCIL"


@dataclass(frozen=True)
class EventSpec:
    kind: EventKind
    stage: str
    operation_id: str | None = None
    provider: str | None = None
    model: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _nonempty(self.stage, "stage")
        _optional_nonempty(self.operation_id, "operation_id")
        _optional_nonempty(self.provider, "provider")
        _optional_nonempty(self.model, "model")
        _json_object(self.details, "details")


@dataclass(frozen=True)
class TraceEvent:
    schema_version: int
    event_id: str
    run_id: str
    revision: int
    trace_cursor: int
    kind: EventKind
    stage: str
    timestamp: str
    operation_id: str | None
    provider: str | None
    model: str | None
    details: dict[str, Any]

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        revision: int,
        trace_cursor: int,
        spec: EventSpec,
    ) -> "TraceEvent":
        _nonempty(run_id, "run_id")
        _nonnegative_int(revision, "revision")
        if type(trace_cursor) is not int or trace_cursor < 1:
            raise EventValidationError("trace_cursor must be an integer >= 1")
        identity = {
            "run_id": run_id,
            "revision": revision,
            "trace_cursor": trace_cursor,
            "kind": spec.kind.value,
            "stage": spec.stage,
            "operation_id": spec.operation_id,
            "provider": spec.provider,
            "model": spec.model,
            "details": copy.deepcopy(spec.details),
        }
        digest = hashlib.sha256(
            json.dumps(
                identity,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ).hexdigest()
        return cls(
            schema_version=TRACE_EVENT_SCHEMA_VERSION,
            event_id=f"trace:v1:sha256:{digest}",
            run_id=run_id,
            revision=revision,
            trace_cursor=trace_cursor,
            kind=spec.kind,
            stage=spec.stage,
            timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            operation_id=spec.operation_id,
            provider=spec.provider,
            model=spec.model,
            details=copy.deepcopy(spec.details),
        )

    def to_dict(self) -> dict[str, Any]:
        validate_event(self)
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "run_id": self.run_id,
            "revision": self.revision,
            "trace_cursor": self.trace_cursor,
            "kind": self.kind.value,
            "stage": self.stage,
            "timestamp": self.timestamp,
            "operation_id": self.operation_id,
            "provider": self.provider,
            "model": self.model,
            "details": copy.deepcopy(self.details),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "TraceEvent":
        expected = {
            "schema_version",
            "event_id",
            "run_id",
            "revision",
            "trace_cursor",
            "kind",
            "stage",
            "timestamp",
            "operation_id",
            "provider",
            "model",
            "details",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise EventValidationError("trace event has invalid keys")
        try:
            kind = EventKind(value["kind"])
        except (TypeError, ValueError) as exc:
            raise EventValidationError("trace event kind is invalid") from exc
        event = cls(
            schema_version=value["schema_version"],
            event_id=value["event_id"],
            run_id=value["run_id"],
            revision=value["revision"],
            trace_cursor=value["trace_cursor"],
            kind=kind,
            stage=value["stage"],
            timestamp=value["timestamp"],
            operation_id=value["operation_id"],
            provider=value["provider"],
            model=value["model"],
            details=copy.deepcopy(dict(value["details"])),
        )
        validate_event(event)
        return event


def validate_event(event: TraceEvent) -> None:
    if not isinstance(event, TraceEvent):
        raise EventValidationError("event must be TraceEvent")
    if event.schema_version != TRACE_EVENT_SCHEMA_VERSION:
        raise EventValidationError("unsupported trace event schema_version")
    if not isinstance(event.event_id, str) or not event.event_id.startswith(
        "trace:v1:sha256:"
    ):
        raise EventValidationError("event_id must be a v1 SHA-256 id")
    _nonempty(event.run_id, "run_id")
    _nonnegative_int(event.revision, "revision")
    if type(event.trace_cursor) is not int or event.trace_cursor < 1:
        raise EventValidationError("trace_cursor must be an integer >= 1")
    if not isinstance(event.kind, EventKind):
        raise EventValidationError("kind must be EventKind")
    _nonempty(event.stage, "stage")
    _nonempty(event.timestamp, "timestamp")
    _optional_nonempty(event.operation_id, "operation_id")
    _optional_nonempty(event.provider, "provider")
    _optional_nonempty(event.model, "model")
    _json_object(event.details, "details")


def _json_object(value: Any, path: str) -> None:
    if not isinstance(value, Mapping):
        raise EventValidationError(f"{path} must be an object")
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EventValidationError(f"{path} must be finite JSON") from exc


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_nonempty(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _nonempty(value, path)


def _nonnegative_int(value: Any, path: str) -> None:
    if type(value) is not int or value < 0:
        raise EventValidationError(f"{path} must be an integer >= 0")
