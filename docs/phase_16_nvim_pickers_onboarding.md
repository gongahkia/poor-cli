# Phase 16: Nvim Pickers & Onboarding

**Priority:** Medium — DX and discoverability improvements for the Neovim plugin surface.
**Estimated agents:** 3 (staged — not all parallel).
**Dependencies:** 16C (picker adapter layer) is a prerequisite for 16A (provider/model picker), which consumes `pickers.pick`. 16B is independent.
**Philosophy:** Unblock picker-dependent UX by landing the adapter first; rerunnable onboarding ships in parallel since it touches a disjoint file set.

---

## File scope table

| File | 16A | 16B | 16C |
|------|-----|-----|-----|
| `nvim-poor-cli/lua/poor-cli/providers.lua` | modify | | |
| `nvim-poor-cli/lua/poor-cli/commands.lua` | modify | modify | |
| `nvim-poor-cli/lua/poor-cli/keymaps.lua` | modify | | |
| `nvim-poor-cli/lua/poor-cli/provider_picker.lua` | new | | |
| `nvim-poor-cli/tests/provider_picker_spec.lua` | new | | |
| `nvim-poor-cli/lua/poor-cli/onboarding.lua` | | modify | |
| `nvim-poor-cli/lua/poor-cli/onboarding_milestones.lua` | | new | |
| `nvim-poor-cli/lua/poor-cli/pickers.lua` | | | new |
| `nvim-poor-cli/lua/poor-cli/telescope.lua` | | | modify (narrow) |
| `nvim-poor-cli/tests/pickers_spec.lua` | | | new |

### Intra-phase collisions

- `commands.lua` is touched by both **16A** (registers `:PoorCliSwitchProvider` modal entry) and **16B** (registers `:PoorCliOnboarding` rerun). Edits are additive to disjoint command blocks; land 16B first (Wave 16.1) so 16A (Wave 16.2) rebases cleanly against it.
- **16A** consumes `pickers.pick(items, opts)` from **16C**. 16A cannot merge until 16C is on `main`.

### Proposed sub-waves

- **Wave 16.1 (parallel):** 16C (picker adapter) + 16B (onboarding rerun). Disjoint file sets.
- **Wave 16.2 (solo, after 16C merges):** 16A (provider/model picker) — depends on the adapter API.

---

## Agent 16A: Provider / Model Picker modal

**Blocked by:** 16C (adapter), and upstream PRD 020 (capability discovery — assumed already landed per the source PRD).
**Estimated effort:** medium (4–5d).

### What to build

A modal picker invoked via `:PoorCliSwitchProvider` (no-arg form) that lists providers × models with capability icons and pricing indicators, and switches the active provider+model on selection. Replaces the discoverability-hostile text-arg form without removing it.

### Implementation details

1. **Item list construction** — pull from `provider_catalog.py` over the existing RPC surface and merge in capability flags (streaming, thinking, caching, vision) discovered via PRD 020. Each item is `{id, label, preview, data}` shaped for the adapter.
2. **Label formatting** — render `provider / model  <icons>  $in/$out` with a `(current)` marker on the active selection. Locals show `local (free)`. Last-used item floats to the top of the list.
3. **Preview pane** — right-side preview with expanded capability list, model description, and last-used timestamp. Supply the preview text in the adapter item payload so backends that support previews render it natively.
4. **Picker invocation** — call `require("poor-cli.pickers").pick(items, { title = "Switch provider/model", on_pick = ... })`. Do not branch on backend; the adapter handles that.
5. **Switch RPC** — on pick, fire `poor-cli/switchProvider` with `{provider, model}`. Handle RPC failure with a `vim.notify` error; do not silently no-op.
6. **Last-used cache** — persist to an existing plugin state file (e.g. reuse the onboarding state dir) keyed by `{provider, model}` with a timestamp. Surface top-1 most-recent at list head.
7. **Keymap + command** — register `:PoorCliSwitchProvider` (no-arg → modal; with-arg → existing direct switch) and bind a leader key (e.g. `<leader>pp`) in `keymaps.lua`.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/provider_picker.lua` (new)
- `nvim-poor-cli/lua/poor-cli/providers.lua` (modify — expose picker entry)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (modify — no-arg dispatch to picker)
- `nvim-poor-cli/lua/poor-cli/keymaps.lua` (modify — add leader binding)
- `nvim-poor-cli/tests/provider_picker_spec.lua` (new)

### Acceptance criteria

- [ ] `:PoorCliSwitchProvider` with no args opens the modal via the adapter.
- [ ] Each item shows provider/model, capability icons, and pricing.
- [ ] Current model is marked.
- [ ] Selecting an item fires the `switchProvider` RPC with the correct payload.
- [ ] Last-used model appears at the top on subsequent opens.
- [ ] `test_items_include_capability_icons` passes.
- [ ] `test_selecting_item_calls_switch_rpc` passes.
- [ ] `test_current_model_marked` passes.
- [ ] CLI-arg form of `:PoorCliSwitchProvider` still works unchanged.

**PRD reference:** prd/030-provider-model-picker.md

---

## Agent 16B: Onboarding rerun + guided tour

**Blocked by:** none. Parallel-safe with 16C.
**Estimated effort:** small-to-medium (4d).

### What to build

Make onboarding re-runnable, add event-driven milestone prompts for feature discovery, ship an interactive 7-step guided tour, and add a settings-cheatsheet export keybind.

### Implementation details

1. **Rerunnable onboarding** — `:PoorCliOnboarding` always opens the onboarding UI regardless of dismissal state. The dismissed flag in `.poor-cli/onboarding.json` only suppresses auto-open at startup, not manual invocation.
2. **Milestone counters** — extend `.poor-cli/onboarding.json` with event counters (`completions`, `turns`, `diffs_reviewed`, etc.). Bump them from existing event hooks in the plugin.
3. **Milestone triggers** — new module `onboarding_milestones.lua` defines `{event, threshold, suggestion}` tuples (e.g. "after 10 completions → suggest Plan Mode via `:PoorCliPlan`"). Fire once per milestone; persist fired-set in the same JSON.
4. **Guided tour (7 steps)** — provider select → prompt entry → diff review → checkpoint → rollback → (two more per PRD). Each step is a fake guided action triggered by the user; no real LLM calls. Stepwise controls: `n` next, `p` previous, `q` quit. Tour completion is global, not per-project.
5. **Cheatsheet export** — `<leader>po?` dumps the current resolved plugin config as a paste-ready snippet (Lua table literal) into a scratch buffer. Keep it deterministic so users can diff against defaults.
6. **No feature gating** — tour completion must not gate any feature; it is purely informational.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/onboarding.lua` (modify — rerun, tour flow, cheatsheet)
- `nvim-poor-cli/lua/poor-cli/onboarding_milestones.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (modify — `:PoorCliOnboarding` always-open)

### Acceptance criteria

- [ ] `:PoorCliOnboarding` opens the UI even after prior dismissal.
- [ ] Milestone suggestion fires once after its threshold is crossed.
- [ ] Guided tour progresses with `n`/`p`/`q` through all steps.
- [ ] Tour makes no real LLM calls.
- [ ] `<leader>po?` writes current config to a scratch buffer as a paste-ready snippet.
- [ ] `test_onboarding_rerun_always_opens` passes.
- [ ] `test_milestone_fires_after_N_completions` passes.
- [ ] `test_cheatsheet_export_matches_config` passes.

**PRD reference:** prd/040-onboarding-rerun-tour.md

---

## Agent 16C: Picker adapter layer (Telescope / fzf-lua / Snacks)

**Blocked by:** none. Prerequisite for 16A.
**Estimated effort:** medium (1w).

### What to build

A single `pickers.pick(items, opts)` API that auto-detects the available picker backend (Snacks → Telescope → fzf-lua → `vim.ui.select`) and routes accordingly. All picker call sites in the plugin migrate to this adapter; no backend is a hard dependency.

### Implementation details

1. **Adapter module** — `pickers.lua` exposes `M.pick(items, opts)` where `items` is a list of `{id, label, preview, data}` and `opts` is `{title, on_pick}`. Detection uses `pcall(require, ...)` with the precedence: `snacks.picker` > `telescope` > `fzf-lua` > native `vim.ui.select`.
2. **Per-backend shims** — one implementation per backend. Keep them colocated in `pickers.lua` or split into `pickers_<backend>.lua` files; the PRD permits either. Each shim translates the common item shape into backend-specific calls and wires `on_pick` to the selected item's `data`.
3. **Preview forwarding** — Snacks and Telescope get a real preview pane populated from `item.preview`; fzf-lua uses its preview callback; native fallback ignores preview (label-only).
4. **Call-site migration** — `telescope.lua` shrinks to a thin shim (or its direct callers move to the adapter). Grep existing call sites inside the plugin and route them through `pickers.pick`.
5. **No forks, no self-hosting** — never implement a picker UI ourselves; never hard-require any backend.
6. **Tests** — mock `require` to simulate each backend's presence/absence and assert detection precedence, native fallback, and preview forwarding.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/pickers.lua` (new — adapter + backends)
- `nvim-poor-cli/lua/poor-cli/telescope.lua` (modify — narrow to a shim or route callers through adapter)
- `nvim-poor-cli/tests/pickers_spec.lua` (new)

### Acceptance criteria

- [ ] `pickers.pick(items, opts)` works with Snacks, Telescope, fzf-lua, and native fallback.
- [ ] Detection precedence is Snacks > Telescope > fzf-lua > native.
- [ ] Native fallback works with no picker plugin installed.
- [ ] Preview text forwards correctly to backends that support previews.
- [ ] All existing picker call sites in the plugin route through the adapter.
- [ ] No hard dependency added on any picker plugin.
- [ ] `test_detect_prefers_snacks` passes.
- [ ] `test_native_fallback_works` passes.
- [ ] `test_items_preview_forwarded_correctly` passes.

**PRD reference:** prd/055-picker-adapter-layer.md
