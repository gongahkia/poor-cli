# CLAUDE.md — Walk Implementation Guide

Walk is a Warp-inspired, GPU-accelerated, cross-platform terminal emulator written in Rust (2021 edition, MSRV 1.75+). No AI, no login, no cloud. The key differentiator is **Blocks** — each command-output pair is a navigable, collapsible unit. Rendering uses wgpu, terminal emulation uses alacritty_terminal, PTY management uses portable-pty, font loading uses cosmic-text.

The full implementation spec lives in `todo.md` — 73 tasks across 19 phases. This file is the single reference for all coding conventions, architecture, and workflow decisions.

---

## Workspace Architecture

```
walk-app (binary, entry point)
  ├── walk-renderer  (GPU rendering, glyph atlas, text layout)
  ├── walk-terminal  (alacritty_terminal wrapper, PTY, shell integration)
  ├── walk-blocks    (block detection, navigation, search, metadata)
  ├── walk-input     (gap buffer editor, cursor ops, syntax highlighting, history)
  └── walk-ui        (layout, tabs, splits, viewport, theme, clipboard, selection, search)
```

- **walk-app**: Entry point, winit event loop, window management, config loading, keybinding dispatch, Lua scripting, main `WalkApp` struct wiring everything together.
- **walk-renderer**: wgpu GPU context, glyph atlas (shelf-packing), text shaping/layout (cosmic-text), render pipeline (vertex/fragment shaders), damage tracking, compositor. Leaf crate — no workspace-internal dependencies.
- **walk-terminal**: Thin wrapper around `alacritty_terminal::Term` + `portable-pty`. Async PTY I/O with crossbeam channels. Shell detection, shell integration scripts (OSC 133 markers), terminal config. Leaf crate — no workspace-internal dependencies.
- **walk-blocks**: Block data model, `BlockManager` state machine driven by `SemanticEvent`s. Block navigation, collapse/expand, per-block search, git/timing metadata. Depends on walk-terminal (for `SemanticEvent`, grid access).
- **walk-input**: Gap buffer `InputBuffer`, cursor movement operations, syntax highlighting for shell commands, bracket matching, `InputEditor` coordination, command history with file persistence. Depends on walk-terminal (for `ShellType`).
- **walk-ui**: Flexbox-inspired layout engine, tab management, split pane binary tree, viewport rendering, tab bar, status bar, theme data model + TOML loader + hot-reload, clipboard (arboard), mouse selection, global search, font zoom, bell, URL detection, mouse reporting, session persistence. Depends on walk-renderer, walk-terminal, walk-blocks.

---

## Build, Test, Run Commands

```bash
# Build entire workspace
cargo build --workspace

# Build release
cargo build --workspace --release

# Run the application (debug)
cargo run -p walk

# Run all tests
cargo test --workspace

# Run tests for a specific crate
cargo test -p walk-input
cargo test -p walk-blocks
cargo test -p walk-terminal
cargo test -p walk-renderer

# Check lints
cargo clippy --all-targets --all-features -- -D warnings

# Check formatting
cargo fmt --check

# Format code
cargo fmt

# Build documentation
cargo doc --no-deps --workspace

# Run a specific test
cargo test -p walk-input test_insert_at_start
```

---

## Code Style Conventions

### Naming

Prefix types with crate context to avoid ambiguity across crate boundaries:

- `GpuContext` (not `Context`) in walk-renderer
- `PtyManager` (not `Manager`) in walk-terminal
- `BlockNavigator` (not `Navigator`) in walk-blocks
- `InputBuffer` (not `Buffer`) in walk-input
- `LayoutNode` (not `Node`) in walk-ui

Functions: `snake_case`. Modules: `snake_case`. Constants: `SCREAMING_SNAKE_CASE`. Enum variants: `PascalCase` without repeating the enum name (`PtyEvent::Data`, not `PtyEvent::PtyData`).

### Module Organization

Each crate follows this structure:

```
walk-<crate>/
  Cargo.toml
  src/
    lib.rs          # Crate-level attributes + public re-exports only
    <module>.rs     # One file per logical unit
    subdir/mod.rs   # Only when a module has sub-modules
  tests/
    <test_name>.rs  # Integration tests
```

`lib.rs` must contain these crate-level attributes at the top:

```rust
//! Walk <crate-name>: <one-line description>.
#![deny(missing_docs)]
#![forbid(unsafe_code)]  // or #![allow(unsafe_code)] for crates needing it
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
```

### Error Handling

Every crate defines its own error enum using `thiserror`. Pattern:

```rust
use thiserror::Error;

/// Errors that can occur during PTY operations.
#[derive(Debug, Error)]
pub enum PtyError {
    /// Failed to create the native PTY system.
    #[error("failed to create PTY system: {0}")]
    SystemCreation(#[source] Box<dyn std::error::Error + Send + Sync>),

    /// Failed to spawn the shell process.
    #[error("failed to spawn shell '{shell}': {source}")]
    SpawnFailed {
        /// The shell path that was attempted.
        shell: String,
        /// The underlying error.
        #[source]
        source: std::io::Error,
    },

    /// The PTY reader channel was disconnected.
    #[error("PTY reader channel disconnected")]
    ChannelDisconnected,
}
```

Rules:
- `#[error("...")]` messages start with lowercase (Rust convention).
- Use `#[source]` for error chaining, not `#[from]` unless the conversion is unambiguous.
- Every variant must have a doc comment.
- Library crate functions return `Result<T, CrateSpecificError>`. The binary crate (`walk-app/src/main.rs`) may use `Box<dyn Error>` at the top level only.

### Public API Documentation

The workspace enforces `#![deny(missing_docs)]`. Every `pub` item needs a doc comment:

```rust
/// A gap-buffer-backed text buffer for the input editor.
///
/// The gap buffer provides O(1) amortized insertion and deletion at the cursor
/// position, which is the dominant operation pattern for interactive text editing.
pub struct InputBuffer {
    // ...
}

/// Inserts text at the specified cursor position.
///
/// # Errors
///
/// Returns [`InputError::CursorOutOfBounds`] if `cursor_idx` exceeds the
/// number of cursors.
pub fn insert_at(&mut self, cursor_idx: usize, text: &str) -> Result<(), InputError> {
    // ...
}
```

Rules:
- Summary line: imperative mood ("Create", "Return", "Insert"), no trailing period.
- `# Errors` section mandatory on all functions returning `Result`.
- `# Examples` section recommended for public API entry points.
- Module-level docs (`//!`) in every file.

---

## Linting and Formatting

Every crate's `lib.rs` must include:

```rust
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]  // Intentional: prefixed types
#![allow(clippy::cast_possible_truncation)] // Terminal dimensions bounded to u16
#![allow(clippy::cast_sign_loss)]           // Grid coordinates always non-negative
#![allow(clippy::cast_precision_loss)]      // f64->f32 acceptable for GPU coords
```

Additional per-crate allows if needed:
- `walk-renderer`: `#![allow(clippy::similar_names)]` for shader parameters.
- `walk-app`: `#![allow(clippy::too_many_lines)]` for the `handle_action` match.

Use default `rustfmt` settings. Always run `cargo fmt` before committing.

---

## Testing Approach

- **Unit tests**: `#[cfg(test)] mod tests` at the bottom of each source file.
- **Integration tests**: `<crate>/tests/<name>.rs`.
- **Test naming**: `test_<what_is_being_tested>` in snake_case.
- **Mock helpers**: functions prefixed with `mock_` in the test module.

```rust
#[cfg(test)]
mod tests {
    use super::*;

    fn mock_buffer_with_text(text: &str) -> InputBuffer {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, text).unwrap();
        buf
    }

    #[test]
    fn test_insert_at_start() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "hello").unwrap();
        assert_eq!(buf.text(), "hello", "text should match after insertion");
    }

    #[test]
    fn test_error_on_invalid_cursor() {
        let mut buf = InputBuffer::new();
        let result = buf.insert_at(5, "oops");
        assert!(matches!(result, Err(InputError::CursorOutOfBounds { .. })));
    }
}
```

---

## Tracing / Logging

The project uses `tracing` with structured spans. Key functions get `#[instrument]`:

```rust
use tracing::{debug, info, instrument, warn};

/// Spawns a new shell process with the given configuration.
#[instrument(skip(env), fields(shell = %shell, cols = size.cols, rows = size.rows))]
pub fn spawn(shell: &str, size: PtySize, env: HashMap<String, String>) -> Result<PtyPair, PtyError> {
    info!("spawning shell process");
    // ...
    debug!(pid = %child.process_id(), "shell process started");
    Ok(pair)
}
```

Rules:
- `#[instrument]` on: public functions with I/O, state transitions, or subsystem entry points.
- `skip` large arguments (buffers, hashmaps, GPU types).
- `fields(...)` for structured context (IDs, dimensions).
- Log levels: `error!` unrecoverable, `warn!` recoverable, `info!` significant state changes (shell spawned, tab created, theme loaded), `debug!` detailed flow, `trace!` per-frame/high-frequency.
- Initialize in `main.rs` with `tracing_subscriber`: `warn` in release, `debug` in debug builds, output to `~/.config/walk/walk.log`.

---

## Unsafe Code Policy

```rust
// Workspace default in every crate:
#![forbid(unsafe_code)]

// Crates needing unsafe (walk-renderer for GPU interop) override per-crate:
#![allow(unsafe_code)]
```

Every `unsafe` block must have a `// SAFETY:` comment:

```rust
// SAFETY: The wgpu buffer was created with MAP_READ usage and we verified
// the mapping succeeded before accessing the slice.
let data = unsafe { slice.get_unchecked(0..len) };
```

---

## Concurrency Model

Walk uses OS threads + crossbeam channels. **No async runtime** (no tokio, no async-std).

- **PTY reader**: dedicated `std::thread` per terminal, sends `PtyEvent` through `crossbeam_channel::bounded(256)`.
- **Main thread**: runs winit event loop, processes PTY events via `try_recv()`, drives rendering.
- **Theme watcher**: `notify` crate runs its own background thread, communicates via channel.
- No shared mutable state between threads without explicit `Arc<Mutex<>>` or channels.

```rust
use crossbeam_channel::{bounded, Receiver, Sender};

let (tx, rx): (Sender<PtyEvent>, Receiver<PtyEvent>) = bounded(256);

// Sender (reader thread)
std::thread::spawn(move || {
    loop {
        // ... read data ...
        if tx.send(PtyEvent::Data(buf)).is_err() {
            break; // receiver dropped
        }
    }
});

// Receiver (main thread, non-blocking)
while let Ok(event) = rx.try_recv() {
    // process event
}
```

---

## Dependency Management

Use semver caret ranges. Commit `Cargo.lock` (this is a binary application).

Key dependencies:

| Crate | Version | Purpose |
|---|---|---|
| `winit` | `"0.30"` | Windowing and event loop |
| `wgpu` | `"24"` | GPU rendering |
| `alacritty_terminal` | `"0.24"` | Terminal emulation |
| `portable-pty` | `"0.8"` | PTY management |
| `cosmic-text` | `"0.12"` | Font loading/shaping |
| `crossbeam-channel` | `"0.5"` | Thread channels |
| `thiserror` | `"2"` | Error derive macros |
| `tracing` | `"0.1"` | Structured logging |
| `tracing-subscriber` | `"0.3"` | Log output |
| `serde` | `"1"` (with `derive`) | Serialization |
| `toml` | `"0.8"` | Config file parsing |
| `arboard` | `"3"` | Clipboard |
| `notify` | `"6"` | File watching |
| `clap` | `"4"` (with `derive`) | CLI argument parsing |
| `mlua` | `"0.10"` (with `lua54`, `serialize`) | Lua scripting |
| `image` | `"0.25"` | Image decoding |
| `unicode-width` | `"0.2"` | Character width detection |

---

## Git Workflow

### Branching

- Phase branches: `feat/phase-N-name` (e.g., `feat/phase-1-platform`, `feat/phase-2-renderer`).
- Branch from `main`, merge to `main` when the phase is complete.
- A phase is complete when all its tasks pass their "DONE WHEN" criteria.

### Commit Format — Conventional Commits

```
type(scope): description

[optional body]
```

**Types**: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `ci`, `style`.

**Scopes** match crate names without the `walk-` prefix: `app`, `renderer`, `terminal`, `blocks`, `input`, `ui`. Cross-cutting: `workspace`.

Examples:
```
feat(terminal): add PtyManager with shell auto-detection
fix(renderer): prevent glyph atlas overflow on CJK text
test(input): add gap buffer boundary condition tests
refactor(blocks): extract BlockBuildState into separate module
docs(workspace): add ARCHITECTURE.md
chore(workspace): update wgpu to v24.1
ci: add pr-checks workflow with clippy and fmt gates
```

---

## Platform Considerations

**Linux + macOS first.** All code must build and pass tests on both before considering Windows. Windows support is deferred — use `#[cfg(target_os = "windows")]` guards for platform-specific code but keep it minimal initially.

```rust
#[cfg(target_os = "macos")]
fn platform_modifier() -> Modifiers {
    Modifiers { meta: true, ..Default::default() }
}

#[cfg(not(target_os = "macos"))]
fn platform_modifier() -> Modifiers {
    Modifiers { ctrl: true, ..Default::default() }
}
```

---

## How to Read and Follow todo.md

Each task in `todo.md` has:
- **Number and priority** (A = critical path, B = important, C = nice-to-have)
- **Tag** (+platform, +renderer, +terminal, etc.)
- **blockedBy** — listed tasks must be complete first
- **PURPOSE** — why this task exists
- **WHAT TO DO** — step-by-step implementation guide
- **DONE WHEN** — acceptance criteria (checkboxes)
- **WHY annotations** — design rationale inline; respect these decisions

Work through tasks in dependency order within each phase. Phases can overlap when dependencies allow. A task is not complete until all "DONE WHEN" criteria pass.

---

## Common Patterns Quick Reference

### New Crate Setup

```rust
// walk-<name>/src/lib.rs
//! Walk <name>: <description>.
#![deny(missing_docs)]
#![forbid(unsafe_code)]
#![warn(clippy::pedantic)]
#![warn(clippy::nursery)]
#![allow(clippy::module_name_repetitions)]
#![allow(clippy::cast_possible_truncation)]
#![allow(clippy::cast_sign_loss)]
#![allow(clippy::cast_precision_loss)]

mod some_module;

pub use some_module::SomePublicType;
```

### New Error Type

```rust
use thiserror::Error;

/// Errors from the <subsystem> crate.
#[derive(Debug, Error)]
pub enum FooError {
    /// Description of this variant.
    #[error("message: {0}")]
    Variant(#[source] SomeOtherError),
}
```

### New Struct with Tracing

```rust
use tracing::{debug, info, instrument};

/// Does something important.
#[instrument(skip(large_arg), fields(id = %self.id))]
pub fn do_thing(&self, large_arg: &BigStruct) -> Result<(), FooError> {
    info!("starting thing");
    // ...
    debug!(result = ?value, "thing completed");
    Ok(())
}
```

### Import Ordering

```rust
// 1. Standard library
use std::collections::HashMap;
use std::path::PathBuf;

// 2. External crates (alphabetical)
use crossbeam_channel::{bounded, Receiver, Sender};
use thiserror::Error;
use tracing::{debug, info, instrument};

// 3. Workspace crates (alphabetical)
use walk_renderer::GpuContext;
use walk_terminal::Terminal;

// 4. Crate-internal modules (alphabetical)
use crate::config::WalkConfig;
use crate::keybindings::Action;
```

### Numeric Literals

Use underscores for readability: `10_000`, `2_048`, `65_536`, `256`.

### Visibility

Default to private. Use `pub(crate)` for crate-internal items. Only `pub` what forms the crate's public API. Re-export in `lib.rs`.
