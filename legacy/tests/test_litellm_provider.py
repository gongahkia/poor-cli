"""Tests for C4 LiteLLM fallback provider."""

from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from poor_cli.exceptions import ConfigurationError


def _skip_if_missing():
    try:
        import litellm  # noqa: F401
        return False
    except ImportError:
        return True


@unittest.skipIf(_skip_if_missing(), "litellm not installed")
class LiteLLMProviderTests(unittest.TestCase):
    def setUp(self):
        from poor_cli.providers.litellm_provider import LiteLLMProvider
        self.Provider = LiteLLMProvider

    def test_requires_model_name(self):
        with self.assertRaises(ConfigurationError):
            self.Provider(api_key="x", model_name="")

    def test_capabilities_declared(self):
        p = self.Provider(api_key="x", model_name="groq/llama-3.1-70b-versatile")
        caps = p.get_capabilities()
        self.assertTrue(caps.supports_streaming)
        self.assertTrue(caps.supports_function_calling)
        self.assertTrue(caps.supports_system_instructions)
        self.assertTrue(caps.supports_structured_output)

    def test_initialize_stores_tools_and_system(self):
        p = self.Provider(api_key="x", model_name="groq/llama-3.1-8b-instant")
        asyncio.run(p.initialize(
            tools=[{"name": "read_file", "description": "read", "parameters": {"type": "object"}}],
            system_instruction="You are a helpful assistant.",
        ))
        self.assertIsNotNone(p.tools)
        self.assertEqual(p.system_instruction, "You are a helpful assistant.")
        # tools wrapped for OpenAI function-calling shape
        self.assertEqual(p.tools[0]["type"], "function")

    def test_build_messages_includes_system(self):
        p = self.Provider(api_key="x", model_name="groq/llama-3.1-8b-instant")
        p.system_instruction = "sys"
        msgs = p._build_messages("hello")
        self.assertEqual(msgs[0]["role"], "system")
        self.assertEqual(msgs[-1]["content"], "hello")

    def test_send_message_routes_through_acompletion(self):
        p = self.Provider(api_key="x", model_name="groq/llama-3.1-8b-instant")
        fake_response = MagicMock()
        fake_response.choices = [MagicMock()]
        fake_response.choices[0].message = MagicMock(content="hello back", tool_calls=None)
        fake_response.choices[0].finish_reason = "stop"
        fake_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

        with patch("poor_cli.providers.litellm_provider.acompletion", new=AsyncMock(return_value=fake_response)) as mock_call:
            result = asyncio.run(p.send_message("say hi"))
            self.assertEqual(result.content, "hello back")
            self.assertEqual(result.finish_reason, "stop")
            self.assertEqual(result.usage.input_tokens, 10)
            self.assertEqual(result.usage.output_tokens, 5)
            call_args = mock_call.call_args.kwargs
            self.assertEqual(call_args["model"], "groq/llama-3.1-8b-instant")

    def test_send_message_extracts_function_calls(self):
        p = self.Provider(api_key="x", model_name="groq/llama-3.1-70b-versatile")
        fake_response = MagicMock()
        tool_call = MagicMock()
        tool_call.id = "call_1"
        tool_call.function = MagicMock(name="read_file", arguments='{"file_path": "x.py"}')
        tool_call.function.name = "read_file"
        tool_call.function.arguments = '{"file_path": "x.py"}'
        fake_response.choices = [MagicMock()]
        fake_response.choices[0].message = MagicMock(content="", tool_calls=[tool_call])
        fake_response.choices[0].finish_reason = "tool_calls"
        fake_response.usage = MagicMock(prompt_tokens=5, completion_tokens=3, total_tokens=8)

        with patch("poor_cli.providers.litellm_provider.acompletion", new=AsyncMock(return_value=fake_response)):
            result = asyncio.run(p.send_message("read file"))
            self.assertIsNotNone(result.function_calls)
            self.assertEqual(result.function_calls[0].name, "read_file")
            self.assertEqual(result.function_calls[0].arguments, {"file_path": "x.py"})

    def test_clear_history(self):
        p = self.Provider(api_key="x", model_name="groq/llama-3.1-8b-instant")
        p.messages = [{"role": "user", "content": "hi"}]
        asyncio.run(p.clear_history())
        self.assertEqual(p.messages, [])

    def test_get_set_history(self):
        p = self.Provider(api_key="x", model_name="groq/llama-3.1-8b-instant")
        msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        p.set_history(msgs)
        self.assertEqual(len(p.get_history()), 2)
        # returned copy, not same object
        p.get_history()[0]["content"] = "mutated"
        self.assertEqual(p.messages[0]["content"], "a")


class LiteLLMFactoryIntegrationTests(unittest.TestCase):
    def test_factory_lists_litellm_when_installed(self):
        try:
            import litellm  # noqa: F401
        except ImportError:
            self.skipTest("litellm not installed")
        from poor_cli.providers.provider_factory import ProviderFactory
        providers = ProviderFactory.list_providers()
        self.assertIn("litellm", providers)

    def test_factory_create_raises_on_missing_model(self):
        try:
            import litellm  # noqa: F401
        except ImportError:
            self.skipTest("litellm not installed")
        from poor_cli.providers.provider_factory import ProviderFactory
        with self.assertRaises(ConfigurationError):
            ProviderFactory.create("litellm", api_key="", model_name="")


if __name__ == "__main__":
    unittest.main()
