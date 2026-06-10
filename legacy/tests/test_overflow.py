"""Tests for tool result overflow to temp files."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestOverflowToolResult(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.overflow_dir = Path(self.tmpdir) / ".poor-cli" / "overflow"

    def _make_core(self, overflow_threshold=30000, overflow_dir=None):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.config = MagicMock()
        core.config.agentic.overflow_threshold_chars = overflow_threshold
        core.config.agentic.overflow_dir = overflow_dir or str(self.overflow_dir)
        core.config.agentic.max_tool_result_chars_per_turn = 60000
        return core

    def test_large_result_overflows(self):
        core = self._make_core(overflow_threshold=100)
        large_text = "x" * 500
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            results = [{"id": "1", "name": "read_file", "result": large_text}]
            bounded, info = core._apply_tool_result_budget(results)
        self.assertEqual(info["overflowCount"], 1)
        ref = str(bounded[0]["result"])
        self.assertIn("Full result saved to", ref)
        self.assertIn("500 chars", ref)

    def test_small_result_not_overflowed(self):
        core = self._make_core(overflow_threshold=1000)
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            results = [{"id": "1", "name": "read_file", "result": "small"}]
            bounded, info = core._apply_tool_result_budget(results)
        self.assertEqual(info["overflowCount"], 0)
        self.assertEqual(bounded[0]["result"], "small")

    def test_overflow_file_contains_full_text(self):
        core = self._make_core(overflow_threshold=100)
        large_text = "y" * 500
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            ref = core._overflow_tool_result(large_text)
        files = list(self.overflow_dir.glob("*.txt"))
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].read_text(), large_text)

    def test_budget_still_applies_after_overflow(self):
        core = self._make_core(overflow_threshold=50000)
        core.config.agentic.max_tool_result_chars_per_turn = 1000
        results = [
            {"id": "1", "name": "read_file", "result": "a" * 800},
            {"id": "2", "name": "read_file", "result": "b" * 800},
        ]
        with patch("pathlib.Path.cwd", return_value=Path(self.tmpdir)):
            bounded, info = core._apply_tool_result_budget(results)
        self.assertEqual(info["truncatedCount"], 1)
