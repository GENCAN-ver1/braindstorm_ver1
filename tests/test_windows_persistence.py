import unittest
from unittest.mock import patch

from runtime.governor_modules import p2


class WindowsPersistenceTests(unittest.TestCase):
    def test_transient_windows_lock_retries(self):
        error = PermissionError('locked')
        error.winerror = 32
        with patch.object(p2.os, 'replace', side_effect=[error, error, None]) as replace:
            with patch.object(p2.time, 'sleep') as sleep:
                p2._replace_with_retry('source', 'target')
        self.assertEqual(replace.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_persistent_or_unrelated_permission_failure_is_not_hidden(self):
        for winerror, expected_calls in ((5, 6), (None, 1)):
            error = PermissionError('denied')
            error.winerror = winerror
            with patch.object(p2.os, 'replace', side_effect=error) as replace:
                with patch.object(p2.time, 'sleep'):
                    with self.assertRaises(PermissionError):
                        p2._replace_with_retry('source', 'target')
            self.assertEqual(replace.call_count, expected_calls)
