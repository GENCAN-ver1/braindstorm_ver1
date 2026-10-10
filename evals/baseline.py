"""Explicitly approved, immutable FV-07 live-regression baseline manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from evals.live_runner import load_live_report
from evals.version_fingerprint import VersionFingerprint


BASELINE_SCHEMA_VERSION = 1


class BaselineError(ValueError):
    """Raised when a baseline is invalid or approval is not explicit."""


def approve_baseline(
    live_report_path: str | Path,
    output_path: str | Path,
    *,
    approval_id: str,
    reviewer: str,
    explicitly_approved: bool = False,
    project_root: str | Path | None = None,
) -> dict[str, Any]:
    if explicitly_approved is not True:
        raise BaselineError("baseline update requires explicit approval")
    approval = _nonempty(approval_id, "approval_id")
    approved_by = _nonempty(reviewer, "reviewer")
    report_path = Path(live_report_path).resolve()
    root = Path(project_root or Path(__file__).parents[1]).resolve()
    try:
        relative_report = report_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise BaselineError("live report must stay inside project_root") from exc
    report = load_live_report(report_path)
    if report["result"] != "PASS":
        raise BaselineError("failed live report cannot become a baseline")
    if report["mocked"] is not False:
        raise BaselineError("mock-only report cannot become a baseline")
    fingerprint = VersionFingerprint.from_dict(report["version_fingerprint"])
    baseline = {
        "schema_version": BASELINE_SCHEMA_VERSION,
        "baseline_id": f"baseline:{fingerprint.aggregate}",
        "version_fingerprint": fingerprint.to_dict(),
        "live_report_path": relative_report,
        "live_report_sha256": _sha256(report_path),
        "result": "PASS",
        "approved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "approval": {
            "explicit": True,
            "approval_id": approval,
            "reviewer": approved_by,
        },
        "metrics": dict(report["metrics"]),
        "cost": dict(report["cost"]),
        "thresholds": dict(report["thresholds"]),
        "case_count": len(report["core_cases"]) + len(report["supplemental_cases"]),
    }
    validate_baseline(baseline)
    save_baseline(output_path, baseline)
    return baseline


def validate_baseline(value: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "baseline_id",
        "version_fingerprint",
        "live_report_path",
        "live_report_sha256",
        "result",
        "approved_at",
        "approval",
        "metrics",
        "cost",
        "thresholds",
        "case_count",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise BaselineError("baseline manifest has invalid keys")
    if value["schema_version"] != BASELINE_SCHEMA_VERSION:
        raise BaselineError("unsupported baseline schema")
    fingerprint = VersionFingerprint.from_dict(value["version_fingerprint"])
    if value["baseline_id"] != f"baseline:{fingerprint.aggregate}":
        raise BaselineError("baseline_id conflicts with its fingerprint")
    _nonempty(value["live_report_path"], "live_report_path")
    digest = _nonempty(value["live_report_sha256"], "live_report_sha256")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise BaselineError("live_report_sha256 is invalid")
    if value["result"] != "PASS":
        raise BaselineError("baseline result must be PASS")
    _nonempty(value["approved_at"], "approved_at")
    approval = value["approval"]
    if not isinstance(approval, Mapping) or set(approval) != {
        "explicit",
        "approval_id",
        "reviewer",
    }:
        raise BaselineError("baseline approval is invalid")
    if approval["explicit"] is not True:
        raise BaselineError("baseline approval must be explicit")
    _nonempty(approval["approval_id"], "approval.approval_id")
    _nonempty(approval["reviewer"], "approval.reviewer")
    for field in ("metrics", "cost", "thresholds"):
        if not isinstance(value[field], Mapping):
            raise BaselineError(f"baseline {field} must be an object")
    if type(value["case_count"]) is not int or value["case_count"] < 16:
        raise BaselineError("baseline case_count must be at least 16")


def load_baseline(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BaselineError(f"cannot load baseline: {exc}") from exc
    validate_baseline(value)
    return dict(value)


def save_baseline(path: str | Path, baseline: Mapping[str, Any]) -> Path:
    validate_baseline(baseline)
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(baseline, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(target)
    return target


def verify_baseline_report(
    baseline: Mapping[str, Any], *, project_root: str | Path
) -> dict[str, Any]:
    validate_baseline(baseline)
    root = Path(project_root).resolve()
    report_path = (root / baseline["live_report_path"]).resolve()
    try:
        report_path.relative_to(root)
    except ValueError as exc:
        raise BaselineError("baseline live report escaped project_root") from exc
    if not report_path.is_file() or _sha256(report_path) != baseline["live_report_sha256"]:
        raise BaselineError("baseline live report is missing or hash-mismatched")
    report = load_live_report(report_path)
    if report["version_fingerprint"] != baseline["version_fingerprint"]:
        raise BaselineError("baseline live report fingerprint mismatch")
    if report["result"] != "PASS" or report["mocked"] is not False:
        raise BaselineError("baseline live report is not an accepted PASS")
    return report


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BaselineError(f"{path} must be a non-empty string")
    return value.strip()


__all__ = [
    "BaselineError",
    "approve_baseline",
    "load_baseline",
    "save_baseline",
    "validate_baseline",
    "verify_baseline_report",
]
