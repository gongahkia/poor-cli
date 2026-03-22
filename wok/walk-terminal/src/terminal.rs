//! Terminal: connects the PTY async reader to alacritty_terminal.

use std::collections::HashMap;
use std::path::PathBuf;

use thiserror::Error;
use tracing::{debug, instrument};

use crate::async_io::{PtyEvent, PtyIoHandle};
use crate::pty::{PtyError, PtyManager};
use crate::shell::ShellType;
use crate::state::{AbsoluteRow, TermEvent, TerminalState};

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
        /// Absolute row where the prompt starts.
        row: AbsoluteRow,
    },
    /// Command input started (OSC 133;B).
    CommandStart {
        /// Absolute row where command input starts.
        row: AbsoluteRow,
    },
    /// Command output started (OSC 133;C).
    OutputStart {
        /// Absolute row where command output starts.
        row: AbsoluteRow,
    },
    /// Command finished (OSC 133;D).
    CommandEnd {
        /// Absolute row where command output ended.
        row: AbsoluteRow,
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
    events: Vec<SemanticEvent>,
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
        let spawned = manager.spawn(shell, cols, rows, &env)?;
        let pty = PtyIoHandle::new(spawned);
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
                    self.scan_osc_markers(&bytes);
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
                    self.title.clone_from(&title);
                    self.events.push(SemanticEvent::TitleChanged(title));
                }
                TermEvent::PtyWrite(_)
                | TermEvent::Bell
                | TermEvent::Exit
                | TermEvent::ChildExit(_)
                | TermEvent::ClipboardStore(_)
                | TermEvent::CursorBlinkingChange => {}
            }
        }
    }

    /// Scan raw bytes for OSC 133 semantic markers.
    ///
    /// Looks for `\x1b]133;X\x07` patterns where X is A, B, C, or D.
    fn scan_osc_markers(&mut self, bytes: &[u8]) {
        let cursor_row = self.state.absolute_cursor_row();
        let mut i = 0;
        while i + 6 < bytes.len() {
            // Look for ESC ] 133 ;
            if bytes[i] == 0x1b && bytes.get(i + 1) == Some(&b']') {
                // Find the ST (BEL \x07 or ESC \\ )
                if let Some(end) = bytes[i..].iter().position(|&b| b == 0x07) {
                    let payload = &bytes[i + 2..i + end];
                    if let Ok(s) = std::str::from_utf8(payload) {
                        if let Some(rest) = s.strip_prefix("133;") {
                            match rest.chars().next() {
                                Some('A') => {
                                    self.events.push(SemanticEvent::PromptStart { row: cursor_row });
                                }
                                Some('B') => {
                                    self.events.push(SemanticEvent::CommandStart { row: cursor_row });
                                }
                                Some('C') => {
                                    self.events.push(SemanticEvent::OutputStart { row: cursor_row });
                                }
                                Some('D') => {
                                    let exit_code = rest.get(2..).and_then(|s| {
                                        s.trim_start_matches(';').parse::<i32>().ok()
                                    });
                                    self.events.push(SemanticEvent::CommandEnd {
                                        row: cursor_row,
                                        exit_code,
                                    });
                                }
                                _ => {}
                            }
                        } else if let Some(rest) = s.strip_prefix("7;") {
                            // OSC 7: CWD reporting
                            if let Some(path) = rest.strip_prefix("file://") {
                                // Strip hostname: file://hostname/path
                                if let Some(slash) = path.find('/') {
                                    self.events.push(SemanticEvent::CwdChanged(PathBuf::from(
                                        &path[slash..],
                                    )));
                                }
                            }
                        }
                    }
                    i += end + 1;
                    continue;
                }
            }
            i += 1;
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
    ///
    /// # Errors
    ///
    /// Returns [`TerminalError`] if the PTY kernel size cannot be updated.
    pub fn resize(&mut self, cols: u16, rows: u16) -> Result<(), TerminalError> {
        self.pty.resize(cols, rows)?;
        self.cols = cols;
        self.rows = rows;
        self.state.resize(cols as usize, rows as usize);
        self.dirty = true;
        Ok(())
    }

    /// Drain semantic events collected during the most recent PTY processing pass.
    pub fn drain_semantic_events(&mut self) -> Vec<SemanticEvent> {
        std::mem::take(&mut self.events)
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
