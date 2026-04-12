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

**Blocked by:** 16C (adapter), and upstream PRD 020 (capability discovery — assumed already landed).
**Estimated effort:** medium (4–5d).

### Problem

`:PoorCliSwitchProvider` takes a text arg. Discoverability is poor. Users don't know which models are available, their capabilities (cache? thinking?), or estimated cost per 1K tokens. Reference: LEARNING.md §3.4.

### What to build

A modal picker invoked via `:PoorCliSwitchProvider` (no-arg form) that lists providers × models with capability icons (streaming, thinking, caching, vision) and $$/1K-token pricing indicators, and switches the active provider+model on selection. Replaces the discoverability-hostile text-arg form without removing it.

### Non-goals / boundary

- Do not implement capability discovery (PRD 020 responsibility; assumed landed).
- Do not change economy logic.
- Do not implement per-model pricing discovery.
- Do not fetch from a remote catalog.

### Item rendering (reference layout)

```
anthropic / claude-sonnet-4        [stream] [think] [cache] [vision]   $3.00/$15.00  (current)
anthropic / claude-3-5-haiku       [stream]                             $0.80/$4.00
openai / gpt-5.1                   [stream] [think]        [vision]    $2.50/$10.00
gemini / gemini-2.5-flash          [stream]                [vision]    $0.075/$0.30
ollama / llama3.1                  [stream]                             local (free)
```

Preview pane (right side): expanded capability list, model description, last-used timestamp.

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
- [ ] Modal opens, picks, and switches end-to-end.
- [ ] Capabilities are visible in the rendered list.
- [ ] `test_items_include_capability_icons` passes.
- [ ] `test_selecting_item_calls_switch_rpc` passes.
- [ ] `test_current_model_marked` passes.
- [ ] CLI-arg form of `:PoorCliSwitchProvider` still works unchanged.

### Rollback / risk

Low. Command-line variant still works, so failure of the modal path is non-blocking.

---

## Agent 16B: Onboarding rerun + guided tour

**Blocked by:** none. Parallel-safe with 16C.
**Estimated effort:** small-to-medium (4d).

### Problem

Onboarding is one-shot. Users forget keybinds; cannot replay; no milestone progression. Reference: LEARNING.md §3.10.

### What to build

1. `:PoorCliOnboarding` always re-opens the onboarding UI.
2. Milestone tour: at N completions / M turns, suggest the next feature (e.g. "Try Plan Mode with `:PoorCliPlan`").
3. Interactive ~2-minute guided tour, 7 steps: provider select → prompt entry → diff review → checkpoint → rollback → (two more feature steps). Each step is a fake guided action the user triggers; no real LLM calls.
4. Settings-cheatsheet export: `<leader>po?` dumps the current resolved config as a paste-ready snippet.

### Non-goals / boundary

- Do not record real LLM interactions in the tour.
- Do not persist tour completion state per-project (global is fine).
- Do not gate any feature behind tour completion — it is purely informational.

### Implementation details

1. **Rerunnable onboarding** — `:PoorCliOnboarding` always opens the onboarding UI regardless of dismissal state. The dismissed flag in `.poor-cli/onboarding.json` only suppresses auto-open at startup, not manual invocation.
2. **Milestone counters** — extend `.poor-cli/onboarding.json` with event counters (`completions`, `turns`, `diffs_reviewed`, etc.). Bump them from existing event hooks in the plugin.
3. **Milestone triggers** — new module `onboarding_milestones.lua` defines `{event, threshold, suggestion}` tuples (e.g. "after 10 completions → suggest Plan Mode via `:PoorCliPlan`"). Fire once per milestone; persist fired-set in the same JSON.
4. **Guided tour (7 steps)** — provider select → prompt entry → diff review → checkpoint → rollback → (two more). Each step is a fake guided action triggered by the user; no real LLM calls. Stepwise controls: `n` next, `p` previous, `q` quit. Tour completion is global, not per-project.
5. **Cheatsheet export** — `<leader>po?` dumps the current resolved plugin config as a paste-ready snippet (Lua table literal) into a scratch buffer. Keep it deterministic so users can diff against defaults.

### Files to create/modify

- `nvim-poor-cli/lua/poor-cli/onboarding.lua` (modify — rerun, tour flow, cheatsheet)
- `nvim-poor-cli/lua/poor-cli/onboarding_milestones.lua` (new)
- `nvim-poor-cli/lua/poor-cli/commands.lua` (modify — `:PoorCliOnboarding` always-open)

### Acceptance criteria

- [ ] `:PoorCliOnboarding` opens the UI even after prior dismissal.
- [ ] Milestone suggestion fires once after its threshold is crossed.
- [ ] Guided tour progresses with `n`/`p`/`q` through all 7 steps.
- [ ] Tour makes no real LLM calls.
- [ ] `<leader>po?` writes current config to a scratch buffer as a paste-ready snippet.
- [ ] Cheatsheet content matches the resolved config.
- [ ] `test_onboarding_rerun_always_opens` passes.
- [ ] `test_milestone_fires_after_N_completions` passes.
- [ ] `test_cheatsheet_export_matches_config` passes.

### Rollback / risk

Low. State file format is additive; old entries remain readable.

---

## Agent 16C: Picker adapter layer (Telescope / fzf-lua / Snacks)

**Blocked by:** none. Prerequisite for 16A.
**Estimated effort:** medium (1w).

### Problem

Plugin currently integrates only with Telescope (with `vim.ui.select` fallback). fzf-lua and Snacks picker users are left out. Reference: LEARNING.md §3.7.

### What to build

A single `pickers.pick(items, opts)` API that auto-detects the available picker backend (Snacks → Telescope → fzf-lua → `vim.ui.select`) and routes accordingly. All picker call sites in the plugin migrate to this adapter; no backend is a hard dependency.

### Non-goals / boundary

- Do not implement a picker UI ourselves.
- Do not hard-depend on any backend.
- Do not fork any picker.

### Adapter sketch

```lua
-- pickers.lua
local M = {}
local function detect()
  if pcall(require, "snacks.picker") then return "snacks" end
  if pcall(require, "telescope") then return "telescope" end
  if pcall(require, "fzf-lua") then return "fzf-lua" end
  return "native"
end

function M.pick(items, opts)
  -- items: { {id, label, preview, data}... }
  -- opts:  { title, on_pick }
end
return M
```

### Implementation details

1. **Adapter module** — `pickers.lua` exposes `M.pick(items, opts)` where `items` is a list of `{id, label, preview, data}` and `opts` is `{title, on_pick}`. Detection uses `pcall(require, ...)` with the precedence: `snacks.picker` > `telescope` > `fzf-lua` > native `vim.ui.select`.
2. **Per-backend shims** — one implementation per backend. Keep them colocated in `pickers.lua` or split into `pickers_<backend>.lua` files; either is permitted. Each shim translates the common item shape into backend-specific calls and wires `on_pick` to the selected item's `data`.
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

### Rollback / risk

Low. Adapter is additive; Telescope path remains the default when present.
