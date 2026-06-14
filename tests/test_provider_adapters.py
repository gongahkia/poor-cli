from __future__ import annotations

import json
from types import SimpleNamespace

from poor_cli.provider_adapters import AnthropicProvider, GeminiProvider, OllamaProvider, OpenAIProvider
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
