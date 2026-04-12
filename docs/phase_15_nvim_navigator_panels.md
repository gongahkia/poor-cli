# Phase 15: Nvim Navigator Panels

**Priority:** High — transforms invisible backend capabilities (plans, prompts, workflows, MCP, multiplayer, repo graph, history) into navigable Neovim surfaces.
**Estimated agents:** 7 (with sub-waves due to collisions)
**Dependencies:** PRDs 055 (picker adapter), 024 (MCP RPCs), 063 (multiplayer commit/cut), 022 (repo graph RPC), 043 (regenerate), 003 (history migration).
**Philosophy:** Every agent adds one navigator surface under `nvim-poor-cli/lua/poor-cli/`. Terminal-native, no external UI deps. Backend RPCs mostly already exist.

---

## File-scope map & collision warning

All 7 agents write under `nvim-poor-cli/lua/poor-cli/`. Two files are touched by **every** agent:

| File | Agents touching | Resolution |
|---|---|---|
| `nvim-poor-cli/lua/poor-cli/commands.lua` | 15A, 15B, 15C, 15D, 15E, 15F, 15G | **HIGH collision** — serialize; each agent adds one `:PoorCli*` command entry only |
| `nvim-poor-cli/lua/poor-cli/init.lua` | (only if lazy-loading modules is registered there) | **Low-med** — coordinate `require()` registration |
| `nvim-poor-cli/lua/poor-cli/plan.lua` | 15A | sole owner |
| `nvim-poor-cli/lua/poor-cli/prompt_library.lua` | 15B | sole owner |
| `nvim-poor-cli/lua/poor-cli/collab.lua` / `collab_ext.lua` | 15E | sole owner |
| `poor_cli/plan_mode.py` | 15A | sole owner (narrow RPC surface) |
| `poor_cli/history.py` | 15G | sole owner (schema migration) |

**Proposed sub-waves** (to avoid `commands.lua` merge hell):

- **Sub-wave 15.1 (parallel, no picker dep):** 15A (plan board), 15F (repo map), 15G (branch tree)
- **Sub-wave 15.2 (parallel, picker-based, after PRD 055):** 15B (prompt library), 15C (workflow starter), 15D (MCP registry)
- **Sub-wave 15.3 (after PRD 063 commit decision):** 15E (multiplayer room)

Each sub-wave ends with a single rebase/merge pass on `commands.lua`. Agents must add command entries as isolated blocks with a PRD-tagged comment (`-- PRD 031: plan board`) so conflict resolution is mechanical.

New files per agent do not collide.

---

## Agent 15A: Plan Board Kanban

**Pain points addressed:** Linear plan popup hides dependencies; multi-step plans with blocked/in-progress/done states need a board.
**Sub-wave:** 15.1

### What to build

Kanban buffer (four columns: todo / in-progress / done / blocked) rendered as ASCII box-drawing + extmark highlights, replacing the current linear `plan.lua` floating window for multi-step plans.

### Implementation details

1. Expose structured plan via RPC in `poor_cli/plan_mode.py`: `poor-cli/getPlan`, `poor-cli/updatePlanStep` (extend existing plan-mode RPCs).
2. Lua scratch buffer, vertical layout, four columns as extmarks; no auto-inferred dependencies.
3. Keymaps: `<Tab>` advance status, `<S-Tab>` regress, `<CR>` expand step, `x` mark blocked, `a` add step, `d` delete step.
4. Keep old floating popup as fallback (`g:poor_cli_plan_board_enabled`).
5. Do not persist board state across sessions.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/plan_board.lua` (new)
- `nvim-poor-cli/tests/plan_board_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/plan.lua` (modify — delegate to board when multi-step)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliPlanBoard`)
- `poor_cli/plan_mode.py` (narrow — expose structured plan via RPC)

### Acceptance criteria

- [ ] `test_board_renders_four_columns` passes
- [ ] `test_tab_advances_status_via_rpc` passes
- [ ] `test_blocked_step_rendered_red` passes
- [ ] Board usable end-to-end; floating popup still reachable as fallback
- [ ] No plan approval semantics changed

**PRD reference:** prd/031-plan-board-kanban.md

---

## Agent 15B: Prompt Library Picker

**Pain points addressed:** `/prompts` lists saved prompts as flat text — no preview, no picker, no CRUD UX.
**Sub-wave:** 15.2 (requires PRD 055 picker adapter)

### What to build

Picker (via PRD 055 adapter) over saved prompts stored in `.poor-cli/prompts/`, with preview pane and inline CRUD actions.

### Implementation details

1. Items populated from `poor-cli/listPrompts` RPC; preview pane renders full prompt body.
2. Keymaps: `<CR>` runs prompt, `e` edits, `d` deletes, `<C-n>` clones.
3. Wire existing RPCs: `savePrompt`, `updatePrompt`, `deletePrompt`, `runPrompt`.
4. Do **not** implement prompt templating here — out of scope.
5. Picker adapter abstraction means backend-agnostic to telescope / fzf-lua / snacks.picker.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/prompt_library.lua` (modify — replace list view with picker launcher)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliPrompts`)
- `nvim-poor-cli/tests/prompt_library_spec.lua` (new)

### Acceptance criteria

- [ ] `test_picker_lists_saved_prompts` passes
- [ ] `test_enter_runs_selected` passes
- [ ] `test_delete_removes` passes
- [ ] `:PoorCliPrompts` launches picker

**PRD reference:** prd/032-prompt-library-picker.md

---

## Agent 15C: Workflow Starter Picker

**Pain points addressed:** `/workflow` surfaces templates as plain text; no category grouping or preview.
**Sub-wave:** 15.2 (requires PRD 055)

### What to build

Picker over workflow templates defined in `workflow_templates.py` (standup, weekly-update, pr-summary, release-notes, release-check, changelog, ci-failures, ci-debug, triage, scan-bugs, test-coverage, perf-audit, dep-drift, dep-upgrade, update-docs, skill-suggest, perf-opportunity), grouped by category tag.

### Implementation details

1. Items from `poor-cli/listWorkflows` RPC; preview shows template body.
2. Keymaps: `<CR>` runs selected workflow, `s` opens scaffold for customization.
3. Tag workflows by category (time, git, ci, refactor) — render as picker groups.
4. Use same picker adapter as 15B.
5. Do not add new workflow templates in this PRD.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/workflow_picker.lua` (new)
- `nvim-poor-cli/tests/workflow_picker_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliWorkflow`)

### Acceptance criteria

- [ ] `test_picker_shows_category_groups` passes
- [ ] `test_enter_runs_workflow` passes
- [ ] `:PoorCliWorkflow` accessible

**PRD reference:** prd/033-workflow-starter-picker.md

---

## Agent 15D: MCP Registry Browser

**Pain points addressed:** `.poor-cli/mcp.json` edited by hand; no visibility of server status, tool counts, or the official registry.
**Sub-wave:** 15.2 (requires PRD 024 RPCs)

### What to build

Full-screen buffer with two sections: CONFIGURED (installed servers with status, tool count, last error) and REGISTRY (paginated official registry search). Inline per-server actions.

### Implementation details

1. Use RPCs from PRD 024: `listMcpServers`, `healthMcp`, `registrySearch`.
2. Layout mirrors mcphub.nvim but kept native (no wrapper dep).
3. Per-server actions: `[toggle]`, `[edit]`, `[remove]`, `[test-tool]`, `[health-check]`.
4. Registry section: search box + install action per result; writes to `.poor-cli/mcp.json`.
5. Do not auto-install or auto-execute registry commands — explicit prompt before write.
6. Manual `mcp.json` edit remains supported (rollback path).

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/mcp_registry.lua` (new)
- `nvim-poor-cli/tests/mcp_registry_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliMcp`)

### Acceptance criteria

- [ ] `test_configured_servers_render` passes
- [ ] `test_registry_search_filters` passes
- [ ] `test_install_prompt_writes_mcp_json` passes
- [ ] Config writes round-trip correctly

**PRD reference:** prd/035-mcp-registry-browser.md

---

## Agent 15E: Multiplayer Room Fullscreen

**Pain points addressed:** Multiplayer is the unique differentiator but has no real Neovim UI — no share button, no driver-handoff UX, no room chat.
**Sub-wave:** 15.3 (gated on PRD 063 commit-or-cut decision)

### What to build

Tab-scoped fullscreen buffer: room name, invite link with copy-to-clipboard, members with roles (owner/prompter/viewer), driver indicator, hands-raised queue, event stream, embedded room-scoped chat input.

### Implementation details

1. Reuse existing collab RPCs: `listMembers`, `passDriver`, `raiseHand`, `grantDriver`, `roomChat`, `roomEvents`, `getInviteLink`.
2. Actions: `[Pass driver]`, `[Grant]` (per queued hand), copy invite link.
3. Room chat is separate from agent chat — different buffer/context.
4. Event stream shows join/leave/role-change/plan-events.
5. Do not implement voice/video; do not touch WebRTC transport.
6. Gate behind PRD 063 outcome — if multiplayer cut, this PRD shelves.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/multiplayer_room.lua` (new)
- `nvim-poor-cli/tests/multiplayer_room_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/collab.lua` (modify — delegate to room when fullscreen invoked)
- `nvim-poor-cli/lua/poor-cli/collab_ext.lua` (modify)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliRoom`)

### Acceptance criteria

- [ ] `test_members_rendered_with_roles` passes
- [ ] `test_pass_driver_updates_indicator` passes
- [ ] `test_hand_raised_appears_in_queue` passes
- [ ] Invite link copy works
- [ ] Room surface usable end-to-end

**PRD reference:** prd/037-multiplayer-room-fullscreen.md

---

## Agent 15F: Repo Map Visualizer

**Pain points addressed:** `repo_graph.py` produces a PageRank dependency graph that users can't see.
**Sub-wave:** 15.1 (requires PRD 022 repo-graph RPC)

### What to build

ASCII tree-like buffer visualizing the top-N PageRank files with import neighborhoods and tree-sitter-derived top symbols. Terminal-native, no canvas.

### Implementation details

1. RPC: `poor-cli/repoMapTopK` (from PRD 022). Default top-50.
2. Render score + path; expand to show `↓ imports:` and `↑ imported-by:` lines.
3. Keymaps: `<CR>` opens file, `gl` expands imports/import-by, `gs` lists tree-sitter symbols.
4. Expand/collapse via extmark state on each line.
5. Do not ship 2D canvas or graph editor — terminal-only, read-only.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/repo_map.lua` (new)
- `nvim-poor-cli/tests/repo_map_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliRepoMap`)

### Acceptance criteria

- [ ] `test_top_k_rendered_sorted` passes
- [ ] `test_expand_shows_imports` passes
- [ ] Map opens and is navigable

**PRD reference:** prd/038-repo-map-visualizer.md

---

## Agent 15G: Conversation Branch Tree

**Pain points addressed:** Conversations are linear — regenerate discards prior reply; no way to keep both branches.
**Sub-wave:** 15.1 (requires PRD 043 regenerate + PRD 003 migration path)

### What to build

Turn history becomes a DAG. Regenerate creates a sibling branch instead of overwriting. Right-split tree view with sibling navigation.

### Implementation details

1. Schema change in `poor_cli/history.py` — turns gain `id`, `parent_id`, `branch_of`; top-level `active_leaf` pointer. Migration via PRD 003.
2. Update `regenerate` (from PRD 043) to produce a sibling of the current assistant turn.
3. Lua right-split buffer renders tree; keymaps `[[` / `]]` navigate siblings, `<CR>` switches active leaf.
4. Active leaf drives context reconstruction for next turn.
5. Do not support branch merging. Configurable max-depth for serialization.
6. Risk: medium (schema change) — migration path mandatory.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/branch_tree.lua` (new)
- `nvim-poor-cli/tests/branch_tree_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliBranches`)
- `poor_cli/history.py` (modify — DAG schema + migration)

### Acceptance criteria

- [ ] `test_regenerate_creates_sibling` passes
- [ ] `test_active_leaf_drives_context` passes
- [ ] `test_tree_view_navigates` passes
- [ ] Schema migration idempotent for existing flat histories

**PRD reference:** prd/039-conversation-branch-tree.md
