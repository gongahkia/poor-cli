# Walk Interview Pack

## One-Minute Framing

Walk is a local-first terminal emulator written as a Rust workspace. The product wedge is block-oriented command review for build, test, and git loops. The engineering spine is PTY correctness, shell bootstrap, scrollback-safe terminal state, and a GPU renderer.

The current runtime is a real workspace terminal:

- one window containing tabs and split panes
- one PTY-backed terminal per pane
- pane-local blocks, search state, and input drafts
- autosaved sessions plus explicit snapshot save/load
- Lua limited to actions, hooks, command aliases, `exec`, and `notify`

## Architecture Story

### Why the crate split exists

- `walk-app` owns startup, windowing, workspace state, sessions, and scripting.
- `walk-terminal` isolates PTY lifecycle, shell bootstrap, resize, and terminal emulation.
- `walk-blocks` turns semantic shell events into product-level command blocks.
- `walk-renderer` isolates GPU concerns and text rasterization.
- `walk-input` isolates editor/history behavior for the owned input bar.
- `walk-ui` holds clipboard, search, split layout, and theme-oriented state.

That split keeps the systems boundary, the product boundary, and the rendering boundary explainable.

### End-to-end flow

1. `winit` produces normalized `InputEvent`s.
2. `WalkHandler` resolves actions for the focused pane or workspace.
3. Pane-local `WalkApp` state handles keybindings, input editor, block navigation, search, clipboard, and zoom.
4. `walk-terminal` writes to the PTY and drains output on frame ticks.
5. The terminal parser updates the emulator state and emits `SemanticEvent`s from OSC 133 / OSC 7 markers.
6. `walk-blocks` turns those events into pane-local block records anchored to absolute scrollback rows.
7. The renderer reads visible rows, block decorations, search highlights, the input bar, the search overlay, and workspace chrome, then submits one batched frame.

## Deliberate Tradeoffs

### What I optimized for

- Reliable shell process ownership before aesthetic breadth.
- Automatic shell integration so blocks work on first launch.
- Pane-local state isolation so tabs, splits, sessions, and restore are predictable.
- Sessions that restore layout and metadata by respawning shells, not by trying to serialize live PTYs.
- A Lua surface that extends actions and lifecycle hooks without bypassing the core runtime model.

### What I intentionally constrained

- Search is scoped to the focused pane, not the full workspace.
- Lua is not a plugin API with custom renderers or arbitrary runtime mutation.
- `walk.on(...)` hooks are lifecycle notifications; today they carry `nil` payloads rather than rich structured event objects.
- PowerShell and WSL are supported, but Bash/Zsh/Fish remain the most battle-tested shells for the block workflow.

## Questions You Should Expect

### Why not build on top of Alacritty directly?

Because the project goal is not only terminal emulation. Walk needs a product layer for blocks, pane-local input/search, sessions, and scripting, so it uses `alacritty_terminal` as infrastructure while keeping higher-level UX and product logic separate.

### Why shell bootstrap instead of asking users to edit dotfiles?

Because the product wedge fails if blocks are a setup chore. Walk prepares temporary shell wrappers for Bash, Zsh, Fish, PowerShell, and WSL shells so semantic markers are injected automatically.

### Why are blocks anchored to absolute rows instead of visible viewport rows?

Because viewport-relative bookkeeping breaks after scrollback growth, search jumps, and resize reflow. Absolute row ids let copy, collapse, and search survive scrolling and resizing.

### Why does session restore respawn shells instead of reviving them?

Because reviving live PTY state is brittle and platform-specific. Restoring layout, cwd, shell choice, search query, and input draft is a clean boundary that keeps sessions reliable and explainable.

### What is the weakest part of the current implementation?

The weakest part is runtime hardening rather than missing architecture. The code now covers tabs, splits, search, sessions, Lua, and multiple shells, but the next engineering step is heavier end-to-end smoke coverage and broader shell/runtime soak testing, especially for PowerShell and WSL.

### How would you scale this next?

1. Add more integration smoke tests for shell markers, session restore, and block/search flows.
2. Decide whether to deepen the block workflow further with summaries, filters, and export.
3. Or expand daily-driver breadth with richer command palette and broader platform polish.

## Demo Checklist

1. Launch `cargo run -p walk -- --shell zsh`.
2. Run `echo hello`, `pwd`, and `false`.
3. Show block separators and exit-status accents.
4. Split the workspace and run another command in the second pane.
5. Navigate blocks with `Mod+Up` / `Mod+Down`.
6. Collapse a block with `Mod+Shift+E`.
7. Search the focused pane with `Mod+F`.
8. Save the `manual` snapshot with `Mod+Shift+S`.
9. Restart with `restore_session = true` or reload the snapshot with `Mod+Shift+R`.
10. Resize the window to show block anchors and PTY size stay coherent.

## Honest Current-State Summary

If asked whether this is production-ready, the strongest accurate answer is:

Walk is a credible local-first v1 workspace terminal with a differentiated block workflow. The architecture and runtime are coherent enough to defend in an interview. The remaining gap is not conceptual clarity; it is broader runtime hardening, especially end-to-end coverage and shell/platform soak time.
