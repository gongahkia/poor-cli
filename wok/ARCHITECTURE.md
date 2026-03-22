# Walk Architecture

Walk is a 6-crate Rust workspace implementing a GPU-accelerated terminal emulator. This document describes the dependency graph, data flow, threading model, rendering pipeline, key abstractions, and module organization.

---

## Crate Dependency Graph

```
                       walk-app
                    /     |     \
                   /      |      \
             walk-ui   walk-blocks  walk-input
               |  \       |            |
               |   \      |            |
        walk-renderer  walk-terminal --+
               |           |
               +-----+-----+
                     |
              (external crates only)
```

Precise dependencies:

| Crate | Workspace Dependencies | Key External Dependencies |
|---|---|---|
| `walk-app` | walk-ui, walk-blocks, walk-input, walk-renderer, walk-terminal | winit, clap, tracing-subscriber, mlua |
| `walk-ui` | walk-renderer, walk-terminal, walk-blocks | arboard, notify, toml, serde, image |
| `walk-blocks` | walk-terminal | (none beyond std) |
| `walk-input` | walk-terminal | unicode-width |
| `walk-renderer` | (none) | wgpu, cosmic-text |
| `walk-terminal` | (none) | alacritty_terminal, portable-pty, crossbeam-channel |

`walk-renderer` and `walk-terminal` are **leaf crates** with no workspace-internal dependencies. They can be developed and tested independently.

---

## Data Flow Pipeline

```
User Input (keyboard)
       |
       v
  walk-app (winit event loop)
       |
       +---> Keybinding resolution -----> Action dispatch
       |                                     |
       +---> walk-input (InputEditor)        |
       |         |                           |
       |    EditorAction::Submit(cmd)        |
       |         |                           |
       +-------- + --------------------------+
       |
       v
  PTY write (bytes to shell)
       |
       v
  Shell Process (bash/zsh/fish/powershell)
       |
       v
  PTY read (bytes from shell — reader thread)
       |
       v
  crossbeam channel: PtyEvent::Data(bytes)
       |
       v
  walk-terminal: Terminal::process_pty_output()
       |
       +---> alacritty_terminal::Term::advance(bytes)
       |         |
       |         v
       |     Grid<Cell> updated (screen state)
       |
       +---> SemanticEvent detection (OSC 133 markers)
       |         |
       |         v
       |     walk-blocks: BlockManager::handle_event()
       |         |
       |         v
       |     Block records created/finalized
       |
       v
  walk-ui: ViewportRenderer::render()
       |
       +---> walk-renderer: text_layout + glyph_atlas + render_pipeline
       |
       v
  wgpu surface presentation ---> Screen
```

### Transition Details

1. **Keyboard to PTY**: User keystrokes arrive via winit. `walk-app` resolves keybindings first. If no binding matches, the keystroke goes to `walk-input`'s `InputEditor`. On Enter, the editor emits `EditorAction::Submit(command_text)`, written to the PTY.

2. **PTY to Terminal State**: A dedicated reader thread reads bytes from the PTY master and sends them through a `crossbeam_channel::bounded(256)`. The main thread calls `Terminal::process_pty_output()` each frame, draining up to 64 channel messages. Each message's bytes are fed to `alacritty_terminal::Term::advance()`, updating the internal `Grid<Cell>`.

3. **Terminal State to Blocks**: During PTY processing, OSC 133 sequences are detected via the `EventListener` trait. These become `SemanticEvent` values. `BlockManager::handle_event()` processes them through a state machine to build `Block` records.

4. **Terminal State to Screen**: Each frame, `ViewportRenderer` reads the `Grid<Cell>`, calls `walk-renderer`'s text layout to produce `GlyphRun`s, looks up each glyph in the `GlyphAtlas`, builds a vertex buffer of textured quads, and submits a single draw call to wgpu.

---

## Threading Model

```
+-------------------+     crossbeam channel       +------------------+
|  PTY Reader       | ---- PtyEvent::Data ------> |                  |
|  Thread (per tab) |     bounded(256)            |  Main Thread     |
+-------------------+                             |  (winit event    |
                                                  |   loop)          |
+-------------------+     notify channel          |                  |
|  File Watcher     | ---- theme changed -------> |  - process PTY   |
|  Thread (notify)  |                             |  - update state  |
+-------------------+                             |  - compute layout|
                                                  |  - render (wgpu) |
                                                  |  - present frame |
                                                  +------------------+
```

### Rules

- The **main thread** owns all mutable state: terminals, blocks, UI, renderer.
- **Background threads** are readers only — they push events into channels.
- No `Arc<Mutex<>>` on hot paths. The PTY writer is `Arc<Mutex<PtyWriter>>` because writes come from the main thread at any time, but reads are always on the dedicated thread.
- **One reader thread per terminal/tab**. When a tab is closed, its reader thread terminates naturally (channel drops).
- **No async runtime**. Concurrency is handled entirely through `std::thread` + `crossbeam_channel`.

---

## Rendering Pipeline Stages

Each frame follows these stages in order:

| Stage | Description |
|---|---|
| 1. Frame Begin | `GpuContext::begin_frame()` acquires a `SurfaceTexture` |
| 2. Layout | `walk-ui` computes `LayoutResult` — rects for tab bar, viewport, input editor, status bar |
| 3. Background | Background image as full-viewport textured quad, or clear with `theme.background` |
| 4. Cell Backgrounds | For each visible cell with non-default bg, emit a colored quad |
| 5. Text Layout | Look up glyphs in `GlyphAtlas` (rasterize via cosmic-text SwashCache if missing), produce `PositionedGlyph` with atlas UV coords and screen position |
| 6. Text Rendering | All glyph quads batched into single vertex buffer. Single draw call with atlas texture. Vertex format: `(x, y, u, v, fg_rgba, bg_rgba)` |
| 7. Decorations | Underline, strikethrough, cursor (block/bar/underline shapes as thin rects) |
| 8. Block Decorations | Left-side color bars (green = exit 0, red = nonzero), separator lines between blocks |
| 9. Overlays | Selection highlights (semi-transparent blue), search match highlights, UI overlays (search bar) |
| 10. UI Chrome | Tab bar, status bar, input editor — each rendered into their layout rect |
| 11. Frame Present | `GpuContext::present(frame)` submits the surface texture |

### Damage Tracking

After the initial working render: implement `DirtyRegion` (one bit per row). Only rebuild vertex buffers for dirty rows. Scrollback position change marks everything dirty. Typing a single character should not cause a full-grid re-render.

---

## Key Abstractions and Interfaces Between Crates

### walk-app → walk-terminal

```rust
pub struct Terminal {
    // Main interface
    pub fn process_pty_output(&mut self);            // Drain PTY channel, feed to Term
    pub fn send_input(&self, data: &[u8]);           // Write to PTY
    pub fn resize(&mut self, rows: u16, cols: u16);  // Resize PTY + Term
    pub fn is_dirty(&self) -> bool;                  // New output since last render?
    pub fn mark_clean(&mut self);                    // Reset dirty flag
    pub fn grid(&self) -> &Grid<Cell>;               // Current screen state
    pub fn cursor(&self) -> CursorPosition;          // Cursor location
    pub fn events(&self) -> &[SemanticEvent];        // Pending semantic events
}
```

### walk-app → walk-renderer

```rust
pub struct GpuContext { /* Device, Queue, Surface */ }
    pub fn begin_frame(&mut self) -> SurfaceTexture;
    pub fn present(&self, frame: SurfaceTexture);
    pub fn resize(&mut self, width: u32, height: u32);

pub struct GlyphAtlas { /* GPU texture + shelf-packing */ }
    pub fn get_or_insert(&mut self, key: GlyphKey) -> AtlasRegion;

pub struct FontSystem { /* cosmic_text::FontSystem wrapper */ }

pub fn layout_grid(grid: &Grid<Cell>, origin: Point, font: &FontSystem, atlas: &mut GlyphAtlas) -> Vec<GlyphRun>;
```

### walk-app → walk-blocks

```rust
pub struct BlockManager { /* Block collection + state machine */ }
    pub fn handle_event(&mut self, event: &SemanticEvent, grid: &Grid<Cell>);
    pub fn visible_blocks(&self) -> &[Block];
    pub fn get_block(&self, id: u64) -> Option<&Block>;

pub struct BlockNavigator { /* Navigation state */ }
    pub fn select_prev(&mut self);
    pub fn select_next(&mut self);
    pub fn selected_block(&self) -> Option<&Block>;
    pub fn toggle_collapse(&mut self);
```

### walk-app → walk-input

```rust
pub struct InputEditor { /* Editor coordination */ }
    pub fn handle_key(&mut self, event: &InputEvent) -> Option<EditorAction>;
    pub fn render_data(&self) -> InputRenderData;

pub struct CommandHistory { /* Persistent history */ }
    pub fn prev(&mut self) -> Option<&str>;
    pub fn next(&mut self) -> Option<&str>;
    pub fn search(&mut self, query: &str) -> Vec<&str>;
    pub fn push(&mut self, command: &str);
```

### walk-app → walk-ui

```rust
pub fn compute_layout(root: &LayoutNode, available: Rect) -> LayoutResult;

pub struct TabManager { /* Tab collection */ }
    pub fn new_tab(&mut self, shell: &ShellType) -> u64;
    pub fn close_tab(&mut self, id: u64);
    pub fn switch_tab(&mut self, index: usize);
    pub fn active_terminal(&mut self) -> &mut Terminal;

pub struct SplitManager { /* Binary tree of panes */ }
    pub fn split_active(&mut self, direction: SplitDirection, new_tab_id: u64);
    pub fn close_split(&mut self, tab_id: u64);
    pub fn compute_rects(&self, available: Rect) -> HashMap<u64, Rect>;

pub struct Theme { /* Complete color/style specification */ }
pub struct ClipboardManager { /* arboard wrapper */ }
    pub fn copy(&mut self, text: &str) -> Result<(), ClipboardError>;
    pub fn paste(&mut self) -> Result<String, ClipboardError>;
```

### Cross-crate data dependencies

- **walk-blocks → walk-terminal**: Reads `SemanticEvent` enum and `Grid<Cell>` for extracting prompt/command text.
- **walk-input → walk-terminal**: Reads `ShellType` for syntax highlighting context.

---

## Block Build State Machine

The `BlockManager` uses a state machine driven by `SemanticEvent`s from shell integration (OSC 133):

```
WaitingForPrompt
       |
       | PromptStart { line }
       v
  InPrompt { start_line }
       |
       | CommandStart { line }
       v
  InCommand { prompt_text }
       |
       | OutputStart { line }
       v
  InOutput { block_id }
       |
       | CommandEnd { exit_code }
       v
WaitingForPrompt  (block finalized)
```

Each completed cycle creates one `Block` record containing: command text, output line range, exit code, duration, CWD, and optional git info.

---

## Module Organization

### walk-app/src/

```
lib.rs
main.rs              — fn main(), CLI arg parsing, panic handler, tracing init
app.rs               — WalkApp struct, AppHandler impl
config.rs            — WalkConfig, TOML loading, config_dir()
dpi.rs               — ScaleContext, coordinate conversion
event_loop.rs        — run_event_loop()
frame_clock.rs       — FrameClock, FPS tracking
handler.rs           — AppHandler trait definition
input.rs             — KeyAction, Modifiers, InputEvent, translate_key_event
keybindings.rs       — Action enum, KeyCombo, KeybindingConfig
session.rs           — SessionState, save/load
scripting/
  mod.rs             — LuaRuntime initialization
  api.rs             — walk.* Lua API surface
  keymaps.rs         — walk.keymap() implementation
  themes.rs          — walk.theme.* implementation
  events.rs          — walk.on() event hooks
```

### walk-renderer/src/

```
lib.rs
atlas.rs             — GlyphAtlas, shelf-packing allocator
compositor.rs        — Layer blending, alpha compositing
damage.rs            — DirtyRegion bitmap
gpu.rs               — GpuContext (Device, Queue, Surface)
pipeline.rs          — wgpu render pipeline, vertex/fragment shaders
text_layout.rs       — GlyphRun, PositionedGlyph, layout_line, layout_grid
text_shaper.rs       — FontSystem, TextShaper wrapping cosmic-text
```

### walk-terminal/src/

```
lib.rs
async_io.rs          — PtyIoHandle, PtyEvent, reader thread
config.rs            — TerminalConfig (scrollback, wrapping, unicode width)
prompt.rs            — PromptDetector, PromptFramework detection
pty.rs               — PtyManager, shell process spawning
semantic.rs          — SemanticEvent enum (or re-export from walk-blocks)
shell.rs             — ShellType, detect_default_shell, shell_spawn_config
shell_integration.rs — Embedded shell scripts (include_str!), integration_args
state.rs             — TerminalState wrapping alacritty_terminal::Term
terminal.rs          — Terminal struct (state + pty + dirty flag)
```

### walk-blocks/src/

```
lib.rs
block.rs             — Block struct, BlockManager, BlockBuildState
block_nav.rs         — BlockNavigator
block_search.rs      — BlockSearch, SearchMatch
metadata.rs          — GitInfo, detect_git_info
semantic.rs          — SemanticEvent enum
```

### walk-input/src/

```
lib.rs
brackets.rs          — find_matching_bracket
buffer.rs            — InputBuffer (gap buffer)
cursor_ops.rs        — move_left/right/word/line/up/down, select_*
editor.rs            — InputEditor, EditorAction, InputRenderData
highlighter.rs       — HighlightSpan, SpanKind, highlight()
history.rs           — CommandHistory, file persistence
```

### walk-ui/src/

```
lib.rs
background.rs        — BackgroundRenderer (image loading, textured quad)
bell.rs              — BellHandler, BellStyle
clipboard.rs         — ClipboardManager (arboard wrapper)
layout/
  mod.rs             — LayoutNode, LayoutResult, compute_layout, NodeId
links.rs             — URL detection, UrlSpan
search.rs            — GlobalSearch, GlobalMatch
selection.rs         — SelectionManager, CellPos, TextSelection
splits.rs            — SplitNode, SplitManager, SplitDirection
status_bar.rs        — StatusBarRenderer, StatusBarState
tab_bar.rs           — TabBarRenderer, TabBarAction
tabs.rs              — TabManager, Tab
theme.rs             — Theme, Color, SyntaxColors
theme_loader.rs      — load_theme, parse_hex_color, ThemeToml
theme_watcher.rs     — ThemeWatcher (notify-based hot-reload)
viewport.rs          — ViewportRenderer, smooth scrolling
zoom.rs              — ZoomManager
```

---

## Configuration Paths

| Item | Path |
|---|---|
| Config file | `$WALK_CONFIG` or `~/.config/walk/config.toml` or `~/.walk.toml` |
| Theme files | `~/.config/walk/themes/*.toml` |
| History file | `~/.walk_history` |
| Session state | `~/.config/walk/session.json` |
| Log file | `~/.config/walk/walk.log` |
| Lua init | `~/.config/walk/init.lua` |
| Windows config | `%APPDATA%\Walk\config.toml` |
