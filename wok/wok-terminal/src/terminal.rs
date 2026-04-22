//! Terminal: connects the PTY async reader to alacritty_terminal.

use std::collections::HashMap;
use std::fs;
use std::path::Path;
use std::path::PathBuf;

use base64::Engine;
use thiserror::Error;
use tracing::{debug, instrument, warn};

use crate::async_io::{PtyEvent, PtyIoHandle, WakeCallback};
use crate::pty::{PtyError, PtyManager};
use crate::shell::ShellType;
use crate::sixel;
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
    /// Inline image protocol event.
    InlineImage(InlineImageEvent),
}

/// Inline image operations emitted by supported graphics protocols.
#[derive(Debug, Clone)]
pub enum InlineImageEvent {
    /// Store or replace decoded RGBA image data at a placement.
    Put {
        /// Image id.
        image_id: u32,
        /// RGBA width.
        width: u32,
        /// RGBA height.
        height: u32,
        /// RGBA8 pixels.
        pixels: Vec<u8>,
        /// Absolute row anchor.
        row: usize,
        /// Column anchor.
        col: usize,
        /// Placement width in cells.
        display_cols: u16,
        /// Placement height in cells.
        display_rows: u16,
        /// Protocol placement id.
        placement_id: u32,
    },
    /// Add one placement to an existing image id.
    Place {
        /// Image id.
        image_id: u32,
        /// Absolute row anchor.
        row: usize,
        /// Column anchor.
        col: usize,
        /// Placement width in cells.
        display_cols: u16,
        /// Placement height in cells.
        display_rows: u16,
        /// Protocol placement id.
        placement_id: u32,
    },
    /// Delete one image id or all images when `None`.
    Delete {
        /// Optional image id.
        image_id: Option<u32>,
        /// Optional placement id.
        placement_id: Option<u32>,
    },
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
    kitty_chunks: HashMap<u32, String>,
    next_inline_image_id: u32,
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
        Self::new_with_wake_callback(shell, cols, rows, scrollback, env, cwd, None)
    }

    /// Create a new terminal session with a runtime wake callback.
    ///
    /// # Errors
    ///
    /// Returns [`TerminalError`] if the PTY cannot be created or the shell
    /// cannot be spawned.
    #[instrument(skip(env, wake_callback), fields(%shell, cols, rows))]
    pub fn new_with_wake_callback(
        shell: &ShellType,
        cols: u16,
        rows: u16,
        scrollback: usize,
        env: HashMap<String, String>,
        cwd: Option<&Path>,
        wake_callback: Option<WakeCallback>,
    ) -> Result<Self, TerminalError> {
        let manager = PtyManager::new();
        let spawned = manager.spawn(shell, cols, rows, &env, cwd)?;
        let pty = PtyIoHandle::new_with_wake_callback(spawned, wake_callback);
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
            kitty_chunks: HashMap::new(),
            next_inline_image_id: 1,
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
    #[allow(clippy::too_many_lines)]
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
            if bytes[i] == 0x1b && bytes.get(i + 1) == Some(&b'_') {
                if let Some((payload_end, terminator_len)) = find_apc_terminator(bytes, i + 2) {
                    let payload = &bytes[i + 2..payload_end];
                    if let Ok(payload) = std::str::from_utf8(payload) {
                        if let Some(inline_event) = self.parse_kitty_apc(payload, absolute_row, col)
                        {
                            self.events.push(SemanticEvent::InlineImage(inline_event));
                        }
                    } else {
                        warn!("ignoring non-utf8 APC payload");
                    }
                    i = payload_end + terminator_len;
                    continue;
                }
            }
            if bytes[i] == 0x1b && bytes.get(i + 1) == Some(&b'P') {
                if let Some((payload_end, terminator_len)) = find_dcs_terminator(bytes, i + 2) {
                    let payload = &bytes[i + 2..payload_end];
                    if let Ok(payload) = std::str::from_utf8(payload) {
                        match sixel::parse_sixel_dcs(payload) {
                            Ok(image) => {
                                let image_id = self.next_inline_image_id;
                                self.next_inline_image_id =
                                    self.next_inline_image_id.saturating_add(1);
                                let (display_cols, display_rows) =
                                    sixel_display_size(image.width, image.height);
                                self.events.push(SemanticEvent::InlineImage(
                                    InlineImageEvent::Put {
                                        image_id,
                                        width: image.width,
                                        height: image.height,
                                        pixels: image.pixels,
                                        row: absolute_row,
                                        col,
                                        display_cols,
                                        display_rows,
                                        placement_id: 0,
                                    },
                                ));
                                col = col.saturating_add(display_cols as usize);
                            }
                            Err(error) => {
                                warn!("failed to parse sixel payload: {error}");
                            }
                        }
                    } else {
                        warn!("ignoring non-utf8 DCS payload");
                    }
                    i = payload_end + terminator_len;
                    continue;
                }
            }
            if bytes[i] == 0x1b && bytes.get(i + 1) == Some(&b'[') {
                if let Some(csi_end) = find_csi_terminator(bytes, i + 2) {
                    if bytes[csi_end] == b'u' {
                        match std::str::from_utf8(&bytes[i + 2..csi_end]) {
                            Ok(params) => match parse_kitty_keyboard_control(params) {
                                Some(KittyKeyboardControl::Query) => {
                                    let reply =
                                        format!("\x1b[?{}u", self.state.kitty_keyboard_flags());
                                    if let Err(error) = self.send_input(reply.as_bytes()) {
                                        warn!("failed to reply to kitty keyboard query: {error}");
                                    }
                                }
                                Some(KittyKeyboardControl::Push(flags)) => {
                                    self.state.push_kitty_keyboard_flags(flags);
                                }
                                Some(KittyKeyboardControl::Pop) => {
                                    self.state.pop_kitty_keyboard_flags();
                                }
                                None => {}
                            },
                            Err(error) => {
                                warn!("ignoring non-utf8 kitty keyboard CSI payload: {error}");
                            }
                        }
                    }
                    i = csi_end + 1;
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

    #[allow(clippy::too_many_lines)]
    fn parse_kitty_apc(
        &mut self,
        payload: &str,
        row: usize,
        col: usize,
    ) -> Option<InlineImageEvent> {
        let payload = payload.trim_start_matches('G');
        let (header, body) = payload.split_once(';').unwrap_or((payload, ""));
        let mut params = HashMap::new();
        for token in header
            .split(',')
            .flat_map(|segment| segment.split(';'))
            .filter(|segment| !segment.trim().is_empty())
        {
            if let Some((key, value)) = token.split_once('=') {
                params.insert(key.trim().to_string(), value.trim().to_string());
            }
        }

        let action = params
            .get("a")
            .map_or("t", String::as_str)
            .chars()
            .next()
            .unwrap_or('t');
        let transmission = params
            .get("t")
            .map_or("d", String::as_str)
            .chars()
            .next()
            .unwrap_or('d');
        let parsed_image_id = params.get("i").and_then(|value| value.parse::<u32>().ok());
        let placement_id = params
            .get("p")
            .and_then(|value| value.parse::<u32>().ok())
            .unwrap_or(0);
        let display_cols = params
            .get("c")
            .and_then(|value| value.parse::<u16>().ok())
            .unwrap_or(1);
        let display_rows = params
            .get("r")
            .and_then(|value| value.parse::<u16>().ok())
            .unwrap_or(1);

        match action {
            'd' => {
                let placement_id = params.get("p").and_then(|value| value.parse::<u32>().ok());
                Some(InlineImageEvent::Delete {
                    image_id: parsed_image_id,
                    placement_id,
                })
            }
            'p' => {
                let Some(image_id) = parsed_image_id else {
                    warn!("ignoring kitty display action without image id");
                    return None;
                };
                Some(InlineImageEvent::Place {
                    image_id,
                    row,
                    col,
                    display_cols,
                    display_rows,
                    placement_id,
                })
            }
            _ => {
                let image_id = parsed_image_id.unwrap_or_else(|| {
                    let id = self.next_inline_image_id;
                    self.next_inline_image_id = self.next_inline_image_id.saturating_add(1);
                    id
                });
                let more_chunks = params
                    .get("m")
                    .and_then(|value| value.parse::<u8>().ok())
                    .unwrap_or(0)
                    == 1;
                let chunk_buffer = self.kitty_chunks.entry(image_id).or_default();
                chunk_buffer.push_str(body);
                if more_chunks {
                    return None;
                }
                let encoded = self.kitty_chunks.remove(&image_id).unwrap_or_default();

                let format = params
                    .get("f")
                    .and_then(|value| value.parse::<u32>().ok())
                    .unwrap_or(100);
                let source_width = params
                    .get("s")
                    .and_then(|value| value.parse::<u32>().ok())
                    .unwrap_or(1);
                let source_height = params
                    .get("v")
                    .and_then(|value| value.parse::<u32>().ok())
                    .unwrap_or(1);

                let (width, height, pixels) = match decode_kitty_image_data(
                    format,
                    transmission,
                    &encoded,
                    source_width,
                    source_height,
                ) {
                    Ok(decoded) => decoded,
                    Err(error) => {
                        warn!(
                            "failed to decode kitty inline image id={image_id}, action={action}, transmission={transmission}: {error}"
                        );
                        return None;
                    }
                };
                Some(InlineImageEvent::Put {
                    image_id,
                    width,
                    height,
                    pixels,
                    row,
                    col,
                    display_cols,
                    display_rows,
                    placement_id,
                })
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

fn find_apc_terminator(bytes: &[u8], start: usize) -> Option<(usize, usize)> {
    let mut idx = start;
    while idx < bytes.len() {
        if bytes[idx] == 0x1b && bytes.get(idx + 1) == Some(&b'\\') {
            return Some((idx, 2));
        }
        idx += 1;
    }
    None
}

fn find_dcs_terminator(bytes: &[u8], start: usize) -> Option<(usize, usize)> {
    let mut idx = start;
    while idx < bytes.len() {
        if bytes[idx] == 0x1b && bytes.get(idx + 1) == Some(&b'\\') {
            return Some((idx, 2));
        }
        if bytes[idx] == 0x9c {
            return Some((idx, 1));
        }
        idx += 1;
    }
    None
}

fn find_csi_terminator(bytes: &[u8], start: usize) -> Option<usize> {
    let mut idx = start;
    while idx < bytes.len() {
        let byte = bytes[idx];
        if (0x40..=0x7e).contains(&byte) {
            return Some(idx);
        }
        idx += 1;
    }
    None
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum KittyKeyboardControl {
    Query,
    Push(u32),
    Pop,
}

fn parse_kitty_keyboard_control(params: &str) -> Option<KittyKeyboardControl> {
    let trimmed = params.trim();
    match trimmed {
        "?" => Some(KittyKeyboardControl::Query),
        "<" => Some(KittyKeyboardControl::Pop),
        _ => {
            let rest = trimmed.strip_prefix('>')?;
            let flags_text = rest.split(';').next().unwrap_or_default().trim();
            if flags_text.is_empty() {
                return Some(KittyKeyboardControl::Push(0));
            }
            match flags_text.parse::<u32>() {
                Ok(flags) => Some(KittyKeyboardControl::Push(flags)),
                Err(error) => {
                    warn!("ignoring invalid kitty keyboard flags '{flags_text}': {error}");
                    None
                }
            }
        }
    }
}

fn decode_kitty_image_data(
    format: u32,
    transmission: char,
    encoded: &str,
    source_width: u32,
    source_height: u32,
) -> Result<(u32, u32, Vec<u8>), String> {
    let bytes = match transmission {
        'd' => base64::engine::general_purpose::STANDARD
            .decode(encoded.as_bytes())
            .map_err(|error| format!("invalid kitty base64 payload: {error}"))?,
        'f' | 't' => {
            let path = parse_kitty_file_path(encoded)?;
            let bytes = fs::read(&path).map_err(|error| {
                format!(
                    "failed to read kitty image file {}: {error}",
                    path.display()
                )
            })?;
            if transmission == 't' {
                if let Err(error) = fs::remove_file(&path) {
                    warn!("failed to remove kitty temp image {path:?}: {error}");
                }
            }
            bytes
        }
        other => {
            return Err(format!(
                "unsupported kitty transmission mode '{other}' (expected d/f/t)"
            ));
        }
    };

    match format {
        24 => {
            let width = source_width.max(1);
            let height = source_height.max(1);
            let expected = (width as usize)
                .saturating_mul(height as usize)
                .saturating_mul(3);
            if bytes.len() < expected {
                return Err("kitty RGB payload shorter than declared dimensions".to_string());
            }
            let mut rgba = Vec::with_capacity((width as usize) * (height as usize) * 4);
            for chunk in bytes[..expected].chunks_exact(3) {
                rgba.push(chunk[0]);
                rgba.push(chunk[1]);
                rgba.push(chunk[2]);
                rgba.push(255);
            }
            Ok((width, height, rgba))
        }
        32 => {
            let width = source_width.max(1);
            let height = source_height.max(1);
            let expected = (width as usize)
                .saturating_mul(height as usize)
                .saturating_mul(4);
            if bytes.len() < expected {
                return Err("kitty RGBA payload shorter than declared dimensions".to_string());
            }
            Ok((width, height, bytes[..expected].to_vec()))
        }
        100 => {
            let image = image::load_from_memory(&bytes)
                .map_err(|error| format!("failed to decode kitty image payload: {error}"))?
                .to_rgba8();
            Ok((image.width(), image.height(), image.into_raw()))
        }
        other => Err(format!(
            "unsupported kitty format '{other}' (expected 24/32/100)"
        )),
    }
}

fn parse_kitty_file_path(encoded: &str) -> Result<PathBuf, String> {
    let decoded = base64::engine::general_purpose::STANDARD
        .decode(encoded.as_bytes())
        .ok()
        .and_then(|bytes| String::from_utf8(bytes).ok())
        .unwrap_or_else(|| encoded.to_string());
    let cleaned = decoded.trim_matches('\0').trim();
    if cleaned.is_empty() {
        return Err("empty kitty file transmission path".to_string());
    }
    Ok(PathBuf::from(cleaned))
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

fn sixel_display_size(width: u32, height: u32) -> (u16, u16) {
    const CELL_PIXEL_WIDTH: u32 = 8;
    const CELL_PIXEL_HEIGHT: u32 = 16;

    let cols = width.div_ceil(CELL_PIXEL_WIDTH).max(1);
    let rows = height.div_ceil(CELL_PIXEL_HEIGHT).max(1);
    (
        cols.min(u32::from(u16::MAX)) as u16,
        rows.min(u32::from(u16::MAX)) as u16,
    )
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

    #[test]
    fn test_sixel_display_size_rounds_up_cells() {
        assert_eq!(sixel_display_size(1, 1), (1, 1));
        assert_eq!(sixel_display_size(16, 32), (2, 2));
        assert_eq!(sixel_display_size(17, 33), (3, 3));
    }

    #[test]
    fn test_parse_kitty_file_path_accepts_raw_and_base64() {
        let raw = parse_kitty_file_path("/tmp/a.png").expect("raw path");
        assert_eq!(raw, PathBuf::from("/tmp/a.png"));

        let encoded = base64::engine::general_purpose::STANDARD.encode("/tmp/b.png");
        let decoded = parse_kitty_file_path(&encoded).expect("base64 path");
        assert_eq!(decoded, PathBuf::from("/tmp/b.png"));
    }

    #[test]
    fn test_parse_kitty_keyboard_control_variants() {
        assert_eq!(
            parse_kitty_keyboard_control("?"),
            Some(KittyKeyboardControl::Query)
        );
        assert_eq!(
            parse_kitty_keyboard_control("<"),
            Some(KittyKeyboardControl::Pop)
        );
        assert_eq!(
            parse_kitty_keyboard_control(">5"),
            Some(KittyKeyboardControl::Push(5))
        );
        assert_eq!(
            parse_kitty_keyboard_control(">5;1"),
            Some(KittyKeyboardControl::Push(5))
        );
    }

    #[test]
    fn test_parse_kitty_keyboard_control_rejects_invalid_flags() {
        assert_eq!(parse_kitty_keyboard_control(">abc"), None);
        assert_eq!(parse_kitty_keyboard_control(""), None);
    }
}
