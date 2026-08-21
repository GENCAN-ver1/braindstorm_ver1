#!/usr/bin/env python3
"""Provider-neutral Council contracts for DeepSeek, Kimi, and MiniMax."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence
from urllib.parse import urlparse

from p0_runtime import ContractError


class CouncilProvider(str, Enum):
    DEEPSEEK = "deepseek"
    KIMI = "kimi"
    MINIMAX = "minimax"


class CouncilProtocol(str, Enum):
    OPENAI_COMPATIBLE = "OPENAI_COMPATIBLE"


@dataclass(frozen=True)
class CouncilProviderDefaults:
    protocol: CouncilProtocol
    base_url: str
    credential_env: str


PROVIDER_DEFAULTS = {
    CouncilProvider.DEEPSEEK: CouncilProviderDefaults(
        CouncilProtocol.OPENAI_COMPATIBLE,
        "https://api.deepseek.com",
        "DEEPSEEK_API_KEY",
    ),
    CouncilProvider.KIMI: CouncilProviderDefaults(
        CouncilProtocol.OPENAI_COMPATIBLE,
        "https://api.moonshot.cn/v1",
        "MOONSHOT_API_KEY",
    ),
    CouncilProvider.MINIMAX: CouncilProviderDefaults(
        CouncilProtocol.OPENAI_COMPATIBLE,
        "https://api.minimaxi.com/v1",
        "MINIMAX_API_KEY",
    ),
}


@dataclass(frozen=True)
class CouncilProviderConfig:
    provider: CouncilProvider
    enabled: bool
    protocol: CouncilProtocol
    base_url: str
    model: str | None
    credential_env: str
    timeout_seconds: int = 60
    max_output_tokens: int = 4096
    provider_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CouncilRuntimeConfig:
    requested: bool = False
    minimum_successful_members: int = 2
    providers: list[CouncilProviderConfig] = field(default_factory=list)


@dataclass(frozen=True)
class CouncilReadiness:
    enabled: bool
    configured_providers: list[CouncilProvider]
    reasons: list[str]


@dataclass(frozen=True)
class CouncilEvidenceDatum:
    id: str
    claim: str
    source: str | None
    treatment: str = "DATA_ONLY"


@dataclass(frozen=True)
class CouncilMemberAssignment:
    member_id: str
    provider: CouncilProvider
    assigned_dimension: str


@dataclass(frozen=True)
class CouncilMemberRequest:
    member_id: str
    provider: CouncilProvider
    shared_frame: dict[str, Any]
    question: str
    assigned_dimension: str
    hard_constraints: list[str]
    evidence_summary: list[CouncilEvidenceDatum]
    output_contract: dict[str, Any]


@dataclass(frozen=True)
class CouncilUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class CouncilMemberResult:
    member_id: str
    provider: CouncilProvider
    model: str
    success: bool
    output: dict[str, Any] | None
    usage: CouncilUsage = CouncilUsage()
    error: str | None = None


@dataclass(frozen=True)
class CouncilSynthesisInput:
    shared_frame: dict[str, Any]
    question: str
    member_results: list[CouncilMemberResult]
    output_contract: dict[str, Any]


@dataclass(frozen=True)
class CouncilSynthesisResult:
    agreements: list[str]
    disagreements: list[str]
    recommendation: str | None
    decisive_uncertainties: list[str]


class CouncilProviderAdapter(Protocol):
    """Vendor adapter; resolves credentials at call time and returns no raw payload."""

    def invoke(
        self,
        config: CouncilProviderConfig,
        request: CouncilMemberRequest,
    ) -> CouncilMemberResult:
        ...


class CouncilSynthesizer(Protocol):
    """External synthesis boundary; it cannot write governor state directly."""

    def synthesize(self, request: CouncilSynthesisInput) -> CouncilSynthesisResult:
        ...


class CouncilAdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[CouncilProvider, CouncilProviderAdapter] = {}

    def register(
        self, provider: CouncilProvider, adapter: CouncilProviderAdapter
    ) -> None:
        if not isinstance(provider, CouncilProvider):
            raise ContractError("provider must be CouncilProvider")
        if not hasattr(adapter, "invoke"):
            raise ContractError("Council provider adapter must implement invoke")
        if provider in self._adapters:
            raise ContractError(f"Council adapter already registered for {provider.value}")
        self._adapters[provider] = adapter

    def resolve(self, provider: CouncilProvider) -> CouncilProviderAdapter:
        if not isinstance(provider, CouncilProvider):
            raise ContractError("provider must be CouncilProvider")
        try:
            return self._adapters[provider]
        except KeyError as exc:
            raise ContractError(
                f"no Council adapter registered for {provider.value}"
            ) from exc

    def providers(self) -> list[CouncilProvider]:
        return sorted(self._adapters, key=lambda item: item.value)


def default_runtime_config() -> CouncilRuntimeConfig:
    """Return disabled templates; model IDs must be chosen at deployment time."""
    return CouncilRuntimeConfig(
        requested=False,
        minimum_successful_members=2,
        providers=[
            CouncilProviderConfig(
                provider=provider,
                enabled=False,
                protocol=defaults.protocol,
                base_url=defaults.base_url,
                model=None,
                credential_env=defaults.credential_env,
            )
            for provider, defaults in PROVIDER_DEFAULTS.items()
        ],
    )


def council_readiness(config: CouncilRuntimeConfig) -> CouncilReadiness:
    validate_runtime_config(config)
    configured = [
        item.provider
        for item in config.providers
        if item.enabled and item.model is not None
    ]
    reasons: list[str] = []
    if not config.requested:
        reasons.append("Council was not requested")
    if len(configured) < config.minimum_successful_members:
        reasons.append(
            "fewer configured providers than minimum_successful_members"
        )
    return CouncilReadiness(
        enabled=not reasons,
        configured_providers=configured,
        reasons=reasons or ["Council provider configuration is ready"],
    )


def prepare_member_requests(
    config: CouncilRuntimeConfig,
    assignments: Sequence[CouncilMemberAssignment],
    *,
    shared_frame: Mapping[str, Any],
    question: str,
    hard_constraints: Sequence[str],
    evidence_summary: Sequence[CouncilEvidenceDatum],
    output_contract: Mapping[str, Any],
) -> list[CouncilMemberRequest]:
    """Create peer-isolated requests; no member receives another member's output."""
    readiness = council_readiness(config)
    if not readiness.enabled:
        raise ContractError("Council is not ready: " + "; ".join(readiness.reasons))
    frame = _required_mapping(shared_frame, "shared_frame")
    prompt = _required_string(question, "question")
    constraints = _unique_strings(hard_constraints, "hard_constraints")
    contract = _required_mapping(output_contract, "output_contract")
    if not contract:
        raise ContractError("output_contract must not be empty")
    evidence = list(evidence_summary)
    for index, item in enumerate(evidence):
        _validate_evidence(item, f"evidence_summary[{index}]")
    assignment_items = list(assignments)
    if len(assignment_items) < config.minimum_successful_members:
        raise ContractError("Council requires at least two independent assignments")
    enabled = set(readiness.configured_providers)
    member_ids: set[str] = set()
    providers: set[CouncilProvider] = set()
    requests: list[CouncilMemberRequest] = []
    for index, assignment in enumerate(assignment_items):
        if not isinstance(assignment, CouncilMemberAssignment):
            raise ContractError(
                f"assignments[{index}] must be CouncilMemberAssignment"
            )
        member_id = _required_string(
            assignment.member_id, f"assignments[{index}].member_id"
        )
        dimension = _required_string(
            assignment.assigned_dimension,
            f"assignments[{index}].assigned_dimension",
        )
        if not isinstance(assignment.provider, CouncilProvider):
            raise ContractError(f"assignments[{index}].provider is invalid")
        if assignment.provider not in enabled:
            raise ContractError(
                f"provider {assignment.provider.value!r} is not enabled and configured"
            )
        if member_id in member_ids:
            raise ContractError(f"duplicate Council member_id {member_id!r}")
        if assignment.provider in providers:
            raise ContractError(
                f"provider {assignment.provider.value!r} cannot represent two members"
            )
        member_ids.add(member_id)
        providers.add(assignment.provider)
        requests.append(
            CouncilMemberRequest(
                member_id=member_id,
                provider=assignment.provider,
                shared_frame=copy.deepcopy(frame),
                question=prompt,
                assigned_dimension=dimension,
                hard_constraints=copy.deepcopy(constraints),
                evidence_summary=copy.deepcopy(evidence),
                output_contract=copy.deepcopy(contract),
            )
        )
    return requests


def build_synthesis_input(
    config: CouncilRuntimeConfig,
    requests: Sequence[CouncilMemberRequest],
    results: Sequence[CouncilMemberResult],
) -> CouncilSynthesisInput:
    """Admit only successful independent members after every result is available."""
    readiness = council_readiness(config)
    if not readiness.enabled:
        raise ContractError("Council is not ready: " + "; ".join(readiness.reasons))
    request_items = list(requests)
    result_items = list(results)
    if len(request_items) < config.minimum_successful_members:
        raise ContractError("Council synthesis requires at least two member requests")
    request_by_id: dict[str, CouncilMemberRequest] = {}
    for index, item in enumerate(request_items):
        _validate_request(item, f"requests[{index}]")
        if item.member_id in request_by_id:
            raise ContractError(f"duplicate request member_id {item.member_id!r}")
        request_by_id[item.member_id] = item
    successful: list[CouncilMemberResult] = []
    seen_results: set[str] = set()
    seen_providers: set[CouncilProvider] = set()
    for index, item in enumerate(result_items):
        validate_member_result(item, f"results[{index}]")
        request = request_by_id.get(item.member_id)
        if request is None:
            raise ContractError(f"result for unknown member {item.member_id!r}")
        if item.member_id in seen_results:
            raise ContractError(f"duplicate result for member {item.member_id!r}")
        if item.provider is not request.provider:
            raise ContractError(f"result provider mismatch for {item.member_id!r}")
        seen_results.add(item.member_id)
        if not item.success:
            continue
        if item.provider in seen_providers:
            raise ContractError("successful Council providers must be independent")
        seen_providers.add(item.provider)
        successful.append(copy.deepcopy(item))
    missing_results = set(request_by_id) - seen_results
    if missing_results:
        raise ContractError(
            f"Council results are incomplete for members {sorted(missing_results)}"
        )
    if len(successful) < config.minimum_successful_members:
        raise ContractError(
            "fewer than minimum_successful_members returned valid results"
        )
    first = request_items[0]
    if any(
        item.shared_frame != first.shared_frame
        or item.question != first.question
        or item.output_contract != first.output_contract
        for item in request_items[1:]
    ):
        raise ContractError("Council members must share frame, question, and output contract")
    return CouncilSynthesisInput(
        shared_frame=copy.deepcopy(first.shared_frame),
        question=first.question,
        member_results=successful,
        output_contract=copy.deepcopy(first.output_contract),
    )


def validate_runtime_config(config: CouncilRuntimeConfig) -> None:
    if not isinstance(config, CouncilRuntimeConfig):
        raise ContractError("Council config must be CouncilRuntimeConfig")
    if type(config.requested) is not bool:
        raise ContractError("council.requested must be boolean")
    if (
        type(config.minimum_successful_members) is not int
        or config.minimum_successful_members < 2
    ):
        raise ContractError("minimum_successful_members must be an integer >= 2")
    if not isinstance(config.providers, list):
        raise ContractError("council.providers must be a list")
    seen: set[CouncilProvider] = set()
    for index, item in enumerate(config.providers):
        _validate_provider_config(item, f"providers[{index}]")
        if item.provider in seen:
            raise ContractError(f"duplicate provider {item.provider.value!r}")
        seen.add(item.provider)


def validate_member_result(
    result: CouncilMemberResult, path: str = "result"
) -> None:
    if not isinstance(result, CouncilMemberResult):
        raise ContractError(f"{path} must be CouncilMemberResult")
    _required_string(result.member_id, f"{path}.member_id")
    if not isinstance(result.provider, CouncilProvider):
        raise ContractError(f"{path}.provider is invalid")
    _required_string(result.model, f"{path}.model")
    if type(result.success) is not bool:
        raise ContractError(f"{path}.success must be boolean")
    _validate_usage(result.usage, f"{path}.usage")
    if result.success:
        if not isinstance(result.output, dict) or not result.output:
            raise ContractError(f"{path}.output must be non-empty on success")
        if result.error is not None:
            raise ContractError(f"{path}.error must be null on success")
    else:
        if result.output is not None:
            raise ContractError(f"{path}.output must be null on failure")
        _required_string(result.error, f"{path}.error")


def runtime_config_from_dict(value: Mapping[str, Any]) -> CouncilRuntimeConfig:
    data = _exact_keys(
        value,
        {"requested", "minimum_successful_members", "providers"},
        "council",
    )
    providers_value = data["providers"]
    if not isinstance(providers_value, list):
        raise ContractError("council.providers must be a list")
    providers: list[CouncilProviderConfig] = []
    for index, item in enumerate(providers_value):
        provider_data = _exact_keys(
            item,
            {
                "provider",
                "enabled",
                "protocol",
                "base_url",
                "model",
                "credential_env",
                "timeout_seconds",
                "max_output_tokens",
                "provider_options",
            },
            f"providers[{index}]",
        )
        providers.append(
            CouncilProviderConfig(
                provider=_enum(CouncilProvider, provider_data["provider"], "provider"),
                enabled=provider_data["enabled"],
                protocol=_enum(
                    CouncilProtocol, provider_data["protocol"], "protocol"
                ),
                base_url=provider_data["base_url"],
                model=provider_data["model"],
                credential_env=provider_data["credential_env"],
                timeout_seconds=provider_data["timeout_seconds"],
                max_output_tokens=provider_data["max_output_tokens"],
                provider_options=_required_mapping(
                    provider_data["provider_options"], "provider_options"
                ),
            )
        )
    config = CouncilRuntimeConfig(
        requested=data["requested"],
        minimum_successful_members=data["minimum_successful_members"],
        providers=providers,
    )
    validate_runtime_config(config)
    return config


def runtime_config_to_dict(config: CouncilRuntimeConfig) -> dict[str, Any]:
    validate_runtime_config(config)
    return _json_ready(config)


def _validate_provider_config(item: CouncilProviderConfig, path: str) -> None:
    if not isinstance(item, CouncilProviderConfig):
        raise ContractError(f"{path} must be CouncilProviderConfig")
    if not isinstance(item.provider, CouncilProvider):
        raise ContractError(f"{path}.provider is invalid")
    if type(item.enabled) is not bool:
        raise ContractError(f"{path}.enabled must be boolean")
    if not isinstance(item.protocol, CouncilProtocol):
        raise ContractError(f"{path}.protocol is invalid")
    _validate_https_url(item.base_url, f"{path}.base_url")
    if item.enabled:
        _required_string(item.model, f"{path}.model")
    elif item.model is not None:
        _required_string(item.model, f"{path}.model")
    credential = _required_string(item.credential_env, f"{path}.credential_env")
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", credential):
        raise ContractError(f"{path}.credential_env must be an environment variable name")
    for name in ("timeout_seconds", "max_output_tokens"):
        value = getattr(item, name)
        if type(value) is not int or value < 1:
            raise ContractError(f"{path}.{name} must be an integer >= 1")
    options = _required_mapping(item.provider_options, f"{path}.provider_options")
    forbidden = {
        "api_key",
        "authorization",
        "credential",
        "access_token",
        "secret",
    }
    conflicts = {str(key).casefold() for key in options} & forbidden
    if conflicts:
        raise ContractError(
            f"{path}.provider_options cannot contain credentials: {sorted(conflicts)}"
        )


def _validate_request(item: CouncilMemberRequest, path: str) -> None:
    if not isinstance(item, CouncilMemberRequest):
        raise ContractError(f"{path} must be CouncilMemberRequest")
    _required_string(item.member_id, f"{path}.member_id")
    if not isinstance(item.provider, CouncilProvider):
        raise ContractError(f"{path}.provider is invalid")
    _required_mapping(item.shared_frame, f"{path}.shared_frame")
    _required_string(item.question, f"{path}.question")
    _required_string(item.assigned_dimension, f"{path}.assigned_dimension")
    _unique_strings(item.hard_constraints, f"{path}.hard_constraints")
    for index, evidence in enumerate(item.evidence_summary):
        _validate_evidence(evidence, f"{path}.evidence_summary[{index}]")
    if not _required_mapping(item.output_contract, f"{path}.output_contract"):
        raise ContractError(f"{path}.output_contract must not be empty")


def _validate_evidence(item: CouncilEvidenceDatum, path: str) -> None:
    if not isinstance(item, CouncilEvidenceDatum):
        raise ContractError(f"{path} must be CouncilEvidenceDatum")
    _required_string(item.id, f"{path}.id")
    _required_string(item.claim, f"{path}.claim")
    if item.source is not None:
        _required_string(item.source, f"{path}.source")
    if item.treatment != "DATA_ONLY":
        raise ContractError(f"{path} external evidence must remain DATA_ONLY")


def _validate_usage(item: CouncilUsage, path: str) -> None:
    if not isinstance(item, CouncilUsage):
        raise ContractError(f"{path} must be CouncilUsage")
    for name in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = getattr(item, name)
        if value is not None and (type(value) is not int or value < 0):
            raise ContractError(f"{path}.{name} must be an integer >= 0 or null")
    if (
        item.prompt_tokens is not None
        and item.completion_tokens is not None
        and item.total_tokens is not None
        and item.total_tokens < item.prompt_tokens + item.completion_tokens
    ):
        raise ContractError(f"{path}.total_tokens is inconsistent")


def _validate_https_url(value: Any, path: str) -> None:
    url = _required_string(value, path)
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ContractError(f"{path} must be a credential-free HTTPS base URL")


def _required_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{path} must be a non-empty string")
    return value.strip()


def _required_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    return copy.deepcopy(dict(value))


def _unique_strings(values: Sequence[str], path: str) -> list[str]:
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        raise ContractError(f"{path} must be a sequence of strings")
    result: list[str] = []
    for index, item in enumerate(values):
        cleaned = _required_string(item, f"{path}[{index}]")
        if cleaned in result:
            raise ContractError(f"{path} cannot contain duplicates")
        result.append(cleaned)
    return result


def _exact_keys(value: Any, expected: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractError(f"{path} must be an object")
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing or unknown:
        raise ContractError(
            f"{path} keys invalid; missing={sorted(missing)}, unknown={sorted(unknown)}"
        )
    return value


def _enum(enum_type: type[Enum], value: Any, path: str) -> Any:
    try:
        return enum_type(value)
    except (TypeError, ValueError) as exc:
        raise ContractError(f"{path} is invalid") from exc


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


def _load_json(value: str | None) -> Any:
    raw = value if value is not None else sys.stdin.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON: {exc}") from exc


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser(
        "validate-config", help="validate Council provider configuration"
    )
    validate.add_argument("--json", help="config JSON; defaults to stdin")
    defaults = subparsers.add_parser(
        "defaults", help="emit disabled provider templates"
    )
    defaults.set_defaults(command="defaults")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        config = (
            default_runtime_config()
            if args.command == "defaults"
            else runtime_config_from_dict(_load_json(args.json))
        )
        print(
            json.dumps(
                {
                    "config": runtime_config_to_dict(config),
                    "readiness": _json_ready(council_readiness(config)),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 0
    except ContractError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
