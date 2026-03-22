# Walk Interview Pack

## One-Minute Framing

Walk is a local-first terminal emulator written as a Rust workspace. The product wedge is block-oriented command review for developer loops like build, test, and git, while the engineering spine is PTY correctness, shell integration, and GPU rendering.

The current version is intentionally narrow:

- one active terminal runtime
- Bash, Zsh, and Fish as the best-supported shells for block semantics
- tabs, splits, Lua, and session restore kept as deferred breadth instead of pretending they are production-ready today

## Architecture Story

### Why the crate split exists

- `walk-app` owns process startup, windowing, config, and runtime orchestration.
- `walk-terminal` isolates PTY lifecycle and terminal emulation, which is the most failure-prone systems boundary.
- `walk-blocks` keeps command-structure logic separate from terminal bytes and rendering.
- `walk-renderer` isolates GPU concerns and text rasterization.
- `walk-input` isolates editor/history behavior.
- `walk-ui` holds clipboard, search, theme, and layout-oriented state.

That split lets you discuss the project in layers instead of as one large binary.

### End-to-end flow

1. `winit` produces normalized `InputEvent`s.
2. `WalkApp` resolves keybindings first, then editor/search state, then raw PTY fallback.
3. `walk-terminal` writes to the PTY and drains PTY output on frame ticks.
4. The terminal parser updates the emulator grid and emits `SemanticEvent`s from OSC 133 / OSC 7 markers.
5. `walk-blocks` turns those events into block records.
6. The renderer reads terminal cells plus block metadata and emits one batched frame.

## Deliberate Tradeoffs

### What I optimized for

- Correct shell process ownership before feature breadth.
- Local shell integration instead of cloud features.
- Explicit crate boundaries so the project is explainable in an interview.
- Keeping the active runtime truthful: single-terminal first instead of half-wired tabs and splits.

### What I intentionally deferred

- Multi-tab and split-pane orchestration.
- Session restore as an active startup feature.
- Lua as a live runtime extension point.
- A full search overlay and richer chrome such as status bars and tab bars.

## Questions You Should Expect

### Why not build on top of Alacritty directly?

Because the goal was not only terminal emulation. The project needs a product layer for block semantics, input workflow, and customization, so it uses `alacritty_terminal` as infrastructure while keeping the higher-level UX in separate crates.

### Why the shell integration bootstrap instead of manual user setup?

Because blocks only matter if they work on first launch. The runtime now prepares temporary bootstrap wrappers for Bash, Zsh, and Fish so OSC markers are injected without asking the user to hand-edit shell files.

### What is the weakest part of the current implementation?

The product surface is ahead of the runtime surface in a few places. Search state exists before the full visual search UI; Lua/session/tabs exist as modules before they are runtime commitments. The repo is clearer now about that boundary, but it is still the main area to deepen next.

### How would you scale this next?

First finish the user-visible block/search experience and tighten smoke coverage. After that, choose one expansion path: either daily-driver breadth through tabs/splits/sessions, or deeper block workflows such as richer command summaries, block filtering, and export/share flows.

## Demo Checklist

Use this when presenting the project live.

1. Launch `cargo run -p walk -- --shell zsh`.
2. Run `echo hello`, `pwd`, and `false`.
3. Show that blocks are separated and accented by exit status.
4. Navigate blocks with `Mod+Up` / `Mod+Down`.
5. Collapse a block with `Mod+Shift+E`.
6. Copy a block with `Mod+Shift+C`.
7. Resize the window to show PTY resize propagation still works.

## Honest Current-State Summary

If asked "is this production-ready?", the strongest accurate answer is:

Walk is a credible v1 technical foundation with a visible block workflow, but it is not yet a full terminal replacement. The engineering story is strongest around PTY lifecycle, shell bootstrap, crate decomposition, and renderer/runtime integration; the next work is product polish and breadth.
