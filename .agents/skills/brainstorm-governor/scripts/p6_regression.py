#!/usr/bin/env python3
"""Provider-neutral P6 behavioral regression harness."""

from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from p0_runtime import ContractError
from p6_quality import CoreMetrics, MetricSample, aggregate_metrics


class RegressionStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    XFAIL = "XFAIL"
    XPASS = "XPASS"


@dataclass(frozen=True)
class RegressionCase:
    id: str
    scenario: str
    input_payload: dict[str, Any]
    expected_behavior: dict[str, Any]
    xfail_reason: str | None = None


@dataclass(frozen=True)
class RegressionObservation:
    behavior: dict[str, Any]
    metrics: MetricSample


class RegressionRunner(Protocol):
    def run(self, case: RegressionCase) -> RegressionObservation:
        ...


@dataclass(frozen=True)
class RegressionCaseResult:
    case_id: str
    status: RegressionStatus
    mismatches: list[str]


@dataclass(frozen=True)
class RegressionSuiteResult:
    cases: list[RegressionCaseResult]
    metrics: CoreMetrics
    failing_cases: list[str]
    xfail_cases: list[str]


REQUIRED_SCENARIOS = {
    "quick_idea",
    "ambiguous_concept",
    "weak_existing_solution",
    "unknown_domain",
    "high_risk_decision",
    "duplicate_candidates",
    "missing_information",
    "brief_reentry",
    "malicious_external_content",
    "budget_exhaustion",
}


def load_regression_cases(path: str | Path) -> list[RegressionCase]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load regression cases: {exc}") from exc
    if not isinstance(value, list):
        raise ContractError("regression fixture must be a list")
    result: list[RegressionCase] = []
    ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ContractError(f"cases[{index}] must be an object")
        allowed = {
            "id",
            "scenario",
            "input_payload",
            "expected_behavior",
            "xfail_reason",
        }
        unknown = set(item) - allowed
        missing = allowed - {"xfail_reason"} - set(item)
        if unknown or missing:
            raise ContractError(
                f"cases[{index}] keys invalid; missing={sorted(missing)}, "
                f"unknown={sorted(unknown)}"
            )
        case = RegressionCase(
            id=_required_string(item["id"], f"cases[{index}].id"),
            scenario=_required_string(
                item["scenario"], f"cases[{index}].scenario"
            ),
            input_payload=_required_mapping(
                item["input_payload"], f"cases[{index}].input_payload"
            ),
            expected_behavior=_required_mapping(
                item["expected_behavior"],
                f"cases[{index}].expected_behavior",
            ),
            xfail_reason=_optional_string(
                item.get("xfail_reason"), f"cases[{index}].xfail_reason"
            ),
        )
        if case.id in ids:
            raise ContractError(f"duplicate regression case id {case.id!r}")
        ids.add(case.id)
        result.append(case)
    missing_scenarios = REQUIRED_SCENARIOS - {item.scenario for item in result}
    if missing_scenarios:
        raise ContractError(
            f"regression fixture misses scenarios: {sorted(missing_scenarios)}"
        )
    return result


def run_regression_suite(
    cases: Sequence[RegressionCase], runner: RegressionRunner
) -> RegressionSuiteResult:
    items = list(cases)
    if not items:
        raise ContractError("regression suite requires at least one case")
    if not hasattr(runner, "run"):
        raise ContractError("runner must implement run")
    results: list[RegressionCaseResult] = []
    samples: list[MetricSample] = []
    for case in items:
        mismatches: list[str] = []
        try:
            observation = runner.run(copy.deepcopy(case))
            if not isinstance(observation, RegressionObservation):
                raise ContractError("runner must return RegressionObservation")
            if observation.metrics.case_id != case.id:
                raise ContractError("metric sample case_id must match regression case")
            samples.append(observation.metrics)
            mismatches = _compare_expected(
                case.expected_behavior, observation.behavior
            )
        except Exception as exc:
            mismatches = [f"runner error: {exc}"]

        passed = not mismatches
        if case.xfail_reason is None:
            status = RegressionStatus.PASS if passed else RegressionStatus.FAIL
        else:
            status = RegressionStatus.XPASS if passed else RegressionStatus.XFAIL
        results.append(RegressionCaseResult(case.id, status, mismatches))

    if not samples:
        raise ContractError("regression runner produced no metric samples")
    return RegressionSuiteResult(
        cases=results,
        metrics=aggregate_metrics(samples),
        failing_cases=[
            item.case_id
            for item in results
            if item.status in {RegressionStatus.FAIL, RegressionStatus.XPASS}
        ],
        xfail_cases=[
            item.case_id for item in results if item.status is RegressionStatus.XFAIL
        ],
    )


def _compare_expected(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    if not isinstance(actual, Mapping):
        return ["observed behavior must be an object"]
    mismatches: list[str] = []
    for key, value in expected.items():
        if key not in actual:
            mismatches.append(f"missing observed key {key!r}")
        elif actual[key] != value:
            mismatches.append(
                f"{key}: expected {value!r}, observed {actual[key]!r}"
            )
    return mismatches


def _required_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return copy.deepcopy(dict(value))


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value.strip()


def _optional_string(value: Any, path: str) -> str | None:
    if value is None:
        return None
    return _required_string(value, path)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {
            item.name: _json_ready(getattr(value, item.name)) for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return copy.deepcopy(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "fixture",
        nargs="?",
        default=str(Path(__file__).parents[1] / "evals" / "p6_regression.json"),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        cases = load_regression_cases(args.fixture)
        print(
            json.dumps(
                {
                    "valid": True,
                    "case_count": len(cases),
                    "scenarios": sorted({item.scenario for item in cases}),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except ContractError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
