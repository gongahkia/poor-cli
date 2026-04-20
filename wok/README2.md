# Wok (Current-State Technical Guide)

Wok is a local-first workspace terminal focused on block-oriented command review for build/test/git workflows.

This file reflects the implemented runtime as of the current repository state.

## What Is Implemented

- GPU-rendered PTY terminal (`wgpu` + `alacritty_terminal`)
- Multi-tab, split-pane workspace with floating panes
- Block timeline with collapse/copy/bookmark/find/filter/rerun
- Workspace-global search across panes and block command lines
- Quick Select pattern overlay (viewport and selected-block scopes)
- Owned-primary input mode with completion popup and history search
- Lua scripting surface for keymaps, hooks, actions, exec, themes, triggers, workflows
- Session autosave + named snapshot save/load
- Theme loading, theme file watching, runtime overrides, background image support
- Replay snapshots with timeline markers and replay navigation
- JSON-RPC remote control server (Unix domain socket + Windows TCP loopback)
- Daemon mode with multi-pane runtime, attach/detach/list/kill lifecycle
- Attached-session parity with per-pane snapshot sync and pane lifecycle mapping
- Standardized JSON-RPC error codes (-32601, -32602, -32000)
- Runtime metrics and debug overlay (`debug_overlay` config option)

## Current Scope

| Area | Status |
| --- | --- |
| GPU rendering (wgpu) | Active |
| PTY + shell integration (bash/zsh/fish/powershell/wsl) | Active |
| Block timeline + navigation | Active |
| Multi-tab, split-pane workspace | Active |
| Owned-primary input + history | Active |
| Lua scripting surface | Active |
| Session autosave/restore | Active |
| Replay snapshots | Active |
| Daemon multi-pane runtime (Phase B) | Active |
| Attached-session parity with pane lifecycle (Phase C) | Active |
| JSON-RPC error standardization (Phase D) | Active |
| Windows remote control backend (Phase E) | Active |
| Runtime metrics and debug overlay (Phase F) | Active |
| Extracted modules: workspace_runtime, render_runtime, cli_runtime | Active |

## Run

```bash
cargo run -p wok
```

Useful variants:

```bash
cargo run -p wok -- --shell zsh
cargo run -p wok -- --shell powershell
cargo run -p wok -- --shell wsl:Ubuntu
cargo run -p wok -- --daemon work
cargo run -p wok -- attach work
cargo run -p wok -- list
cargo run -p wok -- rpc wok.get_panes
cargo run -p wok -- rpc wok.run_action --params '["SplitVertical", {"index": 2}]'
```

## Key Runtime Surfaces

### Replay

- Toggle replay: `Mod+Alt+Shift+R`
- Replay navigation: `Left`, `Right`, `Home`, `End`, `[`, `]`, `Escape`

### Quick Select

- Viewport scope: `Mod+Shift+Q`
- Selected block scope: `Mod+Alt+Q`

### Sessions

- Save manual snapshot: `Mod+Shift+S`
- Load manual snapshot: `Mod+Shift+R`

## Daemon Mode

Wok supports a background daemon that owns terminal state independently of the GUI.

### Lifecycle

```bash
wok --daemon <name>       # start a named daemon session
wok attach <name>         # attach a GUI window to a running daemon
wok detach <name>         # detach the current client from a daemon
wok list                  # list running daemon sessions
wok kill <name>           # terminate a daemon session
```

### Multi-Pane Support

The daemon tracks multiple panes per session via IPC. Each `DaemonPane` holds its own `Terminal`, column/row dimensions, and scrollback. The attached client maps local workspace panes to daemon pane ids for synchronized state.

IPC messages for pane lifecycle:

- `CreatePane { direction }` -- create a new pane in the daemon
- `ClosePane { pane_id }` -- close an existing daemon pane
- `GetPanes` -- list all panes in the session

### RPC from CLI

```bash
wok rpc <method> --params '{...}'
```

Connects to the daemon's Unix socket (or TCP port on Windows) and sends a JSON-RPC request.

## Remote Control

Wok exposes a JSON-RPC 2.0 server over a Unix domain socket (Linux/macOS) or TCP loopback (Windows).

The socket path is exported as `WOK_SOCKET` in spawned shell environments. On Windows, a port file is written to a temp-dir path and the port number is available in `WOK_SOCKET`.

### Available Methods

| Method | Description |
| --- | --- |
| `wok.get_panes` | List all panes with ids and dimensions |
| `wok.send_text` | Send text/keystrokes to a pane |
| `wok.run_action` | Execute a named workspace action |
| `wok.get_blocks` | Retrieve block timeline for a pane |
| `wok.get_text` | Read terminal text content |
| `wok.create_pane` | Create a new pane (split) |
| `wok.close_pane` | Close a pane by id |
| `wok.set_theme` | Apply a theme at runtime |
| `wok.notify` | Push a status notification |

### Example

```bash
echo '{"jsonrpc":"2.0","method":"wok.get_panes","id":1}' \
  | socat - UNIX-CONNECT:"$WOK_SOCKET"
```

Built-in client shortcut:

```bash
wok rpc wok.get_panes
wok rpc wok.send_text --params '{"pane_id":1,"text":"ls\n"}'
wok rpc wok.run_action --params '["save_session", {"name":"manual"}]'
```

### Error Code Semantics

| Code | Meaning |
| --- | --- |
| `-32601` | Method not found -- the requested method name is not recognized |
| `-32602` | Invalid params -- required parameters are missing or have wrong types |
| `-32000` | Server/runtime error -- a valid request failed during execution |

## Current Constraints

- Runtime orchestration is partially concentrated in `wok-app/src/main.rs` (large extractions done to `workspace_runtime`, `render_runtime`, `cli_runtime`).
- Attached-session sync follows per-pane transcript updates mapped by daemon pane id.
- Remote control on non-Unix platforms uses TCP loopback rather than named pipes.
- Plugins are action/hook scoped (no custom render pipeline ownership).

## Verification Snapshot

These commands currently pass in this repository:

```bash
cargo test --workspace
cargo clippy --all-targets -- -D warnings
```

## Repo Map

- `wok-app`: runtime orchestration, event loop integration, session/daemon/remote/scripting
  - `workspace_runtime`: workspace effect handlers (tab/split/focus/layout/session actions)
  - `render_runtime`: rendering orchestration helpers (status bar, overlays, replay, quad batching)
  - `cli_runtime`: CLI dispatch and session bootstrap
  - `remote_runtime`: attached-session sync and remote-control request handling
  - `daemon`: daemon session model with multi-pane support (`DaemonSession`, `DaemonPane`)
  - `ipc`: IPC protocol and framing (length-prefixed JSON, `ClientMessage`/`ServerMessage`)
  - `jsonrpc_params`: typed parameter extraction and `RpcError` with standard codes
  - `remote_control`: platform-specific JSON-RPC server (Unix socket / Windows TCP loopback)
- `wok-terminal`: PTY lifecycle, shell bootstrap, semantic parsing, replay snapshots
- `wok-renderer`: GPU context, batching, glyph atlas, inline image support
- `wok-input`: editor buffer, completion/history/workflows
- `wok-ui`: layout/search/selection/theme/status/quick-select/replay overlay helpers
- `wok-blocks`: block state machine, navigation, block search, trigger engine
