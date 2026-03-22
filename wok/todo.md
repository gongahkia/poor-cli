# Walk — A Warp-Inspired Terminal Emulator

> GPU-accelerated, cross-platform terminal with Blocks, modern input editing, and deep customization. No AI, no login, no cloud. Just a fast terminal. Built on Rust ecosystem crates (wgpu, alacritty_terminal, portable-pty, cosmic-text) for infrastructure, focusing original code on the novel Warp-like features.

**Language:** Rust (2021 edition, MSRV 1.75+)
**Rendering:** wgpu (cross-platform: Metal on macOS, Vulkan on Linux, DX12 on Windows)
**Terminal emulation:** alacritty_terminal
**PTY management:** portable-pty
**Font loading/shaping:** cosmic-text + rustybuzz
**Shells:** Bash, Zsh, Fish, PowerShell, WSL passthrough
**Platforms:** macOS (ARM64 + x86_64), Linux (X11 + Wayland), Windows 10/11 (native + WSL)

**Workspace crates:**
- `walk-app`: entry point, event loop, window management (winit + wgpu)
- `walk-renderer`: glyph atlas, text rendering pipeline, damage tracking (wgpu)
- `walk-terminal`: thin wrapper around alacritty_terminal + portable-pty
- `walk-blocks`: block detection, shell integration, git info
- `walk-input`: gap buffer editor, syntax highlighting, command history
- `walk-ui`: tabs, splits, search, status bar, theming

---

## Phase 1: Core Platform & Windowing (+platform)

### Task 1 (A) +platform
**blockedBy:** none

**PURPOSE** — Establishes the application entry point and cross-platform event loop; every other module depends on having a window and an event stream.

**WHAT TO DO**
1. Create the project scaffold: `cargo init walk`, set up a Cargo workspace in `/Cargo.toml` with member crates `walk-app`, `walk-renderer`, `walk-terminal`, `walk-blocks`, `walk-input`, `walk-ui`.
2. In `walk-app/src/lib.rs`, integrate `winit 0.30+` as the windowing backend. Create a `WalkWindow` struct wrapping `winit::window::Window` with fields: `title: String`, `size: PhysicalSize<u32>`, `scale_factor: f64`, `is_focused: bool`.
3. Implement `WalkWindow::new(config: &WindowConfig) -> Result<Self, PlatformError>` that creates a resizable, titled window with a minimum size of 400x300 pixels. — WHY 400x300: smallest usable terminal size that fits ~40 cols x ~15 rows at default font, preventing layout breakage.
4. In `walk-app/src/event_loop.rs`, create `fn run_event_loop(window: WalkWindow, mut app: impl AppHandler)` that starts the `winit` event loop and dispatches `AppHandler` trait methods: `on_redraw()`, `on_resize(new_size)`, `on_key_event(KeyEvent)`, `on_mouse_event(MouseEvent)`, `on_focus_change(bool)`, `on_close_requested()`.
5. Define the `AppHandler` trait in `walk-app/src/handler.rs` with all six methods above, each with default no-op implementations.

**DONE WHEN**
- [ ] `cargo build --workspace` succeeds with zero errors on macOS, Linux, and Windows.
- [ ] Running the binary opens a native window with the title "Walk" that responds to resize, focus, and close events (verified by logging each event to stdout).

---

### Task 2 (A) +platform
**blockedBy:** [1]

**PURPOSE** — Provides a high-resolution timer and frame-pacing mechanism so the renderer can target 60fps (or display refresh rate) without spinning the CPU.

**WHAT TO DO**
1. In `walk-app/src/frame_clock.rs`, create `FrameClock` struct with fields: `target_fps: u32`, `last_frame: Instant`, `frame_count: u64`, `accumulated_time: Duration`.
2. Implement `FrameClock::new(target_fps: u32) -> Self` defaulting to 60fps. — WHY 60fps default: matches most monitor refresh rates; higher targets (120/144) waste GPU on terminals where content changes infrequently.
3. Implement `FrameClock::should_render(&mut self) -> bool` that returns `true` if elapsed time since `last_frame` exceeds `1.0 / target_fps` seconds (16ms at 60fps — WHY 16ms: 1000ms / 60fps = 16.67ms, the standard vsync interval for 60Hz displays), and updates `last_frame` accordingly.
4. Implement `FrameClock::fps(&self) -> f64` that returns a rolling average FPS over the last 60 frames. — WHY 60-frame window: smooths out per-frame jitter while remaining responsive to sustained performance changes (covers exactly 1 second at target fps).
5. Integrate `FrameClock` into the event loop from Task 1: only call `on_redraw()` when `should_render()` returns true, and request a new frame via `window.request_redraw()`.

**DONE WHEN**
- [ ] With an empty `on_redraw()`, CPU usage stays below 5% at idle (no spinning). — WHY 5% threshold: above this users notice battery drain / fan noise; idle terminals should be near-zero CPU.
- [ ] `FrameClock::fps()` reports a value within +/-2 of the target FPS when the window is focused.

---

### Task 3 (B) +platform
**blockedBy:** [1]

**PURPOSE** — Input event normalization: converts raw `winit` key events into a Walk-internal `KeyAction` enum so downstream modules (input editor, keybindings) work with a stable, platform-agnostic type.

**WHAT TO DO**
1. In `walk-app/src/input.rs`, define `KeyAction` enum with variants: `Char(char)`, `Enter`, `Tab`, `Backspace`, `Delete`, `Escape`, `ArrowUp`, `ArrowDown`, `ArrowLeft`, `ArrowRight`, `Home`, `End`, `PageUp`, `PageDown`, `FunctionKey(u8)`, `Copy`, `Paste`, `Cut`, `SelectAll`, `Undo`, `Redo`.
2. Define `Modifiers` struct with fields: `ctrl: bool`, `alt: bool`, `shift: bool`, `meta: bool` (meta = Cmd on macOS, Win on Windows).
3. Define `InputEvent` struct: `{ action: KeyAction, modifiers: Modifiers, is_repeat: bool }`.
4. Implement `fn translate_key_event(event: &winit::event::KeyEvent, modifiers: &winit::event::Modifiers) -> Option<InputEvent>` that maps winit's `KeyCode` and `ModifiersState` to `InputEvent`. Handle platform differences: Cmd+C on macOS and Ctrl+C on Linux/Windows both map to `KeyAction::Copy`.
5. Wire `translate_key_event` into the event loop from Task 1 so `AppHandler::on_key_event` receives `InputEvent` instead of raw winit events.

**DONE WHEN**
- [ ] Pressing Cmd+C on macOS, Ctrl+C on Linux, and Ctrl+C on Windows all produce `InputEvent { action: KeyAction::Copy, modifiers: Modifiers { ctrl: true, .. }, .. }` (with `meta: true` on macOS).
- [ ] Arrow keys, function keys F1-F12, and modifier-only presses are correctly translated or filtered.

---

### Task 4 (B) +platform
**blockedBy:** [1]

**PURPOSE** — DPI/scale-factor awareness so text and UI elements render crisply on HiDPI/Retina displays without manual scaling.

**WHAT TO DO**
1. In `walk-app/src/dpi.rs`, create `ScaleContext` struct: `{ scale_factor: f64, physical_size: PhysicalSize<u32>, logical_size: LogicalSize<f64> }`.
2. Implement `ScaleContext::from_window(window: &WalkWindow) -> Self`.
3. Implement `ScaleContext::logical_to_physical(&self, x: f64, y: f64) -> (u32, u32)` and `physical_to_logical(&self, x: u32, y: u32) -> (f64, f64)`.
4. Hook into `winit`'s `ScaleFactorChanged` event in the event loop. When it fires, update `ScaleContext` and invoke a new `AppHandler::on_scale_factor_changed(new_ctx: ScaleContext)` method.
5. All downstream rendering and layout code must use `ScaleContext` for coordinate conversion — enforce this by making `ScaleContext` a required parameter in the renderer's `begin_frame()`.

**DONE WHEN**
- [ ] Moving the window between a 1x and 2x display triggers `on_scale_factor_changed` with the correct new scale factor.
- [ ] Text rendered at 14pt logical size appears identical in physical sharpness on both 1x and 2x displays.

---

### Task 5 (B) +platform
**blockedBy:** [1, 4]

**PURPOSE** — Platform-specific window chrome: makes the window feel native on each platform.

**WHAT TO DO**
1. On macOS: use `winit::platform::macos::WindowAttributesExtMacOS` for titlebar transparency and full-size content view.
2. On Linux (Wayland): use standard CSD (client-side decorations) from winit.
3. On Windows: standard title bar (or optional borderless with custom title bar).
4. Apply theme colors to window decorations where possible.

**DONE WHEN**
- [ ] Window looks native on each platform with correct title bar behavior.
- [ ] Titlebar transparency works on macOS with full-size content view.
- [ ] Window chrome respects theme colors where the platform allows.

---

## Phase 2: GPU Rendering Pipeline (+renderer)

### Task 6 (A) +renderer
**blockedBy:** [1, 4]

**PURPOSE** — Sets up the GPU rendering context using wgpu's cross-platform abstraction.

**WHAT TO DO**
1. In `walk-renderer/src/gpu.rs`, create `GpuContext` struct holding `wgpu::Device`, `wgpu::Queue`, `wgpu::Surface`.
2. Request adapter with `PowerPreference::HighPerformance`. — WHY HighPerformance: terminal rendering needs the discrete GPU on laptops for smooth text scrolling; integrated GPU can cause frame drops during rapid output.
3. Create device with features needed for text rendering (push constants if available, otherwise uniform buffers).
4. Create surface from winit window handle.
5. Configure surface with `PresentMode::Fifo` (vsync) and window size. — WHY Fifo: provides vsync which prevents tearing; Mailbox would waste GPU cycles rendering frames that are never displayed.
6. Implement `resize(width, height)` that reconfigures the surface.
7. Implement `begin_frame() -> wgpu::SurfaceTexture` and `present(frame)`.

**DONE WHEN**
- [ ] A blank colored window renders via wgpu on macOS, Linux, and Windows.
- [ ] Resize reconfigures the surface without crash or flicker.
- [ ] Vsync is active (frame rate matches display refresh rate).

---

### Task 7 (A) +renderer
**blockedBy:** [6]

**PURPOSE** — Handles font loading, shaping, and fallback using cosmic-text instead of raw FreeType/HarfBuzz.

**WHAT TO DO**
1. Add `cosmic-text` as a dependency in `walk-renderer/Cargo.toml`.
2. Create `FontSystem` that initializes `cosmic_text::FontSystem::new()` (loads system fonts).
3. Create `TextShaper` that uses a `cosmic_text::Buffer` to shape text runs.
4. Configure font family, size, weight, and style from user config.
5. Implement font fallback chain: user-specified -> system monospace -> built-in fallback.
6. Support bold, italic, and bold-italic variants.
7. Measure cell dimensions (width, height) from the configured font for grid layout.

**DONE WHEN**
- [ ] Text renders with correct font, including CJK characters and emoji via fallback.
- [ ] Bold, italic, and bold-italic variants render correctly.
- [ ] Cell dimensions (width, height) are accurate for grid layout with the configured monospace font.

---

### Task 8 (A) +renderer
**blockedBy:** [6, 7]

**PURPOSE** — Caches rasterized glyphs in a GPU texture atlas for fast rendering.

**WHAT TO DO**
1. In `walk-renderer/src/atlas.rs`, create `GlyphAtlas` struct with a `wgpu::Texture` (e.g., 2048x2048 RGBA). — WHY 2048x2048: fits ~4000 ASCII glyphs at 16px, covers most terminal use cases without resize; 1024x1024 would overflow with CJK/emoji fallback fonts, 4096x4096 wastes VRAM on GPUs with small texture budgets.
2. Use cosmic-text's `SwashCache` to rasterize glyphs on CPU.
3. Implement `get_or_insert(glyph_key) -> AtlasRegion` that checks cache, rasterizes if missing, uploads to GPU texture.
4. Use a simple shelf-packing algorithm for atlas allocation. — WHY shelf-packing: O(1) allocation per glyph, simple to implement, ~85% space utilization for uniform-sized terminal glyphs; more complex algorithms (skyline, maxrects) add complexity with minimal gain for monospaced text.
5. When atlas is full, create a new atlas texture (keep old one alive until current frame completes).
6. Cache key: (font_id, glyph_id, font_size, subpixel_offset).

**DONE WHEN**
- [ ] Glyphs are cached in GPU texture and reused across frames.
- [ ] Atlas growth works when initial texture fills up.
- [ ] No two glyph entries overlap in UV space (verified by a unit test that checks all rects for non-intersection).
- [ ] Inserting the same glyph twice returns the same atlas region without re-uploading.

---

### Task 9 (A) +renderer
**blockedBy:** [6, 7, 8]

**PURPOSE** — The core rendering loop that reads terminal grid state and draws it to the screen.

**WHAT TO DO**
1. In `walk-renderer/src/pipeline.rs`, create the wgpu render pipeline with vertex and fragment shaders.
2. Vertex format: position (x, y), texture coords (u, v), foreground color (rgba), background color (rgba).
3. For each visible cell in the terminal grid:
   a. Look up glyph in atlas (get texture coords).
   b. Calculate screen position from (column, row) x cell dimensions.
   c. Emit background quad (for cell background color).
   d. Emit glyph quad (textured with atlas region).
4. Batch all quads into a single vertex buffer, draw in one call. — WHY single draw call: minimizes GPU driver overhead; terminal grids are uniform enough that instancing or multi-draw adds complexity without benefit.
5. Handle cell attributes: bold (use bold font variant), underline (draw line), strikethrough, inverse video.
6. Render cursor as a separate quad (block, bar, or underline shape).

**DONE WHEN**
- [ ] Terminal output renders correctly with colors, bold, underline.
- [ ] Cursor is visible and positioned correctly.
- [ ] Batched rendering achieves target frame rate (60fps) with a full 80x24 grid of colored text.

---

### Task 10 (A) +renderer
**blockedBy:** [6, 9]

**PURPOSE** — Color blending and frame rendering with double-buffering via wgpu.

**WHAT TO DO**
1. In `walk-renderer/src/compositor.rs`, implement a compositor that blends layers: background color/image -> terminal cell backgrounds -> terminal glyphs -> UI overlays (selection, search highlights, block decorations).
2. Use wgpu's built-in alpha blending modes for transparency.
3. Support `theme.opacity` by rendering the terminal content with configurable alpha.
4. Implement double-buffering via wgpu's surface presentation model (acquire texture, render, present).
5. Ensure frame presentation is synchronized with vsync to prevent tearing.

**DONE WHEN**
- [ ] Semi-transparent backgrounds blend correctly with the desktop behind.
- [ ] Selection highlights overlay text without obscuring it (alpha blending).
- [ ] No tearing artifacts during scrolling or rapid output.

---

### Task 11 (B) +renderer
**blockedBy:** [9]

**PURPOSE** — Avoids re-rendering the entire grid every frame for better performance.

**WHAT TO DO**
1. In `walk-renderer/src/damage.rs`, maintain a `DirtyRegion` bitmap (one bit per cell). — WHY per-row granularity as first pass: simpler than per-cell, and most terminal updates affect full rows (scrolling, line editing); per-cell tracking adds O(cols) bookkeeping with marginal savings.
2. After `TerminalState` processes new PTY output, mark changed cells as dirty.
3. On each frame, only rebuild vertex buffer for dirty cells (or dirty rows as a simpler first pass).
4. If scrollback position changes, mark entire viewport dirty.
5. Clear dirty bits after rendering.

**DONE WHEN**
- [ ] Typing a single character does not cause a full-grid re-render (measure with frame timing).
- [ ] Scrolling marks the entire viewport dirty and re-renders correctly.
- [ ] Rapid output (e.g., `cat` a large file) still renders at target frame rate.

---

### Task 12 (A) +renderer
**blockedBy:** [7, 8]

**PURPOSE** — Text shaping and layout: arranges a sequence of characters into positioned glyph runs, handling ligatures and combining characters for correct terminal text rendering.

**WHAT TO DO**
1. Create `walk-renderer/src/text_layout.rs`. Define `GlyphRun { glyphs: Vec<PositionedGlyph> }` and `PositionedGlyph { atlas_entry: AtlasRegion, x: f32, y: f32, color: Color }`.
2. Implement `fn layout_line(text: &str, start_x: f32, baseline_y: f32, style: GlyphStyle, color: Color, font: &FontSystem, atlas: &mut GlyphAtlas) -> GlyphRun`: iterate chars, call `atlas.get_or_insert()` for each, position each glyph using cosmic-text's shaping output.
3. Handle wide characters (CJK, emoji): use `unicode_width::UnicodeWidthChar` to detect double-width characters and advance by `2 * cell_width` for those. Add `unicode-width = "0.2"` to dependencies. — WHY double-width: Unicode Technical Report #11 defines East Asian Width; CJK ideographs and most emoji are 2 cells wide in terminal convention, matching xterm/VT220 behavior.
4. Implement `fn layout_grid(grid: &Grid<Cell>, origin: Point, font: &FontSystem, atlas: &mut GlyphAtlas) -> Vec<GlyphRun>`: Layout each cell at `(col * cell_width, row * line_height)` grid positions, reading cell contents from alacritty_terminal's grid.

**DONE WHEN**
- [ ] `layout_line("Hello", 0.0, 20.0, Regular, WHITE, ...)` produces 5 `PositionedGlyph` entries with strictly increasing x positions.
- [ ] A CJK character (e.g., U+6F22) occupies 2 cell widths in the output positions.
- [ ] `layout_grid` positions glyphs correctly on a 80x24 grid (glyph at col 5, row 3 has x = 5*cell_width, y = 3*line_height + baseline_offset).

---

## Phase 3: Terminal Emulation (+terminal)

### Task 13 (A) +terminal
**blockedBy:** [1]

**PURPOSE** — Provides full VT100/xterm terminal emulation without writing a parser from scratch.

**WHAT TO DO**
1. Add `alacritty_terminal` as a dependency in `walk-terminal/Cargo.toml`.
2. Create `TerminalState` struct wrapping `alacritty_terminal::Term<EventListener>`.
3. Implement `EventListener` trait to capture terminal events (title changes, bell, color requests).
4. Feed PTY output bytes to `term.advance(bytes)`.
5. Expose `grid() -> &Grid<Cell>` for the renderer to read cell contents, colors, and attributes.
6. Expose `selection()`, `cursor()`, and `scrollback_len()` for UI components.
7. Handle resize by calling `term.resize(TermSize { columns, rows })`.

**DONE WHEN**
- [ ] Shell output renders correctly through alacritty_terminal (test with `ls --color`, `vim`, `htop`).
- [ ] Title change events are captured via the EventListener.
- [ ] Resize correctly updates the terminal grid dimensions.

---

### Task 14 (A) +terminal
**blockedBy:** [1]

**PURPOSE** — Spawns and manages shell processes across platforms without writing raw PTY code.

**WHAT TO DO**
1. Add `portable-pty` as a dependency in `walk-terminal/Cargo.toml`.
2. Create `PtyManager` struct that uses `portable_pty::native_pty_system()`.
3. Implement `spawn(shell: &str, size: PtySize, env: HashMap) -> Result<PtyPair>`.
4. Auto-detect shell: check `$SHELL` env, fall back to `/bin/bash` (Unix) or `powershell.exe` (Windows).
5. Spawn reader thread that reads from PTY master and feeds bytes to `TerminalState`.
6. Implement `write(data: &[u8])` to send input to the PTY.
7. Implement `resize(cols, rows)` to resize the PTY.

**DONE WHEN**
- [ ] A shell spawns and interactive commands work (type `echo hello`, see output).
- [ ] Shell auto-detection works on all three platforms.
- [ ] PTY resize correctly propagates to the shell process.

---

### Task 15 (A) +terminal
**blockedBy:** [14]

**PURPOSE** — Asynchronous PTY I/O: spawns a dedicated reader thread that continuously reads PTY output and sends it to the main thread via a channel, preventing UI blocking.

**WHAT TO DO**
1. In `walk-terminal/src/async_io.rs`, create `PtyIoHandle` struct: `{ writer: Arc<Mutex<PtyWriter>>, rx: Receiver<PtyEvent>, _reader_thread: JoinHandle<()> }`.
2. Define `PtyEvent` enum: `Data(Vec<u8>)`, `Exited(i32)`, `Error(PtyError)`.
3. Implement `PtyIoHandle::new(reader: Box<dyn Read>, writer: Box<dyn Write>) -> Self`: spawn a thread that loops: read up to 64KB from the PTY reader into a buffer (WHY 64KB: balances syscall overhead vs memory; smaller reads increase context switches, larger reads increase latency for interactive keystrokes), send `PtyEvent::Data(buf[..n].to_vec())` through a `crossbeam_channel::bounded(256)` channel (WHY bounded(256): backpressure prevents unbounded memory growth during rapid output like `cat /dev/urandom`; 256 * 64KB = 16MB max queue, enough to absorb burst output without starving the reader). On read error, send `PtyEvent::Error`. On EOF, send `PtyEvent::Exited` with the exit code.
4. Implement `PtyIoHandle::try_recv(&self) -> Option<PtyEvent>`: non-blocking receive from the channel.
5. Implement `PtyIoHandle::write(&self, data: &[u8]) -> Result<(), PtyError>`: lock the mutex, write to PTY.
6. Implement `PtyIoHandle::resize(&self, rows: u16, cols: u16) -> Result<(), PtyError>`: resize the PTY.

**DONE WHEN**
- [ ] `PtyIoHandle::try_recv()` returns `Some(PtyEvent::Data(...))` containing shell prompt output within 100ms of spawning.
- [ ] Writing a command via `PtyIoHandle::write` and then polling `try_recv` yields the command output.
- [ ] When the shell exits (`exit 0`), `PtyEvent::Exited(0)` is eventually received.

---

### Task 16 (A) +terminal
**blockedBy:** [13, 15]

**PURPOSE** — Connects the PTY async reader to alacritty_terminal, forming the core data pipeline: PTY bytes -> alacritty_terminal -> screen state for rendering.

**WHAT TO DO**
1. In `walk-terminal/src/terminal.rs`, create `Terminal` struct: `{ state: TerminalState, pty: PtyIoHandle, title: String, dirty: bool }`.
2. Implement `Terminal::new(config: &TerminalConfig) -> Result<Self, TerminalError>`: create PTY via PtyManager with shell from config, create TerminalState with rows/cols.
3. Implement `Terminal::process_pty_output(&mut self)`: call `self.pty.try_recv()` in a loop (up to 64 iterations per frame to avoid stalling the render — WHY 64 iterations: at 64KB per read, processes up to 4MB per frame; enough for `cat` of large files while keeping frame time under 2ms for processing). For each `PtyEvent::Data(bytes)`, feed bytes to `state.advance(bytes)`. Set `self.dirty = true` if any data was processed.
4. Implement `Terminal::send_input(&self, data: &[u8])`: writes to the PTY.
5. Implement `Terminal::resize(&mut self, rows: u16, cols: u16)`: resize TerminalState and PTY.
6. Implement `Terminal::is_dirty(&self) -> bool` and `Terminal::mark_clean(&mut self)`.

**DONE WHEN**
- [ ] Creating a `Terminal` with bash spawns a shell and `process_pty_output` yields a visible prompt in the grid.
- [ ] Calling `send_input(b"ls\n")` and then `process_pty_output` results in `ls` output appearing in the grid cells.
- [ ] `is_dirty()` returns true after new output arrives and false after `mark_clean()`.

---

### Task 17 (B) +terminal
**blockedBy:** [13, 16]

**PURPOSE** — Thin wrapper configuration for alacritty_terminal features: scrollback, text wrapping, Unicode/wide chars, and alternate screen buffer.

**WHAT TO DO**
1. In `walk-terminal/src/config.rs`, create `TerminalConfig` struct exposing configurable options that map to alacritty_terminal's config:
   - `scrollback_lines: usize` (default 10,000) — WHY 10,000: balances memory usage (~10MB for 80-col lines) against usability; most users scroll back minutes, not hours; configurable for power users. Configures alacritty_terminal's scrollback history.
   - `text_wrap: bool` (default true) — configures line wrapping behavior.
   - `unicode_ambiguous_width: u16` (default 1) — WHY default 1: matches xterm default; East Asian users who need width-2 can override, but width-1 is correct for Latin/Cyrillic/Greek scripts. Configures how ambiguous-width Unicode characters are treated.
2. Implement `TerminalConfig::to_alacritty_config(&self) -> alacritty_terminal::Config` that maps Walk's config to alacritty_terminal's internal config struct.
3. Support runtime reconfiguration: implement `Terminal::update_config(&mut self, config: &TerminalConfig)` that applies config changes to the running terminal.
4. Ensure alternate screen buffer handling works correctly for programs like vim, less, htop (alacritty_terminal handles this, but verify the grid switching works with Walk's rendering).

**DONE WHEN**
- [ ] Setting `scrollback_lines = 50000` allows scrolling back through 50,000 lines of history.
- [ ] Text wrapping correctly wraps long lines at the terminal width.
- [ ] Wide characters (CJK) occupy two columns in the grid.
- [ ] Opening and closing `vim` correctly switches between main and alternate screen buffers.

---

## Phase 4: Shell Integration (+shell)

### Task 18 (A) +shell
**blockedBy:** [14]

**PURPOSE** — Shell detection and configuration: automatically detects the user's default shell and provides correct initialization arguments for each supported shell.

**WHAT TO DO**
1. Create `walk-terminal/src/shell.rs`. Define `ShellType` enum: `Bash`, `Zsh`, `Fish`, `PowerShell`, `Wsl(String)` (String = distro name).
2. Implement `fn detect_default_shell() -> ShellType`:
   - On Unix: read `$SHELL` env var, parse the basename. If unset, fall back to `/etc/passwd` entry for current user.
   - On Windows: default to `PowerShell`. Check registry `HKCU\Software\Walk\DefaultShell` for overrides.
3. Implement `fn shell_spawn_config(shell: &ShellType) -> PtyConfig`:
   - Bash: `shell="/bin/bash"`, `args=["--login"]`, set `TERM=xterm-256color`. — WHY xterm-256color: widely supported terminfo entry; enables 256-color and most modern escape sequences without requiring a custom terminfo.
   - Zsh: `shell="/bin/zsh"`, `args=["--login"]`, set `TERM=xterm-256color`.
   - Fish: `shell="/usr/bin/fish"`, `args=["--login"]`, set `TERM=xterm-256color`.
   - PowerShell: `shell="powershell.exe"`, `args=["-NoLogo"]`, set `TERM=xterm-256color`.
   - Wsl(distro): `shell="wsl.exe"`, `args=["-d", &distro, "--", "bash", "--login"]`.
4. Implement `fn available_shells() -> Vec<ShellType>`: scans the system for available shells (check `/etc/shells` on Unix, check PATH for powershell/wsl on Windows).

**DONE WHEN**
- [ ] On a macOS system with zsh as default, `detect_default_shell()` returns `Zsh`.
- [ ] `shell_spawn_config(&ShellType::Bash)` returns a config where `shell` is a valid path to bash and `TERM` is set.
- [ ] `available_shells()` returns at least one shell on every supported platform.

---

### Task 19 (B) +shell
**blockedBy:** [18]

**PURPOSE** — Shell integration scripts: enables block detection by having the shell emit markers around each command.

**WHAT TO DO**
1. Create `shell-integration/` directory with `bash.sh`, `zsh.zsh`, `fish.fish` scripts.
2. Each script hooks into the shell's pre-command and post-command events:
   - bash: `PROMPT_COMMAND` and `trap ... DEBUG`
   - zsh: `precmd` and `preexec` hooks
   - fish: `fish_prompt` and `fish_preexec`/`fish_postexec`
3. Emit OSC escape sequences as markers: `\e]133;A\a` (prompt start), `\e]133;B\a` (command start), `\e]133;C\a` (command end), `\e]133;D;{exit_code}\a` (post-command with exit code). — WHY OSC 133: FinalTerm/iTerm2/VS Code convention for semantic shell integration; using a standard ensures compatibility with existing shell plugins.
4. Also emit OSC 7 (`\033]7;file://<hostname><cwd>\007`) after each `cd` to report the current working directory.
5. Auto-source the appropriate script on shell startup (inject via PTY environment or shell rc detection).
6. Embed all scripts as `include_str!()` constants in `walk-terminal/src/shell_integration.rs`. Implement `fn integration_args(shell: &ShellType) -> Vec<String>` that returns the extra args needed to inject the integration script.

**DONE WHEN**
- [ ] Shell commands in Walk emit OSC 133 markers. Terminal can detect command boundaries.
- [ ] In a Walk+zsh session, `cd /tmp` causes `\033]7;file://<host>/tmp\007` to appear in the PTY output.
- [ ] Integration scripts do not break normal shell operation: `.bashrc`, `.zshrc`, `config.fish` still load, aliases and functions work.

---

### Task 20 (B) +shell
**blockedBy:** [13, 19]

**PURPOSE** — Parse OSC 133 semantic markers from the PTY output stream to identify command boundaries, enabling the Blocks feature.

**WHAT TO DO**
1. Hook into alacritty_terminal's `EventListener` to detect OSC 133 sequences. When the terminal emits an OSC event with first param `133`, parse the second param as the marker type: `A` (prompt start), `B` (command start), `C` (output start), `D` (command end, optional exit code).
2. Define `SemanticEvent` enum in `walk-blocks/src/semantic.rs`: `PromptStart { line: u16 }`, `CommandStart { line: u16 }`, `OutputStart { line: u16 }`, `CommandEnd { line: u16, exit_code: Option<i32> }`, `CwdChanged(PathBuf)`.
3. Extend `Terminal::process_pty_output` to detect these and emit them via a new `events: Vec<SemanticEvent>` field on `Terminal`, drained each frame.
4. Also parse OSC 7 (CWD reporting) and emit `CwdChanged`.

**DONE WHEN**
- [ ] Running `ls` in a Walk+bash session emits the sequence: `PromptStart` -> `CommandStart` -> `OutputStart` -> `CommandEnd { exit_code: Some(0) }`.
- [ ] Running `cd /tmp` emits `CwdChanged("/tmp")`.
- [ ] A command that fails (`false`) emits `CommandEnd { exit_code: Some(1) }`.

---

## Phase 5: Blocks (+blocks)

### Task 21 (A) +blocks
**blockedBy:** [16, 20]

**PURPOSE** — Block data model: represents each command-output pair as a navigable, self-contained "Block" that is the core UX differentiator from traditional terminals.

**WHAT TO DO**
1. Create `walk-blocks/src/block.rs`. Define `Block` struct: `{ id: u64, prompt_text: String, command_text: String, output_start_line: usize, output_end_line: usize, exit_code: Option<i32>, start_time: Instant, end_time: Option<Instant>, is_collapsed: bool, scroll_offset: usize }`.
2. Define `BlockManager` struct: `{ blocks: Vec<Block>, active_block: Option<u64>, next_id: u64, state: BlockBuildState }` where `BlockBuildState` enum: `WaitingForPrompt`, `InPrompt { start_line: u16 }`, `InCommand { prompt_text: String }`, `InOutput { block_id: u64 }`.
3. Implement `BlockManager::handle_event(&mut self, event: &SemanticEvent, grid: &Grid<Cell>)`:
   - `PromptStart`: transition to `InPrompt`, record start line.
   - `CommandStart`: capture prompt text from grid lines between prompt start and current line, transition to `InCommand`.
   - `OutputStart`: create a new `Block` with the captured command text, transition to `InOutput`.
   - `CommandEnd`: finalize the active block with exit code and `end_time`.
4. Implement `BlockManager::get_block(&self, id: u64) -> Option<&Block>`.
5. Implement `BlockManager::visible_blocks(&self) -> &[Block]`: returns blocks that should be rendered in the current viewport.
6. Track output line ranges while in `InOutput` state by recording start/end line indices into the terminal grid.

**DONE WHEN**
- [ ] After running `echo hello`, `BlockManager` contains one completed Block with `command_text == "echo hello"`, correct output line range, and `exit_code == Some(0)`.
- [ ] After running 3 commands, `blocks.len() == 3` with correct ordering.
- [ ] A block for `false` has `exit_code == Some(1)`.

---

### Task 22 (A) +blocks
**blockedBy:** [21]

**PURPOSE** — Block navigation: keyboard shortcuts to jump between blocks, select blocks, and copy block content.

**WHAT TO DO**
1. In `walk-blocks/src/block_nav.rs`, implement `BlockNavigator` struct: `{ selected_block_index: Option<usize>, block_manager: BlockManager }`.
2. Implement navigation keybindings (to be wired in the keybinding system later):
   - `Cmd/Ctrl+Up`: select previous block (decrement `selected_block_index`).
   - `Cmd/Ctrl+Down`: select next block.
   - `Cmd/Ctrl+Shift+C`: copy selected block's output to clipboard (full text).
   - `Cmd/Ctrl+Shift+Up`: select from current block to the first block.
   - `Enter` on a selected block: re-run the block's command (send command text to PTY).
3. Implement `BlockNavigator::selected_block(&self) -> Option<&Block>`.
4. Implement `BlockNavigator::toggle_collapse(&mut self)`: collapse/expand the selected block's output.
5. Visual state: when a block is selected, the renderer should draw a highlight border around it. Add `is_selected: bool` to the block rendering data.

**DONE WHEN**
- [ ] After running 5 commands, pressing Cmd+Up 3 times selects the 3rd-from-last block.
- [ ] Pressing Cmd+Down from the first block selects the second block.
- [ ] Copy block (Cmd+Shift+C) on a selected block writes the output text to the system clipboard (verified by pasting elsewhere).
- [ ] Toggle collapse hides the block's output lines and re-expand shows them.

---

### Task 23 (B) +blocks
**blockedBy:** [21]

**PURPOSE** — Block metadata: captures timing and git context for each command block.

**WHAT TO DO**
1. In `walk-blocks/src/block.rs`, extend `Block` with fields: `duration: Option<Duration>` (computed from `end_time - start_time`), `git_branch: Option<String>`, `git_dirty: Option<bool>`, `cwd: PathBuf`.
2. When `CommandEnd` fires, compute duration and store it.
3. Implement `fn detect_git_info(cwd: &Path) -> Option<GitInfo>` where `GitInfo { branch: String, is_dirty: bool }`: walk up from CWD, find `.git/HEAD`, parse branch name. Check `.git/status` or run lightweight git status check.
4. Render block metadata in the block header: show duration (e.g., "1.2s"), git branch if available, and CWD.

**DONE WHEN**
- [ ] A block that ran for 2 seconds shows `duration: Some(Duration::from_secs(2))`.
- [ ] A block executed inside a git repo shows the current branch name.
- [ ] Block headers display duration and git info in the UI.

---

### Task 24 (B) +blocks
**blockedBy:** [21, 22]

**PURPOSE** — Search within a Block: allows the user to search for text within a specific block's output, with match highlighting and navigation.

**WHAT TO DO**
1. In `walk-blocks/src/block_search.rs`, create `BlockSearch` struct: `{ query: String, matches: Vec<SearchMatch>, current_match: usize, target_block_id: u64 }` where `SearchMatch { line: usize, col_start: usize, col_end: usize }`.
2. Implement `BlockSearch::new(block: &Block, query: &str, grid: &Grid<Cell>) -> Self`: scan the block's output lines in the grid for substring matches (case-insensitive). Populate `matches`.
3. Implement `BlockSearch::next_match(&mut self) -> Option<&SearchMatch>`: advance `current_match`, wrapping at end.
4. Implement `BlockSearch::prev_match(&mut self) -> Option<&SearchMatch>`.
5. Implement `BlockSearch::highlight_ranges(&self) -> Vec<(usize, usize, usize)>`: returns `(line, col_start, col_end)` tuples for the renderer to overlay highlights on matching text (yellow background for all matches, orange for the current match).
6. Keybinding: `Cmd/Ctrl+F` while a block is selected enters block-search mode. `Enter` = next match, `Shift+Enter` = previous, `Escape` = exit search.

**DONE WHEN**
- [ ] Searching "error" in a block containing 3 lines with "error" returns `matches.len() == 3`.
- [ ] `next_match` cycles through all matches and wraps to the first after the last.
- [ ] `highlight_ranges` returns correct `(line, col_start, col_end)` tuples that correspond to the actual positions of "error" in the output.

---

## Phase 6: Input Editor (+input)

### Task 25 (A) +input
**blockedBy:** [1]

**PURPOSE** — Core text buffer for the input editor: a gap buffer data structure that supports efficient editing, insertions, and deletions.

**WHAT TO DO**
1. Create `walk-input/src/buffer.rs`. Implement `InputBuffer` struct using a gap buffer: `{ text: Vec<char>, gap_start: usize, gap_end: usize, cursors: Vec<Cursor> }` where `Cursor { position: usize, anchor: Option<usize> }` (anchor is set when there's a selection; the selection range is `min(position, anchor)..max(position, anchor)`).
2. Implement `InputBuffer::new() -> Self` with initial capacity of 1024 chars, gap size 256. — WHY 1024 initial capacity: covers the vast majority of single-line commands (typical shell command <200 chars) with room for multi-line scripts; avoids reallocation for normal use. WHY 256 gap: amortizes insert cost; gap is moved on cursor movement, so a gap matching typical typing burst size (a few words) minimizes memmoves.
3. Implement `insert_at(&mut self, cursor_idx: usize, text: &str)`: move gap to cursor position, insert chars, advance cursor and adjust all cursors after it.
4. Implement `delete_range(&mut self, start: usize, end: usize)`: collapse range, adjust cursors.
5. Implement `text(&self) -> String`: return the full text content (excluding gap).
6. Implement `line_count(&self) -> usize`, `line_text(&self, line: usize) -> &str`, `cursor_positions(&self) -> Vec<(usize, usize)>` (row, col).
7. Implement multi-cursor support: `add_cursor(&mut self, position: usize)`, `remove_cursor(&mut self, idx: usize)`. When inserting/deleting, apply the operation at every cursor, adjusting positions after each application.

**DONE WHEN**
- [ ] `insert_at(0, "hello")` then `text()` returns `"hello"`, cursor is at position 5.
- [ ] With two cursors at positions 0 and 5 in `"helloworld"`, inserting `"_"` at both produces `"_hello_world"`.
- [ ] `delete_range(2, 4)` on `"abcdef"` produces `"abef"`.
- [ ] `line_count()` returns 3 for `"a\nb\nc"`.

---

### Task 26 (A) +input
**blockedBy:** [25]

**PURPOSE** — Input editor cursor movement: implements all VS Code-style cursor motions including word boundaries, line start/end, and selection extension.

**WHAT TO DO**
1. In `walk-input/src/cursor_ops.rs`, implement cursor movement functions that operate on `InputBuffer`:
   - `move_left(buf, cursor_idx, extend_selection: bool)`: move one char left. If `extend_selection`, set/maintain anchor; otherwise clear anchor.
   - `move_right(buf, cursor_idx, extend_selection)`: one char right.
   - `move_word_left(buf, cursor_idx, extend_selection)`: jump to previous word boundary (transition from non-alphanumeric to alphanumeric, scanning left).
   - `move_word_right(buf, cursor_idx, extend_selection)`: jump to next word boundary.
   - `move_line_start(buf, cursor_idx, extend_selection)`: move to column 0 of current line, or to first non-whitespace char if already at column 0 (smart home).
   - `move_line_end(buf, cursor_idx, extend_selection)`.
   - `move_up(buf, cursor_idx, extend_selection)`: move to same column on previous line (or clamp).
   - `move_down(buf, cursor_idx, extend_selection)`.
2. Implement `select_all(buf)`: set cursor at end with anchor at 0.
3. Implement `select_word_at(buf, position: usize)`: set anchor and cursor to word boundaries around position.
4. Implement `select_line_at(buf, line: usize)`: select entire line.

**DONE WHEN**
- [ ] In `"hello world"`, cursor at 6, `move_word_left` moves cursor to 0 (start of "hello").
- [ ] In `"  hello"`, cursor at 0, `move_line_start` moves to 2 (first non-space). Pressing again moves to 0.
- [ ] `select_all` on `"abc"` results in selection range `0..3`.
- [ ] `move_down` from middle of line 1 in a 3-line buffer moves to the same column on line 2 (or end of line 2 if shorter).

---

### Task 27 (A) +input
**blockedBy:** [25, 18]

**PURPOSE** — Syntax highlighting for the command input: provides real-time coloring of commands, arguments, paths, strings, and flags as the user types.

**WHAT TO DO**
1. Create `walk-input/src/highlighter.rs`. Define `HighlightSpan { start: usize, end: usize, kind: SpanKind }` and `SpanKind` enum: `Command`, `Argument`, `Flag`, `Path`, `String`, `Number`, `Pipe`, `Redirect`, `Variable`, `Comment`, `Error`, `Default`.
2. Implement `fn highlight(text: &str, shell: &ShellType) -> Vec<HighlightSpan>`:
   - Tokenize by splitting on whitespace, respecting quoted strings (`"..."`, `'...'`).
   - First token = `Command` (check if it exists in PATH for error highlighting -- cache PATH lookup results).
   - Tokens starting with `-` or `--` = `Flag`.
   - Tokens containing `/` or `~` = `Path`.
   - Tokens matching `$VARNAME` or `${VAR}` = `Variable`.
   - `|` = `Pipe`, `>`, `>>`, `<` = `Redirect`.
   - Tokens starting with `#` (in bash/zsh/fish) = `Comment` (rest of line).
   - Quoted strings = `String`.
   - Numeric-only tokens = `Number`.
3. Map each `SpanKind` to a `Color` via the active theme.

**DONE WHEN**
- [ ] `highlight("git commit -m 'hello'", &Bash)` returns spans: `Command(0..3)`, `Argument(4..10)`, `Flag(11..13)`, `String(14..21)`.
- [ ] `highlight("cat /tmp/file | grep 'err'", &Bash)` correctly identifies `Path`, `Pipe`, `Command(grep)`, `String`.
- [ ] A non-existent command like `highlight("xyznotreal arg", &Bash)` marks `xyznotreal` as `Error`.

---

### Task 28 (B) +input
**blockedBy:** [25]

**PURPOSE** — Bracket matching: highlights the matching bracket/paren/brace when the cursor is adjacent to one, essential for complex command editing.

**WHAT TO DO**
1. In `walk-input/src/brackets.rs`, define bracket pairs: `('(', ')')`, `('[', ']')`, `('{', '}')`.
2. Implement `fn find_matching_bracket(text: &str, position: usize) -> Option<usize>`:
   - If char at `position` (or `position - 1`) is an opening bracket, scan forward with a nesting counter, skipping quoted strings.
   - If it's a closing bracket, scan backward with a nesting counter.
   - Return the position of the matching bracket, or `None` if unmatched.
3. Integrate with the input editor rendering: when cursor is adjacent to a bracket, call `find_matching_bracket`. If a match is found, both brackets should be rendered with a highlight background color (from theme).

**DONE WHEN**
- [ ] In `"echo $(cat file)"`, cursor at position 5 (the `$(`), `find_matching_bracket` returns the position of the closing `)`.
- [ ] Nested brackets: `"echo $((1+2))"` -- cursor at outer `(` matches outer `)`.
- [ ] Unmatched `"echo (foo"` returns `None`.
- [ ] Brackets inside quotes are ignored: `"echo '(not a bracket)'"` -- cursor at `'(` returns `None`.

---

### Task 29 (B) +input
**blockedBy:** [25, 26, 27, 3]

**PURPOSE** — Multi-line input editing with proper line wrapping display and the ability to toggle input position between top and bottom of the terminal.

**WHAT TO DO**
1. In `walk-input/src/editor.rs`, create `InputEditor` struct: `{ buffer: InputBuffer, highlighter: fn, scroll_offset: usize, position: InputPosition, history: CommandHistory, is_active: bool }` where `InputPosition` enum: `Top`, `Bottom`.
2. Implement `InputEditor::handle_key(&mut self, event: &InputEvent) -> Option<EditorAction>` where `EditorAction` enum: `Submit(String)` (user pressed Enter without Shift), `None`. Map:
   - Regular chars -> insert at all cursors.
   - `Shift+Enter` -> insert newline (multi-line mode).
   - `Enter` -> Submit.
   - `Backspace` -> delete before cursor.
   - `Delete` -> delete after cursor.
   - Arrow keys (with/without Shift/Ctrl/Alt) -> delegate to cursor_ops.
   - `Ctrl+D` on empty buffer -> send EOF to PTY.
   - `Tab` -> insert literal tab or trigger completion (future).
3. Implement `InputEditor::render_data(&self) -> InputRenderData` containing: all lines of text with syntax highlights, cursor positions, bracket match positions, selection ranges, the `InputPosition`.
4. Implement `InputEditor::set_position(&mut self, pos: InputPosition)`.
5. The renderer will use `render_data` to draw the input area at the top or bottom of the terminal viewport.

**DONE WHEN**
- [ ] Typing `echo hello` and pressing Enter returns `EditorAction::Submit("echo hello")` and clears the buffer.
- [ ] `Shift+Enter` inserts a newline; buffer contains `"line1\nline2"`.
- [ ] `set_position(Top)` causes `render_data().position` to be `Top`.
- [ ] Multi-cursor editing works end-to-end: `Ctrl+Click` (from mouse handler) adds a cursor; typing inserts at all cursors.

---

### Task 30 (B) +input
**blockedBy:** [25]

**PURPOSE** — Command history: persists and navigates through previously executed commands, shared across sessions via a history file.

**WHAT TO DO**
1. In `walk-input/src/history.rs`, create `CommandHistory` struct: `{ entries: Vec<String>, cursor: usize, history_file: PathBuf, max_entries: usize, search_query: Option<String>, search_results: Vec<usize> }`.
2. Implement `CommandHistory::load(path: &Path, max: usize) -> Self`: read history file (one command per line, most recent last). Default path: `~/.walk_history`. Default max: 10,000 entries. — WHY 10,000 max entries: balances file size (~500KB for typical commands) against recall depth; matches shell history defaults (bash HISTSIZE=1000 is often too low, 10K covers weeks of use).
3. Implement `push(&mut self, command: &str)`: append to entries and to history file. Skip duplicates of the immediately previous entry.
4. Implement `prev(&mut self) -> Option<&str>`: navigate backward (Up arrow). Save the current input buffer as a "future" entry so Down arrow can return to it.
5. Implement `next(&mut self) -> Option<&str>`: navigate forward (Down arrow).
6. Implement `search(&mut self, query: &str) -> Vec<&str>`: reverse search (Ctrl+R style) returning all entries containing the query, most recent first.
7. Implement `save(&self)`: write all entries to history file.
8. Implement `Drop for CommandHistory`: call `save()`.

**DONE WHEN**
- [ ] After executing 3 commands and pressing Up 3 times, the input shows each previous command in reverse order.
- [ ] Pressing Down after Up returns to the next command, and from the most recent returns to the user's partially typed input.
- [ ] `search("git")` returns all history entries containing "git".
- [ ] History persists across application restarts (file exists at `~/.walk_history`).

---

## Phase 7: UI Framework & Layout (+ui)

### Task 31 (A) +ui
**blockedBy:** [1, 4]

**PURPOSE** — Layout engine: a flexbox-inspired layout system that computes positions and sizes for all UI elements (tabs bar, input editor, terminal viewport, status bar, split panes).

**WHAT TO DO**
1. Create `walk-ui/src/layout/mod.rs`. Define `LayoutNode` enum:
   ```rust
   enum LayoutNode {
       Leaf { id: NodeId, min_size: Size, flex: f32 },
       Row { children: Vec<LayoutNode>, gap: f32 },
       Column { children: Vec<LayoutNode>, gap: f32 },
   }
   ```
2. Define `LayoutResult` struct: `{ rects: HashMap<NodeId, Rect> }`.
3. Implement `fn compute_layout(root: &LayoutNode, available: Rect) -> LayoutResult`:
   - For `Row`: distribute `available.w` among children proportional to their `flex` values, respecting `min_size.w`. Each child gets full height.
   - For `Column`: distribute `available.h` among children proportional to `flex`, respecting `min_size.h`. Each child gets full width.
   - For `Leaf`: assign the computed rect to the `id`.
4. Define `NodeId` constants: `TAB_BAR`, `TERMINAL_VIEWPORT`, `INPUT_EDITOR`, `STATUS_BAR`, `SPLIT_DIVIDER`.
5. Implement `fn build_default_layout(input_position: InputPosition) -> LayoutNode`: constructs the column layout. If `InputPosition::Bottom`: TabBar (fixed 32px — WHY 32px: fits one row of tab text at 14px with 9px vertical padding, matching browser tab bar conventions) -> Viewport (flex 1.0) -> InputEditor (min 40px — WHY 40px: fits one line of input text at 14px with padding, expanding for multi-line; smaller causes text clipping, flex 0) -> StatusBar (fixed 24px — WHY 24px: fits status text at 12px with 6px vertical padding, compact but readable). If `Top`: TabBar -> InputEditor -> Viewport -> StatusBar.

**DONE WHEN**
- [ ] `compute_layout` with a 1200x800 available rect and default bottom layout produces: TabBar at (0,0,1200,32), Viewport at (0,32,1200,704), InputEditor at (0,736,1200,40), StatusBar at (0,776,1200,24).
- [ ] Resizing to 600x400 still allocates correctly with the viewport shrinking.
- [ ] `build_default_layout(Top)` places InputEditor before Viewport.

---

### Task 32 (A) +ui
**blockedBy:** [16, 18, 31]

**PURPOSE** — Tab management: allows multiple terminal sessions as tabs with creation, closing, switching, and drag-to-reorder.

**WHAT TO DO**
1. In `walk-ui/src/tabs.rs`, create `TabManager` struct: `{ tabs: Vec<Tab>, active_tab: usize }` where `Tab { id: u64, title: String, terminal: Terminal, is_dirty: bool }`.
2. Implement `TabManager::new_tab(&mut self, shell: &ShellType) -> u64`: create a new `Terminal` instance, add a `Tab`, make it active, return the id.
3. Implement `close_tab(&mut self, id: u64)`: close the tab's terminal (drop PTY), remove from list, adjust `active_tab`.
4. Implement `switch_tab(&mut self, index: usize)`, `next_tab(&mut self)`, `prev_tab(&mut self)`.
5. Implement `move_tab(&mut self, from: usize, to: usize)`: reorder tabs.
6. Implement `active_terminal(&mut self) -> &mut Terminal`: returns the active tab's terminal.
7. Tab title: default to shell name. Update to current CWD basename when `CwdChanged` events arrive. Update to running process name if available (parse from OSC 0 title-setting sequences).
8. Keybindings: `Cmd/Ctrl+T` = new tab, `Cmd/Ctrl+W` = close tab, `Cmd/Ctrl+Tab` = next tab, `Cmd/Ctrl+Shift+Tab` = prev tab, `Cmd/Ctrl+1-9` = switch to tab N.

**DONE WHEN**
- [ ] `new_tab` creates a tab with a running shell; `close_tab` terminates the shell process.
- [ ] `next_tab` from the last tab wraps to the first.
- [ ] `move_tab(0, 2)` reorders tabs correctly in a 3-tab setup.
- [ ] Tab title updates when `cd /tmp` is run (becomes "tmp").

---

### Task 33 (A) +ui
**blockedBy:** [31, 32]

**PURPOSE** — Split pane management: allows horizontal and vertical splitting of the terminal viewport with resizable dividers.

**WHAT TO DO**
1. In `walk-ui/src/splits.rs`, define a binary tree structure:
   ```rust
   enum SplitNode {
       Leaf { tab_id: u64 },
       Split { direction: SplitDirection, ratio: f32, first: Box<SplitNode>, second: Box<SplitNode> },
   }
   enum SplitDirection { Horizontal, Vertical }
   ```
2. Create `SplitManager` struct: `{ root: SplitNode, focused_leaf: u64 }`.
3. Implement `SplitManager::split_active(&mut self, direction: SplitDirection, new_tab_id: u64)`: replace the focused leaf with a `Split` node containing the old leaf and a new leaf with `new_tab_id`, ratio 0.5.
4. Implement `close_split(&mut self, tab_id: u64)`: remove the leaf, collapse the parent Split into the remaining sibling.
5. Implement `resize_split(&mut self, tab_id: u64, delta: f32)`: adjust the ratio of the parent split, clamping to `[0.1, 0.9]`. — WHY [0.1, 0.9] clamp: prevents a pane from becoming too small to display content (< ~80px on a 800px viewport) while allowing extreme splits for reference panes.
6. Implement `focus_direction(&mut self, direction: Direction)` where `Direction { Left, Right, Up, Down }`: navigate focus to the adjacent pane in the given direction.
7. Implement `compute_rects(&self, available: Rect) -> HashMap<u64, Rect>`: recursively compute the screen rect for each leaf by splitting the available rect according to direction and ratio.
8. Keybindings: `Cmd/Ctrl+D` = split vertical, `Cmd/Ctrl+Shift+D` = split horizontal, `Cmd/Ctrl+Alt+Arrow` = focus direction, `Cmd/Ctrl+Shift+Arrow` = resize split.

**DONE WHEN**
- [ ] Splitting an 800x600 pane vertically produces two 400x600 rects.
- [ ] Splitting horizontally produces two 800x300 rects.
- [ ] `resize_split` with delta +0.1 changes ratio from 0.5 to 0.6, adjusting child rects.
- [ ] `close_split` on one leaf of a 2-pane setup returns to a single leaf with the full rect.
- [ ] Nested splits work: split A vertically, then split the right pane horizontally -> 3 panes with correct rects.

---

### Task 34 (A) +ui
**blockedBy:** [9, 10, 12, 16, 21, 31]

**PURPOSE** — Terminal viewport renderer: draws the terminal grid, cursor, and block decorations using the wgpu renderer, forming the main visual area of the terminal.

**WHAT TO DO**
1. In `walk-ui/src/viewport.rs`, create `ViewportRenderer` struct: `{ scroll_position: f32, smooth_scroll_target: f32, selection: Option<TextSelection> }` where `TextSelection { start: (u16, u16), end: (u16, u16) }`.
2. Implement `ViewportRenderer::render(&mut self, gpu: &GpuContext, terminal: &Terminal, rect: Rect, font: &FontSystem, atlas: &mut GlyphAtlas, theme: &Theme)`:
   - Clear the viewport rect with `theme.background_color`.
   - Iterate visible rows of the terminal grid (accounting for scroll position into scrollback).
   - For each cell: if `bg != default`, draw a background rect. Draw the glyph with fg color from the cell style.
   - Draw underline/strikethrough as thin rects if cell attrs include them.
   - Draw the cursor: block cursor = filled rect at cursor position with inverted colors; bar cursor = 2px wide rect (WHY 2px: visible on both 1x and 2x displays; 1px disappears on some LCDs, 3px looks chunky); underline cursor = 2px tall rect at baseline.
   - Draw block decorations: if BlockManager has completed blocks visible, draw a left-side color bar (green for exit 0, red for nonzero) and a subtle separator line between blocks.
   - Draw selection highlight: semi-transparent blue overlay rect for selected cells.
3. Implement smooth scrolling: each frame, lerp `scroll_position` toward `smooth_scroll_target` by 0.2. — WHY 0.2 lerp factor: reaches target in ~10 frames (~167ms at 60fps), feels responsive without being jarring; lower values (0.05) feel sluggish, higher values (0.5) remove the smoothing effect.
4. Implement `ViewportRenderer::handle_scroll(&mut self, delta: f32)`: adjust `smooth_scroll_target` (clamped to valid scrollback range).

**DONE WHEN**
- [ ] A screen with "Hello" at row 0, col 0 renders the 5 glyphs at the correct pixel positions.
- [ ] Bold and colored text renders with the correct font variant and color.
- [ ] Cursor is visible and blinks (toggle visibility every 500ms — WHY 500ms: standard cursor blink rate used by Windows, macOS, and most editors; fast enough to notice, slow enough not to distract).
- [ ] Scrolling up into scrollback shows historical lines; scrolling down returns to live output.
- [ ] Block separators and exit-code color bars are visible between completed command blocks.

---

### Task 35 (B) +ui
**blockedBy:** [9, 12, 31, 32]

**PURPOSE** — Tab bar renderer: draws the tab strip at the top of the window with active tab highlighting, close buttons, and new-tab button.

**WHAT TO DO**
1. In `walk-ui/src/tab_bar.rs`, create `TabBarRenderer`.
2. Implement `render(&self, gpu: &GpuContext, tabs: &TabManager, rect: Rect, font: &FontSystem, atlas: &mut GlyphAtlas, theme: &Theme)`:
   - Background: draw a rect with `theme.tab_bar_bg`.
   - For each tab: draw a tab rect. Active tab gets `theme.tab_active_bg`, inactive gets `theme.tab_inactive_bg`. Render tab title text centered in the tab rect, truncated with "..." if too wide.
   - Draw a small "x" close button on hover (tracked via mouse position).
   - Draw a "+" new tab button at the end of the tab strip.
   - If tabs overflow the width, draw left/right scroll arrows.
3. Implement `TabBarRenderer::handle_click(&self, pos: Point, tabs: &mut TabManager) -> Option<TabBarAction>` where `TabBarAction { SwitchTab(usize), CloseTab(u64), NewTab, DragStart(usize) }`.
4. Implement `handle_drag(&self, from: usize, to_pos: Point, tabs: &mut TabManager)`: reorder tabs via drag.

**DONE WHEN**
- [ ] 3 tabs render side by side with the active tab visually distinct.
- [ ] Clicking a tab switches to it.
- [ ] Clicking "x" on a tab closes it.
- [ ] Clicking "+" creates a new tab.
- [ ] More tabs than fit in the width shows scroll indicators.

---

### Task 36 (B) +ui
**blockedBy:** [9, 12, 23, 31]

**PURPOSE** — Status bar renderer: displays current CWD, shell type, git branch (if in a repo), encoding, and line/col position.

**WHAT TO DO**
1. In `walk-ui/src/status_bar.rs`, create `StatusBarRenderer`.
2. Implement `render(&self, gpu: &GpuContext, state: &StatusBarState, rect: Rect, font: &FontSystem, atlas: &mut GlyphAtlas, theme: &Theme)`:
   - Background: `theme.status_bar_bg`.
   - Left side: shell icon/name + CWD (truncated from left if too long, e.g., ".../src/main.rs").
   - Center: git branch name if available (read from CWD's `.git/HEAD`).
   - Right side: cursor position "Ln X, Col Y" + encoding "UTF-8".
3. Define `StatusBarState { cwd: PathBuf, shell: ShellType, git_branch: Option<String>, cursor_line: u16, cursor_col: u16 }`.
4. Implement `fn detect_git_branch(cwd: &Path) -> Option<String>`: walk up from cwd, find `.git/HEAD`, parse `ref: refs/heads/<branch>`.

**DONE WHEN**
- [ ] Status bar renders CWD, shell name, and cursor position at the correct locations.
- [ ] Git branch shows "main" when CWD is inside a git repo on the main branch.
- [ ] CWD longer than available width truncates with "..." prefix.
- [ ] Git branch shows `None` when not in a git repo.

---

## Phase 8: Theming (+theme)

### Task 37 (A) +theme
**blockedBy:** [1]

**PURPOSE** — Theme data model: defines the complete color and style specification for every visual element of the terminal.

**WHAT TO DO**
1. Create `walk-ui/src/theme.rs`. Define `Theme` struct with fields:
   ```rust
   pub struct Theme {
       pub name: String,
       pub background: Color,
       pub foreground: Color,
       pub cursor: Color,
       pub selection: Color,
       pub ansi_colors: [Color; 16],  // standard 8 + bright 8 — WHY 16: ECMA-48 standard defines 8 base + 8 bright colors; every terminal app expects these 16 to be present
       pub tab_bar_bg: Color,
       pub tab_active_bg: Color,
       pub tab_inactive_bg: Color,
       pub tab_text: Color,
       pub status_bar_bg: Color,
       pub status_bar_text: Color,
       pub input_bg: Color,
       pub input_text: Color,
       pub block_separator: Color,
       pub block_success_accent: Color,
       pub block_error_accent: Color,
       pub highlight_match: Color,
       pub highlight_current_match: Color,
       pub bracket_match: Color,
       pub syntax: SyntaxColors,
       pub font_family: String,
       pub font_size: f32,
       pub opacity: f32,
       pub background_image: Option<PathBuf>,
   }
   ```
   where `SyntaxColors { command: Color, argument: Color, flag: Color, path: Color, string: Color, number: Color, pipe: Color, redirect: Color, variable: Color, comment: Color, error: Color }`.
2. Implement `Theme::default() -> Self`: a dark theme inspired by Warp's default (dark navy background, light text, teal accents).
3. Implement the standard ANSI 16-color palette as constants.

**DONE WHEN**
- [ ] `Theme::default()` returns a valid theme with all 16 ANSI colors set, `opacity == 1.0`, `font_size == 14.0`. — WHY 14.0 default font size: readable on both 1x and 2x displays; 12px is too small for Retina, 16px wastes space; 14px is the most common default across VS Code, Warp, iTerm2.
- [ ] All `Color` fields have alpha values in `[0.0, 1.0]`.

---

### Task 38 (A) +theme
**blockedBy:** [37]

**PURPOSE** — Theme loading from TOML files: allows users to customize the terminal's appearance by providing a TOML theme file.

**WHAT TO DO**
1. Add `toml = "0.8"` and `serde = { version = "1", features = ["derive"] }` to `walk-ui/Cargo.toml`.
2. In `walk-ui/src/theme_loader.rs`, implement `fn load_theme(path: &Path) -> Result<Theme, ThemeError>`:
   - Read file, parse as TOML.
   - Deserialize into a `ThemeToml` struct (all fields optional) using `serde::Deserialize`.
   - Merge with `Theme::default()`: for each field in `ThemeToml`, if `Some`, override the default.
3. Define the TOML schema:
   ```toml
   name = "My Theme"
   background = "#1a1b26"
   foreground = "#c0caf5"
   cursor = "#f7768e"
   opacity = 0.95
   font_family = "JetBrains Mono"
   font_size = 14.0
   [ansi]
   black = "#15161e"
   red = "#f7768e"
   # ... etc
   [syntax]
   command = "#7aa2f7"
   # ... etc
   ```
4. Implement `fn discover_themes(config_dir: &Path) -> Vec<PathBuf>`: scan `<config_dir>/themes/` for `.toml` files.
5. Support hex color strings (`#RRGGBB`, `#RRGGBBAA`) with `fn parse_hex_color(s: &str) -> Result<Color, ThemeError>`.

**DONE WHEN**
- [ ] A valid TOML theme file loads and overrides the default background color.
- [ ] A TOML file with only `background` set results in a theme where all other fields match the default.
- [ ] `parse_hex_color("#ff0000")` returns `Color { r: 1.0, g: 0.0, b: 0.0, a: 1.0 }`.
- [ ] `parse_hex_color("#ff000080")` returns `Color { ..., a: 0.502 }`.
- [ ] An invalid TOML file returns `Err(ThemeError::Parse(...))`.

---

### Task 39 (B) +theme
**blockedBy:** [37, 38]

**PURPOSE** — Theme hot-reloading: watches the active theme file for changes and applies updates without restarting the terminal.

**WHAT TO DO**
1. Add `notify = "6"` to `walk-ui/Cargo.toml` (cross-platform filesystem watcher).
2. In `walk-ui/src/theme_watcher.rs`, create `ThemeWatcher` struct: `{ watcher: RecommendedWatcher, rx: Receiver<notify::Result<Event>>, active_path: PathBuf }`.
3. Implement `ThemeWatcher::new(theme_path: &Path) -> Result<Self, ThemeError>`: create a `notify` watcher watching the theme file for `Modify` events.
4. Implement `ThemeWatcher::poll(&self) -> Option<Theme>`: non-blocking check for file change events. If changed, reload the theme via `load_theme`, return `Some(theme)`. If the reload fails, log the error and return `None` (keep the old theme).
5. Integrate into the main app loop: each frame, call `theme_watcher.poll()`. If `Some(new_theme)`, update the active theme, invalidate the glyph atlas if font changed, and trigger a full re-render.

**DONE WHEN**
- [ ] Editing and saving the theme TOML file while Walk is running causes the UI to update colors within 1 second.
- [ ] Changing `font_size` in the theme triggers atlas rebuild and re-render at the new size.
- [ ] A syntax error in the theme TOML does not crash the app; the old theme persists and an error is logged to stderr.

---

### Task 40 (C) +theme
**blockedBy:** [6, 9, 37]

**PURPOSE** — Background image and transparency support: renders a user-specified background image behind the terminal content with configurable opacity.

**WHAT TO DO**
1. In `walk-ui/src/background.rs`, create `BackgroundRenderer` struct: `{ texture: Option<wgpu::Texture>, image_size: (u32, u32) }`.
2. Implement `BackgroundRenderer::load_image(&mut self, path: &Path, gpu: &GpuContext) -> Result<(), BackgroundError>`: read image file using `image = "0.25"` crate, decode to RGBA8 pixels, upload to GPU via wgpu texture.
3. Implement `BackgroundRenderer::render(&self, gpu: &GpuContext, viewport: Rect, opacity: f32)`:
   - If no image: skip (clear color handles background).
   - If image loaded: draw a full-viewport textured quad with the image, scaled to cover (maintaining aspect ratio, cropping overflow). Apply `opacity` to the image.
4. Window transparency: on macOS, set `NSWindow.isOpaque = false` and `NSWindow.backgroundColor = NSColor.clear`. On Linux, request an ARGB visual. On Windows, use `DwmExtendFrameIntoClientArea` or `SetLayeredWindowAttributes`.
5. Integrate: render background image first, then render terminal content on top. When `theme.opacity < 1.0`, the window itself is transparent and the terminal content is rendered with semi-transparent background rects.

**DONE WHEN**
- [ ] Setting `background_image = "/path/to/image.png"` in theme displays the image behind terminal text.
- [ ] Setting `opacity = 0.8` makes the window 20% transparent, showing the desktop behind.
- [ ] An invalid image path logs an error but doesn't crash; terminal renders normally without a background image.
- [ ] Resizing the window rescales the background image correctly.

---

## Phase 9: Configuration & Keybindings (+config)

### Task 41 (A) +config
**blockedBy:** [18, 37]

**PURPOSE** — Configuration file system: loads, validates, and provides typed access to all Walk settings from a TOML config file.

**WHAT TO DO**
1. In `walk-app/src/config.rs`, define `WalkConfig` struct:
   ```rust
   pub struct WalkConfig {
       pub shell: ShellType,
       pub theme_path: Option<PathBuf>,
       pub font_family: String,
       pub font_size: f32,
       pub input_position: InputPosition,
       pub scrollback_lines: usize,
       pub cursor_style: CursorStyle,  // Block, Bar, Underline
       pub cursor_blink: bool,
       pub tab_bar_visible: bool,
       pub status_bar_visible: bool,
       pub window_opacity: f32,
       pub background_image: Option<PathBuf>,
       pub copy_on_select: bool,
       pub confirm_close_with_running_process: bool,
       pub keybindings: KeybindingConfig,
   }
   ```
2. Implement `WalkConfig::load() -> Self`:
   - Search for config file at: `$WALK_CONFIG`, then `~/.config/walk/config.toml`, then `~/.walk.toml`.
   - Parse TOML, deserialize with `serde`, merge with `WalkConfig::default()`.
   - If no config file found, use defaults.
3. Implement `WalkConfig::default()`: sensible defaults (14px JetBrains Mono, auto-detected shell, 10000 scrollback, block cursor, bottom input).
4. Implement `WalkConfig::config_dir() -> PathBuf`: `~/.config/walk/` on Unix, `%APPDATA%\Walk\` on Windows.

**DONE WHEN**
- [ ] `WalkConfig::load()` with no config file returns defaults without error.
- [ ] A config file with `font_size = 18` results in `config.font_size == 18.0` with all other fields defaulted.
- [ ] An invalid TOML file produces a meaningful error message.
- [ ] `config_dir()` returns platform-appropriate paths.

---

### Task 42 (A) +config
**blockedBy:** [3, 41]

**PURPOSE** — Keybinding system: maps key combinations to actions with user-overridable defaults, supporting both global and context-specific bindings.

**WHAT TO DO**
1. In `walk-app/src/keybindings.rs`, define `Action` enum with all bindable actions:
   ```rust
   pub enum Action {
       NewTab, CloseTab, NextTab, PrevTab, SwitchToTab(u8),
       SplitVertical, SplitHorizontal, CloseSplit,
       FocusLeft, FocusRight, FocusUp, FocusDown,
       ResizeSplitLeft, ResizeSplitRight, ResizeSplitUp, ResizeSplitDown,
       Copy, Paste, SelectAll,
       ScrollUp, ScrollDown, ScrollPageUp, ScrollPageDown, ScrollToTop, ScrollToBottom,
       BlockPrev, BlockNext, BlockCopy, BlockCollapse, BlockSearch,
       SearchInBlock, SearchGlobal,
       ToggleInputPosition,
       ZoomIn, ZoomOut, ZoomReset,
       ClearScreen,
       SendEof,
   }
   ```
2. Define `KeyCombo { key: KeyAction, modifiers: Modifiers }` and `KeybindingConfig { bindings: HashMap<KeyCombo, Action>, context_bindings: HashMap<Context, HashMap<KeyCombo, Action>> }` where `Context` enum: `Terminal`, `InputEditor`, `BlockSelected`, `SearchActive`.
3. Implement `KeybindingConfig::default() -> Self`: populate with all default keybindings (Cmd/Ctrl+T = NewTab, Cmd/Ctrl+W = CloseTab, etc., adjusting modifier for platform).
4. Implement `KeybindingConfig::resolve(&self, combo: &KeyCombo, context: &Context) -> Option<Action>`: check context bindings first, fall back to global.
5. Implement TOML deserialization:
   ```toml
   [keybindings]
   "ctrl+t" = "new_tab"
   "ctrl+shift+d" = "split_horizontal"
   ```
6. Parse key combo strings: `"ctrl+shift+a"` -> `KeyCombo { key: Char('a'), modifiers: { ctrl: true, shift: true, .. } }`.

**DONE WHEN**
- [ ] Default keybindings include all actions listed in the `Action` enum.
- [ ] `resolve(Ctrl+T, Terminal)` returns `Some(Action::NewTab)`.
- [ ] A user config overriding `"ctrl+t" = "split_vertical"` causes `resolve(Ctrl+T, Terminal)` to return `SplitVertical`.
- [ ] Parsing `"cmd+shift+k"` on macOS produces correct `KeyCombo` with `meta: true, shift: true`.

---

### Task 43 (B) +config
**blockedBy:** [7, 8, 37, 42]

**PURPOSE** — Font zoom: allows runtime font size adjustment with keyboard shortcuts, scaling all text and recomputing the cell grid.

**WHAT TO DO**
1. In `walk-ui/src/zoom.rs`, create `ZoomManager` struct: `{ base_size: f32, current_size: f32, min_size: f32, max_size: f32, step: f32 }`.
2. Implement `ZoomManager::new(base: f32) -> Self`: min 8.0, max 32.0, step 1.0. — WHY min 8.0: below 8px, most fonts become unreadable even on 2x displays; standard minimum for accessibility. WHY max 32.0: at 32px, an 80-col terminal needs ~2560px width, fitting most displays; larger makes the terminal unusable. WHY step 1.0: matches browser zoom behavior (Cmd+/Cmd-); finer steps (0.5) feel unresponsive, coarser (2.0) feels jarring.
3. Implement `zoom_in(&mut self)`: increase `current_size` by `step`, clamp to max.
4. Implement `zoom_out(&mut self)`: decrease by step, clamp to min.
5. Implement `zoom_reset(&mut self)`: reset to `base_size`.
6. When zoom changes: recalculate `FontSystem` metrics, clear glyph atlas, recompute screen dimensions (new rows/cols based on viewport size / new cell size), resize all PTYs.

**DONE WHEN**
- [ ] `zoom_in` from 14.0 produces 15.0.
- [ ] `zoom_in` at 32.0 stays at 32.0.
- [ ] `zoom_reset` from any size returns to the config's `font_size`.
- [ ] After zoom, the terminal grid recalculates: a 800x600 viewport at 16px cell width has 50 cols (not the 80 it had at ~10px).

---

## Phase 10: Prompt Framework Support (+prompt)

### Task 44 (C) +prompt
**blockedBy:** [13, 16, 18]

**PURPOSE** — Detect and support popular prompt frameworks (Starship, Powerlevel10k, Oh-my-Posh) so their styled prompts render correctly in Walk.

**WHAT TO DO**
1. In `walk-terminal/src/prompt.rs`, create `PromptDetector`.
2. Implement `fn detect_prompt_framework(shell: &ShellType) -> Option<PromptFramework>` where `PromptFramework` enum: `Starship`, `P10k`, `OhMyPosh`, `OhMyZsh`, `Spaceship`, `Custom`.
   - Check for `starship` in PATH -> Starship.
   - Check for `POWERLEVEL9K_*` or `P10K_*` env vars or `.p10k.zsh` in home -> P10k.
   - Check for `oh-my-posh` in PATH -> OhMyPosh.
   - Check for `$ZSH` env var pointing to oh-my-zsh -> OhMyZsh.
3. Ensure alacritty_terminal correctly handles the escape sequences these frameworks emit:
   - Starship: standard ANSI + OSC sequences. Handled by alacritty_terminal.
   - P10k: uses `%{...%}` zsh prompt escapes which the shell expands before sending to PTY. Needs correct handling of right-aligned prompt sequences (CSI `...G` to move cursor to column).
   - Oh-my-Posh: similar to Starship, uses ANSI sequences.
4. Implement `fn configure_env_for_prompt(framework: &PromptFramework) -> HashMap<String, String>`: set `TERM=xterm-256color`, `COLORTERM=truecolor` to enable full color support. For Starship, set `STARSHIP_SHELL` if not set.

**DONE WHEN**
- [ ] With Starship installed, the prompt renders with correct colors, icons (if font supports them), and segments.
- [ ] P10k's right-aligned prompt content appears at the correct column (right edge of terminal).
- [ ] Prompt frameworks detect correctly on a system where they're installed.
- [ ] `COLORTERM=truecolor` is set in the PTY environment, enabling 24-bit color prompts.

---

## Phase 11: Clipboard & Selection (+clipboard)

### Task 45 (A) +clipboard
**blockedBy:** [13, 16, 42]

**PURPOSE** — System clipboard integration: enables copy and paste between Walk and other applications on all platforms.

**WHAT TO DO**
1. Add `arboard = "3"` to `walk-ui/Cargo.toml` (cross-platform clipboard crate).
2. In `walk-ui/src/clipboard.rs`, create `ClipboardManager` struct wrapping `arboard::Clipboard`.
3. Implement `ClipboardManager::copy(&mut self, text: &str) -> Result<(), ClipboardError>`: set system clipboard text.
4. Implement `ClipboardManager::paste(&mut self) -> Result<String, ClipboardError>`: get system clipboard text.
5. Integrate with keybindings:
   - `Cmd/Ctrl+C` (when text is selected in viewport): extract selected text from screen cells, call `copy()`.
   - `Cmd/Ctrl+C` (when no text selected): send `\x03` (SIGINT) to PTY.
   - `Cmd/Ctrl+V`: call `paste()`, send result to PTY via `terminal.send_input(text.as_bytes())`. Handle bracketed paste mode: if terminal has requested it (via `\033[?2004h`), wrap pasted text in `\033[200~...\033[201~`.
   - `Cmd/Ctrl+Shift+C`: always copy (even if nothing selected, copy current block output).

**DONE WHEN**
- [ ] Selecting text in the viewport and pressing Cmd+C puts the text on the system clipboard (verified by pasting in another app).
- [ ] Cmd+V pastes clipboard content into the terminal as if typed.
- [ ] Cmd+C with no selection sends SIGINT (verified by interrupting a `sleep 100` command).
- [ ] Bracketed paste mode wraps pasted content correctly when enabled by the shell.

---

### Task 46 (B) +clipboard
**blockedBy:** [13, 34, 45]

**PURPOSE** — Mouse-based text selection: click-and-drag to select text in the terminal viewport, with word and line selection on double/triple click.

**WHAT TO DO**
1. In `walk-ui/src/selection.rs`, create `SelectionManager` struct: `{ state: SelectionState, last_click: Option<(Instant, Point)> }` where `SelectionState` enum: `None`, `Selecting { start: CellPos, end: CellPos }`, `Selected { start: CellPos, end: CellPos }` and `CellPos { row: u16, col: u16 }`.
2. Implement `handle_mouse_down(&mut self, pos: Point, cell_size: (f32, f32)) -> SelectionState`: convert pixel position to cell position. Set `state = Selecting { start, end: start }`. Detect double-click (< 300ms since last click at same position — WHY 300ms: standard double-click threshold used by macOS/Windows/GTK; shorter misses slow clickers, longer triggers false positives) -> select word. Detect triple-click -> select line.
3. Implement `handle_mouse_drag(&mut self, pos: Point, cell_size: (f32, f32))`: update `end` of selection.
4. Implement `handle_mouse_up(&mut self) -> SelectionState`: transition from `Selecting` to `Selected`.
5. Implement `selected_text(&self, grid: &Grid<Cell>, scrollback_len: usize) -> String`: extract text from cells in the selection range, handling line wraps and trimming trailing whitespace per line.
6. If `config.copy_on_select` is true, automatically copy to clipboard on mouse-up.

**DONE WHEN**
- [ ] Click-and-drag selects text; the selected region is visually highlighted in the viewport.
- [ ] Double-click on "hello" selects the entire word.
- [ ] Triple-click selects the entire line.
- [ ] `selected_text` returns the correct string including text that spans multiple lines.
- [ ] Selection across scrollback content works correctly.

---

## Phase 12: Global Search (+search)

### Task 47 (B) +search
**blockedBy:** [13, 34, 42]

**PURPOSE** — Global terminal search: search across all terminal output (scrollback + visible screen) with match highlighting and navigation.

**WHAT TO DO**
1. In `walk-ui/src/search.rs`, create `GlobalSearch` struct: `{ query: String, matches: Vec<GlobalMatch>, current: usize, is_active: bool, search_input: String }` where `GlobalMatch { screen_row: i64 (negative = scrollback), col_start: u16, col_end: u16 }`.
2. Implement `GlobalSearch::search(&mut self, query: &str, grid: &Grid<Cell>, scrollback_len: usize)`: search all scrollback lines and all screen lines for case-insensitive substring matches.
3. Implement `next_match`, `prev_match`: cycle through matches, scroll the viewport to make the current match visible.
4. Implement `highlight_ranges_for_viewport(&self, viewport_start_row: i64, viewport_end_row: i64) -> Vec<(u16, u16, u16, bool)>`: returns `(row, col_start, col_end, is_current)` for matches visible in the current viewport.
5. UI: render a search bar overlay at the top of the viewport when active. Show match count "N of M".
6. Keybinding: `Cmd/Ctrl+F` (when no block selected) activates global search. `Enter` = next, `Shift+Enter` = prev, `Escape` = close.

**DONE WHEN**
- [ ] Searching "error" highlights all occurrences in both scrollback and visible screen.
- [ ] `next_match` scrolls the viewport to center the next match if it's off-screen.
- [ ] Match count displays "3 of 15" correctly.
- [ ] Closing search clears all highlights.

---

## Phase 13: Application Shell & Integration (+app)

### Task 48 (A) +app
**blockedBy:** [2, 6, 7, 8, 29, 31, 32, 33, 34, 37, 41, 42, 45, 47]

**PURPOSE** — Main application struct: wires together all subsystems (platform, renderer, terminals, UI, config) into a running application.

**WHAT TO DO**
1. In `walk-app/src/app.rs`, create `WalkApp` struct:
   ```rust
   pub struct WalkApp {
       config: WalkConfig,
       theme: Theme,
       theme_watcher: ThemeWatcher,
       gpu: GpuContext,
       font_system: FontSystem,
       glyph_atlas: GlyphAtlas,
       tab_manager: TabManager,
       split_manager: SplitManager,
       input_editor: InputEditor,
       clipboard: ClipboardManager,
       selection: SelectionManager,
       global_search: GlobalSearch,
       zoom: ZoomManager,
       layout: LayoutNode,
       frame_clock: FrameClock,
       keybindings: KeybindingConfig,
   }
   ```
2. Implement `WalkApp::new(config: WalkConfig) -> Result<Self, AppError>`: initialize all subsystems in dependency order. Create default tab with detected shell.
3. Implement `AppHandler` for `WalkApp`:
   - `on_redraw()`: process PTY output for all terminals, poll theme watcher, compute layout, render all UI components via wgpu.
   - `on_resize(size)`: recompute layout, resize terminals, reconfigure wgpu surface.
   - `on_key_event(event)`: resolve keybinding, dispatch action (or forward to input editor / PTY).
   - `on_mouse_event(event)`: dispatch to tab bar, split dividers, viewport selection, or input editor based on hit testing.
   - `on_focus_change(focused)`: pause/resume cursor blink.
   - `on_close_requested()`: if `confirm_close_with_running_process` and any terminal has running child processes, show confirmation (for now, just close).
4. Implement the action dispatch in `handle_action(&mut self, action: Action)` with match arms for every `Action` variant.

**DONE WHEN**
- [ ] `WalkApp::new(default_config)` creates a running app with one tab, one terminal, and a visible prompt.
- [ ] Typing produces visible characters in the terminal.
- [ ] All keybindings dispatch to their correct actions.
- [ ] Resizing recomputes layout and resizes PTY.

---

### Task 49 (A) +app
**blockedBy:** [48]

**PURPOSE** — Main entry point: the `fn main()` that ties everything together and starts the application.

**WHAT TO DO**
1. In `walk-app/src/main.rs` (the root crate):
   ```rust
   fn main() -> Result<(), Box<dyn Error>> {
       let config = WalkConfig::load();
       let window_config = WindowConfig { title: "Walk", width: 1200, height: 800 };
       let window = WalkWindow::new(&window_config)?;
       let gpu = GpuContext::new(&window)?;
       let mut app = WalkApp::new(config, gpu)?;
       run_event_loop(window, app);
   }
   ```
   — WHY 1200x800 default window size: fits 80 columns at 14px font with room for UI chrome; 80 cols is the POSIX standard terminal width, and 800px height shows ~40 rows which covers most interactive programs.
2. Handle CLI arguments: `--config <path>` to override config file, `--shell <shell>` to override default shell, `--title <title>` for window title, `--working-dir <path>` for initial CWD.
3. Use `clap = "4"` for argument parsing.
4. Set up panic handler: on panic, attempt to restore terminal state (raw mode cleanup) before printing the panic message.
5. Set up logging: use `tracing = "0.1"` with `tracing-subscriber` for structured logging. Default level: `warn` in release, `debug` in debug builds. Log to `~/.config/walk/walk.log`.

**DONE WHEN**
- [ ] `cargo run` launches Walk with a functional terminal.
- [ ] `cargo run -- --shell /bin/bash` opens with bash regardless of the user's default shell.
- [ ] `cargo run -- --working-dir /tmp` starts with CWD `/tmp`.
- [ ] A panic in any subsystem prints a useful backtrace and doesn't leave the terminal in a broken state.

---

## Phase 14: Lua Scripting (+scripting)

### Task 50 (B) +scripting
**blockedBy:** [41, 48]

**PURPOSE** — Enables user-extensible configuration and scripting, following the WezTerm/Neovim pattern.

**WHAT TO DO**
1. Add `mlua` crate with `lua54` and `serialize` features to `walk-app/Cargo.toml`. — WHY Lua 5.4: latest stable Lua version; 5.4 adds integers (useful for exit codes, line numbers) and generational GC (lower latency for interactive use). WHY mlua: safe Rust bindings, async support, serde integration; rlua is unmaintained, hlua lacks features.
2. Create `walk-app/src/scripting/mod.rs` with `LuaRuntime` struct wrapping `mlua::Lua`.
3. Initialize Lua VM on app startup, loading user config from `~/.config/walk/init.lua`.
4. Register a `walk` global table exposing: `walk.config`, `walk.keybindings`, `walk.theme`, `walk.on(event, callback)`.
5. Implement `reload_config()` that re-executes `init.lua` without restarting the app.

**DONE WHEN**
- [ ] Lua VM initializes on startup and loads `init.lua` if present.
- [ ] `walk.config` table is readable from Lua.
- [ ] Errors in `init.lua` are caught and displayed in status bar, not crashes.

---

### Task 51 (B) +scripting
**blockedBy:** [42, 50]

**PURPOSE** — Lets users define custom keybindings and commands in Lua.

**WHAT TO DO**
1. In Lua, expose `walk.keymap(mode, key, action)` where mode is `"normal"|"input"|"search"`.
2. `action` can be a string (built-in command name) or a Lua function.
3. Built-in commands: `"split_horizontal"`, `"split_vertical"`, `"close_pane"`, `"next_tab"`, `"prev_tab"`, `"new_tab"`, `"toggle_search"`, `"copy_block"`, `"scroll_up"`, `"scroll_down"`.
4. Example: `walk.keymap("normal", "ctrl+shift+t", "new_tab")`
5. Example with Lua function: `walk.keymap("normal", "ctrl+shift+e", function() walk.exec("echo hello") end)`

**DONE WHEN**
- [ ] User-defined keybindings in `init.lua` override defaults.
- [ ] Lua function callbacks execute correctly.
- [ ] Invalid keybindings produce clear error messages.

---

### Task 52 (B) +scripting
**blockedBy:** [37, 38, 50]

**PURPOSE** — Lets users define and switch themes programmatically.

**WHAT TO DO**
1. Expose `walk.theme.set(theme_table)` where `theme_table` has: `background`, `foreground`, `cursor`, `selection`, `ansi_colors` (16), and `ui_colors` (`tab_bar`, `status_bar`, `border`).
2. Expose `walk.theme.load(name)` to load a named theme from `~/.config/walk/themes/`.
3. Theme changes apply immediately (hot-reload).

**DONE WHEN**
- [ ] `walk.theme.set({background = "#1e1e2e"})` changes the background immediately.
- [ ] `walk.theme.load("catppuccin")` loads and applies a theme file.

---

### Task 53 (C) +scripting
**blockedBy:** [50]

**PURPOSE** — Lets users run Lua code on terminal events (new tab, command finished, directory changed).

**WHAT TO DO**
1. Expose `walk.on(event, callback)` for events: `"tab_created"`, `"tab_closed"`, `"command_finished"`, `"directory_changed"`, `"block_created"`.
2. Callback receives an event table with context (e.g., `{exit_code = 0, duration_ms = 1234}` for `command_finished`).
3. Example: `walk.on("command_finished", function(e) if e.exit_code ~= 0 then walk.notify("Command failed!") end end)`

**DONE WHEN**
- [ ] All listed events fire correctly.
- [ ] Callbacks can access event context data.

---

## Phase 15: Cross-Platform Packaging & CI (+build)

### Task 54 (B) +build
**blockedBy:** [49]

**PURPOSE** — Ensures cross-platform builds work via CI matrix.

**WHAT TO DO**
1. Create `.github/workflows/ci.yml` with matrix: macOS ARM64, macOS x86_64, Linux X11, Linux Wayland, Windows.
2. Build with `cargo build --release` on each target.
3. Run `cargo clippy --all-targets -- -D warnings` and `cargo test --workspace` on each target.
4. Add `cargo fmt --check` to CI.

**DONE WHEN**
- [ ] CI builds pass on all 5 targets.
- [ ] `cargo clippy` and `cargo fmt --check` pass with zero warnings/errors.
- [ ] `cargo test --workspace` passes on all platforms.

---

### Task 55 (C) +build
**blockedBy:** [49]

**PURPOSE** — macOS application bundle: packages Walk as a `.app` bundle with an icon, Info.plist, and code signing support.

**WHAT TO DO**
1. Create `packaging/macos/` directory.
2. Create `Info.plist` with: `CFBundleName: Walk`, `CFBundleIdentifier: dev.walk.terminal`, `CFBundleVersion: 0.1.0`, `CFBundleExecutable: walk`, `CFBundleIconFile: walk.icns`, `LSMinimumSystemVersion: 10.15`, `NSHighResolutionCapable: true`.
3. Create a build script `packaging/macos/bundle.sh` that: runs `cargo build --release`, creates `Walk.app/Contents/MacOS/walk`, copies binary, copies `Info.plist` to `Contents/`, copies `walk.icns` to `Contents/Resources/`.
4. Create a placeholder `walk.icns` (can be generated from a PNG using `iconutil`).
5. Add a Makefile target: `make bundle-macos`.

**DONE WHEN**
- [ ] `make bundle-macos` produces `Walk.app` that launches by double-clicking on macOS.
- [ ] The app icon appears in the Dock and in Finder.
- [ ] `Info.plist` values are correct when inspected with `plutil`.

---

### Task 56 (C) +build
**blockedBy:** [49]

**PURPOSE** — Linux packaging: produces `.deb` and `.AppImage` packages.

**WHAT TO DO**
1. Create `packaging/linux/` directory.
2. Create `walk.desktop` file: `[Desktop Entry]`, `Name=Walk`, `Exec=walk`, `Icon=walk`, `Type=Application`, `Categories=System;TerminalEmulator;`.
3. For `.deb`: create `packaging/linux/build_deb.sh` using `cargo-deb` or manual `dpkg-deb`. Include: binary at `/usr/bin/walk`, desktop file at `/usr/share/applications/walk.desktop`, icon at `/usr/share/icons/hicolor/256x256/apps/walk.png`, man page stub at `/usr/share/man/man1/walk.1.gz`.
4. For AppImage: create `packaging/linux/build_appimage.sh` using `linuxdeploy` with the AppDir structure: `AppDir/usr/bin/walk`, `AppDir/usr/share/applications/walk.desktop`, `AppDir/walk.png`.
5. Add Makefile targets: `make deb`, `make appimage`.

**DONE WHEN**
- [ ] `make deb` produces a `.deb` file that installs with `dpkg -i` and `walk` is available in PATH.
- [ ] `make appimage` produces a `.AppImage` that runs on a fresh Ubuntu system.
- [ ] `walk.desktop` causes Walk to appear in the application launcher.

---

### Task 57 (C) +build
**blockedBy:** [49]

**PURPOSE** — Windows packaging: produces an installer and ensures WSL integration works.

**WHAT TO DO**
1. Create `packaging/windows/` directory.
2. Create a WiX-based or Inno Setup installer script (`walk_installer.iss` or `walk.wxs`) that: installs `walk.exe` to `%PROGRAMFILES%\Walk\`, adds to PATH, creates Start Menu shortcut, registers as a terminal emulator.
3. Create `build_windows.ps1` script: runs `cargo build --release --target x86_64-pc-windows-msvc`, then invokes the installer compiler.
4. For `winget` manifest: create `packaging/windows/winget/Walk.Walk.yaml` with installer metadata.
5. Add Makefile target: `make installer-windows` (runs via PowerShell or cross-compilation).

**DONE WHEN**
- [ ] The installer installs Walk and it's accessible from the Start Menu.
- [ ] `walk.exe` is in PATH after installation.
- [ ] Uninstaller cleanly removes all files.

---

### Task 58 (C) +build
**blockedBy:** [54]

**PURPOSE** — Release CI: automated packaging on all three platforms on tag push.

**WHAT TO DO**
1. Create `.github/workflows/release.yml`: on tag push (`v*`), build all platform packages and create a GitHub Release with attached binaries.
2. Matrix: macOS `.app` bundle, Linux `.deb` + `.AppImage`, Windows installer.
3. Upload all artifacts to the GitHub Release.
4. Add basic integration test in `tests/integration/`: spawn Walk in headless mode (no window), send input to PTY, verify output.

**DONE WHEN**
- [ ] Pushing a `v0.1.0` tag creates a GitHub Release with macOS `.app`, Linux `.deb` + `.AppImage`, and Windows installer attached.
- [ ] Integration tests pass on all platforms.

---

## Phase 16: Testing (+testing)

### Task 59 (A) +testing
**blockedBy:** [25, 26]

**PURPOSE** — Validates the core input editor data structure (gap buffer) and cursor movement logic with comprehensive unit tests, catching regressions in the most interacted-with component.

**WHAT TO DO**
1. Create `walk-input/tests/buffer_tests.rs` with unit tests for all `InputBuffer` operations:
   - Insert at start, middle, end of buffer.
   - Delete single char, range, at buffer boundaries.
   - Gap movement: insert at position 0, then position 100 (verify gap relocates correctly).
   - Multi-cursor insert/delete: 2 cursors, 5 cursors, cursors at same position.
   - Selection: set anchor, extend, clear, select all.
   - Undo/redo stack if implemented.
2. Create `walk-input/tests/cursor_tests.rs` with unit tests for all cursor movement operations:
   - `move_left`/`move_right` at buffer start/end (boundary conditions).
   - `move_word_left`/`move_word_right` with punctuation, mixed case, Unicode.
   - `move_line_start` smart home toggle behavior.
   - `move_up`/`move_down` with lines of different lengths (column clamping).
   - Selection extension with `extend_selection: true`.
3. Use `#[test]` and `assert_eq!` for all tests. Target: 100% branch coverage of `buffer.rs` and `cursor_ops.rs`.

**DONE WHEN**
- [ ] `cargo test -p walk-input` passes with all tests green.
- [ ] Edge cases covered: empty buffer operations, single-char buffer, buffer with only newlines.
- [ ] Multi-cursor tests verify all cursors update correctly after each operation.

---

### Task 60 (A) +testing
**blockedBy:** [20, 21]

**PURPOSE** — Validates block detection logic by feeding mock PTY output containing OSC 133 markers and verifying that BlockManager correctly creates and finalizes blocks.

**WHAT TO DO**
1. Create `walk-blocks/tests/block_detection_tests.rs`.
2. Build helper `fn mock_semantic_events(sequence: &[(SemanticEvent, &str)]) -> (Vec<SemanticEvent>, MockGrid)` that produces a sequence of semantic events and a mock grid with the given text at each line.
3. Test scenarios:
   - Single command: PromptStart -> CommandStart -> OutputStart -> CommandEnd. Verify one block with correct fields.
   - Multiple sequential commands: verify block count, ordering, and individual exit codes.
   - Failed command (exit code 1): verify `exit_code == Some(1)`.
   - Interrupted command (no CommandEnd received): verify block remains in `InOutput` state.
   - Empty command (Enter on empty prompt): verify no block is created or a zero-output block is handled gracefully.
   - Rapid commands: 100 commands in sequence, verify all 100 blocks exist with correct indices.
4. Test `BlockManager::visible_blocks()` with various viewport positions.

**DONE WHEN**
- [ ] `cargo test -p walk-blocks` passes with all tests green.
- [ ] All 6+ scenarios produce correct block states.
- [ ] No panics on malformed event sequences (e.g., CommandEnd before CommandStart).

---

### Task 61 (B) +testing
**blockedBy:** [13, 15, 16]

**PURPOSE** — Validates the full PTY-to-terminal pipeline as an integration test, ensuring bytes flow correctly from a real shell process through alacritty_terminal to the screen grid.

**WHAT TO DO**
1. Create `walk-terminal/tests/pty_integration.rs`.
2. Spawn a real PTY with `/bin/sh` (POSIX shell for portability).
3. Send `echo "WALK_TEST_MARKER"\n` to PTY.
4. Poll `Terminal::process_pty_output()` in a loop (with timeout of 5 seconds — WHY 5 seconds: covers slow CI machines and shell startup time; typical response is <100ms, but 5s prevents flaky failures).
5. Scan the terminal grid for "WALK_TEST_MARKER" text.
6. Test resize: resize PTY to 40x10 (WHY 40x10: intentionally small to test wrapping behavior; 80x24 is the default and might mask bugs), send a long line, verify it wraps at column 40.
7. Test shell exit: send `exit 0\n`, verify `PtyEvent::Exited(0)` is received.

**DONE WHEN**
- [ ] Integration test passes on Linux and macOS (skip on Windows CI if `/bin/sh` unavailable).
- [ ] "WALK_TEST_MARKER" is found in the terminal grid.
- [ ] Resize and exit scenarios pass.

---

### Task 62 (B) +testing
**blockedBy:** [9, 12, 34]

**PURPOSE** — Validates visual rendering output via snapshot testing, catching rendering regressions by comparing frame buffer output against reference screenshots.

**WHAT TO DO**
1. Create `walk-renderer/tests/snapshot_tests.rs`.
2. Set up a headless wgpu rendering context (using `wgpu::Backends::GL` or software rasterizer for CI compatibility). — WHY software rasterizer: CI runners often lack GPUs; wgpu's GL backend with Mesa llvmpipe renders identically to hardware for 2D text.
3. Implement `fn render_to_image(grid: &MockGrid, theme: &Theme, font: &FontSystem) -> RgbaImage`:
   - Create a mock terminal grid with predefined content (e.g., "Hello World" in white on black, colored ANSI text, cursor at specific position).
   - Run the full render pipeline (text layout -> glyph atlas -> render pipeline -> compositor).
   - Read back the frame buffer pixels into an `image::RgbaImage`.
4. Compare against reference images stored in `walk-renderer/tests/snapshots/` using pixel-diff with a tolerance of 2% (WHY 2%: accounts for sub-pixel rendering differences across platforms/font engines while catching visible regressions like wrong colors or missing glyphs).
5. Test scenarios: plain text, colored text (ANSI 16 + 256 + truecolor), bold/italic/underline, cursor shapes (block, bar, underline), selection highlight.

**DONE WHEN**
- [ ] `cargo test -p walk-renderer` passes with snapshot comparisons.
- [ ] Reference snapshots are committed in the repo and reviewed.
- [ ] Tolerance catches intentional changes (update snapshots with `UPDATE_SNAPSHOTS=1 cargo test`).

---

## Phase 17: CI/CD (+ci)

### Task 63 (B) +ci
**blockedBy:** [54]

**PURPOSE** — Ensures every pull request passes quality gates before merge, catching regressions early with automated checks.

**WHAT TO DO**
1. Create `.github/workflows/pr-checks.yml` triggered on `pull_request` events targeting `main`.
2. Steps:
   - `cargo fmt --check` — fail if code is not formatted.
   - `cargo clippy --all-targets --all-features -- -D warnings` — fail on any lint warning.
   - `cargo test --workspace` — run all unit and integration tests.
   - `cargo doc --no-deps --workspace` — verify docs build without errors.
3. Add status check requirement: configure branch protection on `main` to require `pr-checks` to pass.
4. Cache `~/.cargo/registry` and `target/` directories for faster CI runs.

**DONE WHEN**
- [ ] Opening a PR triggers the checks workflow.
- [ ] A PR with `cargo fmt` violations fails the check.
- [ ] A PR with all tests passing shows green checks.

---

### Task 64 (C) +ci
**blockedBy:** [58]

**PURPOSE** — Automated release workflow that builds platform binaries and publishes GitHub Releases with assets on version tags.

**WHAT TO DO**
1. Extend `.github/workflows/release.yml` (from Task 58) to:
   - Build on matrix: macOS ARM64 (`aarch64-apple-darwin`), macOS x86_64 (`x86_64-apple-darwin`), Linux (`x86_64-unknown-linux-gnu`), Windows (`x86_64-pc-windows-msvc`).
   - For each target: `cargo build --release --target <triple>`, then compress binary into `.tar.gz` (Unix) or `.zip` (Windows).
   - Create GitHub Release using `softprops/action-gh-release` with all compressed binaries as assets.
   - Generate changelog from commit messages since last tag.
2. Name assets consistently: `walk-<version>-<os>-<arch>.<ext>` (e.g., `walk-v0.1.0-linux-x86_64.tar.gz`).
3. Add SHA256 checksums file as a release asset.

**DONE WHEN**
- [ ] Pushing tag `v0.1.0` produces a GitHub Release with 4 binary assets + checksums.
- [ ] Each binary runs on its target platform.
- [ ] Changelog is populated with commit summaries.

---

### Task 65 (C) +ci
**blockedBy:** [63]

**PURPOSE** — Dependency security auditing and supply-chain checks on every CI run.

**WHAT TO DO**
1. Add `cargo-audit` step to PR checks workflow: `cargo audit` to check for known vulnerabilities in dependencies.
2. Add `cargo-deny` check: create `deny.toml` with rules for license compatibility (allow MIT, Apache-2.0, BSD; deny GPL for library deps), duplicate dependency detection, and advisory database checks.
3. Run `cargo deny check` in CI.
4. Schedule a weekly cron job to run `cargo audit` independently, opening an issue if new advisories are found.

**DONE WHEN**
- [ ] `cargo audit` runs on every PR and fails if vulnerabilities are found.
- [ ] `cargo deny check` passes with the configured license and advisory rules.
- [ ] Weekly audit cron job is configured and runs.

---

## Phase 18: Documentation (+docs)

### Task 66 (C) +docs
**blockedBy:** [49, 50]

**PURPOSE** — Provides a comprehensive README and user-facing documentation so new users can install, configure, and use Walk effectively.

**WHAT TO DO**
1. Create `README.md` with sections:
   - Hero section: project name, one-line description, screenshot.
   - Feature list: Blocks, GPU rendering, input editor, tabs/splits, theming, Lua scripting, cross-platform.
   - Installation: Homebrew (macOS), `cargo install walk-terminal`, AppImage (Linux), winget (Windows), build from source.
   - Quick start: first launch, basic keybindings table.
   - Configuration: config file location, full annotated example `config.toml`.
   - Keybinding reference: table of all default keybindings organized by category (tabs, splits, blocks, navigation, clipboard, zoom).
   - Theming: how to create a theme, link to theme gallery.
   - Shell integration: supported shells, how to verify integration is working.
   - Troubleshooting: common issues (GPU not detected, shell integration not loading, font rendering issues).
2. Add screenshots to `docs/screenshots/` directory (placeholder `.gitkeep` until screenshots are available).
3. Create `docs/CONFIGURATION.md` with full reference of every config option, type, default value, and description.

**DONE WHEN**
- [ ] `README.md` covers all listed sections.
- [ ] Keybinding reference table includes every action from the `Action` enum.
- [ ] Configuration reference documents every field in `WalkConfig` and `Theme`.

---

### Task 67 (C) +docs
**blockedBy:** [50, 51, 52, 53]

**PURPOSE** — Provides a Lua scripting guide so users can extend Walk with custom keybindings, themes, and event hooks.

**WHAT TO DO**
1. Create `docs/LUA_SCRIPTING.md` with sections:
   - Overview: what Lua scripting enables, where `init.lua` lives, how to reload.
   - API reference: document every function in the `walk` global table:
     - `walk.config` — reading and setting config values.
     - `walk.keymap(mode, key, action)` — full keybinding API with mode explanations.
     - `walk.theme.set(table)` — theme table schema with all fields.
     - `walk.theme.load(name)` — loading named themes.
     - `walk.on(event, callback)` — all events and their context tables.
     - `walk.exec(command)` — running shell commands.
     - `walk.notify(message)` — displaying status bar messages.
   - Examples section with complete, copy-pasteable snippets:
     - Custom keybinding for opening a specific directory.
     - Catppuccin theme definition in Lua.
     - Notification on failed commands.
     - Auto-switching theme based on macOS dark mode.
     - Custom status bar segment via event hooks.
2. Create `docs/examples/` directory with example `init.lua` files:
   - `minimal.lua` — basic keybinding overrides.
   - `full.lua` — comprehensive config with theme, keybindings, and event hooks.

**DONE WHEN**
- [ ] `LUA_SCRIPTING.md` documents every Lua API function with type signatures and examples.
- [ ] Example `init.lua` files are syntactically valid Lua.
- [ ] A user can follow the guide to create a working `init.lua` from scratch.

---

## Phase 19: Polish & Edge Cases (+polish)

### Task 68 (C) +polish
**blockedBy:** [13]

**PURPOSE** — Terminal bell handling: responds to BEL character (0x07) with visual or audible feedback.

**WHAT TO DO**
1. In `walk-ui/src/bell.rs`, implement `BellHandler` with config option: `BellStyle { Visual, Audible, None }`.
2. Visual bell: briefly flash the terminal background (invert for 100ms — WHY 100ms: long enough to be noticeable, short enough not to be annoying; matches iTerm2/Alacritty visual bell duration, then revert).
3. Audible bell: use platform audio API to play the system alert sound. On macOS: `NSBeep()`. On Linux: use `XBell()` or write `\x07` to system speaker. On Windows: `MessageBeep(MB_OK)`.
4. Wire into alacritty_terminal's `EventListener`: when a bell event fires, trigger the bell handler.

**DONE WHEN**
- [ ] `echo -e "\a"` in the terminal triggers a visual flash (with `bell_style = Visual`).
- [ ] Bell respects the config setting: `None` produces no effect.

---

### Task 69 (C) +polish
**blockedBy:** [13, 34]

**PURPOSE** — URL detection and clickable links: detect URLs in terminal output and make them clickable to open in the default browser.

**WHAT TO DO**
1. In `walk-ui/src/links.rs`, implement `fn detect_urls(line_text: &str) -> Vec<UrlSpan>` where `UrlSpan { col_start: u16, col_end: u16, url: String }`.
2. Use a regex pattern matching `https?://[^\s<>"{}|\\^[\]` to find URLs in the text content of cells.
3. Render detected URLs with underline decoration and a distinct color (from theme).
4. On `Cmd/Ctrl+Click` on a URL: open in default browser using `open` (macOS), `xdg-open` (Linux), or `start` (Windows) via `std::process::Command`.
5. On hover over a URL, change cursor to pointer (if windowing system supports it) and show a tooltip with the full URL.

**DONE WHEN**
- [ ] `echo "visit https://example.com today"` renders the URL underlined in a distinct color.
- [ ] Cmd+Click on the URL opens `https://example.com` in the default browser.
- [ ] URLs with paths, query strings, and fragments are correctly detected: `https://example.com/path?q=1#section`.
- [ ] Non-URLs like `http://` alone or broken URLs are not detected.

---

### Task 70 (C) +polish
**blockedBy:** [13, 20]

**PURPOSE** — Window title tracking: updates the native window title based on OSC 0/2 sequences from the shell (showing the running command or CWD).

**WHAT TO DO**
1. In alacritty_terminal's `EventListener` implementation, detect title change events (OSC 0 and OSC 2).
2. When received, emit a `SemanticEvent::TitleChanged(String)`.
3. In the app handler, update `WalkWindow::set_title(title)` (via `winit::window::Window::set_title`).
4. Also update the corresponding tab title in `TabManager`.

**DONE WHEN**
- [ ] Running `printf '\033]0;My Custom Title\007'` changes the window title to "My Custom Title".
- [ ] The tab title also updates.
- [ ] Starting `vim` updates the title to reflect vim's title-setting sequence.

---

### Task 71 (C) +polish
**blockedBy:** [13, 16]

**PURPOSE** — Mouse reporting: forwards mouse events to the PTY when the shell/application requests mouse tracking (for vim, tmux, etc.).

**WHAT TO DO**
1. Track which mouse modes are active via alacritty_terminal's mode flags:
   - `\033[?1000h` (X11 mouse tracking), `\033[?1002h` (button event tracking), `\033[?1003h` (any event tracking), `\033[?1006h` (SGR extended mode).
2. When mouse events occur in the viewport and mouse reporting is enabled:
   - Encode mouse button + position in the requested format (X10, normal, SGR extended).
   - Send the encoded bytes to PTY via `terminal.send_input()`.
   - SGR format: `\033[<button;col;rowM` (press) or `\033[<button;col;rowm` (release).
3. When mouse reporting is active, disable Walk's own selection (the application handles its own mouse input).

**DONE WHEN**
- [ ] Opening `vim` in Walk and clicking positions the vim cursor at the clicked cell.
- [ ] `tmux` mouse support works: clicking panes switches focus, scrolling works.
- [ ] When mouse reporting is disabled (exiting vim), Walk's selection behavior resumes.

---

### Task 72 (C) +polish
**blockedBy:** [6, 9, 13]

**PURPOSE** — Sixel / image protocol support (basic): renders inline images in the terminal for tools that output them.

**WHAT TO DO**
1. Detect Sixel data sequences (DCS `q` for sixel graphics) and the iTerm2/Kitty image protocols (OSC 1337 for iTerm2, APC for Kitty) via alacritty_terminal events or custom parsing on the PTY byte stream.
2. For basic Sixel support: parse the Sixel data into an RGBA pixel buffer. Create a wgpu texture from it. Render the texture inline at the cursor position, spanning the appropriate number of cell rows/columns.
3. Store inline images in a `Vec<InlineImage>` associated with the terminal: `InlineImage { texture: wgpu::Texture, row: u16, col: u16, width_cells: u16, height_cells: u16 }`.
4. Render inline images in the viewport renderer after drawing text.
5. Start with Sixel only; iTerm2/Kitty protocols can be added later.

**DONE WHEN**
- [ ] A tool that outputs Sixel graphics (e.g., `img2sixel image.png` from `libsixel`) displays the image inline in the terminal.
- [ ] The image occupies the correct number of cell rows and columns.
- [ ] Scrolling past the image works correctly (image scrolls with text).

---

### Task 73 (C) +polish
**blockedBy:** [32, 33, 41]

**PURPOSE** — Session persistence: save and restore terminal sessions (scrollback content, working directory, tab layout) across app restarts.

**WHAT TO DO**
1. In `walk-app/src/session.rs`, define `SessionState`:
   ```rust
   pub struct SessionState {
       pub tabs: Vec<TabState>,
       pub split_tree: SplitNodeState,
       pub active_tab: usize,
       pub window_size: (u32, u32),
       pub window_position: (i32, i32),
   }
   pub struct TabState {
       pub cwd: PathBuf,
       pub shell: ShellType,
       pub scrollback_text: String,
       pub title: String,
   }
   ```
2. Implement `fn save_session(app: &WalkApp) -> Result<(), SessionError>`: serialize `SessionState` to JSON, write to `~/.config/walk/session.json`.
3. Implement `fn load_session(path: &Path) -> Result<SessionState, SessionError>`.
4. On app close: save session. On app start: if session file exists, offer to restore (or auto-restore based on config `restore_session: bool`).
5. Restoring: create tabs with saved shell and CWD, populate scrollback (as plain text -- no styles preserved), restore split layout.

**DONE WHEN**
- [ ] Closing Walk with 3 tabs and reopening restores 3 tabs with the correct CWDs.
- [ ] Split pane layout is restored.
- [ ] Scrollback text from the previous session is visible (even without original styling).
- [ ] `restore_session = false` in config prevents auto-restore.
