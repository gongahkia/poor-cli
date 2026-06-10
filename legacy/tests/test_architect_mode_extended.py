"""Extended tests for architect/editor dual-model mode."""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from poor_cli.architect_mode import ArchitectConfig, ArchitectMode


class TestArchitectConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = ArchitectConfig()
        self.assertFalse(cfg.enabled)
        self.assertEqual(cfg.architect_provider, "")
        self.assertEqual(cfg.architect_model, "")
        self.assertEqual(cfg.editor_provider, "")
        self.assertEqual(cfg.editor_model, "")


class TestArchitectModeDisabled(unittest.TestCase):
    def test_not_enabled_without_providers(self):
        cfg = ArchitectConfig(enabled=True) # no providers set
        mode = ArchitectMode(cfg)
        self.assertFalse(mode.enabled)

    def test_not_enabled_without_architect(self):
        cfg = ArchitectConfig(enabled=True, editor_provider="gemini", editor_model="flash")
        mode = ArchitectMode(cfg)
        self.assertFalse(mode.enabled)

    def test_not_enabled_without_editor(self):
        cfg = ArchitectConfig(enabled=True, architect_provider="anthropic", architect_model="sonnet")
        mode = ArchitectMode(cfg)
        self.assertFalse(mode.enabled)

    def test_switch_to_architect_returns_false(self):
        cfg = ArchitectConfig()
        mode = ArchitectMode(cfg)
        core = MagicMock()
        result = asyncio.run(mode.switch_to_architect(core))
        self.assertFalse(result)

    def test_switch_to_editor_returns_false(self):
        cfg = ArchitectConfig()
        mode = ArchitectMode(cfg)
        core = MagicMock()
        result = asyncio.run(mode.switch_to_editor(core, "plan text"))
        self.assertFalse(result)


class TestArchitectModeEnabled(unittest.TestCase):
    def _make_mode(self):
        cfg = ArchitectConfig(
            enabled=True,
            architect_provider="anthropic",
            architect_model="claude-sonnet-4",
            editor_provider="gemini",
            editor_model="gemini-2.5-flash",
        )
        lifecycle = AsyncMock()
        return ArchitectMode(cfg, lifecycle_service=lifecycle), lifecycle

    def test_enabled(self):
        mode, _ = self._make_mode()
        self.assertTrue(mode.enabled)

    def test_initial_phase_is_architect(self):
        mode, _ = self._make_mode()
        self.assertEqual(mode.phase, "architect")

    def test_switch_to_editor(self):
        mode, lifecycle = self._make_mode()
        core = MagicMock()
        result = asyncio.run(mode.switch_to_editor(core, "## Plan\nStep 1: read files"))
        self.assertTrue(result)
        self.assertEqual(mode.phase, "editor")
        lifecycle.switch_provider.assert_called_with("gemini", "gemini-2.5-flash")

    def test_switch_to_editor_stores_plan(self):
        mode, _ = self._make_mode()
        core = MagicMock()
        asyncio.run(mode.switch_to_editor(core, "my plan"))
        self.assertIn("my plan", mode.get_plan_prefix())

    def test_switch_to_architect(self):
        mode, lifecycle = self._make_mode()
        core = MagicMock()
        asyncio.run(mode.switch_to_architect(core))
        self.assertEqual(mode.phase, "architect")
        lifecycle.switch_provider.assert_called_with("anthropic", "claude-sonnet-4")

    def test_reset_clears_plan(self):
        mode, _ = self._make_mode()
        core = MagicMock()
        asyncio.run(mode.switch_to_editor(core, "some plan"))
        self.assertNotEqual(mode.get_plan_prefix(), "")
        asyncio.run(mode.reset_to_architect(core))
        self.assertEqual(mode.get_plan_prefix(), "")
        self.assertEqual(mode.phase, "architect")

    def test_plan_prefix_contains_plan_text(self):
        mode, _ = self._make_mode()
        core = MagicMock()
        asyncio.run(mode.switch_to_editor(core, "1. Read files\n2. Edit code"))
        prefix = mode.get_plan_prefix()
        self.assertIn("1. Read files", prefix)
        self.assertIn("Plan from architect", prefix)

    def test_plan_prefix_empty_without_plan(self):
        mode, _ = self._make_mode()
        self.assertEqual(mode.get_plan_prefix(), "")


class TestPlanDetection(unittest.TestCase):
    def _make_mode(self):
        cfg = ArchitectConfig(enabled=True, architect_provider="a", architect_model="b", editor_provider="c", editor_model="d")
        return ArchitectMode(cfg)

    def test_detects_plan_header(self):
        mode = self._make_mode()
        self.assertTrue(mode.should_switch_to_editor("## Plan\nStep 1: do stuff"))

    def test_detects_step_list(self):
        mode = self._make_mode()
        self.assertTrue(mode.should_switch_to_editor("Here's my approach:\nStep 1: read the code"))

    def test_detects_numbered_list(self):
        mode = self._make_mode()
        self.assertTrue(mode.should_switch_to_editor("1. Read the file\n2. Edit the function"))

    def test_detects_checkbox(self):
        mode = self._make_mode()
        self.assertTrue(mode.should_switch_to_editor("- [ ] Implement feature A"))

    def test_no_plan_in_simple_answer(self):
        mode = self._make_mode()
        self.assertFalse(mode.should_switch_to_editor("The answer is 42"))

    def test_no_plan_in_code_block(self):
        mode = self._make_mode()
        self.assertFalse(mode.should_switch_to_editor("```python\ndef foo(): pass\n```"))

    def test_only_triggers_in_architect_phase(self):
        mode = self._make_mode()
        mode._phase = "editor"
        self.assertFalse(mode.should_switch_to_editor("## Plan\nStep 1: stuff"))


class TestFormatStatus(unittest.TestCase):
    def test_status_shape(self):
        cfg = ArchitectConfig(enabled=True, architect_provider="anthropic", architect_model="sonnet", editor_provider="gemini", editor_model="flash")
        mode = ArchitectMode(cfg)
        status = mode.format_status()
        self.assertIn("enabled", status)
        self.assertIn("phase", status)
        self.assertIn("architect", status)
        self.assertIn("editor", status)
        self.assertIn("has_plan", status)
        self.assertTrue(status["enabled"])
        self.assertEqual(status["phase"], "architect")
        self.assertFalse(status["has_plan"])

    def test_switch_failure_handled(self):
        cfg = ArchitectConfig(enabled=True, architect_provider="a", architect_model="b", editor_provider="c", editor_model="d")
        lifecycle = AsyncMock()
        lifecycle.switch_provider.side_effect = RuntimeError("provider not found")
        mode = ArchitectMode(cfg, lifecycle_service=lifecycle)
        core = MagicMock()
        result = asyncio.run(mode.switch_to_editor(core, "plan"))
        self.assertFalse(result) # graceful failure


if __name__ == "__main__":
    unittest.main()
