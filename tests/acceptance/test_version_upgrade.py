from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path

from ci.regression_gate import OfflineContractResult, evaluate_release_gate
from evals.version_fingerprint import compute_version_fingerprint


PROJECT_ROOT = Path(__file__).parents[2]
INPUTS = PROJECT_ROOT / "evals/version-inputs.json"
BASELINE = PROJECT_ROOT / "evals/baseline-manifest.json"
FIXTURE = PROJECT_ROOT / "tests/acceptance/fixtures/ac07_version_upgrade.json"


class VersionUpgradeAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.prefix = f".fv07-ac-{uuid.uuid4().hex}"
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.original = json.loads(INPUTS.read_text(encoding="utf-8"))
        self.offline = OfflineContractResult(True, 0, "0" * 64, 108)

    def path(self, name):
        path = PROJECT_ROOT / "tests" / "acceptance" / f"{self.prefix}-{name}"
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def write_json(self, name, value):
        path = self.path(name)
        path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        return path

    def changed_inputs(self, dimension):
        value = json.loads(json.dumps(self.original))
        if dimension == "governor_prompt":
            prompt = self.path("governor-prompt.md")
            prompt.write_text("changed governor prompt", encoding="utf-8")
            value["governor_prompt_paths"] = [
                prompt.relative_to(PROJECT_ROOT).as_posix()
            ]
        elif dimension == "evaluator_prompt":
            prompt = self.path("evaluator-prompt.md")
            prompt.write_text("changed evaluator prompt", encoding="utf-8")
            value["evaluator_prompt_paths"] = [
                prompt.relative_to(PROJECT_ROOT).as_posix()
            ]
        elif dimension == "provider":
            value["model"]["provider"] = "changed-provider"
        elif dimension == "model":
            value["model"]["model_id"] = "changed-model"
        elif dimension == "adapter":
            value["provider_adapter"]["version"] = "changed-adapter"
        elif dimension == "schema":
            value["output_schema"]["version"] = "changed-schema"
        elif dimension == "pricing":
            pricing = json.loads(
                (PROJECT_ROOT / "config/provider-pricing.json").read_text(
                    encoding="utf-8"
                )
            )
            pricing["version"] = "changed-pricing"
            pricing_path = self.write_json("pricing.json", pricing)
            value["pricing_table_path"] = pricing_path.relative_to(
                PROJECT_ROOT
            ).as_posix()
        else:
            raise AssertionError(dimension)
        return self.write_json(f"inputs-{dimension}.json", value)

    def test_ac_07_version_changes_require_non_mocked_live_regression(self):
        triggered = []
        for dimension in self.fixture["changed_dimensions"]:
            with self.subTest(dimension=dimension):
                inputs_path = self.changed_inputs(dimension)
                current = compute_version_fingerprint(
                    inputs_path, project_root=PROJECT_ROOT
                )
                result = evaluate_release_gate(
                    version_inputs_path=inputs_path,
                    baseline_path=BASELINE,
                    offline_result=self.offline,
                )
                self.assertEqual(result["result"], "BLOCK")
                self.assertTrue(result["live_regression_required"])
                self.assertIn(dimension, result["changed_dimensions"])
                self.assertEqual(
                    result["current_fingerprint"]["aggregate"], current.aggregate
                )
                triggered.append(dimension)
        self.assertEqual(triggered, self.fixture["changed_dimensions"])


if __name__ == "__main__":
    unittest.main()
