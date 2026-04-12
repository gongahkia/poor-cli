# PRD 050: `trouble.nvim` integration

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (3–4d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/diagnostics.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/trouble_source.lua`
  - `nvim-poor-cli/tests/trouble_source_spec.lua`

## 1. Problem

AI suggestions (`file:line` references in assistant output) currently surface as virtual-text diagnostics. Users expect them in trouble.nvim's unified problems view next to LSP diagnostics. LEARNING.md §3.8 — "biggest single integration win."

## 2. Current state

`diagnostics.lua` parses assistant text for `file:line:` patterns and calls `vim.diagnostic.set(...)` with a custom namespace. No trouble integration.

## 3. Goal & non-goals

**Goal:** register a `poor_cli` source in trouble.nvim's extension API. `:Trouble poor_cli` shows all current AI suggestions. Use the same namespace as diagnostics.lua.

**Non-goals:**
- Do not hard-require trouble.nvim — detect availability, integrate if present.
- Do not replace existing diagnostic virtual text.

## 4. Design

Trouble's extension API (as of 3.x) accepts sources via `require("trouble").setup({ modes = { poor_cli = {...} } })`. Our source queries the existing diagnostic namespace.

Register only if `pcall(require, "trouble")` succeeds.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Author `trouble_source.lua` with trouble's expected interface.
2. Lazy-register on setup if trouble present.
3. Docs.
4. Plenary test mocking trouble.

## 7. Testing & acceptance criteria

- `test_source_registers_when_trouble_present`
- `test_source_noop_when_trouble_absent`
- `test_source_returns_items_matching_namespace`

**Done criterion**
- [ ] `:Trouble poor_cli` works.
- [ ] No error if trouble absent.

## 8. Rollback / risk

Low. Optional integration.

## 9. Out-of-scope & boundary

- 🚫 Do not depend on trouble.
- 🚫 Do not modify diagnostic parsing.

## 10. Related PRDs & references

- LEARNING.md §3.8, §3.10.
- trouble.nvim: https://github.com/folke/trouble.nvim
