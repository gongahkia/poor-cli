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

import time
from typing import Any, Dict, List, Optional

from poor_cli.tool_circuit import get_circuit
from poor_cli.tool_blocks import CodeBlock, TableBlock, TextBlock, ToolResult
from poor_cli.tool_health import snapshot as health_snapshot, snapshots as all_health_snapshots
from poor_cli.tool_rate_limit import get_limiter as get_tool_rate_limiter
from poor_cli.tool_prompt_gen import describe_registry_tool
from poor_cli.tools._registry import ToolSpec, all_tools, get as registry_get, register_tool


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
        msg = "no tools match"
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


async def handle_what_changed(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    recorder = getattr(ctx, "session_recorder", None)
    if recorder is None:
        return ToolResult.text(
            "no session_recorder on ctx (this session doesn't track file changes)"
        )
    rows_data = recorder.file_writes()
    if not rows_data:
        return ToolResult.text("no files touched by mutating tools this session yet")
    rows = [[r["path"], r["first_touched_by"], str(r["touches"])] for r in rows_data]
    return ToolResult(
        content=[
            TextBlock(
                text=f"{len(rows)} file(s) touched by mutating tool calls "
                "(declared args only — subprocess side effects not tracked)"
            ),
            TableBlock(columns=["path", "first_touched_by", "touches"], rows=rows),
        ],
        metadata={"files_touched": len(rows), "session_total_calls": len(recorder.records)},
    )


register_tool(
    name="meta.what_changed",
    description=(
        "Return files touched by the agent's mutating tool calls this session "
        "(git.stage, hunks.stage/reset, fs.write, etc.). Declared-args-only — "
        "subprocess side effects (task.run, deploy.run) aren't tracked. Use "
        "this to answer 'what have I changed?' without re-running git.status."
    ),
    schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
    handler=handle_what_changed,
    examples=[
        {
            "when": "before drafting a commit message, agent wants to review its own edits",
            "args": {},
            "result_summary": "TableBlock listing paths with first_touched_by tool",
        }
    ],
    circuit_disabled=True,
)


def _fmt_ts(at: float) -> str:
    """Relative time like '12s', '3m42s', '1h5m'. Frugal: shorter than
    absolute timestamps, agent can reason about recency directly."""
    delta = max(0.0, time.time() - at)
    if delta < 60:
        return f"{int(delta)}s"
    if delta < 3600:
        return f"{int(delta // 60)}m{int(delta % 60)}s"
    return f"{int(delta // 3600)}h{int((delta % 3600) // 60)}m"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.0f}%"


def _fmt_ms(value: Optional[int]) -> str:
    if value is None:
        return "-"
    return f"{value}ms"


def _feature_flag(ctx: Any, name: str, default: bool = True) -> bool:
    tools_cfg = getattr(getattr(ctx, "config", None), "tools", None)
    if tools_cfg is None:
        return default
    value = getattr(tools_cfg, name, None)
    if value is None:
        return default
    return bool(value)


def _circuit_state(ctx: Any, spec: Optional[ToolSpec]) -> Dict[str, Any]:
    if spec is None or spec.circuit_disabled or not _feature_flag(ctx, "circuit_breakers", True):
        return {"state": "disabled", "open": False, "retry_after_s": 0.0}
    circuit = get_circuit(ctx, create=False)
    if circuit is None:
        return {"state": "closed", "open": False, "retry_after_s": 0.0}
    return circuit.state(spec.name, spec)


def _rate_usage(ctx: Any, spec: Optional[ToolSpec]) -> Optional[Dict[str, float]]:
    if spec is None or spec.max_per_minute is None or not _feature_flag(ctx, "rate_limits", True):
        return None
    limiter = get_tool_rate_limiter(ctx, create=False)
    if limiter is None:
        return {
            "used": 0.0,
            "max": float(spec.max_per_minute),
            "remaining": float(spec.max_per_minute),
            "retry_after_s": 0.0,
        }
    return limiter.usage(spec.name, max_per_minute=spec.max_per_minute)


async def handle_health(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    tool = args.get("tool")
    if tool is not None and not isinstance(tool, str):
        return ToolResult.error("tool must be a string")
    try:
        window_s = float(args.get("window_s", 3600.0) or 3600.0)
    except (TypeError, ValueError):
        return ToolResult.error("window_s must be a number")
    window_s = max(1.0, min(window_s, 86400.0))

    if tool:
        snap = health_snapshot(tool, window_s=window_s)
        if snap is None:
            return ToolResult.text(
                f"no health data for {tool!r} (tool has not been dispatched this session)"
            )
        spec = registry_get(tool)
        circuit_state = _circuit_state(ctx, spec)
        rate_usage = _rate_usage(ctx, spec)
        # Single-tool snapshot → CodeBlock(json-ish) for the agent to parse.
        lines = [
            f"name: {snap['name']}",
            f"total: {snap['total']} (successes={snap['successes']} failures={snap['failures']})",
            f"success_rate: {_fmt_pct(snap['success_rate'])}",
            f"window_s: {int(snap['window_s'])}",
            f"window_total: {snap['window_total']} window_success_rate: {_fmt_pct(snap['window_success_rate'])}",
            f"p50: {_fmt_ms(snap['p50_ms'])}",
            f"p95: {_fmt_ms(snap['p95_ms'])}",
            (
                f"circuit: {circuit_state.get('state')} "
                f"(open={bool(circuit_state.get('open'))}, "
                f"retry_after_s={float(circuit_state.get('retry_after_s', 0.0) or 0.0):.1f})"
            ),
        ]
        if rate_usage is not None:
            lines.append(
                "rate_limit: "
                f"{int(rate_usage['used'])}/{int(rate_usage['max'])} in last 60s "
                f"(remaining={int(rate_usage['remaining'])}, "
                f"retry_after_s={float(rate_usage['retry_after_s']):.1f})"
            )
        if snap["recent_errors"]:
            lines.append("recent_errors:")
            for err in snap["recent_errors"][-5:]:
                lines.append(f"  - ts={int(err['at'])}, retries={err.get('retry_attempts', 0)},"
                             f" timeout={err.get('timeout', False)}, excerpt={err.get('excerpt', '')!r}")
        metadata = dict(snap)
        metadata["circuit"] = circuit_state
        if rate_usage is not None:
            metadata["rate_limit"] = rate_usage
        return ToolResult(
            content=[CodeBlock(language="text", code="\n".join(lines))],
            metadata=metadata,
        )

    # Multi-tool summary
    snaps = all_health_snapshots(window_s=window_s)
    if not snaps:
        return ToolResult.text("no tool-health data this session yet")
    snaps.sort(key=lambda s: s["name"])
    rows: List[List[str]] = []
    for snap in snaps:
        spec = registry_get(snap["name"])
        circuit_state = _circuit_state(ctx, spec)
        rate_usage = _rate_usage(ctx, spec)
        if rate_usage is None:
            rate_cell = "-"
        else:
            rate_cell = f"{int(rate_usage['used'])}/{int(rate_usage['max'])}"
        rows.append([
            snap["name"],
            str(snap["total"]),
            _fmt_pct(snap["success_rate"]),
            _fmt_pct(snap["window_success_rate"]),
            _fmt_ms(snap["p50_ms"]),
            _fmt_ms(snap["p95_ms"]),
            str(circuit_state.get("state", "closed")),
            rate_cell,
        ])
    return ToolResult(
        content=[
            TextBlock(text=f"{len(snaps)} tool(s) tracked · window={int(window_s)}s"),
            TableBlock(
                columns=["tool", "total", "success", "win_success", "p50", "p95", "circuit", "rate"],
                rows=rows,
            ),
        ],
        metadata={"tools_tracked": len(snaps), "window_s": int(window_s)},
    )


register_tool(
    name="meta.health",
    description=(
        "Return per-tool health: success rate, p50/p95 latency, recent "
        "errors. Pass ``tool`` for one tool's detailed snapshot; omit for "
        "a summary table over all tools that have dispatched this session. "
        "``window_s`` (default 3600) sets the rolling window for the "
        "windowed success rate."
    ),
    schema={
        "type": "object",
        "properties": {
            "tool": {"type": "string"},
            "window_s": {"type": "number", "minimum": 1, "maximum": 86400, "default": 3600},
        },
        "additionalProperties": False,
    },
    handler=handle_health,
    examples=[
        {
            "when": "agent notices repeated failures and wants to know if a tool is broken",
            "args": {"tool": "git.push"},
            "result_summary": "CodeBlock with success_rate, p50/p95, recent errors",
        }
    ],
    circuit_disabled=True,
)


async def handle_call_history(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    recorder = getattr(ctx, "session_recorder", None)
    if recorder is None:
        return ToolResult.text(
            "no session_recorder on ctx (this session doesn't record tool calls)"
        )
    try:
        n = int(args.get("n", 20) or 20)
    except (TypeError, ValueError):
        return ToolResult.error("n must be an integer")
    n = max(1, min(n, 500))
    tool_filter = args.get("tool")
    if tool_filter is not None and not isinstance(tool_filter, str):
        return ToolResult.error("tool must be a string")
    calls = recorder.recent(n=n, tool_filter=tool_filter)
    if not calls:
        prefix = "no tool calls this session"
        if tool_filter:
            prefix = f"no calls to tool {tool_filter!r} this session"
        return ToolResult.text(prefix)
    rows = [
        [
            call.tool,
            call.outcome,
            str(call.rec.wall_time_ms),
            str(call.rec.retry_attempts),
            _fmt_ts(call.at),
        ]
        for call in calls
    ]
    prefix = f"last {len(calls)} call(s)"
    if tool_filter:
        prefix += f" filtered by tool={tool_filter!r}"
    prefix += f" · session started {_fmt_ts(recorder.started_at)} ago"
    return ToolResult(
        content=[
            TextBlock(text=prefix),
            TableBlock(columns=["tool", "outcome", "wall_ms", "retries", "ago"], rows=rows),
        ],
        metadata={"returned": len(calls), "session_total": len(recorder.records)},
    )


register_tool(
    name="meta.call_history",
    description=(
        "Return the most recent tool-call records from this session: tool, "
        "outcome (ok/err/timeout/degraded), wall-time ms, retries, relative "
        "time. Use this to answer 'what did I just do?' without keeping the "
        "tool trace in model context. Filter by exact tool name with ``tool``."
    ),
    schema={
        "type": "object",
        "properties": {
            "n": {"type": "integer", "minimum": 1, "maximum": 500, "default": 20},
            "tool": {
                "type": "string",
                "description": "Exact tool name. Omit to include all tools.",
            },
        },
        "additionalProperties": False,
    },
    handler=handle_call_history,
    examples=[
        {
            "when": "the agent needs to reference a recent git.status without re-running",
            "args": {"tool": "git.status", "n": 1},
            "result_summary": "TableBlock of 1 git.status call + timestamp",
        }
    ],
    circuit_disabled=True,
)


async def handle_describe_tool(*, ctx: Any, args: Dict[str, Any]) -> ToolResult:
    name = args.get("name")
    if not isinstance(name, str) or not name.strip():
        return ToolResult.error("name is required")
    spec = registry_get(name.strip())
    if spec is None:
        # Provide a helpful nudge: list-tools with a query-matching suggestion.
        suggestions: List[str] = []
        needle = name.split(".", 1)[0].lower()
        for candidate in all_tools():
            if needle and needle in candidate.lower():
                suggestions.append(candidate)
                if len(suggestions) >= 5:
                    break
        msg = f"unknown tool {name!r}"
        if suggestions:
            msg += f"\nsimilar: {', '.join(sorted(suggestions))}"
        return ToolResult.error(msg, unknown_tool=True)
    markdown = describe_registry_tool(spec)
    return ToolResult(
        content=[CodeBlock(language="markdown", code=markdown.rstrip())],
        metadata={
            "name": spec.name,
            "exclusive": spec.exclusive,
            "timeout_s": spec.timeout_s,
            "has_examples": bool(spec.examples),
        },
    )


register_tool(
    name="meta.describe_tool",
    description=(
        "Return the full schema + examples for one tool by name. Use this "
        "when meta.list_tools' one-line summary isn't enough to construct "
        "a valid call."
    ),
    schema={
        "type": "object",
        "required": ["name"],
        "properties": {
            "name": {
                "type": "string",
                "description": "Exact tool name, e.g. 'git.commit'.",
            },
        },
        "additionalProperties": False,
    },
    handler=handle_describe_tool,
    examples=[
        {
            "when": "the agent needs the schema of a rarely-used tool",
            "args": {"name": "git.push"},
            "result_summary": "CodeBlock (markdown) with args + examples",
        }
    ],
    cacheable=True,
    cache_ttl_s=300.0,
    circuit_disabled=True,
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
    cacheable=True,
    cache_ttl_s=300.0,
    circuit_disabled=True,
)
