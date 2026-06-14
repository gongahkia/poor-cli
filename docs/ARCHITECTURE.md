# poor-cli v6 architecture

`poor-cli` v6 records orchestration state before optimizing agent quality.

## Runtime

- `RunStore` persists runs, tasks, agents, events, and artifact references in SQLite.
- `CAS` stores durable payloads by SHA-256 under `.poor-cli/v6/cas/`.
- Each run mirrors replay-critical state under `.poor-cli/v6/runs/<run_id>/`, including `cas/<sha256>` payloads.
- `meta.json` stores the latest run metadata; `events.jsonl` stores the append-only event stream.
- Every important transition emits an append-only event.
- Agent inputs, planner prompts/responses, context packets, and agent results are stored as artifacts.
- `poor-cli replay --verify` checks the per-run event mirror and CAS artifact hashes, then emits a stable trace digest.
- `poor-cli --offline` sets `POOR_CLI_OFFLINE=1`; provider adapters, provider cache misses, and non-local delegated agents fail before live network calls.
- Hook entry points use the `poor_cli.hooks` group and receive lifecycle callbacks for turns, model calls, tool calls, and run completion.
- Tool entry points use the `poor_cli.tools` group and merge with built-ins at dispatcher startup.
- Provider entry points use the `poor_cli.providers` group and return provider instances behind the shared `Provider` contract.
- Provider adapters wrap Anthropic, OpenAI Responses, Gemini, and Ollama clients behind the shared replayable provider contract.
- MCP is client-only in v6.0.0: `poor-cli mcp list` and `poor-cli mcp call server:tool` consume configured stdio MCP servers.
- Graph tools use tree-sitter-backed Python and JavaScript indexing, incrementally refresh changed graph files before uncached queries, expose a polling watch handle for long-lived graph users, and are exposed through the replayable `ToolDispatcher`.

## Commands

- `poor-cli agents`: detect local agents.
- `poor-cli plan`: create and persist an LLM-backed structured plan.
- `poor-cli run`: create a plan, require confirmation unless `--yes` or `--dry-run`, then execute tasks.
- `poor-cli inspect`: inspect run internals.
- `poor-cli replay`: reconstruct orchestration state from events.
- `poor-cli mcp`: list or call external stdio MCP server tools.
- Graph tools: `find_symbol`, `definition_of`, `imports_of`, `callers_of`, and `subgraph`.
- `poor-cli plan --graph` and `poor-cli run --graph` bias planner prompts toward symbolic-first graph navigation.

## Boundaries

The alpha intentionally excludes worktree isolation, parallel scheduling, local GPU providers, MCP server hosting, broad multi-language graph indexing beyond Python/JavaScript, kernel-native file watchers, and live graph-mode SWE-bench benchmarking. The TUI, MCP client, benchmark harness, and graph tools are present but intentionally small.
