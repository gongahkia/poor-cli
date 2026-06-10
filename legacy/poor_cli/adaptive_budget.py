"""CB4 per-session reward moving-average budget adaptation.

Wraps the rule-based ``RuleBasedController`` with a session-local trend
detector. Tracks the last N turn rewards; when the trend is negative (tasks
getting worse) bump thinking budget and relax compression slightly, when the
trend is positive pull them back in.

This is intentionally NOT a Thompson-sampling bandit — that was evaluated and
rejected as too heavy for the cost-conscious hobbyist audience. Moving-average
adaptation is cheap, bounded, and explainable.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional

from .exceptions import setup_logger
from .token_budget_controller import (
    MIN_OUTPUT_TOKENS,
    MIN_THINKING_TOKENS,
    MAX_COMPRESSION_RATIO,
    MAX_OUTPUT_TOKENS,
    THINKING_CEIL,
    RuleBasedController,
    TokenBudgetAction,
    TokenBudgetState,
    TurnOutcome,
    compute_reward,
)

logger = setup_logger(__name__)

DEFAULT_WINDOW = 10                # number of recent turns to look at
MIN_SAMPLES_FOR_TREND = 4          # need at least this many rewards to act
NEGATIVE_TREND_THRESHOLD = -0.1    # trend delta that triggers bump
POSITIVE_TREND_THRESHOLD = 0.1     # trend delta that triggers relax
THINKING_BUMP_FACTOR = 1.10        # +10% thinking when trend negative
THINKING_RELAX_FACTOR = 0.95       # -5% thinking when trend positive
COMPRESSION_STEP = 0.05            # compression relax/tighten per trend


@dataclass
class AdaptationStats:
    window_size: int = 0
    avg_reward_recent: float = 0.0
    avg_reward_early: float = 0.0
    trend: float = 0.0
    last_adjustment: str = "none"   # "bump" | "relax" | "none"
    adjustments_made: int = 0

    def to_dict(self) -> dict:
        return {
            "windowSize": self.window_size,
            "avgRewardRecent": round(self.avg_reward_recent, 4),
            "avgRewardEarly": round(self.avg_reward_early, 4),
            "trend": round(self.trend, 4),
            "lastAdjustment": self.last_adjustment,
            "adjustmentsMade": self.adjustments_made,
        }


class AdaptiveBudgetController:
    """Composes with RuleBasedController; applies trend-based adjustments."""

    def __init__(
        self,
        inner: Optional[RuleBasedController] = None,
        *,
        window: int = DEFAULT_WINDOW,
        enabled: bool = True,
    ):
        self._inner = inner or RuleBasedController()
        self._rewards: Deque[float] = deque(maxlen=window)
        self._complexities: Deque[float] = deque(maxlen=window)
        self._successes: Deque[bool] = deque(maxlen=window)
        self._window = window
        self._enabled = enabled
        self._stats = AdaptationStats(window_size=window)

    @property
    def inner(self) -> RuleBasedController:
        return self._inner

    @property
    def stats(self) -> AdaptationStats:
        return self._stats

    def set_enabled(self, flag: bool) -> None:
        self._enabled = bool(flag)

    def decide(self, state: TokenBudgetState) -> TokenBudgetAction:
        """Run the rule-based controller then apply trend-based adjustments."""
        action = self._inner.decide(state)
        if not self._enabled:
            self._stats.last_adjustment = "none"
            return action
        trend = self._compute_trend()
        self._stats.trend = trend
        if len(self._rewards) < MIN_SAMPLES_FOR_TREND:
            self._stats.last_adjustment = "none"
            return action
        if trend <= NEGATIVE_TREND_THRESHOLD:
            action = self._bump(action)
            self._stats.last_adjustment = "bump"
            self._stats.adjustments_made += 1
        elif trend >= POSITIVE_TREND_THRESHOLD:
            action = self._relax(action)
            self._stats.last_adjustment = "relax"
            self._stats.adjustments_made += 1
        else:
            self._stats.last_adjustment = "none"
        return action

    def observe(self, state: TokenBudgetState, action: TokenBudgetAction, outcome: TurnOutcome) -> float:
        reward = compute_reward(state, action, outcome)
        self._rewards.append(reward)
        self._complexities.append(float(getattr(state, "task_complexity", 0.5) or 0.5))
        self._successes.append(bool(getattr(outcome, "task_succeeded", False)))
        self._stats.window_size = len(self._rewards)
        return reward

    def recent_complexity_estimate(self) -> float:
        if not self._complexities:
            return 0.5
        return sum(self._complexities) / len(self._complexities)

    def recent_success_rate(self, window: int = DEFAULT_WINDOW) -> float:
        if not self._successes:
            return 0.0
        recent = list(self._successes)[-max(1, int(window or 1)):]
        return sum(1 for item in recent if item) / len(recent)

    # ── internals ────────────────────────────────────────────────────────

    def _compute_trend(self) -> float:
        """Return (recent_half_avg - early_half_avg). Empty window → 0."""
        n = len(self._rewards)
        if n < 2:
            return 0.0
        half = n // 2
        early = list(self._rewards)[:half]
        recent = list(self._rewards)[-half:]
        if not early or not recent:
            return 0.0
        avg_early = sum(early) / len(early)
        avg_recent = sum(recent) / len(recent)
        self._stats.avg_reward_early = avg_early
        self._stats.avg_reward_recent = avg_recent
        return avg_recent - avg_early

    def _bump(self, action: TokenBudgetAction) -> TokenBudgetAction:
        """Trend negative → bump thinking, relax compression."""
        action.max_thinking_tokens = min(
            THINKING_CEIL,
            max(MIN_THINKING_TOKENS, int(action.max_thinking_tokens * THINKING_BUMP_FACTOR)),
        )
        action.compression_ratio = max(0.0, min(MAX_COMPRESSION_RATIO, action.compression_ratio - COMPRESSION_STEP))
        action.max_output_tokens = min(MAX_OUTPUT_TOKENS, max(MIN_OUTPUT_TOKENS, action.max_output_tokens))
        return action

    def _relax(self, action: TokenBudgetAction) -> TokenBudgetAction:
        """Trend positive → tighten thinking, tighten compression."""
        action.max_thinking_tokens = min(
            THINKING_CEIL,
            max(MIN_THINKING_TOKENS, int(action.max_thinking_tokens * THINKING_RELAX_FACTOR)),
        )
        action.compression_ratio = max(0.0, min(MAX_COMPRESSION_RATIO, action.compression_ratio + COMPRESSION_STEP))
        action.max_output_tokens = min(MAX_OUTPUT_TOKENS, max(MIN_OUTPUT_TOKENS, action.max_output_tokens))
        return action
