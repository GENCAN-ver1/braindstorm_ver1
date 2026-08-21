from __future__ import annotations

import copy
import json
import math
import unittest
from pathlib import Path

from runtime.fault_injection import (
    FaultAction,
    FaultInjector,
    FaultPoint,
    FaultRule,
    InjectedFault,
    InjectedInterruption,
    Stage,
)
from runtime.state_fingerprint import (
    MAIN_STATE_FIELDS,
    StateFingerprintError,
    canonical_state_payload,
    fingerprint_state,
)


PROJECT_ROOT = Path(__file__).parents[2]
MANIFEST_PATH = PROJECT_ROOT / "acceptance" / "manifest.json"
REPORT_SCHEMA_PATH = PROJECT_ROOT / "acceptance" / "report.schema.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = load_json(MANIFEST_PATH)

    def test_exactly_eight_unique_acceptance_criteria_are_registered(self):
        criteria = self.manifest["criteria"]
        ids = [item["id"] for item in criteria]
        self.assertEqual(ids, [f"AC-{index:02d}" for index in range(1, 9)])
        self.assertEqual(len(ids), len(set(ids)))

    def test_manifest_stage_and_fault_matrices_match_runtime_enums(self):
        self.assertEqual(
            self.manifest["stage_matrix"], [item.value for item in Stage]
        )
        self.assertEqual(
            self.manifest["fault_points"], [item.value for item in FaultPoint]
        )

    def test_manifest_fingerprint_fields_match_runtime_contract(self):
        self.assertEqual(
            self.manifest["state_fingerprint_fields"], list(MAIN_STATE_FIELDS)
        )

    def test_every_fixture_exists_and_is_valid_json(self):
        for criterion in self.manifest["criteria"]:
            for relative_path in criterion["fixtures"]:
                path = PROJECT_ROOT / relative_path
                self.assertTrue(path.is_file(), f"missing fixture: {relative_path}")
                self.assertIsInstance(load_json(path), dict)

    def test_criterion_status_tracks_real_implementation_progress(self):
        allowed = set(self.manifest["criterion_status_values"])
        self.assertEqual(allowed, {"SCAFFOLDED", "IMPLEMENTED"})
        statuses = {item["id"]: item["status"] for item in self.manifest["criteria"]}
        self.assertEqual(statuses["AC-01"], "IMPLEMENTED")
        self.assertEqual(statuses["AC-02"], "IMPLEMENTED")
        self.assertEqual(statuses["AC-03"], "IMPLEMENTED")
        self.assertEqual(statuses["AC-05"], "IMPLEMENTED")
        self.assertEqual(statuses["AC-06"], "IMPLEMENTED")
        self.assertEqual(statuses["AC-04"], "IMPLEMENTED")
        self.assertEqual(statuses["AC-08"], "IMPLEMENTED")
        self.assertEqual(statuses["AC-07"], "IMPLEMENTED")

    def test_acceptance_report_contract_has_all_required_audit_fields(self):
        schema = load_json(REPORT_SCHEMA_PATH)
        self.assertEqual(
            set(schema["required"]),
            {
                "schema_version",
                "suite_id",
                "criterion_id",
                "test_id",
                "implementation_status",
                "version_fingerprint",
                "started_at",
                "finished_at",
                "result",
                "failure_reason",
                "artifact_paths",
                "trace_path",
            },
        )
        self.assertIn("NOT_IMPLEMENTED", schema["properties"]["result"]["enum"])


class FaultInjectorTests(unittest.TestCase):
    def test_every_stage_and_fault_point_can_be_injected(self):
        for stage in Stage:
            for point in FaultPoint:
                injector = FaultInjector([FaultRule(stage=stage, point=point)])
                with self.assertRaises(InjectedFault) as raised:
                    injector.check(stage, point, context={"run_id": "run-fv00"})
                self.assertEqual(raised.exception.event.stage, stage)
                self.assertEqual(raised.exception.event.point, point)
                self.assertEqual(raised.exception.event.context["run_id"], "run-fv00")

    def test_rule_triggers_only_on_configured_occurrence(self):
        injector = FaultInjector(
            [
                FaultRule(
                    stage=Stage.DIVERGE,
                    point=FaultPoint.AFTER_CHECKPOINT,
                    occurrence=2,
                )
            ]
        )
        injector.check(Stage.DIVERGE, FaultPoint.AFTER_CHECKPOINT)
        with self.assertRaises(InjectedFault):
            injector.check(Stage.DIVERGE, FaultPoint.AFTER_CHECKPOINT)
        injector.check(Stage.DIVERGE, FaultPoint.AFTER_CHECKPOINT)
        self.assertEqual(
            injector.visits(Stage.DIVERGE, FaultPoint.AFTER_CHECKPOINT), 3
        )
        self.assertEqual(len(injector.triggered_events), 1)

    def test_interrupt_uses_keyboard_interrupt_semantics(self):
        injector = FaultInjector(
            [
                FaultRule(
                    stage=Stage.RESEARCH,
                    point=FaultPoint.BEFORE_EXTERNAL_CALL,
                    action=FaultAction.INTERRUPT,
                )
            ]
        )
        with self.assertRaises(InjectedInterruption):
            injector.check(Stage.RESEARCH, FaultPoint.BEFORE_EXTERNAL_CALL)
        self.assertTrue(issubclass(InjectedInterruption, KeyboardInterrupt))

    def test_disabled_injector_is_inert_but_counts_visits(self):
        injector = FaultInjector.disabled()
        injector.check(Stage.ROUTE, FaultPoint.BEFORE_ENTER)
        self.assertEqual(injector.visits(Stage.ROUTE, FaultPoint.BEFORE_ENTER), 1)
        self.assertEqual(injector.triggered_events, ())

    def test_invalid_or_duplicate_rules_are_rejected(self):
        with self.assertRaises(ValueError):
            FaultRule(Stage.ROUTE, FaultPoint.BEFORE_ENTER, occurrence=0)
        rule = FaultRule(Stage.ROUTE, FaultPoint.BEFORE_ENTER)
        with self.assertRaises(ValueError):
            FaultInjector([rule, rule])
        with self.assertRaises(ValueError):
            FaultInjector.from_dicts(
                [{"stage": "ROUTE", "point": "before_enter", "secret": "x"}]
            )


class StateFingerprintTests(unittest.TestCase):
    def state(self):
        return {
            "frame": {"problem": "choose a reversible concept"},
            "candidates": [{"id": "c1"}, {"id": "c2"}],
            "assumptions": [{"id": "a1", "statement": "users need guidance"}],
            "unknowns": [{"id": "u1", "statement": "conversion baseline"}],
            "evidence": [{"id": "e1", "claim": "supporting evidence"}],
            "decisions": [{"id": "d1", "status": "LOCKED", "value": "c1"}],
            "result": {"recommendation": "c1"},
            "ephemeral": {"timestamp": "ignored"},
        }

    def test_fingerprint_is_deterministic_across_mapping_key_order(self):
        state = self.state()
        reversed_state = dict(reversed(list(state.items())))
        self.assertEqual(fingerprint_state(state), fingerprint_state(reversed_state))
        self.assertEqual(canonical_state_payload(state), canonical_state_payload(state))

    def test_each_main_state_field_changes_the_fingerprint(self):
        original = self.state()
        baseline = fingerprint_state(original)
        for field in MAIN_STATE_FIELDS:
            changed = copy.deepcopy(original)
            changed[field] = {"changed": field}
            self.assertNotEqual(
                baseline,
                fingerprint_state(changed),
                f"field was not covered by fingerprint: {field}",
            )

    def test_non_main_state_field_does_not_change_fingerprint(self):
        original = self.state()
        changed = copy.deepcopy(original)
        changed["ephemeral"] = {"timestamp": "different"}
        self.assertEqual(fingerprint_state(original), fingerprint_state(changed))

    def test_missing_or_non_json_state_is_rejected(self):
        state = self.state()
        del state["decisions"]
        with self.assertRaises(StateFingerprintError):
            fingerprint_state(state)
        state = self.state()
        state["result"] = {"score": math.nan}
        with self.assertRaises(StateFingerprintError):
            fingerprint_state(state)


if __name__ == "__main__":
    unittest.main()
