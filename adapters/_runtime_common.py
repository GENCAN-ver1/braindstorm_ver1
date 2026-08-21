"""Shared failure recording helpers for isolated runtime adapters."""

from __future__ import annotations

from runtime.failure_ledger import FailureCategory, FailureEntry
from runtime.idempotency import stable_idempotency_key
from runtime.reentry import StageContext


def record_operational_failure(
    context: StageContext,
    *,
    operation_id: str,
    provider: str,
    category: FailureCategory,
    message: str,
) -> FailureEntry:
    entry = FailureEntry.create(
        run_id=context.session.state.run.id,
        stage=context.stage,
        operation_id=operation_id,
        provider=provider,
        category=category,
        message=message,
        idempotency_key=stable_idempotency_key(
            context.session.state.run.id,
            context.stage.value,
            operation_id,
        ),
    )
    context.session.record_failure(entry)
    return entry

