from __future__ import annotations

import copy
import json
import tempfile
import unittest
import uuid
from pathlib import Path

from runtime.config_loader import (
    ConfigError,
    config_from_dict,
    config_to_dict,
    load_config,
)
from runtime.full_cycle import FullCycleRunner, RequestError, p2, request_from_dict


PROJECT_ROOT = Path(__file__).parents[1]
EXAMPLE_CONFIG = PROJECT_ROOT / "config" / "brainstorm-governor.example.yaml"


def valid_config_dict():
    return {
        "schema_version": 1,
        "runtime": {
            "mode": "auto",
            "parallelism": 1,
            "budget": {"max_steps": 32, "max_parallelism": 1},
        },
        "persistence": {"brief_path": "./CONCEPT_BRIEF.md"},
        "features": {
            "research": False,
            "workers": False,
            "council": False,
            "evaluator": False,
        },
        "evaluation": {"max_rounds": 2},
    }


class ConfigLoaderTests(unittest.TestCase):
    def test_bundled_zero_dependency_yaml_is_valid_strict_config(self):
        config = load_config(EXAMPLE_CONFIG)
        self.assertEqual(config_to_dict(config), valid_config_dict())
        self.assertFalse(config.features.research)
        self.assertFalse(config.features.workers)
        self.assertFalse(config.features.council)
        self.assertFalse(config.features.evaluator)

    def test_unknown_missing_or_wrong_typed_fields_are_rejected(self):
        value = valid_config_dict()
        value["secret"] = "must-not-be-accepted"
        with self.assertRaises(ConfigError):
            config_from_dict(value)

        value = valid_config_dict()
        del value["features"]["research"]
        with self.assertRaises(ConfigError):
            config_from_dict(value)

        value = valid_config_dict()
        value["features"]["research"] = 1
        with self.assertRaises(ConfigError):
            config_from_dict(value)

    def test_schema_parallelism_council_and_evaluator_invariants(self):
        value = valid_config_dict()
        value["schema_version"] = 2
        with self.assertRaises(ConfigError):
            config_from_dict(value)

        value = valid_config_dict()
        value["runtime"]["parallelism"] = 2
        with self.assertRaises(ConfigError):
            config_from_dict(value)

        value = valid_config_dict()
        value["features"]["council"] = True
        with self.assertRaises(ConfigError):
            config_from_dict(value)

        value = valid_config_dict()
        value["evaluation"]["max_rounds"] = 3
        with self.assertRaises(ConfigError):
            config_from_dict(value)


class FullCycleRunnerTests(unittest.TestCase):
    def temp_path(self, name: str) -> Path:
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-{name}"
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_plain_text_runs_p0_p1_p2_to_legal_needs_input(self):
        config = config_from_dict(valid_config_dict())
        brief_path = self.temp_path("CONCEPT_BRIEF.md")
        summary = FullCycleRunner(config).run(
            {
                "request_id": "run-fv01-unit",
                "text": "Shape a reversible onboarding idea.",
                "routing": {"ambiguous_concept": True},
            },
            brief_path=brief_path,
        )
        self.assertEqual(summary.run_id, "run-fv01-unit")
        self.assertEqual(summary.mode, "Shape")
        self.assertEqual(summary.exit_status, "NEEDS_INPUT")
        self.assertEqual(
            summary.stage_history, ["ROUTE", "CONTEXT", "FRAME", "STOPPED"]
        )
        self.assertTrue(brief_path.is_file())
        restored = p2.load_brief(brief_path)
        self.assertEqual(restored.runtime_state.result.exit_status.value, "NEEDS_INPUT")
        self.assertEqual(restored.next_action, summary.next_action)

    def test_config_mode_overrides_automatic_routing(self):
        value = valid_config_dict()
        value["runtime"]["mode"] = "Stress"
        config = config_from_dict(value)
        summary = FullCycleRunner(config).run(
            {"text": "Generate a quick idea.", "routing": {"low_risk": True}},
            brief_path=self.temp_path("brief.md"),
        )
        self.assertEqual(summary.mode, "Stress")

    def test_request_cannot_override_config_or_canonical_state(self):
        config = config_from_dict(valid_config_dict())
        runner = FullCycleRunner(config)
        with self.assertRaises(RequestError):
            runner.run(
                {
                    "text": "idea",
                    "routing": {"budget": {"max_steps": 1000}},
                },
                brief_path=self.temp_path("a.md"),
            )
        with self.assertRaises(RequestError):
            runner.run(
                {"text": "idea", "core": {"state": {}}},
                brief_path=self.temp_path("b.md"),
            )

    def test_request_envelope_is_strict(self):
        with self.assertRaises(RequestError):
            request_from_dict({"text": "idea", "unexpected": True})
        with self.assertRaises(RequestError):
            request_from_dict({"text": ""})
        with self.assertRaises(RequestError):
            request_from_dict({"text": "idea", "routing": []})


if __name__ == "__main__":
    unittest.main()
