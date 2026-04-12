# PRD 057: `nvim-dap` integration — bug → breakpoint

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (4d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `nvim-poor-cli/lua/poor-cli/diagnostics.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/dap_bridge.lua`
  - `nvim-poor-cli/tests/dap_bridge_spec.lua`

## 1. Problem

When AI flags a bug at `file:line`, the user copies the path and sets a breakpoint manually. LEARNING.md §3.8.

## 2. Current state

File:line references in chat become diagnostics but are not clickable to a DAP breakpoint.

## 3. Goal & non-goals

**Goal:** on a diagnostic (or a chat `file:line` reference), `<leader>pb` sets a DAP breakpoint at that location. Optional `<leader>pB` launches DAP run.

**Non-goals:**
- Do not configure a debugger per-language (user's DAP config handles that).
- Do not hard-depend on DAP.

## 4. Design

Detect DAP availability; parse the line reference; call `require("dap").toggle_breakpoint()` at the target.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Bridge.
2. Keymaps.
3. Tests.

## 7. Testing & acceptance criteria

- `test_breakpoint_set_at_line`
- `test_noop_when_dap_absent`

**Done criterion**
- [ ] Breakpoint flow works.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not ship DAP configurations.

## 10. Related PRDs & references

- nvim-dap: https://github.com/mfussenegger/nvim-dap
- LEARNING.md §3.8.
