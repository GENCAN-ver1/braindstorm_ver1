"""Final FV-06 gate: revalidate checkpoint, manifest, artifact, and P6 outcome."""

from __future__ import annotations

import hmac
from pathlib import Path
from typing import Sequence

from artifacts.manifest import (
    ArtifactManifestError,
    QualityStatus,
    compute_sha256,
    load_manifest,
)
from runtime.checkpoint import (
    CheckpointSession,
    checkpoint_from_state,
    validate_envelope,
)
from runtime.governor_modules import p0, p2, p6
from runtime.state_fingerprint import fingerprint_state


class HandoffGateError(p0.ContractError):
    """Raised when the current approved artifact cannot produce handoff."""


class HandoffGate:
    def build(
        self,
        session: CheckpointSession,
        outcome: p6.QualityGateOutcome,
        manifest_path: str | Path,
        *,
        acceptance_criteria: Sequence[str],
        risks: Sequence[str],
        next_validation: str,
    ) -> p6.FinalHandoff:
        if not isinstance(session, CheckpointSession):
            raise HandoffGateError("session must be CheckpointSession")
        if not session.path.is_file():
            raise HandoffGateError("current Living Brief does not exist")
        try:
            current_brief = p2.load_brief(session.path)
            current_envelope = checkpoint_from_state(current_brief.runtime_state)
            if current_envelope is None:
                raise HandoffGateError("current Living Brief has no checkpoint envelope")
            validate_envelope(current_envelope, current_brief.runtime_state)
        except p0.ContractError as exc:
            raise HandoffGateError(f"current Living Brief is invalid: {exc}") from exc
        if (
            current_envelope.revision != session.envelope.revision
            or current_envelope.run_id != session.envelope.run_id
            or current_envelope.state_hash != session.envelope.state_hash
        ):
            raise HandoffGateError("session is stale relative to the current Living Brief")
        if not _is_commit(current_brief.runtime_state):
            raise HandoffGateError("handoff requires the current COMMIT checkpoint")
        if current_envelope.artifact_status != QualityStatus.APPROVED.value:
            raise HandoffGateError("checkpoint artifact_status is not APPROVED")
        if not isinstance(outcome, p6.QualityGateOutcome) or not outcome.approved:
            raise HandoffGateError("handoff requires an approved P6 outcome")
        if outcome.state.run.id != current_brief.runtime_state.run.id:
            raise HandoffGateError("quality outcome belongs to another run")
        if not _is_commit(outcome.state):
            raise HandoffGateError("quality outcome is not COMMIT")
        if fingerprint_state(p0.state_to_dict(outcome.state)) != current_envelope.state_hash:
            raise HandoffGateError("quality outcome does not match the current Brief state")

        try:
            manifest = load_manifest(manifest_path)
        except ArtifactManifestError as exc:
            raise HandoffGateError(str(exc)) from exc
        if manifest.quality_status is not QualityStatus.APPROVED:
            raise HandoffGateError("artifact quality_status is not APPROVED")
        if manifest.run_id != current_brief.runtime_state.run.id:
            raise HandoffGateError("artifact belongs to another run")
        if manifest.brief_revision != current_envelope.revision:
            raise HandoffGateError("artifact belongs to another Brief revision")
        if (
            current_envelope.quality_gate_id is None
            or manifest.quality_gate_id != current_envelope.quality_gate_id
        ):
            raise HandoffGateError("artifact was not approved by the current quality gate")

        artifact_path = Path(manifest.artifact_path).resolve()
        if not artifact_path.is_file() or artifact_path.stat().st_size < 1:
            raise HandoffGateError("approved artifact is missing or empty")
        try:
            actual_sha256 = compute_sha256(artifact_path)
        except ArtifactManifestError as exc:
            raise HandoffGateError(str(exc)) from exc
        if not hmac.compare_digest(actual_sha256, manifest.sha256):
            raise HandoffGateError("approved artifact SHA-256 mismatch")

        try:
            return p6.build_final_handoff(
                outcome,
                approved_artifact_path=artifact_path,
                acceptance_criteria=acceptance_criteria,
                risks=risks,
                next_validation=next_validation,
            )
        except p0.ContractError as exc:
            raise HandoffGateError(str(exc)) from exc


def _is_commit(state: p0.RuntimeState) -> bool:
    return (
        state.run.status is p0.RunStatus.COMPLETED
        and state.result.exit_status is p0.ExitStatus.COMMIT
    )


__all__ = ["HandoffGate", "HandoffGateError"]
