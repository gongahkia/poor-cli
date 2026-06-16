# poor-cli v6 architecture

`poor-cli` v6 records orchestration state before optimizing agent quality.

## Runtime

- `RunStore` persists runs, tasks, agents, events, and artifact references in SQLite.
- `CAS` stores durable payloads by SHA-256 under `.poor-cli/v6/cas/`.
- Each run mirrors replay-critical state under `.poor-cli/v6/runs/<run_id>/`, including `cas/<sha256>` payloads.
- `meta.json` stores the latest run metadata, including record schema version; `events.jsonl` stores the append-only event stream.
- Every important transition emits an append-only event.
- Agent inputs, planner prompts/responses, context packets, and agent results are stored as artifacts.
- Deterministic human-facing artifacts are mirrored under `.poor-cli/v6/runs/<run_id>/artifacts/`.
- Planner artifacts include `PLAN.json` and `PLAN.md`; worker artifacts include `RESULT.md`, `PATCH.diff`, and changed-file metadata.
- Review and verifier artifacts are always typed, even when a run has no active reviewer or verifier lane.
- `poor-cli review-run <run-id>` uses the configured `reviewer` route to run a model-backed review over plan, patch, and result artifacts.
- `poor-cli verify-run <run-id>` executes sandbox-checked validation commands and writes deterministic verifier results.
- The DAG scheduler runs independent tasks up to the configured cap, blocks failed dependents, records scheduler metrics, and honors cancellation.
- `poor-cli run-swarm` creates detached worker worktrees, collects patch artifacts, and writes a collect-only merge plan.
- `poor-cli rpc serve --stdio` exposes JSONL JSON-RPC methods for run, inspect, status, cancel, and replay.
- Provider calls update `budget/LEDGER.json` with token estimates, provider-reported usage/cost where available, warning thresholds, and hard budget-stop events.
- `poor-cli replay --verify` checks the per-run event mirror and CAS artifact hashes under a socket guard, then emits a stable trace digest and JSON verdict.
- `poor-cli --offline` sets `POOR_CLI_OFFLINE=1`; provider adapters, provider cache misses, and non-local delegated agents fail before live network calls.
- Hook entry points use the `poor_cli.hooks` group and receive lifecycle callbacks for turns, model calls, tool calls, and run completion.
- Tool entry points use the `poor_cli.tools` group and merge with built-ins at dispatcher startup.
- Provider entry points use the `poor_cli.providers` group and return provider instances behind the shared `Provider` contract.
- Provider adapters wrap Anthropic, OpenAI Responses, Gemini, Ollama, vLLM, and SGLang clients behind the shared replayable provider contract.
- `CachedReplayProvider.call_many()` batches uncached provider misses when the wrapped provider exposes `call_many()`, while replaying cached requests individually.
- vLLM and SGLang adapters normalize local structured-output and function-tool shims into OpenAI-compatible chat payloads.
- Configured/local providers can use `ProviderBackedAgentRunner`, which sends JSON-schema tool definitions, validates tool arguments, records provider/tool replay artifacts, and appends tool results until final output or budget stop.
- Shell runners remain the compatibility path for Codex, Claude, and generic shell tasks.
- Linux/CUDA setup emits provider-native cache controls for vLLM prefix caching/hash/KV dtype and SGLang radix/KV dtype.
- A provider-backed delegated agent named `local` can route task prompts to Ollama, vLLM, or SGLang through `POOR_CLI_PROVIDER`, `POOR_CLI_MODEL`, and `POOR_CLI_LOCAL_BASE_URL`.
- MCP is client-only in v6.0.0: `poor-cli mcp list` and `poor-cli mcp call server:tool` consume configured stdio MCP servers.
- Graph tools use tree-sitter-backed Python, JavaScript, TypeScript, and TSX indexing, incrementally refresh changed graph files before uncached queries, expose polling and native watch handles for long-lived graph users, and are exposed through the replayable `ToolDispatcher`.

## Commands

- `poor-cli agents`: detect local agents.
- `poor-cli doctor`: print agent and graph dependency diagnostics.
- `poor-cli plan`: create and persist an LLM-backed structured plan.
- `poor-cli run`: create a plan, require confirmation unless `--yes` or `--dry-run`, then execute tasks.
- `poor-cli run-swarm`: execute plan tasks in isolated worktrees and collect patches without applying them.
- `poor-cli inspect`: inspect run internals.
- `poor-cli review-run`: run the configured reviewer route over a completed run's artifacts.
- `poor-cli verify-run`: run sandbox-checked validation commands for a completed run.
- `poor-cli replay`: reconstruct orchestration state from events.
- `poor-cli cleanup-swarm`: remove recorded run-owned worker worktrees.
- `poor-cli rpc serve --stdio`: serve the headless JSONL RPC interface.
- `poor-cli provider`: add, list, inspect, diagnose, and switch config-backed provider profiles.
- `poor-cli route explain`: show the selected role/profile/model route and fallback reason for a task.
- `poor-cli mcp`: list or call external stdio MCP server tools.
- Graph tools: `find_symbol`, `definition_of`, `imports_of`, `callers_of`, and `subgraph`.
- `poor-cli plan --graph` and `poor-cli run --graph` bias planner prompts toward symbolic-first graph navigation and persist graph-context evidence.

## Boundaries

The alpha intentionally excludes MCP server hosting, live Linux/CUDA benchmark rows, and remote RPC transports. The TUI, MCP client, benchmark harness, provider adapters, native provider tool loop, scheduler, swarm, stdio RPC, artifact contracts, and graph tools are present but intentionally small.
