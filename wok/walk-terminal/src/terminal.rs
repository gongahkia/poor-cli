//! Terminal: connects the PTY async reader to alacritty_terminal.

use std::collections::HashMap;
use std::path::PathBuf;

use thiserror::Error;
use tracing::{debug, instrument};

use crate::async_io::{PtyEvent, PtyIoHandle};
use crate::pty::{PtyError, PtyManager};
use crate::shell::ShellType;
use crate::state::{TermEvent, TerminalState};

/// Errors from terminal operations.
#[derive(Debug, Error)]
pub enum TerminalError {
    /// Failed to create PTY.
    #[error("PTY error: {0}")]
    Pty(#[from] PtyError),

    /// Terminal I/O error.
    #[error("terminal I/O error: {0}")]
    Io(#[from] std::io::Error),
}

/// Semantic events emitted by shell integration markers.
#[derive(Debug, Clone)]
pub enum SemanticEvent {
    /// Shell prompt started (OSC 133;A).
    PromptStart {
        /// Line number where the prompt starts.
        line: u16,
    },
    /// Command input started (OSC 133;B).
    CommandStart {
        /// Line number where command input starts.
        line: u16,
    },
    /// Command output started (OSC 133;C).
    OutputStart {
        /// Line number where output starts.
        line: u16,
    },
    /// Command finished (OSC 133;D).
    CommandEnd {
        /// Line number.
        line: u16,
        /// Exit code if available.
        exit_code: Option<i32>,
    },
    /// Current working directory changed (OSC 7).
    CwdChanged(PathBuf),
    /// Window title changed.
    TitleChanged(String),
}

/// A terminal session connecting PTY I/O to terminal emulation state.
pub struct Terminal {
    /// Terminal emulation state (alacritty_terminal wrapper).
    pub state: TerminalState,
    /// Async PTY I/O handle.
    pty: PtyIoHandle,
    /// Current window title.
    pub title: String,
    /// Whether the terminal has new output since last render.
    dirty: bool,
    /// Semantic events collected this frame.
    pub events: Vec<SemanticEvent>,
    /// Number of columns.
    cols: u16,
    /// Number of rows.
    rows: u16,
    /// Whether the shell has exited.
    pub exited: bool,
    /// Exit code if shell has exited.
    pub exit_code: Option<i32>,
}

impl Terminal {
    /// Create a new terminal session.
    ///
    /// # Errors
    ///
    /// Returns [`TerminalError`] if the PTY cannot be created or the shell
    /// cannot be spawned.
    #[instrument(skip(env), fields(%shell, cols, rows))]
    pub fn new(
        shell: &ShellType,
        cols: u16,
        rows: u16,
        scrollback: usize,
        env: HashMap<String, String>,
    ) -> Result<Self, TerminalError> {
        let manager = PtyManager::new();
        let pair = manager.spawn(shell, cols, rows, env)?;

        let reader = pair.master.try_clone_reader().map_err(|e| {
            PtyError::SystemCreation(format!("failed to clone PTY reader: {e}"))
        })?;
        let writer = pair
            .master
            .take_writer()
            .map_err(|e| PtyError::SystemCreation(format!("failed to take PTY writer: {e}")))?;

        let pty = PtyIoHandle::new(reader, writer);
        let state = TerminalState::new(cols as usize, rows as usize, scrollback);

        debug!("terminal created");
        Ok(Self {
            state,
            pty,
            title: shell.to_string(),
            dirty: false,
            events: Vec::new(),
            cols,
            rows,
            exited: false,
            exit_code: None,
        })
    }

    /// Process pending PTY output, feeding bytes to the terminal emulator.
    ///
    /// Processes up to 64 events per call to avoid stalling the render loop.
    pub fn process_pty_output(&mut self) {
        self.events.clear();
        let mut count = 0;

        while count < 64 {
            match self.pty.try_recv() {
                Some(PtyEvent::Data(bytes)) => {
                    self.state.process_bytes(&bytes);
                    self.dirty = true;
                    count += 1;
                }
                Some(PtyEvent::Exited(code)) => {
                    self.exited = true;
                    self.exit_code = Some(code);
                    self.dirty = true;
                    break;
                }
                Some(PtyEvent::Error(e)) => {
                    debug!("PTY error: {e}");
                    self.exited = true;
                    break;
                }
                None => break,
            }
        }

        // Drain terminal events and convert to semantic events
        for event in self.state.drain_events() {
            match event {
                TermEvent::TitleChanged(title) => {
                    self.title = title.clone();
                    self.events.push(SemanticEvent::TitleChanged(title));
                }
                _ => {}
            }
        }
    }

    /// Send input to the PTY.
    ///
    /// # Errors
    ///
    /// Returns [`TerminalError`] if the write fails.
    pub fn send_input(&self, data: &[u8]) -> Result<(), TerminalError> {
        self.pty.write(data).map_err(TerminalError::Pty)
    }

    /// Resize the terminal and PTY.
    pub fn resize(&mut self, cols: u16, rows: u16) {
        self.cols = cols;
        self.rows = rows;
        self.state.resize(cols as usize, rows as usize);
        self.dirty = true;
    }

    /// Check if the terminal has new output to render.
    pub fn is_dirty(&self) -> bool {
        self.dirty
    }

    /// Mark the terminal as clean (after rendering).
    pub fn mark_clean(&mut self) {
        self.dirty = false;
    }

    /// Get the current number of columns.
    pub fn cols(&self) -> u16 {
        self.cols
    }

    /// Get the current number of rows.
    pub fn rows(&self) -> u16 {
        self.rows
    }
}
