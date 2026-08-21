"""Deterministic lifecycle fault injection for full-version acceptance tests.

The injector is inert unless explicit rules are supplied. Production code can
place ``injector.check(stage, point)`` at lifecycle boundaries without adding
test-only branches to business logic.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping


class Stage(str, Enum):
    INITIALIZE = "INITIALIZE"
    ROUTE = "ROUTE"
    CONTEXT = "CONTEXT"
    FRAME = "FRAME"
    DIVERGE = "DIVERGE"
    NORMALIZE = "NORMALIZE"
    CHALLENGE = "CHALLENGE"
    RESEARCH = "RESEARCH"
    CONVERGE = "CONVERGE"
    EVALUATE = "EVALUATE"
    COMMIT = "COMMIT"


class FaultPoint(str, Enum):
    BEFORE_ENTER = "before_enter"
    AFTER_CHECKPOINT = "after_checkpoint"
    BEFORE_EXTERNAL_CALL = "before_external_call"
    AFTER_EXTERNAL_CALL = "after_external_call"
    BEFORE_COMMIT = "before_commit"


class FaultAction(str, Enum):
    ERROR = "error"
    INTERRUPT = "interrupt"


@dataclass(frozen=True)
class FaultRule:
    """A deterministic rule triggered on one visit to a stage boundary."""

    stage: Stage
    point: FaultPoint
    action: FaultAction = FaultAction.ERROR
    occurrence: int = 1
    repeat: bool = False
    label: str | None = None

    def __post_init__(self) -> None:
        if self.occurrence < 1:
            raise ValueError("fault occurrence must be >= 1")


@dataclass(frozen=True)
class FaultEvent:
    stage: Stage
    point: FaultPoint
    action: FaultAction
    occurrence: int
    label: str | None
    context: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "point": self.point.value,
            "action": self.action.value,
            "occurrence": self.occurrence,
            "label": self.label,
            "context": dict(self.context),
        }


class InjectedFault(RuntimeError):
    """Catchable injected runtime failure."""

    def __init__(self, event: FaultEvent):
        self.event = event
        super().__init__(_event_message(event))


class InjectedInterruption(KeyboardInterrupt):
    """Injected process interruption with KeyboardInterrupt semantics."""

    def __init__(self, event: FaultEvent):
        self.event = event
        super().__init__(_event_message(event))


class FaultInjector:
    """Apply explicit fault rules and retain an auditable trigger history."""

    def __init__(self, rules: Iterable[FaultRule] = ()) -> None:
        self._rules = tuple(rules)
        self._validate_rules()
        self._visits: dict[tuple[Stage, FaultPoint], int] = defaultdict(int)
        self._triggered: list[FaultEvent] = []

    @classmethod
    def disabled(cls) -> "FaultInjector":
        return cls()

    @classmethod
    def from_dicts(cls, values: Iterable[Mapping[str, Any]]) -> "FaultInjector":
        rules = []
        for value in values:
            unknown = set(value) - {
                "stage",
                "point",
                "action",
                "occurrence",
                "repeat",
                "label",
            }
            if unknown:
                raise ValueError(f"unknown fault-rule fields: {sorted(unknown)}")
            rules.append(
                FaultRule(
                    stage=Stage(value["stage"]),
                    point=FaultPoint(value["point"]),
                    action=FaultAction(value.get("action", FaultAction.ERROR.value)),
                    occurrence=value.get("occurrence", 1),
                    repeat=value.get("repeat", False),
                    label=value.get("label"),
                )
            )
        return cls(rules)

    @property
    def rules(self) -> tuple[FaultRule, ...]:
        return self._rules

    @property
    def triggered_events(self) -> tuple[FaultEvent, ...]:
        return tuple(self._triggered)

    def visits(self, stage: Stage | str, point: FaultPoint | str) -> int:
        return self._visits[(Stage(stage), FaultPoint(point))]

    def check(
        self,
        stage: Stage | str,
        point: FaultPoint | str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> None:
        """Raise the configured fault at this lifecycle boundary, if any."""

        normalized_stage = Stage(stage)
        normalized_point = FaultPoint(point)
        key = (normalized_stage, normalized_point)
        self._visits[key] += 1
        visit = self._visits[key]

        for rule in self._rules:
            if rule.stage != normalized_stage or rule.point != normalized_point:
                continue
            if visit != rule.occurrence and not (rule.repeat and visit >= rule.occurrence):
                continue
            event = FaultEvent(
                stage=normalized_stage,
                point=normalized_point,
                action=rule.action,
                occurrence=visit,
                label=rule.label,
                context=dict(context or {}),
            )
            self._triggered.append(event)
            if rule.action is FaultAction.INTERRUPT:
                raise InjectedInterruption(event)
            raise InjectedFault(event)

    def _validate_rules(self) -> None:
        identities: set[tuple[Stage, FaultPoint, int]] = set()
        for rule in self._rules:
            identity = (rule.stage, rule.point, rule.occurrence)
            if identity in identities:
                raise ValueError(
                    "duplicate fault rule for "
                    f"{rule.stage.value}/{rule.point.value}/{rule.occurrence}"
                )
            identities.add(identity)


def _event_message(event: FaultEvent) -> str:
    label = f" ({event.label})" if event.label else ""
    return (
        f"injected {event.action.value} at "
        f"{event.stage.value}/{event.point.value} visit {event.occurrence}{label}"
    )

