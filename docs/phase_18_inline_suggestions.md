# Phase 18: Inline Suggestion Polish

**Priority:** Medium — UX refinements on an already-shipping inline completion surface.
**Estimated agents:** 2 (serialize — see file-scope table)
**Dependencies:** Agent 18B is blocked by Agent 18A (per PRD 049 header).
**Philosophy:** Close the ergonomic gaps in ghost-text editing — line-granularity accept, a readable preview of multi-line suggestions, cycling through alternatives, and syntax-aware suppression so completions stop firing inside comments and strings.

---

## File-scope table

| File | Agent 18A | Agent 18B | Collision? |
|---|---|---|---|
| `nvim-poor-cli/lua/poor-cli/inline.lua` | modify | modify | **Yes — serialize** |
| `nvim-poor-cli/lua/poor-cli/keymaps.lua` | modify | — | No |
| `poor_cli/server/handlers/chat.py` | — | modify | No |

**Collision note:** Both agents mutate `inline.lua`. PRD 049 explicitly declares `Blocked by: 048` and PRD 048 declares `Conflicts with: 049 (serialize)`. **Run 18A to completion and land it first**, then start 18B on top of the merged result. Do not parallelize these two agents.

---

## Agent 18A: Accept-Line Key + Preview Split

**Pain points addressed:** Inline completion only supports full-accept (`<Tab>`) and accept-word (`<M-w>`) — no line-granularity accept, and multi-line ghost text is hard to read inline.
**Expected impact:** Finer control over partial accepts; readable preview for multi-line suggestions.

### What to build

Add two inline-completion interactions:
1. `<M-l>` — accept the next line of the active ghost-text suggestion (up to and including the next `\n`).
2. `<M-?>` — while ghost text is visible, open a preview scratch split rendering the full suggestion with syntax highlighting derived from the current buffer's filetype.

### Implementation details

1. **`accept_line()` helper in `inline.lua`** — consume ghost-text characters from the start of the pending suggestion up to and including the first `\n`. Insert the consumed slice at cursor; retain the remainder as the still-pending ghost text (do not clear the suggestion state unless the remainder is empty). Mirror the state-management style of the existing `accept_word()` path.

2. **Preview split helper** — when invoked with a live suggestion, open a scratch split (`:new` with `buftype=nofile`, `bufhidden=wipe`, `swapfile=false`), write the full suggestion text into it, and set `filetype` to the originating buffer's filetype so treesitter / syntax highlighting kicks in. Close-on-`q` mapping for convenience.

3. **Keymap registration in `keymaps.lua`** — register `<M-l>` → `accept_line()` and `<M-?>` → `open_preview_split()`. Both must no-op when no suggestion is active (do not steal the key from the user's normal mapping).

4. **Do not touch suggestion generation** — PRD 048 §9 explicitly forbids modifying how suggestions are produced. This is purely a consumer-side change.

5. **Tests** — `test_accept_line_consumes_one_line_of_ghost_text` and `test_preview_split_opens_with_same_ft` per PRD.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/inline.lua` (modify — add `accept_line`, `open_preview_split`)
- `nvim-poor-cli/lua/poor-cli/keymaps.lua` (modify — register `<M-l>`, `<M-?>`)

### Acceptance criteria

- [ ] `<M-l>` accepts exactly one line of ghost text, preserving the remainder.
- [ ] `<M-l>` no-ops cleanly when no suggestion is active.
- [ ] `<M-?>` opens a preview split containing the full suggestion.
- [ ] Preview split filetype matches the originating buffer.
- [ ] Preview split closable with `q`.
- [ ] `test_accept_line_consumes_one_line_of_ghost_text` passes.
- [ ] `test_preview_split_opens_with_same_ft` passes.
- [ ] No changes to suggestion generation code paths.

**PRD reference:** prd/048-inline-accept-line-preview.md

---

## Agent 18B: Cycle Alternatives + Syntax-Region Filter

**Pain points addressed:** No way to cycle between candidate completions — user is stuck with whatever suggestion the server returns first. Completions also fire inside comments and strings, where they are rarely wanted (server currently gates by filetype, not by syntax region).
**Expected impact:** Fewer wasted completions inside comments/strings; user can reach a useful alternative without re-triggering.
**Depends on:** Agent 18A must be merged first.

### What to build

1. Request N candidates (default 3) from the server per inline completion request; cache the list client-side and expose `<M-]>` / `<M-[>` to cycle forward/back through the candidates.
2. Client-side pre-filter using treesitter: if the cursor's treesitter node is a comment or string, suppress the auto-trigger. Manual invocation via `<C-Space>` must still fire regardless.

### Implementation details

1. **Server side — `chat.py` handler** (or `runtime.py` if PRD 019 has not yet merged; check at implementation time). Accept a new request field `completions_count: int` (default 1 for backward compatibility, default 3 when sent by the Neovim client). Return a list of candidates instead of a single string. Preserve the existing single-candidate response shape when `completions_count` is absent or 1.

2. **Client cycle state in `inline.lua`** — store `{ candidates: string[], index: int }` alongside the existing suggestion state. `<M-]>` advances `index` (mod `len`); `<M-[>` retreats. On cycle, re-render the ghost text with the newly selected candidate. Invalidate the cache on cursor move (PRD 049 §9 explicitly forbids caching across cursor moves).

3. **Treesitter region check** — before auto-triggering a request, call `vim.treesitter.get_node()` at the cursor. Maintain a small language-keyed skip table, e.g.:
   ```lua
   local SKIP_NODES = {
     lua = { "comment", "string", "string_content" },
     python = { "comment", "string", "string_content" },
     typescript = { "comment", "string", "template_string" },
     -- ...
   }
   ```
   If the node kind (or any ancestor up to a small depth) matches, skip the auto-trigger. Manual `<C-Space>` bypasses this check.

4. **Server backward compat** — older clients that do not send `completions_count` must see identical behavior. Add a test that exercises the legacy path.

5. **Tests** — `test_cycle_shows_second_candidate` and `test_treesitter_comment_skips_auto_trigger` per PRD.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/inline.lua` (modify — cycle state, treesitter gate, new keymaps)
- `poor_cli/server/handlers/chat.py` (modify — accept `completions_count`, return candidate list; or `runtime.py` if PRD 019 not yet merged)

### Acceptance criteria

- [ ] Server accepts `completions_count` and returns a list of that length.
- [ ] Legacy requests (no `completions_count`) return single-candidate shape unchanged.
- [ ] `<M-]>` cycles forward through cached candidates; `<M-[>` cycles back.
- [ ] Candidate cache is invalidated on cursor move.
- [ ] Auto-trigger suppressed when cursor is inside a comment or string treesitter node.
- [ ] Manual `<C-Space>` still fires inside comments/strings.
- [ ] `test_cycle_shows_second_candidate` passes.
- [ ] `test_treesitter_comment_skips_auto_trigger` passes.

**PRD reference:** prd/049-inline-cycle-syntax-filter.md
