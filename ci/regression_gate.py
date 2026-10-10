#!/usr/bin/env python3
"""FV-07 release gate: always run offline contracts; require live run on change."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evals.baseline import (  # noqa: E402
    BaselineError,
    approve_baseline,
    load_baseline,
    verify_baseline_report,
)
from evals.live_runner import (  # noqa: E402
    LiveRegressionError,
    load_live_report,
)
from evals.version_fingerprint import (  # noqa: E402
    VersionFingerprint,
    changed_dimensions,
    compute_version_fingerprint,
)


DEFAULT_INPUTS = PROJECT_ROOT / "evals" / "version-inputs.json"
DEFAULT_BASELINE = PROJECT_ROOT / "evals" / "baseline-manifest.json"
DEFAULT_REPORT = PROJECT_ROOT / "evals" / "live-report.json"


@dataclass(frozen=True)
class OfflineContractResult:
    passed: bool
    return_code: int
    transcript_sha256: str
    test_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "return_code": self.return_code,
            "transcript_sha256": self.transcript_sha256,
            "test_count": self.test_count,
        }


def run_offline_contract_regression() -> OfflineContractResult:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            ".agents/skills/brainstorm-governor/tests",
            "-q",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    transcript = (completed.stdout or "") + (completed.stderr or "")
    return OfflineContractResult(
        passed=completed.returncode == 0 and "Ran 108 tests" in transcript,
        return_code=completed.returncode,
        transcript_sha256=hashlib.sha256(transcript.encode("utf-8")).hexdigest(),
        test_count=108 if "Ran 108 tests" in transcript else 0,
    )


def evaluate_release_gate(
    *,
    version_inputs_path: str | Path = DEFAULT_INPUTS,
    baseline_path: str | Path = DEFAULT_BASELINE,
    live_report_path: str | Path | None = None,
    offline_result: OfflineContractResult | None = None,
) -> dict[str, Any]:
    current = compute_version_fingerprint(
        version_inputs_path, project_root=PROJECT_ROOT
    )
    baseline = load_baseline(baseline_path)
    baseline_fingerprint = VersionFingerprint.from_dict(
        baseline["version_fingerprint"]
    )
    changed = changed_dimensions(baseline_fingerprint, current)
    offline = offline_result or run_offline_contract_regression()
    reasons: list[str] = []
    if not offline.passed:
        reasons.append("offline P0-P6 contract regression failed")

    live_required = bool(changed)
    live_accepted = False
    live_report: Mapping[str, Any] | None = None
    if live_required:
        if live_report_path is None:
            reasons.append("version changed but live regression report was not supplied")
        else:
            try:
                live_report = load_live_report(live_report_path)
                report_fingerprint = VersionFingerprint.from_dict(
                    live_report["version_fingerprint"]
                )
                if report_fingerprint.aggregate != current.aggregate:
                    reasons.append("live report fingerprint is not current")
                elif live_report["result"] != "PASS":
                    reasons.append("live regression failed")
                elif not live_report["threshold_results"]["passed"]:
                    reasons.append("live regression exceeded quality thresholds")
                elif live_report["mocked"] is not False:
                    reasons.append("mock-only live report is forbidden")
                else:
                    live_accepted = True
            except (LiveRegressionError, ValueError) as exc:
                reasons.append(f"live report rejected: {exc}")
    else:
        try:
            live_report = verify_baseline_report(
                baseline, project_root=PROJECT_ROOT
            )
            live_accepted = True
        except BaselineError as exc:
            reasons.append(str(exc))

    quality_delta = _metric_delta(
        baseline["metrics"], None if live_report is None else live_report["metrics"]
    )
    cost_delta = _cost_delta(
        baseline["cost"], None if live_report is None else live_report["cost"]
    )
    failing_cases = (
        [] if live_report is None else list(live_report.get("failing_cases", []))
    )
    allowed = not reasons and offline.passed and live_accepted
    return {
        "schema_version": 1,
        "result": "ALLOW" if allowed else "BLOCK",
        "current_fingerprint": current.to_dict(),
        "baseline_fingerprint": baseline_fingerprint.to_dict(),
        "changed_dimensions": changed,
        "live_regression_required": live_required,
        "live_report_accepted": live_accepted,
        "offline_contract": offline.to_dict(),
        "failing_cases": failing_cases,
        "quality_delta": quality_delta,
        "cost_delta": cost_delta,
        "reasons": reasons,
    }


def save_gate_report(path: str | Path, report: Mapping[str, Any]) -> Path:
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(payload, encoding="utf-8", newline="\n")
    temporary.replace(target)
    return target


def _metric_delta(
    baseline: Mapping[str, Any], current: Mapping[str, Any] | None
) -> dict[str, float | None]:
    if current is None:
        return {name: None for name in baseline}
    result: dict[str, float | None] = {}
    for name, old in baseline.items():
        new = current.get(name)
        result[name] = (
            None
            if old is None or new is None
            else round(float(new) - float(old), 12)
        )
    return result


def _cost_delta(
    baseline: Mapping[str, Any], current: Mapping[str, Any] | None
) -> float | None:
    if current is None:
        return None
    old = baseline.get("calculated_cost")
    new = current.get("calculated_cost")
    return None if old is None or new is None else round(float(new) - float(old), 12)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check")
    check.add_argument("--version-inputs", default=str(DEFAULT_INPUTS))
    check.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    check.add_argument("--live-report")
    check.add_argument("--output")
    approve = subparsers.add_parser("approve-baseline")
    approve.add_argument("--live-report", default=str(DEFAULT_REPORT))
    approve.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    approve.add_argument("--approval-id", required=True)
    approve.add_argument("--reviewer", required=True)
    approve.add_argument("--approve", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "approve-baseline":
            payload = approve_baseline(
                args.live_report,
                args.baseline,
                approval_id=args.approval_id,
                reviewer=args.reviewer,
                explicitly_approved=args.approve,
                project_root=PROJECT_ROOT,
            )
            code = 0
        else:
            payload = evaluate_release_gate(
                version_inputs_path=args.version_inputs,
                baseline_path=args.baseline,
                live_report_path=args.live_report,
            )
            if args.output:
                save_gate_report(args.output, payload)
            code = 0 if payload["result"] == "ALLOW" else 1
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return code
    except (BaselineError, LiveRegressionError, ValueError, OSError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "OfflineContractResult",
    "evaluate_release_gate",
    "run_offline_contract_regression",
    "save_gate_report",
]
