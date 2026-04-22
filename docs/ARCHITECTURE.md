# Architecture

poor-cli is a Python CLI agent harness. The main surfaces are `poor-cli exec` and `poor-cli-server` JSON-RPC.

## Shape

```text
CI job / native client / automation client
  |
  v
poor_cli.cli_app
  |
  v
PoorCLICore
  |-- provider adapters
  |-- tool registry
  |-- permission engine
  |-- checkpoint manager
  |-- memory/session/cost state
  v
filesystem, shell, git, MCP, diagnostics, tasks
```

## Entry Points

- `poor-cli exec`: non-interactive prompt execution for automation and CI.
- `poor-cli-server`: JSON-RPC server used by harness clients and tests.
- `python -m poor_cli`: module entrypoint for local checkout runs.

## Core Runtime

`PoorCLICore` owns provider lifecycle, tool dispatch, permissions, cost tracking, history, checkpoints, and event emission. The CLI surfaces are intentionally thin; business logic stays in Python modules under `poor_cli/`.

## Providers

Provider adapters live under `poor_cli/providers/`. Cloud providers use API keys. Local providers use OpenAI-compatible endpoints or local model runtimes. Provider switching preserves local conversation state and replays context into the next provider.

## Tools

The tool registry exposes structured capabilities for:

- filesystem browse/read/write/glob
- shell execution
- git status/diff/commit helpers
- diagnostics and review
- task execution
- deployment shortcuts
- MCP tool routing
- memory, sessions, checkpoints, and audit state

Tools return structured blocks so `exec`, JSON-RPC, and tests consume the same result shape.

## Safety

`permission_engine.py` evaluates tool rules before execution. Sandbox presets restrict filesystem, network, and process access. Audit logs record allowed and denied sensitive operations.

## State

Repo-local state is under `.poor-cli/` by default:

- config and preferences
- checkpoints
- sessions and history
- memory
- audit logs
- automation runs
- task worktrees

## Adding Surface Area

- New CLI command: add parser wiring in `poor_cli/cli_app.py` and keep it thin.
- New tool: register under `poor_cli/tools/` with schema, handler, tests, and capability metadata.
- New provider: add adapter under `poor_cli/providers/`, catalog metadata, and provider tests.
- New JSON-RPC method: add handler under `poor_cli/server/handlers/` and update registry tests.

## Verification

```sh
python3 -m compileall poor_cli
python3 -m pytest -q
python3 -m poor_cli help
python3 -m poor_cli exec --help
```
