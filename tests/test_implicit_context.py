"""tests for poor_cli.context.ContextManager implicit tracking."""

import unittest
from poor_cli.context import ContextManager


class TestImplicitContextTracking(unittest.TestCase):
    def _make_cm(self):
        return ContextManager()

    def test_record_access_boost_positive(self):
        cm = self._make_cm()
        cm.record_access("/tmp/foo.py")
        self.assertGreater(cm.implicit_priority_boost("/tmp/foo.py"), 0)

    def test_advance_turn_increments(self):
        cm = self._make_cm()
        self.assertEqual(cm._current_turn, 0)
        cm.advance_turn()
        self.assertEqual(cm._current_turn, 1)

    def test_boost_decays_with_distance(self):
        cm = self._make_cm()
        cm.record_access("/tmp/decay.py")
        initial = cm.implicit_priority_boost("/tmp/decay.py")
        for _ in range(5):
            cm.advance_turn()
        later = cm.implicit_priority_boost("/tmp/decay.py")
        self.assertLess(later, initial)

    def test_entries_pruned_after_20_turns(self):
        cm = self._make_cm()
        cm.record_access("/tmp/old.py")
        for _ in range(21):
            cm.advance_turn()
        self.assertEqual(cm.implicit_priority_boost("/tmp/old.py"), 0)

    def test_unknown_file_returns_zero(self):
        cm = self._make_cm()
        self.assertEqual(cm.implicit_priority_boost("/nonexistent"), 0)

    def test_multiple_accesses_increase_boost(self):
        cm = self._make_cm()
        cm.record_access("/tmp/multi.py")
        single = cm.implicit_priority_boost("/tmp/multi.py")
        cm.record_access("/tmp/multi.py")
        cm.record_access("/tmp/multi.py")
        triple = cm.implicit_priority_boost("/tmp/multi.py")
        self.assertGreater(triple, single)


if __name__ == "__main__":
    unittest.main()
