"""Tests for poor_cli.tool_blob_store + poor_cli.tool_truncation (E.2a)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blob_store import SessionBlobStore
from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tool_dispatcher import dispatch_one
from poor_cli.tool_truncation import DEFAULT_MAX_RESULT_TOKENS, maybe_truncate
from poor_cli.tools import _registry


def _ctx(blob_store=None):
    return SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_blob_store=blob_store,
    )


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _snapshot_registry():
    before = dict(_registry._TOOLS)
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


# ──────────────── SessionBlobStore unit tests ────────────────


def test_blob_store_put_get_roundtrip():
    store = SessionBlobStore()
    content = [TextBlock(text="hello")]
    rid = store.put(content, original_token_estimate=10)
    entry = store.get(rid)
    assert entry is not None
    assert entry.content == content
    assert entry.original_token_estimate == 10


def test_blob_store_unknown_id_returns_none():
    store = SessionBlobStore()
    assert store.get("nope") is None


def test_blob_store_evicts_oldest_over_cap():
    store = SessionBlobStore(cap_bytes=4096)
    # 10 blobs of ~1000 chars each → total ~10000 → should evict
    ids = []
    for i in range(10):
        rid = store.put(
            [TextBlock(text="x" * 900 + f"#{i}")],
            original_token_estimate=200,
        )
        ids.append(rid)
    stats = store.stats()
    assert stats["total_bytes"] <= stats["cap_bytes"]
    # First put should have been evicted
    assert store.get(ids[0]) is None
    # Last one still accessible
    assert store.get(ids[-1]) is not None


def test_blob_store_clear():
    store = SessionBlobStore()
    rid = store.put([TextBlock(text="x")], original_token_estimate=1)
    store.clear()
    assert store.get(rid) is None
    assert store.stats()["entries"] == 0


# ──────────────── maybe_truncate logic ────────────────


def test_under_budget_passes_through():
    ctx = _ctx(SessionBlobStore())
    small = ToolResult(content=[TextBlock(text="hello world")])
    out = maybe_truncate(small, ctx=ctx, max_result_tokens=1000)
    assert out is small  # same object, no copy


def test_oversized_textblock_truncated_middle_out():
    ctx = _ctx(SessionBlobStore())
    big = ToolResult(content=[TextBlock(text="X" * 50000)])  # way over budget
    out = maybe_truncate(big, ctx=ctx, max_result_tokens=200)
    assert out.metadata["truncated"] is True
    assert out.metadata["original_token_estimate"] >= 12000  # 50000/4
    assert "result_id" in out.metadata
    # The rendered TextBlock must preserve head + tail
    blocks = [b for b in out.content if isinstance(b, TextBlock)]
    assert any("X" * 50 in b.text for b in blocks)
    assert any("elided" in b.text for b in blocks)


def test_oversized_codeblock_preserves_language():
    ctx = _ctx(SessionBlobStore())
    big = ToolResult(content=[CodeBlock(language="diff", code="- line\n+ line\n" * 5000)])
    out = maybe_truncate(big, ctx=ctx, max_result_tokens=400)
    codes = [b for b in out.content if isinstance(b, CodeBlock)]
    assert codes
    assert codes[0].language == "diff"
    assert "elided" in codes[0].code


def test_result_id_retrieves_full_content():
    store = SessionBlobStore()
    ctx = _ctx(store)
    original = [CodeBlock(language="diff", code="huge diff" + "X" * 40000)]
    big = ToolResult(content=list(original))
    out = maybe_truncate(big, ctx=ctx, max_result_tokens=200)
    rid = out.metadata["result_id"]
    stashed = store.get(rid)
    assert stashed is not None
    assert stashed.content == original


def test_truncation_without_blob_store_still_bounds_context():
    ctx = _ctx(None)  # no blob store on ctx
    big = ToolResult(content=[TextBlock(text="Z" * 20000)])
    out = maybe_truncate(big, ctx=ctx, max_result_tokens=200)
    assert out.metadata["truncated"] is True
    assert "result_id" not in out.metadata  # no stash happened
    # But the rendered content IS bounded
    total = sum(len(b.text) for b in out.content if isinstance(b, TextBlock))
    assert total < 3000


def test_error_results_not_truncated():
    """Errored ToolResults skip truncation — we want the agent to see the
    full failure. Dispatcher gates via `not result.is_error`; test here
    that passing an error result to maybe_truncate still works (no crash)
    but would be short-circuited by dispatcher before reaching us in
    practice."""
    ctx = _ctx(SessionBlobStore())
    huge_err = ToolResult.error("BOOM" * 10000)
    # We call maybe_truncate anyway to verify it doesn't corrupt error state.
    out = maybe_truncate(huge_err, ctx=ctx, max_result_tokens=200)
    assert out.is_error is True


def test_multi_block_truncates_largest():
    ctx = _ctx(SessionBlobStore())
    small = TextBlock(text="summary line")
    big = CodeBlock(language="text", code="Q" * 40000)
    result = ToolResult(content=[small, big])
    out = maybe_truncate(result, ctx=ctx, max_result_tokens=500)
    # Small block should still be present verbatim (or close)
    small_present = any(
        isinstance(b, TextBlock) and "summary line" in b.text for b in out.content
    )
    assert small_present
    # Big one got truncated
    big_out = next((b for b in out.content if isinstance(b, CodeBlock)), None)
    assert big_out is not None
    assert "elided" in big_out.code


# ──────────────── dispatcher integration ────────────────


def _register(name, handler, **kwargs):
    _registry.register_tool(
        name=name,
        description="t",
        schema={"type": "object", "additionalProperties": True},
        handler=handler,
        **kwargs,
    )


def test_dispatch_truncates_huge_result():
    async def h(*, ctx, args):
        return ToolResult(content=[TextBlock(text="Y" * 60000)])

    _register("t.huge", h)
    ctx = SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_blob_store=SessionBlobStore(),
    )
    result, rec = _run(dispatch_one("t.huge", {}, ctx=ctx))
    assert result.metadata["truncated"] is True
    assert "result_id" in result.metadata


def test_dispatch_respects_max_result_tokens_override():
    async def h(*, ctx, args):
        return ToolResult(content=[TextBlock(text="Z" * 5000)])

    # Tight budget override — result would pass default 8000-token budget
    # but fail a 500-token override.
    _register("t.tight", h, max_result_tokens=500)
    ctx = SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_blob_store=SessionBlobStore(),
    )
    result, _ = _run(dispatch_one("t.tight", {}, ctx=ctx))
    # 5000 chars > 500 tokens * 4 chars = 2000 chars → truncated
    assert result.metadata.get("truncated") is True


def test_dispatch_small_result_untouched():
    async def h(*, ctx, args):
        return ToolResult(content=[TextBlock(text="small")])

    _register("t.small", h)
    ctx = SimpleNamespace(
        cwd=".",
        has_plugin=lambda _n: False,
        notify_client=lambda *a, **k: None,
        tool_blob_store=SessionBlobStore(),
    )
    result, _ = _run(dispatch_one("t.small", {}, ctx=ctx))
    assert result.metadata.get("truncated") is None
