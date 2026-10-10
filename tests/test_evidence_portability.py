import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from acceptance.full_version import _atomic_write
from evals.live_runner import save_live_report
from evals.baseline import save_baseline
from ci.regression_gate import save_gate_report


class EvidencePortabilityTests(unittest.TestCase):
    def test_evidence_writers_use_canonical_lf_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            _atomic_write(path, 'first\nsecond\n')
            self.assertEqual(path.read_bytes(), b'first\nsecond\n')
            with patch('evals.live_runner.validate_live_report'), patch('evals.baseline.validate_baseline'):
                for save in (save_live_report, save_baseline, save_gate_report):
                    save(path, {'result': 'PASS'})
                    self.assertNotIn(b'\r\n', path.read_bytes())
