# PRD 046: Chat — `@`-mention picker (file, image, LSP)

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (4–5d)
- **Blocked by:** 045, 055
- **Conflicts with:** 047
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/chat.lua`

## 1. Problem

`@file:path` is text-only. Error-prone on long paths. Images/diagnostics attach only via commands. LEARNING.md §3.5 #7–8.

## 2. Current state

Text mentions; no picker.

## 3. Goal & non-goals

**Goal:** typing `@` in chat input opens a picker with sources:
- `@file:` → files in repo.
- `@buffer:` → open buffers.
- `@lsp:` → current buffer's LSP diagnostics.
- `@image:` → from clipboard or file picker.
- `@function:` → treesitter functions in current buffer.

Insert format: `@file:path/to/thing.py:12-20` (optional line range).

## 4. Design

Multi-step picker: first pick source, then pick item. Use picker adapter.

## 5. Files to create / modify / delete

Modify `chat.lua`.

## 6. Implementation plan

1. Add `@` trigger.
2. Source registry with handlers.
3. Pickers per source.
4. Tests.

## 7. Testing & acceptance criteria

- `test_at_opens_source_picker`
- `test_file_source_lists_tracked_files`
- `test_lsp_source_lists_current_diagnostics`

**Done criterion**
- [ ] `@` picker usable for all sources.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not change server-side mention parsing (already handles `@file:path`).

## 10. Related PRDs & references

- PRD 045, 053, 055.
- LEARNING.md §3.5.
