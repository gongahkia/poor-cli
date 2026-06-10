"""Tests for CB4 AdaptiveBudgetController moving-avg adaptation."""

from __future__ import annotations

import unittest

from poor_cli.adaptive_budget import (
    MIN_SAMPLES_FOR_TREND,
    AdaptiveBudgetController,
)
from poor_cli.token_budget_controller import (
    RuleBasedController,
    TokenBudgetState,
    TurnOutcome,
)


def _state(**kw) -> TokenBudgetState:
    return TokenBudgetState(**kw)


class AdaptiveBudgetTests(unittest.TestCase):
    def test_disabled_defers_to_inner(self):
        inner = RuleBasedController()
        ctrl = AdaptiveBudgetController(inner, enabled=False)
        state = _state(task_complexity=0.5, economy_mode="balanced")
        ctrl._rewards.extend([-1.0, -1.0, -1.0, -1.0, -1.0])
        action = ctrl.decide(state)
        inner_action = inner.decide(state)
        self.assertEqual(action.max_thinking_tokens, inner_action.max_thinking_tokens)
        self.assertEqual(ctrl.stats.last_adjustment, "none")

    def test_small_sample_no_adjustment(self):
        ctrl = AdaptiveBudgetController()
        state = _state(task_complexity=0.5, economy_mode="balanced")
        ctrl._rewards.extend([0.1, -0.1])
        action = ctrl.decide(state)
        self.assertEqual(ctrl.stats.last_adjustment, "none")
        self.assertEqual(action.max_thinking_tokens, ctrl.inner.decide(state).max_thinking_tokens)

    def test_negative_trend_bumps_thinking(self):
        ctrl = AdaptiveBudgetController()
        # early rewards good, recent rewards bad → negative trend
        for r in [0.8, 0.7, 0.6, 0.5, -0.5, -0.8, -0.9, -1.0]:
            ctrl._rewards.append(r)
        state = _state(task_complexity=0.5, economy_mode="balanced")
        baseline = ctrl.inner.decide(state)
        action = ctrl.decide(state)
        self.assertGreater(action.max_thinking_tokens, baseline.max_thinking_tokens)
        self.assertEqual(ctrl.stats.last_adjustment, "bump")

    def test_positive_trend_relaxes_thinking(self):
        ctrl = AdaptiveBudgetController()
        # early bad, recent good → positive trend
        for r in [-0.8, -0.7, -0.6, -0.5, 0.5, 0.7, 0.8, 0.9]:
            ctrl._rewards.append(r)
        state = _state(task_complexity=0.5, economy_mode="balanced")
        baseline = ctrl.inner.decide(state)
        action = ctrl.decide(state)
        self.assertLess(action.max_thinking_tokens, baseline.max_thinking_tokens)
        self.assertEqual(ctrl.stats.last_adjustment, "relax")

    def test_neutral_trend_no_change(self):
        ctrl = AdaptiveBudgetController()
        for r in [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]:
            ctrl._rewards.append(r)
        state = _state(task_complexity=0.5, economy_mode="balanced")
        baseline = ctrl.inner.decide(state)
        action = ctrl.decide(state)
        self.assertEqual(action.max_thinking_tokens, baseline.max_thinking_tokens)
        self.assertEqual(ctrl.stats.last_adjustment, "none")

    def test_observe_appends_reward(self):
        ctrl = AdaptiveBudgetController()
        state = _state()
        action = ctrl.decide(state)
        before = len(ctrl._rewards)
        ctrl.observe(state, action, TurnOutcome(task_succeeded=True))
        self.assertEqual(len(ctrl._rewards), before + 1)

    def test_window_caps_buffer_size(self):
        ctrl = AdaptiveBudgetController(window=5)
        state = _state()
        action = ctrl.decide(state)
        for _ in range(20):
            ctrl.observe(state, action, TurnOutcome(task_succeeded=True))
        self.assertEqual(len(ctrl._rewards), 5)

    def test_adjustments_counted_in_stats(self):
        ctrl = AdaptiveBudgetController()
        for r in [0.8, 0.7, 0.6, -0.5, -0.8, -0.9]:
            ctrl._rewards.append(r)
        ctrl.decide(_state(task_complexity=0.5, economy_mode="balanced"))
        ctrl.decide(_state(task_complexity=0.5, economy_mode="balanced"))
        self.assertGreaterEqual(ctrl.stats.adjustments_made, 1)

    def test_stats_to_dict_keys(self):
        ctrl = AdaptiveBudgetController()
        ctrl._rewards.extend([0.1] * MIN_SAMPLES_FOR_TREND)
        ctrl.decide(_state())
        d = ctrl.stats.to_dict()
        for key in ("windowSize", "avgRewardRecent", "avgRewardEarly", "trend", "lastAdjustment", "adjustmentsMade"):
            self.assertIn(key, d)


if __name__ == "__main__":
    unittest.main()
