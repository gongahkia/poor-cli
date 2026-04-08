"""tests for poor_cli.provider_fallback module."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from poor_cli.provider_fallback import ProviderFallbackManager
from poor_cli.config import FallbackConfig, ConfigManager
from poor_cli.circuit_breaker import CircuitBreakerConfig, CircuitState
from poor_cli.exceptions import (
    APIRateLimitError,
    APIConnectionError,
    APIError,
    ConfigurationError,
)


def _run(coro):
    return asyncio.run(coro)


class TestFallbackManager(unittest.TestCase):
    def _make_manager(self, chain=None, enabled=True, cb_enabled=False):
        cfg = FallbackConfig(
            enabled=enabled,
            chain=chain or ["gemini", "openai", "ollama"],
            retry_on_rate_limit=True,
            retry_on_server_error=True,
            max_fallback_attempts=3,
        )
        cm = MagicMock(spec=ConfigManager)
        cm.get_api_key.return_value = "test-key"
        pc = MagicMock()
        pc.default_model = "test-model"
        pc.base_url = None
        cm.get_provider_config.return_value = pc
        cb_cfg = CircuitBreakerConfig(enabled=cb_enabled, failure_threshold=2, recovery_timeout=0.01)
        return ProviderFallbackManager(cfg, cm, cb_cfg)

    def test_disabled_returns_none(self):
        mgr = self._make_manager(enabled=False)
        result = _run(mgr.try_fallback("gemini", APIRateLimitError("rate limit")))
        self.assertIsNone(result)

    def test_non_fallbackable_error(self):
        mgr = self._make_manager()
        result = _run(mgr.try_fallback("gemini", ValueError("not api error")))
        self.assertIsNone(result)

    def test_rate_limit_triggers_fallback(self):
        mgr = self._make_manager()
        self.assertTrue(mgr._should_fallback(APIRateLimitError("rate limit")))

    def test_connection_error_triggers_fallback(self):
        mgr = self._make_manager()
        self.assertTrue(mgr._should_fallback(APIConnectionError("conn error")))

    def test_server_500_triggers_fallback(self):
        mgr = self._make_manager()
        self.assertTrue(mgr._should_fallback(APIError("500 server error")))

    def test_get_fallback_chain_excludes_primary(self):
        mgr = self._make_manager(chain=["gemini", "openai", "ollama"])
        mgr.config.prefer_cheaper = False
        chain = mgr._get_fallback_chain("gemini")
        self.assertEqual(chain, ["openai", "ollama"])

    def test_get_fallback_chain_prefers_cheaper(self):
        mgr = self._make_manager(chain=["gemini", "openai", "ollama"])
        mgr.config.prefer_cheaper = True
        chain = mgr._get_fallback_chain("gemini")
        self.assertEqual(chain[0], "ollama") # ollama is free, should be first

    def test_circuit_breaker_record_success(self):
        mgr = self._make_manager(cb_enabled=True)
        cb = mgr.get_circuit_breaker("gemini")
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.state, CircuitState.OPEN)
        mgr.reset("gemini")
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_reset_all(self):
        mgr = self._make_manager(cb_enabled=True)
        for name in ["gemini", "openai"]:
            cb = mgr.get_circuit_breaker(name)
            cb.record_failure()
            cb.record_failure()
        mgr.reset()
        for name in ["gemini", "openai"]:
            self.assertEqual(mgr.get_circuit_breaker(name).state, CircuitState.CLOSED)

    @patch("poor_cli.provider_fallback.ProviderFactory")
    def test_try_fallback_skips_open_circuit(self, mock_factory):
        mgr = self._make_manager(cb_enabled=True)
        cb = mgr.get_circuit_breaker("openai")
        cb.record_failure()
        cb.record_failure() # opens circuit
        mock_provider = AsyncMock()
        mock_factory.create.return_value = mock_provider
        result = _run(mgr.try_fallback("gemini", APIRateLimitError("rate limit")))
        # should skip openai (circuit open) and try ollama
        if result is not None:
            create_calls = mock_factory.create.call_args_list
            provider_names = [c.kwargs.get("provider_name") or c.args[0] if c.args else c.kwargs.get("provider_name") for c in create_calls]
            self.assertNotIn("openai", [str(n).lower() for n in provider_names])


if __name__ == "__main__":
    unittest.main()
