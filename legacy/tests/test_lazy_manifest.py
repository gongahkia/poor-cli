"""Tests for lazy-manifest opt-in (Proposal E.4)."""

from __future__ import annotations

import pytest

from poor_cli.tool_prompt import (
    manifest_markdown,
    manifest_markdown_lazy,
    pick_manifest,
)
from poor_cli.tools import _registry


def _dummy_handler(*, ctx, args):
    from poor_cli.tool_blocks import ToolResult
    return ToolResult.text("ok")


@pytest.fixture
def fresh_registry():
    before = dict(_registry._TOOLS)
    _registry._TOOLS.clear()
    yield
    _registry._TOOLS.clear()
    _registry._TOOLS.update(before)


def _register(name: str, **kwargs):
    _registry.register_tool(
        name=name,
        description=f"Fake {name}.",
        schema={"type": "object", "properties": {}},
        handler=_dummy_handler,
        **kwargs,
    )


def test_lazy_manifest_is_smaller_than_full(fresh_registry):
    # Populate a realistic multi-domain registry (~50 tools).
    for d in ("git", "hunks", "debug", "diagnostics", "fs", "task",
              "deploy", "watch", "review"):
        for t in "abcdef":  # 6 tools per domain = 54 total
            _register(f"{d}.{t}")
    full = manifest_markdown()
    lazy = manifest_markdown_lazy()
    # With 54 tools the lazy manifest should be well under half the full one.
    assert len(lazy) < len(full) / 2, (
        f"lazy={len(lazy)} full={len(full)} — lazy should be ≥2× smaller "
        "at realistic tool counts; confirms the token-saving premise"
    )


def test_lazy_manifest_lists_every_domain_once(fresh_registry):
    _register("git.a")
    _register("git.b")
    _register("hunks.a")
    _register("fs.a")
    lazy = manifest_markdown_lazy()
    # Each domain appears exactly once as `\`<domain>.*\``
    for d in ("git", "hunks", "fs"):
        assert lazy.count(f"`{d}.*`") == 1, (
            f"expected `{d}.*` exactly once in lazy manifest"
        )


def test_lazy_manifest_includes_tool_count(fresh_registry):
    _register("git.a")
    _register("git.b")
    _register("git.c")
    lazy = manifest_markdown_lazy()
    assert "`git.*` (3 tools)" in lazy


def test_lazy_manifest_instructs_meta_list_tools(fresh_registry):
    _register("git.a")
    lazy = manifest_markdown_lazy()
    # Explicitly tells the agent how to expand the manifest
    assert "meta.list_tools" in lazy
    assert "meta.describe_tool" in lazy


def test_lazy_manifest_is_byte_stable(fresh_registry):
    _register("git.a")
    _register("hunks.x")
    assert manifest_markdown_lazy() == manifest_markdown_lazy()


def test_lazy_manifest_registration_order_independent(fresh_registry):
    _register("git.b")
    _register("git.a")
    _register("hunks.x")
    order_a = manifest_markdown_lazy()

    _registry._TOOLS.clear()
    _register("hunks.x")
    _register("git.a")
    _register("git.b")
    order_b = manifest_markdown_lazy()
    assert order_a == order_b


def test_pick_manifest_dispatches_by_flag(fresh_registry):
    _register("git.a")
    _register("git.b")
    full = pick_manifest(lazy=False)
    lazy = pick_manifest(lazy=True)
    assert full == manifest_markdown()
    assert lazy == manifest_markdown_lazy()
    assert full != lazy


def test_pick_manifest_default_is_full(fresh_registry):
    """Default-off safety: if a caller forgets the flag, they get the
    full manifest (correctness over speculative savings)."""
    _register("git.a")
    default = pick_manifest()
    assert default == manifest_markdown()


def test_lazy_manifest_empty_registry_returns_empty_string(fresh_registry):
    assert manifest_markdown_lazy() == ""


def test_lazy_manifest_canonical_domain_order(fresh_registry):
    # Register in reverse canonical order
    _register("review.a")
    _register("watch.a")
    _register("deploy.a")
    _register("task.a")
    _register("fs.a")
    _register("diagnostics.a")
    _register("debug.a")
    _register("hunks.a")
    _register("git.a")
    lazy = manifest_markdown_lazy()
    # Domains must appear in the canonical order
    canonical = ["git", "hunks", "debug", "diagnostics", "fs", "task", "deploy", "watch", "review"]
    positions = [lazy.find(f"`{d}.*`") for d in canonical]
    assert positions == sorted(positions)
    assert all(p > 0 for p in positions)
