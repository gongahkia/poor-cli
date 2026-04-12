# PRD 044: Chat — copy and apply code-block actions

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (2–3d)
- **Blocked by:** 043
- **Conflicts with:** 045, 046, 047 (serialize)
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/chat.lua`
  - `nvim-poor-cli/lua/poor-cli/keymaps.lua`

## 1. Problem

No way to yank or apply a code block from chat without visual selection. LEARNING.md §3.5 #3–4.

## 2. Current state

Chat renders markdown; user must `V` + `y` manually.

## 3. Goal & non-goals

**Goal:** cursor on a fenced code block:
- `yc` yanks the block to unnamed register.
- `<leader>ya` applies the block to the current file (via Diff Review panel from PRD 014 if installed, else direct write with permission).
- `<leader>yl` opens the block in a scratch buffer with the right filetype.

## 4. Design

Treesitter markdown parser identifies the fenced block under cursor. Extract content + info string (language tag). For apply, choose target via cursor-in-other-window or prompt via `vim.ui.select`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Use `vim.treesitter.get_node` to find fenced_code_block.
2. Bindings and action handlers.
3. Integrate with Diff Review panel if available.
4. Tests (plenary).

## 7. Testing & acceptance criteria

- `test_yc_yanks_block_content`
- `test_ya_routes_to_diff_review_when_available`
- `test_yl_opens_scratch_with_correct_ft`

**Done criterion**
- [ ] Actions bound and functional.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not change streaming/rendering.

## 10. Related PRDs & references

- PRD 014.
- LEARNING.md §3.5.
