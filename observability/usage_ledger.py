"""Provider-reported usage receipts and versioned token-cost calculation."""

from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from typing import Any, Generic, Mapping, TypeVar


PRICE_TABLE_SCHEMA_VERSION = 1
MILLION = Decimal("1000000")
PayloadT = TypeVar("PayloadT")


class UsageLedgerError(ValueError):
    """Raised when pricing or usage data violates the strict contract."""


class UsageSource(str, Enum):
    PROVIDER = "PROVIDER"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class ProviderUsage:
    request_id: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None
    tool_calls: int | None
    latency_ms: int | float
    usage_source: UsageSource = UsageSource.PROVIDER

    @classmethod
    def unavailable(
        cls, request_id: str, *, latency_ms: int | float
    ) -> "ProviderUsage":
        return cls(
            request_id=request_id,
            prompt_tokens=None,
            completion_tokens=None,
            cached_tokens=None,
            tool_calls=None,
            latency_ms=latency_ms,
            usage_source=UsageSource.UNAVAILABLE,
        )


@dataclass(frozen=True)
class ObservedExternalResult(Generic[PayloadT]):
    payload: PayloadT
    usage: ProviderUsage


class ObservedExternalError(RuntimeError):
    """An external failure that still carries billable provider usage."""

    def __init__(self, message: str, usage: ProviderUsage) -> None:
        super().__init__(message)
        validate_provider_usage(usage)
        self.usage = usage


@dataclass(frozen=True)
class ModelPrice:
    prompt_per_million: Decimal
    completion_per_million: Decimal
    cached_per_million: Decimal
    prompt_tokens_include_cached: bool


@dataclass(frozen=True)
class PriceTable:
    version: str
    currency: str
    providers: dict[str, dict[str, ModelPrice]]

    @classmethod
    def load(cls, path: str | Path) -> "PriceTable":
        try:
            value = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UsageLedgerError(f"cannot load provider pricing: {exc}") from exc
        return cls.from_dict(value)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "PriceTable":
        expected = {"schema_version", "version", "currency", "providers"}
        if not isinstance(value, Mapping) or set(value) != expected:
            raise UsageLedgerError("price table has invalid keys")
        if value["schema_version"] != PRICE_TABLE_SCHEMA_VERSION:
            raise UsageLedgerError("unsupported price table schema_version")
        version = _nonempty(value["version"], "version")
        currency = _nonempty(value["currency"], "currency").upper()
        providers_value = value["providers"]
        if not isinstance(providers_value, Mapping):
            raise UsageLedgerError("providers must be an object")
        providers: dict[str, dict[str, ModelPrice]] = {}
        for provider_name, provider_value in providers_value.items():
            provider = _nonempty(provider_name, "provider")
            if not isinstance(provider_value, Mapping) or set(provider_value) != {"models"}:
                raise UsageLedgerError(f"provider {provider!r} must contain only models")
            models_value = provider_value["models"]
            if not isinstance(models_value, Mapping):
                raise UsageLedgerError(f"provider {provider!r}.models must be an object")
            models: dict[str, ModelPrice] = {}
            for model_name, rate_value in models_value.items():
                model = _nonempty(model_name, "model")
                expected_rates = {
                    "prompt_per_million",
                    "completion_per_million",
                    "cached_per_million",
                    "prompt_tokens_include_cached",
                }
                if not isinstance(rate_value, Mapping) or set(rate_value) != expected_rates:
                    raise UsageLedgerError(
                        f"pricing for {provider}/{model} has invalid keys"
                    )
                include_cached = rate_value["prompt_tokens_include_cached"]
                if type(include_cached) is not bool:
                    raise UsageLedgerError(
                        "prompt_tokens_include_cached must be boolean"
                    )
                models[model] = ModelPrice(
                    prompt_per_million=_decimal_rate(
                        rate_value["prompt_per_million"], "prompt_per_million"
                    ),
                    completion_per_million=_decimal_rate(
                        rate_value["completion_per_million"],
                        "completion_per_million",
                    ),
                    cached_per_million=_decimal_rate(
                        rate_value["cached_per_million"], "cached_per_million"
                    ),
                    prompt_tokens_include_cached=include_cached,
                )
            providers[provider] = models
        return cls(version=version, currency=currency, providers=providers)

    def price(self, provider: str, model: str) -> ModelPrice | None:
        return self.providers.get(provider, {}).get(model)


@dataclass(frozen=True)
class UsageReceipt:
    run_id: str
    stage: str
    provider: str
    model: str
    request_id: str
    prompt_tokens: int | None
    completion_tokens: int | None
    cached_tokens: int | None
    tool_calls: int | None
    latency_ms: int | float
    price_table_version: str
    calculated_cost: float | None
    currency: str
    usage_source: UsageSource

    @property
    def receipt_id(self) -> str:
        identity = {
            "run_id": self.run_id,
            "stage": self.stage,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
        }
        digest = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        return f"usage:v1:sha256:{digest}"

    def to_dict(self) -> dict[str, Any]:
        validate_usage_receipt(self)
        return {
            "run_id": self.run_id,
            "stage": self.stage,
            "provider": self.provider,
            "model": self.model,
            "request_id": self.request_id,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "cached_tokens": self.cached_tokens,
            "tool_calls": self.tool_calls,
            "latency_ms": self.latency_ms,
            "price_table_version": self.price_table_version,
            "calculated_cost": self.calculated_cost,
            "currency": self.currency,
            "usage_source": self.usage_source.value,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "UsageReceipt":
        expected = {
            "run_id",
            "stage",
            "provider",
            "model",
            "request_id",
            "prompt_tokens",
            "completion_tokens",
            "cached_tokens",
            "tool_calls",
            "latency_ms",
            "price_table_version",
            "calculated_cost",
            "currency",
            "usage_source",
        }
        if not isinstance(value, Mapping) or set(value) != expected:
            raise UsageLedgerError("usage receipt has invalid keys")
        try:
            source = UsageSource(value["usage_source"])
        except (TypeError, ValueError) as exc:
            raise UsageLedgerError("usage_source is invalid") from exc
        receipt = cls(
            run_id=value["run_id"],
            stage=value["stage"],
            provider=value["provider"],
            model=value["model"],
            request_id=value["request_id"],
            prompt_tokens=value["prompt_tokens"],
            completion_tokens=value["completion_tokens"],
            cached_tokens=value["cached_tokens"],
            tool_calls=value["tool_calls"],
            latency_ms=value["latency_ms"],
            price_table_version=value["price_table_version"],
            calculated_cost=value["calculated_cost"],
            currency=value["currency"],
            usage_source=source,
        )
        validate_usage_receipt(receipt)
        return receipt


class UsageLedger:
    def __init__(self, price_table: PriceTable) -> None:
        if not isinstance(price_table, PriceTable):
            raise UsageLedgerError("price_table must be PriceTable")
        self.price_table = price_table

    def create_receipt(
        self,
        *,
        run_id: str,
        stage: str,
        provider: str,
        model: str,
        usage: ProviderUsage,
    ) -> UsageReceipt:
        validate_provider_usage(usage)
        rate = self.price_table.price(provider, model)
        cost = None
        if usage.usage_source is UsageSource.PROVIDER and rate is not None:
            prompt = usage.prompt_tokens or 0
            cached = usage.cached_tokens or 0
            ordinary_prompt = prompt - cached if rate.prompt_tokens_include_cached else prompt
            if ordinary_prompt < 0:
                raise UsageLedgerError("cached_tokens cannot exceed prompt_tokens")
            calculated = (
                Decimal(ordinary_prompt) * rate.prompt_per_million
                + Decimal(usage.completion_tokens or 0) * rate.completion_per_million
                + Decimal(cached) * rate.cached_per_million
            ) / MILLION
            cost = float(calculated.quantize(Decimal("0.000000000001")))
        receipt = UsageReceipt(
            run_id=_nonempty(run_id, "run_id"),
            stage=_nonempty(stage, "stage"),
            provider=_nonempty(provider, "provider"),
            model=_nonempty(model, "model"),
            request_id=usage.request_id,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cached_tokens=usage.cached_tokens,
            tool_calls=usage.tool_calls,
            latency_ms=usage.latency_ms,
            price_table_version=self.price_table.version,
            calculated_cost=cost,
            currency=self.price_table.currency,
            usage_source=usage.usage_source,
        )
        validate_usage_receipt(receipt)
        return receipt

    @staticmethod
    def merge(
        existing: list[dict[str, Any]], receipts: list[UsageReceipt]
    ) -> list[dict[str, Any]]:
        parsed = [UsageReceipt.from_dict(item) for item in existing]
        by_id = {item.receipt_id: item for item in parsed}
        for receipt in receipts:
            validate_usage_receipt(receipt)
            previous = by_id.get(receipt.receipt_id)
            if previous is not None and previous != receipt:
                raise UsageLedgerError("usage receipt identity cannot be overwritten")
            by_id.setdefault(receipt.receipt_id, copy.deepcopy(receipt))
        return [item.to_dict() for item in by_id.values()]

    @staticmethod
    def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
        receipts = [UsageReceipt.from_dict(item) for item in records]
        currencies = {item.currency for item in receipts}
        if len(currencies) > 1:
            raise UsageLedgerError("usage ledger cannot aggregate mixed currencies")
        return {
            "prompt_tokens": sum(item.prompt_tokens or 0 for item in receipts),
            "completion_tokens": sum(item.completion_tokens or 0 for item in receipts),
            "cached_tokens": sum(item.cached_tokens or 0 for item in receipts),
            "tool_calls": sum(item.tool_calls or 0 for item in receipts),
            "calculated_cost": round(
                sum(item.calculated_cost or 0.0 for item in receipts), 12
            ),
            "priced_calls": sum(item.calculated_cost is not None for item in receipts),
            "unpriced_calls": sum(
                item.usage_source is UsageSource.PROVIDER
                and item.calculated_cost is None
                for item in receipts
            ),
            "unavailable_calls": sum(
                item.usage_source is UsageSource.UNAVAILABLE for item in receipts
            ),
            "currency": None if not currencies else next(iter(currencies)),
        }


def validate_provider_usage(usage: ProviderUsage) -> None:
    if not isinstance(usage, ProviderUsage):
        raise UsageLedgerError("usage must be ProviderUsage")
    _nonempty(usage.request_id, "request_id")
    _nonnegative_number(usage.latency_ms, "latency_ms")
    for name in ("prompt_tokens", "completion_tokens", "cached_tokens", "tool_calls"):
        value = getattr(usage, name)
        if value is not None and (type(value) is not int or value < 0):
            raise UsageLedgerError(f"{name} must be an integer >= 0 or null")
    if not isinstance(usage.usage_source, UsageSource):
        raise UsageLedgerError("usage_source must be UsageSource")
    token_values = (
        usage.prompt_tokens,
        usage.completion_tokens,
        usage.cached_tokens,
        usage.tool_calls,
    )
    if usage.usage_source is UsageSource.PROVIDER and (
        usage.prompt_tokens is None or usage.completion_tokens is None
    ):
        raise UsageLedgerError(
            "provider usage requires prompt_tokens and completion_tokens"
        )
    if usage.usage_source is UsageSource.UNAVAILABLE and any(
        item is not None for item in token_values
    ):
        raise UsageLedgerError("UNAVAILABLE usage must not invent zero token/tool values")


def validate_usage_receipt(receipt: UsageReceipt) -> None:
    if not isinstance(receipt, UsageReceipt):
        raise UsageLedgerError("receipt must be UsageReceipt")
    for name in (
        "run_id",
        "stage",
        "provider",
        "model",
        "request_id",
        "price_table_version",
        "currency",
    ):
        _nonempty(getattr(receipt, name), name)
    _nonnegative_number(receipt.latency_ms, "latency_ms")
    if receipt.calculated_cost is not None:
        _nonnegative_number(receipt.calculated_cost, "calculated_cost")
    validate_provider_usage(
        ProviderUsage(
            request_id=receipt.request_id,
            prompt_tokens=receipt.prompt_tokens,
            completion_tokens=receipt.completion_tokens,
            cached_tokens=receipt.cached_tokens,
            tool_calls=receipt.tool_calls,
            latency_ms=receipt.latency_ms,
            usage_source=receipt.usage_source,
        )
    )
    if receipt.usage_source is UsageSource.UNAVAILABLE and receipt.calculated_cost is not None:
        raise UsageLedgerError("UNAVAILABLE usage cannot have calculated_cost")


def _decimal_rate(value: Any, path: str) -> Decimal:
    if isinstance(value, bool):
        raise UsageLedgerError(f"{path} must be a non-negative number")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise UsageLedgerError(f"{path} must be a non-negative number") from exc
    if not result.is_finite() or result < 0:
        raise UsageLedgerError(f"{path} must be a non-negative number")
    return result


def _nonnegative_number(value: Any, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise UsageLedgerError(f"{path} must be a non-negative number")


def _nonempty(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise UsageLedgerError(f"{path} must be a non-empty string")
    return value.strip()
