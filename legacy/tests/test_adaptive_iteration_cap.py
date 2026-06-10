"""Tests for adaptive iteration cap via context pressure."""

import unittest
from unittest.mock import MagicMock
from poor_cli.providers.base import ProviderCapabilities


class TestContextPressure(unittest.TestCase):
    def _make_core(self, max_ctx=100000, history_chars=0, stop_ratio=0.2, warn_ratio=0.5):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.provider = MagicMock()
        core.provider.get_capabilities.return_value = ProviderCapabilities(max_context_tokens=max_ctx)
        fake_history = [{"role": "user", "content": "x" * history_chars}]
        core.provider.get_history.return_value = fake_history
        core.config = MagicMock()
        core.config.agentic.context_pressure_stop_ratio = stop_ratio
        core.config.agentic.context_pressure_warn_ratio = warn_ratio
        return core

    def test_low_usage_returns_none(self):
        core = self._make_core(max_ctx=100000, history_chars=1000)
        self.assertIsNone(core._check_context_pressure())

    def test_high_usage_returns_reason(self):
        core = self._make_core(max_ctx=1000, history_chars=4000) # 4000/4=1000 tokens = 100% usage
        self.assertEqual(core._check_context_pressure(), "context_pressure")

    def test_default_config_values(self):
        from poor_cli.config import AgenticConfig
        cfg = AgenticConfig()
        self.assertAlmostEqual(cfg.context_pressure_stop_ratio, 0.2)
        self.assertAlmostEqual(cfg.context_pressure_warn_ratio, 0.5)

    def test_no_provider_returns_none(self):
        from poor_cli.core import PoorCLICore
        core = object.__new__(PoorCLICore)
        core.provider = None
        core.config = None
        self.assertIsNone(core._check_context_pressure())
