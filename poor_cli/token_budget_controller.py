"""Token budget meta-controller (Phase 7A).

Observes session state and selects token budget actions via a rule-based
decision tree.  Safety constraints are hard limits — the controller cannot
violate them.  In quality mode the controller is advisory only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import setup_logger

logger = setup_logger(__name__)

# ── safety hard limits ──────────────────────────────────────────────────

MIN_THINKING_TOKENS = 256 # provider-agnostic floor
MAX_COMPRESSION_RATIO = 0.9
MIN_OUTPUT_TOKENS = 256
MAX_OUTPUT_TOKENS = 8192
THINKING_CEIL = 32_000

# ── state / action / outcome dataclasses ────────────────────────────────

@dataclass
class TokenBudgetState:
    """What the controller observes before each turn."""
    task_complexity: float = 0.5 # 0-1 from model_router classifier
    context_utilization: float = 0.0 # current_tokens / max_tokens
    turn_number: int = 0
    tool_calls_pending: int = 0 # estimated remaining tool calls
    recent_failure_rate: float = 0.0 # failures in last 5 turns
    economy_mode: str = "balanced" # frugal | balanced | quality
    provider: str = ""
    model_tier: str = "balanced" # cheap | balanced | quality

@dataclass
class TokenBudgetAction:
    """What the controller decides for this turn."""
    max_thinking_tokens: int = 4096
    max_output_tokens: int = 4096
    compression_ratio: float = 0.0 # 0.0 = none, up to 0.9
    model_tier: str = "balanced"
    should_compact: bool = False
    should_prune: bool = False

@dataclass
class TurnOutcome:
    """Post-turn measurements for reward/logging."""
    task_succeeded: bool = True
    user_retried: bool = False
    total_tokens_used: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    response_time_seconds: float = 0.0
    tool_calls_made: int = 0
    error: str = ""

# ── reward computation ──────────────────────────────────────────────────

def compute_reward(state: TokenBudgetState, action: TokenBudgetAction, outcome: TurnOutcome) -> float:
    """Scalar reward signal for offline analysis / future bandit upgrade."""
    reward = 0.0
    reward += -0.001 * outcome.total_tokens_used # cost efficiency
    reward += 1.0 if outcome.task_succeeded else -0.5
    reward += 0.5 if not outcome.user_retried else -0.3
    reward += -0.01 * outcome.response_time_seconds
    return round(reward, 4)

# ── safety clamp ────────────────────────────────────────────────────────

def _clamp_action(action: TokenBudgetAction) -> TokenBudgetAction:
    """Enforce hard safety limits on any action."""
    action.max_thinking_tokens = max(MIN_THINKING_TOKENS, min(THINKING_CEIL, action.max_thinking_tokens))
    action.max_output_tokens = max(MIN_OUTPUT_TOKENS, min(MAX_OUTPUT_TOKENS, action.max_output_tokens))
    action.compression_ratio = max(0.0, min(MAX_COMPRESSION_RATIO, action.compression_ratio))
    return action

# ── complexity mapper ───────────────────────────────────────────────────

_COMPLEXITY_TO_FLOAT = {
    "trivial": 0.1,
    "simple": 0.3,
    "moderate": 0.6,
    "complex": 0.9,
}

def complexity_str_to_float(s: str) -> float:
    return _COMPLEXITY_TO_FLOAT.get(s.lower(), 0.5)

# ── decision tree (rule-based baseline) ─────────────────────────────────

class RuleBasedController:
    """Phase 7A-1: hand-crafted decision tree.

    Split order:
      1. economy_mode (hard override for quality)
      2. context_utilization (high pressure -> compact/compress)
      3. task_complexity (simple -> cheap/small, complex -> expensive/large)
      4. recent_failure_rate (high -> escalate tier, more thinking)
    """

    def __init__(self) -> None:
        self._history: List[Tuple[TokenBudgetState, TokenBudgetAction, Optional[TurnOutcome]]] = []

    def decide(self, state: TokenBudgetState) -> TokenBudgetAction:
        """Select an action given current state.  Returns clamped action."""
        action = self._tree(state)
        action = _clamp_action(action)
        return action

    def observe(self, state: TokenBudgetState, action: TokenBudgetAction, outcome: TurnOutcome) -> float:
        """Record outcome, return reward."""
        reward = compute_reward(state, action, outcome)
        self._history.append((state, action, outcome))
        return reward

    # ── the tree ────────────────────────────────────────────────────────

    def _tree(self, s: TokenBudgetState) -> TokenBudgetAction:
        # quality mode: advisory only — maximize everything
        if s.economy_mode == "quality":
            return TokenBudgetAction(
                max_thinking_tokens=THINKING_CEIL,
                max_output_tokens=MAX_OUTPUT_TOKENS,
                compression_ratio=0.0,
                model_tier="quality",
                should_compact=False,
                should_prune=False,
            )

        # high context pressure branch
        if s.context_utilization > 0.85:
            return self._high_pressure(s)
        if s.context_utilization > 0.65:
            return self._medium_pressure(s)

        # normal pressure — route by complexity
        if s.task_complexity <= 0.2:
            return self._trivial_task(s)
        if s.task_complexity <= 0.4:
            return self._simple_task(s)
        if s.task_complexity <= 0.7:
            return self._moderate_task(s)
        return self._complex_task(s)

    # ── pressure sub-trees ──────────────────────────────────────────────

    def _high_pressure(self, s: TokenBudgetState) -> TokenBudgetAction:
        """Context >85% — aggressive compaction."""
        tier = "cheap" if s.economy_mode == "frugal" else "balanced"
        return TokenBudgetAction(
            max_thinking_tokens=1024,
            max_output_tokens=1024,
            compression_ratio=0.7 if s.economy_mode == "frugal" else 0.5,
            model_tier=tier,
            should_compact=True,
            should_prune=s.turn_number > 15,
        )

    def _medium_pressure(self, s: TokenBudgetState) -> TokenBudgetAction:
        """Context 65-85% — moderate compression."""
        tier = "cheap" if s.economy_mode == "frugal" else "balanced"
        thinking = 2048 if s.task_complexity <= 0.5 else 4096
        return TokenBudgetAction(
            max_thinking_tokens=thinking,
            max_output_tokens=2048,
            compression_ratio=0.4 if s.economy_mode == "frugal" else 0.2,
            model_tier=tier,
            should_compact=s.context_utilization > 0.75,
            should_prune=False,
        )

    # ── complexity sub-trees ────────────────────────────────────────────

    def _trivial_task(self, s: TokenBudgetState) -> TokenBudgetAction:
        tier = "cheap"
        return TokenBudgetAction(
            max_thinking_tokens=512,
            max_output_tokens=1024,
            compression_ratio=0.0,
            model_tier=tier,
            should_compact=False,
            should_prune=False,
        )

    def _simple_task(self, s: TokenBudgetState) -> TokenBudgetAction:
        tier = "cheap" if s.economy_mode == "frugal" else "balanced"
        thinking = 1024 if s.economy_mode == "frugal" else 2048
        # bump on recent failures
        if s.recent_failure_rate > 0.4:
            thinking = min(thinking * 2, THINKING_CEIL)
            tier = "balanced"
        return TokenBudgetAction(
            max_thinking_tokens=thinking,
            max_output_tokens=2048,
            compression_ratio=0.0,
            model_tier=tier,
            should_compact=False,
            should_prune=False,
        )

    def _moderate_task(self, s: TokenBudgetState) -> TokenBudgetAction:
        tier = "balanced"
        thinking = 4096
        if s.economy_mode == "frugal":
            tier = "cheap"
            thinking = 2048
        if s.recent_failure_rate > 0.4:
            thinking = min(thinking * 2, THINKING_CEIL)
            tier = "quality" if tier == "balanced" else "balanced"
        return TokenBudgetAction(
            max_thinking_tokens=thinking,
            max_output_tokens=4096,
            compression_ratio=0.0,
            model_tier=tier,
            should_compact=False,
            should_prune=False,
        )

    def _complex_task(self, s: TokenBudgetState) -> TokenBudgetAction:
        tier = "quality" if s.economy_mode != "frugal" else "balanced"
        thinking = 16_000 if s.economy_mode != "frugal" else 8_000
        if s.recent_failure_rate > 0.4:
            thinking = min(thinking + 8_000, THINKING_CEIL)
        return TokenBudgetAction(
            max_thinking_tokens=thinking,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            compression_ratio=0.0,
            model_tier=tier,
            should_compact=False,
            should_prune=False,
        )

    # ── analytics ───────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        if not self._history:
            return {"total_decisions": 0}
        rewards = [compute_reward(s, a, o) for s, a, o in self._history if o]
        tiers = {}
        for _, a, _ in self._history:
            tiers[a.model_tier] = tiers.get(a.model_tier, 0) + 1
        return {
            "total_decisions": len(self._history),
            "avg_reward": round(sum(rewards) / max(len(rewards), 1), 4) if rewards else 0,
            "tier_distribution": tiers,
        }


# ── convenience: build state from engine context ────────────────────────

def build_state_from_engine(
    *,
    complexity_str: str = "simple",
    context_pressure_pct: float = 0.0,
    turn_number: int = 0,
    tool_calls_pending: int = 0,
    recent_failures: int = 0,
    recent_turns: int = 5,
    economy_preset: str = "balanced",
    provider: str = "",
    model_tier: str = "balanced",
) -> TokenBudgetState:
    """Helper to construct TokenBudgetState from engine-level values."""
    return TokenBudgetState(
        task_complexity=complexity_str_to_float(complexity_str),
        context_utilization=min(1.0, max(0.0, context_pressure_pct / 100.0)),
        turn_number=turn_number,
        tool_calls_pending=tool_calls_pending,
        recent_failure_rate=min(1.0, recent_failures / max(recent_turns, 1)),
        economy_mode=economy_preset,
        provider=provider,
        model_tier=model_tier,
    )
