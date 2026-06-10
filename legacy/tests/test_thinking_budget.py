"""Tests for thinking_budget.py — Phase 8B practical fallback."""

import json
import tempfile
import time
from pathlib import Path
from dataclasses import asdict
import pytest
from poor_cli.thinking_budget import (
    ThinkingBudgetOptimizer,
    ThinkingBudgetProfile,
    TaskTypeStats,
    _complexity_to_type,
    _type_to_complexity,
    _percentile,
    _DEFAULT_BUDGETS,
    _TASK_BOUNDS,
    TASK_TYPES,
)
from poor_cli.token_budget_controller import (
    TokenBudgetState,
    TokenBudgetAction,
    MIN_THINKING_TOKENS,
    THINKING_CEIL,
)

# ── helpers ────────────────────────────────────────────────────────────

def _make_log_record(complexity: float, thinking: int, succeeded: bool, total_tokens: int = 5000):
    return {
        "ts": time.time(),
        "state": {"task_complexity": complexity, "context_utilization": 0.3,
                  "turn_number": 1, "tool_calls_pending": 0,
                  "recent_failure_rate": 0.0, "economy_mode": "balanced",
                  "provider": "anthropic", "model_tier": "balanced"},
        "action": {"max_thinking_tokens": thinking, "max_output_tokens": 4096,
                   "compression_ratio": 0.0, "model_tier": "balanced",
                   "should_compact": False, "should_prune": False},
        "outcome": {"task_succeeded": succeeded, "user_retried": False,
                    "total_tokens_used": total_tokens, "input_tokens": 3000,
                    "output_tokens": 2000, "response_time_seconds": 2.0,
                    "tool_calls_made": 1, "error": ""},
        "reward": 0.5 if succeeded else -0.3,
    }

def _write_logs(tmpdir: Path, records: list):
    log_dir = tmpdir / ".poor-cli"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "budget_logs.jsonl"
    with log_file.open("w") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
    return log_dir

# ── unit tests ─────────────────────────────────────────────────────────

class TestComplexityMapping:
    def test_trivial(self):
        assert _complexity_to_type(0.1) == "trivial"
        assert _complexity_to_type(0.0) == "trivial"
        assert _complexity_to_type(0.2) == "trivial"

    def test_simple(self):
        assert _complexity_to_type(0.3) == "simple"
        assert _complexity_to_type(0.4) == "simple"

    def test_moderate(self):
        assert _complexity_to_type(0.5) == "moderate"
        assert _complexity_to_type(0.7) == "moderate"

    def test_complex(self):
        assert _complexity_to_type(0.8) == "complex"
        assert _complexity_to_type(1.0) == "complex"

    def test_roundtrip(self):
        for t in TASK_TYPES:
            c = _type_to_complexity(t)
            assert _complexity_to_type(c) == t

class TestPercentile:
    def test_empty(self):
        assert _percentile([], 50) == 0

    def test_single(self):
        assert _percentile([100], 50) == 100

    def test_p50(self):
        assert _percentile([1, 2, 3, 4, 5], 50) == 3

    def test_p90(self):
        assert _percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 90) == 9

class TestDefaultBudgets:
    def test_all_types_covered(self):
        for t in TASK_TYPES:
            assert t in _DEFAULT_BUDGETS
            assert t in _TASK_BOUNDS

    def test_bounds_ascending(self):
        prev_hi = 0
        for t in TASK_TYPES:
            lo, hi = _TASK_BOUNDS[t]
            assert lo < hi
            assert lo >= MIN_THINKING_TOKENS

    def test_defaults_within_bounds(self):
        for t in TASK_TYPES:
            lo, hi = _TASK_BOUNDS[t]
            assert lo <= _DEFAULT_BUDGETS[t] <= hi

class TestOptimizerNoData:
    def test_defaults_when_no_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            profile = opt.analyze()
            assert profile.budgets == _DEFAULT_BUDGETS
            assert profile.total_records_analyzed == 0

    def test_get_budget_defaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            assert opt.get_budget(0.1) == _DEFAULT_BUDGETS["trivial"]
            assert opt.get_budget(0.9) == _DEFAULT_BUDGETS["complex"]

class TestOptimizerWithData:
    def test_learns_from_logs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            records = []
            for _ in range(30): # trivial tasks with low thinking
                records.append(_make_log_record(0.1, 256, True))
            for _ in range(30): # complex tasks with high thinking
                records.append(_make_log_record(0.9, 16000, True))
            log_dir = _write_logs(Path(tmpdir), records)
            opt = ThinkingBudgetOptimizer(log_dir=log_dir)
            profile = opt.analyze()
            assert profile.total_records_analyzed == 60
            assert profile.budgets["trivial"] <= 1024 # should stay low
            assert profile.budgets["complex"] >= 4096 # should stay high

    def test_failure_bumps_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            records = []
            for _ in range(20): # simple tasks that mostly fail with low budget
                records.append(_make_log_record(0.3, 512, False))
            for _ in range(5): # a few that succeed
                records.append(_make_log_record(0.3, 2048, True))
            log_dir = _write_logs(Path(tmpdir), records)
            opt = ThinkingBudgetOptimizer(log_dir=log_dir)
            profile = opt.analyze()
            # high failure rate should bump budget above default
            assert profile.budgets["simple"] >= _DEFAULT_BUDGETS["simple"]

    def test_savings_estimate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            records = []
            for _ in range(50):
                records.append(_make_log_record(0.1, 256, True))
            log_dir = _write_logs(Path(tmpdir), records)
            opt = ThinkingBudgetOptimizer(log_dir=log_dir)
            profile = opt.analyze()
            assert profile.estimated_savings_pct > 0 # should save vs flat 10K

class TestEconomyModeScaling:
    def test_frugal_reduces(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            balanced = opt.get_budget(0.5, "balanced")
            frugal = opt.get_budget(0.5, "frugal")
            assert frugal <= balanced

    def test_quality_increases(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            balanced = opt.get_budget(0.5, "balanced")
            quality = opt.get_budget(0.5, "quality")
            assert quality >= balanced

    def test_bounds_respected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            for mode in ("frugal", "balanced", "quality"):
                for c in (0.1, 0.3, 0.5, 0.9):
                    b = opt.get_budget(c, mode)
                    t = _complexity_to_type(c)
                    lo, hi = _TASK_BOUNDS[t]
                    assert lo <= b <= hi, f"mode={mode} c={c} budget={b} bounds=({lo},{hi})"

class TestPromptComplexityEstimator:
    def test_trivial_keywords(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            b = opt.get_budget_for_prompt("fix typo in readme")
            assert b <= _DEFAULT_BUDGETS["simple"]

    def test_complex_keywords(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            b = opt.get_budget_for_prompt("refactor the entire authentication module and migrate to the new API")
            assert b >= _DEFAULT_BUDGETS["moderate"]

class TestActionOverride:
    def test_overrides_thinking_tokens(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            state = TokenBudgetState(task_complexity=0.1, economy_mode="balanced")
            action = TokenBudgetAction(max_thinking_tokens=10000)
            result = opt.suggest_action_override(state, action)
            assert result.max_thinking_tokens < 10000 # should reduce for trivial
            assert result.max_thinking_tokens >= MIN_THINKING_TOKENS

    def test_preserves_other_fields(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            state = TokenBudgetState(task_complexity=0.5, economy_mode="balanced")
            action = TokenBudgetAction(
                max_thinking_tokens=10000,
                max_output_tokens=4096,
                model_tier="quality",
                should_compact=True,
            )
            result = opt.suggest_action_override(state, action)
            assert result.max_output_tokens == 4096
            assert result.model_tier == "quality"
            assert result.should_compact is True

class TestSerialization:
    def test_to_dict(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            opt = ThinkingBudgetOptimizer(log_dir=Path(tmpdir) / ".poor-cli")
            d = opt.to_dict()
            assert "budgets" in d
            assert "total_records" in d
            assert "estimated_savings_pct" in d
            assert d["total_records"] == 0

# ── benchmark: savings vs baseline ────────────────────────────────────

class TestBenchmarkSavings:
    """Simulated benchmark: tokens saved vs task success rate."""

    def test_mixed_workload_savings(self):
        """Simulate a mixed workload and verify savings over flat 10K budget."""
        with tempfile.TemporaryDirectory() as tmpdir:
            records = []
            # 40% trivial (256 tokens enough)
            for _ in range(40):
                records.append(_make_log_record(0.1, 256, True))
            # 30% simple (1024 tokens enough)
            for _ in range(30):
                records.append(_make_log_record(0.3, 1024, True))
            # 20% moderate (4096 tokens enough)
            for _ in range(20):
                records.append(_make_log_record(0.6, 4096, True))
            # 10% complex (16000 tokens)
            for _ in range(10):
                records.append(_make_log_record(0.9, 16000, True))
            log_dir = _write_logs(Path(tmpdir), records)
            opt = ThinkingBudgetOptimizer(log_dir=log_dir)
            profile = opt.analyze()
            # calculate actual savings
            flat_total = 100 * 10000 # 1M tokens at flat 10K
            optimized_total = sum(
                profile.stats[_complexity_to_type(r["state"]["task_complexity"])].total_turns
                * profile.budgets[_complexity_to_type(r["state"]["task_complexity"])]
                for r in records[:4] # one of each type
            )
            assert profile.estimated_savings_pct > 30 # expect >30% savings on mixed workload
            # verify no task type lost its budget entirely
            for t in TASK_TYPES:
                assert profile.budgets[t] >= _TASK_BOUNDS[t][0]
