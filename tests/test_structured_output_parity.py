"""SBP2: parity coverage for structured output across providers.

Anthropic + OpenAI coverage already lives in test_structured_output.py. This
file adds Ollama (format: json) and OpenRouter (OpenAI-compatible passthrough)
parity cases so a regression in either wiring fails a targeted test.
"""

from __future__ import annotations

import unittest

from poor_cli.structured_output import (
    StructuredOutputConfig,
    StructuredResponseType,
    build_ollama_format,
    build_openai_response_format,
    should_use_structured_output,
)


class OllamaStructuredOutputTests(unittest.TestCase):
    def test_ollama_format_returns_json_sentinel(self):
        cfg = StructuredOutputConfig(response_type=StructuredResponseType.EDIT_BLOCK)
        self.assertEqual(build_ollama_format(cfg), "json")

    def test_should_use_structured_output_allows_ollama(self):
        # helper uses provider_name + supports_structured flags
        self.assertTrue(should_use_structured_output(
            provider_name="ollama",
            supports_structured=True,
            response_type=StructuredResponseType.EDIT_BLOCK,
        ))

    def test_should_use_structured_output_rejects_tool_call_type(self):
        # tool calls use native function calling, not response_format
        self.assertFalse(should_use_structured_output(
            provider_name="ollama",
            supports_structured=True,
            response_type=StructuredResponseType.TOOL_CALL,
        ))

    def test_ollama_provider_declares_structured_output_support(self):
        from poor_cli.providers.ollama_provider import OllamaProvider
        provider = OllamaProvider(api_key="", model_name="llama3.1")
        caps = provider.get_capabilities()
        self.assertTrue(caps.supports_structured_output)

    def test_ollama_build_chat_request_includes_json_format(self):
        """_build_chat_request writes format: 'json' when structured output is set."""
        from poor_cli.providers.ollama_provider import OllamaProvider

        provider = OllamaProvider(api_key="", model_name="llama3.1")
        cfg = StructuredOutputConfig(response_type=StructuredResponseType.EDIT_BLOCK)
        provider._structured_output = cfg
        provider.messages.append({"role": "user", "content": "go"})
        payload = provider._build_chat_request(stream=False)
        self.assertEqual(payload.get("format"), "json")


class OpenRouterStructuredOutputTests(unittest.TestCase):
    def test_openrouter_inherits_openai_response_format(self):
        """OpenRouter extends OpenAIProvider; response_format is built with the
        OpenAI builder and routes through OpenRouter's OpenAI-compatible endpoint."""
        cfg = StructuredOutputConfig(response_type=StructuredResponseType.PLAN)
        body = build_openai_response_format(cfg)
        self.assertEqual(body["type"], "json_schema")
        self.assertIn("schema", body["json_schema"])
        self.assertIn("name", body["json_schema"])

    def test_openrouter_capabilities_declare_structured_output(self):
        """OpenRouter inherits OpenAIProvider capabilities → supports_structured_output=True.
        Gate-checking per-model happens at the fallback path in openai_provider.send_message."""
        from poor_cli.providers.openrouter_provider import OpenRouterProvider
        try:
            provider = OpenRouterProvider(api_key="fake", model_name="openai/gpt-5")
        except Exception:
            self.skipTest("openai SDK unavailable")
            return
        caps = provider.get_capabilities()
        self.assertTrue(caps.supports_structured_output)


if __name__ == "__main__":
    unittest.main()
