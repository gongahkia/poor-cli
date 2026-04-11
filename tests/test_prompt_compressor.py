"""Tests for prompt compression middleware."""

import re
import time
import unittest
from unittest.mock import MagicMock, patch
from poor_cli.prompt_compressor import (
    PromptCompressor,
    CompressionResult,
    CompressionStats,
    COMPRESSION_RATIOS,
    ECONOMY_RATIO_OVERRIDES,
    LATENCY_BUDGET_MS,
)


class TestCompressionRatios(unittest.TestCase):
    def test_default_ratios_exist(self):
        for key in ("tool_output", "file_content", "conversation_history", "system_prompt"):
            self.assertIn(key, COMPRESSION_RATIOS)
            self.assertGreater(COMPRESSION_RATIOS[key], 0)
            self.assertLessEqual(COMPRESSION_RATIOS[key], 1.0)

    def test_economy_presets_cover_all_types(self):
        for preset, ratios in ECONOMY_RATIO_OVERRIDES.items():
            for key in COMPRESSION_RATIOS:
                self.assertIn(key, ratios, f"{preset} missing {key}")

    def test_frugal_more_aggressive_than_quality(self):
        for key in COMPRESSION_RATIOS:
            self.assertLess(
                ECONOMY_RATIO_OVERRIDES["frugal"][key],
                ECONOMY_RATIO_OVERRIDES["quality"][key],
                f"frugal should compress more than quality for {key}",
            )


class TestPromptCompressorInit(unittest.TestCase):
    def test_default_init(self):
        pc = PromptCompressor()
        self.assertEqual(pc._economy_preset, "balanced")
        self.assertFalse(pc._force_heuristic)
        self.assertIsNone(pc._llmlingua)

    def test_force_heuristic(self):
        pc = PromptCompressor(force_heuristic=True)
        self.assertTrue(pc._force_heuristic)

    def test_set_economy_preset(self):
        pc = PromptCompressor()
        pc.set_economy_preset("frugal")
        self.assertEqual(pc._economy_preset, "frugal")

    def test_set_invalid_preset_ignored(self):
        pc = PromptCompressor()
        pc.set_economy_preset("nonexistent")
        self.assertEqual(pc._economy_preset, "balanced") # unchanged

    def test_get_ratio_by_content_type(self):
        pc = PromptCompressor(economy_preset="frugal")
        self.assertEqual(pc.get_ratio("tool_output"), 0.2)
        pc.set_economy_preset("quality")
        self.assertEqual(pc.get_ratio("tool_output"), 0.6)


class TestHeuristicCompression(unittest.TestCase):
    def setUp(self):
        self.pc = PromptCompressor(force_heuristic=True)

    def test_empty_text_returns_empty(self):
        result = self.pc.compress("", content_type="tool_output")
        self.assertTrue(result.skipped)
        self.assertEqual(result.compressed_text, "")

    def test_short_text_ratio_near_one_skips(self):
        result = self.pc.compress("hello", ratio=0.99)
        self.assertTrue(result.skipped)

    def test_whitespace_normalization(self):
        text = "hello    world\n\n\n\n\nfoo   bar"
        result = self.pc.compress(text, ratio=0.8)
        self.assertNotIn("    ", result.compressed_text)
        self.assertNotIn("\n\n\n", result.compressed_text)

    def test_filler_removal(self):
        text = "Please note that the function works. It is important to note that " * 20
        result = self.pc.compress(text, content_type="tool_output", ratio=0.5)
        self.assertLess(len(result.compressed_text), len(text))
        self.assertNotIn("Please note that", result.compressed_text)

    def test_repeated_punctuation_collapsed(self):
        text = "error!!!!! something happened????" + " more text" * 50
        result = self.pc.compress(text, ratio=0.8)
        self.assertNotIn("!!!!!", result.compressed_text)

    def test_large_import_block_collapsed(self):
        imports = "\n".join([f"import module_{i}" for i in range(20)])
        text = imports + "\n\ndef main():\n    pass\n" + "x = 1\n" * 50
        result = self.pc.compress(text, ratio=0.5)
        self.assertIn("more imports", result.compressed_text)
        self.assertLess(len(result.compressed_text), len(text))

    def test_compression_reduces_token_count(self):
        text = ("This is a verbose tool output with lots of unnecessary information. " * 100)
        result = self.pc.compress(text, content_type="tool_output", ratio=0.3)
        self.assertFalse(result.skipped)
        self.assertLess(result.compressed_tokens, result.original_tokens)
        self.assertEqual(result.backend, "heuristic")

    def test_5000_token_tool_output(self):
        """Acceptance criteria: compress 5000-token tool output, verify reduction."""
        text = "Tool output line: some diagnostic information here.\n" * 625 # ~5000 tokens
        result = self.pc.compress(text, content_type="tool_output", ratio=0.3)
        self.assertFalse(result.skipped)
        self.assertLess(result.ratio, 0.6) # should achieve meaningful compression
        self.assertGreater(result.original_tokens, 4000)

    def test_compression_under_100ms(self):
        """Acceptance criteria: compression < 100ms latency."""
        text = "Some tool output with various data points.\n" * 500
        result = self.pc.compress(text, content_type="tool_output")
        self.assertFalse(result.skipped)
        self.assertLess(result.elapsed_ms, LATENCY_BUDGET_MS)


class TestPreservePatterns(unittest.TestCase):
    def setUp(self):
        self.pc = PromptCompressor(force_heuristic=True)

    def test_code_blocks_preserved(self):
        """Acceptance criteria: code blocks preserved through compression."""
        code = "```python\ndef hello():\n    return 42\n```"
        filler = "Please note that this is verbose output. " * 50
        text = filler + "\n" + code + "\n" + filler
        result = self.pc.compress(text, ratio=0.4)
        self.assertIn("def hello():", result.compressed_text)
        self.assertIn("return 42", result.compressed_text)

    def test_error_messages_preserved(self):
        """Acceptance criteria: error messages preserved through compression."""
        error = "FileNotFoundError: /home/user/missing.py not found"
        filler = "Some verbose diagnostic output here. " * 80
        text = filler + "\n" + error + "\n" + filler
        result = self.pc.compress(text, ratio=0.3)
        self.assertIn("FileNotFoundError", result.compressed_text)

    def test_file_paths_preserved(self):
        path = "/home/user/project/src/main.py"
        filler = "Verbose output with lots of padding. " * 80
        text = filler + "\n" + path + "\n" + filler
        result = self.pc.compress(text, ratio=0.3)
        self.assertIn(path, result.compressed_text)

    def test_urls_preserved(self):
        url = "https://github.com/user/repo/issues/42"
        filler = "Extra text padding for compression test. " * 80
        text = filler + "\n" + url + "\n" + filler
        result = self.pc.compress(text, ratio=0.3)
        self.assertIn(url, result.compressed_text)

    def test_custom_preserve_pattern(self):
        custom = re.compile(r"KEEP_THIS_\w+")
        text = "Filler text. " * 100 + "\nKEEP_THIS_IMPORTANT\n" + "More filler. " * 100
        result = self.pc.compress(text, ratio=0.3, preserve_patterns=[custom])
        self.assertIn("KEEP_THIS_IMPORTANT", result.compressed_text)


class TestEconomyModeIntegration(unittest.TestCase):
    """Acceptance criteria: economy mode controls compression aggressiveness."""

    def test_frugal_compresses_more(self):
        pc_frugal = PromptCompressor(force_heuristic=True, economy_preset="frugal")
        pc_quality = PromptCompressor(force_heuristic=True, economy_preset="quality")
        text = "\n".join([f"Tool output line {i}: some diagnostic data value={i*3}" for i in range(300)])
        r_frugal = pc_frugal.compress(text, content_type="tool_output")
        r_quality = pc_quality.compress(text, content_type="tool_output")
        self.assertLess(len(r_frugal.compressed_text), len(r_quality.compressed_text))

    def test_quality_mode_minimal_compression(self):
        pc = PromptCompressor(force_heuristic=True, economy_preset="quality")
        self.assertGreaterEqual(pc.get_ratio("system_prompt"), 0.9)


class TestMessageListCompression(unittest.TestCase):
    def setUp(self):
        self.pc = PromptCompressor(force_heuristic=True, economy_preset="balanced")

    def test_current_user_message_never_compressed(self):
        messages = [
            {"role": "user", "content": "old question " * 50},
            {"role": "assistant", "content": "old answer " * 50},
            {"role": "user", "content": "current question with verbose text " * 50},
        ]
        compressed, saved = self.pc.compress_message_list(messages, current_user_index=2)
        self.assertEqual(compressed[2]["content"], messages[2]["content"]) # unchanged

    def test_skips_short_messages(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        compressed, saved = self.pc.compress_message_list(messages)
        self.assertEqual(saved, 0) # too short to compress

    def test_tool_messages_compressed(self):
        long_output = "Tool result line with data.\n" * 200
        messages = [
            {"role": "tool", "content": long_output},
            {"role": "user", "content": "what happened?"},
        ]
        compressed, saved = self.pc.compress_message_list(messages)
        self.assertGreater(saved, 0)
        self.assertLess(len(compressed[0]["content"]), len(long_output))

    def test_auto_detects_last_user_message(self):
        messages = [
            {"role": "user", "content": "old " * 100},
            {"role": "assistant", "content": "response " * 100},
            {"role": "user", "content": "new " * 100},
        ]
        compressed, _ = self.pc.compress_message_list(messages) # current_user_index=-1
        self.assertEqual(compressed[2]["content"], messages[2]["content"]) # last user untouched


class TestLazyLoading(unittest.TestCase):
    """Acceptance criteria: compression model loaded lazily on first use."""

    def test_no_model_loaded_on_init(self):
        pc = PromptCompressor()
        self.assertIsNone(pc._llmlingua)
        self.assertIsNone(pc._llmlingua_available)

    def test_heuristic_fallback_when_not_installed(self):
        """Acceptance criteria: falls back gracefully if compression model not installed."""
        pc = PromptCompressor()
        text = "Some verbose text. " * 100
        result = pc.compress(text, content_type="tool_output")
        self.assertIn(result.backend, ("heuristic", "skipped"))


class TestCompressionStats(unittest.TestCase):
    def test_stats_accumulate(self):
        pc = PromptCompressor(force_heuristic=True)
        text = "Verbose output line.\n" * 200
        pc.compress(text, content_type="tool_output")
        pc.compress(text, content_type="tool_output")
        stats = pc.stats
        self.assertEqual(stats.total_compressions, 2)
        self.assertGreater(stats.tokens_saved, 0)
        self.assertGreater(stats.total_time_ms, 0)
        self.assertEqual(stats.backend_counts.get("heuristic", 0), 2)

    def test_stats_to_dict(self):
        stats = CompressionStats()
        d = stats.to_dict()
        self.assertIn("total_compressions", d)
        self.assertIn("tokens_saved", d)
        self.assertIn("avg_ratio", d)

    def test_empty_stats(self):
        stats = CompressionStats()
        self.assertEqual(stats.tokens_saved, 0)
        self.assertEqual(stats.avg_ratio, 1.0)


class TestContentTypeInference(unittest.TestCase):
    def setUp(self):
        self.pc = PromptCompressor(force_heuristic=True)

    def test_tool_role(self):
        self.assertEqual(self.pc._infer_content_type("tool", "anything"), "tool_output")

    def test_function_role(self):
        self.assertEqual(self.pc._infer_content_type("function", "x"), "tool_output")

    def test_system_role(self):
        self.assertEqual(self.pc._infer_content_type("system", "x"), "system_prompt")

    def test_file_content_detected(self):
        self.assertEqual(
            self.pc._infer_content_type("assistant", "see src/main.py for details"),
            "file_content",
        )

    def test_code_block_detected(self):
        self.assertEqual(
            self.pc._infer_content_type("assistant", "```python\ncode\n```"),
            "file_content",
        )

    def test_plain_conversation(self):
        self.assertEqual(
            self.pc._infer_content_type("user", "what does this do"),
            "conversation_history",
        )


class TestRepeatedSimilarLines(unittest.TestCase):
    def test_repeated_lines_collapsed(self):
        pc = PromptCompressor(force_heuristic=True)
        line = "INFO 2024-01-01 12:00:00 - Processing record batch\n"
        text = line * 20 + "Final summary line.\n"
        result = pc.compress(text, ratio=0.3)
        self.assertLess(len(result.compressed_text), len(text))


if __name__ == "__main__":
    unittest.main()
