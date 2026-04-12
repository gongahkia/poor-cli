# PRD 016: Cost HUD — lualine badge, per-turn badges, dashboard

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (4–5d)
- **Blocks:** 041
- **Blocked by:** 001 (for accurate token counting)
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/lualine.lua`
  - `nvim-poor-cli/lua/poor-cli/chat.lua` (narrow — add per-turn cost extmarks)
  - `nvim-poor-cli/lua/poor-cli/cost.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `poor_cli/server/runtime.py` (narrow — one new RPC method)
  - `poor_cli/economy.py`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/cost_dashboard.lua`
  - `nvim-poor-cli/tests/cost_hud_spec.lua`
  - `tests/test_cost_summary.py`

---

## 1. Problem

Cost transparency is the project's stated differentiator (`/broke`, `/my-treat`, `/economy`, `/savings`). But users can't see cost. [`LEARNING.md` §3.3](../LEARNING.md): "Cost is invisible in Neovim today." The lualine segment is minimal; `/cost` opens a scratch buffer users rarely visit.

## 2. Current state

- `lua/poor-cli/cost.lua` — opens a scratch buffer with session summary.
- `lua/poor-cli/lualine.lua` — segment shows provider + inline state + compaction badge; no cost.
- `poor_cli/economy.py` — tracks spend but doesn't expose a `/costSummary` RPC.

## 3. Goal & non-goals

**Goal:** three layers of cost visibility, always on:
1. **Lualine segment** `$0.42 · Δ$0.03 · cache 62%` (session $, last turn delta, cache hit rate).
2. **Per-message badges** — virtual text at the end of each chat turn: `[$0.02 · 1.4s · 312 tok]`.
3. **Dashboard** — `:PoorCliCostDashboard` rich buffer with sparkline of $/turn, top-10 expensive tools, cache hit/miss, projected $/month at current rate.

Also: **soft cost alarms**: config `cost.alarm_session = 5.0`, `cost.alarm_daily = 20.0`; emit a `vim.notify` warning when crossed.

**Non-goals:**
- Do not implement hard cost caps (stretch goal; too disruptive for v1).
- Do not integrate external billing APIs.

## 4. Design

### 4.1 Server-side

New RPC method in `runtime.py`:

```
poor-cli/costSummary → {
    session: {
        total_usd: number,
        total_tokens: {in, out, thinking, cached_read, cached_write},
        turns: Turn[],
        cache_hit_rate: number,
    },
    per_turn: Array<{
        turn_id, started_at, ended_at, duration_ms,
        usd, tokens_in, tokens_out,
        tools_used: {name, count, total_usd}[]
    }>,
    projected_monthly_usd: number,
    daily: {date -> usd}[30]
}
```

### 4.2 Lualine segment

`cost.lua` exposes `component_cost()` returning a short string for lualine. Updates on event `PoorCliTurnEnded`.

### 4.3 Per-turn badges

`chat.lua` hooks `PoorCliTurnEnded` and sets an extmark at the end of the user turn: `[$0.02 · 1.4s · 312 tok]` in a dim highlight. Dismissable globally via `cost.show_turn_badges = false`.

### 4.4 Dashboard (`cost_dashboard.lua`)

A scratch buffer with sections:
- **Session totals** table.
- **Spark chart** for last N turns (using Unicode block characters, no plugin dep).
- **Top tools** table ranked by cost.
- **Cache** hit rate.
- **Projection** — $/month at current rate and at last-week's average.

Keys: `r` refresh, `e` export JSON, `q` close.

### 4.5 Soft alarms

When session total crosses `alarm_session`, emit `vim.notify("poor-cli: session cost has crossed $X", vim.log.levels.WARN)`. Track firing so the same threshold doesn't re-fire every turn.

## 5. Files to create / modify / delete

**Create (Neovim)**
- `nvim-poor-cli/lua/poor-cli/cost_dashboard.lua`
- `nvim-poor-cli/tests/cost_hud_spec.lua`

**Create (server)**
- `tests/test_cost_summary.py`

**Modify (Neovim)**
- `lua/poor-cli/cost.lua` — expose `component_cost()` for lualine; listen for `PoorCliTurnEnded`; implement badge renderer.
- `lua/poor-cli/lualine.lua` — include `component_cost` segment.
- `lua/poor-cli/chat.lua` — narrow: extmark per turn on turn-end event. Do not touch streaming logic.
- `lua/poor-cli/commands.lua` — `:PoorCliCostDashboard`.

**Modify (server)**
- `poor_cli/economy.py` — ensure it tracks per-turn USD, tokens, tools-used. Add `get_session_summary()`.
- `poor_cli/server/runtime.py` — add `poor-cli/costSummary` handler.

## 6. Implementation plan

1. Audit `economy.py` — confirm per-turn tracking exists; fill gaps.
2. Add `costSummary` RPC.
3. Implement `cost.lua::component_cost()`; wire into lualine.
4. Add turn-end extmark badges in `chat.lua`.
5. Implement `cost_dashboard.lua`.
6. Add alarm logic.
7. Tests: server-side summary; Lua renders.
8. Manual verification across a 5-turn session.

## 7. Testing & acceptance criteria

**Server tests**
- `test_cost_summary_includes_per_turn`
- `test_cost_summary_projected_monthly_math`
- `test_cache_hit_rate_computed`

**Lua tests**
- `component_cost returns formatted string`
- `turn badge extmark set on turn-end event`
- `dashboard opens and refreshes`

**Manual**
- 5-turn session; dashboard shows all 5 turns with non-zero cost.
- Cross alarm threshold → notify fires once.

**Done criterion**
- [ ] Lualine shows session + delta + cache rate.
- [ ] Per-turn badges visible.
- [ ] Dashboard renders with real data.
- [ ] Alarms fire and don't spam.

## 8. Rollback / risk

Low. Additive. Disable all layers with `cost.enabled = false`.

## 9. Out-of-scope & boundary

- 🚫 Do not change economy policy logic.
- 🚫 Do not change provider cost tables.
- 🚫 Do not build a pre-request cost estimator in this PRD.

## 10. Related PRDs & references

- PRD 001 (token counter — required for accurate numbers).
- PRD 041 (Savings Dashboard — related surface, later wave).
- LONGTERM-TODO M2.
- LEARNING.md §3.3.
