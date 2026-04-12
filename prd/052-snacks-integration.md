# PRD 052: `snacks.nvim` notifications & dashboard

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small-to-medium (3–4d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/chat.lua` (narrow — notify calls)
  - other modules that call `vim.notify`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/snacks_bridge.lua`
  - `nvim-poor-cli/tests/snacks_bridge_spec.lua`

## 1. Problem

`vim.notify` renders as plain messages; users want grouped, dismissable notifications and can get them from snacks.nvim. LEARNING.md §3.8.

## 2. Current state

All notifications via `vim.notify`.

## 3. Goal & non-goals

**Goal:** route non-error notifications through snacks.nvim if present (grouped by "poor-cli"). Keep `vim.notify` fallback. Add a snacks dashboard tile showing session cost + active turns.

**Non-goals:**
- Do not hard-depend on snacks.

## 4. Design

Bridge module checks `require("snacks")`. Wraps notify calls:

```lua
M.notify(msg, level, opts)
  if snacks_available then snacks.notify(...)
  else vim.notify(...)
  end
end
```

Dashboard tile via `snacks.dashboard` section.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Write bridge.
2. Replace a few strategic `vim.notify` call sites (cost alarms, stream errors, onboarding).
3. Dashboard tile.
4. Tests.

## 7. Testing & acceptance criteria

- `test_bridge_routes_to_snacks_when_present`
- `test_bridge_fallbacks_vim_notify`
- `test_dashboard_tile_registered`

**Done criterion**
- [ ] Notifications route correctly based on availability.
- [ ] Dashboard tile works if snacks present.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not mandate snacks.

## 10. Related PRDs & references

- snacks.nvim: https://github.com/folke/snacks.nvim
- LEARNING.md §3.8.
