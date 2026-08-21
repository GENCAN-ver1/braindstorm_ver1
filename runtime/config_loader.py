"""Strict, versioned configuration loader for the full-cycle runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


CONFIG_SCHEMA_VERSION = 1
VALID_MODES = {"auto", "Spark", "Shape", "Stress", "Decide"}


class ConfigError(ValueError):
    """Raised when runtime configuration is missing, malformed, or unsafe."""


@dataclass(frozen=True)
class BudgetConfig:
    max_steps: int
    max_parallelism: int


@dataclass(frozen=True)
class RuntimeConfig:
    mode: str
    parallelism: int
    budget: BudgetConfig


@dataclass(frozen=True)
class PersistenceConfig:
    brief_path: str


@dataclass(frozen=True)
class FeatureConfig:
    research: bool
    workers: bool
    council: bool
    evaluator: bool


@dataclass(frozen=True)
class EvaluationConfig:
    max_rounds: int


@dataclass(frozen=True)
class GovernorConfig:
    schema_version: int
    runtime: RuntimeConfig
    persistence: PersistenceConfig
    features: FeatureConfig
    evaluation: EvaluationConfig


def load_config(path: str | Path) -> GovernorConfig:
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ConfigError(f"cannot read config {target}: {exc}") from exc
    return config_from_dict(_parse_document(text, target))


def config_from_dict(value: Mapping[str, Any]) -> GovernorConfig:
    data = _mapping(value, "config")
    _exact_keys(
        data,
        {"schema_version", "runtime", "persistence", "features", "evaluation"},
        "config",
    )
    if type(data["schema_version"]) is not int:
        raise ConfigError("config.schema_version must be an integer")
    if data["schema_version"] != CONFIG_SCHEMA_VERSION:
        raise ConfigError(
            f"unsupported config schema_version {data['schema_version']!r}; "
            f"expected {CONFIG_SCHEMA_VERSION}"
        )

    runtime_data = _mapping(data["runtime"], "config.runtime")
    _exact_keys(runtime_data, {"mode", "parallelism", "budget"}, "config.runtime")
    mode = runtime_data["mode"]
    if mode not in VALID_MODES:
        raise ConfigError(f"config.runtime.mode must be one of {sorted(VALID_MODES)}")
    parallelism = _integer(runtime_data["parallelism"], "config.runtime.parallelism", 1)

    budget_data = _mapping(runtime_data["budget"], "config.runtime.budget")
    _exact_keys(
        budget_data,
        {"max_steps", "max_parallelism"},
        "config.runtime.budget",
    )
    max_steps = _integer(
        budget_data["max_steps"], "config.runtime.budget.max_steps", 4
    )
    max_parallelism = _integer(
        budget_data["max_parallelism"],
        "config.runtime.budget.max_parallelism",
        1,
    )
    if parallelism > max_parallelism:
        raise ConfigError(
            "config.runtime.parallelism cannot exceed budget.max_parallelism"
        )

    persistence_data = _mapping(data["persistence"], "config.persistence")
    _exact_keys(persistence_data, {"brief_path"}, "config.persistence")
    brief_path = _nonempty_string(
        persistence_data["brief_path"], "config.persistence.brief_path"
    )

    feature_data = _mapping(data["features"], "config.features")
    _exact_keys(
        feature_data,
        {"research", "workers", "council", "evaluator"},
        "config.features",
    )
    features = FeatureConfig(
        research=_boolean(feature_data["research"], "config.features.research"),
        workers=_boolean(feature_data["workers"], "config.features.workers"),
        council=_boolean(feature_data["council"], "config.features.council"),
        evaluator=_boolean(feature_data["evaluator"], "config.features.evaluator"),
    )
    if features.council and not features.workers:
        raise ConfigError("config.features.council requires workers=true")

    evaluation_data = _mapping(data["evaluation"], "config.evaluation")
    _exact_keys(evaluation_data, {"max_rounds"}, "config.evaluation")
    max_rounds = _integer(
        evaluation_data["max_rounds"], "config.evaluation.max_rounds", 1
    )
    if max_rounds > 2:
        raise ConfigError("config.evaluation.max_rounds cannot exceed 2")

    return GovernorConfig(
        schema_version=CONFIG_SCHEMA_VERSION,
        runtime=RuntimeConfig(
            mode=mode,
            parallelism=parallelism,
            budget=BudgetConfig(
                max_steps=max_steps,
                max_parallelism=max_parallelism,
            ),
        ),
        persistence=PersistenceConfig(brief_path=brief_path),
        features=features,
        evaluation=EvaluationConfig(max_rounds=max_rounds),
    )


def config_to_dict(config: GovernorConfig) -> dict[str, Any]:
    return {
        "schema_version": config.schema_version,
        "runtime": {
            "mode": config.runtime.mode,
            "parallelism": config.runtime.parallelism,
            "budget": {
                "max_steps": config.runtime.budget.max_steps,
                "max_parallelism": config.runtime.budget.max_parallelism,
            },
        },
        "persistence": {"brief_path": config.persistence.brief_path},
        "features": {
            "research": config.features.research,
            "workers": config.features.workers,
            "council": config.features.council,
            "evaluator": config.features.evaluator,
        },
        "evaluation": {"max_rounds": config.evaluation.max_rounds},
    }


def _parse_document(text: str, path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as json_error:
        if path.suffix.casefold() not in {".yaml", ".yml"}:
            raise ConfigError(f"invalid config JSON: {json_error}") from json_error
        try:
            import yaml  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ConfigError(
                "non-JSON YAML requires optional PyYAML; the bundled example uses "
                "JSON syntax, which is valid YAML and needs no dependency"
            ) from exc
        try:
            value = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise ConfigError(f"invalid config YAML: {exc}") from exc
    return _mapping(value, "config")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ConfigError(f"{path} must be an object")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], path: str) -> None:
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        raise ConfigError(f"{path} is missing keys: {sorted(missing)}")
    if unknown:
        raise ConfigError(f"{path} has unknown keys: {sorted(unknown)}")


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{path} must be a non-empty string")
    return value


def _integer(value: Any, path: str, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ConfigError(f"{path} must be an integer >= {minimum}")
    return value


def _boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise ConfigError(f"{path} must be boolean")
    return value

