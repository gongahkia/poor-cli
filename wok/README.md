# Walk

Walk is a local-first terminal emulator for developers who spend most of their day in build, test, and git loops and want command output organized into visible blocks instead of an undifferentiated scrollback wall.

The project is intentionally opinionated: no AI, no login, no cloud dependency. The current v1 target is a single-window, single-terminal workflow with reliable PTY behavior and block-oriented review, not a full Warp/iTerm replacement yet.

## Current Scope

| Area | Status | Notes |
| --- | --- | --- |
| Core terminal | Shipped | GPU-rendered terminal, PTY-backed shell process, resize propagation, copy/paste, zoom, history-backed input state |
| Blocks on Bash/Zsh/Fish | Shipped | Automatic shell bootstrap, OSC 133 parsing, separators, exit-status accents, block selection, collapse, and block copy |
| PowerShell / WSL | Partial | Terminal works, but block markers are not auto-injected yet |
| Mouse selection | Shipped | Drag selection works; `copy_on_select` is honored |
| Search | Partial | Search state and key routing are wired, but the dedicated search UI/highlight layer is still pending |
| Theme loading | Shipped | `theme_path` is loaded at startup |
| Tabs, splits, sessions | Deferred | Modules and types exist, but the active runtime is still single-terminal |
| Lua scripting | Deferred | Runtime scaffolding exists, but the binary does not load scripting into the live event loop yet |
| Status bar / tab bar / separate input bar | Deferred | Layout modules exist; the current renderer still prioritizes the terminal viewport and block layer |

## Run Locally

```bash
cargo run -p walk
```

Useful variants:

```bash
cargo run -p walk -- --shell bash
cargo run -p walk -- --shell zsh
cargo build --release -p walk
```

Configuration search order:

1. `$WALK_CONFIG`
2. `~/.config/walk/config.toml`
3. `~/.walk.toml`

More detail: [docs/CONFIGURATION.md](docs/CONFIGURATION.md)

## Demo Flow

Use `bash`, `zsh`, or `fish` for the cleanest block demo.

1. Launch Walk.
2. Run `echo hello`, `pwd`, and `false`.
3. Use the platform modifier (`Cmd` on macOS, `Ctrl` elsewhere) plus `Up` / `Down` to move across blocks.
4. Use `Mod+Shift+E` to collapse the selected block.
5. Use `Mod+Shift+C` to copy the selected block.
6. Use `Mod+=`, `Mod+-`, and `Mod+0` to verify zoom.

## Repo Map

- `walk-app`: executable, event loop, runtime wiring, config loading
- `walk-terminal`: PTY lifecycle, shell bootstrap, terminal state, semantic events
- `walk-blocks`: block state machine, navigation, search helpers
- `walk-input`: editor buffer, history, syntax-aware input state
- `walk-renderer`: wgpu pipeline, glyph atlas, font rasterization
- `walk-ui`: clipboard, theme loading, search state, layout scaffolding

## Interview Notes

Start with: Walk is a crate-split Rust terminal that treats terminal correctness as the foundation and blocks as the product wedge.

Then explain the runtime path:

1. `winit` captures input and drives the frame loop.
2. `WalkApp` resolves keybindings and UI state.
3. `walk-terminal` owns PTY spawn, shell bootstrap, resize, and terminal emulation.
4. Semantic events feed `walk-blocks`.
5. `walk-renderer` turns terminal cells plus block decorations into one GPU batch.

Use these docs when presenting the project:

- [ARCHITECTURE.md](ARCHITECTURE.md)
- [docs/INTERVIEW.md](docs/INTERVIEW.md)
- [todo.md](todo.md) for the broader roadmap
