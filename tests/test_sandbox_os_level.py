"""Tests for OS-level sandbox, context compression, sub-agent archetypes, and feedback loop."""
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


class TestOSLevelSandbox(unittest.TestCase):
    """Test macOS sandbox-exec profile generation."""

    def test_read_only_profile_denies_writes(self):
        from poor_cli.sandbox import build_seatbelt_profile
        profile = build_seatbelt_profile("read-only")
        self.assertIn("(deny file-write*)", profile)
        self.assertIn("(deny network*)", profile)
        self.assertIn("(allow file-read*)", profile)

    def test_workspace_write_allows_workspace(self):
        from poor_cli.sandbox import build_seatbelt_profile
        ws = Path("/tmp/test-workspace")
        profile = build_seatbelt_profile("workspace-write", workspace=ws)
        self.assertIn(str(ws.resolve()), profile)
        self.assertIn("(deny network*)", profile)

    def test_full_access_allows_all(self):
        from poor_cli.sandbox import build_seatbelt_profile
        profile = build_seatbelt_profile("full-access")
        self.assertIn("(allow default)", profile)

    def test_review_only_same_as_read_only(self):
        from poor_cli.sandbox import build_seatbelt_profile
        profile = build_seatbelt_profile("review-only")
        self.assertIn("(deny file-write*)", profile)

    def test_sandboxed_command_returns_argv(self):
        from poor_cli.sandbox import os_sandbox_available, sandboxed_command
        if not os_sandbox_available():
            result = sandboxed_command("echo hello", "read-only")
            self.assertEqual(result, ["bash", "-c", "echo hello"])
        else:
            result = sandboxed_command("echo hello", "read-only")
            self.assertEqual(result[0], "sandbox-exec")


class TestContextCompressor(unittest.TestCase):
    """Test context compression with extractive and LLM methods."""

    def test_extractive_preserves_recent(self):
        from poor_cli.context_compressor import ContextCompressor
        compressor = ContextCompressor()
        config = MagicMock()
        config.enabled = True
        config.compress_after_turns = 5
        config.preserve_recent_turns = 3
        history = [{"role": "user", "content": f"msg {i}"} for i in range(10)]
        result = compressor.compress(history, config)
        self.assertEqual(len(result), 4) # 1 summary + 3 recent
        self.assertIn("[COMPRESSED CONTEXT]", result[0]["content"])
        self.assertEqual(result[0]["role"], "user") # not "system"

    def test_no_compress_below_threshold(self):
        from poor_cli.context_compressor import ContextCompressor
        compressor = ContextCompressor()
        config = MagicMock()
        config.enabled = True
        config.compress_after_turns = 20
        history = [{"role": "user", "content": f"msg {i}"} for i in range(5)]
        result = compressor.compress(history, config)
        self.assertEqual(len(result), 5)


class TestSubAgentArchetypes(unittest.TestCase):
    """Test sub-agent archetype configuration."""

    def test_research_archetype_has_read_only_tools(self):
        from poor_cli.sub_agent import _ARCHETYPE_CONFIGS
        cfg = _ARCHETYPE_CONFIGS["research"]
        self.assertIn("read_file", cfg["allowed_tools"])
        self.assertIn("grep_files", cfg["allowed_tools"])
        self.assertNotIn("write_file", cfg.get("allowed_tools", set()))
        self.assertNotIn("edit_file", cfg.get("allowed_tools", set()))

    def test_code_archetype_allows_all(self):
        from poor_cli.sub_agent import _ARCHETYPE_CONFIGS
        cfg = _ARCHETYPE_CONFIGS["code"]
        self.assertIsNone(cfg["allowed_tools"])

    def test_test_archetype_includes_run_tests(self):
        from poor_cli.sub_agent import _ARCHETYPE_CONFIGS
        cfg = _ARCHETYPE_CONFIGS["test"]
        self.assertIn("run_tests", cfg["allowed_tools"])
        self.assertIn("bash", cfg["allowed_tools"])

    def test_review_archetype_read_only(self):
        from poor_cli.sub_agent import _ARCHETYPE_CONFIGS
        cfg = _ARCHETYPE_CONFIGS["review"]
        self.assertNotIn("write_file", cfg.get("allowed_tools", set()))
        self.assertIn("git_diff", cfg["allowed_tools"])

    def test_all_archetypes_have_system_prompt(self):
        from poor_cli.sub_agent import _ARCHETYPE_CONFIGS
        for name, cfg in _ARCHETYPE_CONFIGS.items():
            self.assertIn("system_prompt", cfg, f"archetype '{name}' missing system_prompt")
            self.assertTrue(len(cfg["system_prompt"]) > 20, f"archetype '{name}' system_prompt too short")


class TestFeedbackLoopToggle(unittest.TestCase):
    """Test feedback loop toggle function."""

    def test_toggle_enables(self):
        from poor_cli.feedback_loop import toggle_feedback_loop
        config = MagicMock()
        config.agentic = MagicMock()
        config.agentic.auto_lint = False
        config._auto_feedback_enabled = False
        result = toggle_feedback_loop(config)
        self.assertIn("enabled", result)
        self.assertTrue(config.agentic.auto_lint)

    def test_toggle_disables(self):
        from poor_cli.feedback_loop import toggle_feedback_loop
        config = MagicMock()
        config.agentic = MagicMock()
        config.agentic.auto_lint = True
        config._auto_feedback_enabled = True
        result = toggle_feedback_loop(config)
        self.assertIn("disabled", result)

    def test_explicit_enable(self):
        from poor_cli.feedback_loop import toggle_feedback_loop
        config = MagicMock()
        config.agentic = MagicMock()
        config.agentic.auto_lint = False
        result = toggle_feedback_loop(config, enable=True)
        self.assertIn("enabled", result)

    def test_project_detection(self):
        from poor_cli.feedback_loop import detect_project
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            detection = detect_project(tmpdir)
            self.assertEqual(detection.project_type, "unknown")


class TestContextProviders(unittest.TestCase):
    """Test @-mention context provider parsing."""

    def test_mention_regex(self):
        from poor_cli.context_providers import _MENTION_RE
        matches = _MENTION_RE.findall("check @diff and @codebase search terms")
        names = [m[0] for m in matches]
        self.assertIn("diff", names)
        self.assertIn("codebase", names)

    def test_no_mentions(self):
        from poor_cli.context_providers import _MENTION_RE
        matches = _MENTION_RE.findall("plain message with no mentions")
        self.assertEqual(len(matches), 0)

    def test_file_mentions_not_captured(self):
        from poor_cli.context_providers import _MENTION_RE
        matches = _MENTION_RE.findall("check @path/to/file.py")
        # @path/to/file.py should NOT match typed providers
        names = [m[0] for m in matches]
        self.assertNotIn("path/to/file.py", names)


class TestArchitectMode(unittest.TestCase):
    """Test architect/editor dual-model mode."""

    def test_disabled_by_default(self):
        from poor_cli.architect_mode import ArchitectConfig, ArchitectMode
        cfg = ArchitectConfig()
        mode = ArchitectMode(cfg)
        self.assertFalse(mode.enabled)

    def test_enabled_with_both_models(self):
        from poor_cli.architect_mode import ArchitectConfig, ArchitectMode
        cfg = ArchitectConfig(enabled=True, architect_provider="anthropic", architect_model="claude-sonnet-4", editor_provider="gemini", editor_model="gemini-2.5-flash")
        mode = ArchitectMode(cfg)
        self.assertTrue(mode.enabled)
        self.assertEqual(mode.phase, "architect")

    def test_plan_detection_heuristic(self):
        from poor_cli.architect_mode import ArchitectConfig, ArchitectMode
        cfg = ArchitectConfig(enabled=True, architect_provider="a", architect_model="b", editor_provider="c", editor_model="d")
        mode = ArchitectMode(cfg)
        self.assertTrue(mode.should_switch_to_editor("## Plan\nStep 1: Read files"))
        self.assertFalse(mode.should_switch_to_editor("The answer is 42"))

    def test_plan_prefix_empty_without_plan(self):
        from poor_cli.architect_mode import ArchitectConfig, ArchitectMode
        cfg = ArchitectConfig(enabled=True, architect_provider="a", architect_model="b", editor_provider="c", editor_model="d")
        mode = ArchitectMode(cfg)
        self.assertEqual(mode.get_plan_prefix(), "")


if __name__ == "__main__":
    unittest.main()
