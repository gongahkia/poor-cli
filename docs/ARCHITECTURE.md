# poor-cli v6 architecture

`poor-cli` v6 records orchestration state before optimizing agent quality.

## Runtime

- `RunStore` persists runs, tasks, agents, events, and artifact references in SQLite.
- `CAS` stores durable payloads by SHA-256 under `.poor-cli/v6/cas/`.
- Every important transition emits an append-only event.
- Agent inputs, planner prompts/responses, context packets, and agent results are stored as artifacts.

## Commands

- `poor-cli agents`: detect local agents.
- `poor-cli plan`: create and persist an LLM-backed structured plan.
- `poor-cli run`: create a plan, require confirmation unless `--yes` or `--dry-run`, then execute tasks.
- `poor-cli inspect`: inspect run internals.
- `poor-cli replay`: reconstruct orchestration state from events.

## Boundaries

The alpha intentionally excludes worktree isolation, parallel scheduling, TUI, local GPU providers, MCP, and benchmark automation.
