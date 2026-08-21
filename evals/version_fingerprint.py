"""Stable FV-07 fingerprint over prompts, model, adapters, schemas, and pricing."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


FINGERPRINT_SCHEMA_VERSION = 1
EXPECTED_INPUT_KEYS = {
    "schema_version",
    "governor_prompt_paths",
    "evaluator_prompt_paths",
    "model",
    "provider_adapter",
    "citation_checker",
    "output_schema",
    "pricing_table_path",
}


class VersionFingerprintError(ValueError):
    """Raised when version inputs are incomplete, unsafe, or malformed."""


@dataclass(frozen=True)
class VersionFingerprint:
    schema_version: int
    aggregate: str
    dimensions: dict[str, str]

    def to_dict(self) -> dict[str, Any]:
        validate_fingerprint(self)
        return {
            "schema_version": self.schema_version,
            "aggregate": self.aggregate,
            "dimensions": dict(self.dimensions),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "VersionFingerprint":
        if not isinstance(value, Mapping) or set(value) != {
            "schema_version",
            "aggregate",
            "dimensions",
        }:
            raise VersionFingerprintError("version fingerprint has invalid keys")
        dimensions = value["dimensions"]
        if not isinstance(dimensions, Mapping):
            raise VersionFingerprintError("fingerprint dimensions must be an object")
        fingerprint = cls(
            schema_version=value["schema_version"],
            aggregate=value["aggregate"],
            dimensions=dict(dimensions),
        )
        validate_fingerprint(fingerprint)
        return fingerprint


def compute_version_fingerprint(
    inputs_path: str | Path,
    *,
    project_root: str | Path | None = None,
) -> VersionFingerprint:
    source = Path(inputs_path).resolve()
    root = Path(project_root or source.parents[1]).resolve()
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionFingerprintError(f"cannot load version inputs: {exc}") from exc
    if not isinstance(value, Mapping) or set(value) != EXPECTED_INPUT_KEYS:
        raise VersionFingerprintError("version inputs have invalid keys")
    if value["schema_version"] != FINGERPRINT_SCHEMA_VERSION:
        raise VersionFingerprintError("unsupported version-input schema")

    governor_paths = _paths(value["governor_prompt_paths"], root, "governor_prompt_paths")
    evaluator_paths = _paths(value["evaluator_prompt_paths"], root, "evaluator_prompt_paths")
    model = _exact_mapping(
        value["model"], {"provider", "model_id", "reasoning_mode"}, "model"
    )
    adapter = _versioned_paths(value["provider_adapter"], root, "provider_adapter")
    checker = _versioned_paths(value["citation_checker"], root, "citation_checker")
    schema = _versioned_paths(value["output_schema"], root, "output_schema")
    pricing_path = _path(value["pricing_table_path"], root, "pricing_table_path")
    try:
        pricing = json.loads(pricing_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VersionFingerprintError(f"pricing table is invalid: {exc}") from exc
    pricing_version = _nonempty(
        pricing.get("version") if isinstance(pricing, Mapping) else None,
        "pricing.version",
    )

    dimensions = {
        "governor_prompt": _bundle_digest(governor_paths, root),
        "evaluator_prompt": _bundle_digest(evaluator_paths, root),
        "provider": _digest({"provider": _nonempty(model["provider"], "model.provider")}),
        "model": _digest(
            {
                "provider": _nonempty(model["provider"], "model.provider"),
                "model_id": _nonempty(model["model_id"], "model.model_id"),
                "reasoning_mode": _nonempty(
                    model["reasoning_mode"], "model.reasoning_mode"
                ),
            }
        ),
        "adapter": _digest(adapter),
        "citation_checker": _digest(checker),
        "schema": _digest(schema),
        "pricing": _digest(
            {
                "version": pricing_version,
                "path": _relative(pricing_path, root),
                "sha256": _file_digest(pricing_path),
            }
        ),
    }
    fingerprint = VersionFingerprint(
        FINGERPRINT_SCHEMA_VERSION,
        _digest(dimensions),
        dimensions,
    )
    validate_fingerprint(fingerprint)
    return fingerprint


def changed_dimensions(
    baseline: VersionFingerprint, current: VersionFingerprint
) -> list[str]:
    validate_fingerprint(baseline)
    validate_fingerprint(current)
    names = sorted(set(baseline.dimensions) | set(current.dimensions))
    return [
        name
        for name in names
        if baseline.dimensions.get(name) != current.dimensions.get(name)
    ]


def validate_fingerprint(value: VersionFingerprint) -> None:
    if not isinstance(value, VersionFingerprint):
        raise VersionFingerprintError("fingerprint must be VersionFingerprint")
    if value.schema_version != FINGERPRINT_SCHEMA_VERSION:
        raise VersionFingerprintError("unsupported fingerprint schema")
    _fingerprint(value.aggregate, "aggregate")
    required = {
        "governor_prompt",
        "evaluator_prompt",
        "provider",
        "model",
        "adapter",
        "citation_checker",
        "schema",
        "pricing",
    }
    if set(value.dimensions) != required:
        raise VersionFingerprintError("fingerprint dimensions are incomplete")
    for name, fingerprint in value.dimensions.items():
        _fingerprint(fingerprint, f"dimensions.{name}")
    if value.aggregate != _digest(value.dimensions):
        raise VersionFingerprintError("aggregate fingerprint is inconsistent")


def _versioned_paths(value: Any, root: Path, path: str) -> dict[str, Any]:
    item = _exact_mapping(value, {"version", "paths"}, path)
    paths = _paths(item["paths"], root, f"{path}.paths")
    return {
        "version": _nonempty(item["version"], f"{path}.version"),
        "files": _bundle_records(paths, root),
    }


def _paths(value: Any, root: Path, path: str) -> list[Path]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or not value:
        raise VersionFingerprintError(f"{path} must be a non-empty array")
    result = [_path(item, root, f"{path}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise VersionFingerprintError(f"{path} must not contain duplicates")
    return result


def _path(value: Any, root: Path, path: str) -> Path:
    text = _nonempty(value, path)
    target = (root / text).resolve() if not Path(text).is_absolute() else Path(text).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise VersionFingerprintError(f"{path} must stay inside project_root") from exc
    if not target.is_file():
        raise VersionFingerprintError(f"{path} does not exist: {target}")
    return target


def _bundle_digest(paths: Sequence[Path], root: Path) -> str:
    return _digest(_bundle_records(paths, root))


def _bundle_records(paths: Sequence[Path], root: Path) -> list[dict[str, str]]:
    return [
        {"path": _relative(path, root), "sha256": _file_digest(path)}
        for path in sorted(paths, key=lambda item: _relative(item, root))
    ]


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "version:v1:sha256:" + hashlib.sha256(payload).hexdigest()


def _fingerprint(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.startswith("version:v1:sha256:"):
        raise VersionFingerprintError(f"{path} must be a version fingerprint")
    if len(value) != len("version:v1:sha256:") + 64:
        raise VersionFingerprintError(f"{path} has invalid digest length")
    return value


def _exact_mapping(value: Any, expected: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise VersionFingerprintError(f"{path} has invalid keys")
    return value


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise VersionFingerprintError(f"{path} must be a non-empty string")
    return value.strip()


__all__ = [
    "VersionFingerprint",
    "VersionFingerprintError",
    "changed_dimensions",
    "compute_version_fingerprint",
    "validate_fingerprint",
]
