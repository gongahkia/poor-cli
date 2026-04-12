# PRD 032: Prompt Library Browser picker

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (2–3d)
- **Blocked by:** 055
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/prompt_library.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/tests/prompt_library_spec.lua`

## 1. Problem

`/prompts` lists saved prompts as text. No picker, no preview. LEARNING.md §3.4.

## 2. Current state

Backend stores saved prompts under `.poor-cli/prompts/`. Lua command just lists names.

## 3. Goal & non-goals

**Goal:** picker (via PRD 055) listing saved prompts with preview; `<CR>` runs, `e` edits, `d` deletes, `<C-n>` clones.

## 4. Design

Uses picker adapter. Items populated from `poor-cli/listPrompts`. Preview pane shows full prompt content.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Use picker adapter.
2. Wire RPCs (`savePrompt`, `updatePrompt`, `deletePrompt`, `runPrompt`).
3. Tests.

## 7. Testing & acceptance criteria

- `test_picker_lists_saved_prompts`
- `test_enter_runs_selected`
- `test_delete_removes`

**Done criterion**
- [ ] Picker launched via `:PoorCliPrompts`.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not implement prompt templating in this PRD.

## 10. Related PRDs & references

- PRD 055.
