"""Tests for the economy mode system."""

import hashlib
import time
import unittest
from dataclasses import asdict
from unittest.mock import MagicMock, patch
from poor_cli.economy import (
    EconomyConfig,
    EconomySavings,
    EconomySavingsTracker,
    ECONOMY_PRESETS,
    apply_economy_preset,
    classify_prompt_complexity,
    distill_prompt,
)
from poor_cli.config import Config
from poor_cli.provider_catalog import get_cheapest_model, get_downshift_model
from poor_cli.prompts import (
    build_tool_calling_system_instruction,
    ECONOMY_TERSE_SUFFIX,
    ECONOMY_BATCHED_READS_SUFFIX,
)


class TestClassifyPromptComplexity(unittest.TestCase):
    def test_simple_question(self):
        self.assertEqual(classify_prompt_complexity("what is 2+2?"), "simple")

    def test_simple_short(self):
        self.assertEqual(classify_prompt_complexity("hello"), "simple")

    def test_moderate_with_tool_keyword(self):
        result = classify_prompt_complexity("please create a new file called foo.py")
        self.assertIn(result, ("moderate", "complex"))

    def test_complex_with_code_block(self):
        prompt = "Fix this:\n```python\ndef foo():\n    pass\n```\nand also refactor the test"
        self.assertEqual(classify_prompt_complexity(prompt), "complex")

    def test_complex_long_prompt(self):
        prompt = "x " * 1100 # > 2000 chars
        self.assertEqual(classify_prompt_complexity(prompt), "complex")

    def test_moderate_multiple_questions(self):
        prompt = "What is this? How does it work? Where is it defined?"
        self.assertEqual(classify_prompt_complexity(prompt), "moderate")


class TestDistillPrompt(unittest.TestCase):
    def test_collapses_whitespace(self):
        config = EconomyConfig(strip_code_comments=False)
        text = "hello    world\n\n\n\nfoo"
        result, saved = distill_prompt(text, "", config)
        self.assertNotIn("    ", result)
        self.assertNotIn("\n\n\n", result)
        self.assertGreater(saved, 0)

    def test_strips_comments_when_enabled(self):
        config = EconomyConfig(strip_code_comments=True)
        text = "code here\n# this is a comment\nmore code"
        result, _ = distill_prompt(text, "", config)
        self.assertNotIn("# this is a comment", result)
        self.assertIn("code here", result)

    def test_preserves_content_without_comments(self):
        config = EconomyConfig(strip_code_comments=False)
        text = "# this is a comment\ncode here"
        result, _ = distill_prompt(text, "", config)
        self.assertIn("# this is a comment", result)

    def test_context_concatenation(self):
        config = EconomyConfig()
        result, _ = distill_prompt("prompt", "context", config)
        self.assertIn("prompt", result)
        self.assertIn("context", result)


class TestEconomyPresets(unittest.TestCase):
    def test_frugal_preset(self):
        config = EconomyConfig()
        apply_economy_preset(config, "frugal")
        self.assertEqual(config.preset, "frugal")
        self.assertTrue(config.terse_system_prompt)
        self.assertTrue(config.strip_code_comments)
        self.assertEqual(config.economy_max_tokens, 2048)
        self.assertEqual(config.tool_call_budget, 8)
        self.assertTrue(config.response_cache)
        self.assertEqual(config.idle_compact_seconds, 60)

    def test_balanced_preset(self):
        config = EconomyConfig()
        apply_economy_preset(config, "balanced")
        self.assertEqual(config.preset, "balanced")
        self.assertFalse(config.terse_system_prompt)
        self.assertFalse(config.strip_code_comments)
        self.assertEqual(config.economy_max_tokens, 0)
        self.assertEqual(config.tool_call_budget, 0)

    def test_quality_preset(self):
        config = EconomyConfig()
        apply_economy_preset(config, "quality")
        self.assertEqual(config.preset, "quality")
        self.assertFalse(config.auto_downshift)
        self.assertFalse(config.prompt_distill)
        self.assertFalse(config.dedup_context)

    def test_unknown_preset_noop(self):
        config = EconomyConfig()
        original = asdict(config)
        apply_economy_preset(config, "nonexistent")
        self.assertEqual(asdict(config), original)

    def test_all_presets_cover_same_keys(self):
        keys = set(ECONOMY_PRESETS["frugal"].keys())
        for name, vals in ECONOMY_PRESETS.items():
            self.assertEqual(set(vals.keys()), keys, f"preset {name} has different keys")


class TestEconomySavingsTracker(unittest.TestCase):
    def test_record_distillation(self):
        tracker = EconomySavingsTracker()
        tracker.record_distillation(1000, 800)
        summary = tracker.get_summary()
        self.assertEqual(summary["tokens_saved_by_distillation"], 200)

    def test_record_dedup(self):
        tracker = EconomySavingsTracker()
        tracker.record_dedup(500)
        self.assertEqual(tracker.get_summary()["tokens_saved_by_dedup"], 500)

    def test_record_cache_hit(self):
        tracker = EconomySavingsTracker()
        tracker.record_cache_hit()
        tracker.record_cache_hit()
        self.assertEqual(tracker.get_summary()["cache_hits"], 2)

    def test_record_tool_calls_avoided(self):
        tracker = EconomySavingsTracker()
        tracker.record_tool_calls_avoided(5)
        self.assertEqual(tracker.get_summary()["tool_calls_avoided"], 5)

    def test_money_saved_calculation(self):
        tracker = EconomySavingsTracker()
        tracker.record_distillation(10000, 5000) # 5000 tokens saved
        money = tracker.get_money_saved(cost_per_1k_in=0.001, cost_per_1k_out=0.003)
        self.assertGreater(money, 0)

    def test_empty_summary(self):
        tracker = EconomySavingsTracker()
        summary = tracker.get_summary()
        self.assertEqual(summary["tokens_saved_by_distillation"], 0)
        self.assertEqual(summary["cache_hits"], 0)
        self.assertEqual(summary["estimated_money_saved_usd"], 0.0)


class TestConfigIntegration(unittest.TestCase):
    def test_economy_in_config_defaults(self):
        config = Config()
        self.assertEqual(config.economy.preset, "balanced")
        self.assertTrue(config.economy.auto_downshift)

    def test_economy_to_dict(self):
        config = Config()
        d = config.to_dict()
        self.assertIn("economy", d)
        self.assertEqual(d["economy"]["preset"], "balanced")

    def test_economy_from_dict(self):
        config = Config.from_dict({"economy": {"preset": "frugal", "terse_system_prompt": True}})
        self.assertEqual(config.economy.preset, "frugal")
        self.assertTrue(config.economy.terse_system_prompt)

    def test_economy_from_dict_empty(self):
        config = Config.from_dict({})
        self.assertEqual(config.economy.preset, "balanced")


class TestProviderCatalogDownshift(unittest.TestCase):
    def test_get_cheapest_model_gemini(self):
        tier = get_cheapest_model("gemini")
        self.assertIsNotNone(tier)
        self.assertEqual(tier.tier, "cheap")

    def test_get_downshift_model_gemini(self):
        result = get_downshift_model("gemini")
        self.assertIsNotNone(result)
        name, tier = result
        self.assertIn("flash-lite", name)

    def test_get_downshift_model_openai(self):
        result = get_downshift_model("openai")
        self.assertIsNotNone(result)
        name, tier = result
        self.assertIn("mini", name)

    def test_get_downshift_model_anthropic(self):
        result = get_downshift_model("anthropic")
        self.assertIsNotNone(result)
        name, tier = result
        self.assertIn("haiku", name)


class TestResponseCache(unittest.TestCase):
    """Tests for the response cache mechanism in PoorCLICore."""

    def _make_core_stub(self):
        """Create a minimal PoorCLICore-like object for cache testing."""
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.response_cache = True
        core.config.economy.response_cache_ttl = 5
        core._response_cache = {}
        core._economy_tracker = EconomySavingsTracker()
        return core

    def test_cache_store_and_lookup(self):
        core = self._make_core_stub()
        core._cache_store("hello world", "response text")
        result = core._cache_lookup("hello world")
        self.assertEqual(result, "response text")

    def test_cache_miss_on_different_prompt(self):
        core = self._make_core_stub()
        core._cache_store("hello world", "response text")
        result = core._cache_lookup("different prompt")
        self.assertIsNone(result)

    def test_cache_expiry(self):
        core = self._make_core_stub()
        core.config.economy.response_cache_ttl = 0 # immediate expiry
        key = core._cache_key("test prompt")
        core._response_cache[key] = ("cached", time.monotonic() - 1) # already expired
        result = core._cache_lookup("test prompt")
        self.assertIsNone(result)

    def test_cache_disabled(self):
        core = self._make_core_stub()
        core.config.economy.response_cache = False
        core._cache_store("test", "response")
        result = core._cache_lookup("test")
        self.assertIsNone(result)


class TestContextDedup(unittest.TestCase):
    """Tests for context deduplication."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.context_dedup = True
        core._files_seen_in_session = {}
        core._economy_tracker = EconomySavingsTracker()
        return core

    def test_first_file_passes_through(self):
        core = self._make_core_stub()
        text = "File: /tmp/test.py\nprint('hello')\nmore code"
        result, saved = core._dedup_context_files(text)
        self.assertIn("print('hello')", result)
        self.assertEqual(saved, 0)

    def test_second_read_of_same_file_skipped(self):
        core = self._make_core_stub()
        text = "File: /tmp/test.py\nprint('hello')\n"
        core._dedup_context_files(text) # first pass
        result, saved = core._dedup_context_files(text) # second pass
        self.assertIn("already in context", result)
        self.assertGreater(saved, 0)

    def test_dedup_disabled(self):
        core = self._make_core_stub()
        core.config.economy.context_dedup = False
        core.config.economy.dedup_context = False
        text = "File: /tmp/test.py\ncode\n"
        core._dedup_context_files(text)
        result, saved = core._dedup_context_files(text)
        self.assertEqual(saved, 0) # no dedup when both flags disabled


class TestDiffOnlyReads(unittest.TestCase):
    """Tests for diff-only read_file output."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.diff_only_reads = True
        core._last_file_contents = {}
        return core

    def test_first_read_returns_full(self):
        core = self._make_core_stub()
        result = core._apply_diff_only_read("read_file", {"file_path": "/tmp/f.py"}, "line1\nline2\n")
        self.assertEqual(result, "line1\nline2\n")

    def test_unchanged_file_returns_notice(self):
        core = self._make_core_stub()
        content = "line1\nline2\n"
        core._apply_diff_only_read("read_file", {"file_path": "/tmp/f.py"}, content)
        result = core._apply_diff_only_read("read_file", {"file_path": "/tmp/f.py"}, content)
        self.assertIn("unchanged", result)

    def test_changed_file_returns_diff(self):
        core = self._make_core_stub()
        core._apply_diff_only_read("read_file", {"file_path": "/tmp/f.py"}, "line1\nline2\n")
        result = core._apply_diff_only_read("read_file", {"file_path": "/tmp/f.py"}, "line1\nline3\n")
        self.assertIn("diff-only read", result)
        self.assertIn("line3", result)

    def test_non_read_file_passthrough(self):
        core = self._make_core_stub()
        result = core._apply_diff_only_read("bash", {"command": "ls"}, "output")
        self.assertEqual(result, "output")

    def test_disabled_returns_full(self):
        core = self._make_core_stub()
        core.config.economy.diff_only_reads = False
        content = "line1\n"
        core._apply_diff_only_read("read_file", {"file_path": "/tmp/f.py"}, content)
        result = core._apply_diff_only_read("read_file", {"file_path": "/tmp/f.py"}, content)
        self.assertEqual(result, content) # full content, no diff


class TestEconomyMaxTokens(unittest.TestCase):
    """Tests for economy_max_tokens propagation to providers."""

    def _make_core_stub(self, cap=2048):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.economy_max_tokens = cap
        core.provider = MagicMock()
        core.provider.economy_max_output_tokens = 0
        return core

    def test_applies_cap(self):
        core = self._make_core_stub(2048)
        core._apply_economy_max_tokens()
        self.assertEqual(core.provider.economy_max_output_tokens, 2048)

    def test_zero_cap_clears(self):
        core = self._make_core_stub(0)
        core.provider.economy_max_output_tokens = 999
        core._apply_economy_max_tokens()
        self.assertEqual(core.provider.economy_max_output_tokens, 0)


class TestBatchedReadsPrompt(unittest.TestCase):
    """Tests for prefer_batched_reads system prompt hint."""

    def test_batched_reads_suffix_appended(self):
        instruction = build_tool_calling_system_instruction("/tmp", batched_reads=True)
        self.assertIn("batch them into a single tool call round", instruction)

    def test_no_suffix_by_default(self):
        instruction = build_tool_calling_system_instruction("/tmp")
        self.assertNotIn("batch them into a single tool call round", instruction)

    def test_terse_and_batched_combined(self):
        instruction = build_tool_calling_system_instruction("/tmp", terse_mode=True, batched_reads=True)
        self.assertIn("Be extremely concise", instruction)
        self.assertIn("batch them into a single tool call round", instruction)


class TestIdleCompactTimer(unittest.TestCase):
    """Tests for idle auto-compact timer setup."""

    def _make_core_stub(self, seconds=60):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.idle_compact_seconds = seconds
        core._idle_compact_task = None
        core._idle_loop = None
        core._context_compressor = MagicMock()
        core.provider = None
        return core

    def test_disabled_when_zero(self):
        core = self._make_core_stub(0)
        core._reset_idle_compact_timer() # should be a no-op
        self.assertIsNone(core._idle_compact_task)

    def test_no_crash_without_event_loop(self):
        core = self._make_core_stub(60)
        core._reset_idle_compact_timer() # no running loop — should not crash
        self.assertIsNone(core._idle_compact_task)


if __name__ == "__main__":
    unittest.main()
