#!/usr/bin/env python3
"""FV-08 clean-room acceptance runner and Full Version release report."""

from __future__ import annotations

import argparse
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
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.version_fingerprint import compute_version_fingerprint  # noqa: E402


MANIFEST_PATH = PROJECT_ROOT / "acceptance/manifest.json"
VERSION_INPUTS = PROJECT_ROOT / "evals/version-inputs.json"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "acceptance/report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "acceptance/report.md"
CLEANROOM_ROOT = PROJECT_ROOT / "tests/acceptance/cleanroom"


class FullVersionError(ValueError):
    """Raised when full-version inputs or evidence are malformed."""


def run_full_version_acceptance() -> dict[str, Any]:
    manifest = _load_json(MANIFEST_PATH)
    criteria = manifest["criteria"]
    if len(criteria) != 8 or any(item["status"] != "IMPLEMENTED" for item in criteria):
        raise FullVersionError("all eight acceptance criteria must be IMPLEMENTED")
    started_at = _now()
    prefix = f"fv08-{uuid.uuid4().hex}"
    cleanroom_brief = CLEANROOM_ROOT / f".{prefix}-CONCEPT_BRIEF.md"
    cleanroom_trace = cleanroom_brief.with_name(f"{cleanroom_brief.name}.trace.json")
    cleanup_paths = [
        cleanroom_brief,
        cleanroom_trace,
        cleanroom_brief.with_name(f".{cleanroom_brief.name}.cas.lock"),
        cleanroom_trace.with_name(f".{cleanroom_trace.name}.lock"),
    ]
    try:
        if cleanroom_brief.exists():
            raise FullVersionError("clean-room unexpectedly contains a prior Brief")
        cleanroom = _run_command(
            "clean-room-one-command",
            [
                sys.executable,
                "scripts/brainstorm.py",
                "run",
                "--request",
                "tests/acceptance/fixtures/ac01_one_command.json",
                "--config",
                "config/brainstorm-governor.example.yaml",
                "--brief",
                str(cleanroom_brief),
            ],
        )
        cleanroom_payload = _parse_json_output(cleanroom["stdout"])
        cleanroom_passed = (
            cleanroom["return_code"] == 0
            and cleanroom_brief.is_file()
            and cleanroom_payload.get("exit_status")
            in {"EXPLORE", "RESEARCH_REQUIRED", "ITERATE", "COMMIT", "PARK", "NEEDS_INPUT"}
            and cleanroom_payload.get("resumed") is False
        )

        acceptance_tests = _run_command(
            "ac-01-through-ac-08",
            [
                sys.executable,
                "-m",
                "unittest",
                *[item["test_id"] for item in criteria],
                "-q",
            ],
        )
        p0_p6 = _run_command(
            "p0-p6-contract-regression",
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                ".agents/skills/brainstorm-governor/tests",
                "-q",
            ],
        )
        regression_gate = _run_command(
            "fv07-regression-gate",
            [sys.executable, "ci/regression_gate.py", "check"],
        )
        regression_payload = _parse_json_output(regression_gate["stdout"])
        skill_validation = _run_skill_validation()
    finally:
        for path in cleanup_paths:
            path.unlink(missing_ok=True)

    xfail_xpass = _xfail_xpass_count(acceptance_tests["transcript"])
    gates = {
        "clean_room": cleanroom_passed,
        "all_acceptance_criteria": acceptance_tests["return_code"] == 0,
        "p0_p6_regression": (
            p0_p6["return_code"] == 0 and "Ran 108 tests" in p0_p6["transcript"]
        ),
        "version_regression_gate": (
            regression_gate["return_code"] == 0
            and regression_payload.get("result") == "ALLOW"
        ),
        "skill_validation": (
            skill_validation["return_code"] == 0
            and "Skill is valid!" in skill_validation["transcript"]
        ),
        "xfail_xpass_zero": xfail_xpass == 0,
    }
    all_passed = all(gates.values())
    criterion_reports = [
        _criterion_report(item, passed=acceptance_tests["return_code"] == 0)
        for item in criteria
    ]
    report = {
        "schema_version": 1,
        "suite_id": manifest["suite_id"],
        "status": "FULL_VERSION" if all_passed else "RELEASE_BLOCKED",
        "result": "PASS" if all_passed else "FAIL",
        "version_fingerprint": compute_version_fingerprint(
            VERSION_INPUTS, project_root=PROJECT_ROOT
        ).to_dict(),
        "started_at": started_at,
        "finished_at": _now(),
        "clean_room": {
            "root": CLEANROOM_ROOT.relative_to(PROJECT_ROOT).as_posix(),
            "prior_brief": False,
            "legal_exit_status": cleanroom_payload.get("exit_status"),
            "transcript_sha256": cleanroom["transcript_sha256"],
        },
        "criteria": criterion_reports,
        "gates": gates,
        "xfail_xpass_count": xfail_xpass,
        "commands": [
            _command_evidence(cleanroom),
            _command_evidence(acceptance_tests),
            _command_evidence(p0_p6),
            _command_evidence(regression_gate),
            _command_evidence(skill_validation),
        ],
        "release_evidence": _release_evidence(),
        "failure_reasons": [name for name, passed in gates.items() if not passed],
    }
    validate_full_report(report)
    return report


def validate_full_report(value: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "suite_id",
        "status",
        "result",
        "version_fingerprint",
        "started_at",
        "finished_at",
        "clean_room",
        "criteria",
        "gates",
        "xfail_xpass_count",
        "commands",
        "release_evidence",
        "failure_reasons",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise FullVersionError("full-version report has invalid keys")
    if value["schema_version"] != 1:
        raise FullVersionError("unsupported full-version report schema")
    if value["status"] not in {"FULL_VERSION", "RELEASE_BLOCKED"}:
        raise FullVersionError("full-version status is invalid")
    if value["result"] not in {"PASS", "FAIL"}:
        raise FullVersionError("full-version result is invalid")
    if not isinstance(value["criteria"], list) or len(value["criteria"]) != 8:
        raise FullVersionError("full-version report must contain eight criteria")
    if [item.get("id") for item in value["criteria"]] != [f"AC-{i:02d}" for i in range(1, 9)]:
        raise FullVersionError("full-version criteria IDs are invalid")
    if not isinstance(value["gates"], Mapping) or len(value["gates"]) != 6:
        raise FullVersionError("full-version gates are invalid")
    if type(value["xfail_xpass_count"]) is not int or value["xfail_xpass_count"] < 0:
        raise FullVersionError("xfail_xpass_count must be an integer >= 0")
    passed = (
        value["result"] == "PASS"
        and value["status"] == "FULL_VERSION"
        and all(value["gates"].values())
        and value["xfail_xpass_count"] == 0
        and not value["failure_reasons"]
        and all(item.get("result") == "PASS" for item in value["criteria"])
    )
    if value["status"] == "FULL_VERSION" and not passed:
        raise FullVersionError("FULL_VERSION report contains failed evidence")


def save_full_report(
    report: Mapping[str, Any],
    json_path: str | Path = DEFAULT_REPORT_JSON,
    markdown_path: str | Path = DEFAULT_REPORT_MD,
) -> tuple[Path, Path]:
    validate_full_report(report)
    json_target = _atomic_write(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    markdown_target = _atomic_write(markdown_path, render_markdown(report))
    return json_target, markdown_target


def render_markdown(report: Mapping[str, Any]) -> str:
    validate_full_report(report)
    lines = [
        "# Brainstorm Governor Full Version Acceptance Report",
        "",
        f"- Status: `{report['status']}`",
        f"- Result: `{report['result']}`",
        f"- Fingerprint: `{report['version_fingerprint']['aggregate']}`",
        f"- Finished: `{report['finished_at']}`",
        f"- xfail/xpass: `{report['xfail_xpass_count']}`",
        "",
        "## Acceptance Criteria",
        "",
        "| AC | Result | Test | Evidence |",
        "|---|---|---|---|",
    ]
    for item in report["criteria"]:
        evidence = ", ".join(record["path"] for record in item["evidence"])
        lines.append(
            f"| {item['id']} | {item['result']} | `{item['test_id']}` | {evidence} |"
        )
    lines.extend(["", "## Release Gates", ""])
    for name, passed in report["gates"].items():
        lines.append(f"- {name}: `{'PASS' if passed else 'FAIL'}`")
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "This report proves the checked-in local runtime and acceptance contracts. "
            "External Research, Worker, Evaluator, and Council Provider integrations "
            "remain deployment-specific and are not claimed by this report.",
            "",
        ]
    )
    return "\n".join(lines)


def _criterion_report(item: Mapping[str, Any], *, passed: bool) -> dict[str, Any]:
    module_name = ".".join(item["test_id"].split(".")[:-2])
    module_path = PROJECT_ROOT / (module_name.replace(".", "/") + ".py")
    evidence_paths = [module_path, *[PROJECT_ROOT / path for path in item["fixtures"]]]
    evidence = [_evidence(path) for path in evidence_paths]
    return {
        "id": item["id"],
        "test_id": item["test_id"],
        "result": "PASS" if passed else "FAIL",
        "evidence": evidence,
        "expected_artifacts": list(item["expected_artifacts"]),
    }


def _release_evidence() -> list[dict[str, str]]:
    paths = [
        PROJECT_ROOT / "acceptance/manifest.json",
        PROJECT_ROOT / "evals/baseline-manifest.json",
        PROJECT_ROOT / "evals/live-report.json",
        PROJECT_ROOT / "evals/gate-report.json",
        PROJECT_ROOT / ".agents/skills/brainstorm-governor/SKILL.md",
    ]
    return [_evidence(path) for path in paths]


def _evidence(path: Path) -> dict[str, str]:
    target = path.resolve()
    if not target.is_file():
        raise FullVersionError(f"missing release evidence: {target}")
    return {
        "path": target.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }


def _run_skill_validation() -> dict[str, Any]:
    return _run_command(
        "skill-validation",
        [
            sys.executable,
            "ci/validate_skill.py",
            str(PROJECT_ROOT / ".agents/skills/brainstorm-governor"),
        ],
    )


def _run_command(
    name: str,
    command: Sequence[str],
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    completed = subprocess.run(
        list(command),
        cwd=PROJECT_ROOT,
        env=None if environment is None else dict(environment),
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


def _parse_json_output(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return dict(value) if isinstance(value, Mapping) else {}


def _xfail_xpass_count(transcript: str) -> int:
    lowered = transcript.casefold()
    return lowered.count("expected failure") + lowered.count("unexpected success")


def _atomic_write(path: str | Path, text: str) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(target)
    return target


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FullVersionError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, Mapping):
        raise FullVersionError(f"{path} must contain an object")
    return dict(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "validate-report"])
    parser.add_argument("--report-json", default=str(DEFAULT_REPORT_JSON))
    parser.add_argument("--report-md", default=str(DEFAULT_REPORT_MD))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "validate-report":
            report = _load_json(Path(args.report_json))
            validate_full_report(report)
        else:
            report = run_full_version_acceptance()
            save_full_report(report, args.report_json, args.report_md)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["result"] == "PASS" else 1
    except (FullVersionError, ValueError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "FullVersionError",
    "render_markdown",
    "run_full_version_acceptance",
    "save_full_report",
    "validate_full_report",
]
