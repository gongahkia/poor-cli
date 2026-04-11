"""Tests for the model routing engine."""

import pytest
from poor_cli.model_router import (
    TaskComplexity,
    ClassifierContext,
    ModelRouter,
    RouterConfig,
    RoutingDecision,
    classify_complexity,
    detect_low_confidence,
    _build_default_routing_table,
    _get_next_tier_model,
)


# ── classifier tests ─────────────────────────────────────────────────

class TestClassifyComplexity:
    def test_trivial_short(self):
        assert classify_complexity("hi") == TaskComplexity.TRIVIAL

    def test_trivial_typo_fix(self):
        assert classify_complexity("fix typo in readme") == TaskComplexity.TRIVIAL

    def test_trivial_what_is(self):
        assert classify_complexity("what does this function do") == TaskComplexity.TRIVIAL

    def test_trivial_rename(self):
        assert classify_complexity("rename foo") == TaskComplexity.TRIVIAL

    def test_simple_question(self):
        assert classify_complexity("how do I add a new route to the app") == TaskComplexity.TRIVIAL

    def test_simple_single_file(self):
        assert classify_complexity("update the title in config.py") == TaskComplexity.SIMPLE

    def test_moderate_multi_file(self):
        result = classify_complexity("edit config.py and utils.py to add validation")
        assert result in (TaskComplexity.MODERATE, TaskComplexity.COMPLEX)

    def test_moderate_tool_keywords(self):
        result = classify_complexity("create a test file and run the build")
        assert result in (TaskComplexity.MODERATE, TaskComplexity.COMPLEX)

    def test_moderate_refactor(self):
        assert classify_complexity("refactor the auth module") == TaskComplexity.MODERATE

    def test_complex_redesign(self):
        assert classify_complexity("redesign the database schema for users") == TaskComplexity.COMPLEX

    def test_moderate_architect(self):
        assert classify_complexity("architect a new caching layer") == TaskComplexity.MODERATE

    def test_complex_long_prompt(self):
        assert classify_complexity("x " * 1500) == TaskComplexity.COMPLEX

    def test_complex_multiple_verbs(self):
        assert classify_complexity("implement and integrate the new API") == TaskComplexity.COMPLEX

    def test_context_deep_conversation(self):
        ctx = ClassifierContext(conversation_depth=15, tool_calls_so_far=10)
        result = classify_complexity("now edit the file and run tests", ctx)
        assert result == TaskComplexity.COMPLEX

    def test_context_many_files(self):
        ctx = ClassifierContext(files_in_context=5)
        result = classify_complexity("edit the handler to use the new file format", ctx)
        assert result in (TaskComplexity.MODERATE, TaskComplexity.COMPLEX)


# ── routing table tests ──────────────────────────────────────────────

class TestRoutingTable:
    def test_build_gemini_table(self):
        table = _build_default_routing_table("gemini")
        assert table[TaskComplexity.TRIVIAL] == "gemini-2.5-flash-lite"
        assert table[TaskComplexity.COMPLEX] == "gemini-2.5-pro"

    def test_build_anthropic_table(self):
        table = _build_default_routing_table("anthropic")
        assert table[TaskComplexity.TRIVIAL] == "claude-3-5-haiku-20241022"
        assert table[TaskComplexity.COMPLEX] in ("claude-sonnet-4-20250514", "claude-3-7-sonnet-20250219")

    def test_build_openai_table(self):
        table = _build_default_routing_table("openai")
        assert table[TaskComplexity.TRIVIAL] == "gpt-5-mini"
        assert table[TaskComplexity.COMPLEX] == "gpt-5.1"

    def test_unknown_provider_empty(self):
        table = _build_default_routing_table("nonexistent")
        assert table == {}

    def test_next_tier_gemini(self):
        assert _get_next_tier_model("gemini", "gemini-2.5-flash-lite") is not None
        assert _get_next_tier_model("gemini", "gemini-2.5-pro") is None # already top

    def test_next_tier_unknown_model(self):
        assert _get_next_tier_model("gemini", "nonexistent-model") is None


# ── confidence detection ─────────────────────────────────────────────

class TestConfidenceDetection:
    def test_confident_response(self):
        assert not detect_low_confidence(
            "The function calculates the sum of two numbers and returns the result."
        )

    def test_low_confidence_hedging(self):
        assert detect_low_confidence(
            "I'm not sure about this. I think it might be related to the config."
        )

    def test_low_confidence_speculation(self):
        assert detect_low_confidence(
            "[Speculation] This could work. [Unverified] The API may support it."
        )

    def test_empty_response(self):
        assert detect_low_confidence("")

    def test_short_response(self):
        assert detect_low_confidence("ok")


# ── router integration ───────────────────────────────────────────────

class TestModelRouter:
    def setup_method(self):
        self.router = ModelRouter(RouterConfig(enabled=True, max_cascade_retries=1))

    def test_trivial_routes_to_cheapest(self):
        decision = self.router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="balanced",
        )
        assert decision.selected_model == "gemini-2.5-flash-lite"
        assert decision.complexity == TaskComplexity.TRIVIAL

    def test_complex_routes_to_expensive(self):
        decision = self.router.select_model(
            prompt="redesign the entire auth system with OAuth2",
            provider="gemini",
            current_model="gemini-2.5-flash",
            economy_preset="balanced",
        )
        assert decision.selected_model == "gemini-2.5-pro"
        assert decision.complexity == TaskComplexity.COMPLEX

    def test_user_override_skips_routing(self):
        decision = self.router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="balanced",
            user_explicit_model=True,
        )
        assert decision.selected_model == "gemini-2.5-pro"
        assert decision.reason == "user_override"

    def test_quality_mode_no_routing(self):
        decision = self.router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="quality",
        )
        assert decision.selected_model == "gemini-2.5-pro"
        assert decision.reason == "quality_mode"

    def test_frugal_mode_biases_cheaper(self):
        decision = self.router.select_model(
            prompt="update the handler in server.py to return 404",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="frugal",
        )
        # frugal downgrades moderate -> simple -> cheapest
        assert decision.selected_model in ("gemini-2.5-flash-lite", "gemini-2.5-flash")

    def test_cascade_on_low_confidence(self):
        decision = self.router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="balanced",
        )
        escalated = self.router.should_cascade(
            "I'm not sure. I think this might work.",
            decision,
        )
        assert escalated is not None
        assert escalated.escalated is True
        assert escalated.escalated_from == decision.selected_model

    def test_no_cascade_on_confident_response(self):
        decision = self.router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="balanced",
        )
        escalated = self.router.should_cascade(
            "Here is the fix. I renamed the variable from 'tset' to 'test'.",
            decision,
        )
        assert escalated is None

    def test_no_cascade_in_quality_mode(self):
        decision = self.router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="quality",
        )
        escalated = self.router.should_cascade(
            "I'm not sure. I think this might work.",
            decision,
        )
        assert escalated is None

    def test_no_double_cascade(self):
        decision = self.router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="balanced",
        )
        escalated = self.router.should_cascade(
            "I'm not sure. I think this might work.",
            decision,
        )
        assert escalated is not None
        # second cascade should not happen
        double = self.router.should_cascade(
            "I'm not sure. Possibly wrong.",
            escalated,
        )
        assert double is None

    def test_routing_disabled(self):
        router = ModelRouter(RouterConfig(enabled=False))
        decision = router.select_model(
            prompt="fix typo",
            provider="gemini",
            current_model="gemini-2.5-pro",
        )
        assert decision.selected_model == "gemini-2.5-pro"
        assert decision.reason == "routing_disabled"

    def test_custom_routing_table(self):
        custom = {"gemini": {"trivial": "gemini-2.5-flash", "complex": "gemini-2.5-pro"}}
        router = ModelRouter(RouterConfig(custom_routing_table=custom))
        decision = router.select_model(
            prompt="hi",
            provider="gemini",
            current_model="gemini-2.5-pro",
            economy_preset="balanced",
        )
        assert decision.selected_model == "gemini-2.5-flash"

    def test_routing_stats(self):
        self.router.select_model("hi", "gemini", "gemini-2.5-pro")
        self.router.select_model("redesign the auth", "gemini", "gemini-2.5-flash")
        stats = self.router.get_routing_stats()
        assert stats["total_decisions"] == 2
        assert "by_complexity" in stats

    def test_clear_log(self):
        self.router.select_model("hi", "gemini", "gemini-2.5-pro")
        self.router.clear_log()
        assert self.router.get_routing_stats()["total_decisions"] == 0
