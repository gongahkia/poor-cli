"""tests for poor-cli.edit_formats module."""

import unittest

from poor_cli.edit_formats import (
    SearchReplaceFormat,
    WholeFileFormat,
    UnifiedDiffFormat,
    LineRangeFormat,
    estimate_changed_lines,
    render_compact_edit,
    render_search_replace_blocks,
    render_unified_diff,
    select_edit_format,
    suggest_format_for_model,
    get_format,
)
from poor_cli.providers.anthropic_provider import AnthropicProvider
from poor_cli.providers.gemini_provider import GeminiProvider
from poor_cli.providers.ollama_provider import OllamaProvider
from poor_cli.providers.openai_provider import OpenAIProvider
from poor_cli.providers.openrouter_provider import OpenRouterProvider


class TestSearchReplaceFormat(unittest.TestCase):
    def setUp(self):
        self.fmt = SearchReplaceFormat()

    def test_single_match_apply(self):
        content = "hello world"
        result, desc = self.fmt.apply(content, old_text="world", new_text="there")
        self.assertEqual(result, "hello there")
        self.assertIn("search_replace", desc)

    def test_multi_match_replace_all(self):
        content = "aaa bbb aaa"
        result, desc = self.fmt.apply(content, old_text="aaa", new_text="ccc", replace_all=True)
        self.assertEqual(result, "ccc bbb ccc")
        self.assertIn("2", desc)

    def test_no_match_raises(self):
        with self.assertRaises(ValueError):
            self.fmt.apply("hello", old_text="xyz", new_text="abc")

    def test_multi_match_without_replace_all_raises(self):
        with self.assertRaises(ValueError):
            self.fmt.apply("aaa bbb aaa", old_text="aaa", new_text="x")

    def test_search_replace_blocks_apply(self):
        content = "alpha\nbeta\ngamma\n"
        blocks = (
            "<<<<<<< SEARCH\n"
            "beta\n"
            "=======\n"
            "delta\n"
            ">>>>>>> REPLACE\n"
        )
        result, desc = self.fmt.apply(content, blocks_text=blocks)
        self.assertEqual(result, "alpha\ndelta\ngamma\n")
        self.assertIn("blocks", desc)

    def test_invalid_python_after_replace_raises(self):
        content = "def f():\n    return 1\n"
        with self.assertRaises(ValueError):
            self.fmt.apply(
                content,
                old_text="def f():\n",
                new_text="def f(\n",
                file_path="demo.py",
            )


class TestWholeFileFormat(unittest.TestCase):
    def test_replaces_entire_content(self):
        fmt = WholeFileFormat()
        result, desc = fmt.apply("old content", new_text="new content")
        self.assertEqual(result, "new content")
        self.assertEqual(desc, "whole_file")


class TestUnifiedDiffFormat(unittest.TestCase):
    def setUp(self):
        self.fmt = UnifiedDiffFormat()

    def test_single_hunk_apply(self):
        content = "line1\nline2\nline3\n"
        diff = "--- a/demo.py\n+++ b/demo.py\n@@ -2,1 +2,1 @@\n-line2\n+replaced\n"
        result, desc = self.fmt.apply(content, diff_text=diff)
        self.assertEqual(result, "line1\nreplaced\nline3\n")
        self.assertIn("1 hunks", desc)

    def test_no_hunks_raises(self):
        with self.assertRaises(ValueError):
            self.fmt.apply("content", diff_text="no hunks here")

    def test_multiple_hunks_apply(self):
        content = "line1\nline2\nline3\nline4\n"
        diff = (
            "--- a/demo.py\n"
            "+++ b/demo.py\n"
            "@@ -2,1 +2,1 @@\n"
            "-line2\n"
            "+updated2\n"
            "@@ -4,1 +4,2 @@\n"
            "-line4\n"
            "+line4\n"
            "+line5\n"
        )
        result, _ = self.fmt.apply(content, diff_text=diff)
        self.assertEqual(result, "line1\nupdated2\nline3\nline4\nline5\n")

    def test_mismatched_context_raises(self):
        content = "line1\nline2\nline3\n"
        diff = "@@ -2,1 +2,1 @@\n-wrong\n+updated\n"
        with self.assertRaises(ValueError):
            self.fmt.apply(content, diff_text=diff)

    def test_invalid_python_after_diff_raises(self):
        content = "def f():\n    return 1\n"
        diff = (
            "@@ -1,2 +1,2 @@\n"
            "-def f():\n"
            "-    return 1\n"
            "+def f(\n"
            "+    return 1\n"
        )
        with self.assertRaises(ValueError):
            self.fmt.apply(content, diff_text=diff, file_path="demo.py")


class TestLineRangeFormat(unittest.TestCase):
    def setUp(self):
        self.fmt = LineRangeFormat()

    def test_valid_range(self):
        content = "line1\nline2\nline3\n"
        result, desc = self.fmt.apply(content, new_text="replaced\n", start_line=2, end_line=2)
        self.assertIn("replaced", result)
        self.assertIn("line1", result)
        self.assertIn("line3", result)

    def test_invalid_range_raises(self):
        content = "line1\nline2\n"
        with self.assertRaises(ValueError):
            self.fmt.apply(content, new_text="x", start_line=0, end_line=1)
        with self.assertRaises(ValueError):
            self.fmt.apply(content, new_text="x", start_line=1, end_line=99)


class TestSuggestFormatForModel(unittest.TestCase):
    def test_gpt5_returns_unified_diff(self):
        self.assertEqual(suggest_format_for_model("gpt-5"), "unified_diff")

    def test_llama_returns_whole_file(self):
        self.assertEqual(suggest_format_for_model("llama"), "whole_file")

    def test_unknown_returns_default(self):
        self.assertEqual(suggest_format_for_model("unknown_model"), "search_replace")

    def test_openrouter_claude_route_returns_search_replace(self):
        self.assertEqual(
            suggest_format_for_model(
                "anthropic/claude-sonnet-4-20250514",
                provider_name="openrouter",
            ),
            "search_replace",
        )


class TestRenderHelpers(unittest.TestCase):
    def test_render_search_replace_blocks_round_trip(self):
        original = "alpha\nbeta\ngamma\n"
        updated = "alpha\ndelta\ngamma\n"
        payload = render_search_replace_blocks(original, updated)
        rendered, _ = SearchReplaceFormat().apply(original, blocks_text=payload)
        self.assertEqual(rendered, updated)

    def test_render_unified_diff_round_trip(self):
        original = "alpha\nbeta\ngamma\n"
        updated = "alpha\ndelta\ngamma\n"
        payload = render_unified_diff(original, updated, file_path="demo.py")
        rendered, _ = UnifiedDiffFormat().apply(original, diff_text=payload)
        self.assertEqual(rendered, updated)

    def test_estimate_changed_lines_counts_replace_once(self):
        original = "a\nb\nc\n"
        updated = "a\nx\nc\n"
        self.assertEqual(estimate_changed_lines(original, updated), 1)

    def test_select_edit_format_uses_size_heuristic(self):
        small_before = "".join(f"line {idx}\n" for idx in range(4))
        small_after = small_before.replace("line 1\n", "line one\n")
        self.assertEqual(select_edit_format(small_before, small_after), "search_replace")

        medium_before = "".join(f"line {idx}\n" for idx in range(20))
        medium_after = "".join(
            f"line {idx} updated\n" if 5 <= idx < 15 else f"line {idx}\n"
            for idx in range(20)
        )
        self.assertEqual(select_edit_format(medium_before, medium_after), "unified_diff")

        large_before = "".join(f"line {idx}\n" for idx in range(60))
        large_after = "".join(f"new {idx}\n" for idx in range(60))
        self.assertEqual(select_edit_format(large_before, large_after), "whole_file")

    def test_provider_preference_is_respected(self):
        original = "alpha\nbeta\ngamma\n"
        updated = "alpha\ndelta\ngamma\n"
        self.assertEqual(
            select_edit_format(original, updated, provider_preference="unified_diff"),
            "unified_diff",
        )
        self.assertEqual(
            select_edit_format(
                "".join(f"line {idx}\n" for idx in range(10)),
                "".join(
                    f"line {idx} changed\n" if idx < 6 else f"line {idx}\n"
                    for idx in range(10)
                ),
                provider_preference="search_replace",
            ),
            "search_replace",
        )

    def test_whole_file_selection_logs(self):
        with self.assertLogs("poor_cli.edit_formats", level="WARNING") as logs:
            rendered = render_compact_edit("", "new file\n", is_new_file=True)
        self.assertEqual(rendered.format_name, "whole_file")
        self.assertTrue(any("whole_file" in entry for entry in logs.output))

    def test_compact_payload_is_smaller_than_full_rewrite(self):
        original = "".join(f"line {idx}\n" for idx in range(100))
        updated = original.replace("line 50\n", "line fifty\n")
        search_payload = render_search_replace_blocks(original, updated)
        diff_payload = render_unified_diff(original, updated, file_path="demo.py")
        self.assertLess(len(search_payload), len(updated))
        self.assertLess(len(diff_payload), len(updated))
        rendered = render_compact_edit(original, updated)
        self.assertEqual(rendered.format_name, "search_replace")


class TestGetFormat(unittest.TestCase):
    def test_valid_name(self):
        fmt = get_format("search_replace")
        self.assertIsInstance(fmt, SearchReplaceFormat)

    def test_invalid_name_raises(self):
        with self.assertRaises(ValueError):
            get_format("nonexistent_format")

    def test_search_replace_block_alias(self):
        fmt = get_format("search_replace_block")
        self.assertIsInstance(fmt, SearchReplaceFormat)


class TestProviderPreferredEditFormat(unittest.TestCase):
    def _provider(self, provider_cls, model_name):
        provider = provider_cls.__new__(provider_cls)
        provider.model_name = model_name
        return provider

    def test_openai_prefers_unified_diff(self):
        provider = self._provider(OpenAIProvider, "gpt-5")
        self.assertEqual(provider.preferred_edit_format(), "unified_diff")

    def test_anthropic_prefers_search_replace(self):
        provider = self._provider(AnthropicProvider, "claude-sonnet-4")
        self.assertEqual(provider.preferred_edit_format(), "search_replace")

    def test_gemini_prefers_search_replace(self):
        provider = self._provider(GeminiProvider, "gemini-2.5-pro")
        self.assertEqual(provider.preferred_edit_format(), "search_replace")

    def test_ollama_prefers_whole_file(self):
        provider = self._provider(OllamaProvider, "llama3.1")
        self.assertEqual(provider.preferred_edit_format(), "whole_file")

    def test_openrouter_prefers_routed_model_format(self):
        provider = self._provider(OpenRouterProvider, "openai/gpt-5")
        self.assertEqual(provider.preferred_edit_format(), "unified_diff")


if __name__ == "__main__":
    unittest.main()
