"""FV-00 registrations for the eight full-version acceptance criteria.

These tests deliberately verify executable registration only. A criterion must
remain ``SCAFFOLDED`` until its owning FV module replaces the registration test
with end-to-end behavioral assertions and changes the manifest status to
``IMPLEMENTED``. Consequently, passing this file cannot be interpreted as the
criterion itself passing.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
MANIFEST_PATH = PROJECT_ROOT / "acceptance" / "manifest.json"


class AcceptanceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        cls.criteria = {item["id"]: item for item in cls.manifest["criteria"]}

    def assert_contract_registered(
        self,
        criterion_id: str,
        module: str,
        *,
        status: str = "SCAFFOLDED",
        test_suffix: str | None = None,
    ) -> None:
        criterion = self.criteria[criterion_id]
        self.assertEqual(criterion["implementation_module"], module)
        self.assertEqual(criterion["status"], status)
        if test_suffix is None:
            self.assertTrue(
                criterion["test_id"].startswith(
                    "tests.acceptance.test_ac_contracts."
                ),
                criterion["test_id"],
            )
            test_suffix = f".AcceptanceContractTests.{self._testMethodName}"
        self.assertTrue(criterion["test_id"].endswith(test_suffix))
        self.assertTrue(criterion["fixtures"])
        self.assertTrue(criterion["expected_states"])
        self.assertTrue(criterion["expected_artifacts"])

    def test_ac_01_contract_registered(self):
        self.assert_contract_registered(
            "AC-01",
            "FV-01",
            status="IMPLEMENTED",
            test_suffix=(
                ".OneCommandAcceptanceTests."
                "test_ac_01_single_command_reaches_legal_stop"
            ),
        )

    def test_ac_02_contract_registered(self):
        self.assert_contract_registered(
            "AC-02",
            "FV-02",
            status="IMPLEMENTED",
            test_suffix=(
                ".ResumeMatrixAcceptanceTests."
                "test_ac_02_every_stage_resumes_to_equivalent_main_state"
            ),
        )

    def test_ac_03_contract_registered(self):
        self.assert_contract_registered(
            "AC-03",
            "FV-04",
            status="IMPLEMENTED",
            test_suffix=(
                ".ResearchWorkerIsolationAcceptanceTests."
                "test_ac_03_research_and_worker_failures_do_not_pollute_main_state"
            ),
        )

    def test_ac_04_contract_registered(self):
        self.assert_contract_registered(
            "AC-04",
            "FV-06",
            status="IMPLEMENTED",
            test_suffix=(
                ".EvaluatorCapAcceptanceTests."
                "test_ac_04_evaluator_calls_never_exceed_two_across_resume"
            ),
        )

    def test_ac_05_contract_registered(self):
        self.assert_contract_registered(
            "AC-05",
            "FV-03",
            status="IMPLEMENTED",
            test_suffix=(
                ".BudgetParkMatrixAcceptanceTests."
                "test_ac_05_every_stage_parks_before_work"
            ),
        )

    def test_ac_06_contract_registered(self):
        self.assert_contract_registered(
            "AC-06",
            "FV-05",
            status="IMPLEMENTED",
            test_suffix=(
                ".TraceUsageAcceptanceTests."
                "test_ac_06_automatic_activation_and_real_usage_cost_trace"
            ),
        )

    def test_ac_07_contract_registered(self):
        self.assert_contract_registered(
            "AC-07",
            "FV-07",
            status="IMPLEMENTED",
            test_suffix=(
                ".VersionUpgradeAcceptanceTests."
                "test_ac_07_version_changes_require_non_mocked_live_regression"
            ),
        )

    def test_ac_08_contract_registered(self):
        self.assert_contract_registered(
            "AC-08",
            "FV-06",
            status="IMPLEMENTED",
            test_suffix=(
                ".ArtifactGateAcceptanceTests."
                "test_ac_08_only_current_hash_matched_approved_artifact_can_handoff"
            ),
        )


if __name__ == "__main__":
    unittest.main()
