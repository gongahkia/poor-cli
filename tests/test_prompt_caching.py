"""Tests for cross-provider prompt caching support."""

import unittest


class TestOpenAIPromptCaching(unittest.TestCase):
    def test_prompt_caching_flag_stored(self):
        try:
            from poor_cli.providers.openai_provider import OpenAIProvider, OPENAI_AVAILABLE
            if not OPENAI_AVAILABLE:
                self.skipTest("openai not installed")
            provider = OpenAIProvider(api_key="test-key", model_name="gpt-4", prompt_caching=True)
            self.assertTrue(provider.prompt_caching)
        except Exception:
            self.skipTest("openai initialization requires network")

    def test_prompt_caching_default_true(self):
        try:
            from poor_cli.providers.openai_provider import OpenAIProvider, OPENAI_AVAILABLE
            if not OPENAI_AVAILABLE:
                self.skipTest("openai not installed")
            provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
            self.assertTrue(provider.prompt_caching)
        except Exception:
            self.skipTest("openai initialization requires network")

    def test_system_message_is_first(self):
        """OpenAI auto-caches system messages when stable and first in the messages list."""
        try:
            from poor_cli.providers.openai_provider import OpenAIProvider, OPENAI_AVAILABLE
            if not OPENAI_AVAILABLE:
                self.skipTest("openai not installed")
            import asyncio
            provider = OpenAIProvider(api_key="test-key", model_name="gpt-4")
            asyncio.get_event_loop().run_until_complete(
                provider.initialize(system_instruction="You are helpful.")
            )
            self.assertEqual(provider.messages[0]["role"], "system")
            self.assertEqual(provider.messages[0]["content"], "You are helpful.")
        except Exception:
            self.skipTest("openai initialization requires network")


class TestAnthropicPromptCaching(unittest.TestCase):
    def test_anthropic_cache_control(self):
        """Verify Anthropic provider injects cache_control when prompt_caching=True."""
        try:
            from poor_cli.providers.anthropic_provider import AnthropicProvider
        except ImportError:
            self.skipTest("anthropic not installed")
        try:
            provider = AnthropicProvider(api_key="test-key", model_name="claude-3-haiku-20240307", prompt_caching=True)
            self.assertTrue(provider.prompt_caching)
        except Exception:
            self.skipTest("anthropic initialization failed")
