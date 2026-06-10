from __future__ import annotations

from poor_cli.block_cache import (
    ANTHROPIC_CACHE_CONTROL_MAX_BLOCKS,
    BlockCacheSession,
    enforce_anthropic_cache_control_limit,
)
from poor_cli.context_assembly import ContextFile
from poor_cli.providers.base import BaseProvider


def _file(path: str, content: str = "print(1)\n") -> ContextFile:
    return ContextFile(path=path, content=content, tokens=max(1, len(content) // 4), reason="explicit", compressed=False)


def _message(path: str = "a.py", body: str = "print(1)\n", prefix: str = "") -> str:
    return f"{prefix}## Context Files\n### {path} [explicit]\n```python\n{body}\n```\n\nUser request: inspect"


def _texts(content):
    return "".join(part["text"] for part in content)


def test_anthropic_block_cache_marker_emitted():
    cache = BlockCacheSession()
    message = _message()
    payload = cache.provider_message(message, [_file("a.py")], provider_name="anthropic")
    assert _texts(payload) == message
    marked = [part for part in payload if part.get("cache_control") == {"type": "ephemeral"}]
    assert len(marked) == 1
    assert "### a.py [explicit]" in marked[0]["text"]


def test_openai_block_structure_has_no_cache_control():
    cache = BlockCacheSession()
    message = _message()
    payload = cache.provider_message(message, [_file("a.py")], provider_name="openai")
    assert _texts(payload) == message
    assert all("cache_control" not in part for part in payload)


def test_unsupported_provider_silently_skips():
    cache = BlockCacheSession()
    message = _message()
    assert cache.provider_message(message, [_file("a.py")], provider_name="gemini", block_capable=False) == message
    assert cache.get_stats()["blocks"] == 0


def test_file_reuse_within_session_records_cache_hit():
    cache = BlockCacheSession()
    file_ctx = _file("a.py")
    cache.provider_message(_message(prefix="first\n"), [file_ctx], provider_name="anthropic")
    cache.provider_message(_message(prefix="later different position\n"), [file_ctx], provider_name="anthropic")
    stats = cache.get_stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["rolling_hit_rate_pct"] == 50.0


def test_file_order_stable_within_session():
    cache = BlockCacheSession()
    first = cache.stabilize_files([_file("b.py"), _file("a.py")])
    second = cache.stabilize_files([_file("a.py"), _file("b.py")])
    assert [item.path for item in first] == ["b.py", "a.py"]
    assert [item.path for item in second] == ["b.py", "a.py"]


def test_anthropic_block_limit_respected():
    cache = BlockCacheSession()
    files = [_file(f"{idx}.py", f"print({idx})\n") for idx in range(6)]
    sections = [
        f"### {file.path} [explicit]\n```python\n{file.content}\n```"
        for file in files
    ]
    message = "## Context Files\n" + "\n\n".join(sections) + "\n\nUser request: inspect"
    payload = cache.provider_message(message, files, provider_name="anthropic")
    marked = [part for part in payload if "cache_control" in part]
    assert len(marked) == ANTHROPIC_CACHE_CONTROL_MAX_BLOCKS


def test_enforce_anthropic_limit_prefers_message_blocks():
    request = {
        "system": [{"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}],
        "tools": [{"name": "t", "cache_control": {"type": "ephemeral"}}],
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": str(idx), "cache_control": {"type": "ephemeral"}}
                    for idx in range(4)
                ],
            }
        ],
    }
    enforce_anthropic_cache_control_limit(request)
    assert "cache_control" not in request["system"][0]
    assert "cache_control" not in request["tools"][0]
    assert all("cache_control" in part for part in request["messages"][0]["content"])


def test_anthropic_adapter_preserves_block_content():
    from poor_cli.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider.__new__(AnthropicProvider)
    BaseProvider.__init__(provider, api_key="test", model_name="claude-3-5-haiku-latest")
    provider.prompt_caching = True
    provider.messages = []
    provider.prompt_prefix = ""
    provider.tools = None
    provider.system_instruction = None
    payload = BlockCacheSession().provider_message(_message(), [_file("a.py")], provider_name="anthropic")
    provider._append_message(payload)
    messages = provider._build_request_messages()
    assert messages[-1]["content"][1]["cache_control"] == {"type": "ephemeral"}


def test_openai_adapter_preserves_block_content_without_markers():
    from poor_cli.providers.openai_provider import OpenAIProvider

    provider = OpenAIProvider.__new__(OpenAIProvider)
    BaseProvider.__init__(provider, api_key="test", model_name="gpt-5.1")
    provider.messages = []
    provider.prompt_prefix = ""
    provider.tools = None
    provider.system_instruction = None
    payload = BlockCacheSession().provider_message(_message(), [_file("a.py")], provider_name="openai")
    provider._append_message(payload)
    messages = provider._build_request_messages()
    assert _texts(messages[-1]["content"]) == _message()
    assert all("cache_control" not in part for part in messages[-1]["content"])
