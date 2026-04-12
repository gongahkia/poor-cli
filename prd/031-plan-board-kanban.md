# PRD 031: Plan Board (kanban for multi-step plans)

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/plan.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `poor_cli/plan_mode.py` (narrow — expose structured plan via RPC)
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/plan_board.lua`
  - `nvim-poor-cli/tests/plan_board_spec.lua`

## 1. Problem

Plan mode currently shows a linear popup. Multi-step plans with dependencies need a board view (todo / in-progress / done / blocked). LEARNING.md §3.4.

## 2. Current state

`plan.lua` is a floating window with approve/reject actions.

## 3. Goal & non-goals

**Goal:** kanban-style buffer (four columns as extmarks) showing plan steps. Keys: `<Tab>` advance status, `<S-Tab>` regress, `<CR>` expand, `x` mark blocked, `a` add step, `d` delete step.

**Non-goals:**
- Do not auto-infer dependencies.
- Do not persist across sessions.

## 4. Design

RPC `poor-cli/getPlan`, `poor-cli/updatePlanStep` (existing plan-mode extensions).

Board rendered in a vertical scratch; each column uses ASCII box-drawing + extmark highlighting.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Expose structured plan via RPC.
2. Lua board.
3. Keymap bindings.
4. Tests.

## 7. Testing & acceptance criteria

- `test_board_renders_four_columns`
- `test_tab_advances_status_via_rpc`
- `test_blocked_step_rendered_red`

**Done criterion**
- [ ] Board usable end-to-end.

## 8. Rollback / risk

Low. Old floating popup kept as fallback.

## 9. Out-of-scope & boundary

- 🚫 Do not change plan approval semantics.
- 🚫 Do not persist state.

## 10. Related PRDs & references

- LEARNING.md §3.4.
