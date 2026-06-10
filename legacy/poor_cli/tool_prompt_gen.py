"""Deterministic tool-description generator (T12).

When a tool is registered without an explicit ``description``, generate one
from ``{name, schema, examples}`` using a fixed template. Deterministic so
prompt-cache hit rate stays high across reloads.

Usage::

    from poor_cli.tool_prompt_gen import build_description
    desc = build_description(name, schema, examples)

The legacy ``poor_cli.tool_prompt.manifest_markdown`` still renders the
section grouped by domain; this module provides the per-tool block inside.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Sequence


def build_description(
    name: str,
    schema: Mapping[str, Any],
    examples: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Return the prose block describing ``name``. Deterministic order:
    summary → arguments → examples. Empty sections omitted."""
    lines: List[str] = [f"## {name}"]
    summary = (schema.get("description") or "").strip() if isinstance(schema, Mapping) else ""
    if summary:
        lines.append(summary)
    arg_lines = _format_args(schema)
    if arg_lines:
        lines.append("")
        lines.append("Arguments:")
        lines.extend(arg_lines)
    if examples:
        example_lines = _format_examples(examples)
        if example_lines:
            lines.append("")
            lines.append("Examples:")
            lines.extend(example_lines)
    return "\n".join(lines).rstrip() + "\n"


def _format_args(schema: Mapping[str, Any]) -> List[str]:
    if not isinstance(schema, Mapping):
        return []
    properties = schema.get("properties") or {}
    if not properties:
        return []
    required = set(schema.get("required") or [])
    lines: List[str] = []
    for name in sorted(properties):
        prop = properties[name]
        if not isinstance(prop, Mapping):
            lines.append(f"- {name}: (invalid schema entry)")
            continue
        type_label = _type_label(prop)
        req_label = "required" if name in required else "optional"
        desc = str(prop.get("description") or "").strip()
        line = f"- {name}: {type_label}, {req_label}"
        if desc:
            line += f" — {desc}"
        if "default" in prop:
            line += f" (default: {prop['default']!r})"
        if "enum" in prop:
            line += f" (enum: {prop['enum']})"
        lines.append(line)
    return lines


def _type_label(prop: Mapping[str, Any]) -> str:
    if "type" in prop:
        t = prop["type"]
        if isinstance(t, list):
            return " | ".join(str(x) for x in t)
        return str(t)
    if "oneOf" in prop:
        variants = []
        for variant in prop["oneOf"]:
            if isinstance(variant, Mapping):
                variants.append(_type_label(variant))
        return " | ".join(variants) or "any"
    return "any"


def _format_examples(examples: Sequence[Mapping[str, Any]]) -> List[str]:
    out: List[str] = []
    for example in examples:
        if not isinstance(example, Mapping):
            continue
        when = str(example.get("when") or "").strip()
        args = example.get("args") or {}
        result = str(example.get("result_summary") or "").strip()
        parts = []
        if when:
            parts.append(f"When {when}")
        parts.append(f"call with {_compact_args(args)}")
        if result:
            parts.append(f"→ {result}")
        out.append("- " + ". ".join(parts) + ".")
    return out


def _compact_args(args: Mapping[str, Any]) -> str:
    """Stable JSON-ish render. Sorted keys so output is deterministic."""
    if not args:
        return "no args"
    parts = []
    for key in sorted(args):
        parts.append(f"{key}={args[key]!r}")
    return "{" + ", ".join(parts) + "}"


def describe_registry_tool(spec: Any) -> str:
    """Convenience: pull schema/examples off a ``ToolSpec`` and render."""
    schema = getattr(spec, "schema", {}) or {}
    # If the caller already supplied a hand-written description, prefer it
    # over the auto-generated one but still render args/examples for the
    # human-parseable prompt.
    hand_written = getattr(spec, "description", "") or ""
    lines: List[str] = [f"## {spec.name}"]
    if hand_written:
        lines.append(hand_written.strip())
    elif schema.get("description"):
        lines.append(str(schema["description"]).strip())
    arg_lines = _format_args(schema)
    if arg_lines:
        lines.append("")
        lines.append("Arguments:")
        lines.extend(arg_lines)
    examples = getattr(spec, "examples", None)
    if examples:
        example_lines = _format_examples(examples)
        if example_lines:
            lines.append("")
            lines.append("Examples:")
            lines.extend(example_lines)
    return "\n".join(lines).rstrip() + "\n"
