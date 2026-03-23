# Walk Architecture

Walk is a 6-crate Rust workspace implementing a GPU-accelerated workspace terminal. This document describes the current runtime architecture rather than an aspirational one.

## Crate Graph

```
                       walk-app
                    /     |     \
                   /      |      \
             walk-ui   walk-blocks  walk-input
               |  \       |            |
               |   \      |            |
        walk-renderer  walk-terminal --+
```

## Runtime Model

The live runtime is an IDE-style workspace:

- one window
- many tabs
- one split tree per tab
- one focused pane per tab
- one `walk-terminal::Terminal` plus one `walk-app::WalkApp` state bundle per pane

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

1. `winit` delivers keyboard, mouse, resize, and frame events into `walk-app`.
2. `WalkHandler` resolves whether an event is workspace-scoped or focused-pane-scoped.
3. Focused-pane `WalkApp` state resolves keybindings first, then command-palette/search overlays, then raw PTY fallback.
4. `walk-terminal` writes to the PTY and drains PTY output during frame ticks.
5. The terminal parser updates the emulator state and emits semantic events for:
   - prompt start
   - command start
   - output start
   - command end
   - cwd changes
   - title changes
6. `walk-blocks` converts those semantic events into block records anchored to absolute scrollback rows.
7. `walk-renderer` draws terminal cells, block accents, search highlights, the input bar, the search overlay, and workspace chrome into one batched frame.

## Terminal And Block Model

Walk treats scrollback rows as the stable identity for block bookkeeping.

- `walk-terminal` exposes visible rows and buffer text using absolute row ids.
- semantic events carry absolute row anchors
- block output ranges are stored as absolute rows
- search, copy, and collapse read from logical buffer snapshots rather than viewport-relative rows

That keeps block boundaries stable after scrolling, search jumps, and resize reflow.

## Threading Model

- The main thread owns mutable UI, workspace, renderer, and pane state.
- Each terminal owns PTY I/O machinery and feeds output back to the main loop through channels.
- There is no async runtime on the hot path.
- Session restore always respawns fresh shells instead of attempting to serialize live PTY state.

## Sessions

Session persistence lives in `walk-app/src/session.rs`.

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

Autosave is written to `~/.config/walk/session.json`. Named snapshots live under `~/.config/walk/sessions/`.

## Lua Surface

Lua is loaded from `~/.config/walk/init.lua` and is deliberately scoped to the action bus.

Current capabilities:

- bind keys to built-in actions
- register reusable action aliases
- trigger built-in actions through `walk.run_action(...)`
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

Walk bootstraps shells automatically through temporary wrappers rather than requiring manual dotfile edits.

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
- the renderer still rebuilds the live frame batch rather than consuming the dormant row-damage cache
- runtime orchestration is still concentrated in `walk-app/src/main.rs`

For the product framing and demo script, use [README.md](README.md) and [docs/INTERVIEW.md](docs/INTERVIEW.md).
