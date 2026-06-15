from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from poor_cli.offline import OfflineModeError
from poor_cli.provider_adapters import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
    SGLangProvider,
    VLLMProvider,
    function_tool,
    json_schema_response_format,
)
from poor_cli.providers import ProviderRequest


def test_anthropic_provider_uses_messages_api() -> None:
    class Messages:
        def __init__(self) -> None:
            self.kwargs = {}

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(content=[SimpleNamespace(text="ok")])

    client = SimpleNamespace(messages=Messages())
    response = AnthropicProvider(client).call(
        ProviderRequest(provider="anthropic", model="claude-test", prompt="hello", system_prompt="sys", params={"max_tokens": 7})
    )

    assert response.content == "ok"
    assert client.messages.kwargs["model"] == "claude-test"
    assert client.messages.kwargs["system"] == "sys"
    assert client.messages.kwargs["messages"] == [{"role": "user", "content": "hello"}]
    assert client.messages.kwargs["max_tokens"] == 7


def test_openai_provider_uses_responses_api() -> None:
    class Responses:
        def __init__(self) -> None:
            self.kwargs = {}

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(output_text="ok")

    client = SimpleNamespace(responses=Responses())
    response = OpenAIProvider(client).call(ProviderRequest(provider="openai", model="gpt-test", prompt="hello", system_prompt="sys"))

    assert response.content == "ok"
    assert client.responses.kwargs["model"] == "gpt-test"
    assert client.responses.kwargs["input"] == "hello"
    assert client.responses.kwargs["instructions"] == "sys"


def test_openai_provider_maps_native_tool_params() -> None:
    class Responses:
        def __init__(self) -> None:
            self.kwargs = {}

        def create(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(output_text="ok")

    client = SimpleNamespace(responses=Responses())
    schema = {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"], "additionalProperties": False}
    OpenAIProvider(client).call(
        ProviderRequest(
            provider="openai",
            model="gpt-test",
            prompt="hello",
            messages=[{"role": "user", "content": "hello"}],
            params={
                "function_tools": [{"name": "read_file", "description": "read", "parameters": schema}],
                "reasoning_effort": "high",
                "text_verbosity": "low",
                "prompt_cache_key": "cache-key",
            },
        )
    )

    assert client.responses.kwargs["input"] == [{"role": "user", "content": "hello"}]
    assert client.responses.kwargs["tools"][0]["name"] == "read_file"
    assert client.responses.kwargs["reasoning"] == {"effort": "high"}
    assert client.responses.kwargs["text"] == {"verbosity": "low"}
    assert client.responses.kwargs["prompt_cache_key"] == "cache-key"


def test_gemini_provider_uses_generate_content() -> None:
    class Models:
        def __init__(self) -> None:
            self.kwargs = {}

        def generate_content(self, **kwargs):
            self.kwargs = kwargs
            return SimpleNamespace(text="ok")

    client = SimpleNamespace(models=Models())
    response = GeminiProvider(client).call(ProviderRequest(provider="gemini", model="gemini-test", prompt="hello", system_prompt="sys"))

    assert response.content == "ok"
    assert client.models.kwargs["model"] == "gemini-test"
    assert client.models.kwargs["contents"] == "hello"
    assert client.models.kwargs["config"] == {"system_instruction": "sys"}


def test_ollama_provider_posts_generate_request() -> None:
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"response":"ok"}'

    def opener(request):
        seen["url"] = request.full_url
        seen["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    response = OllamaProvider("http://ollama.test", opener).call(
        ProviderRequest(provider="ollama", model="qwen", prompt="hello", system_prompt="sys", params={"temperature": 0})
    )

    assert response.content == "ok"
    assert seen["url"] == "http://ollama.test/api/generate"
    assert seen["payload"]["model"] == "qwen"
    assert seen["payload"]["prompt"] == "hello"
    assert seen["payload"]["system"] == "sys"
    assert seen["payload"]["options"] == {"temperature": 0}


def test_vllm_provider_posts_openai_chat_completion_request() -> None:
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def opener(request):
        seen["url"] = request.full_url
        seen["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    response = VLLMProvider("http://vllm.test", opener).call(
        ProviderRequest(provider="vllm", model="qwen", prompt="hello", system_prompt="sys", params={"temperature": 0})
    )

    assert response.content == "ok"
    assert response.provider == "vllm"
    assert seen["url"] == "http://vllm.test/v1/chat/completions"
    assert seen["payload"]["model"] == "qwen"
    assert seen["payload"]["messages"] == [{"role": "system", "content": "sys"}, {"role": "user", "content": "hello"}]
    assert seen["payload"]["temperature"] == 0


def test_openai_compatible_provider_accepts_v1_base_url() -> None:
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"ok"}}]}'

    def opener(request):
        seen["url"] = request.full_url
        return FakeResponse()

    VLLMProvider("http://vllm.test/v1", opener).call(ProviderRequest(provider="vllm", model="qwen", prompt="hello"))

    assert seen["url"] == "http://vllm.test/v1/chat/completions"


def test_sglang_provider_posts_openai_chat_completion_request() -> None:
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":[{"text":"o"},{"text":"k"}]}}]}'

    def opener(request):
        seen["url"] = request.full_url
        seen["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    response = SGLangProvider("http://sglang.test", opener).call(ProviderRequest(provider="sglang", model="qwen", prompt="hello"))

    assert response.content == "ok"
    assert response.provider == "sglang"
    assert seen["url"] == "http://sglang.test/v1/chat/completions"
    assert seen["payload"]["messages"] == [{"role": "user", "content": "hello"}]


def test_openai_compatible_provider_normalizes_json_schema_response_format() -> None:
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"choices":[{"message":{"content":"{\\"ok\\":true}"}}]}'

    def opener(request):
        seen["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"], "additionalProperties": False}
    response = VLLMProvider("http://vllm.test", opener).call(
        ProviderRequest(
            provider="vllm",
            model="qwen",
            prompt="json",
            params={"json_schema": {"name": "OkResult", "schema": schema, "strict": True}},
        )
    )

    assert response.content == '{"ok":true}'
    assert seen["payload"]["response_format"] == json_schema_response_format("OkResult", schema, strict=True)


def test_openai_compatible_provider_normalizes_function_tools() -> None:
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def read(self):
            return b'{"choices":[{"message":{"tool_calls":[{"function":{"name":"find_symbol","arguments":"{}"}}]}}]}'

    def opener(request):
        seen["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    parameters = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
    response = SGLangProvider("http://sglang.test", opener).call(
        ProviderRequest(
            provider="sglang",
            model="qwen",
            prompt="call tool",
            params={"function_tools": [{"name": "find_symbol", "description": "search symbols", "parameters": parameters}]},
        )
    )

    assert response.raw["choices"][0]["message"]["tool_calls"][0]["function"]["name"] == "find_symbol"
    assert seen["payload"]["tools"] == [function_tool("find_symbol", "search symbols", parameters)]
    assert seen["payload"]["tool_choice"] == "auto"


def test_provider_adapters_block_offline_calls(monkeypatch) -> None:
    class Messages:
        def create(self, **kwargs):
            raise AssertionError("network client should not be called")

    class Responses:
        def create(self, **kwargs):
            raise AssertionError("network client should not be called")

    class Models:
        def generate_content(self, **kwargs):
            raise AssertionError("network client should not be called")

    def opener(request):
        raise AssertionError("network client should not be called")

    monkeypatch.setenv("POOR_CLI_OFFLINE", "1")

    with pytest.raises(OfflineModeError):
        AnthropicProvider(SimpleNamespace(messages=Messages())).call(ProviderRequest(provider="anthropic", model="m", prompt="p"))
    with pytest.raises(OfflineModeError):
        OpenAIProvider(SimpleNamespace(responses=Responses())).call(ProviderRequest(provider="openai", model="m", prompt="p"))
    with pytest.raises(OfflineModeError):
        GeminiProvider(SimpleNamespace(models=Models())).call(ProviderRequest(provider="gemini", model="m", prompt="p"))
    with pytest.raises(OfflineModeError):
        OllamaProvider("http://ollama.test", opener).call(ProviderRequest(provider="ollama", model="m", prompt="p"))
    with pytest.raises(OfflineModeError):
        VLLMProvider("http://vllm.test", opener).call(ProviderRequest(provider="vllm", model="m", prompt="p"))
    with pytest.raises(OfflineModeError):
        SGLangProvider("http://sglang.test", opener).call(ProviderRequest(provider="sglang", model="m", prompt="p"))
