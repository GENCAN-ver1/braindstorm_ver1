"""Canonical fingerprint of the governor fields that define main state."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


FINGERPRINT_SCHEMA_VERSION = 1
MAIN_STATE_FIELDS = (
    "frame",
    "candidates",
    "assumptions",
    "unknowns",
    "evidence",
    "decisions",
    "result",
)


class StateFingerprintError(ValueError):
    """Raised when main state cannot be fingerprinted canonically."""


def canonical_state_payload(
    state: Mapping[str, Any],
    *,
    fields: Sequence[str] = MAIN_STATE_FIELDS,
) -> bytes:
    """Return stable UTF-8 JSON for only the declared main-state fields."""

    if not isinstance(state, Mapping):
        raise StateFingerprintError("state must be a mapping")
    normalized_fields = tuple(fields)
    if not normalized_fields or len(set(normalized_fields)) != len(normalized_fields):
        raise StateFingerprintError("fingerprint fields must be unique and non-empty")
    missing = [field for field in normalized_fields if field not in state]
    if missing:
        raise StateFingerprintError(
            f"state is missing fingerprint fields: {', '.join(missing)}"
        )
    envelope = {
        "fingerprint_schema_version": FINGERPRINT_SCHEMA_VERSION,
        "state": {field: state[field] for field in normalized_fields},
    }
    try:
        canonical = json.dumps(
            envelope,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise StateFingerprintError(f"state is not canonical JSON: {exc}") from exc
    return canonical.encode("utf-8")


def fingerprint_state(
    state: Mapping[str, Any],
    *,
    fields: Sequence[str] = MAIN_STATE_FIELDS,
) -> str:
    """Return a version-explicit SHA-256 main-state fingerprint."""

    digest = hashlib.sha256(canonical_state_payload(state, fields=fields)).hexdigest()
    return f"v{FINGERPRINT_SCHEMA_VERSION}:sha256:{digest}"

