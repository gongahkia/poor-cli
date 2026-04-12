# Phase 14: Nvim Observability Panels — Diff, Timeline, Cost, Context, Savings, Watch

**Priority:** High — six user-facing panels that make poor-cli's agent loop, cost, context, and watchers legible inside Neovim.
**Estimated agents:** 6 (parallel with sub-wave sequencing on shared Lua dispatch files)
**Dependencies:** 14A stands alone; 14B blocked by PRD 025 (streaming) for liveness; 14C blocked by PRD 001 (token counts); 14D blocked by PRD 018 (ContextSnapshot); 14E blocked by 14C; 14F blocked by PRD 005 (FileWatcher).
**Philosophy:** Ship observability surfaces that turn opaque agent behavior into inspectable panels. Each panel is a right-split scratch buffer with buffer-local keymaps, backed by a narrow RPC addition. Shared Lua dispatch files (`commands.lua`, `init.lua`, `keymaps.lua`) are the collision hotspots — sequence writes to them.

---

## File-scope table

| Agent | New Lua (panels)                                             | New server files                                  | Shared Lua files touched                                   | Shared server files touched                                          |
|-------|--------------------------------------------------------------|---------------------------------------------------|------------------------------------------------------------|----------------------------------------------------------------------|
| 14A   | `panels/diff_review.lua`, `panels/diff_parser.lua`           | `poor_cli/edit_staging.py`                        | `init.lua`, `keymaps.lua`, `commands.lua`, `config.lua`    | `server/runtime.py`, `tools_async.py`, `checkpoint.py`               |
| 14B   | `panels/agent_timeline.lua`                                  | `poor_cli/tool_events.py`                         | `init.lua`, `keymaps.lua`, `commands.lua`, `lualine.lua`   | `server/runtime.py`, `core.py`                                       |
| 14C   | `panels/cost_dashboard.lua`                                  | —                                                 | `lualine.lua`, `chat.lua`, `cost.lua`, `commands.lua`      | `server/runtime.py`, `economy.py`                                    |
| 14D   | `panels/context_panel.lua`                                   | —                                                 | `commands.lua`, `context_mgr.lua`                          | `server/handlers/context.py`                                         |
| 14E   | `panels/savings_dashboard.lua`                               | —                                                 | `commands.lua`                                             | `economy.py`                                                         |
| 14F   | `panels/watch_panel.lua`                                     | —                                                 | `commands.lua`                                             | —                                                                    |

> Filename note: PRDs place new panel modules directly under `nvim-poor-cli/lua/poor-cli/`. Because six panels cluster, this phase adopts a `panels/` subdirectory (`nvim-poor-cli/lua/poor-cli/panels/<name>.lua`) to keep the module root tidy. Requires updating `require` paths in `init.lua`. If project convention already flattens, drop the `panels/` prefix.

---

## Intra-phase collision flags & sub-waves

**Hot files (multi-agent writes):**
- `nvim-poor-cli/lua/poor-cli/commands.lua` — **6/6 agents** register commands here.
- `nvim-poor-cli/lua/poor-cli/init.lua` — 14A, 14B register modules in `EAGER_SETUPS`.
- `nvim-poor-cli/lua/poor-cli/keymaps.lua` — 14A (`<leader>pv`), 14B (`<leader>pt`).
- `nvim-poor-cli/lua/poor-cli/lualine.lua` — 14B (running-tool count), 14C (cost segment).
- `poor_cli/server/runtime.py` — 14A (7 methods), 14B (5 methods + push), 14C (1 method).
- `poor_cli/economy.py` — 14C (`get_session_summary`), 14E (savings aggregation).

**Sub-wave plan:**
- **Wave 14-α (parallel, panel bodies & server primitives):** Each agent lands its panel Lua module under `panels/` and its server-side primitive (`edit_staging.py`, `tool_events.py`, new RPC handlers) in isolation. No writes to shared dispatch files yet.
- **Wave 14-β (serialized integration):** Agents land edits to `commands.lua`, `init.lua`, `keymaps.lua`, `lualine.lua`, `runtime.py`, `economy.py` in fixed order 14A → 14B → 14C → 14E → 14D → 14F. Each agent appends — no block rewrites.
- **Wave 14-γ (docs & plenary fixtures):** Tests ride in with each agent but plenary bootstrap (if PRD 065 not yet landed) is a shared prerequisite.

---

## Agent 14A: Diff Review panel with hunk-level accept / reject

**Pain points addressed:** LEARNING.md §3.1 — no visible review step before agent edits land.
**PRD wave:** 1. Blocks PRD 051 (gitsigns bridge).

### What to build

Stage agent edits in a server-side queue instead of writing immediately. Surface pending edits in a right-split **Diff Review panel** with hunk-level `ga`/`gr`/`gA`/`gR`/`gn`/`gp`/`gc` keymaps, layout toggle (unified ↔ side-by-side via `:diffthis`), and an accept-batch checkpoint labeled with the triggering prompt.

### Implementation details

1. **Server staging (`poor_cli/edit_staging.py`):** `PendingEdit{edit_id, path, original, proposed, hunks, tool_call_id, prompt}` and `Hunk{hunk_id, path, header, before, after, line_start}`. `EditStage` class: `stage / list_pending / accept_hunk / reject_hunk / accept_all / reject_all / regenerate_hunk / finalize`. Hunks computed via `difflib.unified_diff` on original vs proposed bytes. In-memory only; no disk persistence in v1.
2. **Mode branch in `tools_async.py`:** At `write_file` / `edit_file` / `apply_patch_unified`, branch on `diff_review.mode` (`auto` | `review` | `review_risky`). Default `review`. Non-interactive sessions bypass staging. `review_risky` triggers panel only when mutation exceeds `risky_line_threshold` or hits `risky_paths`.
3. **Checkpoint helper in `checkpoint.py`:** `create_for_batch(edit_id, path, label)` writes a single checkpoint per finalized batch, label = truncated user prompt + edit count.
4. **RPC (in `server/runtime.py`):** `listPendingEdits`, `previewEdit`, `acceptHunk`, `rejectHunk`, `acceptAll`, `rejectAll`, `regenerateHunk`, plus push notifications `stageEvent` and `editCommitted`.
5. **Lua parser (`panels/diff_parser.lua`):** `parse(diff_text) -> {hunks: [{hunk_id, header, before, after, line_start}]}`.
6. **Lua panel (`panels/diff_review.lua`):** Right split; header line per edit (`[N/M] path (K hunks)`); `[pending]` / `[accepted]` / `[rejected]` extmarks per hunk; buffer-local keymaps; subscribes to `stageEvent` for auto-open; `gl` cycles layout.
7. **Config (`config.lua`):** `diff_review = { mode = "review", layout = "unified", panel_position = "right", panel_width = 90, auto_open = true, risky_paths = {...}, risky_line_threshold = 50 }`.
8. **Escape hatch:** `POOR_CLI_DIFF_REVIEW=auto` env var overrides config.

### Files to create/modify

**Create (server):**
- `poor_cli/edit_staging.py` (new)
- `tests/test_edit_staging.py` (new)

**Create (Neovim):**
- `nvim-poor-cli/lua/poor-cli/panels/diff_review.lua` (new)
- `nvim-poor-cli/lua/poor-cli/panels/diff_parser.lua` (new)
- `nvim-poor-cli/tests/diff_review_spec.lua` (new)

**Modify (server, narrow):**
- `poor_cli/tools_async.py` (mode branch at edit tools)
- `poor_cli/checkpoint.py` (`create_for_batch` helper)
- `poor_cli/server/runtime.py` (register 7 RPC methods + 2 events)

**Modify (Neovim, narrow):**
- `nvim-poor-cli/lua/poor-cli/init.lua` (add `diff_review` to `EAGER_SETUPS`)
- `nvim-poor-cli/lua/poor-cli/keymaps.lua` (`<leader>pv` toggle)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (`:PoorCliReview`, `:PoorCliReviewClose`, `:PoorCliDiffLayout`)
- `nvim-poor-cli/lua/poor-cli/config.lua` (new `diff_review` table)

### Acceptance criteria

- [ ] `diff_review.mode = "review"` is default; edits stage instead of applying.
- [ ] Panel auto-opens on `stageEvent`.
- [ ] `ga` / `gr` accept/reject single hunks; `gA` / `gR` batch.
- [ ] `gc` regenerates a hunk with optional instruction via RPC.
- [ ] `gl` toggles unified ↔ side-by-side.
- [ ] Accept-batch creates one checkpoint labeled with the prompt.
- [ ] Reject-all discards with no file change and no checkpoint.
- [ ] Non-interactive sessions auto-apply with an audit-log note.
- [ ] `env POOR_CLI_DIFF_REVIEW=auto` bypasses the panel.
- [ ] Server tests: stage → accept → finalize → file written + checkpoint exists; reject-all → unchanged.
- [ ] Lua tests: parses unified diff, auto-opens on stage, `ga` marks accepted.

**PRD reference:** prd/014-diff-review-panel.md

---

## Agent 14B: Agent Timeline panel (live tool-call visualization)

**Pain points addressed:** LEARNING.md §3.2 — agent tool execution is opaque.
**PRD wave:** 1. Blocked by PRD 025 for true liveness; ships first with snapshot refresh.

### What to build

A right-split **Agent Timeline** panel that streams every tool call in the current (and scrollable earlier) turns with: tool name, args preview, status (`queued` / `running` / `done` / `failed` / `denied` / `cancelled`), duration, result preview, and token cost. Cancel running tools, retry failed ones, dismiss noisy results from future context. Lualine segment shows running-tool count.

### Implementation details

1. **Event model (`poor_cli/tool_events.py`):** `ToolEvent{event_id, turn_id, tool_call_id, tool_name, status, args_preview, args_full, started_at, ended_at, duration_ms, result_preview, result_full_size, error, cost_tokens}` plus an in-process pubsub.
2. **Emit points in `core.py`:** Single helper (`emit_tool_event`) called at every tool invocation boundary — queue, run, done, fail. Grep `execute_tool|invoke_tool|_call_tool` to find sites; do not refactor the agent loop.
3. **RPC surface (in `runtime.py`):** `listToolEvents{turnId?, limit?}`, `subscribeToolEvents` (stream), `cancelTool{eventId}`, `retryTool{eventId}`, `dismissToolResult{eventId}`.
4. **Panel (`panels/agent_timeline.lua`):** Per-turn grouped rows with status glyphs (`✓` / `⟳` / `✗`), expandable on `<CR>`, buffer-local keymaps `gc` / `gr` / `gd` / `gj` / `gk` / `gf` / `r` / `q`. Snapshot render via `listToolEvents` on open; switch to `subscribeToolEvents` push once PRD 025 lands.
5. **Lualine segment (`lualine.lua`):** `🔧 <running>/<total>` for current turn.
6. **Dismiss semantics:** `dismissToolResult` excludes that result from the next context assembly without retroactively editing audit_log.

### Files to create/modify

**Create (server):**
- `poor_cli/tool_events.py` (new)
- `tests/test_tool_events.py` (new)

**Create (Neovim):**
- `nvim-poor-cli/lua/poor-cli/panels/agent_timeline.lua` (new)
- `nvim-poor-cli/tests/agent_timeline_spec.lua` (new)

**Modify (server, narrow):**
- `poor_cli/core.py` (emit at tool boundaries via helper)
- `poor_cli/server/runtime.py` (register 5 RPC methods + subscription channel)

**Modify (Neovim):**
- `nvim-poor-cli/lua/poor-cli/init.lua` (add `agent_timeline` to `EAGER_SETUPS`)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (`:PoorCliTimeline`, `:PoorCliTimelineCancel`)
- `nvim-poor-cli/lua/poor-cli/keymaps.lua` (`<leader>pt` toggle)
- `nvim-poor-cli/lua/poor-cli/lualine.lua` (running-tool count segment)

### Acceptance criteria

- [ ] `ToolEvent` emitted on queue, run, done, fail with duration on done and error on fail.
- [ ] `cancelTool` interrupts a running tool.
- [ ] `dismissToolResult` excludes the result from future context assembly.
- [ ] Panel lists tool calls grouped by turn with status glyphs.
- [ ] Panel renders spinner for running tools; swaps to checkmark on done.
- [ ] `gc` sends cancel RPC; `gr` retries; `gd` dismisses.
- [ ] Lualine shows live running-tool count.
- [ ] Pubsub failure is non-fatal to the agent loop.

**PRD reference:** prd/015-agent-timeline-panel.md

---

## Agent 14C: Cost HUD — lualine badge, per-turn badges, dashboard

**Pain points addressed:** LEARNING.md §3.3 — cost is invisible in Neovim.
**PRD wave:** 1. Blocked by PRD 001 (token counter). Blocks PRD 041.

### What to build

Three always-on cost layers: (1) lualine segment `$0.42 · Δ$0.03 · cache 62%`; (2) per-turn virtual-text badges `[$0.02 · 1.4s · 312 tok]` at end of each chat turn; (3) rich **Cost Dashboard** buffer with per-turn sparkline, top-10 expensive tools, cache hit rate, projected $/month. Soft alarms (`vim.notify`) on session/daily thresholds, fired once per crossing.

### Implementation details

1. **Economy (`poor_cli/economy.py`):** Confirm per-turn USD/tokens/tools-used tracking; add `get_session_summary()` returning `{session: {total_usd, total_tokens{in,out,thinking,cached_read,cached_write}, turns, cache_hit_rate}, per_turn: [...], projected_monthly_usd, daily: {date -> usd}[30]}`.
2. **RPC (`runtime.py`):** Add `poor-cli/costSummary` handler returning the summary.
3. **Lualine segment (`cost.lua::component_cost()`):** Returns short string; refreshed on `PoorCliTurnEnded` autocmd.
4. **Per-turn badges (`chat.lua`):** On `PoorCliTurnEnded`, set extmark at end of user turn with dim highlight; gated by `cost.show_turn_badges`.
5. **Dashboard (`panels/cost_dashboard.lua`):** Sections — Session totals table, per-turn sparkline (Unicode block chars, no plugin dep), top-10 tools ranked by cost, cache hit rate, $/month projection at current rate and last-week average. Keys: `r` refresh, `e` export JSON, `q` close.
6. **Alarms:** Config `cost.alarm_session = 5.0`, `cost.alarm_daily = 20.0`. Track last-fired threshold per scope to avoid re-firing.

### Files to create/modify

**Create (Neovim):**
- `nvim-poor-cli/lua/poor-cli/panels/cost_dashboard.lua` (new)
- `nvim-poor-cli/tests/cost_hud_spec.lua` (new)

**Create (server):**
- `tests/test_cost_summary.py` (new)

**Modify (Neovim):**
- `nvim-poor-cli/lua/poor-cli/cost.lua` (expose `component_cost()`, turn-end badge renderer)
- `nvim-poor-cli/lua/poor-cli/lualine.lua` (include `component_cost` segment)
- `nvim-poor-cli/lua/poor-cli/chat.lua` (narrow — extmark on turn-end; do not touch streaming)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (`:PoorCliCostDashboard`)

**Modify (server):**
- `poor_cli/economy.py` (`get_session_summary()`)
- `poor_cli/server/runtime.py` (`costSummary` handler)

### Acceptance criteria

- [ ] Lualine segment shows session total, last-turn delta, cache hit rate.
- [ ] Per-turn extmark badges appear on turn end; disable via config.
- [ ] `:PoorCliCostDashboard` opens buffer with session totals, sparkline, top tools, cache rate, monthly projection.
- [ ] Alarm fires once per threshold crossing, not per turn.
- [ ] `costSummary` includes per-turn entries and projected monthly math.
- [ ] `cost.enabled = false` disables all layers.

**PRD reference:** prd/016-cost-hud.md

---

## Agent 14D: Context Explainer panel upgrade

**Pain points addressed:** LEARNING.md §3.4 — users can't see why a file is in context.
**PRD wave:** 3. Blocked by PRD 018 (ContextSnapshot).

### What to build

Replace the static `:PoorCliContext` scratch buffer with a right-split panel listing every file in the current `ContextSnapshot` with columns `path | tokens | reason | compressed? | pinned?`. Reasons: `pagerank-hub`, `recent-open`, `imported-by-target`, `pinned`, `rules`. Actions inside panel: `p` pin/unpin, `d` drop, `r` refresh, `/` filter, `o` open file.

### Implementation details

1. **RPC (`poor_cli/server/handlers/context.py`):** `poor-cli/explainContext` serializes the full `ContextSnapshot` — `{budget, used, files: [{path, tokens, reason, compressed, pinned}]}`. Reads snapshot only; does not mutate assembly.
2. **Panel (`panels/context_panel.lua`):** Right split, aligned columns, extmark icons — `📌` for pinned, `✂` for compressed. Header line shows turn id, budget, used tokens.
3. **Pin/drop wiring (`context_mgr.lua`):** `p` and `d` route through existing `/add` and `/drop` command internals rather than duplicating assembly logic. Re-render on RPC ack.
4. **Filter (`/`):** Client-side substring filter on path; does not re-fetch.

### Files to create/modify

**Create (Neovim):**
- `nvim-poor-cli/lua/poor-cli/panels/context_panel.lua` (new)
- `nvim-poor-cli/tests/context_panel_spec.lua` (new)

**Modify (Neovim):**
- `nvim-poor-cli/lua/poor-cli/commands.lua` (`:PoorCliContext` rewrites to open panel)
- `nvim-poor-cli/lua/poor-cli/context_mgr.lua` (wire `p`/`d` to existing add/drop)

**Modify (server):**
- `poor_cli/server/handlers/context.py` (add `explainContext` method; PRD 019 relocation target)

### Acceptance criteria

- [ ] Panel renders file list with tokens, reason, pinned/compressed flags.
- [ ] `p` pins/unpins and persists across turn.
- [ ] `d` drops file from next assembly.
- [ ] `/` filters visible rows client-side.
- [ ] `o` jumps to file in its own window.
- [ ] `explainContext` serializes `ContextSnapshot` without mutating selection.

**PRD reference:** prd/029-context-explainer-panel.md

---

## Agent 14E: Savings Dashboard

**Pain points addressed:** LEARNING.md §3.4 — value delivered by compaction/caching/RTK/downshift is invisible.
**PRD wave:** 3. Blocked by PRD 016 (cost HUD for shared economy aggregation).

### What to build

A **Savings Dashboard** panel showing estimated token/USD savings broken down by source — compaction, prompt caching, semantic cache, RTK filters, model downshift — with before/after deltas per session and a 30-day history sparkline. Complements (does not duplicate) the Cost Dashboard: focus is savings, not spend.

### Implementation details

1. **Aggregation (`poor_cli/economy.py`):** Add `get_savings_summary()` that reads economy and audit_log stats per event-type (`compaction_event`, `cache_hit`, `rtk_filter`, `model_downshift`). Compute estimated savings per source: for cache hits, saved tokens × provider rate; for compaction, bytes pre-minus-post × tokens-per-byte × rate; for RTK, intercepted-output token delta.
2. **RPC:** `poor-cli/savingsSummary` returns `{by_source: [{source, tokens_saved, usd_saved}], session_delta, history: {date -> usd}[30]}`.
3. **Panel (`panels/savings_dashboard.lua`):** Sections — breakdown table (source / tokens / USD), session before/after delta, 30-day sparkline (Unicode block chars). Keys: `r` refresh, `q` close.
4. **Audit-log contract:** Do not alter audit_log schema; read-only consumer.

### Files to create/modify

**Create (Neovim):**
- `nvim-poor-cli/lua/poor-cli/panels/savings_dashboard.lua` (new)
- `nvim-poor-cli/tests/savings_dashboard_spec.lua` (new)

**Modify (Neovim):**
- `nvim-poor-cli/lua/poor-cli/commands.lua` (`:PoorCliSavingsDashboard`)

**Modify (server):**
- `poor_cli/economy.py` (`get_savings_summary()` + RPC wiring)

### Acceptance criteria

- [ ] Breakdown table shows savings per source (compaction, cache, RTK, downshift).
- [ ] 30-day history sparkline rendered from audit-log aggregation.
- [ ] Session-level before/after delta visible.
- [ ] No audit-log schema changes.
- [ ] Test: `test_savings_breakdown_by_source`, `test_30_day_history_rendered`.

**PRD reference:** prd/041-savings-dashboard.md

---

## Agent 14F: Watch Status panel

**Pain points addressed:** LEARNING.md §3.4 — `/watch` and `/qa` modes run invisibly and waste spend.
**PRD wave:** 3. Blocked by PRD 005 (FileWatcher).

### What to build

A compact **Watch Status** panel listing: active watches (path, last change, matched ignore patterns), QA toggle state, and the last N triggered actions with their outcomes. Read-only — does not change watch behavior.

### Implementation details

1. **RPC (`watchStatus`):** Built on `FileWatcher` state from PRD 005. Returns `{watches: [{path, glob, last_change_at, last_match}], qa_enabled, recent_actions: [{at, trigger_path, action, outcome, duration_ms}]}`.
2. **Panel (`panels/watch_panel.lua`):** Three sections — Watches table, QA toggle indicator, Recent actions table (last 20). Keys: `r` refresh, `q` close. Pure display: no mutation keymaps.
3. **Auto-refresh:** Subscribe (if PRD 005 exposes a push event) or poll every 3s while panel is focused.

### Files to create/modify

**Create (Neovim):**
- `nvim-poor-cli/lua/poor-cli/panels/watch_panel.lua` (new)
- `nvim-poor-cli/tests/watch_panel_spec.lua` (new)

**Modify (Neovim):**
- `nvim-poor-cli/lua/poor-cli/commands.lua` (`:PoorCliWatchStatus`)

### Acceptance criteria

- [ ] Panel lists all active watches with path and last-change timestamp.
- [ ] QA toggle state visible.
- [ ] Recent triggered actions shown with outcome and duration.
- [ ] No watch behavior change (read-only).
- [ ] Tests: `test_panel_lists_active_watches`, `test_recent_triggered_actions`.

**PRD reference:** prd/042-watch-status-panel.md
