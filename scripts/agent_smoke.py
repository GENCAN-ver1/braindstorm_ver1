#!/usr/bin/env python3
"""Run the checked-in brainstorm-governor as a user-facing smoke test."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).parents[1]
DEFAULT_REPORT = PROJECT_ROOT / "acceptance/agent-functional-report.json"
CLEANROOM_ROOT = PROJECT_ROOT / "tests/acceptance/cleanroom"
LEGAL_STOPS = {
    "EXPLORE",
    "RESEARCH_REQUIRED",
    "ITERATE",
    "COMMIT",
    "PARK",
    "NEEDS_INPUT",
}


class SmokeError(ValueError):
    """Raised when smoke inputs or outputs violate the runtime contract."""


def run_agent_smoke() -> dict[str, Any]:
    started_at = _now()
    prefix = f".agent-smoke-{uuid.uuid4().hex}"
    brief = CLEANROOM_ROOT / f"{prefix}-CONCEPT_BRIEF.md"
    trace = brief.with_name(f"{brief.name}.trace.json")
    cleanup_paths = [
        brief,
        trace,
        brief.with_name(f".{brief.name}.cas.lock"),
        brief.with_name(f".{brief.name}.tmp"),
        trace.with_name(f".{trace.name}.lock"),
        trace.with_name(f".{trace.name}.tmp"),
    ]
    commands: list[dict[str, Any]] = []
    try:
        first = _run_command(
            "new-request",
            [
                sys.executable,
                "scripts/brainstorm.py",
                "run",
                "--request",
                "tests/acceptance/fixtures/ac01_one_command.json",
                "--config",
                "config/brainstorm-governor.example.yaml",
                "--brief",
                str(brief),
            ],
        )
        commands.append(first)
        first_payload = _parse_json(first["stdout"])

        second = _run_command(
            "brief-resume",
            [
                sys.executable,
                "scripts/brainstorm.py",
                "run",
                "--request",
                "tests/acceptance/fixtures/ac01_one_command.json",
                "--config",
                "config/brainstorm-governor.example.yaml",
                "--brief",
                str(brief),
            ],
        )
        commands.append(second)
        second_payload = _parse_json(second["stdout"])
        trace_payload = _load_json(trace)
        event_kinds = {item.get("kind") for item in trace_payload.get("events", [])}

        regression = _run_command(
            "version-regression-gate",
            [sys.executable, "ci/regression_gate.py", "check"],
        )
        commands.append(regression)
        regression_payload = _parse_json(regression["stdout"])

        release = _run_command(
            "full-version-report-validation",
            [sys.executable, "acceptance/full_version.py", "validate-report"],
        )
        commands.append(release)
        release_payload = _parse_json(release["stdout"])

        skill = _run_command(
            "skill-validation",
            [
                sys.executable,
                "ci/validate_skill.py",
                ".agents/skills/brainstorm-governor",
            ],
        )
        commands.append(skill)

        checks = {
            "one_command_legal_stop": (
                first["return_code"] == 0
                and first_payload.get("exit_status") in LEGAL_STOPS
                and first_payload.get("resumed") is False
                and brief.is_file()
            ),
            "brief_resume_is_idempotent": (
                second["return_code"] == 0
                and second_payload.get("resumed") is True
                and second_payload.get("run_id") == first_payload.get("run_id")
                and second_payload.get("exit_status") == first_payload.get("exit_status")
            ),
            "durable_trace_linked": (
                trace.is_file()
                and trace_payload.get("run_id") == first_payload.get("run_id")
                and {"CHECKPOINT_SAVED", "EXIT_STATUS", "RECOVERY"} <= event_kinds
            ),
            "version_regression_allowed": (
                regression["return_code"] == 0
                and regression_payload.get("result") == "ALLOW"
                and regression_payload.get("offline_contract", {}).get("test_count")
                == 108
            ),
            "full_version_report_current": (
                release["return_code"] == 0
                and release_payload.get("status") == "FULL_VERSION"
                and release_payload.get("result") == "PASS"
            ),
            "skill_structure_valid": (
                skill["return_code"] == 0 and "Skill is valid!" in skill["transcript"]
            ),
        }
        passed = all(checks.values())
        report = {
            "schema_version": 1,
            "suite_id": "brainstorm-governor-agent-functional-smoke",
            "result": "PASS" if passed else "FAIL",
            "started_at": started_at,
            "finished_at": _now(),
            "checks": checks,
            "runtime": {
                "run_id": first_payload.get("run_id"),
                "mode": first_payload.get("mode"),
                "exit_status": first_payload.get("exit_status"),
                "resumed_exit_status": second_payload.get("exit_status"),
                "trace_event_count": len(trace_payload.get("events", [])),
                "trace_usage_summary": trace_payload.get("summary"),
                "version_fingerprint": release_payload.get(
                    "version_fingerprint", {}
                ).get("aggregate"),
            },
            "commands": [_command_evidence(item) for item in commands],
            "boundaries": {
                "default_full_cycle_stages": ["P0", "P1", "P2"],
                "p4_p5_p6_available_via_validated_apis": True,
                "external_provider_used": False,
                "external_provider_cost": "UNAVAILABLE",
                "council_http_adapter_connected": False,
            },
            "failure_reasons": [name for name, ok in checks.items() if not ok],
        }
        validate_smoke_report(report)
        return report
    finally:
        for path in cleanup_paths:
            path.unlink(missing_ok=True)


def validate_smoke_report(value: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "suite_id",
        "result",
        "started_at",
        "finished_at",
        "checks",
        "runtime",
        "commands",
        "boundaries",
        "failure_reasons",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise SmokeError("agent smoke report has invalid keys")
    if value["schema_version"] != 1:
        raise SmokeError("unsupported agent smoke report schema")
    if value["result"] not in {"PASS", "FAIL"}:
        raise SmokeError("agent smoke result is invalid")
    if not isinstance(value["checks"], Mapping) or len(value["checks"]) != 6:
        raise SmokeError("agent smoke must contain six checks")
    passed = (
        value["result"] == "PASS"
        and all(value["checks"].values())
        and not value["failure_reasons"]
    )
    if value["result"] == "PASS" and not passed:
        raise SmokeError("PASS smoke report contains failed checks")


def save_smoke_report(
    report: Mapping[str, Any], path: str | Path = DEFAULT_REPORT
) -> Path:
    validate_smoke_report(report)
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(target)
    return target


def _run_command(name: str, command: Sequence[str]) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    transcript = (completed.stdout or "") + (completed.stderr or "")
    return {
        "name": name,
        "command": list(command),
        "return_code": completed.returncode,
        "duration_ms": round((time.perf_counter() - started) * 1000, 3),
        "stdout": completed.stdout or "",
        "transcript": transcript,
        "transcript_sha256": hashlib.sha256(
            transcript.encode("utf-8")
        ).hexdigest(),
    }


def _command_evidence(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": value["name"],
        "command": list(value["command"]),
        "return_code": value["return_code"],
        "duration_ms": value["duration_ms"],
        "transcript_sha256": value["transcript_sha256"],
    }


def _parse_json(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise SmokeError(f"{path} must contain an object")
    return dict(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    try:
        report = run_agent_smoke()
        save_smoke_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 1
    except (SmokeError, OSError, ValueError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["run_agent_smoke", "save_smoke_report", "validate_smoke_report"]
