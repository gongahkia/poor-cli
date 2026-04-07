"""Extended tests for context compression (extractive + LLM)."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from poor_cli.context_compressor import ContextCompressor


class TestExtractiveCompression(unittest.TestCase):
    def _make_config(self, enabled=True, threshold=5, preserve=3):
        cfg = MagicMock()
        cfg.enabled = enabled
        cfg.compress_after_turns = threshold
        cfg.preserve_recent_turns = preserve
        return cfg

    def test_tools_used_extracted(self):
        c = ContextCompressor()
        turns = [{"role": "assistant", "content": "I used read_file to check the code"}]
        summary = c._summarize_turns(turns)
        self.assertIn("read_file", summary)

    def test_file_paths_extracted(self):
        c = ContextCompressor()
        turns = [{"role": "assistant", "content": "Modified /src/main.py and /src/utils.py"}]
        summary = c._summarize_turns(turns)
        self.assertIn("/src/main.py", summary)
        self.assertIn("/src/utils.py", summary)

    def test_decisions_extracted(self):
        c = ContextCompressor()
        turns = [{"role": "assistant", "content": "I decided to use a HashMap for the cache"}]
        summary = c._summarize_turns(turns)
        self.assertIn("decided", summary.lower())

    def test_user_intents_captured(self):
        c = ContextCompressor()
        turns = [{"role": "user", "content": "Please refactor the auth module"}]
        summary = c._summarize_turns(turns)
        self.assertIn("refactor the auth module", summary)

    def test_assistant_only_no_user_intents(self):
        c = ContextCompressor()
        turns = [{"role": "assistant", "content": "All done with the task"}] * 5
        summary = c._summarize_turns(turns)
        self.assertIn("[COMPRESSED CONTEXT]", summary)
        self.assertNotIn("user intents", summary)

    def test_empty_content_skipped(self):
        c = ContextCompressor()
        turns = [{"role": "user", "content": ""}, {"role": "user", "content": None}]
        summary = c._summarize_turns(turns)
        self.assertIn("[COMPRESSED CONTEXT]", summary)

    def test_turn_count_in_summary(self):
        c = ContextCompressor()
        turns = [{"role": "user", "content": f"Message {i} with enough content"} for i in range(7)]
        summary = c._summarize_turns(turns)
        self.assertIn("7 turns compressed", summary)

    def test_preserve_recent_count(self):
        c = ContextCompressor()
        cfg = self._make_config(threshold=5, preserve=4)
        history = [{"role": "user", "content": f"msg {i} is long enough"} for i in range(10)]
        result = c.compress(history, cfg)
        self.assertEqual(len(result), 5) # 1 summary + 4 preserved

    def test_disabled_returns_original(self):
        c = ContextCompressor()
        cfg = self._make_config(enabled=False)
        history = [{"role": "user", "content": "msg"}] * 20
        result = c.compress(history, cfg)
        self.assertEqual(len(result), 20)

    def test_below_threshold_returns_original(self):
        c = ContextCompressor()
        cfg = self._make_config(threshold=100)
        history = [{"role": "user", "content": "msg"}] * 10
        result = c.compress(history, cfg)
        self.assertEqual(len(result), 10)

    def test_file_paths_capped_at_20(self):
        c = ContextCompressor()
        paths = " ".join(f"/path/to/file{i}.py" for i in range(30))
        turns = [{"role": "assistant", "content": paths}]
        summary = c._summarize_turns(turns)
        path_count = summary.count("/path/to/")
        self.assertLessEqual(path_count, 20)

    def test_user_intents_capped_at_10(self):
        c = ContextCompressor()
        turns = [{"role": "user", "content": f"Intent number {i} with enough length"} for i in range(15)]
        summary = c._summarize_turns(turns)
        # count semicolons in user intents line (separators between intents)
        for line in summary.splitlines():
            if line.startswith("user intents:"):
                self.assertLessEqual(line.count(";"), 9) # 10 items = 9 separators


class TestLLMCompression(unittest.TestCase):
    def test_llm_compression_uses_provider(self):
        c = ContextCompressor()
        provider = AsyncMock()
        provider.send_message.return_value = MagicMock(content="Summary of conversation")
        cfg = MagicMock()
        cfg.enabled = True
        cfg.compress_after_turns = 3
        cfg.preserve_recent_turns = 2
        history = [{"role": "user", "content": f"msg {i} long enough"} for i in range(8)]
        result = asyncio.run(c.compress_with_llm(history, cfg, provider))
        provider.send_message.assert_called_once()
        self.assertIn("Summary of conversation", result[0]["content"])

    def test_llm_fallback_on_error(self):
        c = ContextCompressor()
        provider = AsyncMock()
        provider.send_message.side_effect = RuntimeError("API down")
        cfg = MagicMock()
        cfg.enabled = True
        cfg.compress_after_turns = 3
        cfg.preserve_recent_turns = 2
        history = [{"role": "user", "content": f"msg {i} long enough"} for i in range(8)]
        result = asyncio.run(c.compress_with_llm(history, cfg, provider))
        # should fall back to extractive
        self.assertIn("[COMPRESSED CONTEXT]", result[0]["content"])

    def test_llm_below_threshold_returns_original(self):
        c = ContextCompressor()
        provider = AsyncMock()
        cfg = MagicMock()
        cfg.enabled = True
        cfg.compress_after_turns = 100
        cfg.preserve_recent_turns = 2
        history = [{"role": "user", "content": "short"}] * 5
        result = asyncio.run(c.compress_with_llm(history, cfg, provider))
        self.assertEqual(len(result), 5)
        provider.send_message.assert_not_called()

    def test_llm_empty_response_falls_back(self):
        c = ContextCompressor()
        provider = AsyncMock()
        provider.send_message.return_value = MagicMock(content="")
        cfg = MagicMock()
        cfg.enabled = True
        cfg.compress_after_turns = 3
        cfg.preserve_recent_turns = 2
        history = [{"role": "user", "content": f"msg {i} with content"} for i in range(8)]
        result = asyncio.run(c.compress_with_llm(history, cfg, provider))
        # empty LLM response triggers extractive fallback
        self.assertIn("[COMPRESSED CONTEXT]", result[0]["content"])


if __name__ == "__main__":
    unittest.main()
