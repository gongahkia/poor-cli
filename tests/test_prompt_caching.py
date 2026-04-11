"""Tests for cache-friendly prompt construction."""

from __future__ import annotations

import asyncio
import unittest


class TestOpenAIPromptCaching(unittest.TestCase):
    def _make_provider(self):
        from poor_cli.providers.openai_provider import OpenAIProvider, OPENAI_AVAILABLE

        if not OPENAI_AVAILABLE:
            self.skipTest("openai not installed")
        provider = OpenAIProvider(api_key="test-key", model_name="gpt-4o-mini", prompt_caching=True)
        asyncio.run(
            provider.initialize(
                tools=[
                    {
                        "name": "z_tool",
                        "description": "z",
                        "parameters": {"type": "OBJECT", "properties": {}},
                    },
                    {
                        "name": "a_tool",
                        "description": "a",
                        "parameters": {"type": "OBJECT", "properties": {}},
                    },
                ],
                system_instruction="system",
            )
        )
        return provider

    def test_request_messages_keep_stable_prefix_before_history(self):
        provider = self._make_provider()
        provider.update_prompt_prefix("repo map then instructions")
        provider.set_history(
            [
                {"role": "user", "content": "older user"},
                {"role": "assistant", "content": "older reply"},
            ]
        )
        provider._append_message("current user")
        messages = provider._build_request_messages()
        self.assertEqual([m["role"] for m in messages[:5]], ["system", "user", "user", "assistant", "user"])
        self.assertEqual(messages[0]["content"], "system")
        self.assertEqual(messages[1]["content"], "repo map then instructions")

    def test_openai_usage_extracts_cached_tokens(self):
        provider = self._make_provider()

        class PromptDetails:
            cached_tokens = 321

        class Usage:
            prompt_tokens = 1000
            completion_tokens = 50
            total_tokens = 1050
            prompt_tokens_details = PromptDetails()

        class Message:
            content = "done"
            tool_calls = []

        class Choice:
            message = Message()
            finish_reason = "stop"

        class Response:
            choices = [Choice()]
            usage = Usage()
            model = "gpt-4o-mini"

        parsed = provider._parse_response(Response())
        self.assertIsNotNone(parsed.usage)
        self.assertEqual(parsed.usage.cache_read_input_tokens, 321)
        self.assertEqual(parsed.metadata["usage"]["cache_read_input_tokens"], 321)


class TestAnthropicPromptCaching(unittest.TestCase):
    def _make_provider(self):
        try:
            from poor_cli.providers.anthropic_provider import AnthropicProvider
        except ImportError:
            self.skipTest("anthropic not installed")
        provider = AnthropicProvider(
            api_key="test-key",
            model_name="claude-3-5-haiku-latest",
            prompt_caching=True,
        )
        asyncio.run(provider.initialize(system_instruction="system"))
        return provider

    def test_anthropic_prefix_message_uses_cache_control(self):
        provider = self._make_provider()
        provider.update_prompt_prefix("repo map then instructions")
        messages = provider._build_request_messages()
        self.assertEqual(messages[0]["role"], "user")
        content = messages[0]["content"][0]
        self.assertEqual(content["text"], "repo map then instructions")
        self.assertEqual(content["cache_control"], {"type": "ephemeral"})
