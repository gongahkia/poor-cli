"""Tests for per-turn dynamic system context refresh."""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock


class TestRefreshSystemContext(unittest.TestCase):
    def _make_core(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core._initialized = True
        core._system_context_hash = None
        core._system_instruction = "old instruction"
        core.config = MagicMock()
        core.config.economy.terse_system_prompt = False
        core.config.economy.prefer_batched_reads = False
        core.config.model.provider = "openai"
        core.provider = MagicMock()
        core._instruction_manager = MagicMock()
        core._instruction_manager._cache_key = "abc123"
        core._memory_manager = MagicMock()
        core._memory_manager.load_index.return_value = ""
        core._repo_root = "/tmp/test"
        return core

    @patch("subprocess.check_output")
    @patch("poor_cli.core.build_tool_calling_system_instruction", return_value="new instruction")
    def test_first_call_returns_true(self, mock_build, mock_sub):
        mock_sub.return_value = "abc123\n"
        core = self._make_core()
        self.assertTrue(core._refresh_system_context())
        core.provider.update_system_instruction.assert_called_once()

    @patch("subprocess.check_output")
    @patch("poor_cli.core.build_tool_calling_system_instruction", return_value="new instruction")
    def test_second_call_returns_false(self, mock_build, mock_sub):
        mock_sub.return_value = "abc123\n"
        core = self._make_core()
        core._refresh_system_context()
        self.assertFalse(core._refresh_system_context())

    @patch("subprocess.check_output")
    @patch("poor_cli.core.build_tool_calling_system_instruction", return_value="rebuilt")
    def test_head_change_triggers_rebuild(self, mock_build, mock_sub):
        core = self._make_core()
        mock_sub.return_value = "aaa\n"
        core._refresh_system_context()
        mock_sub.return_value = "bbb\n"
        self.assertTrue(core._refresh_system_context())
        self.assertEqual(core.provider.update_system_instruction.call_count, 2)

    def test_not_initialized_returns_false(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core._initialized = False
        core.provider = None
        core.config = None
        self.assertFalse(core._refresh_system_context())
