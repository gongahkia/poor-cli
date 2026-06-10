"""Manifest stability invariants (Proposal E.3).

The tool manifest that goes into the provider's system prompt must be
byte-stable across:

  (a) repeated calls in the same process (prompt-cache hit)
  (b) different insertion orders of the same tool set (so a Phase-B
      addition doesn't invalidate Anthropic's ephemeral prompt cache)
  (c) presence/absence of unrelated domains (adding a new domain
      doesn't perturb the byte layout of earlier domains up to the
      insertion point)

These invariants make Anthropic's ``cache_control: ephemeral`` marker
(already wired in ``providers/anthropic_provider.py``) actually pay off:
the stable prefix stays identical between turns, so the provider charges
the cheaper cache-read rate on most of the system prompt.

Philosophical bearings from PROPOSAL-E §1 directly apply:

- **Token-frugal.** Prompt-cache hits convert input tokens to near-zero
  cost. Byte-instability would silently bust them.
- **Correctness over savings.** We don't lie about what's in the
  manifest — we just keep its byte representation deterministic.
"""

from __future__ import annotations

from poor_cli.tool_prompt import manifest_markdown
from poor_cli.tools import _registry
from poor_cli.tools._registry import ToolSpec, register_tool


def _dummy_handler(*, ctx, args):
    from poor_cli.tool_blocks import ToolResult
    return ToolResult.text("ok")


def _register_fake(name: str, *, domain: str = "git", exclusive: bool = False):
    """Register a throwaway tool with a deterministic schema + description."""
    register_tool(
        name=name,
        description=f"Fake {name} tool for manifest tests.",
        schema={"type": "object", "properties": {}},
        handler=_dummy_handler,
        exclusive=exclusive,
    )


# ──────────────── (a) Byte-stability across calls ────────────────


def test_manifest_markdown_is_byte_stable_across_calls():
    """Invariant: two successive renders of the same registry produce
    identical bytes. Without this, every turn busts the prompt cache."""
    a = manifest_markdown()
    b = manifest_markdown()
    assert a == b, "manifest_markdown output differs between calls"


# ──────────────── (b) Registration-order independence ────────────────


def test_manifest_markdown_is_registration_order_independent():
    """Registering the same set of tools in different orders must produce
    identical manifest output. Otherwise an order change in tools/__init__.py
    would invalidate every cached system prompt."""
    # Snapshot + clear
    before = dict(_registry._TOOLS)
    try:
        # Order A
        _registry._TOOLS.clear()
        _register_fake("git.a")
        _register_fake("git.b")
        _register_fake("hunks.x")
        order_a = manifest_markdown()

        # Order B — same tools, reversed insertion order
        _registry._TOOLS.clear()
        _register_fake("hunks.x")
        _register_fake("git.b")
        _register_fake("git.a")
        order_b = manifest_markdown()

        assert order_a == order_b, "manifest order depends on insertion order"
    finally:
        _registry._TOOLS.clear()
        _registry._TOOLS.update(before)


# ──────────────── (c) Prefix stability when new tools land ────────────────


def test_adding_a_later_domain_does_not_shift_earlier_section():
    """Invariant: if I render the manifest with {git.*} and later render
    with {git.*, tool_blob.*}, the git.* section should appear byte-identical
    in both (modulo trailing newline around its boundary).

    This is the fine-grained version of byte-stability — we're claiming the
    git.* prose doesn't subtly drift when an unrelated tool family is added.
    """
    before = dict(_registry._TOOLS)
    try:
        _registry._TOOLS.clear()
        _register_fake("git.a")
        _register_fake("git.b")
        manifest_without = manifest_markdown()

        # Now add a tool in a completely different domain.
        _register_fake("hunks.x")
        manifest_with = manifest_markdown()

        # The git section should appear as a substring of both manifests.
        git_header = "### git\n"
        assert git_header in manifest_without
        assert git_header in manifest_with

        # Extract the git section from each (header to next ### or EOF).
        def _extract_section(text: str, header: str) -> str:
            start = text.find(header)
            assert start != -1, f"missing {header!r} in manifest"
            # Find the next "### " on a new line
            next_hdr = text.find("\n### ", start + len(header))
            if next_hdr == -1:
                return text[start:]
            return text[start:next_hdr]

        git_without = _extract_section(manifest_without, git_header)
        git_with = _extract_section(manifest_with, git_header)
        assert git_without == git_with, (
            "git section drifted when hunks domain was added:\n"
            f"before:\n{git_without!r}\nafter:\n{git_with!r}"
        )
    finally:
        _registry._TOOLS.clear()
        _registry._TOOLS.update(before)


# ──────────────── (d) Deterministic sort within a domain ────────────────


def test_tools_within_a_domain_are_alpha_sorted():
    """Within each ### <domain> section, tools appear in alphabetical order
    (not insertion order). This is what makes (b) work."""
    before = dict(_registry._TOOLS)
    try:
        _registry._TOOLS.clear()
        _register_fake("git.zebra")
        _register_fake("git.apple")
        _register_fake("git.mango")
        out = manifest_markdown()

        # Find position of each tool name; they must appear in alpha order.
        positions = []
        for name in ("git.apple", "git.mango", "git.zebra"):
            idx = out.find(f"`{name}`")
            assert idx > -1, f"missing {name} in manifest"
            positions.append(idx)
        assert positions == sorted(positions), (
            f"tools within a domain appear out of alpha order: {positions}"
        )
    finally:
        _registry._TOOLS.clear()
        _registry._TOOLS.update(before)


# ──────────────── (e) Domain ordering is stable ────────────────


def test_canonical_domain_order_is_stable():
    """Domains rendered in a fixed order (per _DOMAIN_ORDER in
    tool_prompt.py) so adding a new tool to an existing domain doesn't
    reorder the domains themselves."""
    before = dict(_registry._TOOLS)
    try:
        _registry._TOOLS.clear()
        _register_fake("fs.x")  # later in _DOMAIN_ORDER
        _register_fake("git.y")  # earlier in _DOMAIN_ORDER
        out = manifest_markdown()

        git_at = out.find("### git")
        fs_at = out.find("### fs")
        assert git_at != -1 and fs_at != -1
        # git comes before fs regardless of registration order
        assert git_at < fs_at
    finally:
        _registry._TOOLS.clear()
        _registry._TOOLS.update(before)


# ──────────────── (f) Exclusive marker is deterministic ────────────────


def test_exclusive_marker_renders_consistently():
    before = dict(_registry._TOOLS)
    try:
        _registry._TOOLS.clear()
        _register_fake("git.ex", exclusive=True)
        _register_fake("git.ok", exclusive=False)
        out = manifest_markdown()
        assert "`git.ex` **(exclusive)**" in out
        ok_line = next(line for line in out.splitlines() if "`git.ok`" in line)
        assert "**(exclusive)**" not in ok_line
    finally:
        _registry._TOOLS.clear()
        _registry._TOOLS.update(before)
