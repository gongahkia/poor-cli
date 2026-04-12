# PRD 015: Agent Timeline panel (live tool-call visualization)

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** large (1–2w)
- **Blocks:** —
- **Blocked by:** 025 (streaming tool output — for the truly live bit; panel can ship with snapshot refresh first and get live updates once 025 lands)
- **Files it mutates:**
  - `poor_cli/server/runtime.py` (narrow — new RPC methods & events)
  - `poor_cli/core.py` (narrow — emit tool-call events at tool-execution boundaries)
  - `nvim-poor-cli/lua/poor-cli/init.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `nvim-poor-cli/lua/poor-cli/keymaps.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/agent_timeline.lua`
  - `nvim-poor-cli/tests/agent_timeline_spec.lua`
  - `poor_cli/tool_events.py`
  - `tests/test_tool_events.py`

---

## 1. Problem

Today, tool execution is opaque to the user. The agent reads files, greps, calls bash, makes HTTP requests, edits files — and the user sees only the assistant's final prose in chat. Users can't tell:
- What tools were called this turn.
- On what arguments.
- How long each took.
- Whether a tool failed or was denied.

[`LEARNING.md` §3.2](../LEARNING.md): "Agentic mode is *opaque* today. Ship `:PoorCliAgentTimeline`."

The result: users don't trust the agent. They can't tell whether "this is slow because it's doing real work" or "this is broken."

## 2. Current state

Tools execute inside `core.py`'s agent loop. `tool_output_filter.py` and `audit_log.py` record events to SQLite. The Lua side extracts some tool-call references from streamed chat text (`chat.lua`), but this is heuristic and incomplete.

No first-class event stream for tool calls reaches the Lua client.

## 3. Goal & non-goals

**Goal:** a live **Agent Timeline** panel that shows every tool call in the current turn (and previous turns, scrollable) with: tool name, first-line of args, status (pending/running/done/failed/cancelled), duration, and expandable result. Users can cancel a running tool, retry a failed one, and dismiss noisy output from the model's context.

**Non-goals:**
- Do not redesign the agent loop.
- Do not introduce distributed tracing.
- Do not replace the chat panel. Timeline complements chat.

## 4. Design

### 4.1 Event model

```python
# poor_cli/tool_events.py
from dataclasses import dataclass
from typing import Literal

ToolStatus = Literal["queued","running","done","failed","denied","cancelled"]

@dataclass(frozen=True)
class ToolEvent:
    event_id: str        # uuid
    turn_id: str         # id of the agent turn
    tool_call_id: str    # id from provider's function-call
    tool_name: str
    status: ToolStatus
    args_preview: str    # first line, truncated to 120 chars
    args_full: dict      # full args (stripped of secrets)
    started_at: float | None
    ended_at: float | None
    duration_ms: int | None
    result_preview: str  # first 200 chars of stringified result
    result_full_size: int  # bytes of full result
    error: str | None
    cost_tokens: int | None  # tokens added to context by this tool's output
```

### 4.2 Emit points in `core.py`

Every tool invocation fires `on_tool_event` at: queue, run, done, fail. Emission is a single call to a pubsub that the server transport drains onto the RPC event channel.

### 4.3 RPC surface

| Method | Params | Returns |
|---|---|---|
| `poor-cli/listToolEvents` | `{turnId?, limit?}` | `{events: ToolEvent[]}` |
| `poor-cli/subscribeToolEvents` | `{}` | stream of `ToolEvent` pushes |
| `poor-cli/cancelTool` | `{eventId}` | `{cancelled: bool}` |
| `poor-cli/retryTool` | `{eventId}` | `{newEventId}` |
| `poor-cli/dismissToolResult` | `{eventId}` | `{}` — excludes result from future context |

### 4.4 Panel layout (Lua)

```
┌────── poor-cli agent timeline ──────────────────────────────┐
│ Turn 42 (session s-abc)                                     │
│                                                             │
│  ✓ 0.8s read_file docs/ROADMAP.md                           │
│        → 4,310 tok · 81% of turn budget                     │
│                                                             │
│  ⟳ 3.2s grep_files "TODO" (running…)                        │
│        cancel: gc                                           │
│                                                             │
│  ✗ 0.1s bash "git push" (denied)                            │
│        reason: network egress blocked by sandbox            │
│        retry: gr                                            │
│                                                             │
│  ✓ 2.4s edit_file poor_cli/utils.py                         │
│        hunks: 3, staged for review                          │
│        open review: <leader>pv                              │
│                                                             │
│ Turn 41 (earlier) — press [[ to collapse / ]] to expand     │
└─────────────────────────────────────────────────────────────┘
```

### 4.5 Keymaps (buffer-local, inside the panel)

| Key | Action |
|---|---|
| `<CR>` | Expand/collapse event (full args + result) |
| `gc` | Cancel running tool |
| `gr` | Retry failed tool |
| `gd` | Dismiss result (don't feed to model on subsequent turns) |
| `gj` | Next event |
| `gk` | Previous event |
| `gf` | If tool was a file op, jump to file |
| `r` | Manual refresh |
| `q` | Close |

### 4.6 Status-line integration

Lualine segment (via `poor-cli/lualine.lua`) shows current turn's `running` tool count: e.g., `🔧 2/5`.

### 4.7 Streaming behavior

Panel subscribes to `poor-cli/subscribeToolEvents`. Each push updates or inserts a row. Pending tools appear immediately; status updates in place (no re-render of the whole panel).

## 5. Files to create / modify / delete

**Create (server)**
- `poor_cli/tool_events.py` — `ToolEvent`, pubsub.
- `tests/test_tool_events.py`

**Create (Neovim)**
- `nvim-poor-cli/lua/poor-cli/agent_timeline.lua`
- `nvim-poor-cli/tests/agent_timeline_spec.lua`

**Modify (server, narrow)**
- `poor_cli/core.py` — emit events at tool boundaries. **Use a thin helper**; do not otherwise refactor.
- `poor_cli/server/runtime.py` — register 5 new RPC methods; plumb the subscription channel.

**Modify (Neovim)**
- `lua/poor-cli/init.lua` — add module to `EAGER_SETUPS`.
- `lua/poor-cli/commands.lua` — `:PoorCliTimeline`, `:PoorCliTimelineCancel`.
- `lua/poor-cli/keymaps.lua` — `<leader>pt` toggles.
- `lua/poor-cli/lualine.lua` — running-tool count segment.

## 6. Implementation plan

1. Land `tool_events.py` + pubsub. Unit test.
2. Hook emission into `core.py` at every tool-invocation boundary (queue, run, done, fail). Use a single helper function so we don't sprinkle logic. **Grep `execute_tool|invoke_tool|_call_tool` in core.py to find the sites.**
3. Register RPC methods & push channel.
4. Lua: implement `agent_timeline.lua` with snapshot refresh (`listToolEvents`) first.
5. Wire subscribe; convert to live updates.
6. Add status-line integration.
7. Add keymaps for cancel/retry/dismiss — these require server-side hooks (`cancelTool`, `retryTool`, `dismissToolResult`).
8. Tests; manual verification on a multi-tool prompt.

## 7. Testing & acceptance criteria

**Server tests**
- `test_tool_event_emitted_on_queue_and_run_and_done`
- `test_tool_event_contains_duration_on_done`
- `test_tool_event_contains_error_on_failure`
- `test_cancel_tool_interrupts_running`
- `test_dismiss_excludes_result_from_future_context`

**Lua tests**
- `renders pending tool as spinner`
- `swaps spinner for checkmark on done event`
- `gc sends cancel RPC`

**Manual verification**
- Prompt the agent with "summarize docs/MULTIPLAYER.md and tell me what's new" — observe: read_file appears running, turns to done, result preview shows token count.
- Prompt "run pytest" with a long-running process — observe `⟳` spinner, press `gc`, observe `cancelled`.

**Done criterion**
- [ ] Timeline panel opens and lists tool calls.
- [ ] Live updates work (post-PRD 025).
- [ ] Cancel / retry / dismiss RPCs work.
- [ ] Status-line running-tool count.

## 8. Rollback / risk

Low. Additive. Disabling is one config flag. Pubsub failure must be non-fatal to the agent loop.

## 9. Out-of-scope & boundary

- 🚫 Do not refactor `core.py` broadly.
- 🚫 Do not modify the tool schemas themselves.
- 🚫 Do not persist the timeline across sessions (audit_log already handles that).

## 10. Related PRDs & references

- PRD 025 (streaming tool output) is the "live" dependency; panel can launch with snapshot refresh and gain liveness after.
- PRD 028 (tool output schema filter) reshapes what goes into `result_preview`.
- LEARNING.md §3.2.
