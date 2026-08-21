"""Copy-on-write staging transaction for Research and Worker results."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from runtime.governor_modules import p0
from runtime.state_fingerprint import fingerprint_state


class TransactionError(p0.ContractError):
    """Base error for invalid staging or unsafe commit."""


class ConcurrentMainStateError(TransactionError):
    """Raised when main state changed after the read-only snapshot was taken."""


class DuplicateCandidateError(TransactionError):
    """Raised when a candidate duplicates an existing core mechanism."""


class TransactionKind(str, Enum):
    RESEARCH = "RESEARCH"
    WORKER = "WORKER"


class CommitPolicy(str, Enum):
    ALL_OR_NOTHING = "all-or-nothing"
    VALIDATED_PARTIAL = "validated-partial"


class TransactionStatus(str, Enum):
    OPEN = "OPEN"
    COMMITTED = "COMMITTED"
    NOOP = "NOOP"
    DISCARDED = "DISCARDED"


@dataclass
class StagingArea:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[p0.EvidenceRecord] = field(default_factory=list)
    resolved_claims: set[str] = field(default_factory=set)
    failure_ids: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class TransactionResult:
    state: p0.RuntimeState
    status: TransactionStatus
    committed_candidate_ids: list[str]
    committed_evidence_ids: list[str]
    discarded_reason: str | None


class StateTransaction:
    """Own a deep snapshot and publish validated fields in one COW commit."""

    def __init__(
        self,
        state: p0.RuntimeState,
        *,
        kind: TransactionKind,
        operation_id: str,
    ) -> None:
        p0.validate_state(state)
        if not isinstance(kind, TransactionKind):
            raise TransactionError("kind must be TransactionKind")
        if not isinstance(operation_id, str) or not operation_id.strip():
            raise TransactionError("operation_id must be a non-empty string")
        self.kind = kind
        self.operation_id = operation_id.strip()
        self._base_state = copy.deepcopy(state)
        self.base_fingerprint = fingerprint_state(p0.state_to_dict(state))
        self.staging = StagingArea()
        self.status = TransactionStatus.OPEN

    def snapshot(self) -> p0.RuntimeState:
        return copy.deepcopy(self._base_state)

    def stage_candidate(self, candidate: Mapping[str, Any]) -> bool:
        self._ensure_open()
        normalized = _candidate(candidate)
        candidate_id = normalized["id"]
        mechanism = _mechanism(normalized["core_mechanism"])
        for existing in [*self._base_state.candidates, *self.staging.candidates]:
            if existing.get("id") == candidate_id:
                if _canonical(existing) == _canonical(normalized):
                    return False
                raise TransactionError(
                    f"candidate id {candidate_id!r} has conflicting content"
                )
            existing_mechanism = existing.get("core_mechanism")
            if isinstance(existing_mechanism, str) and _mechanism(existing_mechanism) == mechanism:
                raise DuplicateCandidateError(
                    f"duplicate candidate core mechanism for {candidate_id!r}"
                )
        self.staging.candidates.append(normalized)
        return True

    def stage_evidence(self, record: p0.EvidenceRecord) -> bool:
        self._ensure_open()
        if not isinstance(record, p0.EvidenceRecord):
            raise TransactionError("record must be EvidenceRecord")
        serialized = _canonical(p0._json_ready(record))
        for existing in [*self._base_state.evidence, *self.staging.evidence]:
            if existing.id != record.id:
                continue
            if _canonical(p0._json_ready(existing)) == serialized:
                return False
            raise TransactionError(
                f"evidence id {record.id!r} has conflicting content"
            )
        self.staging.evidence.append(copy.deepcopy(record))
        return True

    def stage_resolved_claim(self, claim: str) -> None:
        self._ensure_open()
        if not isinstance(claim, str) or not claim.strip():
            raise TransactionError("resolved claim must be a non-empty string")
        self.staging.resolved_claims.add(_normalize(claim))

    def register_failure(self, failure_id: str) -> None:
        self._ensure_open()
        if not isinstance(failure_id, str) or not failure_id.strip():
            raise TransactionError("failure_id must be a non-empty string")
        self.staging.failure_ids.add(failure_id.strip())

    def stage_batch(
        self,
        *,
        candidates: Sequence[Mapping[str, Any]] = (),
        evidence: Sequence[p0.EvidenceRecord] = (),
        resolved_claims: Sequence[str] = (),
    ) -> None:
        """Stage one validation unit atomically; rollback the unit on error."""
        self._ensure_open()
        before = copy.deepcopy(self.staging)
        try:
            for candidate in candidates:
                self.stage_candidate(candidate)
            for record in evidence:
                self.stage_evidence(record)
            for claim in resolved_claims:
                self.stage_resolved_claim(claim)
        except Exception:
            self.staging = before
            raise

    def commit(
        self,
        current_state: p0.RuntimeState,
        *,
        policy: CommitPolicy = CommitPolicy.VALIDATED_PARTIAL,
    ) -> TransactionResult:
        self._ensure_open()
        if not isinstance(policy, CommitPolicy):
            raise TransactionError("policy must be CommitPolicy")
        p0.validate_state(current_state)
        if fingerprint_state(p0.state_to_dict(current_state)) != self.base_fingerprint:
            raise ConcurrentMainStateError(
                "main state changed after transaction snapshot"
            )
        if self.staging.failure_ids and policy is CommitPolicy.ALL_OR_NOTHING:
            return self.discard(
                current_state,
                reason="all-or-nothing policy rejected a batch containing failures",
            )

        committed = copy.deepcopy(current_state)
        candidate_ids: list[str] = []
        evidence_ids: list[str] = []
        for candidate in self.staging.candidates:
            if not any(item.get("id") == candidate["id"] for item in committed.candidates):
                committed.candidates.append(copy.deepcopy(candidate))
                candidate_ids.append(candidate["id"])
        for record in self.staging.evidence:
            if not any(item.id == record.id for item in committed.evidence):
                committed.evidence.append(copy.deepcopy(record))
                evidence_ids.append(record.id)
        if self.staging.resolved_claims:
            committed.assumptions = [
                item
                for item in committed.assumptions
                if _normalize(item.statement) not in self.staging.resolved_claims
            ]
            committed.unknowns = [
                item
                for item in committed.unknowns
                if _normalize(item.statement) not in self.staging.resolved_claims
            ]
        p0.validate_state(committed)
        self.status = (
            TransactionStatus.COMMITTED
            if candidate_ids or evidence_ids or self.staging.resolved_claims
            else TransactionStatus.NOOP
        )
        return TransactionResult(
            state=committed,
            status=self.status,
            committed_candidate_ids=candidate_ids,
            committed_evidence_ids=evidence_ids,
            discarded_reason=None,
        )

    def discard(
        self,
        current_state: p0.RuntimeState,
        *,
        reason: str,
    ) -> TransactionResult:
        self._ensure_open()
        if not isinstance(reason, str) or not reason.strip():
            raise TransactionError("discard reason must be a non-empty string")
        p0.validate_state(current_state)
        self.status = TransactionStatus.DISCARDED
        return TransactionResult(
            state=copy.deepcopy(current_state),
            status=self.status,
            committed_candidate_ids=[],
            committed_evidence_ids=[],
            discarded_reason=reason.strip(),
        )

    def _ensure_open(self) -> None:
        if self.status is not TransactionStatus.OPEN:
            raise TransactionError("transaction is already closed")


def _candidate(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TransactionError("candidate must be an object")
    normalized = copy.deepcopy(dict(value))
    for field_name in ("id", "core_mechanism"):
        field_value = normalized.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip():
            raise TransactionError(f"candidate.{field_name} must be non-empty")
    _canonical(normalized)
    return normalized


def _canonical(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise TransactionError(f"staging value must be canonical JSON: {exc}") from exc


def _mechanism(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())
