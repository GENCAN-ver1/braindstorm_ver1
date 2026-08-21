"""Copy-safe artifact writer bound to a durable quality-gate checkpoint."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from artifacts.manifest import (
    ArtifactManifest,
    QualityStatus,
    compute_sha256,
    manifest_path_for,
    save_manifest,
)
from runtime.checkpoint import CheckpointSession
from runtime.governor_modules import p0


class ArtifactWriterError(p0.ContractError):
    """Raised when an artifact cannot be safely written or approved."""


@dataclass(frozen=True)
class ArtifactWriteResult:
    manifest: ArtifactManifest
    manifest_path: Path


class ArtifactWriter:
    def write_for_session(
        self,
        session: CheckpointSession,
        artifact_path: str | Path,
        content: str | bytes | Mapping[str, Any] | Sequence[Any],
        *,
        quality_gate_id: str,
        quality_status: QualityStatus = QualityStatus.APPROVED,
        manifest_path: str | Path | None = None,
    ) -> ArtifactWriteResult:
        if not isinstance(session, CheckpointSession):
            raise ArtifactWriterError("session must be CheckpointSession")
        if not isinstance(quality_status, QualityStatus):
            raise ArtifactWriterError("quality_status must be QualityStatus")
        gate_id = _nonempty(quality_gate_id, "quality_gate_id")
        if quality_status is QualityStatus.APPROVED and not _is_commit(session.state):
            raise ArtifactWriterError("only a COMMIT checkpoint can approve an artifact")
        target = Path(artifact_path).resolve()
        destination_manifest = (
            manifest_path_for(target)
            if manifest_path is None
            else Path(manifest_path).resolve()
        )
        if target == session.path.resolve():
            raise ArtifactWriterError("artifact path cannot overwrite the Living Brief")
        if destination_manifest in {target, session.path.resolve()}:
            raise ArtifactWriterError("manifest path conflicts with a protected file")
        if target.exists() or destination_manifest.exists():
            raise ArtifactWriterError("artifact and manifest paths must be new")
        payload = _content_bytes(content)
        if not payload:
            raise ArtifactWriterError("artifact content must not be empty")

        session.update_progress(artifact_status="PENDING", quality_gate_id=gate_id)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.tmp")
        temporary.write_bytes(payload)
        temporary.replace(target)

        session.update_progress(
            artifact_status=quality_status.value,
            quality_gate_id=gate_id,
        )
        manifest = ArtifactManifest(
            artifact_path=str(target),
            sha256=compute_sha256(target),
            run_id=session.state.run.id,
            brief_revision=session.envelope.revision,
            quality_gate_id=gate_id,
            quality_status=quality_status,
            created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        )
        saved_path = save_manifest(destination_manifest, manifest)
        return ArtifactWriteResult(manifest, saved_path)


def _content_bytes(
    value: str | bytes | Mapping[str, Any] | Sequence[Any],
) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    if isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes))
    ):
        try:
            return (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise ArtifactWriterError("artifact content must be finite JSON") from exc
    raise ArtifactWriterError("artifact content type is unsupported")


def _is_commit(state: p0.RuntimeState) -> bool:
    return (
        state.run.status is p0.RunStatus.COMPLETED
        and state.result.exit_status is p0.ExitStatus.COMMIT
    )


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactWriterError(f"{path} must be a non-empty string")
    return value.strip()


__all__ = ["ArtifactWriteResult", "ArtifactWriter", "ArtifactWriterError"]
