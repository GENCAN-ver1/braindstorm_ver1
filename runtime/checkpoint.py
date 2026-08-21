"""Living-Brief checkpoint envelope, optimistic CAS, and atomic persistence."""

from __future__ import annotations

import copy
import hashlib
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from observability.events import ActivationKind, EventKind, EventSpec, TraceEvent
from observability.trace_sink import TraceSink, TraceSinkError
from observability.usage_ledger import UsageLedger, UsageReceipt

from runtime.budget_guard import BudgetChargeKind, BudgetGuard
from runtime.failure_ledger import FailureEntry, FailureLedger
from runtime.fault_injection import Stage
from runtime.governor_modules import p0, p2
from runtime.idempotency import (
    InFlightOperation,
    OperationStatus,
    RetryPolicy,
    stable_idempotency_key,
)
from runtime.state_fingerprint import fingerprint_state


CHECKPOINT_SCHEMA_VERSION = 1
CHECKPOINT_RECORD_TYPE = "brainstorm-governor-checkpoint-v1"
ARTIFACT_STATUSES = {"NONE", "PENDING", "APPROVED", "REJECTED"}


class CheckpointError(p0.ContractError):
    """Base error for invalid or unsafe checkpoint operations."""


class CheckpointValidationError(CheckpointError):
    """Raised when a persisted checkpoint is corrupt or inconsistent."""


class ConcurrentCheckpointError(CheckpointError):
    """Raised when a stale revision or competing writer would be overwritten."""


@dataclass(frozen=True)
class CheckpointEnvelope:
    schema_version: int
    revision: int
    run_id: str
    last_completed_stage: str | None
    next_stage: str | None
    in_flight_operation: InFlightOperation | None
    idempotency_key: str | None
    state_hash: str
    trace_cursor: int
    evaluator_rounds_used: int
    evaluator_request_keys: list[str] = field(default_factory=list)
    evaluator_consumed_keys: list[str] = field(default_factory=list)
    usage_totals: dict[str, int | float | None] = field(default_factory=dict)
    artifact_status: str = "NONE"
    quality_gate_id: str | None = None
    operation_receipts: dict[str, Any] = field(default_factory=dict)
    budget_charges: dict[str, int] = field(default_factory=dict)
    failure_ledger: list[dict[str, Any]] = field(default_factory=list)
    usage_receipt_ids: list[str] = field(default_factory=list)
    recovery_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "revision": self.revision,
            "run_id": self.run_id,
            "last_completed_stage": self.last_completed_stage,
            "next_stage": self.next_stage,
            "in_flight_operation": (
                None
                if self.in_flight_operation is None
                else self.in_flight_operation.to_dict()
            ),
            "idempotency_key": self.idempotency_key,
            "state_hash": self.state_hash,
            "trace_cursor": self.trace_cursor,
            "evaluator_rounds_used": self.evaluator_rounds_used,
            "evaluator_request_keys": list(self.evaluator_request_keys),
            "evaluator_consumed_keys": list(self.evaluator_consumed_keys),
            "usage_totals": copy.deepcopy(self.usage_totals),
            "artifact_status": self.artifact_status,
            "quality_gate_id": self.quality_gate_id,
            "operation_receipts": copy.deepcopy(self.operation_receipts),
            "budget_charges": copy.deepcopy(self.budget_charges),
            "failure_ledger": copy.deepcopy(self.failure_ledger),
            "usage_receipt_ids": list(self.usage_receipt_ids),
            "recovery_count": self.recovery_count,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "CheckpointEnvelope":
        expected = {
            "schema_version",
            "revision",
            "run_id",
            "last_completed_stage",
            "next_stage",
            "in_flight_operation",
            "idempotency_key",
            "state_hash",
            "trace_cursor",
            "evaluator_rounds_used",
            "evaluator_request_keys",
            "evaluator_consumed_keys",
            "usage_totals",
            "artifact_status",
            "quality_gate_id",
            "operation_receipts",
            "budget_charges",
            "failure_ledger",
            "usage_receipt_ids",
            "recovery_count",
        }
        # Older envelopes predate additive FV-03/FV-04/FV-05 operational fields.
        # They are migrated in memory and written on the next checkpoint.
        additive_fields = {
            "budget_charges",
            "failure_ledger",
            "usage_receipt_ids",
            "evaluator_request_keys",
            "evaluator_consumed_keys",
            "quality_gate_id",
        }
        missing = (expected - additive_fields) - set(value)
        unknown = set(value) - expected
        if missing or unknown:
            raise CheckpointValidationError(
                f"invalid checkpoint keys; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        operation_value = value["in_flight_operation"]
        try:
            operation = (
                None
                if operation_value is None
                else InFlightOperation.from_dict(_mapping(operation_value, "in_flight_operation"))
            )
        except ValueError as exc:
            raise CheckpointValidationError(str(exc)) from exc
        evaluator_rounds_used = value["evaluator_rounds_used"]
        _nonnegative_int(evaluator_rounds_used, "evaluator_rounds_used")
        legacy_evaluator_keys = [
            f"legacy:evaluator:{index}"
            for index in range(1, evaluator_rounds_used + 1)
        ]
        evaluator_request_keys = list(
            _sequence(
                value.get("evaluator_request_keys", legacy_evaluator_keys),
                "evaluator_request_keys",
            )
        )
        evaluator_consumed_keys = list(
            _sequence(
                value.get("evaluator_consumed_keys", evaluator_request_keys),
                "evaluator_consumed_keys",
            )
        )
        envelope = cls(
            schema_version=value["schema_version"],
            revision=value["revision"],
            run_id=value["run_id"],
            last_completed_stage=value["last_completed_stage"],
            next_stage=value["next_stage"],
            in_flight_operation=operation,
            idempotency_key=value["idempotency_key"],
            state_hash=value["state_hash"],
            trace_cursor=value["trace_cursor"],
            evaluator_rounds_used=evaluator_rounds_used,
            evaluator_request_keys=evaluator_request_keys,
            evaluator_consumed_keys=evaluator_consumed_keys,
            usage_totals=copy.deepcopy(dict(_mapping(value["usage_totals"], "usage_totals"))),
            artifact_status=value["artifact_status"],
            quality_gate_id=value.get("quality_gate_id"),
            operation_receipts=copy.deepcopy(
                dict(_mapping(value["operation_receipts"], "operation_receipts"))
            ),
            budget_charges=copy.deepcopy(
                dict(_mapping(value.get("budget_charges", {}), "budget_charges"))
            ),
            failure_ledger=copy.deepcopy(
                list(_sequence(value.get("failure_ledger", []), "failure_ledger"))
            ),
            usage_receipt_ids=list(
                _sequence(value.get("usage_receipt_ids", []), "usage_receipt_ids")
            ),
            recovery_count=value["recovery_count"],
        )
        validate_envelope(envelope)
        return envelope


@dataclass
class CheckpointSession:
    path: Path
    brief: p2.ConceptBrief
    state: p0.RuntimeState
    envelope: CheckpointEnvelope
    source_digest: str
    created: bool
    migrated: bool
    trace_sink: TraceSink | None = None
    usage_ledger: UsageLedger | None = None

    def enter_stage(self, stage: Stage, *, preserve_runtime_stage: bool = False) -> None:
        state = copy.deepcopy(self.state)
        if _terminal(state):
            raise CheckpointError("cannot enter a stage from a terminal state")
        if not preserve_runtime_stage:
            state.run.stage = p0.Stage(stage.value)
        state.run.status = p0.RunStatus.ACTIVE
        state.result.exit_status = None
        p0.validate_state(state)
        existing_operation = self.envelope.in_flight_operation
        if existing_operation is not None and existing_operation.stage != stage.value:
            raise CheckpointError(
                "in-flight operation belongs to a different checkpoint stage"
            )
        envelope = replace(
            self.envelope,
            next_stage=stage.value,
            in_flight_operation=existing_operation,
            idempotency_key=(
                existing_operation.idempotency_key
                if existing_operation is not None
                else stable_idempotency_key(state.run.id, stage.value, "stage")
            ),
        )
        self._persist(
            state,
            envelope,
            next_action=f"execute {stage.value}",
            event_specs=[
                EventSpec(
                    EventKind.STAGE_TRANSITION,
                    stage.value,
                    details={"transition": "ENTER"},
                )
            ],
        )

    def commit_stage(
        self,
        state: p0.RuntimeState,
        stage: Stage,
        next_stage: Stage | None,
        *,
        terminal_exit: p0.ExitStatus | None = None,
        preserve_runtime_stage: bool = False,
        next_action: str | None = None,
    ) -> None:
        committed = copy.deepcopy(state)
        if not preserve_runtime_stage:
            committed.run.stage = p0.Stage(stage.value)
        if terminal_exit is None:
            committed.run.status = p0.RunStatus.ACTIVE
            committed.result.exit_status = None
        else:
            committed.run.status = (
                p0.RunStatus.COMPLETED
                if terminal_exit is p0.ExitStatus.COMMIT
                else p0.RunStatus.STOPPED
            )
            committed.result.exit_status = terminal_exit
        p0.validate_state(committed)
        envelope = replace(
            self.envelope,
            last_completed_stage=stage.value,
            next_stage=None if next_stage is None else next_stage.value,
            in_flight_operation=None,
            idempotency_key=stable_idempotency_key(
                committed.run.id, stage.value, "stage"
            ),
        )
        resolved_next_action = next_action or (
            f"resume at {next_stage.value}"
            if next_stage is not None
            else "run complete"
        )
        events = [
            EventSpec(
                EventKind.STAGE_TRANSITION,
                stage.value,
                details={
                    "transition": "COMMIT",
                    "next_stage": None if next_stage is None else next_stage.value,
                },
            )
        ]
        if terminal_exit is not None:
            events.append(
                EventSpec(
                    EventKind.EXIT_STATUS,
                    stage.value,
                    details={"exit_status": terminal_exit.value},
                )
            )
        self._persist(
            committed,
            envelope,
            next_action=resolved_next_action,
            previous_stop_reason=(
                None if terminal_exit is None else terminal_exit.value
            ),
            event_specs=events,
        )

    def consume_budget(
        self,
        guard: BudgetGuard,
        stage: Stage,
        operation_id: str,
        kind: BudgetChargeKind,
    ) -> bool:
        """Atomically reserve one idempotent budget charge.

        A persisted charge is reused after interruption, so stage and external
        work cannot be double-charged during Brief-first recovery.
        """
        if self.envelope.next_stage != stage.value:
            raise CheckpointError("budget charge stage must equal checkpoint next_stage")
        key = guard.charge_key(self.state, stage, operation_id, kind)
        if key in self.envelope.budget_charges:
            return False
        charged = copy.deepcopy(self.state)
        guard.consume(charged, stage, operation_id, kind)
        charges = copy.deepcopy(self.envelope.budget_charges)
        charges[key] = guard.step_cost
        envelope = replace(self.envelope, budget_charges=charges)
        next_action = (
            f"call external operation {operation_id} at {stage.value}"
            if kind is BudgetChargeKind.EXTERNAL
            else f"execute {stage.value}"
        )
        self._persist(charged, envelope, next_action=next_action)
        return True

    def park(self, exhausted: "BudgetExhausted") -> None:
        """Persist a valid PARK without consuming another budget step."""
        from runtime.lifecycle_errors import BudgetExhausted

        if not isinstance(exhausted, BudgetExhausted):
            raise TypeError("exhausted must be BudgetExhausted")
        parked = copy.deepcopy(self.state)
        parked.run.budget.used_steps = min(
            parked.run.budget.max_steps,
            max(parked.run.budget.used_steps, exhausted.used_steps),
        )
        parked.run.stage = p0.Stage.STOPPED
        parked.run.status = p0.RunStatus.STOPPED
        parked.result.exit_status = p0.ExitStatus.PARK
        p0.validate_state(parked)
        envelope = replace(
            self.envelope,
            next_stage=exhausted.stage.value,
            in_flight_operation=None,
            idempotency_key=stable_idempotency_key(
                parked.run.id, exhausted.stage.value, "budget-park"
            ),
        )
        self._persist(
            parked,
            envelope,
            next_action=exhausted.next_action,
            previous_stop_reason=p0.ExitStatus.PARK.value,
            event_specs=[
                EventSpec(
                    EventKind.EXIT_STATUS,
                    exhausted.stage.value,
                    details={
                        "exit_status": p0.ExitStatus.PARK.value,
                        "reason": "budget exhausted",
                    },
                )
            ],
        )

    def resume_park(self, guard: BudgetGuard, new_max_steps: int) -> None:
        """Resume only when the caller explicitly raises the persisted limit."""
        state = copy.deepcopy(self.state)
        if (
            state.run.status is not p0.RunStatus.STOPPED
            or state.result.exit_status is not p0.ExitStatus.PARK
        ):
            raise CheckpointError("only a PARK checkpoint can resume by budget increase")
        if self.envelope.next_stage is None:
            raise CheckpointError("PARK checkpoint is missing its blocked stage")
        guard.increase_limit(state, new_max_steps)
        state.run.stage = p0.Stage(self.envelope.next_stage)
        state.run.status = p0.RunStatus.ACTIVE
        state.result.exit_status = None
        p0.validate_state(state)
        envelope = replace(
            self.envelope,
            in_flight_operation=None,
            idempotency_key=stable_idempotency_key(
                state.run.id, self.envelope.next_stage, "budget-resume"
            ),
        )
        self._persist(
            state,
            envelope,
            next_action=f"resume at {self.envelope.next_stage}",
            event_specs=[
                EventSpec(
                    EventKind.RECOVERY,
                    self.envelope.next_stage,
                    details={"reason": "budget limit increased"},
                )
            ],
        )

    def prepare_external(
        self,
        stage: Stage,
        operation_id: str,
        retry_policy: RetryPolicy,
        *,
        provider: str | None = None,
        model: str | None = None,
        retry: bool = False,
    ) -> str:
        key = stable_idempotency_key(self.state.run.id, stage.value, operation_id)
        operation = InFlightOperation(
            operation_id=operation_id,
            stage=stage.value,
            idempotency_key=key,
            status=OperationStatus.STARTED,
            retry_policy=retry_policy,
        )
        envelope = replace(
            self.envelope,
            in_flight_operation=operation,
            idempotency_key=key,
        )
        self._persist(
            self.state,
            envelope,
            next_action=f"complete external operation {operation_id}",
            event_specs=[
                EventSpec(
                    (
                        EventKind.EXTERNAL_CALL_RETRY
                        if retry
                        else EventKind.EXTERNAL_CALL_STARTED
                    ),
                    stage.value,
                    operation_id=operation_id,
                    provider=provider,
                    model=model,
                    details={"idempotency_key": key},
                )
            ],
        )
        return key

    def complete_external(
        self,
        key: str,
        receipt: Any,
        *,
        provider: str | None = None,
        model: str | None = None,
        usage_receipt: UsageReceipt | None = None,
    ) -> None:
        _ensure_json(receipt, "operation receipt")
        if self.envelope.in_flight_operation is None:
            raise CheckpointError("no in-flight operation to complete")
        if self.envelope.in_flight_operation.idempotency_key != key:
            raise CheckpointError("external completion key does not match in-flight operation")
        receipts = copy.deepcopy(self.envelope.operation_receipts)
        if key in receipts and receipts[key] != receipt:
            raise CheckpointError("idempotency receipt cannot be overwritten")
        receipts[key] = copy.deepcopy(receipt)
        usage_receipt_ids = list(self.envelope.usage_receipt_ids)
        usage_totals = copy.deepcopy(self.envelope.usage_totals)
        persisted_usage: list[UsageReceipt] = []
        if usage_receipt is not None and usage_receipt.receipt_id not in usage_receipt_ids:
            usage_receipt_ids.append(usage_receipt.receipt_id)
            usage_totals = _add_usage_totals(usage_totals, usage_receipt)
            persisted_usage.append(usage_receipt)
        envelope = replace(
            self.envelope,
            in_flight_operation=None,
            idempotency_key=key,
            operation_receipts=receipts,
            usage_receipt_ids=usage_receipt_ids,
            usage_totals=usage_totals,
        )
        operation = self.envelope.in_flight_operation
        assert operation is not None
        self._persist(
            self.state,
            envelope,
            next_action="commit the current stage",
            event_specs=[
                EventSpec(
                    EventKind.EXTERNAL_CALL_SUCCEEDED,
                    operation.stage,
                    operation_id=operation.operation_id,
                    provider=provider,
                    model=model,
                    details={
                        "idempotency_key": key,
                        "usage_receipt_id": (
                            None if usage_receipt is None else usage_receipt.receipt_id
                        ),
                    },
                )
            ],
            usage_receipts=persisted_usage,
        )

    def abort_external(
        self,
        key: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        error_type: str | None = None,
        usage_receipt: UsageReceipt | None = None,
    ) -> None:
        """Clear a known failed call while leaving no reusable success receipt."""
        operation = self.envelope.in_flight_operation
        if operation is None:
            raise CheckpointError("no in-flight operation to abort")
        if operation.idempotency_key != key:
            raise CheckpointError("external abort key does not match in-flight operation")
        usage_receipt_ids = list(self.envelope.usage_receipt_ids)
        usage_totals = copy.deepcopy(self.envelope.usage_totals)
        persisted_usage: list[UsageReceipt] = []
        if usage_receipt is not None and usage_receipt.receipt_id not in usage_receipt_ids:
            usage_receipt_ids.append(usage_receipt.receipt_id)
            usage_totals = _add_usage_totals(usage_totals, usage_receipt)
            persisted_usage.append(usage_receipt)
        envelope = replace(
            self.envelope,
            in_flight_operation=None,
            idempotency_key=key,
            usage_receipt_ids=usage_receipt_ids,
            usage_totals=usage_totals,
        )
        self._persist(
            self.state,
            envelope,
            next_action=f"review failed external operation {operation.operation_id}",
            event_specs=[
                EventSpec(
                    EventKind.EXTERNAL_CALL_FAILED,
                    operation.stage,
                    operation_id=operation.operation_id,
                    provider=provider,
                    model=model,
                    details={
                        "idempotency_key": key,
                        "error_type": error_type,
                        "usage_receipt_id": (
                            None if usage_receipt is None else usage_receipt.receipt_id
                        ),
                    },
                )
            ],
            usage_receipts=persisted_usage,
        )

    def record_failure(self, entry: FailureEntry) -> bool:
        """Append one idempotent failure and advance the checkpoint Trace cursor."""
        if entry.run_id != self.state.run.id:
            raise CheckpointError("failure run_id conflicts with checkpoint state")
        ledger = FailureLedger.from_records(self.envelope.failure_ledger)
        if not ledger.append(entry):
            return False
        envelope = replace(
            self.envelope,
            failure_ledger=ledger.to_records(),
            trace_cursor=(
                self.envelope.trace_cursor
                if self.trace_sink is not None
                else self.envelope.trace_cursor + 1
            ),
        )
        self._persist(
            self.state,
            envelope,
            next_action=f"review {entry.category.value} at {entry.stage}",
            event_specs=[
                EventSpec(
                    EventKind.FAILURE_RECORDED,
                    entry.stage,
                    operation_id=entry.operation_id,
                    provider=entry.provider,
                    details={
                        "failure_id": entry.failure_id,
                        "category": entry.category.value,
                    },
                )
            ],
        )
        return True

    def mark_recovered(self) -> None:
        envelope = replace(
            self.envelope,
            recovery_count=self.envelope.recovery_count + 1,
        )
        self._persist(
            self.state,
            envelope,
            next_action=self.brief.next_action
            or (
                "run complete"
                if envelope.next_stage is None
                else f"resume at {envelope.next_stage}"
            ),
            event_specs=[
                EventSpec(
                    EventKind.RECOVERY,
                    envelope.next_stage or self.state.run.stage.value,
                    details={"recovery_count": envelope.recovery_count},
                )
            ],
        )

    def record_gate_decision(
        self,
        stage: Stage,
        gate: str,
        enabled: bool,
        reason: str,
    ) -> bool:
        if type(enabled) is not bool:
            raise CheckpointError("gate enabled must be boolean")
        gate_name = _nonempty_text(gate, "gate")
        gate_reason = _nonempty_text(reason, "gate reason")
        if self.trace_sink is None:
            return False
        dedupe_key = f"gate:{stage.value}:{gate_name}:{enabled}:{gate_reason}"
        if self.trace_sink is not None and self.trace_sink.has_dedupe_key(
            self.state.run.id, dedupe_key
        ):
            return False
        self._persist(
            self.state,
            self.envelope,
            next_action=self.brief.next_action or f"continue {stage.value}",
            event_specs=[
                EventSpec(
                    EventKind.GATE_DECISION,
                    stage.value,
                    details={
                        "gate": gate_name,
                        "enabled": enabled,
                        "reason": gate_reason,
                        "dedupe_key": dedupe_key,
                    },
                )
            ],
        )
        return True

    def record_activation(self, stage: Stage, activation: ActivationKind) -> bool:
        if not isinstance(activation, ActivationKind):
            raise CheckpointError("activation must be ActivationKind")
        if self.trace_sink is None:
            return False
        dedupe_key = f"activation:{activation.value}"
        if self.trace_sink is not None and self.trace_sink.has_dedupe_key(
            self.state.run.id, dedupe_key
        ):
            return False
        self._persist(
            self.state,
            self.envelope,
            next_action=self.brief.next_action or f"continue {stage.value}",
            event_specs=[
                EventSpec(
                    EventKind.ACTIVATION,
                    stage.value,
                    details={
                        "activation": activation.value,
                        "dedupe_key": dedupe_key,
                    },
                )
            ],
        )
        return True

    def reserve_evaluator_round(
        self,
        operation_id: str,
        *,
        max_rounds: int,
    ) -> int | None:
        """Persist one evaluator reservation before any provider call.

        Returns the durable one-based round number, or ``None`` when the
        configured cap has already been reached. Reusing the same operation is
        idempotent and never increments the counter.
        """
        if self.envelope.next_stage != Stage.EVALUATE.value:
            raise CheckpointError("evaluator round requires the EVALUATE stage")
        if type(max_rounds) is not int or max_rounds < 1:
            raise CheckpointError("max_rounds must be an integer >= 1")
        operation = _nonempty_text(operation_id, "operation_id")
        key = stable_idempotency_key(
            self.state.run.id, Stage.EVALUATE.value, operation
        )
        if key in self.envelope.evaluator_request_keys:
            return self.envelope.evaluator_request_keys.index(key) + 1
        if self.envelope.evaluator_rounds_used >= max_rounds:
            return None
        expected_operation = (
            f"evaluator:{self.envelope.evaluator_rounds_used + 1}"
        )
        if operation != expected_operation:
            raise CheckpointError(
                f"next evaluator operation must be {expected_operation!r}"
            )
        request_keys = [*self.envelope.evaluator_request_keys, key]
        envelope = replace(
            self.envelope,
            evaluator_rounds_used=self.envelope.evaluator_rounds_used + 1,
            evaluator_request_keys=request_keys,
        )
        self._persist(
            self.state,
            envelope,
            next_action=f"call evaluator round {len(request_keys)}",
            event_specs=[
                EventSpec(
                    EventKind.GATE_DECISION,
                    Stage.EVALUATE.value,
                    operation_id=operation,
                    details={
                        "gate": "evaluator_round_cap",
                        "enabled": True,
                        "round": len(request_keys),
                        "max_rounds": max_rounds,
                    },
                )
            ],
        )
        return len(request_keys)

    def mark_evaluator_result_consumed(self, operation_id: str) -> bool:
        """Mark a returned evaluator receipt as consumed, idempotently."""
        operation = _nonempty_text(operation_id, "operation_id")
        key = stable_idempotency_key(
            self.state.run.id, Stage.EVALUATE.value, operation
        )
        if key not in self.envelope.evaluator_request_keys:
            raise CheckpointError("cannot consume an unreserved evaluator round")
        if key in self.envelope.evaluator_consumed_keys:
            return False
        consumed = [*self.envelope.evaluator_consumed_keys, key]
        envelope = replace(self.envelope, evaluator_consumed_keys=consumed)
        self._persist(
            self.state,
            envelope,
            next_action="process evaluator corrections",
        )
        return True

    def update_progress(
        self,
        *,
        trace_cursor: int | None = None,
        evaluator_rounds_used: int | None = None,
        usage_totals: Mapping[str, int | float | None] | None = None,
        artifact_status: str | None = None,
        quality_gate_id: str | None = None,
    ) -> None:
        request_keys = list(self.envelope.evaluator_request_keys)
        consumed_keys = list(self.envelope.evaluator_consumed_keys)
        if evaluator_rounds_used is not None:
            if (
                type(evaluator_rounds_used) is not int
                or evaluator_rounds_used < self.envelope.evaluator_rounds_used
            ):
                raise CheckpointError(
                    "evaluator_rounds_used cannot decrease and must be an integer"
                )
            while len(request_keys) < evaluator_rounds_used:
                key = f"legacy:evaluator:{len(request_keys) + 1}"
                request_keys.append(key)
                consumed_keys.append(key)
        envelope = replace(
            self.envelope,
            trace_cursor=(
                self.envelope.trace_cursor
                if trace_cursor is None
                else trace_cursor
            ),
            evaluator_rounds_used=(
                self.envelope.evaluator_rounds_used
                if evaluator_rounds_used is None
                else evaluator_rounds_used
            ),
            evaluator_request_keys=request_keys,
            evaluator_consumed_keys=consumed_keys,
            usage_totals=(
                copy.deepcopy(self.envelope.usage_totals)
                if usage_totals is None
                else copy.deepcopy(dict(usage_totals))
            ),
            artifact_status=(
                self.envelope.artifact_status
                if artifact_status is None
                else artifact_status
            ),
            quality_gate_id=(
                self.envelope.quality_gate_id
                if quality_gate_id is None
                else _nonempty_text(quality_gate_id, "quality_gate_id")
            ),
        )
        self._persist(
            self.state,
            envelope,
            next_action=self.brief.next_action
            or (
                "run complete"
                if envelope.next_stage is None
                else f"resume at {envelope.next_stage}"
            ),
        )

    def _persist(
        self,
        state: p0.RuntimeState,
        envelope: CheckpointEnvelope,
        *,
        next_action: str,
        previous_stop_reason: str | None = None,
        event_specs: Sequence[EventSpec] = (),
        usage_receipts: Sequence[UsageReceipt] = (),
    ) -> None:
        expected_revision = self.envelope.revision
        state_copy = copy.deepcopy(state)
        specs = list(event_specs)
        if self.trace_sink is not None:
            specs.append(
                EventSpec(
                    EventKind.CHECKPOINT_SAVED,
                    envelope.next_stage
                    or envelope.last_completed_stage
                    or state_copy.run.stage.value,
                    details={"next_action": next_action},
                )
            )
        candidate = replace(
            envelope,
            revision=expected_revision + 1,
            run_id=state_copy.run.id,
            state_hash=_state_hash(state_copy),
            trace_cursor=(
                envelope.trace_cursor + len(specs)
                if self.trace_sink is not None
                else envelope.trace_cursor
            ),
        )
        validate_envelope(candidate, state_copy)
        _set_checkpoint_record(state_copy, candidate)
        brief_copy = copy.deepcopy(self.brief)

        with _brief_lock(self.path):
            if not self.path.is_file():
                raise ConcurrentCheckpointError("Brief disappeared during checkpoint CAS")
            current_digest = _file_digest(self.path)
            if current_digest != self.source_digest:
                raise ConcurrentCheckpointError(
                    "Brief content changed since restore; refusing stale overwrite"
                )
            current_brief = p2.load_brief(self.path)
            current = checkpoint_from_state(current_brief.runtime_state)
            if current is None or current.revision != expected_revision:
                actual = None if current is None else current.revision
                raise ConcurrentCheckpointError(
                    f"checkpoint revision changed: expected {expected_revision}, got {actual}"
                )
            p2.save_round(
                self.path,
                brief_copy,
                state_copy,
                next_action=next_action,
                previous_stop_reason=(
                    brief_copy.previous_stop_reason
                    if previous_stop_reason is None
                    else previous_stop_reason
                ),
            )
            digest = _file_digest(self.path)

        self.brief = brief_copy
        self.state = state_copy
        self.envelope = candidate
        self.source_digest = digest
        if self.trace_sink is not None:
            first_cursor = candidate.trace_cursor - len(specs) + 1
            events = [
                TraceEvent.create(
                    run_id=candidate.run_id,
                    revision=candidate.revision,
                    trace_cursor=first_cursor + index,
                    spec=spec,
                )
                for index, spec in enumerate(specs)
            ]
            self.trace_sink.append_batch(events, list(usage_receipts))


class CheckpointStore:
    def __init__(
        self,
        *,
        trace_sink: TraceSink | None = None,
        usage_ledger: UsageLedger | None = None,
    ) -> None:
        self.trace_sink = trace_sink
        self.usage_ledger = usage_ledger

    def open(
        self,
        path: str | Path,
        initial_state: p0.RuntimeState,
        *,
        initial_next_stage: Stage = Stage.INITIALIZE,
        trace_sink: TraceSink | None = None,
        usage_ledger: UsageLedger | None = None,
    ) -> CheckpointSession:
        target = Path(path).resolve()
        active_trace_sink = trace_sink or self.trace_sink
        active_usage_ledger = usage_ledger or self.usage_ledger
        p0.validate_state(initial_state)
        with _brief_lock(target):
            if target.is_file():
                brief = p2.load_brief(target)
                envelope = checkpoint_from_state(brief.runtime_state)
                if envelope is None:
                    state = copy.deepcopy(brief.runtime_state)
                    envelope = new_envelope(state, next_stage=_resume_stage(state, initial_next_stage))
                    _set_checkpoint_record(state, envelope)
                    brief = copy.deepcopy(brief)
                    p2.save_round(
                        target,
                        brief,
                        state,
                        next_action=(
                            "run complete"
                            if envelope.next_stage is None
                            else f"resume at {envelope.next_stage}"
                        ),
                    )
                    migrated = True
                else:
                    state = copy.deepcopy(brief.runtime_state)
                    validate_envelope(envelope, state)
                    migrated = False
                if active_trace_sink is not None:
                    try:
                        active_trace_sink.validate_link(
                            envelope.run_id,
                            envelope.revision,
                            envelope.trace_cursor,
                        )
                    except TraceSinkError as exc:
                        raise CheckpointValidationError(
                            f"checkpoint/trace link is invalid: {exc}"
                        ) from exc
                return CheckpointSession(
                    path=target,
                    brief=brief,
                    state=state,
                    envelope=envelope,
                    source_digest=_file_digest(target),
                    created=False,
                    migrated=migrated,
                    trace_sink=active_trace_sink,
                    usage_ledger=active_usage_ledger,
                )

            state = copy.deepcopy(initial_state)
            envelope = new_envelope(state, next_stage=initial_next_stage)
            _set_checkpoint_record(state, envelope)
            brief = p2.brief_from_state(
                state,
                next_action=f"resume at {initial_next_stage.value}",
            )
            p2.save_brief(target, brief)
            return CheckpointSession(
                path=target,
                brief=brief,
                state=state,
                envelope=envelope,
                source_digest=_file_digest(target),
                created=True,
                migrated=False,
                trace_sink=active_trace_sink,
                usage_ledger=active_usage_ledger,
            )


def new_envelope(
    state: p0.RuntimeState,
    *,
    next_stage: Stage | None,
) -> CheckpointEnvelope:
    return CheckpointEnvelope(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        revision=0,
        run_id=state.run.id,
        last_completed_stage=None,
        next_stage=None if next_stage is None else next_stage.value,
        in_flight_operation=None,
        idempotency_key=None,
        state_hash=_state_hash(state),
        trace_cursor=0,
        evaluator_rounds_used=0,
        evaluator_request_keys=[],
        evaluator_consumed_keys=[],
        usage_totals={},
        artifact_status="NONE",
        quality_gate_id=None,
        operation_receipts={},
        budget_charges={},
        failure_ledger=[],
        usage_receipt_ids=[],
        recovery_count=0,
    )


def checkpoint_from_state(state: p0.RuntimeState) -> CheckpointEnvelope | None:
    records = [
        item
        for item in state.deferred
        if item.get("type") == CHECKPOINT_RECORD_TYPE
    ]
    if len(records) > 1:
        raise CheckpointValidationError("state contains duplicate checkpoint records")
    if not records:
        return None
    record = records[0]
    if set(record) != {"type", "envelope"}:
        raise CheckpointValidationError("checkpoint record has unknown fields")
    return CheckpointEnvelope.from_dict(_mapping(record["envelope"], "checkpoint.envelope"))


def validate_envelope(
    envelope: CheckpointEnvelope,
    state: p0.RuntimeState | None = None,
) -> None:
    if envelope.schema_version != CHECKPOINT_SCHEMA_VERSION:
        raise CheckpointValidationError(
            f"unsupported checkpoint schema_version {envelope.schema_version!r}"
        )
    _nonnegative_int(envelope.revision, "revision")
    if not isinstance(envelope.run_id, str) or not envelope.run_id.strip():
        raise CheckpointValidationError("run_id must be a non-empty string")
    _optional_stage(envelope.last_completed_stage, "last_completed_stage")
    _optional_stage(envelope.next_stage, "next_stage")
    if envelope.idempotency_key is not None and (
        not isinstance(envelope.idempotency_key, str)
        or not envelope.idempotency_key.strip()
    ):
        raise CheckpointValidationError("idempotency_key must be non-empty or null")
    if not isinstance(envelope.state_hash, str) or not envelope.state_hash.startswith(
        "v1:sha256:"
    ):
        raise CheckpointValidationError("state_hash must be a v1 SHA-256 fingerprint")
    _nonnegative_int(envelope.trace_cursor, "trace_cursor")
    _nonnegative_int(envelope.evaluator_rounds_used, "evaluator_rounds_used")
    if envelope.evaluator_rounds_used != len(envelope.evaluator_request_keys):
        raise CheckpointValidationError(
            "evaluator_rounds_used must equal evaluator_request_keys length"
        )
    if len(envelope.evaluator_request_keys) != len(
        set(envelope.evaluator_request_keys)
    ):
        raise CheckpointValidationError("evaluator_request_keys must be unique")
    if len(envelope.evaluator_consumed_keys) != len(
        set(envelope.evaluator_consumed_keys)
    ):
        raise CheckpointValidationError("evaluator_consumed_keys must be unique")
    if not set(envelope.evaluator_consumed_keys).issubset(
        envelope.evaluator_request_keys
    ):
        raise CheckpointValidationError(
            "evaluator_consumed_keys must be reserved evaluator requests"
        )
    for index, key in enumerate(envelope.evaluator_request_keys, start=1):
        if key.startswith("legacy:evaluator:"):
            if key != f"legacy:evaluator:{index}":
                raise CheckpointValidationError(
                    "legacy evaluator request keys must preserve round order"
                )
            continue
        expected = stable_idempotency_key(
            envelope.run_id, Stage.EVALUATE.value, f"evaluator:{index}"
        )
        if key != expected:
            raise CheckpointValidationError(
                "evaluator request key conflicts with its durable round"
            )
    _nonnegative_int(envelope.recovery_count, "recovery_count")
    if envelope.artifact_status not in ARTIFACT_STATUSES:
        raise CheckpointValidationError(
            f"artifact_status must be one of {sorted(ARTIFACT_STATUSES)}"
        )
    if envelope.quality_gate_id is not None and (
        not isinstance(envelope.quality_gate_id, str)
        or not envelope.quality_gate_id.strip()
    ):
        raise CheckpointValidationError("quality_gate_id must be non-empty or null")
    for key, value in envelope.usage_totals.items():
        if not isinstance(key, str) or not key.strip():
            raise CheckpointValidationError("usage_totals keys must be non-empty strings")
        if value is not None and (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
        ):
            raise CheckpointValidationError(
                "usage_totals values must be non-negative numbers or null"
            )
    _ensure_json(envelope.operation_receipts, "operation_receipts")
    for key, value in envelope.budget_charges.items():
        if not isinstance(key, str) or not key.strip():
            raise CheckpointValidationError(
                "budget_charges keys must be non-empty strings"
            )
        if type(value) is not int or value < 1:
            raise CheckpointValidationError(
                "budget_charges values must be integers >= 1"
            )
    try:
        FailureLedger.from_records(envelope.failure_ledger)
    except ValueError as exc:
        raise CheckpointValidationError(f"invalid failure_ledger: {exc}") from exc
    if not isinstance(envelope.usage_receipt_ids, list):
        raise CheckpointValidationError("usage_receipt_ids must be an array")
    if len(envelope.usage_receipt_ids) != len(set(envelope.usage_receipt_ids)):
        raise CheckpointValidationError("usage_receipt_ids must be unique")
    for value in envelope.usage_receipt_ids:
        if not isinstance(value, str) or not value.startswith("usage:v1:sha256:"):
            raise CheckpointValidationError(
                "usage_receipt_ids must contain v1 SHA-256 ids"
            )
    if envelope.in_flight_operation is not None:
        if envelope.idempotency_key != envelope.in_flight_operation.idempotency_key:
            raise CheckpointValidationError(
                "idempotency_key conflicts with in_flight_operation"
            )
        if envelope.in_flight_operation.stage != envelope.next_stage:
            raise CheckpointValidationError(
                "in_flight_operation stage must equal next_stage"
            )
    if state is not None:
        p0.validate_state(state)
        if envelope.run_id != state.run.id:
            raise CheckpointValidationError("checkpoint run_id conflicts with state")
        if envelope.state_hash != _state_hash(state):
            raise CheckpointValidationError("checkpoint state_hash mismatch")


def _set_checkpoint_record(
    state: p0.RuntimeState, envelope: CheckpointEnvelope
) -> None:
    state.deferred = [
        copy.deepcopy(item)
        for item in state.deferred
        if item.get("type") != CHECKPOINT_RECORD_TYPE
    ]
    state.deferred.append(
        {"type": CHECKPOINT_RECORD_TYPE, "envelope": envelope.to_dict()}
    )
    p0.validate_state(state)


def _state_hash(state: p0.RuntimeState) -> str:
    return fingerprint_state(p0.state_to_dict(state))


def _resume_stage(state: p0.RuntimeState, fallback: Stage) -> Stage | None:
    if _terminal(state):
        return None
    try:
        return Stage(state.run.stage.value)
    except ValueError:
        return fallback


def _terminal(state: p0.RuntimeState) -> bool:
    return state.run.status in {p0.RunStatus.COMPLETED, p0.RunStatus.STOPPED}


@contextmanager
def _brief_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.cas.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ConcurrentCheckpointError(
            f"checkpoint lock already held for {path}"
        ) from exc
    try:
        os.close(descriptor)
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _add_usage_totals(
    totals: Mapping[str, int | float | None], receipt: UsageReceipt
) -> dict[str, int | float | None]:
    result = copy.deepcopy(dict(totals))
    for name in ("prompt_tokens", "completion_tokens", "cached_tokens", "tool_calls"):
        value = getattr(receipt, name)
        if value is not None:
            result[name] = int(result.get(name) or 0) + value
    if receipt.calculated_cost is not None:
        result["calculated_cost"] = round(
            float(result.get("calculated_cost") or 0.0) + receipt.calculated_cost,
            12,
        )
        result["priced_calls"] = int(result.get("priced_calls") or 0) + 1
    elif receipt.usage_source.value == "PROVIDER":
        result["unpriced_calls"] = int(result.get("unpriced_calls") or 0) + 1
    if receipt.usage_source.value == "UNAVAILABLE":
        result["unavailable_calls"] = int(result.get("unavailable_calls") or 0) + 1
    return result


def _nonempty_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CheckpointError(f"{path} must be a non-empty string")
    return value.strip()


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CheckpointValidationError(f"{path} must be an object")
    return value


def _sequence(value: Any, path: str) -> list[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, list):
        raise CheckpointValidationError(f"{path} must be an array")
    return value


def _optional_stage(value: Any, path: str) -> None:
    if value is None:
        return
    try:
        Stage(value)
    except (TypeError, ValueError) as exc:
        raise CheckpointValidationError(f"{path} must be a lifecycle stage or null") from exc


def _nonnegative_int(value: Any, path: str) -> None:
    if type(value) is not int or value < 0:
        raise CheckpointValidationError(f"{path} must be an integer >= 0")


def _ensure_json(value: Any, path: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise CheckpointValidationError(f"{path} must be canonical JSON: {exc}") from exc
