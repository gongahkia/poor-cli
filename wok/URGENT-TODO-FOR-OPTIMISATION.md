# Urgent To Do For Ideal Optimization

## Mac-Specific Native Bridge

Goal: keep the Rust core, but use native macOS APIs where cross-platform abstractions leave performance or platform fidelity on the table.

1. Add a Core Text glyph path for macOS.
   - Use Core Text for font fallback, glyph ids, metrics, shaping, and emoji/CJK behavior.
   - Keep the existing cosmic-text path for non-macOS platforms.
   - Feed the existing atlas/renderer with native glyph ids and rasterized masks.

2. Add native macOS text input support.
   - Implement an AppKit `NSTextInputClient` bridge for IME, dead keys, marked text, and composition.
   - Keep winit key events for non-text shortcuts and terminal control sequences.

3. Add macOS profiling instrumentation.
   - Add signposts around PTY drain, terminal parse, dirty-row propagation, quad/instance build, GPU upload, render pass, and present.
   - Create repeatable Instruments profiles for CPU Time Profiler and Metal System Trace.

4. Improve native app lifecycle polish.
   - Audit AppKit activation, menu integration, Services support, titlebar behavior, display changes, and full-screen transitions.

## Rewrite Option

Do not start without explicit approval.

Suggested architecture: Swift/AppKit + CAMetalLayer/CAMetalDisplayLink frontend, Rust core retained.

1. Swift/AppKit owns:
   - Window lifecycle
   - Menus and Services
   - Native IME through `NSTextInputClient`
   - `CAMetalLayer`
   - Display timing through `CAMetalDisplayLink`

2. Rust keeps:
   - PTY management
   - Terminal state
   - Blocks, sessions, search, command history
   - Config and scripting

3. Bridge shape:
   - Rust exposes a C ABI or UniFFI-style API.
   - Swift sends input/window events and receives immutable frame snapshots.
   - Renderer consumes compact row/glyph/background instance streams.

4. Approval criteria:
   - Instruments data shows winit/wgpu or text input abstractions are the limiting factor.
   - Rust/wgpu trench has been exhausted.
   - The project is willing to carry a macOS-specific frontend long-term.
