# Wok Architecture

Wok is a Rust workspace implementing a GPU-accelerated workspace terminal. This document describes the current runtime architecture rather than an aspirational one.

## Crate Graph

```
                       wok-app
                    /     |     \
                   /      |      \
             wok-ui   wok-blocks  wok-input
               |  \       |            |
               |   \      |            |
        wok-renderer  wok-terminal --+

        sidecar domain crate: wok-git
```

## Module Map (wok-app)

The `wok-app` binary crate has been decomposed into focused modules:

| Module | Responsibility |
| --- | --- |
| `main.rs` | Entry point, event loop wiring, top-level dispatch |
| `workspace_runtime.rs` | Workspace effect handlers (tab/split/focus/layout/session actions) |
| `render_runtime.rs` | Frame rendering orchestration (status bar, overlays, replay, quad batching) |
| `cli_runtime.rs` | CLI argument dispatch and session bootstrap |
| `remote_runtime.rs` | Attached-session snapshot sync and JSON-RPC request handling |
| `daemon.rs` | `DaemonSession` / `DaemonPane` model, daemon lifecycle loop |
| `ipc.rs` | Length-prefixed JSON framing, `ClientMessage` / `ServerMessage` enums |
| `remote_control.rs` | Platform-specific JSON-RPC server (Unix socket on unix, TCP loopback on Windows) |
| `jsonrpc_params.rs` | Typed parameter extraction helpers, `RpcError` with standard codes |
| `rpc_cli.rs` | `wok rpc` CLI client |
| `input_codec.rs` | Input encoding helpers |
| `app.rs` | Core `WokApp` per-pane state |
| `workspace.rs` | Workspace/tab/split state |
| `session.rs` | Session persistence and restore |
| `config.rs` | TOML config loading |
| `keybindings.rs` | Keybinding resolution |
| `plugin_host.rs` | Lua plugin host |
| `scripting.rs` | Lua scripting surface |
| `event_loop.rs` | winit event loop integration |

## Runtime Model

The live runtime is an IDE-style workspace:

- one window
- many tabs
- one split tree per tab
- one focused pane per tab
- one `wok-terminal::Terminal` plus one `wok-app::WokApp` state bundle per pane

Each pane owns:

- PTY-backed shell process
- terminal emulator state and scrollback
- block timeline
- input draft and command history state
- pane-local search query and match state
- selection state
- zoom state

Workspace-level state owns:

- tab/split structure
- focused pane routing
- autosave/restore session handling
- plugin host, theme overrides, and plugin side effects
- top tab bar and bottom status bar

## Data Flow

1. `winit` delivers keyboard, mouse, resize, and frame events into `wok-app`.
2. `WokHandler` resolves whether an event is workspace-scoped or focused-pane-scoped.
3. Focused-pane `WokApp` state resolves keybindings first, then command-palette/search overlays, then raw PTY fallback.
4. `wok-terminal` writes to the PTY and drains PTY output during frame ticks.
5. The terminal parser updates the emulator state and emits semantic events for:
   - prompt start
   - command start
   - output start
   - command end
   - cwd changes
   - title changes
6. `wok-blocks` converts those semantic events into block records anchored to absolute scrollback rows.
7. `wok-renderer` draws terminal cells, block accents, search highlights, the input bar, the search overlay, and workspace chrome into one batched frame.

## Terminal And Block Model

Wok treats scrollback rows as the stable identity for block bookkeeping.

- `wok-terminal` exposes visible rows and buffer text using absolute row ids.
- semantic events carry absolute row anchors
- block output ranges are stored as absolute rows
- search, copy, and collapse read from logical buffer snapshots rather than viewport-relative rows

That keeps block boundaries stable after scrolling, search jumps, and resize reflow.

## Git Parsing

Git parsing lives in `wok-git` so future VCS panels, block metadata, RPC payloads,
and project/worktree flows can share the same pure parser layer. It currently
handles `git status --porcelain=v1 -z`, `git diff --numstat`, and unified diff
display rows, including rename normalization and long-context collapsing.

## Daemon Session Architecture

Wok supports headless daemon sessions that own terminal state independently of the GUI window.

### DaemonSession / DaemonPane

```
DaemonSession
  name: String
  shell: ShellType
  panes: HashMap<u64, DaemonPane>
  focused_pane: u64
  next_pane_id: u64
  attached_clients: usize

DaemonPane
  terminal: Terminal
  cols: u16
  rows: u16
```

A `DaemonSession` starts with one pane (id 0) and can grow via `CreatePane` IPC messages. Each pane owns its own `Terminal` instance with independent PTY, scrollback, and dimensions.

### IPC Protocol

Client-to-daemon messages (`ClientMessage`):

| Variant | Purpose |
| --- | --- |
| `Attach { session }` | Request attach to a named session |
| `Detach { session }` | Notify detach |
| `SessionState { session }` | Request session metadata |
| `Kill { session }` | Request daemon shutdown |
| `Input { pane_id, data }` | Forward terminal input bytes to a pane |
| `Resize { pane_id, cols, rows }` | Resize a pane |
| `Snapshot` | Request full state snapshot (all panes) |
| `CreatePane { direction }` | Create a new pane |
| `ClosePane { pane_id }` | Close an existing pane |
| `GetPanes` | List all panes |

Daemon-to-client messages (`ServerMessage`):

| Variant | Purpose |
| --- | --- |
| `Ack` | Acknowledge |
| `Error { message }` | Error response |
| `SessionState { session, pane_count, attached_clients, running }` | Session metadata |
| `Snapshot { payload }` | Serialized workspace snapshot (per-pane rows, offsets, dimensions) |
| `PaneCreated { pane_id }` | New pane confirmation |
| `Panes { items }` | List of `PaneInfo { pane_id, cols, rows }` |

Messages are framed as length-prefixed JSON (4-byte big-endian length + JSON payload).

### Attached-Mode Pane Mapping

When a GUI client attaches to a daemon (`wok attach <name>`), local workspace panes are mapped to daemon pane ids. The attached client:

- Periodically fetches per-pane snapshots from the daemon
- Applies transcript updates to each mapped local pane
- Routes workspace mutations (create/close pane) through the daemon rather than executing locally
- Blocks local workspace mutations that would desynchronize state

## Threading Model

- The main thread owns mutable UI, workspace, renderer, and pane state.
- Each terminal owns PTY I/O machinery and feeds output back to the main loop through channels.
- There is no async runtime on the hot path.
- Session restore always respawns fresh shells instead of attempting to serialize live PTY state.

## Sessions

Session persistence lives in `wok-app/src/session.rs`.

What is persisted:

- tabs and split layout
- focused pane per tab
- pane shell choice
- pane cwd
- pane title
- input draft
- search query
- restored plain-text terminal transcript
- restored block timeline and collapsed state
- viewport scroll position
- window size and position

What is intentionally not persisted:

- live PTY process state

Autosave is written to `~/.config/wok/session.json`. Named snapshots live under `~/.config/wok/sessions/`.

## Lua Surface

Lua is loaded from `~/.config/wok/init.lua` and is deliberately scoped to the action bus.

Current capabilities:

- bind keys to built-in actions
- register reusable action aliases
- trigger built-in actions through `wok.run_action(...)`
- run shell commands in the focused pane
- receive structured lifecycle hooks
- inspect app/workspace/pane/session state snapshots
- load themes and apply live theme overrides
- push status notifications

Current non-goals:

- custom rendering
- arbitrary mutation of internal runtime structures
- bypassing the workspace/action pipeline

## Shell Integration

Wok bootstraps shells automatically through temporary wrappers rather than requiring manual dotfile edits.

Supported shells:

- Bash
- Zsh
- Fish
- PowerShell
- WSL via `wsl:<distro>`

The shell layer emits OSC markers and cwd/title updates that feed the block model.

## Current Boundaries

The current runtime is coherent, but a few edges are still intentionally narrow:

- search is workspace-global, but the overlay is still rendered in the focused pane
- plugins do not own custom rendering or arbitrary layout mutation
- runtime orchestration is partially concentrated in `main.rs`, with large sections extracted to `workspace_runtime`, `render_runtime`, and `cli_runtime`
- remote control on non-Unix platforms uses TCP loopback rather than native named pipes

For the product framing and demo script, use [README.md](README.md) and [docs/INTERVIEW.md](docs/INTERVIEW.md).
