# PRD 053: `oil.nvim` file-mention integration

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (2d)
- **Blocked by:** 046
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/chat.lua` (narrow — add oil source to mention picker)
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/oil_bridge.lua`

## 1. Problem

Mention picker (PRD 046) `@file:` source uses a default file picker. Users of oil.nvim want to navigate the tree visually. LEARNING.md §3.8.

## 2. Current state

Mention picker lists tracked files.

## 3. Goal & non-goals

**Goal:** `@oil:` mention source opens oil.nvim in floating mode; on `<CR>` on a file, path gets inserted into the chat input.

**Non-goals:**
- Do not depend on oil.
- Do not modify oil's own behavior.

## 4. Design

Call `require("oil").open_float(cwd)`; register a one-shot autocmd to capture the `<CR>`-selected path; on capture, close oil and insert `@file:<path>` into chat input.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Bridge module.
2. Register as a source in mention picker.
3. Plenary test with mocked oil.

## 7. Testing & acceptance criteria

- `test_oil_path_inserted_on_select`
- `test_noop_when_oil_absent`

**Done criterion**
- [ ] Oil source works.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not depend on oil.

## 10. Related PRDs & references

- PRD 046.
- oil.nvim: https://github.com/stevearc/oil.nvim
