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
    EconomyTurnReport,
    ECONOMY_PRESETS,
    apply_economy_preset,
    classify_prompt_complexity,
    distill_prompt,
    resolve_output_verbosity,
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

    def test_simple_pure_questions(self):
        prompt = "What is this? How does it work? Where is it defined?"
        self.assertEqual(classify_prompt_complexity(prompt), "simple") # pure questions without tool keywords

    def test_moderate_question_with_file_path(self):
        prompt = "What does utils.py do? How is it connected?"
        self.assertEqual(classify_prompt_complexity(prompt), "moderate") # file path detected

    def test_complex_with_verb(self):
        prompt = "refactor the auth module"
        self.assertEqual(classify_prompt_complexity(prompt), "complex") # complex verb


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
        text = "```python\ncode here\n# this is a comment\nmore code\n```"
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
        self.assertEqual(resolve_output_verbosity(config), "caveman")
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
        self.assertEqual(resolve_output_verbosity(config), "normal")
        self.assertFalse(config.terse_system_prompt)
        self.assertFalse(config.strip_code_comments)
        self.assertEqual(config.economy_max_tokens, 0)
        self.assertEqual(config.tool_call_budget, 0)

    def test_quality_preset(self):
        config = EconomyConfig()
        apply_economy_preset(config, "quality")
        self.assertEqual(config.preset, "quality")
        self.assertEqual(resolve_output_verbosity(config), "comprehensive")
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
        self.assertIn("OUTPUT RULES (frugal mode active)", instruction)
        self.assertIn("Preserve exact code blocks", instruction)
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


class TestSystemPromptSize(unittest.TestCase):
    """Verify system prompt is compact after tool-listing removal."""

    def test_default_prompt_under_6000_chars(self):
        instruction = build_tool_calling_system_instruction("/tmp")
        self.assertLess(len(instruction), 6000,
            f"System prompt too large: {len(instruction)} chars (target <6000)")

    def test_no_duplicate_tool_listings(self):
        instruction = build_tool_calling_system_instruction("/tmp")
        self.assertNotIn("gh_pr_list(state, limit)", instruction) # GH tool listing section gone
        self.assertNotIn("fetch_url(url, timeout?", instruction) # extended tool listing section gone
        self.assertNotIn("dependency_inspect(path?)", instruction) # extended tool listing gone

    def test_budget_aware_pruning(self):
        full = build_tool_calling_system_instruction("/tmp")
        pruned = build_tool_calling_system_instruction("/tmp", max_system_tokens=500)
        self.assertLessEqual(len(pruned), len(full))
        self.assertIn("CURRENT WORKING DIRECTORY", pruned) # intro always kept

    def test_ollama_truncation_still_works(self):
        instruction = build_tool_calling_system_instruction("/tmp", provider="ollama")
        self.assertLessEqual(len(instruction), 4000)


class TestBalancedPresetActivation(unittest.TestCase):
    """Verify dormant features now active in balanced preset."""

    def test_balanced_enables_response_cache(self):
        config = EconomyConfig()
        apply_economy_preset(config, "balanced")
        self.assertTrue(config.response_cache)

    def test_balanced_enables_diff_only_reads(self):
        config = EconomyConfig()
        apply_economy_preset(config, "balanced")
        self.assertTrue(config.diff_only_reads)

    def test_balanced_enables_idle_compact(self):
        config = EconomyConfig()
        apply_economy_preset(config, "balanced")
        self.assertEqual(config.idle_compact_seconds, 180)

    def test_balanced_tool_strip_chars(self):
        config = EconomyConfig()
        apply_economy_preset(config, "balanced")
        self.assertEqual(config.tool_strip_chars, 200)

    def test_frugal_tool_strip_chars(self):
        config = EconomyConfig()
        apply_economy_preset(config, "frugal")
        self.assertEqual(config.tool_strip_chars, 50)


class TestDistillTraceCollapse(unittest.TestCase):
    """Verify stack trace and code paste collapsing."""

    def test_python_traceback_collapsed(self):
        config = EconomyConfig(prompt_distill=True)
        trace = "\n".join([
            f'  File "/app/mod{i}.py", line {i*10}, in func{i}\n    result = call{i}()'
            for i in range(10)
        ])
        result, saved = distill_prompt(trace, "", config)
        self.assertIn("similar frames", result)
        self.assertGreater(saved, 0)

    def test_node_trace_collapsed(self):
        config = EconomyConfig(prompt_distill=True)
        trace = "\n".join([f"    at Function.{i} (/app/file{i}.js:{i}:1)" for i in range(8)])
        result, saved = distill_prompt(trace, "", config)
        self.assertIn("similar frames", result)

    def test_short_trace_untouched(self):
        config = EconomyConfig(prompt_distill=True)
        trace = '  File "/app/a.py", line 1, in f\n    x()\n  File "/app/b.py", line 2, in g\n    y()'
        result, _ = distill_prompt(trace, "", config)
        self.assertNotIn("similar frames", result)


class TestCostGuardrailPerTask(unittest.TestCase):
    """Verify per-task cost guardrails."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.cost_guardrails.task_max_tokens = 1000
        core.config.cost_guardrails.session_max_tokens = 0
        core._session_total_input_tokens = 0
        core._session_total_output_tokens = 0
        core._session_total_cost_usd = 0.0
        core._task_input_tokens = 500
        core._task_output_tokens = 600
        core._task_cost_usd = 0.0
        core._cost_warning_emitted = False
        return core

    def test_task_token_limit_triggers(self):
        core = self._make_core_stub()
        reason = core._check_cost_guardrails()
        self.assertIsNotNone(reason)
        self.assertIn("Task token limit", reason)

    def test_task_under_limit_passes(self):
        core = self._make_core_stub()
        core._task_input_tokens = 200
        core._task_output_tokens = 200
        reason = core._check_cost_guardrails()
        self.assertIsNone(reason)


class TestCostWarningThreshold(unittest.TestCase):
    """Verify 80% budget warning."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.cost_guardrails.session_max_tokens = 10000
        core._session_total_input_tokens = 4500
        core._session_total_output_tokens = 4000 # total 8500 = 85% of 10000
        core._session_total_cost_usd = 0.0
        core._task_input_tokens = 0
        core._task_output_tokens = 0
        core._task_cost_usd = 0.0
        core._cost_warning_emitted = False
        return core

    def test_80_percent_warning(self):
        core = self._make_core_stub()
        warning = core._check_cost_warning()
        self.assertIsNotNone(warning)
        self.assertIn("80%", warning)

    def test_warning_emitted_once(self):
        core = self._make_core_stub()
        core._check_cost_warning()
        second = core._check_cost_warning()
        self.assertIsNone(second) # only fires once

    def test_no_warning_under_threshold(self):
        core = self._make_core_stub()
        core._session_total_input_tokens = 1000
        core._session_total_output_tokens = 1000
        warning = core._check_cost_warning()
        self.assertIsNone(warning)


class TestResponseCacheSkipsMutations(unittest.TestCase):
    """Verify response cache skips mutation-likely prompts."""

    def _make_core_stub(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = Config()
        core.config.economy.response_cache = True
        core.config.economy.response_cache_ttl = 300
        core._response_cache = {}
        core._economy_tracker = EconomySavingsTracker()
        return core

    def test_mutation_prompt_not_cached(self):
        core = self._make_core_stub()
        core._cache_store("create a new file called foo.py", "ok done")
        result = core._cache_lookup("create a new file called foo.py")
        self.assertIsNone(result) # was never stored

    def test_readonly_prompt_cached(self):
        core = self._make_core_stub()
        core._cache_store("what does this function do?", "it does X")
        result = core._cache_lookup("what does this function do?")
        self.assertEqual(result, "it does X")


if __name__ == "__main__":
    unittest.main()
