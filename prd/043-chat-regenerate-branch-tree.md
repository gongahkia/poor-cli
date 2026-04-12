# PRD 043: Chat — regenerate + branch tree navigation

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Conflicts with:** 044, 045, 046, 047 (all modify chat.lua — serialize this chain)
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/chat.lua`
  - `nvim-poor-cli/lua/poor-cli/keymaps.lua`
  - `poor_cli/history.py`
  - `poor_cli/server/handlers/chat.py` (or runtime.py if PRD 019 not merged)

## 1. Problem

Chat is linear. No way to regenerate a turn with a new seed while keeping the old answer. LEARNING.md §3.5 #1.

## 2. Current state

`/edit-last` edits the last user message. No regenerate. No branching.

## 3. Goal & non-goals

**Goal:** `<leader>rr` on any assistant turn regenerates it (new seed), creating a sibling branch. `[[` / `]]` navigate siblings. Active branch drives subsequent turns. PRD 039 surfaces this as a tree view; this PRD ships the backend plumbing.

**Non-goals:**
- Do not implement the tree *view* (PRD 039).
- Do not auto-pick winners.

## 4. Design

Extend history schema (coordinated with PRD 039 / 003):
- Each turn gets `parent_id` and optional `branch_of`.
- `active_leaf` pointer tracks the branch the user is on.

RPC `poor-cli/regenerateTurn(turn_id)` produces a new assistant turn as a sibling.

Chat renders siblings with a small badge `[branch 2/3]` at the top of the bubble.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Schema migration for parent_id/branch_of.
2. `regenerateTurn` RPC.
3. Chat.lua: detect cursor-on-assistant, bind `<leader>rr`.
4. Render branch badge via extmark.
5. Navigation keys.
6. Tests.

## 7. Testing & acceptance criteria

- `test_regenerate_creates_sibling`
- `test_active_leaf_updates`
- `test_branch_badge_renders`

**Done criterion**
- [ ] Regenerate works; siblings exist; navigation works.

## 8. Rollback / risk

Medium (schema change).

## 9. Out-of-scope & boundary

- 🚫 Do not implement tree viewer (PRD 039).
- 🚫 Do not touch inline completion.

## 10. Related PRDs & references

- PRD 003, 039.
- LEARNING.md §3.5.
