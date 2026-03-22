# Walk Rust Style Guide

Code style conventions for the Walk terminal emulator. All contributors (human and automated) must follow these patterns.

---

## Module File Organization

- One logical unit per file. Do not put multiple unrelated types in one file.
- `lib.rs` is for crate-level attributes and public re-exports only. No implementation logic.
- Use `mod` declarations in `lib.rs` to declare all modules.
- Prefer flat module structure (`src/foo.rs`) over nested (`src/foo/mod.rs`) unless the module has sub-modules.

Example `lib.rs`:

```rust
//! Walk Renderer: GPU-accelerated text rendering pipeline.
#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]

mod atlas;
mod compositor;
mod damage;
mod gpu;
mod pipeline;
mod text_layout;
mod text_shaper;

pub use atlas::{AtlasRegion, GlyphAtlas};
pub use compositor::Compositor;
pub use damage::DirtyRegion;
pub use gpu::GpuContext;
pub use pipeline::RenderPipeline;
pub use text_layout::{GlyphRun, PositionedGlyph};
pub use text_shaper::{FontSystem, TextShaper};
```

---

## Import Ordering

Four groups separated by blank lines, each sorted alphabetically:

```rust
// 1. Standard library
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

// 2. External crates
use crossbeam_channel::{bounded, Receiver, Sender};
use thiserror::Error;
use tracing::{debug, info, instrument, warn};

// 3. Workspace crates
use walk_renderer::GpuContext;
use walk_terminal::Terminal;

// 4. Crate-internal modules
use crate::config::WalkConfig;
use crate::keybindings::Action;
```

---

## Error Type Patterns

### Pattern 1: Simple Crate Error

For crates with self-contained errors (no external error wrapping):

```rust
use thiserror::Error;

/// Errors that can occur in the walk-input crate.
#[derive(Debug, Error)]
pub enum InputError {
    /// Cursor index exceeds the number of active cursors.
    #[error("cursor index {index} out of bounds (have {count} cursors)")]
    CursorOutOfBounds {
        /// The requested cursor index.
        index: usize,
        /// The actual number of cursors.
        count: usize,
    },

    /// Delete range extends beyond buffer length.
    #[error("delete range {start}..{end} exceeds buffer length {len}")]
    RangeOutOfBounds {
        /// Start of the requested range.
        start: usize,
        /// End of the requested range.
        end: usize,
        /// Current buffer length.
        len: usize,
    },
}
```

### Pattern 2: Crate Error Wrapping External Errors

For crates that interact with external systems:

```rust
use thiserror::Error;

/// Errors that can occur in the walk-terminal crate.
#[derive(Debug, Error)]
pub enum TerminalError {
    /// Failed to create the PTY.
    #[error("PTY creation failed: {0}")]
    PtyCreation(#[source] Box<dyn std::error::Error + Send + Sync>),

    /// Failed to spawn the shell process.
    #[error("failed to spawn shell '{shell}': {source}")]
    ShellSpawn {
        /// The shell path attempted.
        shell: String,
        /// The underlying I/O error.
        #[source]
        source: std::io::Error,
    },

    /// I/O error during PTY read or write.
    #[error("PTY I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// The PTY reader channel disconnected unexpectedly.
    #[error("PTY reader channel disconnected")]
    ChannelDisconnected,
}
```

### Pattern 3: Application-Level Aggregating Error

For `walk-app` which composes errors from all subsystems:

```rust
use thiserror::Error;

/// Top-level application errors.
#[derive(Debug, Error)]
pub enum AppError {
    /// Terminal subsystem error.
    #[error("terminal error: {0}")]
    Terminal(#[from] walk_terminal::TerminalError),

    /// Renderer subsystem error.
    #[error("renderer error: {0}")]
    Renderer(#[from] walk_renderer::RenderError),

    /// Configuration error.
    #[error("config error: {0}")]
    Config(#[from] ConfigError),
}
```

### Error Rules

- `#[error("...")]` messages start with lowercase.
- Use `#[source]` for error chaining. Use `#[from]` only when the conversion is unambiguous (one variant per source type).
- Every variant gets a doc comment.
- Never use `unwrap()` or `expect()` in library code without documenting why it cannot fail.

---

## Tracing / Logging Patterns

### Pattern: Function-Level Instrumentation

```rust
use tracing::{debug, info, instrument, warn};

/// Creates a new terminal session with the specified shell.
#[instrument(skip(env), fields(shell = %config.shell, cols = config.cols, rows = config.rows))]
pub fn new(config: &TerminalConfig, env: HashMap<String, String>) -> Result<Self, TerminalError> {
    info!("creating new terminal session");
    let pty = PtyManager::spawn(&config.shell_path(), config.pty_size(), env)?;
    debug!(pid = %pty.process_id(), "shell process spawned");
    // ...
}
```

### Pattern: Subsystem Span

```rust
use tracing::info_span;

fn process_frame(&mut self) {
    let _span = info_span!("frame", number = self.frame_clock.frame_count()).entered();

    {
        let _pty_span = info_span!("pty_processing").entered();
        self.process_all_pty_output();
    }

    {
        let _render_span = info_span!("render").entered();
        self.render_all();
    }
}
```

### Pattern: Structured Error Logging

```rust
match load_theme(path) {
    Ok(theme) => {
        info!(?path, name = %theme.name, "theme loaded successfully");
        self.theme = theme;
    }
    Err(err) => {
        warn!(?path, %err, "failed to load theme, keeping current theme");
    }
}
```

### Log Level Guidelines

| Level | Use For |
|---|---|
| `error!` | Unrecoverable failures that will terminate a subsystem |
| `warn!` | Recoverable issues (bad config, failed theme load, transient errors) |
| `info!` | Significant state changes (shell spawned, tab created, theme loaded) |
| `debug!` | Detailed control flow useful for development |
| `trace!` | Per-frame or high-frequency data (PTY bytes received, glyph cache hits) |

### Instrumentation Rules

- Use `#[instrument]` on: public functions with I/O, state transitions, or subsystem entry points.
- Use `skip` for large arguments: buffers, hashmaps, GPU types, closures.
- Use `fields(...)` to add structured context: IDs, dimensions, counts.

---

## Struct and Enum Naming

### Type Naming

Prefix types with crate context for cross-crate clarity:

| Do | Don't |
|---|---|
| `GpuContext` | `Context` |
| `PtyManager` | `Manager` |
| `BlockNavigator` | `Navigator` |
| `InputBuffer` | `Buffer` |
| `LayoutNode` | `Node` |
| `TerminalConfig` | `Config` |

### Enum Variant Naming

Variants do not repeat the enum name:

```rust
// Good
pub enum PtyEvent {
    Data(Vec<u8>),
    Exited(i32),
    Error(PtyError),
}

// Bad
pub enum PtyEvent {
    PtyData(Vec<u8>),
    PtyExited(i32),
    PtyError(PtyError),
}
```

### State Machine States

Name as adjectives or prepositions describing the current state:

```rust
enum BlockBuildState {
    WaitingForPrompt,
    InPrompt { start_line: u16 },
    InCommand { prompt_text: String },
    InOutput { block_id: u64 },
}
```

### Action/Command Enums

Use imperative verbs:

```rust
pub enum Action {
    NewTab,
    CloseTab,
    ScrollUp,
    BlockPrev,
    ZoomIn,
    SendEof,
}
```

---

## Public API Documentation Requirements

Every `pub` item must have a doc comment (`#![deny(missing_docs)]` enforced).

### Function Documentation Template

```rust
/// Short summary in imperative mood, no trailing period
///
/// Extended description explaining *why* this exists and how it fits
/// into the larger system. Reference related types with [`TypeName`] links.
///
/// # Errors
///
/// Returns [`FooError::VariantA`] when condition X.
/// Returns [`FooError::VariantB`] when condition Y.
///
/// # Panics
///
/// Panics if <condition> (prefer returning Result instead).
///
/// # Examples
///
/// ```rust
/// let mut buf = InputBuffer::new();
/// buf.insert_at(0, "hello").unwrap();
/// assert_eq!(buf.text(), "hello");
/// ```
pub fn example_fn(&mut self) -> Result<(), FooError> {
    // ...
}
```

### Rules

- **Summary line**: imperative mood ("Create", "Return", "Insert"), no trailing period.
- **`# Errors`**: mandatory on all functions returning `Result`.
- **`# Panics`**: mandatory if the function can panic.
- **`# Examples`**: recommended for public API entry points, not required for every method.
- **Module-level docs** (`//!`): required in every `.rs` file.

---

## Testing Patterns

### Unit Tests — Co-located

```rust
// ... implementation code ...

#[cfg(test)]
mod tests {
    use super::*;

    fn mock_buffer(text: &str) -> InputBuffer {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, text).unwrap();
        buf
    }

    #[test]
    fn test_insert_at_empty_buffer() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "hello").unwrap();
        assert_eq!(buf.text(), "hello");
    }

    #[test]
    fn test_delete_range_middle() {
        let mut buf = mock_buffer("abcdef");
        buf.delete_range(2, 4).unwrap();
        assert_eq!(buf.text(), "abef");
    }

    #[test]
    fn test_error_on_invalid_cursor() {
        let mut buf = InputBuffer::new();
        let result = buf.insert_at(5, "oops");
        assert!(matches!(result, Err(InputError::CursorOutOfBounds { .. })));
    }
}
```

### Integration Tests

```rust
// walk-terminal/tests/pty_integration.rs
use walk_terminal::{Terminal, TerminalConfig};
use std::time::{Duration, Instant};

#[test]
fn test_pty_echo_output() {
    let config = TerminalConfig::default();
    let mut terminal = Terminal::new(&config).expect("failed to create terminal");

    terminal.send_input(b"echo WALK_TEST_MARKER\n");

    let deadline = Instant::now() + Duration::from_secs(5);
    let mut found = false;
    while Instant::now() < deadline {
        terminal.process_pty_output();
        if grid_contains_text(terminal.grid(), "WALK_TEST_MARKER") {
            found = true;
            break;
        }
        std::thread::sleep(Duration::from_millis(10));
    }

    assert!(found, "WALK_TEST_MARKER not found in terminal grid within 5s");
}
```

### Testing Rules

- Test naming: `test_<what_is_being_tested>` in snake_case.
- Mock helpers: prefix with `mock_`.
- Use `assert_eq!` with descriptive messages for non-obvious assertions.
- Use `assert!(matches!(...))` for error variant checking.
- Cover boundary conditions: empty inputs, single elements, maximum values.
- Each task's "DONE WHEN" criteria map directly to test cases.

---

## Clippy Configuration

Every crate's `lib.rs` includes:

```rust
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]

// Targeted allows with rationale:
#![allow(clippy::module_name_repetitions)]   // Intentional: GpuContext in gpu module
#![allow(clippy::cast_possible_truncation)]  // Terminal dimensions bounded to u16
#![allow(clippy::cast_sign_loss)]            // Grid coordinates always non-negative
#![allow(clippy::cast_precision_loss)]       // f64->f32 acceptable for GPU coords
```

Per-crate additions if needed:

| Crate | Additional Allow | Rationale |
|---|---|---|
| `walk-renderer` | `clippy::similar_names` | Shader parameter names (`u`, `v`, `x`, `y`) |
| `walk-app` | `clippy::too_many_lines` | The `handle_action` match block |

Never globally suppress: `clippy::unwrap_used`, `clippy::panic`, `clippy::expect_used`. Use these sparingly and document why.

---

## Struct Construction Patterns

### Simple Constructor

```rust
impl FrameClock {
    /// Creates a new frame clock targeting the specified FPS
    pub fn new(target_fps: u32) -> Self {
        Self {
            target_fps,
            last_frame: Instant::now(),
            frame_count: 0,
            accumulated_time: Duration::ZERO,
        }
    }
}
```

### Fallible Constructor

```rust
impl GpuContext {
    /// Creates a new GPU rendering context from the given window
    ///
    /// # Errors
    ///
    /// Returns [`RenderError::AdapterNotFound`] if no suitable GPU adapter is available.
    /// Returns [`RenderError::DeviceCreation`] if the GPU device cannot be created.
    pub fn new(window: &WalkWindow) -> Result<Self, RenderError> {
        // ...
    }
}
```

### Default Implementation

```rust
impl Default for TerminalConfig {
    fn default() -> Self {
        Self {
            scrollback_lines: 10_000,
            text_wrap: true,
            unicode_ambiguous_width: 1,
        }
    }
}
```

### Builder Pattern

Use only when structs have more than 5 configuration fields. Prefer `::new(required_args)` with `Default` for simple types.

---

## Enum Design Patterns

### State Machine

```rust
/// The current state of block construction from semantic events.
#[derive(Debug)]
enum BlockBuildState {
    /// Waiting for the next prompt to appear.
    WaitingForPrompt,
    /// Inside a prompt, recording the start line.
    InPrompt {
        /// The terminal line where the prompt started.
        start_line: u16,
    },
    /// Between command start and output start.
    InCommand {
        /// The captured prompt text.
        prompt_text: String,
    },
    /// Receiving command output.
    InOutput {
        /// The ID of the block being built.
        block_id: u64,
    },
}
```

### Event/Message

```rust
/// Events received from the PTY reader thread.
#[derive(Debug)]
pub enum PtyEvent {
    /// Raw bytes read from the PTY output.
    Data(Vec<u8>),
    /// The shell process has exited with the given code.
    Exited(i32),
    /// An error occurred reading from the PTY.
    Error(PtyError),
}
```

### Action (Exhaustive, Copyable)

```rust
/// All bindable user actions.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Action {
    /// Create a new tab.
    NewTab,
    /// Close the current tab.
    CloseTab,
    // ... every variant documented
}
```

---

## Visibility Rules

- **Default to private.** Only make items `pub` if used by another module within the crate or by another crate.
- **`pub(crate)`** for items visible within the crate but not exported.
- **`lib.rs`** re-exports only the items forming the crate's public API.
- **Internal helpers stay private.**

```rust
// In buffer.rs
pub struct InputBuffer { /* public: used by other crates */ }
pub(crate) fn move_gap(buf: &mut InputBuffer, pos: usize) { /* crate-internal */ }
fn validate_position(pos: usize, len: usize) -> bool { /* file-private */ }
```

---

## Numeric Literals

Use underscores for readability in large numbers:

```rust
const SCROLLBACK_DEFAULT: usize = 10_000;
const ATLAS_SIZE: u32 = 2_048;
const CHANNEL_BOUND: usize = 256;
const MAX_HISTORY: usize = 10_000;
const READ_BUFFER_SIZE: usize = 65_536;
```

---

## Miscellaneous

- **String formatting**: Prefer `format!()` over string concatenation.
- **Iterators**: Prefer iterator chains over manual loops when the intent is clearer.
- **`match` exhaustiveness**: Always handle all variants. Use `_` catch-all only when new variants should use a default behavior.
- **`todo!()`**: Acceptable as a placeholder during development but must not be present in code merged to `main`.
- **`dbg!()`**: Development only. Strip before committing.
