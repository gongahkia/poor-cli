"""Tests for tool_blob.get (Proposal E.2b)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blob_store import SessionBlobStore
from poor_cli.tool_blocks import CodeBlock, TextBlock, ToolResult
from poor_cli.tool_dispatcher import dispatch_one
import poor_cli.tools  # noqa: F401
from poor_cli.tools import _registry
from poor_cli.tools.tool_blob import handle_get


def _ctx(blob_store=None):
    return SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_blob_store=blob_store,
    )


def _run(coro):
    return asyncio.run(coro)


def test_get_requires_result_id():
    result = _run(handle_get(ctx=_ctx(SessionBlobStore()), args={}))
    assert result.is_error


def test_get_rejects_non_string():
    result = _run(handle_get(ctx=_ctx(SessionBlobStore()), args={"result_id": 42}))
    assert result.is_error


def test_get_returns_stashed_content():
    store = SessionBlobStore()
    original = [CodeBlock(language="diff", code="++ lots of lines ++")]
    rid = store.put(original, original_token_estimate=100)
    result = _run(handle_get(ctx=_ctx(store), args={"result_id": rid}))
    assert not result.is_error
    assert result.content == original
    assert result.metadata["bypass_truncation"] is True
    assert result.metadata["original_token_estimate"] == 100


def test_get_unknown_id_returns_error():
    result = _run(handle_get(ctx=_ctx(SessionBlobStore()), args={"result_id": "blob_deadbeef"}))
    assert result.is_error
    assert result.metadata.get("unknown_result_id") is True


def test_get_without_store_returns_error():
    result = _run(handle_get(ctx=_ctx(None), args={"result_id": "blob_foo"}))
    assert result.is_error
    assert result.metadata.get("unavailable") is True


# ──────────────── dispatcher integration: truncation → tool_blob.get roundtrip ────────────────


@pytest.fixture(autouse=True)
def _snapshot_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


def test_truncate_then_retrieve_full_via_dispatcher():
    """E2E: handler returns a huge result → dispatcher truncates → tool_blob.get
    retrieves the full original content."""

    async def h(*, ctx, args):
        # 40000 chars > 8000 tokens × 4 chars/tok = 32000 char budget → truncated.
        return ToolResult(content=[CodeBlock(language="text", code="ABC" * 20000)])

    _registry.register_tool(
        name="t.bigger",
        description="t",
        schema={"type": "object", "additionalProperties": True},
        handler=h,
    )
    store = SessionBlobStore()
    ctx = SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_blob_store=store,
    )
    truncated, _ = _run(dispatch_one("t.bigger", {}, ctx=ctx))
    assert truncated.metadata["truncated"] is True
    rid = truncated.metadata["result_id"]
    # Now fetch via dispatch_one on tool_blob.get (proves registry wiring)
    full, _ = _run(dispatch_one("tool_blob.get", {"result_id": rid}, ctx=ctx))
    assert not full.is_error
    assert len(full.content) == 1
    full_block = full.content[0]
    assert isinstance(full_block, CodeBlock)
    assert full_block.code == "ABC" * 20000
    assert full.metadata["bypass_truncation"] is True


def test_tool_blob_get_discoverable_via_meta_list_tools():
    """The whole truncation → retrieval flow only works if the agent knows
    tool_blob.get exists. Proves it shows up in meta.list_tools."""
    from poor_cli.tools.meta import handle_list_tools

    result = _run(handle_list_tools(
        ctx=SimpleNamespace(
            cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None,
        ),
        args={"domain": "tool_blob"},
    ))
    assert not result.is_error
    from poor_cli.tool_blocks import TableBlock
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = {row[0] for row in tables[0].rows}
    assert "tool_blob.get" in names


def test_schema_rejects_malformed_result_id():
    """T1 validation: pattern `^blob_[0-9a-f]{8,16}$` must reject random strings."""
    ctx = SimpleNamespace(
        cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None,
        tool_blob_store=SessionBlobStore(),
    )
    result, _ = _run(dispatch_one("tool_blob.get", {"result_id": "definitely not a blob id"}, ctx=ctx))
    assert result.is_error
    assert result.metadata.get("validation_error") is True
