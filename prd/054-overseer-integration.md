# PRD 054: `overseer.nvim` long-task integration

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (4d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/tasks.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/overseer_bridge.lua`
  - `nvim-poor-cli/tests/overseer_bridge_spec.lua`

## 1. Problem

Long-running poor-cli tasks (deployments, test runs, benchmarks, embeddings) currently live in poor-cli's task system only. Overseer users want them in overseer's task runner view. LEARNING.md §3.8.

## 2. Current state

`tasks.lua` surfaces the server's task list as a panel.

## 3. Goal & non-goals

**Goal:** for every long-running poor-cli task, register an overseer Task that mirrors status (start/running/success/failed). Output streams into overseer's output buffer via the streaming tool output (PRD 025).

**Non-goals:**
- Do not run tasks *via* overseer.
- Do not depend on overseer.

## 4. Design

On `poor-cli/taskStarted` event, call `overseer.new_task(...)` if available. Plumb status events.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Bridge module.
2. Event plumbing.
3. Tests.

## 7. Testing & acceptance criteria

- `test_task_mirrored_to_overseer`
- `test_noop_when_overseer_absent`

**Done criterion**
- [ ] Tasks visible in overseer.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not depend on overseer.
- 🚫 Do not modify task semantics.

## 10. Related PRDs & references

- PRD 025.
- overseer: https://github.com/stevearc/overseer.nvim
