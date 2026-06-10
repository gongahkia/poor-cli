"""Tests for poor_cli.tool_prompt."""

from __future__ import annotations

import poor_cli.tools  # trigger registrations  # noqa: F401
from poor_cli.tool_prompt import manifest_markdown


def test_manifest_groups_by_domain():
    md = manifest_markdown()
    assert "## Integration tools" in md
    assert "### git" in md
    assert "### hunks" in md
    assert "### debug" in md
    assert "### fs" in md
    assert "### deploy" in md
    assert "### watch" in md
    assert "### review" in md


def test_manifest_marks_exclusive_tools():
    md = manifest_markdown()
    # git.commit is exclusive
    assert "`git.commit` **(exclusive)**" in md
    # git.status is not
    status_line = next(line for line in md.splitlines() if "`git.status`" in line)
    assert "**(exclusive)**" not in status_line


def test_manifest_is_deterministic():
    # Two calls should produce identical output (prompt-cache stability).
    assert manifest_markdown() == manifest_markdown()


def test_manifest_domain_order_stable():
    md = manifest_markdown()
    git_idx = md.find("### git")
    hunks_idx = md.find("### hunks")
    debug_idx = md.find("### debug")
    fs_idx = md.find("### fs")
    # canonical domain ordering from _DOMAIN_ORDER
    assert 0 < git_idx < hunks_idx < debug_idx < fs_idx
