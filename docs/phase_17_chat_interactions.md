# Phase 17: Chat Interactions

**Priority:** High — UX polish bundle for the chat buffer, addressing LEARNING.md §3.5 pain points (linear chat, no codeblock actions, weak discoverability, fragile mentions, missing edit/export/cost surfacing).
**Estimated agents:** 5 (strictly serialized — all touch `chat.lua`)
**Dependencies:** Picker adapter (PRD 055) for 17C/17D; Diff Review panel (PRD 014) optional for 17B; Cost metadata stream (PRD 016) for 17E.
**Philosophy:** Turn the chat buffer from a passive scrollback into an interactive surface. Regenerate-and-branch, cursor-aware codeblock actions, autocomplete for `/` and `@`, and a small polish bundle (edit/resend, cost badges, export). All five PRDs mutate the same file — they must ship as sub-waves, not in parallel.

---

## File scope & collision map

| Agent | PRD | Primary file(s) | Secondary files |
|-------|-----|-----------------|-----------------|
| 17A | 043 | `nvim-poor-cli/lua/poor-cli/chat.lua` | `keymaps.lua`, `poor_cli/history.py`, `poor_cli/server/handlers/chat.py` |
| 17B | 044 | `nvim-poor-cli/lua/poor-cli/chat.lua` | `keymaps.lua` |
| 17C | 045 | `nvim-poor-cli/lua/poor-cli/chat.lua` | — |
| 17D | 046 | `nvim-poor-cli/lua/poor-cli/chat.lua` | — |
| 17E | 047 | `nvim-poor-cli/lua/poor-cli/chat.lua` | — |

**Collision flag (critical):** all five agents mutate `nvim-poor-cli/lua/poor-cli/chat.lua`. The PRDs explicitly declare a blocking chain: 043 → 044 → 045 → 046 → 047. These **cannot** run in parallel — attempting to do so will produce merge conflicts on nearly every hunk. Additionally 17A also touches `keymaps.lua` (shared with 17B) and the Python server side (isolated — no collision with 17B–17E there).

**Proposed sub-waves (must be strictly sequential):**

- **Sub-wave 17.1:** Agent 17A (043) — schema migration + regenerate RPC + branch badge. Largest blast radius; land first while chat.lua is still quiet.
- **Sub-wave 17.2:** Agent 17B (044) — codeblock yank/apply/open keymaps. Adds treesitter-based cursor actions; rebase onto 17A's badge extmarks.
- **Sub-wave 17.3:** Agent 17C (045) — slash-command autocomplete picker. Introduces first InsertCharPre hook in chat input.
- **Sub-wave 17.4:** Agent 17D (046) — `@`-mention picker. Extends the InsertCharPre pattern from 17C; shares picker adapter plumbing.
- **Sub-wave 17.5:** Agent 17E (047) — edit/resend, cost badges, export. Smallest surface area; lands last to polish on top of everything.

Each sub-wave must merge and stabilise before the next begins. No concurrent branches against `chat.lua` within this phase.

---

## Agent 17A: Regenerate + Branch Tree Navigation

**Pain points addressed:** LEARNING.md §3.5 #1 — chat is linear, no way to regenerate a turn while keeping the old answer.
**Dependencies:** Coordinates history schema with PRD 003 / 039. Does not implement the tree *viewer* (that is PRD 039).

### What to build

Add branching to chat history. `<leader>rr` on any assistant turn regenerates it with a fresh seed, producing a sibling branch rather than overwriting. `[[` / `]]` cycle siblings. The active branch drives all subsequent turns. PRD 039 will later surface this as a tree view — this agent ships only the backend plumbing plus a minimal inline branch badge.

### Implementation details

1. **History schema migration** in `poor_cli/history.py`:
   - Add `parent_id: str | None` and `branch_of: str | None` fields to each turn record.
   - Add an `active_leaf` pointer at the conversation level tracking which leaf the user is "on".
   - Write a one-shot migration that backfills `parent_id` as the previous turn's id for legacy transcripts.

2. **`regenerateTurn` RPC** in `poor_cli/server/handlers/chat.py` (or `runtime.py` if PRD 019 has not merged yet):
   - Input: `turn_id`. Output: new assistant turn id.
   - Re-runs generation from the parent user turn with a new seed.
   - Attaches the result as a sibling (`branch_of = turn_id`, same `parent_id`).
   - Updates `active_leaf` to the new turn.

3. **Chat.lua wiring:**
   - Detect cursor-on-assistant via the existing turn-extmark metadata.
   - Bind `<leader>rr` to call the RPC and refresh the buffer.
   - Bind `[[` / `]]` to navigate siblings of the turn under cursor by rewriting `active_leaf` and re-rendering from that branch.

4. **Branch badge:** render `[branch 2/3]` as an extmark at the top of each bubble with siblings. Keep it minimal — the full tree view belongs to PRD 039.

5. **Keymap registration** in `nvim-poor-cli/lua/poor-cli/keymaps.lua`: scope the `<leader>rr` / `[[` / `]]` bindings to the chat buffer filetype only.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/chat.lua` (regenerate action, badge rendering, sibling navigation)
- `nvim-poor-cli/lua/poor-cli/keymaps.lua` (new chat-local bindings)
- `poor_cli/history.py` (schema fields + migration)
- `poor_cli/server/handlers/chat.py` — or `runtime.py` if PRD 019 not merged (new `regenerateTurn` RPC)

### Acceptance criteria

- [ ] `test_regenerate_creates_sibling` — calling the RPC produces a second assistant turn with matching `parent_id` and correct `branch_of`.
- [ ] `test_active_leaf_updates` — `active_leaf` advances to the new leaf after regenerate and after `[[`/`]]`.
- [ ] `test_branch_badge_renders` — `[branch N/M]` extmark appears only when siblings exist.
- [ ] `<leader>rr` on an assistant turn produces a new sibling without touching the old one.
- [ ] `[[` / `]]` cycle through siblings and subsequent turns follow the active branch.
- [ ] Legacy transcripts (no `parent_id`) migrate cleanly on load.

**PRD reference:** prd/043-chat-regenerate-branch-tree.md

---

## Agent 17B: Codeblock Copy & Apply Actions

**Pain points addressed:** LEARNING.md §3.5 #3–4 — no ergonomic way to yank or apply fenced code blocks from chat without visual selection.
**Dependencies:** Blocked by 17A. Integrates with PRD 014's Diff Review panel if present.

### What to build

Cursor-on-codeblock actions in the chat buffer. Treesitter identifies the fenced block under the cursor; three keymaps act on it: `yc` yanks the block body, `<leader>ya` applies it to a target file (via Diff Review when available, otherwise direct write with permission), `<leader>yl` opens it in a scratch buffer with the right filetype.

### Implementation details

1. **Block detection:** use `vim.treesitter.get_node()` with the markdown parser to walk up from cursor position until a `fenced_code_block` node is found. Extract both the body text and the info string (language tag) for filetype inference.

2. **`yc` — yank:**
   - Copy the block body (excluding the fences) to the unnamed register.
   - Respect the user's `clipboard` option — if `unnamedplus` is set, it lands on the system clipboard naturally.

3. **`<leader>ya` — apply:**
   - Target selection: prefer cursor position in the most recently visited non-chat window. Otherwise prompt via `vim.ui.select()` over the open buffer list.
   - If PRD 014's Diff Review panel module is loadable, route the block + target through that panel so the user sees a diff before commit.
   - Else direct-write with an explicit `vim.ui.input` confirmation prompt.

4. **`<leader>yl` — open in scratch:**
   - Create a scratch buffer, set `filetype` from the info string (fall back to `text`), populate with the block body, open in a split.

5. **Keymap registration** in `keymaps.lua`: chat-buffer-scoped only, no global bindings.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/chat.lua` (treesitter block lookup + three action handlers)
- `nvim-poor-cli/lua/poor-cli/keymaps.lua` (chat-local bindings for `yc`, `<leader>ya`, `<leader>yl`)

### Acceptance criteria

- [ ] `test_yc_yanks_block_content` — unnamed register contains exactly the block body, no fences.
- [ ] `test_ya_routes_to_diff_review_when_available` — Diff Review panel receives the block when PRD 014 module is loadable; direct-write path used otherwise.
- [ ] `test_yl_opens_scratch_with_correct_ft` — scratch buffer filetype matches the fence info string.
- [ ] Cursor outside any fenced block: actions no-op with a non-intrusive message.
- [ ] Streaming/rendering behavior unchanged.

**PRD reference:** prd/044-chat-codeblock-actions.md

---

## Agent 17C: Slash-Command Autocomplete

**Pain points addressed:** LEARNING.md §3.5 #6 — 90+ slash commands, discoverability is painful.
**Dependencies:** Blocked by 17B. Requires the picker adapter from PRD 055.

### What to build

Typing `/` at column 1 of the chat input opens a picker listing all slash commands with one-line descriptions. Fuzzy-match filters as the user types. Selecting a command inserts it into the input with the cursor positioned at the first argument slot.

### Implementation details

1. **Trigger:** `InsertCharPre` autocmd scoped to the chat input area. Fire only when the character is `/` and the cursor is at column 1 (i.e. start of a fresh input line, not embedded in text).

2. **Source the command list** from the existing slash-command registry — do not duplicate or hardcode. This is a reflection of whatever commands are registered today.

3. **Picker:** delegate to the PRD 055 picker adapter. Each entry shows `name + one-line description`. Preview pane shows the full description and usage examples if present in the registry.

4. **Fuzzy filter:** standard substring-and-subsequence scoring from the adapter; no custom ranking needed.

5. **On pick:**
   - Replace the `/` that triggered the popup with the selected command text.
   - If the command takes arguments, position the cursor at the first argument slot (space after the command name).
   - If it takes none, drop the cursor at end of line.

6. **Escape hatch:** `<Esc>` closes the picker and leaves the bare `/` in the input so the user can continue typing manually.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/chat.lua` (InsertCharPre hook, picker invocation, insertion logic)

### Acceptance criteria

- [ ] `test_slash_triggers_picker` — typing `/` at col 1 opens the picker; typing `/` mid-line does not.
- [ ] `test_fuzzy_filter_narrows` — typing characters filters the list via the adapter.
- [ ] `test_pick_inserts_command` — selection replaces the trigger and positions the cursor correctly per-command.
- [ ] Picker reflects the live registry — does not ship its own command list.
- [ ] No new slash commands introduced by this agent.

**PRD reference:** prd/045-chat-slash-autocomplete.md

---

## Agent 17D: `@`-Mention Picker (file, buffer, LSP, image, function)

**Pain points addressed:** LEARNING.md §3.5 #7–8 — `@file:path` is text-only, error-prone on long paths; images and diagnostics attach only via commands.
**Dependencies:** Blocked by 17C. Requires PRD 055 picker adapter.

### What to build

Typing `@` in the chat input opens a two-step picker: first pick a source, then pick an item from that source. Sources: `@file:` (repo files), `@buffer:` (open buffers), `@lsp:` (current buffer diagnostics), `@image:` (clipboard or file), `@function:` (treesitter functions in the current buffer). The final insertion uses the existing wire format `@file:path/to/thing.py:12-20` — server-side parsing is unchanged.

### Implementation details

1. **Trigger:** same `InsertCharPre` pattern as 17C, but for `@`. Fire when `@` is typed at start of word (col 1 or preceded by whitespace).

2. **Source registry** (Lua table in `chat.lua`, each entry provides `label`, `handler`):
   - `file` — list repo-tracked files (git-aware where possible).
   - `buffer` — list open buffers with non-trivial content.
   - `lsp` — list current diagnostics for the caller's last non-chat buffer, with severity + line.
   - `image` — offer clipboard paste or file picker.
   - `function` — use treesitter to list function nodes in the caller's last non-chat buffer; optional line-range capture for the insert.

3. **Step 1 picker:** source selection (5 items, fixed).

4. **Step 2 picker:** invokes the chosen source's handler, returning the items to feed into the picker adapter.

5. **Insertion format:**
   - File / buffer / function: `@file:path/thing.py` or `@file:path/thing.py:12-20` when a range is available.
   - LSP: `@lsp:path/thing.py:LINE` plus the diagnostic text inline.
   - Image: `@image:<tempfile path>` after writing the clipboard image to the session's attachment dir.

6. **Server-side parsing is off-limits** — the existing `@file:path` parser already handles the wire format. This agent only improves the client-side picker that produces the text.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/chat.lua` (trigger, source registry, per-source handlers, insertion)

### Acceptance criteria

- [ ] `test_at_opens_source_picker` — typing `@` opens the two-step picker at source-selection step.
- [ ] `test_file_source_lists_tracked_files` — repo files appear (git-aware where available).
- [ ] `test_lsp_source_lists_current_diagnostics` — the LSP source lists diagnostics for the caller's most recent non-chat buffer.
- [ ] Final insertion string matches the existing `@file:path[:range]` wire format.
- [ ] Image source writes clipboard content to the attachment dir and emits `@image:<path>`.
- [ ] Server-side mention parsing is untouched.

**PRD reference:** prd/046-chat-mention-picker.md

---

## Agent 17E: Chat Polish Bundle — edit/resend, cost badges, export

**Pain points addressed:** LEARNING.md §3.5 #5, #9, #10 — `/edit-last` not surfaced in UI, no per-message cost visible in buffer, no in-UI conversation export.
**Dependencies:** Blocked by 17D. Reuses PRD 016 cost metadata already on the stream payload. Does not touch branching (PRD 043 / 17A) or cost logic (PRD 016).

### What to build

Three small, adjacent UI polish items bundled into one agent:

1. `<leader>ee` on any user turn opens it for editing and resends on save.
2. Per-turn virtual-text badge `[$0.02 · 1.4s · 312 tok]` rendered on each assistant turn.
3. `<leader>ex` opens an export picker (md / json / transcript) and writes the chosen format to `.poor-cli/exports/`.

### Implementation details

1. **`<leader>ee` — edit/resend:**
   - Cursor-on-user-turn detection via the existing turn-extmark metadata (same mechanism as 17A).
   - Populate the input area with the turn's content, mark the original as being-edited, remove the turn and all turns after it on send.
   - Resend via the existing send path — no new RPC.

2. **Per-turn cost badges:**
   - Cost, duration, and token count are already on the stream payload courtesy of PRD 016.
   - Render an extmark with `virt_text` at the end of the assistant turn's first line: `[$0.02 · 1.4s · 312 tok]`.
   - Toggle is a simple on/off config flag — nothing more configurable per the PRD non-goals.

3. **`<leader>ex` — export:**
   - `vim.ui.select` offers `markdown`, `json`, `transcript` formats.
   - Call the existing `poor-cli/exportConversation` RPC; do not reimplement serialization.
   - Write into `.poor-cli/exports/<timestamp>.<ext>` and echo the path.

4. **Keep clear of adjacent PRDs:**
   - No branching logic here — that is 17A.
   - No changes to cost calculation — that is PRD 016.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/chat.lua` (edit/resend flow, cost badge extmarks, export picker)

### Acceptance criteria

- [ ] `test_ee_edit_resend_flow` — `<leader>ee` on a user turn re-populates the input, discards subsequent turns, and resends.
- [ ] `test_cost_badge_present_after_turn` — each completed assistant turn has a cost virtual-text badge.
- [ ] `test_export_writes_file` — `<leader>ex` writes a file under `.poor-cli/exports/` in the chosen format.
- [ ] Cost badge toggleable via a single on/off config flag.
- [ ] No changes to cost logic or branching behaviour.

**PRD reference:** prd/047-chat-polish-bundle.md
