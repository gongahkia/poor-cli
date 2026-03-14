# poor-cli Architecture

## Product Surfaces

poor-cli has three user-facing surfaces that share one execution engine:

- `poor-cli-tui/`
  - The Rust terminal UI.
  - Owns local UX state: chat transcript, slash commands, mutation review overlays, context inspector, pair-presence UI, and plan review UI.
- `poor_cli/_server.py`
  - The Python JSON-RPC server used by the TUI and Neovim client.
  - Bridges long-running streaming requests, permission prompts, plan review prompts, and editor-style RPC methods onto the core engine.
- `nvim-poor-cli/`
  - The Neovim integration layer.
  - Reuses the Python server contract rather than implementing its own agent loop.

The canonical execution path is now:

`TUI/Neovim -> JSON-RPC server -> PoorCLICore -> provider + tools`

## Main Backend Split

### `poor_cli/core.py`

`PoorCLICore` is the shared engine. It owns:

- Provider initialization and switching
- Tool registration and execution
- Context selection and prompt assembly
- Instruction stack assembly
- Repo-local policy hooks
- Audit logging
- Checkpoint creation and restore
- Streaming event emission for chat/tool/progress/cost flows

The core does not know about terminal widgets. It emits structured events and accepts callbacks for:

- Permission review
- Plan review

### `poor_cli/_server.py`

The JSON-RPC server adapts core callbacks and events into transport messages.

It is responsible for:

- Session initialization
- Per-request streaming notifications
- Forwarding permission and plan review prompts to clients
- Maintaining pending approval futures
- Exposing additive RPC methods for config, checkpoints, instructions, policy status, and MCP status

### Operator-facing inspection commands

The TUI should expose backend state that materially changes execution:

- `/instructions` for the effective instruction stack
- `/memory` for repo-local durable memory in `.poor-cli/memory.md`
- `/policy` for repo-local hooks and audit status
- `/mcp` for MCP health and per-server controls

### `poor_cli/tools_async.py`

The tool registry is the mutation boundary. It provides:

- Built-in file, shell, git, formatting, search, and utility tools
- Mutation previews
- Narrowing/scoping for approved patch subsets
- External tool registration for MCP

## Request Lifecycle

### Standard chat flow

1. The TUI sends `poor-cli/chatStreaming`.
2. The server calls `PoorCLICore.send_message_events(...)`.
3. The core builds the request message from:
   - Built-in tool-calling system instruction
   - Repo-root instructions (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`)
   - Path-local instructions for referenced files
   - `.poor-cli/memory.md`
   - Active `.poor-cli/focus.json`
   - Selected file context excerpts
   - Live user request
4. Provider responses stream back as:
   - text chunks
   - tool call starts/results
   - plan review requests
   - permission requests
   - progress updates
   - cost updates
5. The server forwards those as JSON-RPC notifications.
6. The client renders them in the terminal and returns approval decisions when needed.

### Background automation flow

`/watch` and `/qa` do not execute a second agent loop anymore.

They now:

1. Detect a file-system or QA event in the Rust background worker.
2. Enqueue an automation prompt back onto the normal TUI prompt queue.
3. Re-enter the same `chatStreaming` path the foreground chat uses.

That means plan review, permission prompts, checkpoints, hooks, timeline entries, and audit logging stay consistent for background-driven requests as well.

## Mutation, Policy, and Audit Pipeline

All mutating execution is intended to pass through one guarded path in `PoorCLICore`.

### Before execution

For each tool call:

1. Tool targets are inspected.
2. Repo-local `pre_tool_use` hooks run from `.poor-cli/hooks/*.json`.
3. If plan mode is active and the batch qualifies, the user receives a plan review gate before execution.
4. If a tool is mutating, the core requests a mutation preview when possible.
5. The user receives a permission review prompt unless the config auto-approves or auto-denies it.
6. Approved file/chunk scopes are applied to the tool arguments.
7. A checkpoint is created before accepted mutations when checkpointing is enabled.

### During execution

- The tool runs through `ToolRegistryAsync.execute_tool_raw(...)`.
- MCP tools are registered into the same registry, so they use the same review, hook, checkpoint, and audit path as built-in tools.

### After execution

1. The result is normalized into a `ToolOutcome` when applicable.
2. Edited files are marked in the context manager.
3. Repo-local `post_tool_use` hooks run.
4. Structured audit entries are written for:
   - session start
   - permission granted/denied
   - hook allow/deny
   - tool execution
   - checkpoint create/restore

Audit logs are stored repo-locally under:

- `.poor-cli/audit/audit.db`

## Plan Review Loop

Plan mode is meant to be backend-owned, not TUI-prompt-owned.

The intended phase-1 plan loop is:

1. Model proposes a batch of tool calls.
2. Core converts those calls into a plan summary with steps, risks, and affected files.
3. Server emits a plan review request.
4. TUI shows the plan review overlay.
5. User approves or rejects.
6. Only then does execution continue to preview/permission/checkpoint/apply.

The manual `/plan` command can still exist as a user-initiated planning shortcut, but the guarded execution path should rely on the backend plan-review callback, not client-side prompt tricks.

## Multiplayer Model

Multiplayer uses the Python server as the execution authority.

- The host/room layer lives in Python.
- The TUI reflects room membership, roles, queue depth, suggestions, and role updates.
- Pairing and review flows should remain thin UX layers over the same guarded chat/tool execution path.

This keeps collaboration features from bypassing permission, checkpoint, and audit behavior.

## MCP Integration

MCP servers are configured in config and initialized in the core.

- Connected MCP tools are registered into the normal tool registry.
- Status is exposed through server RPC and surfaced in `/doctor`.
- Per-server controls are exposed through the normal config surface and the `/mcp` command, not a separate execution path.

## Design Constraints

- The TUI is the primary surface.
- The Python server is an integration/runtime boundary, not a second competing product shell.
- Any user-visible command or toggle should correspond to a real backend behavior.
- New automation/autonomy features should reuse the same guarded engine rather than inventing parallel execution stacks.
