#!/usr/bin/env python3
"""Run FV-07 regression against real local runtime APIs and acceptance paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.local_runtime_scenarios import LocalRuntimeScenarioRunner  # noqa: E402
from evals.version_fingerprint import (  # noqa: E402
    VersionFingerprint,
    compute_version_fingerprint,
)
from runtime.governor_modules import p0  # noqa: E402

import p6_regression as regression  # noqa: E402


LIVE_REPORT_SCHEMA_VERSION = 1
DEFAULT_FIXTURE = (
    PROJECT_ROOT
    / ".agents"
    / "skills"
    / "brainstorm-governor"
    / "evals"
    / "p6_regression.json"
)
DEFAULT_INPUTS = PROJECT_ROOT / "evals" / "version-inputs.json"
DEFAULT_THRESHOLDS = PROJECT_ROOT / "evals" / "thresholds.json"
DEFAULT_SUPPLEMENTAL = PROJECT_ROOT / "evals" / "supplemental-cases.json"
DEFAULT_REPORT = PROJECT_ROOT / "evals" / "live-report.json"
WORK_ROOT = PROJECT_ROOT / "evals" / "work"


class LiveRegressionError(p0.ContractError):
    """Raised when a live run or report violates the FV-07 contract."""


def run_live_regression(
    *,
    fixture_path: str | Path = DEFAULT_FIXTURE,
    version_inputs_path: str | Path = DEFAULT_INPUTS,
    thresholds_path: str | Path = DEFAULT_THRESHOLDS,
    supplemental_path: str | Path = DEFAULT_SUPPLEMENTAL,
) -> dict[str, Any]:
    started_at = _now()
    fingerprint = compute_version_fingerprint(
        version_inputs_path, project_root=PROJECT_ROOT
    )
    thresholds = load_thresholds(thresholds_path)
    runner = LocalRuntimeScenarioRunner(
        WORK_ROOT, prefix=f"live-{uuid.uuid4().hex}"
    )
    try:
        suite = regression.run_regression_suite(
            regression.load_regression_cases(fixture_path), runner
        )
    finally:
        runner.cleanup()
    supplemental = run_supplemental_cases(supplemental_path)
    metrics = asdict(suite.metrics)
    threshold_results = evaluate_thresholds(
        metrics,
        calculated_cost=None,
        thresholds=thresholds,
    )
    core_cases = [
        {
            "case_id": item.case_id,
            "status": item.status.value,
            "mismatches": list(item.mismatches),
        }
        for item in suite.cases
    ]
    passed = (
        not suite.failing_cases
        and not suite.xfail_cases
        and all(item["status"] == "PASS" for item in supplemental)
        and threshold_results["passed"]
    )
    report = {
        "schema_version": LIVE_REPORT_SCHEMA_VERSION,
        "execution_mode": "LOCAL_RUNTIME",
        "mocked": False,
        "external_provider_used": False,
        "runner": "evals.local_runtime_scenarios.LocalRuntimeScenarioRunner",
        "version_fingerprint": fingerprint.to_dict(),
        "started_at": started_at,
        "finished_at": _now(),
        "result": "PASS" if passed else "FAIL",
        "core_cases": core_cases,
        "supplemental_cases": supplemental,
        "failing_cases": [
            *suite.failing_cases,
            *suite.xfail_cases,
            *[item["case_id"] for item in supplemental if item["status"] != "PASS"],
        ],
        "metrics": metrics,
        "cost": {
            "status": "UNAVAILABLE",
            "calculated_cost": None,
            "currency": "USD",
            "reason": "local runtime regression made no external Provider call",
        },
        "thresholds": thresholds,
        "threshold_results": threshold_results,
    }
    validate_live_report(report)
    return report


def run_supplemental_cases(path: str | Path) -> list[dict[str, Any]]:
    try:
        values = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveRegressionError(f"cannot load supplemental cases: {exc}") from exc
    if not isinstance(values, list) or not values:
        raise LiveRegressionError("supplemental cases must be a non-empty array")
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(values):
        if not isinstance(item, Mapping) or set(item) != {"id", "test_id"}:
            raise LiveRegressionError(f"supplemental_cases[{index}] is invalid")
        case_id = _nonempty(item["id"], f"supplemental_cases[{index}].id")
        test_id = _nonempty(
            item["test_id"], f"supplemental_cases[{index}].test_id"
        )
        if case_id in seen:
            raise LiveRegressionError(f"duplicate supplemental case {case_id!r}")
        seen.add(case_id)
        started = time.perf_counter()
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", test_id, "-q"],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        transcript = (completed.stdout or "") + (completed.stderr or "")
        results.append(
            {
                "case_id": case_id,
                "test_id": test_id,
                "status": "PASS" if completed.returncode == 0 else "FAIL",
                "return_code": completed.returncode,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                "transcript_sha256": hashlib.sha256(
                    transcript.encode("utf-8")
                ).hexdigest(),
            }
        )
    required = {"provider-failure", "resume", "every-stage-park", "artifact-tamper"}
    if {item["case_id"] for item in results} != required:
        raise LiveRegressionError("supplemental cases do not match the FV-07 contract")
    return results


def load_thresholds(path: str | Path) -> dict[str, Any]:
    expected = {
        "schema_version",
        "minimum_constraint_adherence",
        "maximum_candidate_duplication",
        "minimum_exploration_coverage",
        "minimum_critical_assumption_discovery",
        "maximum_fact_inference_mislabel_rate",
        "maximum_average_rounds",
        "maximum_calculated_cost",
    }
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveRegressionError(f"cannot load thresholds: {exc}") from exc
    if not isinstance(value, Mapping) or set(value) != expected:
        raise LiveRegressionError("thresholds have invalid keys")
    if value["schema_version"] != 1:
        raise LiveRegressionError("unsupported threshold schema")
    for name in expected - {"schema_version", "maximum_calculated_cost"}:
        amount = value[name]
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0:
            raise LiveRegressionError(f"threshold {name} must be a number >= 0")
    maximum_cost = value["maximum_calculated_cost"]
    if maximum_cost is not None and (
        isinstance(maximum_cost, bool)
        or not isinstance(maximum_cost, (int, float))
        or maximum_cost < 0
    ):
        raise LiveRegressionError("maximum_calculated_cost must be null or >= 0")
    return dict(value)


def evaluate_thresholds(
    metrics: Mapping[str, Any],
    *,
    calculated_cost: int | float | None,
    thresholds: Mapping[str, Any],
) -> dict[str, Any]:
    checks = {
        "constraint_adherence": metrics["constraint_adherence"]
        >= thresholds["minimum_constraint_adherence"],
        "candidate_duplication": metrics["candidate_duplication"]
        <= thresholds["maximum_candidate_duplication"],
        "exploration_coverage": metrics["exploration_coverage"]
        >= thresholds["minimum_exploration_coverage"],
        "critical_assumption_discovery": metrics["critical_assumption_discovery"]
        >= thresholds["minimum_critical_assumption_discovery"],
        "fact_inference_mislabel_rate": metrics["fact_inference_mislabel_rate"]
        <= thresholds["maximum_fact_inference_mislabel_rate"],
        "average_rounds": metrics["average_rounds"]
        <= thresholds["maximum_average_rounds"],
        "calculated_cost": (
            True
            if thresholds["maximum_calculated_cost"] is None
            else calculated_cost is not None
            and calculated_cost <= thresholds["maximum_calculated_cost"]
        ),
    }
    return {"passed": all(checks.values()), "checks": checks}


def validate_live_report(value: Mapping[str, Any]) -> None:
    expected = {
        "schema_version",
        "execution_mode",
        "mocked",
        "external_provider_used",
        "runner",
        "version_fingerprint",
        "started_at",
        "finished_at",
        "result",
        "core_cases",
        "supplemental_cases",
        "failing_cases",
        "metrics",
        "cost",
        "thresholds",
        "threshold_results",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise LiveRegressionError("live report has invalid keys")
    if value["schema_version"] != LIVE_REPORT_SCHEMA_VERSION:
        raise LiveRegressionError("unsupported live report schema")
    if value["execution_mode"] not in {"LOCAL_RUNTIME", "LIVE_PROVIDER"}:
        raise LiveRegressionError("execution_mode is not live")
    if value["mocked"] is not False:
        raise LiveRegressionError("mock-only reports are forbidden")
    if type(value["external_provider_used"]) is not bool:
        raise LiveRegressionError("external_provider_used must be boolean")
    _nonempty(value["runner"], "runner")
    VersionFingerprint.from_dict(value["version_fingerprint"])
    if value["result"] not in {"PASS", "FAIL"}:
        raise LiveRegressionError("live report result is invalid")
    if not isinstance(value["core_cases"], list) or len(value["core_cases"]) < 12:
        raise LiveRegressionError("live report must contain at least 12 core cases")
    if not isinstance(value["supplemental_cases"], list) or len(value["supplemental_cases"]) != 4:
        raise LiveRegressionError("live report must contain four supplemental cases")
    if not isinstance(value["failing_cases"], list):
        raise LiveRegressionError("failing_cases must be an array")
    if not isinstance(value["metrics"], Mapping):
        raise LiveRegressionError("metrics must be an object")
    if not isinstance(value["cost"], Mapping):
        raise LiveRegressionError("cost must be an object")
    if not isinstance(value["threshold_results"], Mapping):
        raise LiveRegressionError("threshold_results must be an object")
    if value["result"] == "PASS" and (
        value["failing_cases"]
        or not value["threshold_results"].get("passed")
        or any(item.get("status") != "PASS" for item in value["core_cases"])
        or any(item.get("status") != "PASS" for item in value["supplemental_cases"])
    ):
        raise LiveRegressionError("PASS report contains failed evidence")


def save_live_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    validate_live_report(report)
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(target)
    return target


def load_live_report(path: str | Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveRegressionError(f"cannot load live report: {exc}") from exc
    validate_live_report(value)
    return dict(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LiveRegressionError(f"{path} must be a non-empty string")
    return value.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["run", "fingerprint"])
    parser.add_argument("--version-inputs", default=str(DEFAULT_INPUTS))
    parser.add_argument("--fixture", default=str(DEFAULT_FIXTURE))
    parser.add_argument("--thresholds", default=str(DEFAULT_THRESHOLDS))
    parser.add_argument("--supplemental", default=str(DEFAULT_SUPPLEMENTAL))
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "fingerprint":
            payload = compute_version_fingerprint(
                args.version_inputs, project_root=PROJECT_ROOT
            ).to_dict()
        else:
            payload = run_live_regression(
                fixture_path=args.fixture,
                version_inputs_path=args.version_inputs,
                thresholds_path=args.thresholds,
                supplemental_path=args.supplemental,
            )
            save_live_report(args.report, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if args.command == "fingerprint" or payload["result"] == "PASS" else 1
    except (LiveRegressionError, p0.ContractError, ValueError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "LiveRegressionError",
    "evaluate_thresholds",
    "load_live_report",
    "load_thresholds",
    "run_live_regression",
    "save_live_report",
    "validate_live_report",
]
