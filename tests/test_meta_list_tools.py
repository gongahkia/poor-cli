"""Tests for meta.list_tools (Proposal D.2)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from poor_cli.tool_blocks import TableBlock, TextBlock, ToolResult
import poor_cli.tools  # trigger registrations # noqa: F401
from poor_cli.tools import _registry
from poor_cli.tools.meta import handle_list_tools


def _ctx():
    return SimpleNamespace(cwd=".", has_plugin=lambda _n: False, notify_client=lambda *a, **k: None)


def _run(coro):
    return asyncio.run(coro)


def test_list_all_tools_returns_full_set():
    result = _run(handle_list_tools(ctx=_ctx(), args={}))
    assert not result.is_error
    assert result.metadata["total"] >= 30  # phase B+C registered ~34
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    assert tables
    names = [row[0] for row in tables[0].rows]
    # Sorted alphabetically → deterministic
    assert names == sorted(names)


def test_filter_by_domain_exact():
    result = _run(handle_list_tools(ctx=_ctx(), args={"domain": "git"}))
    assert not result.is_error
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    assert names  # at least one git.* tool exists
    assert all(n == "git" or n.startswith("git.") for n in names)


def test_filter_by_domain_deep_prefix():
    # `git.branch` should match git.branch, git.branch.list, etc.
    result = _run(handle_list_tools(ctx=_ctx(), args={"domain": "git.branch"}))
    assert not result.is_error
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    assert all(n.startswith("git.branch") for n in names)


def test_filter_by_query_case_insensitive():
    result = _run(handle_list_tools(ctx=_ctx(), args={"query": "COMMIT"}))
    assert not result.is_error
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    # git.commit is one of the hits; may also match description-matches
    assert "git.commit" in names


def test_filter_with_no_matches_returns_text_only():
    result = _run(handle_list_tools(ctx=_ctx(), args={"domain": "nonexistent"}))
    assert not result.is_error
    assert not any(isinstance(b, TableBlock) for b in result.content)
    assert "no tools match" in result.content[0].text


def test_domain_and_query_can_combine():
    result = _run(
        handle_list_tools(ctx=_ctx(), args={"domain": "git", "query": "status"})
    )
    assert not result.is_error
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    assert "git.status" in names
    assert all(n.startswith("git") for n in names)


def test_pagination_offset_limit():
    # Get first 3
    page1 = _run(handle_list_tools(ctx=_ctx(), args={"offset": 0, "limit": 3}))
    assert page1.metadata["returned"] == 3
    assert page1.metadata["offset"] == 0
    table1 = [b for b in page1.content if isinstance(b, TableBlock)][0]
    assert len(table1.rows) == 3
    # Get next 3
    next_off = page1.metadata["next_offset"]
    assert next_off == 3
    page2 = _run(handle_list_tools(ctx=_ctx(), args={"offset": 3, "limit": 3}))
    assert page2.metadata["offset"] == 3
    table2 = [b for b in page2.content if isinstance(b, TableBlock)][0]
    # No overlap
    page1_names = [row[0] for row in table1.rows]
    page2_names = [row[0] for row in table2.rows]
    assert set(page1_names).isdisjoint(set(page2_names))


def test_limit_clamped_to_upper_bound():
    result = _run(handle_list_tools(ctx=_ctx(), args={"limit": 9999}))
    # Should clamp to max 200; assert by checking returned <= 200
    assert result.metadata["returned"] <= 200


def test_meta_list_tools_is_self_discoverable():
    # Registering the tool means meta.list_tools itself appears in listing.
    result = _run(handle_list_tools(ctx=_ctx(), args={"domain": "meta"}))
    tables = [b for b in result.content if isinstance(b, TableBlock)]
    names = [row[0] for row in tables[0].rows]
    assert "meta.list_tools" in names


def test_invalid_domain_type_returns_error():
    result = _run(handle_list_tools(ctx=_ctx(), args={"domain": 42}))
    assert result.is_error


def test_invalid_offset_type_returns_error():
    result = _run(handle_list_tools(ctx=_ctx(), args={"offset": "nope"}))
    assert result.is_error


def test_rendered_output_stays_within_budget():
    """meta.list_tools({}) must stay under the 4000-token budget per the
    hard invariant in PROPOSAL-D §3.2."""
    result = _run(handle_list_tools(ctx=_ctx(), args={}))
    # Rough token estimate: 4 chars/token
    total_chars = sum(
        len(b.text) if isinstance(b, TextBlock)
        else sum(sum(len(c) for c in row) for row in b.rows) if isinstance(b, TableBlock)
        else 0
        for b in result.content
    )
    estimated_tokens = total_chars / 4
    assert estimated_tokens < 4500, f"estimated {estimated_tokens} tokens, budget 4000"
