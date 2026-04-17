"""meta.* tools — agent self-discovery (Proposal D).

These tools let the agent introspect the tool registry, session state, and
tool-health telemetry via tool calls instead of relying on the system-prompt
manifest (which may be compressed out of context mid-session).

Invariants (from PROPOSAL-D-DISCOVERY.md §1):
  - Agent-centric. Every tool here exists for the agent, not the user. No
    user-facing command wraps them.
  - Token-frugal. Every list tool paginates, filters, and truncates so
    the agent spends tokens only on information it actually needs.
  - Read-only. meta.* tools never mutate state. (meta.* is specifically
    excluded from the mutating-tool whitelist in session_recorder.py.)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from poor_cli.tool_blocks import TableBlock, TextBlock, ToolResult
from poor_cli.tools._registry import ToolSpec, all_tools, register_tool


# ~4 chars per token rough estimate. We pick a conservative default so
# `meta.list_tools({})` never dumps a giant wall of description into the
# agent's context. The agent can still paginate via offset+limit.
_MAX_TOKENS_PER_CALL = 4000
_CHARS_PER_TOKEN = 4
_DEFAULT_LIMIT = 50


def _first_sentence(text: str, *, cap: int = 110) -> str:
    """Pull the first sentence (up to ``cap`` chars) from a description for
    the one-line TableBlock row. Keeps meta.list_tools compact."""
    text = (text or "").strip()
    if not text:
        return ""
    # Cut at first full-stop-space or newline; else hard cap.
    for terminator in [". ", "\n"]:
        idx = text.find(terminator)
        if 0 < idx <= cap:
            return text[:idx].rstrip(".") + "."
    if len(text) <= cap:
        return text
    return text[: cap - 1].rstrip() + "…"


def _filter_tools(
    tools: Dict[str, ToolSpec],
    *,
    domain: Optional[str] = None,
    query: Optional[str] = None,
) -> List[ToolSpec]:
    """Apply the domain prefix and free-text query filters. Returns the
    surviving specs sorted alphabetically by name (deterministic for
    prompt-cache stability)."""
    specs = list(tools.values())
    if domain:
        domain = domain.rstrip(".")
        specs = [s for s in specs if s.name == domain or s.name.startswith(domain + ".")]
    if query:
        needle = query.lower()
        specs = [
            s
            for s in specs
            if needle in s.name.lower() or needle in (s.description or "").lower()
        ]
    specs.sort(key=lambda s: s.name)
    return specs


def _build_list_table(
    specs: List[ToolSpec],
    *,
    offset: int,
    limit: int,
) -> tuple[TableBlock, Dict[str, Any]]:
    """Render at most ``limit`` rows (and also stop early if the rendered
    output would blow the token budget). Returns the table + pagination
    metadata."""
    end = min(len(specs), offset + max(1, limit))
    rows: List[List[str]] = []
    rendered_chars = 0
    budget_chars = _MAX_TOKENS_PER_CALL * _CHARS_PER_TOKEN
    truncated = False
    next_offset: Optional[int] = None
    consumed = 0
    for idx in range(offset, end):
        spec = specs[idx]
        row = [
            spec.name,
            "yes" if spec.exclusive else "no",
            _first_sentence(spec.description),
        ]
        row_chars = sum(len(c) for c in row) + 6  # 6 for separators
        if rendered_chars + row_chars > budget_chars and rows:
            truncated = True
            next_offset = idx
            break
        rows.append(row)
        rendered_chars += row_chars
        consumed += 1
    if not truncated and offset + consumed < len(specs):
        truncated = True
        next_offset = offset + consumed
    meta: Dict[str, Any] = {
        "total": len(specs),
        "offset": offset,
        "returned": consumed,
    }
    if truncated:
        meta["truncated"] = True
        meta["next_offset"] = next_offset
    return TableBlock(columns=["name", "exclusive", "summary"], rows=rows), meta


async def handle_list_tools(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    domain = args.get("domain")
    if domain is not None and not isinstance(domain, str):
        return ToolResult.error("domain must be a string")
    query = args.get("query")
    if query is not None and not isinstance(query, str):
        return ToolResult.error("query must be a string")
    try:
        offset = int(args.get("offset", 0) or 0)
    except (TypeError, ValueError):
        return ToolResult.error("offset must be an integer")
    try:
        limit = int(args.get("limit", _DEFAULT_LIMIT) or _DEFAULT_LIMIT)
    except (TypeError, ValueError):
        return ToolResult.error("limit must be an integer")
    limit = max(1, min(limit, 200))

    specs = _filter_tools(all_tools(), domain=domain, query=query)
    if not specs:
        msg = f"no tools match"
        if domain:
            msg += f" domain={domain!r}"
        if query:
            msg += f" query={query!r}"
        return ToolResult(
            content=[TextBlock(text=msg)],
            metadata={"total": 0, "offset": offset, "returned": 0},
        )

    table, meta = _build_list_table(specs, offset=offset, limit=limit)
    prefix_parts: List[str] = [f"{meta['total']} tool(s)"]
    if domain:
        prefix_parts.append(f"domain={domain!r}")
    if query:
        prefix_parts.append(f"query={query!r}")
    if meta.get("truncated"):
        prefix_parts.append(f"showing [{offset}:{offset + meta['returned']}), next_offset={meta['next_offset']}")
    else:
        prefix_parts.append(f"showing [{offset}:{offset + meta['returned']})")
    return ToolResult(
        content=[TextBlock(text=" · ".join(prefix_parts)), table],
        metadata=meta,
    )


register_tool(
    name="meta.list_tools",
    description=(
        "List registered tools. Optional filters: ``domain`` (e.g. 'git' or "
        "'git.branch'), ``query`` (free text, matches name or description). "
        "Paginate with ``offset`` / ``limit``; ``next_offset`` in metadata "
        "when the page is truncated."
    ),
    schema={
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "description": "Filter to tools whose name starts with this prefix (exact or followed by '.').",
            },
            "query": {
                "type": "string",
                "description": "Free-text filter over tool name + description (case-insensitive).",
            },
            "offset": {"type": "integer", "minimum": 0, "default": 0},
            "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 50},
        },
        "additionalProperties": False,
    },
    handler=handle_list_tools,
    examples=[
        {
            "when": "the agent needs to find a tool but the system prompt was compressed",
            "args": {"domain": "git"},
            "result_summary": "TableBlock of git.* tools",
        }
    ],
)
