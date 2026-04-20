# Wok

Wok is a local-first workspace terminal for developers who live in build, test, and git loops and want terminal output organized into navigable command blocks instead of one undifferentiated scrollback wall.

The product is intentionally opinionated: no AI, no login, no cloud dependency. The current v1 target is a trustworthy single-window workspace with pane-local terminals, block timelines, search, sessions, and scriptable actions.

## Current Scope

| Area | Status | Notes |
| --- | --- | --- |
| Core terminal | Shipped | GPU-rendered terminal, PTY-backed shell process, resize propagation, copy/paste, zoom, scrollback-backed buffer |
| Blocks on Bash/Zsh/Fish | Shipped | Automatic shell bootstrap, OSC 133 parsing, separators, exit-status accents, collapse, and block copy |
| PowerShell / WSL | Shipped | Automatic bootstrap wrappers emit block markers, source user profiles deterministically, restore startup cwd, and now have explicit regression coverage |
| Tabs, splits, sessions | Shipped | IDE-style workspace with autosave/restore, manual snapshot save/load, and restored transcript/block continuity |
| Input bar | Shipped | Bottom bar supports both the action palette and an owned-primary command editor behind `command_entry_mode = "owned_primary"` |
| Search | Shipped | Workspace-global query with focused-pane overlay, match counts, next/prev navigation, and cross-pane result jumps |
| Mouse selection | Shipped | Drag selection works; `copy_on_select` is honored |
| Lua scripting | Shipped | Loads `~/.config/wok/init.lua`, supports keybindings, command aliases, structured hooks, `run_action`, `exec`, `notify`, and runtime state accessors |
| Theme loading | Shipped | `theme_path` loads at startup, hot reloads on file changes, and can be changed live through `wok.theme.load(...)` / `wok.theme.set(...)` |
| Remaining limits | Honest gap | Plugins are still action/hook scoped rather than custom renderers, and the main runtime orchestration still lives in one large entrypoint instead of a fully split module tree |

## Run Locally

```bash
cargo run -p wok
```

Useful variants:

```bash
cargo run -p wok -- --shell zsh
cargo run -p wok -- --shell powershell
cargo run -p wok -- --shell wsl:Ubuntu
cargo build --release -p wok
cargo run -p wok -- init
cargo run -p wok -- doctor
cargo run -p wok -- doctor --json
cargo run -p wok -- reset --scope managed --yes
cargo run -p wok -- shell install --shell zsh
cargo run -p wok -- shell rollback --yes
```

Owned-primary input is opt-in for now:

```toml
command_entry_mode = "owned_primary"
```

In that mode, Wok owns prompt-time editing, `Up` / `Down` performs pane-first history recall, and `Ctrl+R` opens pane-first command history search.

Configuration search order:

1. `$WOK_CONFIG`
2. `~/.config/wok/config.toml`
3. `~/.wok.toml`

More detail:

- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- [docs/LUA_SCRIPTING.md](docs/LUA_SCRIPTING.md)
- [docs/CLI.md](docs/CLI.md)
- [docs/REMOTE_RPC.md](docs/REMOTE_RPC.md)
- [docs/RELEASE_HARDENING.md](docs/RELEASE_HARDENING.md)

## Demo Flow

Use `bash`, `zsh`, or `fish` for the cleanest first-run block demo.

1. Launch Wok.
2. Run `echo hello`, `pwd`, and `false`.
3. Split the workspace with `Mod+D` or `Mod+Shift+D`.
4. Use `Mod+Up` / `Mod+Down` to move across blocks in the focused pane.
5. Use `Mod+Shift+E` to collapse the selected block.
6. Use `Mod+Shift+C` to copy the selected block.
7. Use `Mod+F` to search across the workspace and jump between panes.
8. Use `Mod+Shift+S` to save the `manual` session snapshot, then `Mod+Shift+R` to load it.

Named snapshots are available through Lua action aliases such as `save_session:demo` and `load_session:demo`.

## Repo Map

- `wok-app`: executable, event loop, workspace orchestration, sessions, scripting
- `wok-terminal`: PTY lifecycle, shell bootstrap, terminal state, semantic events
- `wok-blocks`: block state machine, navigation, block metadata
- `wok-input`: editor buffer and command history
- `wok-renderer`: wgpu pipeline, glyph atlas, font rasterization
- `wok-ui`: clipboard, search state, split layout, theme loading

## Interview Notes

Start with: Wok is a crate-split Rust terminal that treats PTY correctness as the foundation and block-oriented command review as the product wedge.

Then explain the runtime path:

1. `winit` captures input and drives the frame loop.
2. `WokHandler` owns workspace tabs, split panes, sessions, and Lua side effects.
3. Each pane owns a `WokApp` state bundle plus a `wok-terminal::Terminal`.
4. `wok-terminal` emits semantic events from shell markers and cwd/title changes.
5. `wok-blocks` turns those events into pane-local block records.
6. `wok-renderer` turns terminal cells, block decorations, search highlights, and chrome into one GPU batch.

Use these docs when presenting the project:

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/INTERVIEW.md](docs/INTERVIEW.md)
- [todo.md](todo.md) for the broader roadmap
