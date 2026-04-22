# Legacy Command Manifest

poor-cli keeps **117 legacy command aliases** across 9 categories for client/workflow compatibility.

## Categories

- [Core Workflow](#core-workflow) (23 commands)
- [Review & Safety](#review-safety) (22 commands)
- [Providers & Config](#providers-config) (16 commands)
- [Economy & Output](#economy-output) (5 commands)
- [Context & Reuse](#context-reuse) (15 commands)
- [Automation & Tasks](#automation-tasks) (9 commands)
- [Services & Shell](#services-shell) (9 commands)
- [Git & Workspace](#git-workspace) (1 commands)
- [Workflows](#workflows) (17 commands)

## Core Workflow

| Command | Description |
|---|---|
| `/help` ⭐ | Show all available commands |
| `/onboarding` | Start guided CLI onboarding |
| `/plan` ⭐ | Generate a plan before executing |
| `/history` ⭐ | Show recent messages |
| `/sessions` | List recent sessions |
| `/new-session` ⭐ | Start a fresh session |
| `/queue` | Manage prompt queue (add/list/clear/drop) |
| `/compact` ⭐ | Manage context (auto/compact/gentle/aggressive/compress/handoff) |
| `/search` ⭐ | Search transcript, tools, and diffs |
| `/status` ⭐ | Show canonical session status summary |
| `/runs` | Inspect recent shared run history |
| `/audit-export` | Export audit log JSONL |
| `/workflow` | Legacy alias: inspect slash-trigger AutomationRule scaffolds |
| `/export` | Export conversation history |
| `/retry` | Retry last request |
| `/edit-last` | Edit and resend last prompt |
| `/copy` | Copy last assistant response |
| `/quit` ⭐ | Exit the CLI |
| `/clear` | Clear conversation history |
| `/clear-output` | Clear screen output only |
| `/cost` ⭐ | Show session token usage and estimated cost |
| `/ollama-models` | List locally available Ollama models |
| `/mcp-health` | Check health of MCP servers |

## Review & Safety

| Command | Description |
|---|---|
| `/review` | Review code or staged diff |
| `/test` | Generate tests for a file |
| `/permission-mode` | Show permission mode |
| `/sandbox` ⭐ | Show or set sandbox preset |
| `/instructions` | Inspect the active instruction stack |
| `/memory` | Show or update repo-local memory |
| `/policy` | Inspect repo-local hooks and audit status |
| `/docker-sandbox` | Show Docker sandbox status and resource limits |
| `/context` ⭐ | Open backend context inspector or `/context explain` |
| `/trust` | Open the trust center for provider, sandbox, rollback, and policy state |
| `/timeline` | Open agent timeline and diffs |
| `/explain-diff` | Explain behavior and risk in current diff |
| `/fix-failures` | Analyze latest test/lint failure output |
| `/checkpoints` ⭐ | Browse and manage checkpoints |
| `/checkpoint` ⭐ | Create named checkpoint (optional label) |
| `/save` | Quick checkpoint alias |
| `/rewind` | Restore checkpoint (alias for /undo) |
| `/restore` | Restore latest checkpoint (alias for /undo) |
| `/diff` | Compare two files |
| `/undo` ⭐ | Undo file changes (restore last or specific checkpoint) |
| `/plan-mode` | Toggle plan-first execution guidance |
| `/gc` | Clean up stale checkpoints |

## Providers & Config

| Command | Description |
|---|---|
| `/provider` ⭐ | Show provider info, models, or switch (F2) |
| `/switch` | Switch provider/model (alias for /provider switch) |
| `/providers` | List providers (alias for /provider switch) |
| `/config` | Show active configuration |
| `/model-info` | Show model capabilities (alias for /provider) |
| `/profile` | Set execution profile (speed\|safe\|deep-review) |
| `/settings` | List editable config settings |
| `/setup` ⭐ | Open the guided setup summary and recommended first workflow |
| `/env` | API key editor (alias for /setup) |
| `/api-key` | Open the API key editor or use `/api-key status` |
| `/verbose` | Toggle verbose logging |
| `/toggle` | Toggle boolean config value |
| `/set` | Set config key to a value |
| `/theme` | Show or set UI theme (dark/light) |
| `/tools` | List backend tools |
| `/mcp` | Inspect or control MCP servers and tools |

## Economy & Output

| Command | Description |
|---|---|
| `/broke` | Set frugal mode (terse responses) |
| `/my-treat` | Set rich mode (comprehensive responses) |
| `/economy` | Show or switch economy preset (frugal\|balanced\|quality) |
| `/savings` | Show economy savings dashboard |
| `/cache-clear` | Clear semantic response cache |

## Context & Reuse

| Command | Description |
|---|---|
| `/files` | List pinned context files |
| `/add` | Pin file/directory for context |
| `/drop` | Unpin context file |
| `/clear-files` | Clear all pinned context files |
| `/focus` | Manage persistent coding focus state |
| `/resume` | Resume with branch/checkpoint/session summary |
| `/workspace-map` | Summarize repository layout and hotspots |
| `/bootstrap` | Detect project type and suggest quickstart commands |
| `/context-budget` | Rank context files against a token budget |
| `/image` | Queue image for next message |
| `/save-prompt` | Save reusable prompt |
| `/use` | Load and run saved prompt |
| `/prompts` | List saved prompts |
| `/save-session` | Save current session for later restore |
| `/restore-session` | Restore most recent saved session |

## Automation & Tasks

| Command | Description |
|---|---|
| `/autopilot` | Toggle bounded autonomous execution mode |
| `/qa` | Run background QA watch for lint/tests |
| `/task` | Manage durable background tasks, including retry and replay |
| `/automation` | Inspect AutomationRule run history and replay runs |
| `/inbox` | Show pending and actionable tasks |
| `/skills` | Inspect or run repo and user skills |
| `/commands` | Legacy alias: inspect or run slash-trigger AutomationRules |
| `/watch` | Watch directory for changes |
| `/unwatch` | Stop watch mode |

## Services & Shell

| Command | Description |
|---|---|
| `/doctor` | Open structured diagnostics with remediation guidance |
| `/preview` | Start or manage web preview server with live reload |
| `/deploy` | Detect targets and deploy project to cloud platforms |
| `/service` | Manage local background services |
| `/ollama` | Manage Ollama service and models |
| `/run` | Run shell command via backend |
| `/read` | Read file through backend |
| `/pwd` | Show current working directory |
| `/ls` | List files in directory |

## Git & Workspace

| Command | Description |
|---|---|
| `/commit` | Create commit message from staged diff |

## Workflows

| Command | Description |
|---|---|
| `/standup` | Summarize yesterday's git activity for standup |
| `/weekly-update` | Synthesize this week's PRs into a weekly update |
| `/pr-summary` | Summarize recent PRs by teammate and theme |
| `/release-notes` | Draft release notes from merged PRs |
| `/release-check` | Pre-release verification: changelog, migrations, tests |
| `/changelog` | Update changelog with this week's highlights |
| `/ci-failures` | Summarize CI failures and flaky tests; suggest fixes |
| `/ci-debug` | Debug latest CI failure; find root cause |
| `/triage` | Triage new issues; suggest owner, priority, labels |
| `/scan-bugs` | Scan recent commits for likely bugs |
| `/test-coverage` | Find untested paths and add focused tests |
| `/perf-audit` | Audit recent changes for performance regressions |
| `/dep-drift` | Detect dependency drift and propose alignment |
| `/dep-upgrade` | Scan outdated deps; propose safe upgrades |
| `/update-docs` | Update project docs with recent changes |
| `/skill-suggest` | Suggest next skills to deepen from recent work |
| `/perf-opportunity` | Find top performance improvement opportunities |

## Conventions

- ⭐ = recommended starting point for new users.
- The built-in terminal chat UI has been removed.
- Native/editor clients may still map these aliases onto JSON-RPC actions or AutomationRule workflows.
- Custom aliases defined via AutomationRule (`type: slash`) appear here only after manifest regeneration; see `docs/AUTOMATIONS.md`.

## See also

- [PROVIDERS.md](./PROVIDERS.md) — provider selection and API keys
- [ECONOMY.md](./ECONOMY.md) — `/broke`, `/my-treat`, `/economy`, `/savings`
- [SANDBOX.md](./SANDBOX.md) — `/sandbox`, `/permission-mode`, `/trust`, `/policy`
- [AUTOMATIONS.md](./AUTOMATIONS.md) — `/automation`, `/workflow`, `/skills`
- [AUTO_COMMIT.md](./AUTO_COMMIT.md) — `/commit`
