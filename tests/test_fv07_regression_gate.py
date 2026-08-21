from __future__ import annotations

import copy
import json
import unittest
import uuid
from pathlib import Path

from ci.regression_gate import (
    OfflineContractResult,
    evaluate_release_gate,
    run_offline_contract_regression,
)
from evals.baseline import BaselineError, approve_baseline, load_baseline
from evals.live_runner import load_live_report
from evals.version_fingerprint import (
    changed_dimensions,
    compute_version_fingerprint,
)


PROJECT_ROOT = Path(__file__).parents[1]
INPUTS = PROJECT_ROOT / "evals/version-inputs.json"
BASELINE = PROJECT_ROOT / "evals/baseline-manifest.json"
LIVE_REPORT = PROJECT_ROOT / "evals/live-report.json"


class Fv07Mixin:
    def setUp(self):
        self.prefix = f".fv07-{uuid.uuid4().hex}"

    def path(self, name):
        path = PROJECT_ROOT / "tests" / f"{self.prefix}-{name}"
        self.addCleanup(path.unlink, missing_ok=True)
        self.addCleanup(
            path.with_name(f".{path.name}.tmp").unlink, missing_ok=True
        )
        return path

    def inputs(self):
        return json.loads(INPUTS.read_text(encoding="utf-8"))

    def write_inputs(self, value, name="inputs.json"):
        path = self.path(name)
        path.write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def offline_pass(self):
        return OfflineContractResult(True, 0, "0" * 64, 108)


class VersionFingerprintTests(Fv07Mixin, unittest.TestCase):
    def test_fingerprint_is_stable_and_covers_all_dimensions(self):
        first = compute_version_fingerprint(INPUTS, project_root=PROJECT_ROOT)
        second = compute_version_fingerprint(INPUTS, project_root=PROJECT_ROOT)
        self.assertEqual(first, second)
        self.assertEqual(
            set(first.dimensions),
            {
                "governor_prompt",
                "evaluator_prompt",
                "provider",
                "model",
                "adapter",
                "citation_checker",
                "schema",
                "pricing",
            },
        )

    def test_offline_contract_regression_is_real_and_complete(self):
        result = run_offline_contract_regression()
        self.assertTrue(result.passed)
        self.assertEqual(result.test_count, 108)


class BaselineGateTests(Fv07Mixin, unittest.TestCase):
    def test_unchanged_fingerprint_reuses_hash_verified_baseline(self):
        result = evaluate_release_gate(
            version_inputs_path=INPUTS,
            baseline_path=BASELINE,
            offline_result=self.offline_pass(),
        )
        self.assertEqual(result["result"], "ALLOW")
        self.assertFalse(result["live_regression_required"])
        self.assertTrue(result["live_report_accepted"])

    def test_baseline_update_requires_explicit_approval_and_passing_report(self):
        output = self.path("baseline.json")
        with self.assertRaises(BaselineError):
            approve_baseline(
                LIVE_REPORT,
                output,
                approval_id="approval",
                reviewer="reviewer",
                explicitly_approved=False,
                project_root=PROJECT_ROOT,
            )
        failed = load_live_report(LIVE_REPORT)
        failed["result"] = "FAIL"
        failed_path = self.path("failed-report.json")
        failed_path.write_text(json.dumps(failed), encoding="utf-8")
        with self.assertRaises(BaselineError):
            approve_baseline(
                failed_path,
                output,
                approval_id="approval",
                reviewer="reviewer",
                explicitly_approved=True,
                project_root=PROJECT_ROOT,
            )

    def test_mock_only_or_threshold_failed_report_blocks_release(self):
        changed = self.inputs()
        changed["model"]["model_id"] = "changed-model"
        changed_path = self.write_inputs(changed)
        current = compute_version_fingerprint(changed_path, project_root=PROJECT_ROOT)

        mock_report = load_live_report(LIVE_REPORT)
        mock_report["version_fingerprint"] = current.to_dict()
        mock_report["mocked"] = True
        mock_path = self.path("mock-report.json")
        mock_path.write_text(json.dumps(mock_report), encoding="utf-8")
        mocked = evaluate_release_gate(
            version_inputs_path=changed_path,
            baseline_path=BASELINE,
            live_report_path=mock_path,
            offline_result=self.offline_pass(),
        )
        self.assertEqual(mocked["result"], "BLOCK")
        self.assertFalse(mocked["live_report_accepted"])

        failed_report = copy.deepcopy(mock_report)
        failed_report["mocked"] = False
        failed_report["result"] = "FAIL"
        failed_report["threshold_results"]["passed"] = False
        failed_report["threshold_results"]["checks"]["constraint_adherence"] = False
        failed_path = self.path("threshold-report.json")
        failed_path.write_text(json.dumps(failed_report), encoding="utf-8")
        failed = evaluate_release_gate(
            version_inputs_path=changed_path,
            baseline_path=BASELINE,
            live_report_path=failed_path,
            offline_result=self.offline_pass(),
        )
        self.assertEqual(failed["result"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
