#!/usr/bin/env python3
"""Run two isolated real-provider Council members for the diet-app Stress pass.

The command emits normalized JSON to stdout and never writes a result file.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
GOVERNOR_SCRIPTS = (
    PROJECT_ROOT / ".agents" / "skills" / "brainstorm-governor" / "scripts"
)
if str(GOVERNOR_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(GOVERNOR_SCRIPTS))

from adapters.council_http import OpenAICompatibleCouncilAdapter  # noqa: E402
from p0_runtime import ContractError  # noqa: E402
from p5_council import (  # noqa: E402
    CouncilAdapterRegistry,
    CouncilEvidenceDatum,
    CouncilMemberAssignment,
    CouncilMemberRequest,
    CouncilMemberResult,
    CouncilProvider,
    CouncilProviderAdapter,
    CouncilRuntimeConfig,
    build_synthesis_input,
    prepare_member_requests,
    runtime_config_from_dict,
    validate_member_result,
)


DEFAULT_CONFIG = PROJECT_ROOT / "config" / "diet-app-council.json"
DEFAULT_REQUEST = PROJECT_ROOT / "diet-control-app.brainstorm.v3.json"
DEFAULT_EVIDENCE = PROJECT_ROOT / "evidence" / "diet-app-evidence.json"

QUESTION = (
    "对已由用户确认的 c2 实时自适应饮食教练进行独立 Stress 验证：判断该机制是否应继续、"
    "必须先修复什么，以及一周原型最小且诚实的验证设计是什么。不得把一周行为信号表述为"
    "稳定健康结果，也不得扩展为医疗诊断。"
)

DIMENSIONS = {
    CouncilProvider.DEEPSEEK: "产品价值、行为闭环、竞品差异化与用户采纳风险",
    CouncilProvider.KIMI: "营养建议安全、食物识别误差、首周验证有效性与范围可行性",
}

OUTPUT_CONTRACT: dict[str, Any] = {
    "type": "object",
    "required": [
        "verdict",
        "strongest_case",
        "fatal_risks",
        "repairable_risks",
        "recommendation",
        "decisive_uncertainties",
        "one_week_validation",
        "evidence_used",
    ],
    "properties": {
        "verdict": {"type": "string", "enum": ["PROCEED", "REFINE", "REJECT"]},
        "strongest_case": {"type": "string"},
        "fatal_risks": {"type": "array", "items": {"type": "string"}},
        "repairable_risks": {"type": "array", "items": {"type": "string"}},
        "recommendation": {"type": "string"},
        "decisive_uncertainties": {
            "type": "array",
            "items": {"type": "string"},
        },
        "one_week_validation": {
            "type": "object",
            "required": ["hypothesis", "method", "pass_signal", "fail_signal"],
        },
        "evidence_used": {"type": "array", "items": {"type": "string"}},
    },
}


def prepare_diet_member_requests(
    config: CouncilRuntimeConfig,
    brainstorm_request: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
) -> list[CouncilMemberRequest]:
    core = _mapping(brainstorm_request.get("core"), "request.core")
    problem_frame = _mapping(core.get("problem_frame"), "request.core.problem_frame")
    confirmed = _item_by_id(core.get("candidates"), "c2", "candidates")
    challenge = _item_by_id(core.get("challenges"), "c2", "challenges", "candidate_id")
    assessment = _item_by_id(core.get("assessments"), "c2", "assessments", "candidate_id")
    if core.get("recommended_candidate_id") != "c2":
        raise ContractError("request must preserve confirmed candidate c2")

    enabled = {
        item.provider
        for item in config.providers
        if item.enabled and item.model is not None
    }
    selected = [CouncilProvider.DEEPSEEK, CouncilProvider.KIMI]
    missing = [item.value for item in selected if item not in enabled]
    if missing:
        raise ContractError(
            "diet Council requires enabled DeepSeek and Kimi providers: "
            + ", ".join(missing)
        )
    assignments = [
        CouncilMemberAssignment(
            member_id=f"diet-{provider.value}",
            provider=provider,
            assigned_dimension=DIMENSIONS[provider],
        )
        for provider in selected
    ]
    hard_constraints = [
        _statement(item, "hard_constraints")
        for item in _list(problem_frame.get("hard_constraints"), "hard_constraints")
    ]
    shared_frame = {
        "problem_frame": copy.deepcopy(dict(problem_frame)),
        "confirmed_candidate": copy.deepcopy(dict(confirmed)),
        "existing_challenge": copy.deepcopy(dict(challenge)),
        "existing_assessment": copy.deepcopy(dict(assessment)),
        "current_confidence": core.get("confidence"),
        "cheapest_test": core.get("cheapest_test"),
    }
    return prepare_member_requests(
        config,
        assignments,
        shared_frame=shared_frame,
        question=QUESTION,
        hard_constraints=hard_constraints,
        evidence_summary=evidence_from_document(evidence_document),
        output_contract=OUTPUT_CONTRACT,
    )


def evidence_from_document(
    evidence_document: Mapping[str, Any],
) -> list[CouncilEvidenceDatum]:
    if evidence_document.get("treatment") != "DATA_ONLY":
        raise ContractError("evidence document must remain DATA_ONLY")
    result: list[CouncilEvidenceDatum] = []
    for index, value in enumerate(
        _list(evidence_document.get("records"), "evidence.records")
    ):
        record = _mapping(value, f"evidence.records[{index}]")
        source = record.get("source")
        if source is None and "sources" in record:
            urls: list[str] = []
            for source_index, source_value in enumerate(
                _list(record["sources"], f"evidence.records[{index}].sources")
            ):
                source_item = _mapping(
                    source_value,
                    f"evidence.records[{index}].sources[{source_index}]",
                )
                url = source_item.get("url")
                if isinstance(url, str) and url.strip():
                    urls.append(url.strip())
            source = " | ".join(urls) or None
        if source is not None and not isinstance(source, str):
            raise ContractError(f"evidence.records[{index}].source must be string or null")
        datum = CouncilEvidenceDatum(
            id=_string(record.get("id"), f"evidence.records[{index}].id"),
            claim=_string(record.get("claim"), f"evidence.records[{index}].claim"),
            source=source,
            treatment="DATA_ONLY",
        )
        result.append(datum)
    return result


def execute_diet_council(
    config: CouncilRuntimeConfig,
    brainstorm_request: Mapping[str, Any],
    evidence_document: Mapping[str, Any],
    *,
    adapter_factory: Callable[[], CouncilProviderAdapter] = (
        OpenAICompatibleCouncilAdapter
    ),
) -> dict[str, Any]:
    # Prepare and validate every isolated request before any Provider submission.
    requests = prepare_diet_member_requests(
        config, brainstorm_request, evidence_document
    )
    config_by_provider = {
        item.provider: item
        for item in config.providers
        if item.enabled and item.model is not None
    }
    registry = CouncilAdapterRegistry()
    for provider in {item.provider for item in requests}:
        registry.register(provider, adapter_factory())

    # Submit every member before collecting results, preserving peer isolation.
    with ThreadPoolExecutor(max_workers=len(requests)) as executor:
        futures = [
            executor.submit(
                registry.resolve(request.provider).invoke,
                config_by_provider[request.provider],
                request,
            )
            for request in requests
        ]
        results = [future.result() for future in futures]

    normalized_results = [_normalize_contract_result(item) for item in results]
    successful = [item for item in normalized_results if item.success]
    status = "INSUFFICIENT_SUCCESS"
    council_label = "NOT_COUNCIL"
    admission_error: str | None = None
    try:
        build_synthesis_input(config, requests, normalized_results)
        status = "COUNCIL_MEMBERS_READY_FOR_SYNTHESIS"
        council_label = "COUNCIL"
    except ContractError as exc:
        admission_error = str(exc)

    return {
        "schema_version": 1,
        "request_id": brainstorm_request.get("request_id"),
        "status": status,
        "council_label": council_label,
        "adapter": "adapters.council_http.OpenAICompatibleCouncilAdapter",
        "minimum_successful_members": config.minimum_successful_members,
        "successful_member_ids": [item.member_id for item in successful],
        "admission_error": admission_error,
        "member_results": [_json_ready(item) for item in normalized_results],
    }


def _normalize_contract_result(result: CouncilMemberResult) -> CouncilMemberResult:
    validate_member_result(result)
    if not result.success:
        return result
    try:
        _validate_output(result.output)
        return result
    except ContractError as exc:
        return CouncilMemberResult(
            member_id=result.member_id,
            provider=result.provider,
            model=result.model,
            success=False,
            output=None,
            usage=result.usage,
            error=f"member output contract failed: {exc}",
        )


def _validate_output(value: dict[str, Any] | None) -> None:
    if not isinstance(value, dict):
        raise ContractError("output must be an object")
    missing = set(OUTPUT_CONTRACT["required"]) - set(value)
    if missing:
        raise ContractError(f"missing required keys {sorted(missing)}")
    if value["verdict"] not in {"PROCEED", "REFINE", "REJECT"}:
        raise ContractError("verdict is invalid")
    for key in ("strongest_case", "recommendation"):
        _string(value[key], key)
    for key in (
        "fatal_risks",
        "repairable_risks",
        "decisive_uncertainties",
        "evidence_used",
    ):
        items = _list(value[key], key)
        for index, item in enumerate(items):
            _string(item, f"{key}[{index}]")
    validation = _mapping(value["one_week_validation"], "one_week_validation")
    for key in ("hypothesis", "method", "pass_signal", "fail_signal"):
        _string(validation.get(key), f"one_week_validation.{key}")


def _item_by_id(
    value: Any,
    expected_id: str,
    path: str,
    id_key: str = "id",
) -> Mapping[str, Any]:
    for index, item_value in enumerate(_list(value, path)):
        item = _mapping(item_value, f"{path}[{index}]")
        if item.get(id_key) == expected_id:
            return item
    raise ContractError(f"{path} has no {id_key}={expected_id!r}")


def _statement(value: Any, path: str) -> str:
    item = _mapping(value, path)
    return _string(item.get("statement"), f"{path}.statement")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return value


def _list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ContractError(f"{path} must be a list")
    return value


def _string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value.strip()


def _json_ready(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {item.name: _json_ready(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return copy.deepcopy(value)


def _load_json(path: Path) -> Mapping[str, Any]:
    try:
        return _mapping(json.loads(path.read_text(encoding="utf-8")), str(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load JSON {path}: {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--request", type=Path, default=DEFAULT_REQUEST)
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        config = runtime_config_from_dict(_load_json(args.config))
        result = execute_diet_council(
            config,
            _load_json(args.request),
            _load_json(args.evidence),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["council_label"] == "COUNCIL" else 2
    except (ContractError, OSError, UnicodeError) as exc:
        print(
            json.dumps(
                {"schema_version": 1, "status": "ERROR", "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
