# Walk (Current-State Technical Guide)

Walk is a local-first workspace terminal focused on block-oriented command review for build/test/git workflows.

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
- JSON-RPC remote control server (Unix domain socket)
- Daemon mode with attach/detach/list/kill lifecycle commands

## Run

```bash
cargo run -p walk
```

Useful variants:

```bash
cargo run -p walk -- --shell zsh
cargo run -p walk -- --shell powershell
cargo run -p walk -- --shell wsl:Ubuntu
cargo run -p walk -- --daemon work
cargo run -p walk -- attach work
cargo run -p walk -- list
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

### Remote Control

Walk sets `WALK_SOCKET` for spawned shells when the remote server is available.

Example JSON-RPC call:

```bash
echo '{"jsonrpc":"2.0","method":"walk.get_panes","id":1}' \
  | socat - UNIX-CONNECT:"$WALK_SOCKET"
```

Supported methods:

- `walk.get_panes`
- `walk.send_text`
- `walk.run_action`
- `walk.get_blocks`
- `walk.get_text`
- `walk.create_pane`
- `walk.close_pane`
- `walk.set_theme`
- `walk.notify`

## Current Constraints

- Runtime orchestration is still centralized in `walk-app/src/main.rs`.
- Daemon mode currently tracks a single PTY terminal model.
- Attached-session sync currently follows active-pane transcript updates.
- Remote control is Unix-only; non-Unix builds use a placeholder implementation.
- Plugins are action/hook scoped (no custom render pipeline ownership).

## Verification Snapshot

These commands currently pass in this repository:

```bash
cargo test --workspace
cargo clippy --all-targets -- -D warnings
```

## Repo Map

- `walk-app`: runtime orchestration, event loop integration, session/daemon/remote/scripting
- `walk-terminal`: PTY lifecycle, shell bootstrap, semantic parsing, replay snapshots
- `walk-renderer`: GPU context, batching, glyph atlas, inline image support
- `walk-input`: editor buffer, completion/history/workflows
- `walk-ui`: layout/search/selection/theme/status/quick-select/replay overlay helpers
- `walk-blocks`: block state machine, navigation, block search, trigger engine
