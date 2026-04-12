# PRD 049: Inline — cycle alternatives + syntax-region filter

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (4–5d)
- **Blocked by:** 048
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/inline.lua`
  - `poor_cli/server/handlers/chat.py` (or runtime.py if PRD 019 not merged)

## 1. Problem

No way to cycle between candidate completions. No suppression of completion inside comments/strings (server-side gating only). LEARNING.md §3.6 #3, #5.

## 2. Current state

Single suggestion returned; server gates by filetype, not syntax region.

## 3. Goal & non-goals

**Goal:**
- `<M-]>` / `<M-[>` cycle through N candidates (request `n=3` from server).
- Client-side pre-filter: if cursor is inside comment / string (treesitter node kind), skip auto-trigger (manual `<C-Space>` still fires).

## 4. Design

Request `completions_count: N` from server. Client caches list; cycles via index.

Syntax-region check uses `vim.treesitter.get_node()` and a language-specific map of "skip" node types.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Server: accept `n` param; return list.
2. Client: cycle state + bindings.
3. Treesitter region check.
4. Tests.

## 7. Testing & acceptance criteria

- `test_cycle_shows_second_candidate`
- `test_treesitter_comment_skips_auto_trigger`

**Done criterion**
- [ ] Cycling works.
- [ ] Comments/strings don't auto-trigger.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not cache candidates across cursor moves.

## 10. Related PRDs & references

- PRD 048.
- LEARNING.md §3.6.
