"""System-prompt helpers for Phase-B tool advertisement.

Generates a concise markdown block listing every registered Phase-B tool,
grouped by domain prefix. Designed to be inserted into the system prompt
once, near the end of the tool manifest. Keeps wording deterministic so
prompt caching isn't invalidated by insertion-order shuffles.

Callers:
  poor_cli.core_agent_loop.build_system_prompt — appends the block after the
  legacy tool manifest section (integration point).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List

from poor_cli.tools._registry import ToolSpec, all_tools


_DOMAIN_ORDER = [
    "git", "hunks", "debug", "diagnostics",
    "fs", "task", "deploy", "watch", "review",
]


def _group_by_domain(tools: Dict[str, ToolSpec]) -> Dict[str, List[ToolSpec]]:
    grouped: Dict[str, List[ToolSpec]] = defaultdict(list)
    for name, spec in tools.items():
        domain = name.split(".", 1)[0]
        grouped[domain].append(spec)
    for domain in grouped:
        grouped[domain].sort(key=lambda s: s.name)
    return grouped


def manifest_markdown(tools: Dict[str, ToolSpec] | None = None) -> str:
    """Return the full tool manifest block for the system prompt.
    Deterministic order across calls so prompt caching remains hot."""
    tools = tools if tools is not None else all_tools()
    if not tools:
        return ""
    grouped = _group_by_domain(tools)
    # preserve canonical domain order, then any novel domains alphabetically
    domains = [d for d in _DOMAIN_ORDER if d in grouped]
    extras = sorted(d for d in grouped if d not in _DOMAIN_ORDER)
    lines: List[str] = [
        "## Integration tools",
        "",
        (
            "You have tools that drive the user's Neovim plugins and shell. "
            "Prefer these over asking the user to run commands themselves. "
            "Tools that mutate the repo are marked **(exclusive)** — the "
            "dispatcher serializes them. Every tool returns structured "
            "blocks; do not paraphrase — the frontend renders them."
        ),
        "",
    ]
    for domain in domains + extras:
        specs = grouped[domain]
        lines.append(f"### {domain}")
        lines.append("")
        for spec in specs:
            marker = " **(exclusive)**" if spec.exclusive else ""
            # Keep description to first sentence to bound token budget.
            first = spec.description.split(". ", 1)[0].strip().rstrip(".")
            lines.append(f"- `{spec.name}`{marker}: {first}.")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


# ──────────────── Proposal E.4 — lazy manifest (opt-in) ────────────────
#
# Purpose: for sessions where the user prefers a tight system prompt,
# surface only the *domain* names + a pointer at meta.list_tools. The
# agent can pull specific schemas on demand via meta.describe_tool or
# meta.list_tools({domain:...}).
#
# Default is OFF. The full manifest is the safe default — lazy manifest
# is only a win when the agent actually navigates via meta.* instead of
# guessing. Measured before enabling by default.


def manifest_markdown_lazy(tools: Dict[str, ToolSpec] | None = None) -> str:
    """Render the lazy-manifest form: a one-line summary per domain and a
    pointer at meta.list_tools. Deterministic bytes, same prompt-cache
    discipline as the full manifest."""
    tools = tools if tools is not None else all_tools()
    if not tools:
        return ""
    grouped = _group_by_domain(tools)
    domains = [d for d in _DOMAIN_ORDER if d in grouped]
    extras = sorted(d for d in grouped if d not in _DOMAIN_ORDER)
    lines: List[str] = [
        "## Integration tools (lazy manifest)",
        "",
        (
            "Tool domains are available; individual schemas are NOT in this "
            "prompt to conserve tokens. Call `meta.list_tools({domain:\"<name>\"})` "
            "or `meta.describe_tool({name:\"<tool>\"})` to discover specifics "
            "before calling a tool you haven't used this session."
        ),
        "",
    ]
    for domain in domains + extras:
        specs = grouped[domain]
        count = len(specs)
        # Take the domain-prefix of a representative tool's description
        # (first sentence) to give one-line context. Stable across calls
        # because specs are sorted by name.
        hint = (specs[0].description.split(". ", 1)[0].strip().rstrip(".")) if specs else ""
        # Bound hint length.
        if len(hint) > 90:
            hint = hint[:87].rstrip() + "…"
        lines.append(f"- `{domain}.*` ({count} tool{'' if count == 1 else 's'}): {hint}.")
    lines.append("")
    lines.append("Use `meta.list_tools({})` to enumerate everything.")
    return "\n".join(lines).rstrip() + "\n"


def pick_manifest(tools: Dict[str, ToolSpec] | None = None, *, lazy: bool = False) -> str:
    """Dispatch between full + lazy based on the ``lazy`` flag. Callers
    pass ``lazy = config.get("tools", {}).get("lazy_manifest", False)``
    or equivalent."""
    return manifest_markdown_lazy(tools) if lazy else manifest_markdown(tools)
