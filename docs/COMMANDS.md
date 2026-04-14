# Slash Command Reference

poor-cli ships **122 slash commands** across 10 categories.
Generated from `poor_cli/command_manifest.json` — do not edit by hand.
Re-run `python scripts/generate_command_docs.py` after manifest changes.

## Categories

- [Automation & Tasks](#automation-tasks) (9 commands)
- [Collaboration](#collaboration) (4 commands)
- [Context & Reuse](#context-reuse) (15 commands)
- [Core Workflow](#core-workflow) (24 commands)
- [Economy & Output](#economy-output) (5 commands)
- [Git & Workspace](#git-workspace) (1 commands)
- [Providers & Config](#providers-config) (16 commands)
- [Review & Safety](#review-safety) (22 commands)
- [Services & Shell](#services-shell) (9 commands)
- [Workflows](#workflows) (17 commands)

## Automation & Tasks

| Command | Description |
|---|---|
| `/automation` | Inspect AutomationRule run history and replay runs |
| `/autopilot` | Toggle bounded autonomous execution mode |
| `/commands` | Legacy alias: inspect or run slash-trigger AutomationRules |
| `/inbox` | Show pending and actionable tasks |
| `/qa` | Run background QA watch for lint/tests |
| `/skills` | Inspect or run repo and user skills |
| `/task` | Manage durable background tasks, including retry and replay |
| `/unwatch` | Stop watch mode |
| `/watch` | Watch directory for changes |

## Collaboration

| Command | Description |
|---|---|
| `/collab` | Start, join, summarize, and manage collaboration sessions |
| `/leave` | Disconnect from collaboration session |
| `/pass` | Hand driver role to the next collaborator |
| `/suggest` | Send suggestion to the active driver |

## Context & Reuse

| Command | Description |
|---|---|
| `/add` | Pin file/directory for context |
| `/bootstrap` | Detect project type and suggest quickstart commands |
| `/clear-files` | Clear all pinned context files |
| `/context-budget` | Rank context files against a token budget |
| `/drop` | Unpin context file |
| `/files` | List pinned context files |
| `/focus` | Manage persistent coding focus state |
| `/image` | Queue image for next message |
| `/prompts` | List saved prompts |
| `/restore-session` | Restore most recent saved session |
| `/resume` | Resume with branch/checkpoint/session summary |
| `/save-prompt` | Save reusable prompt |
| `/save-session` | Save current session for later restore |
| `/use` | Load and run saved prompt |
| `/workspace-map` | Summarize repository layout and hotspots |

## Core Workflow

| Command | Description |
|---|---|
| `/audit-export` | Export audit log JSONL |
| `/clear` | Clear conversation history |
| `/clear-output` | Clear screen output only |
| `/compact` ⭐ | Manage context (auto/compact/gentle/aggressive/compress/handoff) |
| `/copy` | Copy last assistant response |
| `/cost` ⭐ | Show session token usage and estimated cost |
| `/edit-last` | Edit and resend last prompt |
| `/exit` | Exit the TUI (alias) |
| `/export` | Export conversation history |
| `/help` ⭐ | Show all available commands |
| `/history` ⭐ | Show recent messages |
| `/mcp-health` | Check health of MCP servers |
| `/new-session` ⭐ | Start a fresh session |
| `/ollama-models` | List locally available Ollama models |
| `/onboarding` | Start guided CLI onboarding |
| `/plan` ⭐ | Generate a plan before executing |
| `/queue` | Manage prompt queue (add/list/clear/drop) |
| `/quit` ⭐ | Exit the TUI |
| `/retry` | Retry last request |
| `/runs` | Inspect recent shared run history |
| `/search` ⭐ | Search transcript, tools, and diffs |
| `/sessions` | List recent sessions |
| `/status` ⭐ | Show canonical session status summary |
| `/workflow` | Legacy alias: inspect slash-trigger AutomationRule scaffolds |

## Economy & Output

| Command | Description |
|---|---|
| `/broke` | Set frugal mode (terse responses) |
| `/cache-clear` | Clear semantic response cache |
| `/economy` | Show or switch economy preset (frugal\|balanced\|quality) |
| `/my-treat` | Set rich mode (comprehensive responses) |
| `/savings` | Show economy savings dashboard |

## Git & Workspace

| Command | Description |
|---|---|
| `/commit` | Create commit message from staged diff |

## Providers & Config

| Command | Description |
|---|---|
| `/api-key` | Open the API key editor or use `/api-key status` |
| `/config` | Show active configuration |
| `/env` | API key editor (alias for /setup) |
| `/mcp` | Inspect or control MCP servers and tools |
| `/model-info` | Show model capabilities (alias for /provider) |
| `/profile` | Set execution profile (speed\|safe\|deep-review) |
| `/provider` ⭐ | Show provider info, models, or switch (F2) |
| `/providers` | List providers (alias for /provider switch) |
| `/set` | Set config key to a value |
| `/settings` | List editable config settings |
| `/setup` ⭐ | Open the guided setup summary and recommended first workflow |
| `/switch` | Switch provider/model (alias for /provider switch) |
| `/theme` | Show or set UI theme (dark/light) |
| `/toggle` | Toggle boolean config value |
| `/tools` | List backend tools |
| `/verbose` | Toggle verbose logging |

## Review & Safety

| Command | Description |
|---|---|
| `/checkpoint` ⭐ | Create named checkpoint (optional label) |
| `/checkpoints` ⭐ | Browse and manage checkpoints |
| `/context` ⭐ | Open backend context inspector or `/context explain` |
| `/diff` | Compare two files |
| `/docker-sandbox` | Show Docker sandbox status and resource limits |
| `/explain-diff` | Explain behavior and risk in current diff |
| `/fix-failures` | Analyze latest test/lint failure output |
| `/gc` | Clean up stale checkpoints |
| `/instructions` | Inspect the active instruction stack |
| `/memory` | Show or update repo-local memory |
| `/permission-mode` | Show permission mode |
| `/plan-mode` | Toggle plan-first execution guidance |
| `/policy` | Inspect repo-local hooks and audit status |
| `/restore` | Restore latest checkpoint (alias for /undo) |
| `/review` | Review code or staged diff |
| `/rewind` | Restore checkpoint (alias for /undo) |
| `/sandbox` ⭐ | Show or set sandbox preset |
| `/save` | Quick checkpoint alias |
| `/test` | Generate tests for a file |
| `/timeline` | Open agent timeline and diffs |
| `/trust` | Open the trust center for provider, sandbox, rollback, and policy state |
| `/undo` ⭐ | Undo file changes (restore last or specific checkpoint) |

## Services & Shell

| Command | Description |
|---|---|
| `/deploy` | Detect targets and deploy project to cloud platforms |
| `/doctor` | Open structured diagnostics with remediation guidance |
| `/ls` | List files in directory |
| `/ollama` | Manage Ollama service and models |
| `/preview` | Start or manage web preview server with live reload |
| `/pwd` | Show current working directory |
| `/read` | Read file through backend |
| `/run` | Run shell command via backend |
| `/service` | Manage local background services |

## Workflows

| Command | Description |
|---|---|
| `/changelog` | Update changelog with this week's highlights |
| `/ci-debug` | Debug latest CI failure; find root cause |
| `/ci-failures` | Summarize CI failures and flaky tests; suggest fixes |
| `/dep-drift` | Detect dependency drift and propose alignment |
| `/dep-upgrade` | Scan outdated deps; propose safe upgrades |
| `/perf-audit` | Audit recent changes for performance regressions |
| `/perf-opportunity` | Find top performance improvement opportunities |
| `/pr-summary` | Summarize recent PRs by teammate and theme |
| `/release-check` | Pre-release verification: changelog, migrations, tests |
| `/release-notes` | Draft release notes from merged PRs |
| `/scan-bugs` | Scan recent commits for likely bugs |
| `/skill-suggest` | Suggest next skills to deepen from recent work |
| `/standup` | Summarize yesterday's git activity for standup |
| `/test-coverage` | Find untested paths and add focused tests |
| `/triage` | Triage new issues; suggest owner, priority, labels |
| `/update-docs` | Update project docs with recent changes |
| `/weekly-update` | Synthesize this week's PRs into a weekly update |

## Conventions

- ⭐ = recommended starting point for new users.
- Type `/` in chat to trigger the slash autocomplete picker (PRD 045).
- Custom slash commands defined via AutomationRule (`type: slash`) appear here only after manifest regeneration; see `docs/AUTOMATIONS.md`.

## See also

- [PROVIDERS.md](./PROVIDERS.md) — `/switch`, `/provider`, `/api-key`
- [ECONOMY.md](./ECONOMY.md) — `/broke`, `/my-treat`, `/economy`, `/savings`
- [SANDBOX.md](./SANDBOX.md) — `/sandbox`, `/permission-mode`, `/trust`, `/policy`
- [AUTOMATIONS.md](./AUTOMATIONS.md) — `/automation`, `/workflow`, `/skills`
- [MULTIPLAYER.md](./MULTIPLAYER.md) — `/collab`, `/pass`, `/suggest`, `/leave`
- [AUTO_COMMIT.md](./AUTO_COMMIT.md) — `/commit`
