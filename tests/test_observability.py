"""Tests for token observability and user control features."""

import unittest
from unittest.mock import MagicMock, patch
from dataclasses import asdict
from poor_cli.config import Config
from poor_cli.economy import EconomyTurnReport, EconomySavingsTracker
from poor_cli.core_events import CoreEvent


class TestCoreEventExtensions(unittest.TestCase):
    """Verify new CoreEvent types and extended fields."""

    def test_cost_update_includes_breakdown(self):
        ev = CoreEvent.cost_update(
            input_tokens=100, output_tokens=50,
            system_tokens=30, history_tokens=60, tool_result_tokens=10,
        )
        self.assertEqual(ev.data["systemTokens"], 30)
        self.assertEqual(ev.data["historyTokens"], 60)
        self.assertEqual(ev.data["toolResultTokens"], 10)

    def test_cost_update_omits_zero_breakdown(self):
        ev = CoreEvent.cost_update(input_tokens=100, output_tokens=50)
        self.assertNotIn("systemTokens", ev.data)
        self.assertNotIn("historyTokens", ev.data)

    def test_context_pressure_event(self):
        ev = CoreEvent.context_pressure(used_tokens=8000, max_tokens=10000, pressure_pct=80.0)
        self.assertEqual(ev.type, "context_pressure")
        self.assertEqual(ev.data["usedTokens"], 8000)
        self.assertEqual(ev.data["pressurePct"], 80.0)

    def test_economy_turn_report_event(self):
        report = {"distillation_tokens_saved": 120, "downshifted": True,
                  "downshift_model": "gemini-flash-lite", "cache_hit": False,
                  "dedup_tokens_saved": 0, "diff_only_applied": False}
        ev = CoreEvent.economy_turn_report(report)
        self.assertEqual(ev.type, "economy_turn_report")
        self.assertEqual(ev.data["distillation_tokens_saved"], 120)
        self.assertTrue(ev.data["downshifted"])


class TestEconomyTurnReport(unittest.TestCase):
    def test_default_values(self):
        r = EconomyTurnReport()
        self.assertEqual(r.distillation_tokens_saved, 0)
        self.assertFalse(r.downshifted)
        self.assertFalse(r.cache_hit)
        self.assertFalse(r.diff_only_applied)

    def test_asdict(self):
        r = EconomyTurnReport(distillation_tokens_saved=50, downshifted=True, downshift_model="gpt-5-mini")
        d = asdict(r)
        self.assertEqual(d["distillation_tokens_saved"], 50)
        self.assertEqual(d["downshift_model"], "gpt-5-mini")


class TestContextPressure(unittest.TestCase):
    """Verify get_context_pressure core method."""

    def _make_core_stub(self, history_chars=4000, max_ctx=10000, sys_instruction="x" * 400):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.provider = MagicMock()
        caps = MagicMock()
        caps.max_context_tokens = max_ctx
        core.provider.get_capabilities.return_value = caps
        core.provider.get_history.return_value = [
            {"role": "user", "content": "x" * history_chars},
        ]
        core._system_instruction = sys_instruction
        return core

    def test_low_pressure(self):
        core = self._make_core_stub(history_chars=400, max_ctx=100000)
        result = core.get_context_pressure()
        self.assertLess(result["pressure_pct"], 5)
        self.assertEqual(result["strategy_hint"], "ok")

    def test_high_pressure(self):
        core = self._make_core_stub(history_chars=30000, max_ctx=10000)
        result = core.get_context_pressure()
        self.assertGreater(result["pressure_pct"], 70)
        self.assertEqual(result["strategy_hint"], "compress")

    def test_no_provider(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.provider = None
        core._system_instruction = ""
        result = core.get_context_pressure()
        self.assertEqual(result["pressure_pct"], 0)


class TestContextBreakdown(unittest.TestCase):
    """Verify get_context_breakdown core method."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.provider = MagicMock()
        caps = MagicMock()
        caps.max_context_tokens = 100000
        core.provider.get_capabilities.return_value = caps
        core.provider.get_history.return_value = [
            {"role": "user", "content": "hello " * 100},
            {"role": "assistant", "content": "world " * 200},
            {"role": "tool", "content": "result " * 300},
            {"role": "user", "content": "followup"},
        ]
        core._system_instruction = "system prompt " * 50
        return core

    def test_breakdown_categories(self):
        core = self._make_core_stub()
        result = core.get_context_breakdown()
        self.assertGreater(result["system_tokens"], 0)
        self.assertGreater(result["history_tokens"], 0)
        self.assertGreater(result["tool_result_tokens"], 0)
        self.assertEqual(result["turn_count"], 2) # 2 user messages

    def test_total_matches_sum(self):
        core = self._make_core_stub()
        result = core.get_context_breakdown()
        expected = result["system_tokens"] + result["history_tokens"] + result["tool_result_tokens"]
        self.assertEqual(result["total_tokens"], expected)


class TestEstimateCost(unittest.TestCase):
    """Verify pre-send cost estimate."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.provider = MagicMock()
        caps = MagicMock()
        caps.max_context_tokens = 200000
        core.provider.get_capabilities.return_value = caps
        core.provider.get_history.return_value = [
            {"role": "user", "content": "hello " * 100},
        ]
        core._system_instruction = "system " * 50
        return core

    def test_estimate_returns_breakdown(self):
        core = self._make_core_stub()
        result = core.estimate_cost("what does this function do?")
        self.assertIn("estimated_input_tokens", result)
        self.assertIn("estimated_cost_usd", result)
        self.assertIn("breakdown", result)
        self.assertIn("system", result["breakdown"])
        self.assertIn("history", result["breakdown"])
        self.assertIn("prompt", result["breakdown"])

    def test_estimate_cost_positive(self):
        core = self._make_core_stub()
        result = core.estimate_cost("explain the auth module in detail")
        self.assertGreater(result["estimated_input_tokens"], 0)
        self.assertGreaterEqual(result["estimated_cost_usd"], 0)

    def test_estimate_pressure_after(self):
        core = self._make_core_stub()
        result = core.estimate_cost("x" * 10000)
        self.assertIn("context_pressure_after_pct", result)
        self.assertGreater(result["context_pressure_after_pct"], 0)


class TestModelCostComparison(unittest.TestCase):
    """Verify model cost comparison."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.model.provider = "gemini"
        core.config.model.model_name = "gemini-2.5-flash"
        core._session_total_input_tokens = 10000
        core._session_total_output_tokens = 5000
        core._session_total_cost_usd = 0.01
        return core

    def test_comparison_returns_ratios(self):
        core = self._make_core_stub()
        result = core.compare_model_cost("anthropic", "claude-sonnet-4-20250514")
        if "error" in result:
            self.skipTest("model tier not in catalog")
        self.assertIn("input_cost_ratio", result)
        self.assertIn("session_cost_if_target_usd", result)

    def test_unknown_model_returns_error(self):
        core = self._make_core_stub()
        result = core.compare_model_cost("fake", "fake-model")
        self.assertIn("error", result)


class TestCacheStats(unittest.TestCase):
    """Verify cache stats endpoint."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.response_cache = True
        core._response_cache = {"key1": ("val", 0), "key2": ("val", 0)}
        core.tool_registry = MagicMock()
        core.tool_registry.get_tool_cache_stats.return_value = {
            "cache_hits": 5, "cache_misses": 10, "cache_entries": 3,
        }
        return core

    def test_cache_stats_merged(self):
        core = self._make_core_stub()
        result = core.get_cache_stats()
        self.assertEqual(result["cache_hits"], 5)
        self.assertEqual(result["cache_misses"], 10)
        self.assertEqual(result["response_cache_entries"], 2)
        self.assertTrue(result["response_cache_enabled"])

    def test_cache_stats_no_registry(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.response_cache = False
        core._response_cache = {}
        core.tool_registry = None
        result = core.get_cache_stats()
        self.assertEqual(result["response_cache_entries"], 0)
        self.assertFalse(result["response_cache_enabled"])


class TestCostExport(unittest.TestCase):
    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.provider = MagicMock()
        caps = MagicMock()
        caps.max_context_tokens = 100000
        core.provider.get_capabilities.return_value = caps
        core.provider.get_history.return_value = []
        core._system_instruction = "sys"
        core._session_total_input_tokens = 500
        core._session_total_output_tokens = 300
        core._session_total_cost_usd = 0.01
        core._economy_tracker = EconomySavingsTracker()
        core._response_cache = {}
        core.tool_registry = MagicMock()
        core.tool_registry.get_tool_cache_stats.return_value = {"cache_hits": 0, "cache_misses": 0, "cache_entries": 0}
        return core

    def test_export_contains_all_sections(self):
        core = self._make_core_stub()
        report = core.export_cost_report()
        self.assertIn("session", report)
        self.assertIn("economy_savings", report)
        self.assertIn("context_breakdown", report)
        self.assertIn("cache_stats", report)
        self.assertIn("model", report)


class TestBudgetTemplates(unittest.TestCase):
    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core._cost_warning_emitted = True
        return core

    def test_apply_quick_question(self):
        core = self._make_core_stub()
        result = core.apply_budget_template("quick_question")
        self.assertEqual(result["template"], "quick_question")
        self.assertEqual(core.config.cost_guardrails.session_max_tokens, 5000)
        self.assertFalse(core._cost_warning_emitted) # reset on new budget

    def test_apply_deep_refactor(self):
        core = self._make_core_stub()
        result = core.apply_budget_template("deep_refactor")
        self.assertEqual(core.config.cost_guardrails.session_max_cost_usd, 0.50)

    def test_apply_unknown_template(self):
        core = self._make_core_stub()
        result = core.apply_budget_template("nonexistent")
        self.assertIn("error", result)

    def test_list_templates(self):
        from poor_cli.core import PoorCLICore
        templates = PoorCLICore.list_budget_templates()
        self.assertIn("quick_question", templates)
        self.assertIn("code_review", templates)
        self.assertIn("deep_refactor", templates)
        self.assertIn("unlimited", templates)


class TestAutoCompressOnPressure(unittest.TestCase):
    def _make_core_stub(self, pressure_pct=80):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.auto_compress_pressure_pct = 70
        core.config.context_compression.enabled = True
        core.config.context_compression.compress_after_turns = 3
        core.config.context_compression.preserve_recent_turns = 2
        core.provider = MagicMock()
        caps = MagicMock()
        caps.max_context_tokens = 1000
        core.provider.get_capabilities.return_value = caps
        # simulate high pressure with enough messages (>4 required)
        msg_content = "x" * int(1000 * 4 * pressure_pct / 100 // 6)
        core.provider.get_history.return_value = [
            {"role": "user", "content": msg_content},
            {"role": "assistant", "content": msg_content},
            {"role": "user", "content": msg_content},
            {"role": "assistant", "content": msg_content},
            {"role": "user", "content": msg_content},
            {"role": "assistant", "content": msg_content},
        ]
        core._system_instruction = ""
        from unittest.mock import AsyncMock
        core._context_compressor = MagicMock()
        core._context_compressor.compress_auto = AsyncMock(return_value=[{"role": "user", "content": "compressed"}])
        core._turn_economy = EconomyTurnReport()
        return core

    def test_no_compress_under_threshold(self):
        import asyncio
        core = self._make_core_stub(pressure_pct=50)
        result = asyncio.run(core._auto_compress_on_pressure())
        self.assertIsNone(result)

    def test_compress_over_threshold(self):
        import asyncio
        core = self._make_core_stub(pressure_pct=80)
        result = asyncio.run(core._auto_compress_on_pressure())
        self.assertEqual(result, "auto_pressure")


class TestFallbackCostSort(unittest.TestCase):
    def test_ollama_first_when_prefer_cheaper(self):
        from poor_cli.provider_fallback import ProviderFallbackManager
        from poor_cli.config import FallbackConfig, ConfigManager
        cfg = FallbackConfig(enabled=True, chain=["openai", "gemini", "ollama"], prefer_cheaper=True)
        cm = MagicMock(spec=ConfigManager)
        mgr = ProviderFallbackManager(cfg, cm)
        chain = mgr._get_fallback_chain("anthropic")
        self.assertEqual(chain[0], "ollama")


class TestCalibratedTokenEstimation(unittest.TestCase):
    def test_anthropic_ratio(self):
        from poor_cli.context import chars_per_token
        self.assertEqual(chars_per_token("anthropic"), 3.5)
        self.assertEqual(chars_per_token("gemini"), 4.0)
        self.assertEqual(chars_per_token("unknown"), 4) # default

    def test_model_context_window(self):
        from poor_cli.provider_catalog import get_model_context_window
        self.assertEqual(get_model_context_window("gemini", "gemini-2.5-flash"), 1000000)
        self.assertEqual(get_model_context_window("anthropic", "claude-sonnet-4-20250514"), 200000)
        self.assertEqual(get_model_context_window("fake", "fake"), 0)


class TestResponseCacheFalsePositives(unittest.TestCase):
    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.response_cache = True
        core.config.economy.response_cache_ttl = 300
        core._response_cache = {}
        core._economy_tracker = EconomySavingsTracker()
        return core

    def test_simple_question_is_cached(self):
        core = self._make_core_stub()
        core._cache_store("what is a closure?", "a function that captures its environment")
        result = core._cache_lookup("what is a closure?")
        self.assertEqual(result, "a function that captures its environment") # "simple" — should be cached

    def test_imperative_create_not_cached(self):
        core = self._make_core_stub()
        core._cache_store("create a new React component with tests", "done")
        result = core._cache_lookup("create a new React component with tests")
        self.assertIsNone(result) # "complex" — should not be cached


class TestTokenBreakdownCompute(unittest.TestCase):
    """Verify _compute_token_breakdown helper."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.provider = MagicMock()
        core.provider.get_history.return_value = [
            {"role": "user", "content": "a" * 400},
            {"role": "tool", "content": "b" * 800},
            {"role": "assistant", "content": "c" * 200},
        ]
        core._system_instruction = "d" * 1200
        return core

    def test_breakdown_values(self):
        core = self._make_core_stub()
        sys_tok, hist_tok, tool_tok = core._compute_token_breakdown()
        # uses calibrated chars_per_token (default provider → 4.0)
        self.assertGreater(sys_tok, 250) # ~1200/4 = 300
        self.assertGreater(tool_tok, 150) # ~800/4 = 200
        self.assertGreater(hist_tok, 100) # ~600/4 = 150


if __name__ == "__main__":
    unittest.main()
