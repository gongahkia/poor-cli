# PRD 055: Picker adapter layer (Telescope / fzf-lua / Snacks)

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/telescope.lua` (narrow)
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/pickers.lua`
  - `nvim-poor-cli/tests/pickers_spec.lua`

## 1. Problem

Plugin currently only integrates with Telescope (fallback `vim.ui.select`). fzf-lua and Snacks picker users left out. LEARNING.md §3.7.

## 2. Current state

`telescope.lua` is the only picker integration.

## 3. Goal & non-goals

**Goal:** single API `pickers.pick(items, opts)` that detects available backend — Snacks > Telescope > fzf-lua > `vim.ui.select` — and routes accordingly. All PRDs using pickers call this.

**Non-goals:**
- Do not implement a picker ourselves.
- Do not hard-depend on any backend.

## 4. Design

```lua
-- pickers.lua
local M = {}
local function detect()
  if pcall(require, "snacks.picker") then return "snacks" end
  if pcall(require, "telescope") then return "telescope" end
  if pcall(require, "fzf-lua") then return "fzf-lua" end
  return "native"
end

function M.pick(items, opts)
  -- items: { {id, label, preview, data}... }
  -- opts:  { title, on_pick }
end
```

Backend implementations in `pickers_<backend>.lua`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Write adapter + 4 backends.
2. Switch `telescope.lua` callers to the adapter.
3. Tests per backend (mock `require`).

## 7. Testing & acceptance criteria

- `test_detect_prefers_snacks`
- `test_native_fallback_works`
- `test_items_preview_forwarded_correctly`

**Done criterion**
- [ ] Adapter used by all picker call sites.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not fork any picker.

## 10. Related PRDs & references

- LEARNING.md §3.7.
