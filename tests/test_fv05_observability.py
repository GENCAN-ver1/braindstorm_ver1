from __future__ import annotations

import copy
import json
import unittest
import uuid
from pathlib import Path

from observability.events import EventKind, EventSpec, TraceEvent
from observability.trace_sink import TraceSink, TraceSinkError
from observability.usage_ledger import (
    PriceTable,
    ProviderUsage,
    UsageLedger,
    UsageReceipt,
    UsageSource,
)
from runtime.checkpoint import CheckpointStore, CheckpointValidationError
from runtime.config_loader import config_from_dict
from runtime.fault_injection import Stage
from runtime.full_cycle import FullCycleRunner
from runtime.governor_modules import p2
from tests.fv04_support import state
from tests.test_fv01_full_cycle import valid_config_dict


PROJECT_ROOT = Path(__file__).parents[1]
PRICING_PATH = PROJECT_ROOT / "config" / "provider-pricing.json"


class UsageLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = UsageLedger(PriceTable.load(PRICING_PATH))

    def test_provider_tokens_and_versioned_rates_calculate_cost(self):
        receipt = self.ledger.create_receipt(
            run_id="run-usage",
            stage="RESEARCH",
            provider="fixture-research",
            model="fixture-model",
            usage=ProviderUsage(
                request_id="request-1",
                prompt_tokens=1000,
                completion_tokens=500,
                cached_tokens=200,
                tool_calls=2,
                latency_ms=125,
            ),
        )
        self.assertEqual(receipt.price_table_version, "builtin-fixture-v1")
        self.assertEqual(receipt.calculated_cost, 0.00185)
        self.assertEqual(receipt.usage_source, UsageSource.PROVIDER)

    def test_unavailable_usage_is_null_not_fabricated_zero(self):
        receipt = self.ledger.create_receipt(
            run_id="run-unavailable",
            stage="EVALUATE",
            provider="unknown-provider",
            model="unknown-model",
            usage=ProviderUsage.unavailable("local:1", latency_ms=5),
        )
        self.assertIsNone(receipt.prompt_tokens)
        self.assertIsNone(receipt.completion_tokens)
        self.assertIsNone(receipt.tool_calls)
        self.assertIsNone(receipt.calculated_cost)
        summary = UsageLedger.summarize([receipt.to_dict()])
        self.assertEqual(summary["unavailable_calls"], 1)
        self.assertEqual(summary["calculated_cost"], 0.0)

    def test_receipt_fields_match_frozen_ac06_contract(self):
        fixture = json.loads(
            (PROJECT_ROOT / "tests/acceptance/fixtures/ac06_trace_usage.json")
            .read_text(encoding="utf-8")
        )
        receipt = self.ledger.create_receipt(
            run_id="run-fields",
            stage="RESEARCH",
            provider="fixture-research",
            model="fixture-model",
            usage=ProviderUsage("req-fields", 1, 2, 0, 1, 3),
        )
        self.assertEqual(set(receipt.to_dict()), set(fixture["provider_receipt_fields"]))


class TraceSinkTests(unittest.TestCase):
    def path(self, suffix):
        path = PROJECT_ROOT / "tests" / f".fv05-{uuid.uuid4().hex}{suffix}"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(
            path.with_name(f".{path.name}.lock").unlink, missing_ok=True
        )
        self.addCleanup(
            path.with_name(f".{path.name}.cas.lock").unlink, missing_ok=True
        )
        return path

    def test_trace_is_append_only_sequential_and_idempotent(self):
        sink = TraceSink(self.path(".trace.json"))
        first = TraceEvent.create(
            run_id="run-trace",
            revision=1,
            trace_cursor=1,
            spec=EventSpec(EventKind.CHECKPOINT_SAVED, "ROUTE"),
        )
        sink.append_batch([first])
        sink.append_batch([first])
        self.assertEqual(len(sink.read()["events"]), 1)
        conflicting = TraceEvent.create(
            run_id="run-trace",
            revision=2,
            trace_cursor=1,
            spec=EventSpec(EventKind.RECOVERY, "ROUTE"),
        )
        with self.assertRaises(TraceSinkError):
            sink.append_batch([conflicting])

    def test_fv04_checkpoint_without_usage_ids_migrates_on_save(self):
        path = self.path(".md")
        CheckpointStore().open(path, state("run-legacy-fv05"))
        brief = p2.load_brief(path)
        record = next(
            item
            for item in brief.runtime_state.deferred
            if item.get("type") == "brainstorm-governor-checkpoint-v1"
        )
        record["envelope"].pop("usage_receipt_ids")
        p2.save_round(path, brief, brief.runtime_state, next_action="legacy FV-04")
        restored = CheckpointStore().open(path, state("ignored"))
        self.assertEqual(restored.envelope.usage_receipt_ids, [])
        restored.mark_recovered()
        saved = p2.load_brief(path)
        saved_record = next(
            item
            for item in saved.runtime_state.deferred
            if item.get("type") == "brainstorm-governor-checkpoint-v1"
        )
        self.assertIn("usage_receipt_ids", saved_record["envelope"])

    def test_full_cycle_runner_creates_linked_checkpoint_and_exit_trace(self):
        brief_path = self.path(".runner.md")
        trace_path = brief_path.with_name(f"{brief_path.name}.trace.json")
        self.addCleanup(trace_path.unlink, missing_ok=True)
        self.addCleanup(
            trace_path.with_name(f".{trace_path.name}.lock").unlink,
            missing_ok=True,
        )
        summary = FullCycleRunner(config_from_dict(valid_config_dict())).run(
            {
                "request_id": "run-fv05-full-cycle",
                "text": "Shape a reversible onboarding concept.",
                "routing": {"ambiguous_concept": True},
            },
            brief_path=brief_path,
        )
        self.assertEqual(summary.exit_status, "NEEDS_INPUT")
        trace = TraceSink(trace_path).read()
        kinds = {item["kind"] for item in trace["events"]}
        self.assertIn(EventKind.CHECKPOINT_SAVED.value, kinds)
        self.assertIn(EventKind.EXIT_STATUS.value, kinds)
        restored = CheckpointStore().open(brief_path, state("ignored"))
        self.assertEqual(
            restored.envelope.trace_cursor, trace["events"][-1]["trace_cursor"]
        )

    def test_present_trace_must_match_checkpoint_revision_and_cursor(self):
        brief_path = self.path(".linked.md")
        trace_path = self.path(".linked.trace.json")
        sink = TraceSink(trace_path)
        session = CheckpointStore(trace_sink=sink).open(
            brief_path, state("run-link-check"), initial_next_stage=Stage.ROUTE
        )
        session.enter_stage(Stage.ROUTE)
        detached = CheckpointStore().open(brief_path, state("ignored"))
        detached.update_progress(trace_cursor=detached.envelope.trace_cursor + 1)
        with self.assertRaises(CheckpointValidationError):
            CheckpointStore(trace_sink=sink).open(brief_path, state("ignored"))


if __name__ == "__main__":
    unittest.main()
