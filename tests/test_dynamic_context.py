"""Tests for cache-stable system instruction refresh."""

import unittest
from unittest.mock import MagicMock, patch


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
        core.config.tools.enable_git_tools = True
        core.config.plan_mode.enabled = False
        core.config.sandbox.default_preset = "workspace-write"
        core.provider = MagicMock()
        core._instruction_manager = MagicMock()
        core._instruction_manager._cache_key = "abc123"
        core._memory_manager = MagicMock()
        core._memory_manager.load_index.return_value = ""
        core._memory_manager.list_all.return_value = []
        core._repo_root = "/tmp/test"
        core._git_context_cache = None
        core._context_contract = MagicMock()
        return core

    @patch("poor_cli.core.build_tool_calling_system_instruction", return_value="new instruction")
    def test_first_call_returns_true(self, mock_build):
        core = self._make_core()
        self.assertTrue(core._refresh_system_context())
        core.provider.update_system_instruction.assert_called_once_with("new instruction")

    @patch("poor_cli.core.build_tool_calling_system_instruction", return_value="new instruction")
    def test_second_call_returns_false_when_content_unchanged(self, mock_build):
        core = self._make_core()
        core._refresh_system_context()
        self.assertFalse(core._refresh_system_context())

    @patch("poor_cli.core.build_tool_calling_system_instruction", side_effect=["same instruction", "same instruction"])
    def test_git_churn_does_not_trigger_rebuild_when_content_matches(self, mock_build):
        core = self._make_core()
        self.assertTrue(core._refresh_system_context())
        self.assertFalse(core._refresh_system_context())
        self.assertEqual(core.provider.update_system_instruction.call_count, 1)

    @patch("poor_cli.core.build_tool_calling_system_instruction", side_effect=["first", "second"])
    def test_content_change_triggers_rebuild(self, mock_build):
        core = self._make_core()
        core._refresh_system_context()
        self.assertTrue(core._refresh_system_context())
        self.assertEqual(core.provider.update_system_instruction.call_count, 2)

    def test_not_initialized_returns_false(self):
        from poor_cli.core import PoorCLICore

        core = object.__new__(PoorCLICore)
        core._initialized = False
        core.provider = None
        core.config = None
        self.assertFalse(core._refresh_system_context())
