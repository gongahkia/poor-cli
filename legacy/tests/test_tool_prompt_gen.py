"""Tests for poor_cli.tool_prompt_gen (T12)."""

from __future__ import annotations

from poor_cli.tool_prompt_gen import (
    build_description,
    describe_registry_tool,
)


def test_build_description_includes_required_and_optional_args():
    schema = {
        "description": "Read a file from disk.",
        "type": "object",
        "required": ["path"],
        "properties": {
            "path": {"type": "string", "description": "File path to read"},
            "encoding": {"type": "string", "description": "Text encoding", "default": "utf-8"},
        },
    }
    desc = build_description("fs.read", schema)
    assert "## fs.read" in desc
    assert "Read a file from disk." in desc
    assert "- path: string, required" in desc
    assert "- encoding: string, optional" in desc
    assert "(default: 'utf-8')" in desc


def test_build_description_renders_enums_and_oneOf():
    schema = {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["a", "b"]},
            "cmd": {"oneOf": [{"type": "string"}, {"type": "array"}]},
        },
    }
    desc = build_description("x", schema)
    assert "(enum: ['a', 'b'])" in desc
    assert "string | array" in desc


def test_build_description_with_examples():
    schema = {
        "description": "Toy tool",
        "type": "object",
        "properties": {"n": {"type": "integer"}},
    }
    examples = [
        {"when": "you want five", "args": {"n": 5}, "result_summary": "a textblock"}
    ]
    desc = build_description("toy", schema, examples)
    assert "Examples:" in desc
    assert "When you want five" in desc
    assert "call with {n=5}" in desc
    assert "→ a textblock" in desc


def test_build_description_is_deterministic():
    schema = {
        "description": "d",
        "type": "object",
        "properties": {
            "z": {"type": "string"},
            "a": {"type": "string"},
            "m": {"type": "string"},
        },
    }
    d1 = build_description("t", schema)
    d2 = build_description("t", schema)
    assert d1 == d2
    # Keys appear alphabetically so prompt-cache stability holds
    a_idx = d1.find("- a:")
    m_idx = d1.find("- m:")
    z_idx = d1.find("- z:")
    assert 0 < a_idx < m_idx < z_idx


def test_compact_args_no_args():
    desc = build_description(
        "t",
        {"description": "no-arg tool", "type": "object", "properties": {}},
        examples=[{"when": "trivially", "args": {}, "result_summary": "unit"}],
    )
    assert "call with no args" in desc


def test_describe_registry_tool_uses_hand_written_over_schema():
    class _Spec:
        name = "legacy.tool"
        description = "Hand-written prose."
        schema = {
            "description": "Schema prose should be overridden.",
            "type": "object",
            "properties": {},
        }
        examples: list = []

    desc = describe_registry_tool(_Spec())
    assert "Hand-written prose." in desc
    assert "Schema prose" not in desc
