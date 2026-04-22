# Automations

poor-cli ships a unified `AutomationRule` system that handles three trigger types: cron schedules, file-system events, and slash-command invocations. Same rule shape, three triggers.

Rules live in `.poor-cli/automations.json`. Manage them via `/automation`, `/workflow`, `/skills`, or the AutomationRule helpers in `poor_cli/automations/`.

## Rule shape

```json
{
  "name": "weekly-budget-retune",
  "trigger": {
    "type": "cron",
    "schedule": "0 3 * * 1",
    "timezone": "UTC"
  },
  "steps": [
    { "kind": "run-python", "code": "from poor_cli.budget_retuning import run_retuning; run_retuning()" }
  ],
  "enabled": true,
  "history_max": 50
}
```

Required fields: `name` (unique), `trigger`, `steps[]`. Optional: `enabled` (default true), `history_max` (cap of stored runs), `tags`.

## Trigger types

### `cron`

Standard 5-field cron expression. Timezone defaults to UTC; override per rule. Examples:

| Schedule | Meaning |
|---|---|
| `0 3 * * 1` | Mondays at 03:00 |
| `*/15 * * * *` | Every 15 minutes |
| `0 9-17 * * 1-5` | Hourly during business hours, weekdays |

Cron evaluation runs in `automation_manager.py`; `poor-cli automation serve` daemonizes the scheduler. For one-off testing: `poor-cli automation run-now <name>`.

### `event`

File-system events from `file_watcher.py`:

```json
{
  "type": "event",
  "events": ["file_changed", "file_created"],
  "paths": ["src/**/*.py"],
  "debounce_ms": 500
}
```

Useful for "run tests when X changes" or "regenerate docs when Y is touched".

### `slash`

Custom slash command — invoked by user typing `/<name>` in chat:

```json
{
  "type": "slash",
  "name": "deploy-staging"
}
```

Then `/deploy-staging` in chat runs the rule's steps. Slash-trigger rules are discoverable through `/workflow`.

## Step kinds

| Kind | Purpose |
|---|---|
| `run-python` | Inline Python via `exec`. Runs in poor-cli's process; full access to package. |
| `run-shell` | Subprocess. Respects sandbox preset. |
| `prompt` | Send a fixed prompt to the active model (handy for "summarize today's commits"). |
| `tool-call` | Invoke a single tool with fixed arguments. |
| `notify` | Emit a CLI or JSON-RPC notification. |

Each step gets a per-rule timeout (default 60s) and writes to the rule's run history.

## Examples

### Weekly budget re-tune (CB5)

```json
{
  "name": "weekly-budget-retune",
  "trigger": { "type": "cron", "schedule": "0 3 * * 1" },
  "steps": [
    { "kind": "run-python", "code": "from poor_cli.budget_retuning import run_retuning; run_retuning()" }
  ]
}
```

Mondays 03:00 UTC, run `ThinkingBudgetOptimizer.analyze()` and persist a fresh tuning.

### Auto-test on save

```json
{
  "name": "auto-test-on-save",
  "trigger": {
    "type": "event",
    "events": ["file_changed"],
    "paths": ["poor_cli/**/*.py", "tests/**/*.py"],
    "debounce_ms": 800
  },
  "steps": [
    { "kind": "run-shell", "command": "make test" }
  ]
}
```

### Slash workflow: standup summary

```json
{
  "name": "standup",
  "trigger": { "type": "slash", "name": "standup" },
  "steps": [
    { "kind": "prompt", "text": "Summarize my git activity since yesterday in 5 bullet points." }
  ]
}
```

Then `/standup` in chat fires it.

## Run history

Every rule run writes to `.poor-cli/automations.db` with status, timing, output, and any errors. Inspect:

- `/automation history <name>` — recent runs.
- `/automation replay <name>` — re-execute the last successful run.

`history_max` per rule trims the oldest. Default 50; bump if you need a longer trail.

## Auditing + safety

- Every step execution writes an `AuditEventType.AUTOMATION` row to `.poor-cli/audit.db`.
- `run-shell` steps respect the active sandbox preset; pre-tool hooks fire as for any tool call.
- Cron rules running unattended can hit cost guardrails like any model call — use `/cost` to monitor.

## Migration from legacy

Pre-PRD 064, three concepts coexisted: AutomationRule, custom slash commands, and skills. PRD 064 unified them under AutomationRule + skills. Legacy `.poor-cli/commands.json` is migrated automatically on first load (see `automation_manager.py::migrate_legacy`).

## See also

- `tests/test_automations.py` — round-trip + scheduler tests.
