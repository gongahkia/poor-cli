# PRD 034: Trust Center interactive upgrade

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (4d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/trust.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/tests/trust_spec.lua`

## 1. Problem

`:PoorCliTrust` shows a static text summary. Users want to toggle sandbox preset, check which tools are allowed, change rollback retention, and confirm privacy posture interactively. LEARNING.md §3.4.

## 2. Current state

Read-only scratch buffer.

## 3. Goal & non-goals

**Goal:** single-screen scratch buffer with section headers and inline actions — `[Toggle sandbox]`, `[View permission rules]`, `[Rotate audit log]`, `[Export audit]` — rendered as virtual text with keymaps. Cursor on an action + `<CR>` invokes it.

**Non-goals:**
- Do not re-implement the full configuration UI (that's `:PoorCliSettings` in a future PRD).

## 4. Design

Sections: Provider, Sandbox preset, Permission mode, Permission rules count, Rollback (checkpoints retained), Audit log, Privacy (data leaving the machine?), Memory (AGENTS.md source list).

Each section's `[action]` buttons implemented as buffer-local keymaps on specific lines (via `nvim_buf_set_keymap` with line-scoped check).

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Query existing `poor-cli/trustStatus` RPC (if absent, add).
2. Render sections + actions.
3. Wire actions.
4. Tests.

## 7. Testing & acceptance criteria

- `test_sandbox_toggle_switches_preset`
- `test_rotate_audit_invokes_rpc`

**Done criterion**
- [ ] Interactive Trust Center works.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not modify audit schema.

## 10. Related PRDs & references

- PRD 011, 013.
- LEARNING.md §3.4.
