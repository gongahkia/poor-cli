# PRD 041: Savings Dashboard

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (4d)
- **Blocked by:** 016
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `poor_cli/economy.py`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/savings_dashboard.lua`
  - `nvim-poor-cli/tests/savings_dashboard_spec.lua`

## 1. Problem

`/savings` exists but is text. Users can't see the value delivered by compaction, caching, RTK, model downshift. LEARNING.md §3.4.

## 2. Current state

Text dump.

## 3. Goal & non-goals

**Goal:** dashboard showing estimated savings by source (compaction, prompt caching, semantic cache, RTK filters, model downshift), with before/after deltas per session and a 30-day history sparkline.

**Non-goals:**
- Do not compete with the cost dashboard (PRD 016) — focus is savings, not spend.

## 4. Design

Data source: economy + audit_log stats per event type. RPC `poor-cli/savingsSummary`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Aggregate stats in economy.
2. RPC.
3. Lua dashboard with sparkline + tables.
4. Tests.

## 7. Testing & acceptance criteria

- `test_savings_breakdown_by_source`
- `test_30_day_history_rendered`

**Done criterion**
- [ ] Savings surface visible and accurate.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not modify audit log schema.

## 10. Related PRDs & references

- PRD 016. LEARNING.md §3.4.
