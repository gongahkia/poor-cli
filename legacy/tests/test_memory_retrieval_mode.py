"""Tests for MH5 retrieval-mode partition."""

from __future__ import annotations

import unittest

from poor_cli.memory import MemoryEntry
from poor_cli.memory_retrieval_mode import (
    RetrievalModeConfig,
    is_critical,
    partition,
    render_always_injected,
)


def _entry(name, type_="feedback", content="x", depth=0, lines=None):
    if lines is not None:
        content = "\n".join(f"line {i}" for i in range(lines))
    return MemoryEntry(
        name=name, description="d", type=type_, content=content,
        derivation_depth=depth,
    )


class RetrievalModePartitionTests(unittest.TestCase):
    def test_short_feedback_is_critical(self):
        self.assertTrue(is_critical(_entry("f", type_="feedback", content="short")))

    def test_short_user_is_critical(self):
        self.assertTrue(is_critical(_entry("u", type_="user", content="short")))

    def test_project_type_is_tool_driven(self):
        self.assertFalse(is_critical(_entry("p", type_="project", content="short")))

    def test_reference_type_is_tool_driven(self):
        self.assertFalse(is_critical(_entry("r", type_="reference", content="short")))

    def test_long_feedback_is_tool_driven(self):
        e = _entry("long", type_="feedback", lines=20)
        self.assertFalse(is_critical(e))

    def test_deep_derivation_is_tool_driven(self):
        e = _entry("distilled", type_="feedback", content="short", depth=2)
        self.assertFalse(is_critical(e))

    def test_partition_splits_correctly(self):
        entries = [
            _entry("critical-1", type_="feedback", content="one-liner"),
            _entry("episodic-1", type_="project", content="some context"),
            _entry("critical-2", type_="user", content="short user pref"),
            _entry("long-feedback", type_="feedback", lines=50),
        ]
        always, tool_driven = partition(entries)
        names_always = [e.name for e in always]
        names_tool = [e.name for e in tool_driven]
        self.assertEqual(set(names_always), {"critical-1", "critical-2"})
        self.assertEqual(set(names_tool), {"episodic-1", "long-feedback"})

    def test_custom_config_changes_behavior(self):
        cfg = RetrievalModeConfig(line_limit=2, always_inject_types=frozenset({"project"}))
        entries = [
            _entry("small-project", type_="project", content="two\nlines"),
            _entry("big-project", type_="project", lines=5),
            _entry("feedback", type_="feedback", content="x"),
        ]
        always, tool_driven = partition(entries, cfg)
        names = {e.name for e in always}
        self.assertEqual(names, {"small-project"})
        self.assertIn("feedback", {e.name for e in tool_driven})

    def test_render_always_injected_empty_when_no_criticals(self):
        entries = [_entry("p", type_="project", content="x")]
        self.assertEqual(render_always_injected(entries), "")

    def test_render_always_injected_formats_block(self):
        entries = [
            _entry("prefs", type_="feedback", content="use Go\navoid Rust"),
        ]
        out = render_always_injected(entries)
        self.assertIn("## Critical Memories", out)
        self.assertIn("prefs", out)
        self.assertIn("use Go", out)
        self.assertIn("avoid Rust", out)


if __name__ == "__main__":
    unittest.main()
