# PRD 047: Chat polish bundle — edit/resend, per-message cost, export

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small-to-medium (4d)
- **Blocked by:** 046
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/chat.lua`

## 1. Problem

Three adjacent polish items: edit last user turn, per-message cost badges, conversation export. LEARNING.md §3.5 #5, #9, #10.

## 2. Current state

`/edit-last` exists as a server command; not surfaced in UI. No per-message cost badge in chat buffer. No in-UI export.

## 3. Goal & non-goals

**Goal:**
- `<leader>ee` on any user turn edits it and resends.
- Per-turn virtual-text badge `[$0.02 · 1.4s · 312 tok]` (overlaps PRD 016 but chat-local).
- `<leader>ex` export: picks format (md/json/transcript) and writes to `.poor-cli/exports/`.

**Non-goals:**
- Do not introduce branching (PRD 043).
- Do not make cost rendering configurable beyond on/off.

## 4. Design

Cursor-on-user-turn detection via extmark metadata. Cost metadata already on the stream payload. Export uses `poor-cli/exportConversation` RPC.

## 5. Files to create / modify / delete

Modify chat.lua.

## 6. Implementation plan

1. Add edit/resend keymap.
2. Add per-turn cost extmarks.
3. Add export picker.
4. Tests.

## 7. Testing & acceptance criteria

- `test_ee_edit_resend_flow`
- `test_cost_badge_present_after_turn`
- `test_export_writes_file`

**Done criterion**
- [ ] All three UX polish items work.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not change cost logic (PRD 016).
- 🚫 Do not touch branching.

## 10. Related PRDs & references

- PRD 016, 043, 046.
- LEARNING.md §3.5.
