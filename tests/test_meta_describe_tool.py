"""Tests for meta.describe_tool (Proposal D.3)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import CodeBlock, ToolResult
import poor_cli.tools  # trigger registrations  # noqa: F401
from poor_cli.tools.meta import handle_describe_tool


def _ctx():
    return SimpleNamespace(cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None)


def _run(coro):
    return asyncio.run(coro)


def test_describe_known_tool_returns_codeblock():
    result = _run(handle_describe_tool(ctx=_ctx(), args={"name": "git.commit"}))
    assert not result.is_error
    blocks = [b for b in result.content if isinstance(b, CodeBlock)]
    assert blocks
    assert blocks[0].language == "markdown"
    text = blocks[0].code
    # Anchors that must exist in the generated prose
    assert "## git.commit" in text
    assert "Arguments:" in text
    # git.commit requires message
    assert "- message:" in text
    # git.commit is exclusive — metadata reports that
    assert result.metadata["exclusive"] is True
    assert result.metadata["name"] == "git.commit"


def test_describe_unknown_tool_returns_error_with_suggestions():
    result = _run(handle_describe_tool(ctx=_ctx(), args={"name": "git.something"}))
    assert result.is_error
    assert result.metadata.get("unknown_tool") is True
    # Error text includes "similar:" + at least one real git.* tool
    text = result.content[0].text
    assert "similar:" in text
    assert "git." in text


def test_describe_rejects_missing_name():
    result = _run(handle_describe_tool(ctx=_ctx(), args={}))
    assert result.is_error


def test_describe_rejects_empty_name():
    result = _run(handle_describe_tool(ctx=_ctx(), args={"name": "   "}))
    assert result.is_error


def test_describe_non_string_name():
    result = _run(handle_describe_tool(ctx=_ctx(), args={"name": 42}))
    assert result.is_error


def test_describe_tool_preserves_example_block():
    # meta.list_tools has an example registered; describe_tool should
    # render the Examples: section.
    result = _run(handle_describe_tool(ctx=_ctx(), args={"name": "meta.list_tools"}))
    assert not result.is_error
    text = result.content[0].code
    assert "Examples:" in text
    assert result.metadata["has_examples"] is True


def test_describe_is_deterministic():
    a = _run(handle_describe_tool(ctx=_ctx(), args={"name": "git.status"}))
    b = _run(handle_describe_tool(ctx=_ctx(), args={"name": "git.status"}))
    assert a.content[0].code == b.content[0].code
    assert a.metadata == b.metadata
