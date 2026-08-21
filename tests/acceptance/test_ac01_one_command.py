from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).parents[2]
CLI = PROJECT_ROOT / "scripts" / "brainstorm.py"
CONFIG = PROJECT_ROOT / "config" / "brainstorm-governor.example.yaml"
REQUEST = PROJECT_ROOT / "tests" / "acceptance" / "fixtures" / "ac01_one_command.json"
LEGAL_STOPS = {
    "EXPLORE",
    "RESEARCH_REQUIRED",
    "ITERATE",
    "COMMIT",
    "PARK",
    "NEEDS_INPUT",
}


class OneCommandAcceptanceTests(unittest.TestCase):
    def temp_path(self, name: str) -> Path:
        path = Path(tempfile.gettempdir()) / f"brainstorm-{uuid.uuid4().hex}-{name}"
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_ac_01_single_command_reaches_legal_stop(self):
        brief = self.temp_path("CONCEPT_BRIEF.md")
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "run",
                "--request",
                str(REQUEST),
                "--config",
                str(CONFIG),
                "--brief",
                str(brief),
            ],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        summary = json.loads(completed.stdout)
        self.assertEqual(
            set(summary),
            {
                "run_id",
                "mode",
                "exit_status",
                "brief_path",
                "next_action",
                "resumed",
                "reentry_conflicts",
                "stage_history",
            },
        )
        self.assertIn(summary["exit_status"], LEGAL_STOPS)
        self.assertEqual(summary["run_id"], "run-ac01-one-command")
        self.assertEqual(Path(summary["brief_path"]), brief.resolve())
        self.assertTrue(brief.is_file())
        self.assertNotIn("implementation", completed.stdout.casefold())

    def test_request_can_be_supplied_through_stdin(self):
        request_text = REQUEST.read_text(encoding="utf-8")
        brief = self.temp_path("stdin-brief.md")
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "run",
                "--config",
                str(CONFIG),
                "--brief",
                str(brief),
            ],
            cwd=PROJECT_ROOT,
            input=request_text,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
        self.assertIn(json.loads(completed.stdout)["exit_status"], LEGAL_STOPS)

    def test_contract_error_returns_nonzero_machine_readable_error(self):
        completed = subprocess.run(
            [
                sys.executable,
                str(CLI),
                "run",
                "--config",
                str(CONFIG),
            ],
            cwd=PROJECT_ROOT,
            input='{"text":"idea","unknown":true}',
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(completed.returncode, 2)
        payload = json.loads(completed.stdout)
        self.assertFalse(payload["valid"])
        self.assertTrue(payload["error"])


if __name__ == "__main__":
    unittest.main()
