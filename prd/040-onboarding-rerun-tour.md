# PRD 040: Onboarding rerun + guided tour

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small-to-medium (4d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/onboarding.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`

## 1. Problem

Onboarding is one-shot. Users forget keybinds; cannot replay; no milestone progression. LEARNING.md §3.10.

## 2. Current state

Onboarding runs once and stays dismissed.

## 3. Goal & non-goals

**Goal:**
1. `:PoorCliOnboarding` always re-opens.
2. Milestone tour: at N completions / M turns, suggest the next feature ("Try Plan Mode with `:PoorCliPlan`").
3. Interactive 2-minute tour: provider → prompt → diff review → checkpoint → rollback. Each step has a fake guided action the user triggers.
4. Settings-cheatsheet export: `<leader>po?` → dump current config as a paste-ready snippet.

**Non-goals:**
- Do not record real LLM interactions in the tour.
- Do not persist tour completion state per-project (global is fine).

## 4. Design

Milestone tracking in `.poor-cli/onboarding.json` with event counters; triggers defined in `nvim-poor-cli/lua/poor-cli/onboarding_milestones.lua` (new).

## 5. Files to create / modify / delete

Modify `onboarding.lua`. Add `onboarding_milestones.lua`.

## 6. Implementation plan

1. Make onboarding re-runnable.
2. Add milestone counters (event-driven).
3. Guided tour flow (7 steps, stepwise `n`/`p`/`q`).
4. Cheatsheet export.

## 7. Testing & acceptance criteria

- `test_onboarding_rerun_always_opens`
- `test_milestone_fires_after_N_completions`
- `test_cheatsheet_export_matches_config`

**Done criterion**
- [ ] Rerun works.
- [ ] Tour progresses.
- [ ] Cheatsheet correct.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not gate features behind tour completion.

## 10. Related PRDs & references

- LEARNING.md §3.10.
