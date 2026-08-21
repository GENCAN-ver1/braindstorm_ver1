from __future__ import annotations

import json
import unittest
import uuid
from pathlib import Path

from acceptance.full_version import (
    run_full_version_acceptance,
    save_full_report,
    validate_full_report,
)


PROJECT_ROOT = Path(__file__).parents[2]
CLEANROOM = PROJECT_ROOT / "tests/acceptance/cleanroom"


class FullVersionAcceptanceTests(unittest.TestCase):
    def test_fv_08_all_acceptance_evidence_passes_in_clean_room(self):
        prefix = f".fv08-report-{uuid.uuid4().hex}"
        report_json = CLEANROOM / f"{prefix}.json"
        report_md = CLEANROOM / f"{prefix}.md"
        self.addCleanup(report_json.unlink, missing_ok=True)
        self.addCleanup(report_md.unlink, missing_ok=True)

        report = run_full_version_acceptance()
        validate_full_report(report)
        save_full_report(report, report_json, report_md)

        self.assertEqual(report["status"], "FULL_VERSION")
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(len(report["criteria"]), 8)
        self.assertTrue(all(item["result"] == "PASS" for item in report["criteria"]))
        self.assertTrue(all(report["gates"].values()))
        self.assertEqual(report["xfail_xpass_count"], 0)
        self.assertEqual(
            json.loads(report_json.read_text(encoding="utf-8"))["status"],
            "FULL_VERSION",
        )
        self.assertTrue(report_md.is_file())


if __name__ == "__main__":
    unittest.main()
