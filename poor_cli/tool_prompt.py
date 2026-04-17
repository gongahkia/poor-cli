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
    """Return the tool manifest block for the system prompt. Deterministic
    order across calls so prompt caching remains hot."""
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
