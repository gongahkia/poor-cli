"""Tests for token budget controller (Phase 7A)."""

import json
import tempfile
from pathlib import Path

import pytest

from poor_cli.token_budget_controller import (
    RuleBasedController,
    TokenBudgetState,
    TokenBudgetAction,
    TurnOutcome,
    build_state_from_engine,
    compute_reward,
    complexity_str_to_float,
    _clamp_action,
    MIN_THINKING_TOKENS,
    MAX_COMPRESSION_RATIO,
    MIN_OUTPUT_TOKENS,
    MAX_OUTPUT_TOKENS,
    THINKING_CEIL,
)
from poor_cli.budget_logger import BudgetLogger


# ── safety clamp tests ──────────────────────────────────────────────────

class TestSafetyClamp:
    def test_clamp_thinking_floor(self):
        a = TokenBudgetAction(max_thinking_tokens=0)
        a = _clamp_action(a)
        assert a.max_thinking_tokens == MIN_THINKING_TOKENS

    def test_clamp_thinking_ceil(self):
        a = TokenBudgetAction(max_thinking_tokens=999_999)
        a = _clamp_action(a)
        assert a.max_thinking_tokens == THINKING_CEIL

    def test_clamp_output_floor(self):
        a = TokenBudgetAction(max_output_tokens=10)
        a = _clamp_action(a)
        assert a.max_output_tokens == MIN_OUTPUT_TOKENS

    def test_clamp_output_ceil(self):
        a = TokenBudgetAction(max_output_tokens=99_999)
        a = _clamp_action(a)
        assert a.max_output_tokens == MAX_OUTPUT_TOKENS

    def test_clamp_compression_floor(self):
        a = TokenBudgetAction(compression_ratio=-0.5)
        a = _clamp_action(a)
        assert a.compression_ratio == 0.0

    def test_clamp_compression_ceil(self):
        a = TokenBudgetAction(compression_ratio=0.99)
        a = _clamp_action(a)
        assert a.compression_ratio == MAX_COMPRESSION_RATIO

    def test_valid_action_unchanged(self):
        a = TokenBudgetAction(
            max_thinking_tokens=4096,
            max_output_tokens=4096,
            compression_ratio=0.3,
        )
        a = _clamp_action(a)
        assert a.max_thinking_tokens == 4096
        assert a.max_output_tokens == 4096
        assert a.compression_ratio == 0.3


# ── complexity mapper ───────────────────────────────────────────────────

class TestComplexityMapper:
    def test_known_levels(self):
        assert complexity_str_to_float("trivial") == 0.1
        assert complexity_str_to_float("simple") == 0.3
        assert complexity_str_to_float("moderate") == 0.6
        assert complexity_str_to_float("complex") == 0.9

    def test_unknown_default(self):
        assert complexity_str_to_float("alien") == 0.5

    def test_case_insensitive(self):
        assert complexity_str_to_float("TRIVIAL") == 0.1


# ── decision tree logic ─────────────────────────────────────────────────

class TestDecisionTree:
    def setup_method(self):
        self.ctrl = RuleBasedController()

    def test_quality_mode_maximizes(self):
        s = TokenBudgetState(economy_mode="quality")
        a = self.ctrl.decide(s)
        assert a.max_thinking_tokens == THINKING_CEIL
        assert a.max_output_tokens == MAX_OUTPUT_TOKENS
        assert a.compression_ratio == 0.0
        assert a.model_tier == "quality"

    def test_trivial_task_uses_cheap(self):
        s = TokenBudgetState(task_complexity=0.1, economy_mode="frugal")
        a = self.ctrl.decide(s)
        assert a.model_tier == "cheap"
        assert a.max_thinking_tokens <= 1024

    def test_complex_task_uses_quality_tier(self):
        s = TokenBudgetState(task_complexity=0.9, economy_mode="balanced")
        a = self.ctrl.decide(s)
        assert a.model_tier == "quality"
        assert a.max_thinking_tokens >= 8000

    def test_high_pressure_triggers_compact(self):
        s = TokenBudgetState(context_utilization=0.9, economy_mode="balanced")
        a = self.ctrl.decide(s)
        assert a.should_compact is True
        assert a.compression_ratio > 0

    def test_medium_pressure_moderate_compress(self):
        s = TokenBudgetState(context_utilization=0.7, economy_mode="frugal")
        a = self.ctrl.decide(s)
        assert a.compression_ratio > 0

    def test_frugal_complex_downgrades_tier(self):
        s = TokenBudgetState(task_complexity=0.9, economy_mode="frugal")
        a = self.ctrl.decide(s)
        assert a.model_tier == "balanced" # not quality

    def test_failure_rate_escalates(self):
        s = TokenBudgetState(
            task_complexity=0.3,
            recent_failure_rate=0.6,
            economy_mode="balanced",
        )
        a = self.ctrl.decide(s)
        # should have bumped thinking and/or tier
        assert a.max_thinking_tokens >= 2048 or a.model_tier == "balanced"

    def test_high_pressure_prunes_deep_sessions(self):
        s = TokenBudgetState(
            context_utilization=0.9,
            turn_number=20,
            economy_mode="balanced",
        )
        a = self.ctrl.decide(s)
        assert a.should_prune is True

    def test_all_actions_clamped(self):
        """Every decision should pass safety clamp."""
        states = [
            TokenBudgetState(economy_mode="quality"),
            TokenBudgetState(economy_mode="frugal", task_complexity=0.1),
            TokenBudgetState(economy_mode="balanced", context_utilization=0.95),
            TokenBudgetState(task_complexity=0.9, recent_failure_rate=0.8),
        ]
        for s in states:
            a = self.ctrl.decide(s)
            assert a.max_thinking_tokens >= MIN_THINKING_TOKENS
            assert a.max_thinking_tokens <= THINKING_CEIL
            assert a.max_output_tokens >= MIN_OUTPUT_TOKENS
            assert a.max_output_tokens <= MAX_OUTPUT_TOKENS
            assert 0.0 <= a.compression_ratio <= MAX_COMPRESSION_RATIO


# ── reward computation ──────────────────────────────────────────────────

class TestReward:
    def test_success_positive(self):
        s = TokenBudgetState()
        a = TokenBudgetAction()
        o = TurnOutcome(task_succeeded=True, total_tokens_used=100, response_time_seconds=1.0)
        r = compute_reward(s, a, o)
        assert r > 0

    def test_failure_negative(self):
        s = TokenBudgetState()
        a = TokenBudgetAction()
        o = TurnOutcome(task_succeeded=False, total_tokens_used=5000, response_time_seconds=10.0)
        r = compute_reward(s, a, o)
        assert r < 0

    def test_retry_penalized(self):
        s = TokenBudgetState()
        a = TokenBudgetAction()
        o1 = TurnOutcome(task_succeeded=True, user_retried=False, total_tokens_used=100)
        o2 = TurnOutcome(task_succeeded=True, user_retried=True, total_tokens_used=100)
        assert compute_reward(s, a, o1) > compute_reward(s, a, o2)


# ── build_state_from_engine helper ──────────────────────────────────────

class TestBuildState:
    def test_basic(self):
        s = build_state_from_engine(
            complexity_str="moderate",
            context_pressure_pct=55.0,
            turn_number=3,
            economy_preset="frugal",
        )
        assert s.task_complexity == 0.6
        assert abs(s.context_utilization - 0.55) < 0.01
        assert s.turn_number == 3
        assert s.economy_mode == "frugal"

    def test_clamps_utilization(self):
        s = build_state_from_engine(context_pressure_pct=150.0)
        assert s.context_utilization == 1.0
        s2 = build_state_from_engine(context_pressure_pct=-10.0)
        assert s2.context_utilization == 0.0


# ── budget logger ───────────────────────────────────────────────────────

class TestBudgetLogger:
    def test_log_and_flush(self, tmp_path):
        logger = BudgetLogger(base_dir=tmp_path)
        s = TokenBudgetState()
        a = TokenBudgetAction()
        o = TurnOutcome(task_succeeded=True, total_tokens_used=500)
        logger.log(s, a, o)
        logger.flush()
        records = logger.read_all()
        assert len(records) == 1
        assert records[0]["outcome"]["total_tokens_used"] == 500
        assert "reward" in records[0]

    def test_auto_flush_on_threshold(self, tmp_path):
        logger = BudgetLogger(base_dir=tmp_path)
        logger._flush_every = 3
        s = TokenBudgetState()
        a = TokenBudgetAction()
        o = TurnOutcome(task_succeeded=True)
        for _ in range(3):
            logger.log(s, a, o)
        # should have auto-flushed
        assert len(logger._buffer) == 0
        assert len(logger.read_all()) == 3

    def test_summary_empty(self, tmp_path):
        logger = BudgetLogger(base_dir=tmp_path)
        s = logger.summary()
        assert s["total_records"] == 0

    def test_summary_with_data(self, tmp_path):
        logger = BudgetLogger(base_dir=tmp_path)
        s = TokenBudgetState()
        a = TokenBudgetAction(model_tier="cheap")
        o = TurnOutcome(task_succeeded=True, total_tokens_used=1000)
        logger.log(s, a, o)
        logger.flush()
        summary = logger.summary()
        assert summary["total_records"] == 1
        assert summary["success_rate"] == 1.0
        assert summary["tokens_per_success"] == 1000
        assert "cheap" in summary["tier_distribution"]

    def test_close_flushes(self, tmp_path):
        logger = BudgetLogger(base_dir=tmp_path)
        s = TokenBudgetState()
        a = TokenBudgetAction()
        o = TurnOutcome()
        logger.log(s, a, o)
        assert len(logger._buffer) == 1
        logger.close()
        assert len(logger._buffer) == 0
        assert len(logger.read_all()) == 1


# ── simulated sessions: controller learns cheaper models for simple tasks ─

class TestSimulatedSessions:
    def test_simple_tasks_use_cheap_models(self):
        """Simulate 100 simple-task sessions — controller should consistently pick cheap."""
        ctrl = RuleBasedController()
        cheap_count = 0
        for i in range(100):
            s = TokenBudgetState(
                task_complexity=0.2,
                context_utilization=0.2,
                turn_number=i % 10,
                economy_mode="balanced",
            )
            a = ctrl.decide(s)
            if a.model_tier == "cheap":
                cheap_count += 1
        assert cheap_count >= 90, f"expected >=90 cheap, got {cheap_count}"

    def test_complex_tasks_use_expensive_models(self):
        """Simulate 100 complex-task sessions — controller should pick quality/balanced."""
        ctrl = RuleBasedController()
        quality_count = 0
        for i in range(100):
            s = TokenBudgetState(
                task_complexity=0.9,
                context_utilization=0.3,
                turn_number=i % 10,
                economy_mode="balanced",
            )
            a = ctrl.decide(s)
            if a.model_tier in ("quality", "balanced"):
                quality_count += 1
        assert quality_count == 100

    def test_tokens_per_task_metric(self, tmp_path):
        """Compare tokens/task with and without controller across 50 sessions."""
        ctrl = RuleBasedController()
        logger = BudgetLogger(base_dir=tmp_path)
        # with controller: simple tasks get smaller budgets
        controlled_tokens = 0
        for i in range(50):
            complexity = 0.2 if i % 2 == 0 else 0.8
            s = TokenBudgetState(
                task_complexity=complexity,
                economy_mode="balanced",
            )
            a = ctrl.decide(s)
            simulated_usage = a.max_thinking_tokens + a.max_output_tokens
            o = TurnOutcome(
                task_succeeded=True,
                total_tokens_used=simulated_usage,
            )
            ctrl.observe(s, a, o)
            logger.log(s, a, o)
            controlled_tokens += simulated_usage
        logger.flush()
        # baseline: always use max budgets
        baseline_tokens = 50 * (THINKING_CEIL + MAX_OUTPUT_TOKENS)
        # controller should use significantly less than baseline
        assert controlled_tokens < baseline_tokens * 0.5, (
            f"controller ({controlled_tokens}) should use <50% of baseline ({baseline_tokens})"
        )
        # verify log file written
        summary = logger.summary()
        assert summary["total_records"] == 50
        assert summary["success_rate"] == 1.0


# ── economy mode override tests ─────────────────────────────────────────

class TestEconomyOverrides:
    def test_quality_mode_advisory_only(self):
        """In quality mode, controller never compresses or downgrades."""
        ctrl = RuleBasedController()
        s = TokenBudgetState(
            task_complexity=0.1, # trivial
            context_utilization=0.9, # high pressure
            economy_mode="quality",
        )
        a = ctrl.decide(s)
        assert a.model_tier == "quality"
        assert a.compression_ratio == 0.0
        assert a.should_compact is False

    def test_frugal_biases_cheap(self):
        """Frugal mode should bias toward cheaper tiers."""
        ctrl = RuleBasedController()
        for complexity in [0.1, 0.3, 0.5]:
            s = TokenBudgetState(
                task_complexity=complexity,
                economy_mode="frugal",
            )
            a = ctrl.decide(s)
            assert a.model_tier == "cheap", f"frugal+complexity={complexity} should be cheap"
