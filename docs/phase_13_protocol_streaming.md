# Phase 13: Protocol & Streaming

**Priority:** High — protocol-level upgrades (MCP 2026), long-running tool liveness (streaming), and a first real shell-output reducer (RTK-lite). Together they close LEARNING.md §2.1 (no tool streaming), §2.2 (MCP transport + shipping RTK), and target PAIN-POINTS.md #9.
**Estimated agents:** 3 (one full collision — see sub-waves below)
**Dependencies:** 13B is blocked by PRD 019 (server tool handlers must exist); 13A blocks PRD 035 (MCP registry UI). 13C is independent.
**Philosophy:** Standards compliance where upstream has moved (MCP 2026 drops SSE for Streamable HTTP), liveness where users currently stare at blank timelines, and one concrete high-ROI filter where RTK has sat as a 2-line stub for too long. No Rust binary in this phase.

---

## File-scope table (at-a-glance disjointness)

| Agent | Creates (new files)                                                                                                                                                       | Modifies (existing files)                                                                                 |
|-------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| 13A   | `poor_cli/mcp/__init__.py`, `poor_cli/mcp/transport_stdio.py`, `poor_cli/mcp/transport_http.py`, `poor_cli/mcp/registry.py`, `poor_cli/mcp/multi_server.py`, `tests/test_mcp_transport.py`, `tests/test_mcp_multi_server.py` | `poor_cli/mcp_client.py`, `poor_cli/mcp_scaffold.py`                                                      |
| 13B   | `poor_cli/tool_stream.py`, `tests/test_tool_stream.py`                                                                                                                    | `poor_cli/tools_async.py`, `poor_cli/tool_dispatch.py`, `poor_cli/server/handlers/tools.py`               |
| 13C   | `poor_cli/rtk_lite/__init__.py`, `poor_cli/rtk_lite/git_filter.py`, `poor_cli/rtk_lite/npm_filter.py` (stretch), `poor_cli/rtk_lite/cargo_filter.py` (stretch), `tests/test_rtk_lite_git.py` | `poor_cli/tools_async.py`, `poor_cli/tool_output_filter.py`                                               |

### Intra-phase collisions

- **`poor_cli/tools_async.py`** — shared by **13B** (adds `stream_call` on bash/run_tests/process_logs) and **13C** (wraps `bash` return with `rtk_lite.apply`). Both edits land on the `bash` tool but at different layers (stream path vs. post-process filter).

### Proposed sub-waves

- **Sub-wave α (parallel):** 13A (isolated to `mcp_client.py`, `mcp_scaffold.py`, new `mcp/` package) can run fully in parallel with anything.
- **Sub-wave β (serial):** 13B lands first on `tools_async.py`, establishing the streaming contract and the stream/non-stream branch in the bash tool. 13C then rebases and places `rtk_lite.apply(cmd, raw)` on both branches (stream aggregation result and non-stream `ToolResult.output`). This ordering is chosen because streaming structure is the more invasive change; layering a pure function filter on top is additive.

If schedule pressure demands parallelism on β, the two agents can split `tools_async.py` by explicit line-range contract: 13B owns the dispatch/`stream_call` additions, 13C owns the `ToolResult` construction site — but a final reconciliation pass is required.

---

## Agent 13A: MCP 2026 Compliance — Streamable HTTP, Multi-Server, Registry

**Pain points addressed:** LEARNING.md §2.2, §4 — single-server stdio-only MCP is already behind the 2026 spec; no registry awareness; tool-name conflicts unsolvable.
**Solution reference:** PRD 024.
**Expected outcome:** `poor_cli/mcp/` package with two transports, multi-server aggregation with `<server>:<tool>` namespacing, and optional on-demand pulls from the official MCP registry.

### What to build

Replace `mcp_client.py`'s ~200-line single-server stdio client with a proper `poor_cli/mcp/` package. Support both stdio and MCP 2026 Streamable HTTP (SSE is deprecated — do not implement it). Load a list of servers from `.poor-cli/mcp.json`, start them in parallel, aggregate their tools under `<server>:<tool>` names, and route `call_tool` to the right server. Add a lazy registry client gated behind a `registry_autodiscover` flag.

### Implementation details

1. **Transport abstraction** — define `McpTransport(ABC)` with `connect`, `send`, `recv`, `close`. Extract the existing stdio logic from `mcp_client.py` into `mcp/transport_stdio.py` as `StdioTransport`. Implement `StreamableHttpTransport` in `mcp/transport_http.py` per the MCP 2026 spec.
2. **Server spec dataclass** — `McpServerSpec(name, transport, command|url, env, enabled)`.
3. **MultiMcp orchestrator** — `start_all(specs)`, `tools()` returning namespaced tool dicts, `call_tool(namespaced_name, args)` dispatch, `health()` per-server boolean map.
4. **Config loader** — read `.poor-cli/mcp.json`. Expand `${ENV_VAR}` in the env map. Skip servers with `enabled: false`.
5. **Registry client** — `mcp/registry.py` hits `https://registry.modelcontextprotocol.io/` on demand only; never at startup. Flag defaults to `false`.
6. **Legacy compatibility** — keep single-server path working behind a `multi: false` flag for the first release. `mcp_scaffold.py` routes to either the legacy client or `MultiMcp`.
7. **Tool-call routing** — a tool name containing `:` routes by prefix; a bare name routes to the single-server legacy path.

### Files to create/modify

- `poor_cli/mcp/__init__.py` (new)
- `poor_cli/mcp/transport_stdio.py` (new — extracted from `mcp_client.py`)
- `poor_cli/mcp/transport_http.py` (new — Streamable HTTP)
- `poor_cli/mcp/registry.py` (new — lazy)
- `poor_cli/mcp/multi_server.py` (new)
- `poor_cli/mcp_client.py` (modify — thin compatibility shim)
- `poor_cli/mcp_scaffold.py` (modify — route legacy vs multi)
- `tests/test_mcp_transport.py` (new)
- `tests/test_mcp_multi_server.py` (new)

### Acceptance criteria

- [ ] Stdio and Streamable HTTP transports both pass round-trip tests against mock servers.
- [ ] Multi-server loader starts servers concurrently from `.poor-cli/mcp.json`.
- [ ] Tools are aggregated and namespaced as `<server>:<tool>`; no name collisions possible.
- [ ] `health()` reports per-server liveness.
- [ ] SSE transport is not implemented (deprecated in MCP 2026).
- [ ] Registry pulls happen only when `registry_autodiscover: true` and only on demand.
- [ ] Legacy single-server behavior preserved behind `multi: false`.

**PRD reference:** prd/024-mcp-2026-compliance.md

---

## Agent 13B: Streaming Tool Output with Backpressure

**Pain points addressed:** LEARNING.md §2.1 — a 10K-line `cargo test` failure blocks both the server and the user until every byte is collected; no mid-tool liveness for the Lua timeline.
**Solution reference:** PRD 025.
**Expected outcome:** long-running tools push output chunks through the server pubsub to the Lua client in real time, with consumer-driven backpressure and clean cancellation. The model still sees a single aggregated, budget-capped final result.

### What to build

Introduce a `StreamingToolResult(AsyncIterator[str])` contract. Add `stream_call()` to the three chattiest tools: `bash`, `run_tests`, `process_logs`. Route streaming tools through a stream path in `tool_dispatch.py`. Have the server handler push chunks to subscribers, enforce a ≤16-chunk buffer, and await consumer acks via `poor-cli/toolStreamAck`. On `poor-cli/cancelTool`, abort the iterator and SIGTERM → SIGKILL the subprocess after 3 s. When the stream ends, aggregate chunks into one `ToolResult` truncated to the tool's context-size budget before handing anything to the model.

### Implementation details

1. **Streaming contract** — `poor_cli/tool_stream.py` defines `StreamingToolResult` with `__aiter__` for chunks and `final() -> ToolResult` for the aggregated end state.
2. **Tool-side `stream_call`** — `tools_async.py::bash`, `run_tests`, `process_logs` expose both the existing synchronous `call()` and the new `stream_call()`. `stream_call` reads subprocess stdout line-by-line (or in fixed byte chunks) and yields.
3. **Dispatch routing** — `tool_dispatch.py` checks for `stream_call` on the tool and routes accordingly; non-streaming tools continue through the legacy path untouched.
4. **Server backpressure** — `server/handlers/tools.py` buffers at most 16 chunks per tool-invocation. On buffer full, `await` the consumer ack. Ack messages include `{eventId, chunksProcessed}`.
5. **Cancellation** — tie into the `poor-cli/cancelTool` RPC added by PRD 015. Abort the async iterator, send SIGTERM to the subprocess, escalate to SIGKILL after 3 s.
6. **Aggregation rule** — never feed partial chunks to the model; collect all chunks into the final `ToolResult.output`, then truncate to the tool's configured budget (with a clear `[...truncated N lines...]` marker).
7. **Tool selection** — only stream tools that can produce large or slow output. `file_read`, `edit`, and similar return fast — leave them alone.

### Files to create/modify

- `poor_cli/tool_stream.py` (new)
- `tests/test_tool_stream.py` (new)
- `poor_cli/tools_async.py` (modify — add `stream_call` on bash, run_tests, process_logs)
- `poor_cli/tool_dispatch.py` (modify — route streaming tools through the stream path)
- `poor_cli/server/handlers/tools.py` (modify — push chunks; handle ack)

### Acceptance criteria

- [ ] `test_stream_produces_chunks` passes against a synthetic slow process.
- [ ] `test_backpressure_blocks_when_unacked` — producer awaits once the 16-chunk buffer is full.
- [ ] `test_cancel_kills_subprocess` — SIGTERM then SIGKILL within 3 s.
- [ ] `test_final_aggregation_truncated_to_budget` — model-facing output never exceeds the tool's context budget.
- [ ] Integration test with `yes | head -n 10000` completes without blocking server or user.
- [ ] Streaming partials are never sent to the LLM mid-call.
- [ ] Non-streamable tools unaffected.

**PRD reference:** prd/025-streaming-tool-output.md

---

## Agent 13C: RTK-lite — Python-Side Shell Output Filter

**Pain points addressed:** PAIN-POINTS.md #9 (ambient noise pollution); LEARNING.md §2.2 ("ship one piece of RTK").
**Solution reference:** PRD 026.
**Expected outcome:** The `bash` tool recognizes a small set of high-signal commands (starting with `git status`) and post-processes their output with purpose-built filters. ≥60% token reduction on `git status` fixtures with every changed path preserved. Python-only — no Rust binary in this PRD.

### What to build

A small filter registry under `poor_cli/rtk_lite/`. Each filter is a `Callable[[str], str]` registered against a command pattern. The `bash` tool calls `rtk_lite.apply(cmd, raw)` on the subprocess output before returning. Ship `git status`, `git diff --stat`, and `ls -la` filters in this PRD; `npm install` and `cargo build` are stretch. If a filter raises or parsing fails, return the raw output unchanged.

### Implementation details

1. **Registry** — `poor_cli/rtk_lite/__init__.py` exposes `register(pattern)` decorator, a `REGISTRY` dict, and an `apply(command, output) -> str` function that picks the best-matching registered filter (longest prefix match) and passes through on no match.
2. **`git_filter.py`** — implement `filter_git_status`: preserve branch, ahead/behind, file counts per category, first-N changed paths (configurable, default all). Drop advisory prose ("use `git restore`..."), heading decoration, blank-line padding. Also implement `git diff --stat` and `ls -la` filters.
3. **Bash integration** — `tools_async.py::bash` calls `rtk_lite.apply(cmd, raw)` post-subprocess. Attach `meta={"rtk_reduction_pct": ...}` for observability. Coordinate with Agent 13B's stream path: on streaming completion, apply the filter to the aggregated final output (not per-chunk).
4. **Escape path** — every filter wraps its parser in try/except; on any failure, return raw output and log.
5. **Opt-out** — honor a config flag `rtk_lite.enabled` (default `true`). When false, `apply` is a pass-through.
6. **Fixtures** — `tests/fixtures/rtk_lite/*.txt` with real captured outputs for representative repos.
7. **Boundary** — do not delete `rtk_integration.py` (that stub is coordinated by PRD 007). Do not hook shell aliases. Do not filter arbitrary commands.

### Files to create/modify

- `poor_cli/rtk_lite/__init__.py` (new — registry)
- `poor_cli/rtk_lite/git_filter.py` (new — git status, git diff --stat, ls -la)
- `poor_cli/rtk_lite/npm_filter.py` (new — stretch)
- `poor_cli/rtk_lite/cargo_filter.py` (new — stretch)
- `tests/test_rtk_lite_git.py` (new)
- `poor_cli/tools_async.py` (modify — wrap `bash` return with `rtk_lite.apply`)
- `poor_cli/tool_output_filter.py` (modify — surface `rtk_lite` alongside the existing JSON/YAML filter path)

### Acceptance criteria

- [ ] `test_git_status_filter_reduces_tokens_by_60_percent_on_fixture` passes.
- [ ] `test_git_status_filter_preserves_all_changed_paths` passes.
- [ ] `test_unknown_command_passthrough` — commands with no registered filter return raw output byte-for-byte.
- [ ] `test_bash_tool_reports_reduction_in_meta` — `meta.rtk_reduction_pct` populated.
- [ ] Filter failures fall back to raw output without raising.
- [ ] `rtk_lite.enabled = false` in config disables all filters.
- [ ] No Rust binary introduced; no `rtk_integration.py` deletion.

**PRD reference:** prd/026-rtk-lite-shell-filter.md
