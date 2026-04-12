# Phase 19: Third-Party Plugin Integrations

**Priority:** Medium — ergonomic polish on top of the Neovim client; each integration is optional and gated by availability detection.
**Estimated agents:** 7 (parallel)
**Dependencies:** Agent 19B depends on PRD 014 (Diff Review). Agent 19D depends on PRD 046 (mention picker). Agent 19E depends on PRD 025 (streaming tool output). Others are independent.
**Philosophy:** Never hard-depend on any third-party plugin. Every bridge lazy-checks via `pcall(require, "<plugin>")` and no-ops when absent. Each integration lives in its own `integrations/` (or `_bridge.lua`) module so parallel agents can land without stepping on each other.

---

## File scope table

| Agent | Plugin   | Primary new module                                              | Shared files touched                                     |
|-------|----------|-----------------------------------------------------------------|----------------------------------------------------------|
| 19A   | Trouble  | `nvim-poor-cli/lua/poor-cli/trouble_source.lua`                 | `diagnostics.lua`, `commands.lua`                        |
| 19B   | Gitsigns | `nvim-poor-cli/lua/poor-cli/gitsigns_bridge.lua`                | `diff_review.lua`                                        |
| 19C   | Snacks   | `nvim-poor-cli/lua/poor-cli/snacks_bridge.lua`                  | `chat.lua` + other `vim.notify` call sites               |
| 19D   | Oil      | `nvim-poor-cli/lua/poor-cli/oil_bridge.lua`                     | `chat.lua` (mention picker source)                       |
| 19E   | Overseer | `nvim-poor-cli/lua/poor-cli/overseer_bridge.lua`                | `tasks.lua`                                              |
| 19F   | Neogit   | `nvim-poor-cli/lua/poor-cli/neogit_bridge.lua`                  | `commands.lua`                                           |
| 19G   | nvim-dap | `nvim-poor-cli/lua/poor-cli/dap_bridge.lua`                     | `commands.lua`, `diagnostics.lua`                        |

### Collision flags

- **`commands.lua`** — modified by 19A, 19F, 19G. Each appends its own user-command registration; coordinate so agents land additive blocks (one per bridge) rather than overlapping rewrites. No `init.lua` changes expected.
- **`diagnostics.lua`** — modified by 19A and 19G. 19A reads the existing AI-suggestion namespace; 19G reads file:line references off the same diagnostics. Changes should be strictly additive (no namespace renames).
- **`chat.lua`** — modified by 19C (notify call sites) and 19D (mention picker source registration). Disjoint functions but same file; watch for merge conflicts.
- **No collision on `init.lua`** — bridges self-register from their own `setup` call invoked by the existing bootstrap.

---

## Agent 19A: Trouble.nvim source for AI suggestions

**Pain points addressed:** AI `file:line` suggestions only appear as virtual-text diagnostics; trouble.nvim users want them in the unified problems view.
**PRD reference:** `prd/050-trouble-integration.md`
**Estimated effort:** medium (3–4d)

### What to build

Register a `poor_cli` source in trouble.nvim's 3.x extension API so `:Trouble poor_cli` lists every current AI suggestion alongside LSP diagnostics. Source reads from the existing `diagnostics.lua` namespace — no double-storage.

### Implementation details

1. **Detect trouble** — `pcall(require, "trouble")` on plugin setup. If missing, return early; no error, no warning spam.
2. **Author the source module** — implement trouble's expected interface (items/filter/format callbacks). Items come from `vim.diagnostic.get(nil, { namespace = poor_cli_ns })`.
3. **Register lazily** — on `poor-cli`'s `setup()`, call `require("trouble").setup({ modes = { poor_cli = {...} } })` merging with existing user config rather than clobbering it.
4. **Keep virtual text** — this adds a second surface; it does not replace `diagnostics.lua`'s existing rendering.
5. **User command** — register `:PoorCliTrouble` in `commands.lua` as a thin wrapper for `:Trouble poor_cli`.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/trouble_source.lua` (new)
- `nvim-poor-cli/tests/trouble_source_spec.lua` (new — plenary)
- `nvim-poor-cli/lua/poor-cli/diagnostics.lua` (expose the namespace handle if not already public)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add wrapper command)

### Acceptance criteria

- [ ] `:Trouble poor_cli` shows all active AI suggestions when trouble is installed.
- [ ] No error and no log noise when trouble is absent.
- [ ] Source items share the existing diagnostic namespace (no duplicate store).
- [ ] Plenary: `test_source_registers_when_trouble_present`, `test_source_noop_when_trouble_absent`, `test_source_returns_items_matching_namespace`.

**PRD reference:** prd/050-trouble-integration.md

---

## Agent 19B: Gitsigns bridge for AI-authored hunks

**Pain points addressed:** After accepting a hunk via Diff Review, users can't visually distinguish AI-authored changes from manual edits in the gitsigns gutter.
**PRD reference:** `prd/051-gitsigns-ai-hunks.md`
**Estimated effort:** small (3d)
**Blocked by:** PRD 014 (Diff Review)

### What to build

Track accepted AI hunks per-file in an in-memory session map and render a distinct gutter sign (default `✱`, configurable) via a dedicated sign group. Attribution clears on git commit.

### Implementation details

1. **Attribution map** — keyed by `(bufname, line_range)` living in the bridge module; populated on the `poor-cli/editCommitted` event emitted by Diff Review.
2. **Sign group** — define a separate gutter sign group (not gitsigns'); place `:sign place` entries after each accept so gitsigns' own signs remain untouched.
3. **Recompute on change** — `BufWritePost` + buffer-change autocmd re-derives line ranges (edits above a hunk shift its range).
4. **Commit clears** — listen for `GitCommit` / post-commit hook; wipe the attribution entries for files in that commit.
5. **Graceful absence** — if gitsigns not loaded, still place signs (they're independent), but skip any gitsigns-specific API calls.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/gitsigns_bridge.lua` (new)
- `nvim-poor-cli/tests/gitsigns_bridge_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/diff_review.lua` (emit `editCommitted` with `{file, line_range}`)

### Acceptance criteria

- [ ] `✱` (or configured glyph) appears in the gutter on AI-authored hunks after accept.
- [ ] Signs disappear after `git commit` for the committed files only.
- [ ] Sign glyph and highlight group are configurable.
- [ ] Plenary: `test_signs_placed_after_accept`, `test_signs_cleared_on_commit`.

**PRD reference:** prd/051-gitsigns-ai-hunks.md

---

## Agent 19C: Snacks.nvim notifications and dashboard tile

**Pain points addressed:** `vim.notify` renders as plain echo messages; users want grouped, dismissable notifications and a dashboard tile surfacing session cost / active turns.
**PRD reference:** `prd/052-snacks-integration.md`
**Estimated effort:** small-to-medium (3–4d)

### What to build

Thin bridge that routes non-error notifications through `snacks.notify` (grouped by `"poor-cli"`) when snacks is present, with `vim.notify` as fallback. Also registers a `snacks.dashboard` section showing session cost and in-flight turn count.

### Implementation details

1. **Availability cache** — `pcall(require, "snacks")` once at setup; cache the result. Re-check on `VimEnter` in case of deferred loads.
2. **Notify wrapper** — `M.notify(msg, level, opts)` dispatches to snacks (passing `{ group = "poor-cli" }`) or `vim.notify` otherwise. Errors always stay on `vim.notify` so they don't get dismissed accidentally.
3. **Call-site migration** — replace strategic `vim.notify` invocations (cost alarms, stream errors, onboarding nudges) in `chat.lua` and siblings. Leave low-value ones alone.
4. **Dashboard tile** — register a `snacks.dashboard` section pulling from the already-existing cost tracker; update on `poor-cli/turnFinished`.
5. **No hard dep** — plugin spec lists snacks as optional.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/snacks_bridge.lua` (new)
- `nvim-poor-cli/tests/snacks_bridge_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/chat.lua` (swap notify calls at chosen sites)
- Other modules that call `vim.notify` for cost/stream events

### Acceptance criteria

- [ ] Notifications route to snacks when available; fall back to `vim.notify` otherwise.
- [ ] Dashboard tile displays session cost and active turn count when snacks is present.
- [ ] No hard dependency on snacks at load time.
- [ ] Plenary: `test_bridge_routes_to_snacks_when_present`, `test_bridge_fallbacks_vim_notify`, `test_dashboard_tile_registered`.

**PRD reference:** prd/052-snacks-integration.md

---

## Agent 19D: Oil.nvim mention source

**Pain points addressed:** `@file:` mention picker uses a flat file list; oil users want a tree-navigation experience when inserting file references into chat.
**PRD reference:** `prd/053-oil-file-mention.md`
**Estimated effort:** small (2d)
**Blocked by:** PRD 046 (mention picker)

### What to build

New `@oil:` source for the mention picker that opens oil in a floating window; when the user hits `<CR>` on a file entry, the path is captured, oil closes, and `@file:<path>` is inserted into the chat input.

### Implementation details

1. **Open floating oil** — `require("oil").open_float(cwd)`; respect any user-configured float options.
2. **One-shot capture** — register a buffer-local autocmd (or use oil's `on_select` callback if available) that fires only on `<CR>` inside the oil buffer, reads the row's path via `oil.get_cursor_entry()`, then unregisters itself.
3. **Insert into chat** — close the float, refocus the chat input, and append `@file:<path>` at the cursor position.
4. **Registration** — mention picker exposes a source table; bridge inserts its entry only if oil is installed.
5. **No-op on absence** — selecting `@oil:` when oil is missing falls through to the default file picker with a one-line notify.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/oil_bridge.lua` (new)
- `nvim-poor-cli/lua/poor-cli/chat.lua` (register oil source in mention picker)

### Acceptance criteria

- [ ] `@oil:` opens oil float; `<CR>` inserts `@file:<path>` into chat.
- [ ] Source is absent (or degrades gracefully) when oil is not installed.
- [ ] Oil's own behavior unchanged.
- [ ] Plenary: `test_oil_path_inserted_on_select`, `test_noop_when_oil_absent`.

**PRD reference:** prd/053-oil-file-mention.md

---

## Agent 19E: Overseer.nvim task mirror

**Pain points addressed:** Long-running poor-cli tasks (deploys, test runs, benchmarks, embeddings) are only visible in poor-cli's own panel; overseer users want them in the unified task runner view.
**PRD reference:** `prd/054-overseer-integration.md`
**Estimated effort:** medium (4d)
**Blocked by:** PRD 025 (streaming tool output)

### What to build

For every long-running poor-cli task, register a mirror `overseer.Task` whose status tracks the source task (pending → running → success/failed). Output streams into overseer's output buffer via the streaming tool-output feed.

### Implementation details

1. **Event subscription** — hook `poor-cli/taskStarted`, `poor-cli/taskProgress`, `poor-cli/taskFinished` emitted by `tasks.lua`.
2. **Mirror task creation** — on start, call `overseer.new_task({ name = ..., cmd = ..., components = { "default" } })` and stash the returned task by poor-cli task id.
3. **Status plumbing** — forward lifecycle transitions to the mirror (`task:start`, `task:set_status`, `task:dispose` on terminal states).
4. **Output streaming** — pipe the PRD 025 stream into the overseer task buffer; truncate if overseer's buffer policy caps output.
5. **No reverse control** — mirror is read-only; we never run tasks *via* overseer in this phase.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/overseer_bridge.lua` (new)
- `nvim-poor-cli/tests/overseer_bridge_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/tasks.lua` (emit lifecycle events if not already)

### Acceptance criteria

- [ ] Each poor-cli long-running task appears as a mirror overseer task with live status.
- [ ] Overseer's output buffer receives the streamed tool output.
- [ ] No-op (no errors, no event handler registration) when overseer is absent.
- [ ] Task semantics (run location, lifecycle) unchanged on the poor-cli side.
- [ ] Plenary: `test_task_mirrored_to_overseer`, `test_noop_when_overseer_absent`.

**PRD reference:** prd/054-overseer-integration.md

---

## Agent 19F: Neogit bridge for `/commit` review

**Pain points addressed:** `/commit` runs server-side and never hands control to neogit, so users can't review or tweak the staged change set + message before committing.
**PRD reference:** `prd/056-neogit-integration.md`
**Estimated effort:** small-to-medium (3d)

### What to build

After `/commit`, if neogit is installed and `neogit.open_on_commit = true`, open neogit's status view with only the files touched by the last AI turn staged and the commit message pre-filled from the agent's proposal.

### Implementation details

1. **Config surface** — add `neogit.open_on_commit` (bool, default `false`) so the flow is opt-in.
2. **Last-turn file set** — read from the same source used by diff review (files touched in the last assistant turn).
3. **Stage + open** — call neogit's public API (`require("neogit").open({ kind = "split" })` or equivalent) after staging only the tracked files via `git add -- <paths>`.
4. **Pre-fill message** — write the proposed message into neogit's commit buffer via its API or a buffer autocmd that populates on `FileType NeogitCommitMessage`.
5. **Cancel safety** — if the user exits neogit without committing, poor-cli treats this as a cancel and does not commit itself.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/neogit_bridge.lua` (new)
- `nvim-poor-cli/tests/neogit_bridge_spec.lua` (new — mocked neogit)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (delegate `/commit` post-step to bridge when config is on)

### Acceptance criteria

- [ ] With `neogit.open_on_commit = true` and neogit present, `/commit` opens neogit staged with only AI-touched files and a pre-filled message.
- [ ] With neogit absent, `/commit` falls back to existing behavior silently.
- [ ] User-aborted neogit commit does not create a commit elsewhere.
- [ ] Plenary: `test_opens_neogit_with_prefilled_message`, `test_noop_when_neogit_absent`.

**PRD reference:** prd/056-neogit-integration.md

---

## Agent 19G: nvim-dap bridge — bug to breakpoint

**Pain points addressed:** When the AI flags a bug at `file:line`, setting a DAP breakpoint there requires the user to manually navigate and toggle.
**PRD reference:** `prd/057-nvim-dap-integration.md`
**Estimated effort:** medium (4d)

### What to build

From any diagnostic or chat `file:line` reference, `<leader>pb` sets a DAP breakpoint at that location; `<leader>pB` additionally launches a DAP run. Works only when nvim-dap is installed; no-op otherwise.

### Implementation details

1. **Detect DAP** — cached `pcall(require, "dap")` check.
2. **Parse target** — under cursor in chat or diagnostics, extract `(file, line)` using the existing parser in `diagnostics.lua`.
3. **Toggle breakpoint** — open/focus the target file at `line`, then `require("dap").toggle_breakpoint()`.
4. **Optional launch** — `<leader>pB` additionally calls `require("dap").continue()` (user's DAP config handles the adapter/launch definition — we do not ship any).
5. **Keymaps** — register only when DAP is detected, and only in buffers where the reference parser is active (chat float, diagnostics list). Respect a `dap.keymaps_enabled` config flag.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/dap_bridge.lua` (new)
- `nvim-poor-cli/tests/dap_bridge_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (register keymaps or user commands)
- `nvim-poor-cli/lua/poor-cli/diagnostics.lua` (expose shared `file:line` parser)

### Acceptance criteria

- [ ] `<leader>pb` on a chat/diagnostic reference sets a DAP breakpoint at the parsed location.
- [ ] `<leader>pB` launches DAP run via the user's existing DAP configuration.
- [ ] Nothing registers and no keymaps bind when nvim-dap is absent.
- [ ] No DAP adapter configuration shipped by poor-cli.
- [ ] Plenary: `test_breakpoint_set_at_line`, `test_noop_when_dap_absent`.

**PRD reference:** prd/057-nvim-dap-integration.md
