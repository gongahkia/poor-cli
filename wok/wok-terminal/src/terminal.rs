//! Terminal: connects the PTY async reader to alacritty_terminal.

use std::collections::HashMap;
use std::path::Path;
use std::path::PathBuf;

use thiserror::Error;
use tracing::{debug, instrument, warn};

use crate::async_io::{PtyEvent, PtyIoHandle, WakeCallback};
use crate::iterm_image::{self, DisplayDim};
use crate::parser::{
    decode_kitty_image_data, find_apc_terminator, find_csi_terminator, find_dcs_terminator,
    find_osc_terminator, parse_kitty_keyboard_control, parse_osc8_params, sixel_display_size,
    KittyKeyboardControl,
};
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
        /// Kitty z-index. Higher values render above lower values.
        z_index: i32,
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
        /// Kitty z-index. Higher values render above lower values.
        z_index: i32,
    },
    /// Delete one image id or all images when `None`.
    Delete {
        /// Optional image id.
        image_id: Option<u32>,
        /// Optional placement id.
        placement_id: Option<u32>,
    },
}

/// Terminal damage accumulated since the last render pass.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TerminalDamage {
    /// The visible terminal viewport should be considered dirty.
    Full,
    /// Viewport-relative terminal rows that should be considered dirty.
    Rows(Vec<usize>),
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
    /// Whether all visible rows should be refreshed.
    full_damage: bool,
    /// Viewport-relative rows with pending damage.
    dirty_visible_rows: Vec<usize>,
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
    pending_escape_bytes: Vec<u8>,
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
            full_damage: false,
            dirty_visible_rows: Vec::new(),
            events: Vec::new(),
            cols,
            rows,
            exited: false,
            exit_code: None,
            pending_escape_bytes: Vec::new(),
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
                    let before_visible_start = self.state.visible_start_row();
                    let before_cursor_row = self.state.absolute_cursor_row();
                    self.scan_osc_markers(&bytes);
                    self.state.process_bytes(&bytes);
                    self.mark_output_damage(before_visible_start, before_cursor_row, &bytes);
                    self.dirty = true;
                    count += 1;
                }
                Some(PtyEvent::Exited(code)) => {
                    self.exited = true;
                    self.exit_code = Some(code);
                    self.dirty = true;
                    self.mark_fully_damaged();
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
                TermEvent::PtyWrite(text) => {
                    if let Err(error) = self.pty.write(text.as_bytes()) {
                        warn!("failed to write terminal response to PTY: {error}");
                    }
                }
                TermEvent::Bell
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
        let pending = std::mem::take(&mut self.pending_escape_bytes);
        if pending.is_empty() {
            self.scan_semantic_sequences(bytes);
        } else {
            let mut combined = pending;
            combined.extend_from_slice(bytes);
            self.scan_semantic_sequences(&combined);
        }
    }

    #[allow(clippy::too_many_lines)]
    fn scan_semantic_sequences(&mut self, bytes: &[u8]) {
        let mut i = 0;
        let mut absolute_row = self.state.absolute_cursor_row();
        let mut col = self.state.cursor_position().0;

        while i < bytes.len() {
            if bytes[i] == 0x1b && bytes.get(i + 1).is_none() {
                self.pending_escape_bytes = bytes[i..].to_vec();
                break;
            }
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
                        } else if let Some(rest) = s.strip_prefix("1337;") {
                            // iTerm2 inline-image protocol.
                            match iterm_image::parse(&format!("File={rest}")) {
                                Ok(payload) if payload.inline => {
                                    if let Ok(decoded) = image::load_from_memory(&payload.bytes)
                                        .map(|img| img.to_rgba8())
                                    {
                                        let (w, h) = (decoded.width(), decoded.height());
                                        let pixels = decoded.into_raw();
                                        let (display_cols, display_rows) =
                                            iterm_display_dims(&payload, w, h);
                                        let image_id = self.next_inline_image_id;
                                        self.next_inline_image_id =
                                            self.next_inline_image_id.saturating_add(1);
                                        self.events.push(SemanticEvent::InlineImage(
                                            InlineImageEvent::Put {
                                                image_id,
                                                width: w,
                                                height: h,
                                                pixels,
                                                row: absolute_row,
                                                col,
                                                display_cols,
                                                display_rows,
                                                placement_id: 0,
                                                z_index: 0,
                                            },
                                        ));
                                    } else {
                                        warn!("failed to decode iTerm 1337 image bytes");
                                    }
                                }
                                Ok(_) => {} // inline=0 — ignore.
                                Err(error) => warn!("ignoring invalid iTerm 1337 payload: {error}"),
                            }
                        }
                    }
                    i = payload_end + terminator_len;
                    continue;
                }
                self.pending_escape_bytes = bytes[i..].to_vec();
                break;
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
                self.pending_escape_bytes = bytes[i..].to_vec();
                break;
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
                                        z_index: 0,
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
                self.pending_escape_bytes = bytes[i..].to_vec();
                break;
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
                self.pending_escape_bytes = bytes[i..].to_vec();
                break;
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
        let z_index = params
            .get("z")
            .and_then(|value| value.parse::<i32>().ok())
            .unwrap_or(0);

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
                    z_index,
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
                    z_index,
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
        self.mark_fully_damaged();
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
        self.mark_fully_damaged();
    }

    /// Restore the viewport scroll position.
    pub fn restore_display_offset(&mut self, offset: usize) {
        self.state.set_display_offset(offset);
        self.dirty = true;
        self.mark_fully_damaged();
    }

    /// Drain semantic events collected during the most recent PTY processing pass.
    pub fn drain_semantic_events(&mut self) -> Vec<SemanticEvent> {
        std::mem::take(&mut self.events)
    }

    /// Check if the terminal has new output to render.
    pub fn is_dirty(&self) -> bool {
        self.dirty
    }

    /// Drain accumulated terminal damage for the next render pass.
    pub fn take_damage(&mut self) -> TerminalDamage {
        if self.full_damage {
            self.full_damage = false;
            self.dirty_visible_rows.clear();
            TerminalDamage::Full
        } else {
            let mut rows = std::mem::take(&mut self.dirty_visible_rows);
            rows.sort_unstable();
            rows.dedup();
            TerminalDamage::Rows(rows)
        }
    }

    /// Mark the terminal as clean (after rendering).
    pub fn mark_clean(&mut self) {
        self.dirty = false;
        self.full_damage = false;
        self.dirty_visible_rows.clear();
    }

    /// Get the current number of columns.
    pub fn cols(&self) -> u16 {
        self.cols
    }

    /// Get the current number of rows.
    pub fn rows(&self) -> u16 {
        self.rows
    }

    fn mark_output_damage(
        &mut self,
        before_visible_start: AbsoluteRow,
        before_cursor_row: AbsoluteRow,
        bytes: &[u8],
    ) {
        if bytes_need_full_damage(bytes) || before_visible_start != self.state.visible_start_row() {
            self.mark_fully_damaged();
            return;
        }

        let after_cursor_row = self.state.absolute_cursor_row();
        let start = before_cursor_row.min(after_cursor_row);
        let end = before_cursor_row.max(after_cursor_row);
        if end.saturating_sub(start) >= self.rows as usize {
            self.mark_fully_damaged();
            return;
        }

        for absolute_row in start..=end {
            self.mark_absolute_row_dirty(absolute_row);
        }
    }

    fn mark_fully_damaged(&mut self) {
        self.full_damage = true;
        self.dirty_visible_rows.clear();
    }

    fn mark_absolute_row_dirty(&mut self, absolute_row: AbsoluteRow) {
        if self.full_damage {
            return;
        }

        let visible_start = self.state.visible_start_row();
        let visible_end = visible_start + self.state.screen_lines();
        if (visible_start..visible_end).contains(&absolute_row) {
            self.dirty_visible_rows
                .push(absolute_row.saturating_sub(visible_start));
        }
    }
}

fn bytes_need_full_damage(bytes: &[u8]) -> bool {
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] != 0x1b {
            i += 1;
            continue;
        }

        match bytes.get(i + 1).copied() {
            Some(b'[') => {
                if let Some(csi_end) = find_csi_terminator(bytes, i + 2) {
                    let final_byte = bytes[csi_end];
                    if final_byte != b'm' && final_byte != b'u' {
                        return true;
                    }
                    i = csi_end + 1;
                    continue;
                }
                return true;
            }
            Some(b']') => {
                if let Some((payload_end, terminator_len)) = find_osc_terminator(bytes, i + 2) {
                    i = payload_end + terminator_len;
                    continue;
                }
                return true;
            }
            Some(_) | None => return true,
        }
    }

    false
}

/// Resolve iTerm 1337 width/height into terminal cells.
fn iterm_display_dims(payload: &iterm_image::ItermImagePayload, w: u32, h: u32) -> (u16, u16) {
    let auto = sixel_display_size(w, h);
    let cols = match payload.width {
        Some(DisplayDim::Cells(n)) => n.min(u32::from(u16::MAX)) as u16,
        Some(DisplayDim::Pixels(p)) => sixel_display_size(p, 1).0,
        Some(DisplayDim::Percent(_)) | Some(DisplayDim::Auto) | None => auto.0,
    };
    let rows = match payload.height {
        Some(DisplayDim::Cells(n)) => n.min(u32::from(u16::MAX)) as u16,
        Some(DisplayDim::Pixels(p)) => sixel_display_size(1, p).1,
        Some(DisplayDim::Percent(_)) | Some(DisplayDim::Auto) | None => auto.1,
    };
    (cols.max(1), rows.max(1))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_damage_detection_keeps_sgr_incremental() {
        assert!(!bytes_need_full_damage(b"hello"));
        assert!(!bytes_need_full_damage(b"\x1b[31mred\x1b[0m"));
        assert!(bytes_need_full_damage(b"\x1b[2J"));
        assert!(bytes_need_full_damage(b"\x1b[H"));
    }

    #[test]
    fn iterm_display_dims_uses_payload_overrides() {
        let mut p = iterm_image::ItermImagePayload::default();
        p.width = Some(DisplayDim::Cells(20));
        p.height = Some(DisplayDim::Cells(5));
        assert_eq!(iterm_display_dims(&p, 100, 100), (20, 5));
    }

    #[test]
    fn iterm_display_dims_falls_back_to_pixel_size_when_auto() {
        let p = iterm_image::ItermImagePayload::default();
        // 16x32 pixels → 2x2 cells (8x16 cell pixels).
        assert_eq!(iterm_display_dims(&p, 16, 32), (2, 2));
    }
}
