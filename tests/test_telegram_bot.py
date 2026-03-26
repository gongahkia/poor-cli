"""tests for poor_cli.telegram_bot and telegram_formatter modules."""

import unittest
from poor_cli.telegram_formatter import (
    escape_markdown_v2,
    format_tool_call,
    format_tool_result,
    paginate,
    format_streaming_chunk,
    TELEGRAM_MSG_LIMIT,
)


class TestEscapeMarkdownV2(unittest.TestCase):
    def test_escapes_special_chars(self):
        result = escape_markdown_v2("hello_world *bold* [link](url)")
        self.assertIn(r"\_", result)
        self.assertIn(r"\*", result)
        self.assertIn(r"\[", result)

    def test_plain_text_unchanged(self):
        self.assertEqual(escape_markdown_v2("hello world"), "hello world")


class TestFormatToolCall(unittest.TestCase):
    def test_format_basic(self):
        result = format_tool_call("read_file", {"path": "/tmp/foo.py"})
        self.assertIn("read_file", result)
        self.assertIn("/tmp/foo.py", result)

    def test_truncates_long_args(self):
        result = format_tool_call("bash", {"command": "x" * 200})
        self.assertIn("...", result)


class TestFormatToolResult(unittest.TestCase):
    def test_success(self):
        result = format_tool_result("read_file", "file contents here", success=True)
        self.assertIn("✅", result)
        self.assertIn("read_file", result)

    def test_failure(self):
        result = format_tool_result("bash", "error occurred", success=False)
        self.assertIn("❌", result)


class TestPaginate(unittest.TestCase):
    def test_short_text_single_page(self):
        pages = paginate("hello")
        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0], "hello")

    def test_long_text_multiple_pages(self):
        text = "a" * (TELEGRAM_MSG_LIMIT * 2 + 100)
        pages = paginate(text)
        self.assertGreater(len(pages), 1)
        reassembled = "".join(pages)
        self.assertEqual(len(reassembled), len(text))

    def test_splits_on_newline(self):
        lines = ["line " + str(i) for i in range(1000)]
        text = "\n".join(lines)
        pages = paginate(text)
        for page in pages:
            self.assertLessEqual(len(page), TELEGRAM_MSG_LIMIT)


class TestStreamingChunk(unittest.TestCase):
    def test_appends_chunk(self):
        result = format_streaming_chunk("hello ", "world")
        self.assertEqual(result, "hello world")

    def test_truncates_overflow(self):
        big = "x" * (TELEGRAM_MSG_LIMIT + 500)
        result = format_streaming_chunk(big, "more")
        self.assertLessEqual(len(result), TELEGRAM_MSG_LIMIT)


class TestTelegramBotImport(unittest.TestCase):
    def test_module_loads(self):
        """verify the module loads even without python-telegram-bot."""
        import poor_cli.telegram_bot as tb
        self.assertTrue(hasattr(tb, "PoorCLITelegramBot"))

    def test_bot_raises_without_telegram(self):
        import poor_cli.telegram_bot as tb
        if not tb.TELEGRAM_AVAILABLE:
            from poor_cli.exceptions import ConfigurationError
            with self.assertRaises(ConfigurationError):
                tb.PoorCLITelegramBot(token="test")


if __name__ == "__main__":
    unittest.main()
