"""Thinking-token budget optimizer (Phase 8B practical fallback).

Analyzes historical budget logs to learn per-task-type thinking token
limits.  Provides calibrated thinking budgets that reduce waste on
simple tasks while preserving quality on complex ones.

Integrates with Phase 7A's RuleBasedController and BudgetLogger.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .token_budget_controller import (
    TokenBudgetState,
    TokenBudgetAction,
    TurnOutcome,
    MIN_THINKING_TOKENS,
    THINKING_CEIL,
    _clamp_action,
    complexity_str_to_float,
)
from .exceptions import setup_logger

logger = setup_logger(__name__)

# ── task type definitions ──────────────────────────────────────────────

TASK_TYPES = ("trivial", "simple", "moderate", "complex")

# default thinking budgets when no historical data exists
_DEFAULT_BUDGETS: Dict[str, int] = {
    "trivial": 256,   # typo fix, simple rename
    "simple": 1024,   # single-file edit, config change
    "moderate": 4096,  # multi-file feature, refactor
    "complex": 16000,  # architecture change, debugging
}

# floor / ceiling per task type (safety bounds)
_TASK_BOUNDS: Dict[str, Tuple[int, int]] = {
    "trivial": (MIN_THINKING_TOKENS, 1024),
    "simple": (MIN_THINKING_TOKENS, 4096),
    "moderate": (1024, 16000),
    "complex": (2048, THINKING_CEIL),
}

# ── dataclasses ────────────────────────────────────────────────────────

@dataclass
class TaskTypeStats:
    """Aggregate stats for a single task type from historical data."""
    task_type: str
    total_turns: int = 0
    successful_turns: int = 0
    failed_turns: int = 0
    avg_thinking_tokens: float = 0.0
    avg_thinking_on_success: float = 0.0
    avg_thinking_on_failure: float = 0.0
    p50_thinking: int = 0
    p90_thinking: int = 0
    recommended_budget: int = 0
    confidence: float = 0.0 # 0-1, based on sample size

@dataclass
class ThinkingBudgetProfile:
    """Complete profile of recommended thinking budgets."""
    budgets: Dict[str, int] = field(default_factory=lambda: dict(_DEFAULT_BUDGETS))
    stats: Dict[str, TaskTypeStats] = field(default_factory=dict)
    total_records_analyzed: int = 0
    estimated_savings_pct: float = 0.0

# ── complexity float -> task type mapper ───────────────────────────────

def _complexity_to_type(c: float) -> str:
    if c <= 0.2: return "trivial"
    if c <= 0.4: return "simple"
    if c <= 0.7: return "moderate"
    return "complex"

def _type_to_complexity(t: str) -> float:
    return {"trivial": 0.1, "simple": 0.3, "moderate": 0.6, "complex": 0.9}.get(t, 0.5)

# ── percentile helper ──────────────────────────────────────────────────

def _percentile(sorted_vals: List[int], pct: float) -> int:
    if not sorted_vals: return 0
    idx = int(math.ceil(pct / 100.0 * len(sorted_vals))) - 1
    return sorted_vals[max(0, min(idx, len(sorted_vals) - 1))]

# ── core optimizer ─────────────────────────────────────────────────────

class ThinkingBudgetOptimizer:
    """Learns optimal thinking token budgets from historical data.

    Strategy:
      1. Group historical turns by task complexity
      2. For successful turns, compute p50/p90 of thinking tokens used
      3. Set budget = p90 of successful turns (enough for most tasks)
      4. Clamp to task-type safety bounds
      5. If failure rate is high, bump budget toward ceiling
    """

    def __init__(self, log_dir: Optional[Path] = None):
        self._log_dir = log_dir or Path(".poor-cli")
        self._log_file = self._log_dir / "budget_logs.jsonl"
        self._profile: Optional[ThinkingBudgetProfile] = None

    def analyze(self) -> ThinkingBudgetProfile:
        """Analyze historical logs and produce calibrated budgets."""
        records = self._read_logs()
        if not records:
            logger.info("thinking_budget: no historical data, using defaults")
            return ThinkingBudgetProfile()
        by_type: Dict[str, List[dict]] = defaultdict(list)
        for r in records:
            c = r.get("state", {}).get("task_complexity", 0.5)
            task_type = _complexity_to_type(c)
            by_type[task_type].append(r)
        profile = ThinkingBudgetProfile(total_records_analyzed=len(records))
        baseline_tokens = 0
        optimized_tokens = 0
        for task_type in TASK_TYPES:
            turns = by_type.get(task_type, [])
            stats = self._compute_stats(task_type, turns)
            profile.stats[task_type] = stats
            profile.budgets[task_type] = stats.recommended_budget
            # estimate savings vs a flat 10000-token budget
            baseline_tokens += stats.total_turns * 10000
            optimized_tokens += stats.total_turns * stats.recommended_budget
        if baseline_tokens > 0:
            profile.estimated_savings_pct = round(
                (1.0 - optimized_tokens / baseline_tokens) * 100, 1
            )
        self._profile = profile
        return profile

    def get_budget(self, complexity: float, economy_mode: str = "balanced") -> int:
        """Get recommended thinking budget for a task complexity.

        Args:
            complexity: 0.0-1.0 task complexity score
            economy_mode: frugal | balanced | quality
        Returns:
            thinking token budget (clamped to safety bounds)
        """
        if self._profile is None:
            self.analyze()
        task_type = _complexity_to_type(complexity)
        base = (self._profile.budgets if self._profile else _DEFAULT_BUDGETS).get(
            task_type, _DEFAULT_BUDGETS[task_type]
        )
        # economy mode scaling
        if economy_mode == "frugal":
            base = int(base * 0.6)
        elif economy_mode == "quality":
            base = int(base * 1.5)
        lo, hi = _TASK_BOUNDS[task_type]
        return max(lo, min(hi, base))

    def get_budget_for_prompt(self, prompt: str, economy_mode: str = "balanced") -> int:
        """Estimate thinking budget from prompt text (lightweight classifier)."""
        complexity = self._estimate_complexity(prompt)
        return self.get_budget(complexity, economy_mode)

    def suggest_action_override(
        self, state: TokenBudgetState, action: TokenBudgetAction
    ) -> TokenBudgetAction:
        """Override the controller's thinking budget with calibrated value.

        Replaces the rule-based thinking budget with data-driven budget
        while preserving all other action fields.
        """
        calibrated = self.get_budget(state.task_complexity, state.economy_mode)
        action.max_thinking_tokens = calibrated
        return _clamp_action(action)

    # ── internal ───────────────────────────────────────────────────────

    def _read_logs(self) -> List[dict]:
        if not self._log_file.exists():
            return []
        records = []
        try:
            with self._log_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        except OSError:
            pass
        return records

    def _compute_stats(self, task_type: str, turns: List[dict]) -> TaskTypeStats:
        stats = TaskTypeStats(task_type=task_type, total_turns=len(turns))
        if not turns:
            stats.recommended_budget = _DEFAULT_BUDGETS[task_type]
            return stats
        success_thinking: List[int] = []
        failure_thinking: List[int] = []
        all_thinking: List[int] = []
        for t in turns:
            thinking = t.get("action", {}).get("max_thinking_tokens", 0)
            succeeded = t.get("outcome", {}).get("task_succeeded", True)
            all_thinking.append(thinking)
            if succeeded:
                success_thinking.append(thinking)
                stats.successful_turns += 1
            else:
                failure_thinking.append(thinking)
                stats.failed_turns += 1
        all_thinking.sort()
        success_thinking.sort()
        failure_thinking.sort()
        stats.avg_thinking_tokens = round(sum(all_thinking) / len(all_thinking), 1)
        if success_thinking:
            stats.avg_thinking_on_success = round(sum(success_thinking) / len(success_thinking), 1)
        if failure_thinking:
            stats.avg_thinking_on_failure = round(sum(failure_thinking) / len(failure_thinking), 1)
        stats.p50_thinking = _percentile(all_thinking, 50)
        stats.p90_thinking = _percentile(all_thinking, 90)
        # confidence: higher with more samples (sigmoid-like)
        stats.confidence = round(min(1.0, len(turns) / 50.0), 2)
        # recommended budget: p90 of successful turns (covers 90% of successes)
        if success_thinking:
            budget = _percentile(success_thinking, 90)
        else:
            budget = _DEFAULT_BUDGETS[task_type]
        # if failure rate > 30% and failures used low budgets, bump up
        failure_rate = stats.failed_turns / max(stats.total_turns, 1)
        if failure_rate > 0.3 and failure_thinking:
            avg_fail = sum(failure_thinking) / len(failure_thinking)
            if avg_fail < budget:
                budget = int(budget * 1.3) # bump 30% on high failure rate
        # blend with defaults based on confidence
        default = _DEFAULT_BUDGETS[task_type]
        budget = int(stats.confidence * budget + (1 - stats.confidence) * default)
        lo, hi = _TASK_BOUNDS[task_type]
        stats.recommended_budget = max(lo, min(hi, budget))
        return stats

    @staticmethod
    def _estimate_complexity(prompt: str) -> float:
        """Lightweight prompt complexity estimator (no LLM call).

        Heuristic based on prompt length, keyword signals, and structure.
        """
        words = prompt.split()
        n = len(words)
        prompt_lower = prompt.lower()
        # trivial signals
        trivial_kw = ("typo", "rename", "fix whitespace", "add comma", "remove space")
        if any(k in prompt_lower for k in trivial_kw):
            return 0.1
        # simple signals
        simple_kw = ("change", "update", "modify", "set", "toggle", "add import")
        if n < 20 and any(k in prompt_lower for k in simple_kw):
            return 0.3
        # complex signals
        complex_kw = ("refactor", "architect", "redesign", "migrate", "debug",
                      "investigate", "why does", "root cause", "performance")
        if any(k in prompt_lower for k in complex_kw):
            return 0.85
        # moderate by default, scaled by length
        if n < 15: return 0.3
        if n < 50: return 0.5
        if n < 150: return 0.65
        return 0.75

    def to_dict(self) -> Dict[str, Any]:
        """Serialize current profile for reporting."""
        if self._profile is None:
            self.analyze()
        p = self._profile or ThinkingBudgetProfile()
        return {
            "budgets": p.budgets,
            "total_records": p.total_records_analyzed,
            "estimated_savings_pct": p.estimated_savings_pct,
            "stats": {k: asdict(v) for k, v in p.stats.items()},
        }
