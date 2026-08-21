from __future__ import annotations

import unittest

from scripts.agent_smoke import run_agent_smoke, validate_smoke_report


class AgentFunctionalityTests(unittest.TestCase):
    def test_checked_in_agent_runs_and_resumes_with_release_gates(self):
        report = run_agent_smoke()
        validate_smoke_report(report)

        self.assertEqual(report["result"], "PASS")
        self.assertTrue(all(report["checks"].values()))
        self.assertEqual(report["runtime"]["exit_status"], "NEEDS_INPUT")
        self.assertEqual(report["runtime"]["resumed_exit_status"], "NEEDS_INPUT")
        self.assertFalse(report["boundaries"]["external_provider_used"])


if __name__ == "__main__":
    unittest.main()
