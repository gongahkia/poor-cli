//! Terminal: connects the PTY async reader to alacritty_terminal.

use std::collections::HashMap;
use std::path::Path;
use std::path::PathBuf;

use thiserror::Error;
use tracing::{debug, instrument};

use crate::async_io::{PtyEvent, PtyIoHandle};
use crate::pty::{PtyError, PtyManager};
use crate::shell::ShellType;
use crate::state::{AbsoluteRow, HyperlinkInfo, TermEvent, TerminalState};

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
    /// Command text captured from shell integration before execution.
    CommandText {
        /// Absolute row associated with the command start.
        row: AbsoluteRow,
        /// The shell command text.
        text: String,
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
        cwd: Option<&Path>,
    ) -> Result<Self, TerminalError> {
        let manager = PtyManager::new();
        let spawned = manager.spawn(shell, cols, rows, &env, cwd)?;
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
        let mut i = 0;
        let mut absolute_row = self.state.absolute_cursor_row();
        let mut col = self.state.cursor_position().0;

        while i < bytes.len() {
            if bytes[i] == 0x1b && bytes.get(i + 1) == Some(&b']') {
                if let Some((payload_end, terminator_len)) = find_osc_terminator(bytes, i + 2) {
                    let payload = &bytes[i + 2..payload_end];
                    if let Ok(s) = std::str::from_utf8(payload) {
                        if let Some(rest) = s.strip_prefix("133;") {
                            match rest.chars().next() {
                                Some('A') => {
                                    self.events
                                        .push(SemanticEvent::PromptStart { row: absolute_row });
                                }
                                Some('B') => {
                                    self.events
                                        .push(SemanticEvent::CommandStart { row: absolute_row });
                                }
                                Some('E') => {
                                    self.events.push(SemanticEvent::CommandText {
                                        row: absolute_row,
                                        text: rest.get(2..).unwrap_or_default().to_string(),
                                    });
                                }
                                Some('C') => {
                                    self.events
                                        .push(SemanticEvent::OutputStart { row: absolute_row });
                                }
                                Some('D') => {
                                    let exit_code = rest.get(2..).and_then(|value| {
                                        value.trim_start_matches(';').parse::<i32>().ok()
                                    });
                                    self.events.push(SemanticEvent::CommandEnd {
                                        row: absolute_row,
                                        exit_code,
                                    });
                                }
                                _ => {}
                            }
                        } else if let Some(rest) = s.strip_prefix("7;") {
                            if let Some(path) = rest.strip_prefix("file://") {
                                if let Some(slash) = path.find('/') {
                                    self.events.push(SemanticEvent::CwdChanged(PathBuf::from(
                                        &path[slash..],
                                    )));
                                }
                            }
                        } else if let Some(rest) = s.strip_prefix("8;") {
                            let (params, uri) = rest.split_once(';').unwrap_or((rest, ""));
                            if uri.trim().is_empty() {
                                self.state.set_current_hyperlink(None);
                            } else {
                                let parsed = parse_osc8_params(params);
                                let id = parsed.get("id").cloned();
                                self.state.set_current_hyperlink(Some(HyperlinkInfo {
                                    uri: uri.to_string(),
                                    id,
                                    params: parsed,
                                }));
                            }
                        }
                    }
                    i = payload_end + terminator_len;
                    continue;
                }
            }

            if bytes[i] == b'\n' {
                absolute_row = absolute_row.saturating_add(1);
                col = 0;
                i += 1;
                continue;
            }
            if bytes[i] == b'\r' {
                col = 0;
                i += 1;
                continue;
            }
            if bytes[i].is_ascii_control() {
                i += 1;
                continue;
            }

            let span_start = col;
            while i < bytes.len()
                && !bytes[i].is_ascii_control()
                && !(bytes[i] == 0x1b && bytes.get(i + 1) == Some(&b']'))
            {
                col = col.saturating_add(1);
                i += 1;
            }
            if self.state.current_hyperlink().is_some() && col > span_start {
                self.state
                    .record_hyperlink_span(absolute_row, span_start, col);
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

    /// Restore plain-text terminal history into the emulator buffer.
    pub fn restore_scrollback(&mut self, lines: &[String]) {
        if lines.is_empty() {
            return;
        }

        let mut bytes = Vec::new();
        for (index, line) in lines.iter().enumerate() {
            bytes.extend_from_slice(line.as_bytes());
            if index + 1 != lines.len() {
                bytes.extend_from_slice(b"\r\n");
            }
        }

        self.state.process_bytes(&bytes);
        self.dirty = true;
    }

    /// Restore the viewport scroll position.
    pub fn restore_display_offset(&mut self, offset: usize) {
        self.state.set_display_offset(offset);
        self.dirty = true;
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

fn find_osc_terminator(bytes: &[u8], start: usize) -> Option<(usize, usize)> {
    let mut idx = start;
    while idx < bytes.len() {
        if bytes[idx] == 0x07 {
            return Some((idx, 1));
        }
        if bytes[idx] == 0x1b && bytes.get(idx + 1) == Some(&b'\\') {
            return Some((idx, 2));
        }
        idx += 1;
    }
    None
}

fn parse_osc8_params(params: &str) -> HashMap<String, String> {
    let mut parsed = HashMap::new();
    for token in params
        .split(':')
        .flat_map(|segment| segment.split(';'))
        .filter(|segment| !segment.trim().is_empty())
    {
        if let Some((key, value)) = token.split_once('=') {
            parsed.insert(key.trim().to_string(), value.trim().to_string());
        }
    }
    parsed
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_osc8_params_extracts_id() {
        let params = parse_osc8_params("id=abc123:foo=bar");
        assert_eq!(params.get("id"), Some(&"abc123".to_string()));
        assert_eq!(params.get("foo"), Some(&"bar".to_string()));
    }

    #[test]
    fn test_find_osc_terminator_supports_bel_and_st() {
        let bel = b"\x1b]8;;https://example.com\x07";
        let st = b"\x1b]8;;https://example.com\x1b\\";
        assert_eq!(find_osc_terminator(bel, 2), Some((24, 1)));
        assert_eq!(find_osc_terminator(st, 2), Some((24, 2)));
    }
}
