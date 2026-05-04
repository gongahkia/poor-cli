"""Tests for config dataclass defaults and validation."""
import unittest

from poor_cli.config import (
    AgenticConfig,
    Config,
    ModelConfig,
    HistoryConfig,
    SecurityConfig,
    CheckpointConfig,
    ContextConfig,
    DiffReviewConfig,
)
from poor_cli.economy import EconomyConfig


class TestAgenticConfigDefaults(unittest.TestCase):
    def test_max_iterations(self):
        cfg = AgenticConfig()
        self.assertEqual(cfg.max_iterations, 25)

    def test_max_parallel_tool_calls(self):
        cfg = AgenticConfig()
        self.assertEqual(cfg.max_parallel_tool_calls, 6)

    def test_auto_lint_default_true(self):
        cfg = AgenticConfig()
        self.assertTrue(cfg.auto_lint)

    def test_auto_lint_timeout(self):
        cfg = AgenticConfig()
        self.assertEqual(cfg.auto_lint_timeout, 30)

    def test_sub_agent_max_depth(self):
        cfg = AgenticConfig()
        self.assertEqual(cfg.sub_agent_max_depth, 2)

    def test_sub_agent_max_iterations(self):
        cfg = AgenticConfig()
        self.assertEqual(cfg.sub_agent_max_iterations, 10)

    def test_sub_agent_timeout(self):
        cfg = AgenticConfig()
        self.assertAlmostEqual(cfg.sub_agent_timeout, 120.0)

    def test_sub_agent_token_budgets(self):
        cfg = AgenticConfig()
        self.assertEqual(cfg.sub_agent_max_input_tokens, 40000)
        self.assertEqual(cfg.sub_agent_max_output_tokens, 12000)

    def test_sub_agent_cost_budget(self):
        cfg = AgenticConfig()
        self.assertAlmostEqual(cfg.sub_agent_max_cost_usd, 0.50)

    def test_architect_mode_default_false(self):
        cfg = AgenticConfig()
        self.assertFalse(cfg.architect_mode)

    def test_architect_provider_default_empty(self):
        cfg = AgenticConfig()
        self.assertEqual(cfg.architect_provider, "")

    def test_deny_patterns(self):
        cfg = AgenticConfig()
        self.assertIn("rm -rf", cfg.deny_patterns)
        self.assertIn("sudo", cfg.deny_patterns)

    def test_auto_approve_tools(self):
        cfg = AgenticConfig()
        self.assertIn("read_file", cfg.auto_approve_tools)
        self.assertIn("glob_files", cfg.auto_approve_tools)

    def test_path_scoped_approval_default(self):
        cfg = AgenticConfig()
        self.assertTrue(cfg.path_scoped_approval)

    def test_auto_approve_edits_default_false(self):
        cfg = AgenticConfig()
        self.assertFalse(cfg.auto_approve_edits)

    def test_context_pressure_ratios(self):
        cfg = AgenticConfig()
        self.assertAlmostEqual(cfg.context_pressure_stop_ratio, 0.2)
        self.assertAlmostEqual(cfg.context_pressure_warn_ratio, 0.5)


class TestEconomyConfigDefaults(unittest.TestCase):
    def test_preset_default(self):
        cfg = EconomyConfig()
        self.assertEqual(cfg.preset, "balanced")

    def test_response_cache_default(self):
        cfg = EconomyConfig()
        self.assertFalse(cfg.response_cache)


class TestContextConfigDefaults(unittest.TestCase):
    def test_safe_pretokenization_default_false(self):
        cfg = ContextConfig()
        self.assertFalse(cfg.safe_pretokenization)


class TestDiffReviewConfigDefaults(unittest.TestCase):
    def test_requires_diff_preview_by_default(self):
        cfg = DiffReviewConfig()
        self.assertTrue(cfg.require_diff_preview)
        self.assertFalse(cfg.bypass_diff_preview)


class TestModelConfigDefaults(unittest.TestCase):
    def test_default_provider(self):
        cfg = ModelConfig()
        self.assertIn(cfg.provider, ("gemini", "openai")) # varies by config

    def test_default_model_is_set(self):
        cfg = ModelConfig()
        self.assertTrue(len(cfg.model_name) > 0)


class TestConfigToDict(unittest.TestCase):
    def test_to_dict_excludes_api_keys(self):
        cfg = Config()
        cfg.api_keys = {"openai": "sk-secret123"}
        d = cfg.to_dict()
        self.assertNotIn("api_keys", d)

    def test_to_dict_includes_model(self):
        cfg = Config()
        d = cfg.to_dict()
        self.assertIn("model", d)
        self.assertIn("provider", d["model"])

    def test_to_dict_includes_security(self):
        cfg = Config()
        d = cfg.to_dict()
        self.assertIn("security", d)

    def test_to_dict_includes_context_safe_pretokenization(self):
        cfg = Config()
        d = cfg.to_dict()
        self.assertFalse(d["context"]["safe_pretokenization"])


class TestSecurityConfigDefaults(unittest.TestCase):
    def test_permission_mode_default(self):
        cfg = SecurityConfig()
        self.assertEqual(cfg.permission_mode, "default")

    def test_trusted_workspace_default(self):
        cfg = SecurityConfig()
        self.assertTrue(cfg.enforce_trusted_workspace)


class TestCheckpointConfigDefaults(unittest.TestCase):
    def test_enabled_default(self):
        cfg = CheckpointConfig()
        self.assertTrue(cfg.enabled)

    def test_auto_checkpoint_default(self):
        cfg = CheckpointConfig()
        self.assertTrue(cfg.auto_checkpoint_before_write)


class TestHistoryConfigDefaults(unittest.TestCase):
    def test_auto_save_default(self):
        cfg = HistoryConfig()
        self.assertTrue(cfg.auto_save)

    def test_max_turns_default(self):
        cfg = HistoryConfig()
        self.assertEqual(cfg.max_turns, 50)


if __name__ == "__main__":
    unittest.main()
