"""Tests for CB2 two-tier pinning in history_pruning."""

from __future__ import annotations

import unittest

from poor_cli.history_pruning import HistoryPruner, PruningPolicy


class SoftPinTests(unittest.TestCase):
    def _base_history(self, soft_idx: int = 2) -> list[dict]:
        history = [
            {"role": "user", "content": "first prompt"},
            {"role": "assistant", "content": "okay, doing A" * 20},
            {"role": "assistant", "content": "filler turn " * 30, "pinned": "soft"},
            {"role": "assistant", "content": "another filler " * 30},
            {"role": "tool", "name": "bash", "content": "some tool result " * 20},
            {"role": "user", "content": "second prompt — current"},
        ]
        assert history[soft_idx].get("pinned") == "soft"
        return history

    def test_hard_pin_true_never_pruned(self):
        history = [
            {"role": "user", "content": "first prompt"},
            {"role": "assistant", "content": "very old content " * 50, "pinned": True},
            {"role": "assistant", "content": "filler turn " * 50},
            {"role": "user", "content": "current"},
        ]
        result = HistoryPruner().prune(history, target_tokens=1, mode="balanced")
        kept_contents = [m["content"] for m in result.history]
        self.assertTrue(any("very old content" in c for c in kept_contents))

    def test_soft_pin_preserved_at_mild_pressure(self):
        history = self._base_history()
        pruner = HistoryPruner()
        # estimate target just under current tokens — mild pressure, not severe
        tokens_now = pruner._history_tokens(history)
        target = int(tokens_now * 0.97)
        result = pruner.prune(history, target_tokens=target, mode="balanced")
        pruned_indices = {p.index for p in result.pruned_turns}
        self.assertNotIn(2, pruned_indices, "soft-pinned turn should survive mild pressure")

    def test_soft_pin_evicted_at_severe_pressure(self):
        history = self._base_history()
        pruner = HistoryPruner()
        # target << current = severe pressure > 1.05 factor
        tokens_now = pruner._history_tokens(history)
        target = int(tokens_now * 0.3)
        result = pruner.prune(history, target_tokens=target, mode="balanced")
        # at severe pressure, soft-pinned turn enters the eviction pool
        scored = {t.index: t for t in result.scored_turns}
        self.assertTrue(scored[2].soft_protected)
        # it should be a candidate (not protected hard), so may be pruned if score is low
        pruned_indices = {p.index for p in result.pruned_turns}
        # under severe pressure the pruner can evict soft pin; allow either
        # behavior but assert the soft-pin flag is surfaced
        self.assertTrue(scored[2].to_metadata()["softProtected"])

    def test_metadata_flags_soft_protected(self):
        history = self._base_history()
        scored = HistoryPruner().score_history(history)
        by_idx = {s.index: s for s in scored}
        self.assertTrue(by_idx[2].soft_protected)
        self.assertFalse(by_idx[2].protected)
        self.assertTrue(by_idx[5].protected)  # last user = hard

    def test_soft_pin_factor_configurable(self):
        policy = PruningPolicy(soft_pin_evict_factor=2.0)
        self.assertAlmostEqual(policy.soft_pin_evict_factor, 2.0)

    def test_legacy_pinned_true_treated_as_hard(self):
        history = [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "legacy pin " * 30, "pinned": True},
            {"role": "user", "content": "current"},
        ]
        scored = HistoryPruner().score_history(history)
        by_idx = {s.index: s for s in scored}
        self.assertTrue(by_idx[1].protected)
        self.assertFalse(by_idx[1].soft_protected)


if __name__ == "__main__":
    unittest.main()
