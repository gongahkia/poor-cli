"""Provider adapter contract tests."""

from types import SimpleNamespace

import pytest

import poor_cli.providers.gemini_provider as gemini_module
import poor_cli.providers.ollama_provider as ollama_module
from poor_cli.providers.anthropic_provider import AnthropicProvider
from poor_cli.providers.gemini_provider import GeminiProvider
from poor_cli.providers.ollama_provider import OllamaProvider
from poor_cli.providers.openai_provider import OpenAIProvider


class _FakePart:
    @staticmethod
    def from_function_response(*, name, response):
        return {
            "type": "function_response",
            "name": name,
            "response": response,
        }


def _make_tool_results():
    return [
        {
            "id": "tool-1",
            "name": "read_file",
            "result": "file contents",
        }
    ]


def _make_gemini_provider():
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.max_retries = 1
    provider.retry_delay = 0
    provider.timeout = 1
    provider.chat = None
    return provider


def _make_openai_provider():
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.messages = []
    provider.model_name = "gpt-test"
    provider.tools = None
    provider.max_retries = 1
    provider.retry_delay = 0
    provider.timeout = 1
    return provider


def _make_anthropic_provider():
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider.messages = []
    provider.model_name = "claude-test"
    provider.tools = None
    provider.system_instruction = None
    provider.max_retries = 1
    provider.retry_delay = 0
    provider.timeout = 1
    return provider


def _make_ollama_provider():
    provider = OllamaProvider.__new__(OllamaProvider)
    provider.messages = []
    provider.model_name = "llama3"
    provider.tools = None
    provider.base_url = "http://localhost:11434"
    provider.timeout = 1
    provider.max_retries = 1
    provider.retry_delay = 0
    return provider


@pytest.mark.asyncio
async def test_gemini_stream_chunk_contract(monkeypatch):
    provider = _make_gemini_provider()

    async def _stream_gen():
        yield SimpleNamespace(
            text="chunk-a",
            function_calls=None,
            candidates=[SimpleNamespace(finish_reason=None)],
        )

    class _FakeChat:
        async def send_message_stream(self, _message):
            return _stream_gen()

    provider.chat = _FakeChat()

    chunks = []
    async for chunk in provider.send_message_stream("hello"):
        chunks.append(chunk)

    assert [chunk.content for chunk in chunks] == ["chunk-a"]
    assert chunks[0].metadata["is_chunk"] is True


@pytest.mark.asyncio
async def test_openai_stream_chunk_contract():
    provider = _make_openai_provider()

    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="chunk-1", tool_calls=None)
                )
            ]
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(content="chunk-2", tool_calls=None)
                )
            ]
        ),
    ]

    class _FakeCompletions:
        async def create(self, **_kwargs):
            async def _iter():
                for chunk in chunks:
                    yield chunk

            return _iter()

    provider.client = SimpleNamespace(
        chat=SimpleNamespace(completions=_FakeCompletions())
    )

    yielded = []
    async for chunk in provider.send_message_stream("hello"):
        yielded.append(chunk)

    assert [chunk.content for chunk in yielded] == ["chunk-1", "chunk-2"]
    assert all(chunk.metadata["is_chunk"] is True for chunk in yielded)


@pytest.mark.asyncio
async def test_anthropic_stream_chunk_contract():
    provider = _make_anthropic_provider()

    events = [
        SimpleNamespace(
            type="content_block_delta",
            delta=SimpleNamespace(type="text_delta", text="chunk-a"),
        )
    ]

    class _FakeStream:
        def __init__(self, stream_events):
            self._events = stream_events

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            async def _iter():
                for event in self._events:
                    yield event

            return _iter()

        async def get_final_message(self):
            return SimpleNamespace(content=[])

    class _FakeMessages:
        def stream(self, **_kwargs):
            return _FakeStream(events)

    provider.client = SimpleNamespace(messages=_FakeMessages())

    yielded = []
    async for chunk in provider.send_message_stream("hello"):
        yielded.append(chunk)

    assert [chunk.content for chunk in yielded] == ["chunk-a"]
    assert yielded[0].metadata["is_chunk"] is True


@pytest.mark.asyncio
async def test_ollama_stream_chunk_contract(monkeypatch):
    provider = _make_ollama_provider()

    lines = [
        b'{"message": {"content": "chunk-1"}, "done": false}\n',
        b'{"message": {"content": "chunk-2"}, "done": false}\n',
        b'{"done": true}\n',
    ]

    class _FakeContent:
        def __aiter__(self):
            async def _iter():
                for line in lines:
                    yield line

            return _iter()

    class _FakeResponse:
        status = 200

        def __init__(self):
            self.content = _FakeContent()

        async def text(self):
            return ""

    class _FakePostContext:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def post(self, *_args, **_kwargs):
            return _FakePostContext()

    fake_aiohttp = SimpleNamespace(
        ClientSession=_FakeSession,
        ClientTimeout=lambda total: None,
    )
    monkeypatch.setattr(ollama_module, "aiohttp", fake_aiohttp, raising=False)

    yielded = []
    async for chunk in provider.send_message_stream("hello"):
        yielded.append(chunk)

    assert [chunk.content for chunk in yielded] == ["chunk-1", "chunk-2"]
    assert all(chunk.metadata["is_chunk"] is True for chunk in yielded)


def test_gemini_function_call_parse_contract():
    provider = _make_gemini_provider()

    response = SimpleNamespace(
        text="",
        function_calls=[
            SimpleNamespace(id=None, name="read_file", args={"path": "a.py"})
        ],
        candidates=[SimpleNamespace(finish_reason="STOP")],
    )

    parsed = provider._parse_response(response)

    assert parsed.function_calls is not None
    assert parsed.function_calls[0].id == "gemini_read_file"
    assert parsed.function_calls[0].arguments == {"path": "a.py"}


def test_openai_function_call_parse_contract():
    provider = _make_openai_provider()

    response = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(
                                name="read_file",
                                arguments='{"path": "main.py"}',
                            ),
                        )
                    ],
                ),
                finish_reason="tool_calls",
            )
        ],
        model="gpt-test",
        usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )

    parsed = provider._parse_response(response)

    assert parsed.function_calls is not None
    assert parsed.function_calls[0].id == "call-1"
    assert parsed.function_calls[0].name == "read_file"
    assert parsed.function_calls[0].arguments == {"path": "main.py"}


def test_anthropic_function_call_parse_contract():
    provider = _make_anthropic_provider()

    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="text", text=""),
            SimpleNamespace(type="tool_use", id="tool-1", name="read_file", input={"path": "x"}),
        ],
        stop_reason="tool_use",
        model="claude-test",
        usage=SimpleNamespace(input_tokens=2, output_tokens=1),
    )

    parsed = provider._parse_response(response)

    assert parsed.function_calls is not None
    assert parsed.function_calls[0].id == "tool-1"
    assert parsed.function_calls[0].name == "read_file"
    assert parsed.function_calls[0].arguments == {"path": "x"}


def test_ollama_function_call_parse_contract():
    provider = _make_ollama_provider()

    response = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": "main.py"}',
                    },
                }
            ],
        },
        "done_reason": "tool_calls",
    }

    parsed = provider._parse_response(response)

    assert parsed.function_calls is not None
    assert parsed.function_calls[0].id == "call-1"
    assert parsed.function_calls[0].name == "read_file"
    assert parsed.function_calls[0].arguments == {"path": "main.py"}


def test_gemini_tool_result_format_contract(monkeypatch):
    provider = _make_gemini_provider()
    monkeypatch.setattr(gemini_module, "genai_types", SimpleNamespace(Part=_FakePart))

    formatted = provider.format_tool_results(_make_tool_results())

    assert formatted == [
        {
            "type": "function_response",
            "name": "read_file",
            "response": {"result": "file contents"},
        }
    ]


def test_openai_tool_result_format_contract():
    provider = _make_openai_provider()

    formatted = provider.format_tool_results(_make_tool_results())

    assert formatted == [
        {
            "role": "tool",
            "tool_call_id": "tool-1",
            "content": "file contents",
        }
    ]


def test_anthropic_tool_result_format_contract():
    provider = _make_anthropic_provider()

    formatted = provider.format_tool_results(_make_tool_results())

    assert formatted == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "tool-1",
                "content": "file contents",
            }
        ],
    }


def test_ollama_tool_result_format_contract():
    provider = _make_ollama_provider()

    formatted = provider.format_tool_results(_make_tool_results())

    assert formatted == [
        {
            "role": "tool",
            "tool_call_id": "tool-1",
            "content": "file contents",
        }
    ]
