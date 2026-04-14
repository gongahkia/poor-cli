"""Tests for CB3 ToolSuccessTracker + adaptive pruning integration."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from poor_cli.history_pruning import HistoryPruner, PruningPolicy
from poor_cli.tool_success_tracker import (
    CACHE_FILENAME,
    ToolStats,
    ToolSuccessTracker,
)


class ToolStatsTests(unittest.TestCase):
    def test_rate_returns_none_with_no_samples(self):
        self.assertIsNone(ToolStats().rate())

    def test_rate_returns_fraction(self):
        self.assertAlmostEqual(ToolStats(success=3, failure=1).rate(), 0.75)

    def test_to_from_dict_roundtrip(self):
        src = ToolStats(success=5, failure=2, last_updated="2026-04-14")
        restored = ToolStats.from_dict(src.to_dict())
        self.assertEqual(restored, src)


class ToolSuccessTrackerTests(unittest.TestCase):
    def test_record_increments_counters(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            tracker.record("bash", True)
            tracker.record("bash", True)
            tracker.record("bash", False)
            self.assertAlmostEqual(tracker.rate_for("bash"), 2 / 3)

    def test_rate_for_unknown_tool_is_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            self.assertIsNone(tracker.rate_for("never-seen"))

    def test_multiplier_neutral_before_min_samples(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            for _ in range(3):
                tracker.record("new_tool", True)
            self.assertEqual(tracker.tool_weight_multiplier("new_tool", min_samples=5), 1.0)

    def test_multiplier_amplifies_reliable_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            for _ in range(10):
                tracker.record("reliable", True)
            mult = tracker.tool_weight_multiplier("reliable", min_samples=5)
            self.assertGreater(mult, 1.0)

    def test_multiplier_penalizes_flaky_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            for _ in range(10):
                tracker.record("flaky", False)
            mult = tracker.tool_weight_multiplier("flaky", min_samples=5)
            self.assertLess(mult, 1.0)

    def test_persist_and_reload(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            tracker.record("bash", True)
            tracker.record("bash", True)
            tracker.persist()
            self.assertTrue((Path(tmp) / CACHE_FILENAME).exists())

            tracker2 = ToolSuccessTracker(Path(tmp))
            tracker2.load()
            self.assertAlmostEqual(tracker2.rate_for("bash"), 1.0)

    def test_empty_tool_name_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            tracker.record("", True)
            self.assertIsNone(tracker.rate_for(""))


class AdaptivePruningIntegrationTests(unittest.TestCase):
    def test_adaptive_scoring_respects_policy_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            tracker = ToolSuccessTracker(Path(tmp))
            for _ in range(10):
                tracker.record("bash", True)

            history = [
                {"role": "user", "content": "read auth.py"},
                {"role": "tool", "name": "bash", "content": "ok"},
                {"role": "user", "content": "current prompt"},
            ]
            pruner = HistoryPruner(tool_success_tracker=tracker)

            # adaptive OFF → default scoring path
            off = pruner.score_history(history, policy=PruningPolicy(adaptive_tool_scoring=False))
            # adaptive ON → reliable tool gets amplified tool component
            on = pruner.score_history(history, policy=PruningPolicy(adaptive_tool_scoring=True))

            tool_turn_off = next(t for t in off if t.index == 1)
            tool_turn_on = next(t for t in on if t.index == 1)
            self.assertGreater(tool_turn_on.components["tool"], tool_turn_off.components["tool"])

    def test_no_tracker_safely_falls_back(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "tool", "name": "bash", "content": "ok"},
            {"role": "user", "content": "current"},
        ]
        pruner = HistoryPruner(tool_success_tracker=None)
        # adaptive flag True but no tracker — must not crash, falls back to default
        scored = pruner.score_history(history, policy=PruningPolicy(adaptive_tool_scoring=True))
        tool_turn = next(t for t in scored if t.index == 1)
        self.assertEqual(tool_turn.components["tool"], 0.18)


if __name__ == "__main__":
    unittest.main()
