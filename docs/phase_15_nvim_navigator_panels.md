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
**Effort:** medium (~1w). **Risk:** low — old floating popup kept as fallback.

### What to build

Kanban buffer (four columns: todo / in-progress / done / blocked) rendered as ASCII box-drawing + extmark highlights, replacing the current linear `plan.lua` floating window for multi-step plans. The current `plan.lua` is a floating window with approve/reject actions; that approval flow is unchanged.

### Implementation details

1. Expose structured plan via RPC in `poor_cli/plan_mode.py`: `poor-cli/getPlan`, `poor-cli/updatePlanStep` (extend existing plan-mode RPCs).
2. Lua scratch buffer, vertical layout, four columns as extmarks; each column uses ASCII box-drawing + extmark highlighting.
3. No auto-inferred dependencies — dependencies are user-declared only.
4. Keymaps: `<Tab>` advance status, `<S-Tab>` regress, `<CR>` expand step, `x` mark blocked, `a` add step, `d` delete step.
5. Keep old floating popup as fallback (`g:poor_cli_plan_board_enabled`).
6. Do not persist board state across sessions.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/plan_board.lua` (new)
- `nvim-poor-cli/tests/plan_board_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/plan.lua` (modify — delegate to board when multi-step)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliPlanBoard`)
- `poor_cli/plan_mode.py` (narrow — expose structured plan via RPC)

### Out-of-scope / boundary

- Do not change plan approval semantics.
- Do not persist board state.
- Do not auto-infer dependencies between steps.

### Acceptance criteria

- [ ] `test_board_renders_four_columns` passes
- [ ] `test_tab_advances_status_via_rpc` passes
- [ ] `test_blocked_step_rendered_red` passes
- [ ] Board usable end-to-end; floating popup still reachable as fallback
- [ ] No plan approval semantics changed

---

## Agent 15B: Prompt Library Picker

**Pain points addressed:** `/prompts` lists saved prompts as flat text — no preview, no picker, no CRUD UX.
**Sub-wave:** 15.2 (requires PRD 055 picker adapter)
**Effort:** small (2–3d). **Risk:** low.

### What to build

Picker (via PRD 055 adapter) over saved prompts stored in `.poor-cli/prompts/`, with preview pane and inline CRUD actions. Replaces the current flat text list from the `/prompts` command.

### Implementation details

1. Items populated from `poor-cli/listPrompts` RPC; preview pane renders full prompt body.
2. Keymaps: `<CR>` runs prompt, `e` edits, `d` deletes, `<C-n>` clones.
3. Wire existing RPCs: `savePrompt`, `updatePrompt`, `deletePrompt`, `runPrompt`.
4. Picker adapter abstraction means backend-agnostic to telescope / fzf-lua / snacks.picker.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/prompt_library.lua` (modify — replace list view with picker launcher)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliPrompts`)
- `nvim-poor-cli/tests/prompt_library_spec.lua` (new)

### Out-of-scope / boundary

- Do not implement prompt templating here.

### Acceptance criteria

- [ ] `test_picker_lists_saved_prompts` passes
- [ ] `test_enter_runs_selected` passes
- [ ] `test_delete_removes` passes
- [ ] `:PoorCliPrompts` launches picker

---

## Agent 15C: Workflow Starter Picker

**Pain points addressed:** `/workflow` is now a one-cycle alias for slash-trigger `AutomationRule` scaffolds; no category grouping or preview.
**Sub-wave:** 15.2 (requires PRD 055)
**Effort:** small (~2d). **Risk:** low.

### What to build

Picker over slash-trigger `AutomationRule` workflow scaffolds (standup, weekly-update, pr-summary, release-notes, release-check, changelog, ci-failures, ci-debug, triage, scan-bugs, test-coverage, perf-audit, dep-drift, dep-upgrade, update-docs, skill-suggest, perf-opportunity), grouped by category tag.

### Implementation details

1. Items from `poor-cli/listWorkflows` RPC; preview shows template body.
2. Keymaps: `<CR>` runs selected workflow, `s` opens scaffold for customization.
3. Tag workflows by category (time, git, ci, refactor) — render as picker groups.
4. Use same picker adapter as 15B.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/workflow_picker.lua` (new)
- `nvim-poor-cli/tests/workflow_picker_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliWorkflow`)

### Out-of-scope / boundary

- Do not add new AutomationRule scaffolds in this PRD.

### Acceptance criteria

- [ ] `test_picker_shows_category_groups` passes
- [ ] `test_enter_runs_workflow` passes
- [ ] `:PoorCliWorkflow` accessible

---

## Agent 15D: MCP Registry Browser

**Pain points addressed:** `.poor-cli/mcp.json` edited by hand; no visibility of server status, tool counts, or the official registry. mcphub.nvim does this in its ecosystem, but we keep ours native.
**Sub-wave:** 15.2 (requires PRD 024 RPCs)
**Effort:** medium (~1w). **Risk:** low — manual edit of `mcp.json` remains supported.

### What to build

Full-screen buffer with two sections: CONFIGURED (installed servers with status, tool count, last error) and REGISTRY (paginated official registry search). Inline per-server actions.

### Layout

```
┌─── poor-cli mcp ─────────────────────────────────────────┐
│ CONFIGURED                                                │
│  ● github (stdio)   healthy   24 tools                    │
│    [toggle] [edit] [remove] [test-tool]                   │
│  ○ fs (stdio)       error: command not found              │
│                                                           │
│ REGISTRY                                                  │
│  [Search:             ]                                   │
│  ● @modelcontextprotocol/server-linear                    │
│    [install]                                              │
└───────────────────────────────────────────────────────────┘
```

### Implementation details

1. Use RPCs from PRD 024: `listMcpServers`, `healthMcp`, `registrySearch`.
2. Layout mirrors mcphub.nvim but kept native (no wrapper dep).
3. Per-server actions: `[toggle]`, `[edit]`, `[remove]`, `[test-tool]`, `[health-check]`.
4. Registry section: search box + install action per result; writes to `.poor-cli/mcp.json`.
5. Explicit prompt before any write to `.poor-cli/mcp.json`.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/mcp_registry.lua` (new)
- `nvim-poor-cli/tests/mcp_registry_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliMcp`)

### Out-of-scope / boundary

- Do not ship `mcphub.nvim` integration (would be a thin wrapper).
- Do not auto-install servers.
- Do not auto-execute registry commands.

### Acceptance criteria

- [ ] `test_configured_servers_render` passes
- [ ] `test_registry_search_filters` passes
- [ ] `test_install_prompt_writes_mcp_json` passes
- [ ] Config writes round-trip correctly

### References

- https://registry.modelcontextprotocol.io/

---

## Agent 15E: Multiplayer Room Fullscreen

**Pain points addressed:** Multiplayer is the unique differentiator but has no real Neovim UI — no share button, no driver-handoff UX, no room chat.
**Sub-wave:** 15.3 (gated on PRD 063 commit-or-cut decision)
**Effort:** medium (~1w). **Risk:** low; gated behind PRD 063.

### DECISION gate

PRD 063 resolves "commit or cut" for multiplayer. If PRD 063 = commit, ship this PRD's room UI. If PRD 063 = cut, shelve this agent entirely. Do not begin 15E work until PRD 063 has resolved.

### What to build

Tab-scoped fullscreen buffer containing:

- Room name + invite link (copy-to-clipboard button).
- Members list with roles (owner / prompter / viewer).
- Driver indicator + `[Pass driver]` action.
- Queue of hands-raised + `[Grant]` action (per queued hand).
- Event stream (join/leave/role-change/plan-events).
- Embedded chat input (room-scoped, separate from agent chat).

### Implementation details

1. Reuse existing collab RPCs: `listMembers`, `passDriver`, `raiseHand`, `grantDriver`, `roomChat`, `roomEvents`, `getInviteLink`.
2. Room chat uses a different buffer/context from agent chat.
3. Event stream shows join/leave/role-change/plan-events.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/multiplayer_room.lua` (new)
- `nvim-poor-cli/tests/multiplayer_room_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/collab.lua` (modify — delegate to room when fullscreen invoked)
- `nvim-poor-cli/lua/poor-cli/collab_ext.lua` (modify)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliRoom`)

### Out-of-scope / boundary

- Do not implement voice / video.
- Do not change / touch WebRTC transport.

### Acceptance criteria

- [ ] `test_members_rendered_with_roles` passes
- [ ] `test_pass_driver_updates_indicator` passes
- [ ] `test_hand_raised_appears_in_queue` passes
- [ ] Invite link copy works
- [ ] Room surface usable end-to-end

---

## Agent 15F: Repo Map Visualizer

**Pain points addressed:** `repo_graph.py` produces a PageRank dependency graph that users can't see. Graph is stored in SQLite with no UI today.
**Sub-wave:** 15.1 (requires PRD 022 repo-graph RPC)
**Effort:** medium (1–1.5w). **Risk:** low.

### What to build

ASCII tree-like buffer visualizing the top-N PageRank files with import neighborhoods and tree-sitter-derived top symbols. Terminal-native, no canvas. Default top-50.

### Layout

```
┌──── repo map (top 50 by pagerank) ─────────────────────────┐
│  0.041 poor_cli/core.py                                     │
│         ↓ imports: context, tools_async, provider_factory   │
│         ↑ imported-by: server/runtime, cli/main             │
│  0.027 poor_cli/context.py                                  │
│  ...                                                        │
└─────────────────────────────────────────────────────────────┘
```

### Implementation details

1. RPC: `poor-cli/repoMapTopK` (from PRD 022). Default top-50.
2. Render score + path; expand to show `↓ imports:` and `↑ imported-by:` lines.
3. Keymaps: `<CR>` opens file, `gl` expands imports/import-by, `gs` lists tree-sitter symbols.
4. Expand/collapse via extmark state on each line.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/repo_map.lua` (new)
- `nvim-poor-cli/tests/repo_map_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliRepoMap`)

### Out-of-scope / boundary

- Do not ship a 2D canvas / graph visualizer — terminal-native only.
- Do not show the full graph — top-50 default.
- Do not implement graph editing; read-only.

### Acceptance criteria

- [ ] `test_top_k_rendered_sorted` passes
- [ ] `test_expand_shows_imports` passes
- [ ] Map opens and is navigable

---

## Agent 15G: Conversation Branch Tree

**Pain points addressed:** Conversations are linear — regenerate discards prior reply; no way to keep both branches. `history.py` stores a flat list of turns today.
**Sub-wave:** 15.1 (requires PRD 043 regenerate + PRD 003 migration path)
**Effort:** medium (~1w). **Risk:** medium — schema change; migration path mandatory.

### What to build

Turn history becomes a DAG. Regenerate creates a sibling branch instead of overwriting. Right-split tree view with sibling navigation. Server persists the tree structure.

### Schema change

Turns gain `id`, `parent_id`, `branch_of`; add top-level `active_leaf` pointer.

```json
{
  "turns": [
    {"id": "t1", "parent_id": null, "role": "user"},
    {"id": "t2", "parent_id": "t1", "role": "assistant"},
    {"id": "t3", "parent_id": "t1", "role": "assistant", "branch_of": "t2"}
  ],
  "active_leaf": "t2"
}
```

Schema migration via PRD 003. Migration must be idempotent for existing flat histories.

### Implementation details

1. Migrate history schema in `poor_cli/history.py` per above.
2. Update `regenerate` (from PRD 043) to produce a sibling of the current assistant turn.
3. Lua right-split buffer renders the tree; keymaps `[[` / `]]` navigate siblings, `<CR>` switches active leaf.
4. Active leaf drives context reconstruction for the next turn.
5. Configurable max-depth for serialization (do not serialize trees older than N turns).

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/branch_tree.lua` (new)
- `nvim-poor-cli/tests/branch_tree_spec.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (add `:PoorCliBranches`)
- `poor_cli/history.py` (modify — DAG schema + migration)

### Out-of-scope / boundary

- Do not support branch merging.
- Do not rewrite history persistence beyond this schema extension.
- Do not serialize trees older than configurable N turns.

### Acceptance criteria

- [ ] `test_regenerate_creates_sibling` passes
- [ ] `test_active_leaf_drives_context` passes
- [ ] `test_tree_view_navigates` passes
- [ ] Schema migration idempotent for existing flat histories
- [ ] Branching works end-to-end; tree visualization works
