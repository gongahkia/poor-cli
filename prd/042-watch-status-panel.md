# PRD 042: Watch Status panel

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (2–3d)
- **Blocked by:** 005
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/watch_panel.lua`
  - `nvim-poor-cli/tests/watch_panel_spec.lua`

## 1. Problem

`/watch` and `/qa` modes are active but invisible. Users forget they're on, waste API spend. LEARNING.md §3.4.

## 2. Current state

Toggled via command, no UI.

## 3. Goal & non-goals

**Goal:** panel showing: active watches (paths, last change, matched ignore patterns), QA toggle status, last N triggered actions and their outcomes.

## 4. Design

Uses `FileWatcher` from PRD 005. New RPC `watchStatus`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. RPC.
2. Lua panel.
3. Tests.

## 7. Testing & acceptance criteria

- `test_panel_lists_active_watches`
- `test_recent_triggered_actions`

**Done criterion**
- [ ] Watch state visible.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not change watch behavior.

## 10. Related PRDs & references

- PRD 005.
- LEARNING.md §3.4.
