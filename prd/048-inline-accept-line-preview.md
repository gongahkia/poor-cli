# PRD 048: Inline — accept-line key + preview split

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (3d)
- **Blocked by:** —
- **Conflicts with:** 049 (serialize)
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/inline.lua`
  - `nvim-poor-cli/lua/poor-cli/keymaps.lua`

## 1. Problem

Inline completion has full-accept (`<Tab>`) and accept-word (`<M-w>`). Missing `<M-l>` accept-line. Also: multi-line suggestions hard to read at a glance. LEARNING.md §3.6 #1–2.

## 2. Current state

`inline.lua` partial accept only at word boundary.

## 3. Goal & non-goals

**Goal:**
- `<M-l>` accepts next line of ghost text (up to and including `\n`).
- `<M-?>` while ghost-text visible opens a preview split with the completion in a syntax-highlighted scratch buffer.

## 4. Design

`accept_line()` consumes ghost text up to next newline. Preview split reuses suggestion content; filetype derived from current buffer.

## 5. Files to create / modify / delete

Modify `inline.lua`, `keymaps.lua`.

## 6. Implementation plan

1. `accept_line()` logic.
2. Preview split helper.
3. Keymap registration.
4. Tests.

## 7. Testing & acceptance criteria

- `test_accept_line_consumes_one_line_of_ghost_text`
- `test_preview_split_opens_with_same_ft`

**Done criterion**
- [ ] New keymaps work.
- [ ] Preview split usable.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not modify suggestion generation.

## 10. Related PRDs & references

- LEARNING.md §3.6.
