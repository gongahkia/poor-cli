# PRD 033: Workflow Starter picker

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (2d)
- **Blocked by:** 055
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/workflow_picker.lua`
  - `nvim-poor-cli/tests/workflow_picker_spec.lua`

## 1. Problem

`/workflow` shows workflows as text. LEARNING.md §3.4.

## 2. Current state

`workflow_templates.py` defines templates (standup, weekly-update, pr-summary, release-notes, release-check, changelog, ci-failures, ci-debug, triage, scan-bugs, test-coverage, perf-audit, dep-drift, dep-upgrade, update-docs, skill-suggest, perf-opportunity).

## 3. Goal & non-goals

**Goal:** picker with preview of workflow template contents; `<CR>` runs; `s` opens scaffold (for customization). Tags by category (time, git, ci, refactor).

## 4. Design

Use picker adapter. Items from `poor-cli/listWorkflows`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Adapter.
2. RPC invocation.
3. Tests.

## 7. Testing & acceptance criteria

- `test_picker_shows_category_groups`
- `test_enter_runs_workflow`

**Done criterion**
- [ ] Workflow picker accessible via `:PoorCliWorkflow`.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not add new workflow templates.

## 10. Related PRDs & references

- PRD 055.
