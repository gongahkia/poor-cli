# poor-cli v6 architecture

`poor-cli` v6 records orchestration state before optimizing agent quality.

## Runtime

- `RunStore` persists runs, tasks, agents, events, and artifact references in SQLite.
- `CAS` stores durable payloads by SHA-256 under `.poor-cli/v6/cas/`.
- Each run mirrors replay-critical state under `.poor-cli/v6/runs/<run_id>/`.
- `meta.json` stores the latest run metadata; `events.jsonl` stores the append-only event stream.
- Every important transition emits an append-only event.
- Agent inputs, planner prompts/responses, context packets, and agent results are stored as artifacts.
- `poor-cli replay --verify` checks the per-run event mirror and CAS artifact hashes, then emits a stable trace digest.
- Hook entry points use the `poor_cli.hooks` group and receive lifecycle callbacks for turns, model calls, tool calls, and run completion.
- Tool entry points use the `poor_cli.tools` group and merge with built-ins at dispatcher startup.
- Provider entry points use the `poor_cli.providers` group and return provider instances behind the shared `Provider` contract.
- Provider adapters wrap Anthropic, OpenAI Responses, Gemini, and Ollama clients behind the shared replayable provider contract.

## Commands

- `poor-cli agents`: detect local agents.
- `poor-cli plan`: create and persist an LLM-backed structured plan.
- `poor-cli run`: create a plan, require confirmation unless `--yes` or `--dry-run`, then execute tasks.
- `poor-cli inspect`: inspect run internals.
- `poor-cli replay`: reconstruct orchestration state from events.

## Boundaries

The alpha intentionally excludes worktree isolation, parallel scheduling, TUI, local GPU providers, MCP, and benchmark automation.
