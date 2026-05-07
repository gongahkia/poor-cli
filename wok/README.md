# Wok

Wok is a local-first workspace terminal for developers who live in build, test, and git loops and want terminal output organized into navigable command blocks instead of one undifferentiated scrollback wall.

The product is intentionally opinionated: no AI, no login, no cloud dependency. The current v2 frontend is a trustworthy single-window workspace with pane-local terminals, block timelines, docked search/palette surfaces, sessions, and scriptable actions.

## Current Scope

| Area | Status | Notes |
| --- | --- | --- |
| Core terminal | Shipped | GPU-rendered terminal, PTY-backed shell process, resize propagation, copy/paste, zoom, scrollback-backed buffer |
| Blocks on Bash/Zsh/Fish | Shipped | Automatic shell bootstrap, OSC 133 parsing, separators, exit-status accents, collapse, and block copy |
| PowerShell / WSL | Shipped | Automatic bootstrap wrappers emit block markers, source user profiles deterministically, restore startup cwd, and now have explicit regression coverage |
| Tabs, splits, sessions | Shipped | Pane-first workspace with compact tabstrip, pane headers, autosave/restore, manual snapshot save/load, and restored transcript/block continuity |
| Input bar | Shipped | Owned-primary command editor is the v2 default, with palette/history/search/scratch/media sharing one bottom dock |
| Search | Shipped | Workspace-global query renders in the bottom dock with regex/scope controls, saved queries, result-list navigation, match counts, and cross-pane result jumps |
| Mouse selection | Shipped | Drag selection works; `copy_on_select` is honored |
| Lua scripting | Shipped | Loads `~/.config/wok/init.lua`, supports keybindings, command aliases, structured hooks, `run_action`, `exec`, `notify`, and runtime state accessors |
| Theme loading | Shipped | Wok Clean Dark is the default; `wok init` seeds editable themes, `theme_path` loads at startup, and themes can be changed live through `wok.theme.load(...)` / `wok.theme.set(...)` |
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

Owned-primary input is the v2 default. To use the old shell-native editing path:

```toml
ui_layout = "v1"
# or keep v2 chrome and set:
command_entry_mode = "shell_native"
```

In owned-primary mode, Wok owns prompt-time editing, `Up` / `Down` or `Ctrl+P` / `Ctrl+N` performs pane-first history recall, `Ctrl+A/E/B/F/K/W` uses Emacs-style editing, and `Ctrl+R` opens pane-first command history search. Vi output navigation is available out of the box with `Mod+Shift+V`.

Configuration search order:

1. `$WOK_CONFIG`
2. `~/.config/wok/config.toml`
3. `~/.wok.toml`

More detail:

- [docs/CONFIGURATION.md](docs/CONFIGURATION.md)
- [docs/LUA_SCRIPTING.md](docs/LUA_SCRIPTING.md)
- [docs/CLI_CODING_AGENTS.md](docs/CLI_CODING_AGENTS.md)
- [docs/CLI.md](docs/CLI.md)
- [docs/REMOTE_RPC.md](docs/REMOTE_RPC.md)
- [docs/RELEASE_HARDENING.md](docs/RELEASE_HARDENING.md)
- [docs/PERFORMANCE_BENCHMARKS.md](docs/PERFORMANCE_BENCHMARKS.md)
- [docs/PLUGIN_BRIDGE.md](docs/PLUGIN_BRIDGE.md)

## Demo Flow

Use `bash`, `zsh`, or `fish` for the cleanest first-run block demo.

1. Launch Wok.
2. Run `echo hello`, `pwd`, and `false`.
3. Split the workspace with `Mod+D` or `Mod+Shift+D`.
4. Use `Mod+Up` / `Mod+Down` to move across blocks in the focused pane.
5. Use `Mod+Shift+E` to collapse the selected block.
6. Use `Mod+Shift+C` to copy the selected block.
7. Use `Mod+F` to search across the workspace and jump between panes.
8. Use `Mod+Alt+S` to toggle typewriter-style output reveal.
9. Use `Mod+P` and run `Cycle Visual Effect` to preview the default-off visual effects.
10. Use `Mod+P` and type commands such as `search renderer`, `save demo`, `load demo`, `scratch notes`, `preview ./image.png`, `open ./README.md`, `tail ./server.log`, or `cd ../repo`.
11. Use `Mod+P` and choose a `Preview ...` file entry for images, GIFs, or MP4s in the current directory; `Mod+Alt+Space` pauses GIF/MP4 previews, `Mod+Alt+=/-` changes MP4 speed, `Mod+Alt+M` mutes, and `Escape` or `Close Media Preview` closes them.
12. Put the cursor on a path and use `Mod+Alt+P/O/C/V` for preview/open/copy/reveal. Quoted paths, escaped spaces, and `file:line:col` compiler output are recognized; unsupported previews fall back to Quick Look/open.
13. Use `Mod+Alt+/` for regex search, `Mod+Alt+Shift+F` to cycle search scope, and `Open Search Results` or `Saved Searches` from the palette.
14. Use `Open Block Inspector`, `Block Rerun History`, or `Block Rerun Comparison` on a selected command block.
15. Use `Mod+Alt+X` for the default scratch buffer, `Open Scratch Palette` for named scratches, `Mod+Alt+Shift+X` to insert the selection into command input, or `Send Scratch Selection To Pane` to run/send it directly.
16. Use `Mod+P` and run `Reset Settings` to restore the managed default config.
17. Use `Mod+Shift+S` to save the `manual` session snapshot, then `Mod+Shift+R` to load it.

Named snapshots are available through Lua action aliases such as `save_session:demo` and `load_session:demo`.
From a shell attached to a running Wok instance, `wok workspace save backend`, `wok workspace load backend`, and `wok workspace list` provide the same named-workspace flow.
The command palette also exposes a workspace browser for saved snapshots.

## Repo Map

- `wok-app`: executable, event loop, workspace orchestration, sessions, scripting
- `wok-terminal`: PTY lifecycle, shell bootstrap, terminal state, semantic events
- `wok-blocks`: block state machine, navigation, block metadata
- `wok-input`: editor buffer and command history
- `wok-renderer`: wgpu pipeline, glyph atlas, font rasterization
- `wok-git`: git status, numstat, and unified-diff parsing
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
