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
        core._perf_span_history = []
        core._active_turn_diagnostics = None
        core._tone_cache_index_hash = ""
        core._tone_cache_suffix = ""
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
        core.config.model.model_name = "gpt-5.2"
        self.assertTrue(core._refresh_system_context())
        self.assertEqual(core.provider.update_system_instruction.call_count, 2)

    def test_not_initialized_returns_false(self):
        from poor_cli.core import PoorCLICore

        core = object.__new__(PoorCLICore)
        core._initialized = False
        core.provider = None
        core.config = None
        self.assertFalse(core._refresh_system_context())

    def test_tone_suffix_cache_reuses_result_for_same_memory_index(self):
        core = self._make_core()
        detector = MagicMock(return_value="\n## Response Tone\nShip fast.\n")
        core._memory_manager.list_all.return_value = [MagicMock(content="prefer concise outputs")]

        first = core._tone_suffix_for_memory_index("memory-index-a", detector)
        second = core._tone_suffix_for_memory_index("memory-index-a", detector)

        self.assertEqual(first, second)
        self.assertEqual(core._memory_manager.list_all.call_count, 1)
        self.assertEqual(detector.call_count, 1)

    def test_tone_suffix_cache_refreshes_on_memory_index_change(self):
        core = self._make_core()
        detector = MagicMock(return_value="")

        core._tone_suffix_for_memory_index("memory-index-a", detector)
        core._tone_suffix_for_memory_index("memory-index-b", detector)

        self.assertEqual(core._memory_manager.list_all.call_count, 2)
        self.assertEqual(detector.call_count, 2)
