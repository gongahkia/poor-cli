# Architecture

poor-cli is a Neovim-first AI coding agent split into a Python server and a Lua plugin, connected by JSON-RPC over stdio. This document gives contributors a mental model of how the pieces fit.

## Topology

```txt
Neovim buffers, chat, panels
            |
            v
Lua plugin: nvim-poor-cli
            |  (keymaps, commands, RPC client)
            v
JSON-RPC over stdio
            |
            v
Python server: poor-cli-server
            |
            +--> provider adapters     (poor_cli/providers/)
            +--> tool execution        (poor_cli/tools_async.py)
            +--> context assembly      (poor_cli/context_assembly.py)
            +--> policy + sandbox      (poor_cli/sandbox.py, permission_rules.py)
            +--> sessions + history    (poor_cli/session_manager.py, history.py)
            +--> cost telemetry        (poor_cli/economy.py, cost.py)
            +--> multiplayer           (poor_cli/multiplayer*.py, server/multiplayer_*.py)
```

Everything the user sees in Neovim is a thin projection of server state. All business logic, I/O, and persistence live on the Python side. The plugin contains no API keys, no tool dispatch, no cost math.

## Layers

### Lua Plugin (`nvim-poor-cli/`)

- `lua/poor-cli/init.lua` — entry point; config + lifecycle.
- `lua/poor-cli/rpc.lua` — stdio JSON-RPC client; one persistent server child per Neovim session.
- `lua/poor-cli/chat.lua` — chat panel, slash commands, file mentions.
- `lua/poor-cli/inline.lua` — ghost-text completion, accept/dismiss/cycle.
- `lua/poor-cli/diff_review.lua` — staged-edit hunk-by-hunk accept/reject/regen.
- `lua/poor-cli/timeline.lua` — live tool-call timeline with cancel/retry/dismiss.
- `lua/poor-cli/panels/*.lua` — scratch-buffer dashboards (cost, savings, policy, watch, etc.).
- `lua/poor-cli/integrations/*.lua` — runtime-detected optional plugins (trouble, gitsigns, snacks, oil, overseer, neogit, dap).
- `lua/poor-cli/turn_pin.lua` — CB2 soft/hard pin toggle + badge render on chat turns (`gp` keymap).
- `lua/poor-cli/pins_list.lua` — CB2 cross-session pin viewer (`:PoorCLIPinsList`).
- `lua/poor-cli/memory_picker.lua` — MH8 memory picker sorted by hits / recency / name.
- `lua/poor-cli/memory_expire.lua` — MH3 end-of-session expiry confirmation dialog.
- `lua/poor-cli/strategies.lua` — runtime UI for swap-able strategies (MH7 reranker, CB3 adaptive scoring).
- `lua/poor-cli/ux.lua` + `lua/poor-cli/ux/*.lua` — opt-in UX features (command palette, streaming indicator, home nav, etc.). Off by default; enable via `setup({ ux = { <feature> = true } })`.
- No hard dependencies beyond Neovim + plenary (test-time only).

### Python Server (`poor_cli/`)

Big picture: a core engine wraps a provider adapter and a tool registry, and emits events consumed by the RPC transport and by the Neovim plugin.

Key modules by role:

| Role | Modules |
|---|---|
| Entry | `__main__.py`, `_server.py`, `server/cli.py`, `server/runtime.py` |
| Core loop | `core.py`, `core_agent_loop.py`, `core_tool_dispatch.py`, `core_turn_lifecycle.py` |
| Context | `context_assembly.py`, `context_providers.py`, `context_engine.py`, `context/`, `context_optimizer.py` |
| Memory | `memory.py`, `memory_semantic.py`, `memory_reranker.py` (MMR + cross-encoder + score-order strategies), `memory_forgetting.py`, `memory_review.py`, `memory_retrieval_mode.py`, `auto_memory.py`, `working_memory.py` |
| Providers | `providers/base.py`, `providers/{gemini,openai,anthropic,openrouter,ollama,hf_local,vllm,llama_server,sglang,hf_tgi,lmstudio,litellm}_provider.py`, `providers/portability.py` |
| Tools | `tools_async.py`, `_tool_registry_builder.py`, `shell_filters/`, `tool_output_filter.py`, `tool_events.py`, `tool_success_tracker.py` (CB3 rolling per-tool success counter) |
| Sandbox + policy | `sandbox.py`, `permission_rules.py`, `permission_engine.py`, `policy_hooks.py`, `trust.py` |
| Economy | `economy.py`, `cost.py`, `token_counter.py`, `thinking_budget.py`, `token_budget_controller.py`, `adaptive_budget.py`, `budget_retuning.py` |
| Sessions | `session_manager.py`, `session_store.py`, `history.py`, `history_pruning.py` (CB2 overlay-aware, CB3 adaptive-scored), `run_history.py`, `checkpoint.py`, `turn_pin_overlay.py` (CB2 per-repo soft/hard pin overlay) |
| Multiplayer | `multiplayer.py`, `multiplayer_invites.py`, `multiplayer_session.py`, `server/multiplayer_{runtime,state}.py` |
| MCP | `mcp/` (stdio + http transports, multi-server, registry) |
| RPC layer | `server/runtime.py`, `server/handlers/`, `server/transport.py`, `server/rate_limit.py`, `server/registry.py` |
| User-facing strategy toggles | `ux_strategies.py` (persists `.poor-cli/strategies.json`; feeds reranker strategy + CB3 adaptive override into consumers) |
| Research (gated) | `research/latent_communication.py`, `research/neural_code_encoder.py`, `research/latent_bridge.py` |

### JSON-RPC Contract

The Lua plugin calls methods by name (e.g. `chat.send`, `diff.list`, `cost.snapshot`). Handlers self-register via decorators in `poor_cli/server/handlers/*.py`. Each handler file maps to a functional area (chat, cost, multiplayer, context, trust, etc.). `server/runtime.py` owns dispatch + transport only; handlers do the work.

Streaming events (tool chunks, cost deltas, timeline updates) flow as server-push notifications via the same channel.

## Core Request Lifecycle

1. **Chat send (Lua)** → RPC `chat.send` (or `poor-cli/startRequest`).
2. **Turn lifecycle** (`core_turn_lifecycle.py`) spins up a new run, captures a checkpoint, increments cost counters.
3. **Context assembly** (`context_assembly.py`) builds the `ContextSnapshot`: files (via PageRank selector), rules (AGENTS.md/POOR.md/CLAUDE.md hierarchy), tool schemas (lazy, task-classified), prior messages (hybrid delta mode above threshold), memory (always-injected criticals + tool-driven recall).
4. **Agent loop** (`core_agent_loop.py`) sends the assembled prompt to the provider adapter with the current tool schema.
5. **Provider adapter** translates poor-cli's normalized request to the provider-native format (OpenAI messages, Anthropic messages + cache_control, Gemini contents, Ollama chat, etc.) and returns a normalized `ProviderResponse`.
6. **Tool dispatch** (`core_tool_dispatch.py`) resolves any `function_calls` via `tools_async.ToolRegistryAsync`. Tools that stage edits land in `edit_staging.py` for user review. Tools that mutate the FS fire checkpoints and policy hooks.
7. **Tool results** feed back into step 4 until the provider returns a final message or the iteration/cost cap trips.
8. **Run finalize** persists transcript, updates cost/savings, commits checkpoints if auto-commit is on.

## Provider Abstraction

`poor_cli/providers/base.py` defines `BaseProvider`, `ProviderCapabilities`, `ProviderResponse`, `FunctionCall`, `UsageMetadata`. Every adapter implements:
- `initialize(tools, system_instruction)`
- `send_message(message, *, structured_output=None)`
- `send_message_stream(message)`
- `clear_history()`, `get_history()`, `set_history(...)`
- `get_capabilities() -> ProviderCapabilities`

Adapters must NOT rely on provider-side stateful sessions — `poor_cli/providers/portability.py::enforce_portability` blocks that by default. See [HARNESS_PORTABILITY.md](./docs/HARNESS_PORTABILITY.md).

Capabilities are typed via `ProviderCapability` enum (PRD 020). Features like streaming, vision, thinking, structured output, and latent communication are opt-in per adapter and discoverable at runtime.

## Tool Registry

`poor_cli/tools_async.py::ToolRegistryAsync` owns the canonical set of ~45 tools. Schemas and function bindings are declared in `poor_cli/_tool_registry_builder.py::build_tool_registry(self)` (extracted to keep `tools_async.py` under its line budget).

Tools declare:
- JSON schema (name, description, parameters).
- Optional `output_filter` (PRD 028 JSONPath/regex/keeplines) applied post-execution.
- Optional streaming function (PRD 025) that emits chunks for long-running output.
- Capabilities (`DEFAULT_TOOL_CAPABILITIES`) for sandbox classification (fs-read, fs-write, net, process, etc.).
- Mutating flag (`DEFAULT_MUTATING_TOOLS`) for checkpointing hooks.

MCP tools layer on top via `poor_cli/mcp/` and register as `<server>:<tool>`.

## Sandbox + Policy

`poor_cli/sandbox.py` defines capability classes and tool metadata. Permission rules live in `poor_cli/permission_rules.py` and are loaded from:
- Built-in defaults
- `.poor-cli/permissions.yaml`
- User-global `~/.poor-cli/permissions.yaml`

`permission_engine.py` evaluates rules per-tool-call. The Trust Center (`:PoorCLITrustCenter`) + Policy Panel (`:PoorCLIPolicy`) render the aggregated rule set.

Linux namespaces sandbox + macOS sandbox-exec are wired via `sandbox.py` for bash/tool execution. Docker sandbox exists behind a feature flag for isolated execution.

## Memory + Rules

Two distinct systems:

**Rules** (`agent_rules.py`) — hierarchical `AGENTS.md` / `POOR.md` / `CLAUDE.md` precedence, closest-dir-wins. Loaded fresh each request; cached by mtime. Supports frontmatter `apply_to` globs for path-scoped rules.

**Memory** (`memory.py` + friends) — cross-session user/project/feedback/reference facts persisted as markdown under `~/.poor-cli/memory/*.md`. MH1 provenance (source_session_id, source_turn_id, source_message_hash, extractor, derivation_depth), MH8 telemetry (hit_count, last_accessed_at), MH2 semantic retrieval (`memory_semantic.py`), MH3 forgetting (`memory_forgetting.py`), MH7 reranker (`memory_reranker.py`), MH5 retrieval-mode split (`memory_retrieval_mode.py`). MH9 portability gate (`providers/portability.py`) prevents provider-side state bindings.

## Sessions + Checkpoints

`session_manager.py` owns the active session (history, pinned context, focus). `session_store.py` persists session snapshots to `~/.poor-cli/sessions/`. `history.py` is the in-session message store.

`checkpoint.py` snapshots file state before any mutation. Users can list/restore checkpoints; restoration reverses the last batch of edits.

`run_history.py` tracks every completed run (turn count, cost, status). Surfaces in `/runs` and `/status`.

## Cost Telemetry + Economy

Every provider response carries token counts. `cost.py` maps tokens → USD using `provider_catalog.json` rates. `economy.py` manages presets (`frugal` / `balanced` / `quality`), budget guardrails, model downshift, and savings tracking.

Savings come from multiple sources: prompt compression (`prompt_compressor.py`), semantic cache hits (`semantic_cache.py`), prefix cache hits (Anthropic), model routing downshifts (`model_router.py`), and per-file diff-of-diff (`context/diff_cache.py`). The Savings Dashboard (`:PoorCLISavings`) aggregates these.

## Multiplayer

Invite-only, owner-authoritative WebRTC DataChannel sessions. `multiplayer.py` hosts the state machine; `multiplayer_invites.py` signs/verifies invites; `server/multiplayer_state.py` owns the collaboration state machine. The Neovim plugin exposes `:PoorCLIChat` Share key, `:PoorCLICollabQuick`, `:PoorCLIRoom`. See [MULTIPLAYER.md](./docs/MULTIPLAYER.md) for protocol.

## Contributing

### Starting Points

- **New tool**: declare schema in `_tool_registry_builder.py`, implement the method on `ToolRegistryAsync`, add capabilities + optional output filter. Ship tests in `tests/test_tools_async.py` or a dedicated file.
- **New provider**: subclass `BaseProvider`, implement the 6 required methods, declare capabilities, add an entry to `provider_catalog.json`. Register in `provider_factory.py`.
- **New RPC method**: add a handler under `server/handlers/` with `@register("method.name")`. No runtime.py edit needed.
- **New Neovim panel**: follow the pattern in `panels/` — scratch buffer + keymaps + RPC calls via `rpc.lua`.

### Testing

- Python: `make test` — pytest over `tests/`. Sub-1000 unit tests; no network or provider access required.
- Lua: `make test-lua` — plenary.busted under a test-only Neovim runtime.

### Common Patterns

- **No provider-side state.** See `HARNESS_PORTABILITY.md`. Every test spin-up can reconstruct from `~/.poor-cli/`.
- **Lazy loading** for optional research modules (`research_loader.py`) and optional provider dependencies (import inside `try/except` at call site, not top-of-file).
- **Feature flags** live in `poor_cli/config.py` dataclasses; read via `Config` instance, never module globals.
- **Tests run offline.** Use fakes for providers and embeddings (see `tests/test_memory_semantic.py::_FakeEmbeddingProvider`).

### Style

- Inline comments only, lowercase by default, Capitalize tech names (`# use Docker`).
- Fail fast on bad input; trust internal code and framework guarantees; validate only at boundaries.
- Minimize whitespace; maximize vertical density.

## Notable Non-Obvious Conventions

- `poor_cli/tool_stream.py` and `poor_cli/mcp_client.py` are compatibility shims — the real code moved into subpackages (`server/tool_stream.py`, `mcp/`). The shims re-export with deprecation warnings; new code should import from the subpackages.
- `poor_cli/latent_communication.py` and `poor_cli/neural_code_encoder.py` are shims that redirect to `poor_cli/research/`. Research modules are feature-flagged off by default.
- `docker_sandbox.py` exists but is off by default (requires Docker). `speculative_decoding.py` is intentionally absent (archived in Phase 9).

## See Also

- [README.md](./README.md) — user-facing overview + install.
- [NORTH_STAR.md](./NORTH_STAR.md) — the single metric we optimize for.
- [POOR.md](./POOR.md) — project-level rules loaded alongside AGENTS.md.
- [docs/MCP.md](./docs/MCP.md) — custom MCP server configuration.
- [docs/HARNESS_PORTABILITY.md](./docs/HARNESS_PORTABILITY.md) — anti-lock-in stance.
- [docs/MULTIPLAYER.md](./docs/MULTIPLAYER.md) — real-time collab protocol.
- [LONGTERM-TODO.md](./LONGTERM-TODO.md) — prioritized remaining work.
