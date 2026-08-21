"""Strict seven-field manifest for quality-gated artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


MANIFEST_FIELDS = (
    "artifact_path",
    "sha256",
    "run_id",
    "brief_revision",
    "quality_gate_id",
    "quality_status",
    "created_at",
)


class ArtifactManifestError(ValueError):
    """Raised when an artifact manifest violates the FV-06 contract."""


class QualityStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ArtifactManifest:
    artifact_path: str
    sha256: str
    run_id: str
    brief_revision: int
    quality_gate_id: str
    quality_status: QualityStatus
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        validate_manifest(self)
        return {
            "artifact_path": self.artifact_path,
            "sha256": self.sha256,
            "run_id": self.run_id,
            "brief_revision": self.brief_revision,
            "quality_gate_id": self.quality_gate_id,
            "quality_status": self.quality_status.value,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ArtifactManifest":
        if not isinstance(value, Mapping) or set(value) != set(MANIFEST_FIELDS):
            raise ArtifactManifestError("artifact manifest must have exactly seven fields")
        try:
            quality_status = QualityStatus(value["quality_status"])
        except (TypeError, ValueError) as exc:
            raise ArtifactManifestError("quality_status is invalid") from exc
        manifest = cls(
            artifact_path=value["artifact_path"],
            sha256=value["sha256"],
            run_id=value["run_id"],
            brief_revision=value["brief_revision"],
            quality_gate_id=value["quality_gate_id"],
            quality_status=quality_status,
            created_at=value["created_at"],
        )
        validate_manifest(manifest)
        return manifest


def validate_manifest(manifest: ArtifactManifest) -> None:
    if not isinstance(manifest, ArtifactManifest):
        raise ArtifactManifestError("manifest must be ArtifactManifest")
    artifact_path = Path(_nonempty(manifest.artifact_path, "artifact_path"))
    if not artifact_path.is_absolute():
        raise ArtifactManifestError("artifact_path must be absolute")
    digest = _nonempty(manifest.sha256, "sha256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ArtifactManifestError("sha256 must be a lowercase SHA-256 digest")
    _nonempty(manifest.run_id, "run_id")
    if type(manifest.brief_revision) is not int or manifest.brief_revision < 0:
        raise ArtifactManifestError("brief_revision must be an integer >= 0")
    _nonempty(manifest.quality_gate_id, "quality_gate_id")
    if not isinstance(manifest.quality_status, QualityStatus):
        raise ArtifactManifestError("quality_status must be QualityStatus")
    created_at = _nonempty(manifest.created_at, "created_at")
    try:
        parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ArtifactManifestError("created_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ArtifactManifestError("created_at must include a timezone")


def compute_sha256(path: str | Path) -> str:
    target = Path(path)
    if not target.is_file():
        raise ArtifactManifestError("artifact must be an existing file")
    digest = hashlib.sha256()
    with target.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_path_for(artifact_path: str | Path) -> Path:
    artifact = Path(artifact_path).resolve()
    return artifact.with_name(f"{artifact.name}.manifest.json")


def save_manifest(path: str | Path, manifest: ArtifactManifest) -> Path:
    destination = Path(path).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_manifest(path: str | Path) -> ArtifactManifest:
    source = Path(path).resolve()
    if not source.is_file():
        raise ArtifactManifestError("artifact manifest does not exist")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactManifestError("artifact manifest is unreadable") from exc
    return ArtifactManifest.from_dict(value)


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ArtifactManifestError(f"{path} must be a non-empty string")
    return value.strip()


__all__ = [
    "MANIFEST_FIELDS",
    "ArtifactManifest",
    "ArtifactManifestError",
    "QualityStatus",
    "compute_sha256",
    "load_manifest",
    "manifest_path_for",
    "save_manifest",
    "validate_manifest",
]

