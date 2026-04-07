"""tests for poor_cli.edit_formats module."""

import unittest
from poor_cli.edit_formats import (
    SearchReplaceFormat,
    WholeFileFormat,
    UnifiedDiffFormat,
    LineRangeFormat,
    suggest_format_for_model,
    get_format,
)


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
        diff = "@@ -2,1 +2,1 @@\n-line2\n+replaced\n"
        result, desc = self.fmt.apply(content, diff_text=diff)
        self.assertIn("replaced", result)
        self.assertIn("1 hunks", desc)

    def test_no_hunks_raises(self):
        with self.assertRaises(ValueError):
            self.fmt.apply("content", diff_text="no hunks here")


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
    def test_gpt5_returns_search_replace(self):
        self.assertEqual(suggest_format_for_model("gpt-5"), "search_replace")

    def test_llama_returns_whole_file(self):
        self.assertEqual(suggest_format_for_model("llama"), "whole_file")

    def test_unknown_returns_default(self):
        self.assertEqual(suggest_format_for_model("unknown_model"), "search_replace")


class TestGetFormat(unittest.TestCase):
    def test_valid_name(self):
        fmt = get_format("search_replace")
        self.assertIsInstance(fmt, SearchReplaceFormat)

    def test_invalid_name_raises(self):
        with self.assertRaises(ValueError):
            get_format("nonexistent_format")


if __name__ == "__main__":
    unittest.main()
