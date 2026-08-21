"""Atomic append-only trace storage linked to Brief revision and cursor."""

from __future__ import annotations

import copy
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from observability.events import TraceEvent
from observability.usage_ledger import UsageLedger, UsageReceipt


TRACE_DOCUMENT_SCHEMA_VERSION = 1


class TraceSinkError(ValueError):
    """Raised when append-only trace invariants would be violated."""


class TraceSink:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).resolve()

    def has_dedupe_key(self, run_id: str, dedupe_key: str) -> bool:
        document = self.read()
        if document is None or document["run_id"] != run_id:
            return False
        return any(
            item["details"].get("dedupe_key") == dedupe_key
            for item in document["events"]
        )

    def validate_link(self, run_id: str, revision: int, trace_cursor: int) -> None:
        """Reject a present trace that disagrees with its canonical checkpoint."""
        document = self.read()
        if document is None:
            return
        if document["run_id"] != run_id:
            raise TraceSinkError("trace run_id conflicts with checkpoint")
        events = document["events"]
        actual_cursor = (
            document["base_cursor"] if not events else events[-1]["trace_cursor"]
        )
        if actual_cursor != trace_cursor:
            raise TraceSinkError(
                f"trace cursor mismatch: checkpoint={trace_cursor}, trace={actual_cursor}"
            )
        if events and events[-1]["revision"] != revision:
            raise TraceSinkError(
                f"trace revision mismatch: checkpoint={revision}, "
                f"trace={events[-1]['revision']}"
            )

    def append_batch(
        self,
        events: Sequence[TraceEvent],
        usage_receipts: Sequence[UsageReceipt] = (),
    ) -> None:
        event_items = list(events)
        receipt_items = list(usage_receipts)
        if not event_items and not receipt_items:
            return
        run_ids = {item.run_id for item in event_items} | {
            item.run_id for item in receipt_items
        }
        if len(run_ids) != 1:
            raise TraceSinkError("one append batch must contain exactly one run_id")
        run_id = next(iter(run_ids))
        with _trace_lock(self.path):
            document = self._read_unlocked()
            if document is None:
                first_cursor = event_items[0].trace_cursor if event_items else 1
                document = {
                    "schema_version": TRACE_DOCUMENT_SCHEMA_VERSION,
                    "run_id": run_id,
                    "base_cursor": first_cursor - 1,
                    "events": [],
                    "usage_receipts": [],
                    "summary": UsageLedger.summarize([]),
                }
            if document["run_id"] != run_id:
                raise TraceSinkError("trace run_id cannot be overwritten")

            existing_events = {
                item["event_id"]: TraceEvent.from_dict(item)
                for item in document["events"]
            }
            cursor_map = {
                item.trace_cursor: item.event_id for item in existing_events.values()
            }
            last_cursor = max(
                [document["base_cursor"], *cursor_map.keys()]
            )
            for event in event_items:
                serialized = event.to_dict()
                previous = existing_events.get(event.event_id)
                if previous is not None:
                    if previous.to_dict() != serialized:
                        raise TraceSinkError("trace event identity cannot be overwritten")
                    continue
                if event.trace_cursor in cursor_map:
                    raise TraceSinkError("trace cursor cannot be reused")
                if event.trace_cursor != last_cursor + 1:
                    raise TraceSinkError("trace cursor must append sequentially")
                document["events"].append(serialized)
                existing_events[event.event_id] = event
                cursor_map[event.trace_cursor] = event.event_id
                last_cursor = event.trace_cursor

            document["usage_receipts"] = UsageLedger.merge(
                document["usage_receipts"], receipt_items
            )
            document["summary"] = UsageLedger.summarize(
                document["usage_receipts"]
            )
            self._write_unlocked(document)

    def read(self) -> dict[str, Any] | None:
        with _trace_lock(self.path):
            return self._read_unlocked()

    def _read_unlocked(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TraceSinkError(f"cannot read trace: {exc}") from exc
        return _validate_document(value)

    def _write_unlocked(self, document: Mapping[str, Any]) -> None:
        validated = _validate_document(document)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        payload = json.dumps(
            validated,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(self.path)


def _validate_document(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "run_id",
        "base_cursor",
        "events",
        "usage_receipts",
        "summary",
    }
    if not isinstance(value, Mapping) or set(value) != expected:
        raise TraceSinkError("trace document has invalid keys")
    if value["schema_version"] != TRACE_DOCUMENT_SCHEMA_VERSION:
        raise TraceSinkError("unsupported trace document schema_version")
    if not isinstance(value["run_id"], str) or not value["run_id"].strip():
        raise TraceSinkError("trace run_id must be non-empty")
    if type(value["base_cursor"]) is not int or value["base_cursor"] < 0:
        raise TraceSinkError("base_cursor must be an integer >= 0")
    if not isinstance(value["events"], list):
        raise TraceSinkError("events must be an array")
    events = [TraceEvent.from_dict(item) for item in value["events"]]
    cursors = [item.trace_cursor for item in events]
    expected_cursors = list(
        range(value["base_cursor"] + 1, value["base_cursor"] + 1 + len(events))
    )
    if cursors != expected_cursors:
        raise TraceSinkError("events must have sequential trace cursors")
    if any(item.run_id != value["run_id"] for item in events):
        raise TraceSinkError("event run_id conflicts with trace document")
    if len({item.event_id for item in events}) != len(events):
        raise TraceSinkError("trace events must be unique")
    if not isinstance(value["usage_receipts"], list):
        raise TraceSinkError("usage_receipts must be an array")
    receipts = [UsageReceipt.from_dict(item) for item in value["usage_receipts"]]
    if any(item.run_id != value["run_id"] for item in receipts):
        raise TraceSinkError("usage receipt run_id conflicts with trace document")
    if len({item.receipt_id for item in receipts}) != len(receipts):
        raise TraceSinkError("usage receipts must be unique")
    expected_summary = UsageLedger.summarize(
        [item.to_dict() for item in receipts]
    )
    if value["summary"] != expected_summary:
        raise TraceSinkError("trace usage summary is inconsistent")
    return {
        "schema_version": value["schema_version"],
        "run_id": value["run_id"],
        "base_cursor": value["base_cursor"],
        "events": [item.to_dict() for item in events],
        "usage_receipts": [item.to_dict() for item in receipts],
        "summary": copy.deepcopy(expected_summary),
    }


@contextmanager
def _trace_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f".{path.name}.lock")
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise TraceSinkError(f"trace lock already held for {path}") from exc
    try:
        os.close(descriptor)
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass
