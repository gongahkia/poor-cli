//! Terminal state: wraps alacritty_terminal::Term for terminal emulation.

use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use alacritty_terminal::event::{Event, EventListener};
use alacritty_terminal::grid::{Dimensions, Grid, Scroll};
use alacritty_terminal::index::{Column, Line};
use alacritty_terminal::term::cell::{Cell, Flags};
use alacritty_terminal::term::test::TermSize;
use alacritty_terminal::term::{self, Config, Term};
use alacritty_terminal::vte::ansi::{self, Color};

/// Collected events from the terminal emulator.
#[derive(Debug, Clone)]
pub enum TermEvent {
    /// Window title changed.
    TitleChanged(String),
    /// Bell character received.
    Bell,
    /// Terminal exited.
    Exit,
    /// Child process exited.
    ChildExit(i32),
    /// Clipboard store request.
    ClipboardStore(String),
    /// Cursor blinking state changed.
    CursorBlinkingChange,
    /// Write bytes to PTY.
    PtyWrite(String),
}

/// Stable row index within the terminal buffer, including scrollback.
pub type AbsoluteRow = usize;

/// Text snapshot for a single terminal row.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TerminalTextRow {
    /// Absolute row index within the terminal buffer.
    pub absolute_row: AbsoluteRow,
    /// Viewport-relative row if this line is currently visible.
    pub viewport_row: Option<usize>,
    /// Rendered text for the row with trailing spaces trimmed.
    pub text: String,
}

/// Event listener that collects events into a shared vec.
#[derive(Clone)]
pub struct WalkEventListener {
    events: Arc<Mutex<Vec<TermEvent>>>,
}

impl WalkEventListener {
    /// Create a new event listener.
    pub fn new() -> Self {
        Self {
            events: Arc::new(Mutex::new(Vec::new())),
        }
    }

    /// Drain all collected events.
    pub fn drain_events(&self) -> Vec<TermEvent> {
        let mut events = self.events.lock().unwrap();
        std::mem::take(&mut *events)
    }
}

impl Default for WalkEventListener {
    fn default() -> Self {
        Self::new()
    }
}

impl EventListener for WalkEventListener {
    fn send_event(&self, event: Event) {
        let mut events = self.events.lock().unwrap();
        match event {
            Event::Title(title) => events.push(TermEvent::TitleChanged(title)),
            Event::Bell => events.push(TermEvent::Bell),
            Event::Exit => events.push(TermEvent::Exit),
            Event::ChildExit(code) => events.push(TermEvent::ChildExit(code)),
            Event::ClipboardStore(_, text) => events.push(TermEvent::ClipboardStore(text)),
            Event::CursorBlinkingChange => events.push(TermEvent::CursorBlinkingChange),
            Event::PtyWrite(text) => events.push(TermEvent::PtyWrite(text)),
            _ => {}
        }
    }
}

/// Wraps alacritty_terminal's Term with a VTE parser for byte processing.
pub struct TerminalState {
    /// The alacritty terminal emulator.
    term: Term<WalkEventListener>,
    /// VTE byte parser.
    parser: ansi::Processor,
    /// Event listener for collecting events.
    listener: WalkEventListener,
    /// Current OSC 8 hyperlink context.
    current_hyperlink: Option<HyperlinkInfo>,
    /// Explicit OSC 8 hyperlink spans anchored to absolute rows.
    explicit_links: Vec<ExplicitHyperlinkSpan>,
}

/// Hyperlink metadata from OSC 8 sequences.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HyperlinkInfo {
    /// Link target URI.
    pub uri: String,
    /// Optional link id used to group disjoint spans.
    pub id: Option<String>,
    /// Parsed OSC 8 params map.
    pub params: HashMap<String, String>,
}

/// Stored OSC 8 hyperlink span.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExplicitHyperlinkSpan {
    /// Absolute row containing this span.
    pub absolute_row: AbsoluteRow,
    /// Start column (inclusive).
    pub col_start: usize,
    /// End column (exclusive).
    pub col_end: usize,
    /// Link metadata.
    pub link: HyperlinkInfo,
}

impl TerminalState {
    /// Create a new terminal state with the given dimensions.
    pub fn new(cols: usize, rows: usize, scrollback: usize) -> Self {
        let listener = WalkEventListener::new();
        let config = Config {
            scrolling_history: scrollback,
            ..Config::default()
        };
        let size = TermSize::new(cols, rows);
        let term = Term::new(config, &size, listener.clone());
        let parser = ansi::Processor::new();

        Self {
            term,
            parser,
            listener,
            current_hyperlink: None,
            explicit_links: Vec::new(),
        }
    }

    /// Feed raw bytes from the PTY into the terminal emulator.
    pub fn process_bytes(&mut self, bytes: &[u8]) {
        self.parser.advance(&mut self.term, bytes);
    }

    /// Get the terminal grid (for reading cell contents).
    pub fn grid(&self) -> &Grid<Cell> {
        self.term.grid()
    }

    /// Get the terminal mode flags.
    pub fn mode(&self) -> &term::TermMode {
        self.term.mode()
    }

    /// Return whether the terminal is currently in alternate screen mode.
    pub fn is_alt_screen(&self) -> bool {
        self.term.mode().contains(term::TermMode::ALT_SCREEN)
    }

    /// Resize the terminal grid.
    pub fn resize(&mut self, cols: usize, rows: usize) {
        let size = TermSize::new(cols, rows);
        self.term.resize(size);
    }

    /// Drain collected events from the listener.
    pub fn drain_events(&self) -> Vec<TermEvent> {
        self.listener.drain_events()
    }

    /// Get the total number of scrollback lines.
    pub fn scrollback_len(&self) -> usize {
        self.term.grid().history_size()
    }

    /// Scroll the display.
    pub fn scroll_display(&mut self, scroll: alacritty_terminal::grid::Scroll) {
        self.term.scroll_display(scroll);
    }

    /// Get the current viewport display offset into scrollback.
    pub fn display_offset(&self) -> usize {
        self.term.grid().display_offset()
    }

    /// Scroll the display to a concrete offset.
    pub fn set_display_offset(&mut self, offset: usize) {
        let current = self.display_offset();
        if current == offset {
            return;
        }

        let delta = offset as i32 - current as i32;
        self.term.scroll_display(Scroll::Delta(delta));
    }

    /// Get the number of visible screen lines.
    pub fn screen_lines(&self) -> usize {
        self.term.grid().screen_lines()
    }

    /// Get the total number of rows in the buffer, including scrollback.
    pub fn total_rows(&self) -> usize {
        self.scrollback_len() + self.screen_lines()
    }

    /// Get the number of columns.
    pub fn columns(&self) -> usize {
        self.term.grid().columns()
    }

    /// Get the cursor position as (column, row).
    pub fn cursor_position(&self) -> (usize, usize) {
        let point = self.term.grid().cursor.point;
        (point.column.0, point.line.0 as usize)
    }

    /// Get the cursor row as an absolute row index in the terminal buffer.
    pub fn absolute_cursor_row(&self) -> AbsoluteRow {
        self.scrollback_len() + self.term.grid().cursor.point.line.0 as usize
    }

    /// Get the absolute row at the top of the current viewport.
    pub fn visible_start_row(&self) -> AbsoluteRow {
        self.scrollback_len().saturating_sub(self.display_offset())
    }

    /// Convert a viewport-relative row to an absolute row.
    pub fn viewport_row_to_absolute(&self, viewport_row: usize) -> AbsoluteRow {
        self.visible_start_row() + viewport_row.min(self.screen_lines().saturating_sub(1))
    }

    /// Get all currently visible absolute rows.
    pub fn visible_rows(&self) -> Vec<AbsoluteRow> {
        let start = self.visible_start_row();
        let end = (start + self.screen_lines()).min(self.total_rows());
        (start..end).collect()
    }

    /// Read a cell at the given absolute row and column.
    pub fn cell_at_absolute(&self, absolute_row: AbsoluteRow, col: usize) -> CellRenderData {
        let grid = self.term.grid();
        let line = self.absolute_row_to_grid_line(absolute_row);
        let column = Column(col.min(grid.columns().saturating_sub(1)));
        let cell = &grid[line][column];

        CellRenderData {
            character: cell.c,
            fg: color_to_rgba(&cell.fg),
            bg: color_to_rgba(&cell.bg),
            is_inverse: cell.flags.contains(Flags::INVERSE),
            is_bold: cell.flags.contains(Flags::BOLD),
            is_italic: cell.flags.contains(Flags::ITALIC),
            is_underline: cell.flags.contains(Flags::UNDERLINE),
        }
    }

    /// Read the rendered text for a specific absolute row.
    pub fn row_text(&self, absolute_row: AbsoluteRow) -> String {
        self.row_slice(absolute_row, 0, self.columns())
            .trim_end_matches(' ')
            .to_string()
    }

    /// Read a column slice from a specific absolute row.
    pub fn row_slice(&self, absolute_row: AbsoluteRow, start_col: usize, end_col: usize) -> String {
        let end_col = end_col.min(self.columns());
        let mut text = String::new();

        for col in start_col..end_col {
            let ch = self.cell_at_absolute(absolute_row, col).character;
            text.push(if ch == '\0' { ' ' } else { ch });
        }

        text
    }

    /// Snapshot all text rows in the buffer.
    pub fn text_rows(&self) -> Vec<TerminalTextRow> {
        let visible_start = self.visible_start_row();
        let visible_end = visible_start + self.screen_lines();

        (0..self.total_rows())
            .map(|absolute_row| TerminalTextRow {
                absolute_row,
                viewport_row: if (visible_start..visible_end).contains(&absolute_row) {
                    Some(absolute_row - visible_start)
                } else {
                    None
                },
                text: self.row_text(absolute_row),
            })
            .collect()
    }

    /// Read a cell at the given (row, col) and return its rendering data.
    pub fn cell_at(&self, row: usize, col: usize) -> CellRenderData {
        self.cell_at_absolute(self.viewport_row_to_absolute(row), col)
    }

    fn absolute_row_to_grid_line(&self, absolute_row: AbsoluteRow) -> Line {
        let history = self.scrollback_len() as i32;
        let clamped = absolute_row.min(self.total_rows().saturating_sub(1)) as i32;
        Line(clamped - history)
    }

    /// Set or clear the active OSC 8 hyperlink context.
    pub fn set_current_hyperlink(&mut self, hyperlink: Option<HyperlinkInfo>) {
        self.current_hyperlink = hyperlink;
    }

    /// Return the currently active OSC 8 hyperlink context.
    pub fn current_hyperlink(&self) -> Option<&HyperlinkInfo> {
        self.current_hyperlink.as_ref()
    }

    /// Record one OSC 8 span in absolute terminal coordinates.
    pub fn record_hyperlink_span(
        &mut self,
        absolute_row: AbsoluteRow,
        col_start: usize,
        col_end: usize,
    ) {
        if col_end <= col_start {
            return;
        }
        let Some(link) = self.current_hyperlink.clone() else {
            return;
        };

        self.explicit_links.push(ExplicitHyperlinkSpan {
            absolute_row,
            col_start,
            col_end,
            link,
        });
    }

    /// Return the explicit hyperlink at the given absolute row/column, if any.
    pub fn explicit_link_at(
        &self,
        absolute_row: AbsoluteRow,
        column: usize,
    ) -> Option<&HyperlinkInfo> {
        self.explicit_links
            .iter()
            .rev()
            .find(|span| {
                span.absolute_row == absolute_row
                    && (span.col_start..span.col_end).contains(&column)
            })
            .map(|span| &span.link)
    }

    /// Return all explicit link spans currently known for one row.
    pub fn explicit_links_on_row(&self, absolute_row: AbsoluteRow) -> Vec<&ExplicitHyperlinkSpan> {
        self.explicit_links
            .iter()
            .filter(|span| span.absolute_row == absolute_row)
            .collect()
    }
}

/// Rendering data for a single terminal cell.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CellRenderData {
    /// The character in this cell.
    pub character: char,
    /// Foreground color as [r, g, b, a] in 0-255 range (or named).
    pub fg: CellColor,
    /// Background color.
    pub bg: CellColor,
    /// Whether fg/bg should be swapped.
    pub is_inverse: bool,
    /// Bold flag.
    pub is_bold: bool,
    /// Italic flag.
    pub is_italic: bool,
    /// Underline flag.
    pub is_underline: bool,
}

/// A color resolved from the terminal, abstracting over Named/Indexed/Spec.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CellColor {
    /// A named ANSI color index (0-15 for standard, 256=fg, 257=bg).
    Named(u8),
    /// An indexed 256-color palette entry.
    Indexed(u8),
    /// A direct RGB color.
    Rgb(u8, u8, u8),
}

fn color_to_rgba(color: &Color) -> CellColor {
    match color {
        Color::Named(named) => CellColor::Named(*named as u8),
        Color::Indexed(idx) => CellColor::Indexed(*idx),
        Color::Spec(rgb) => CellColor::Rgb(rgb.r, rgb.g, rgb.b),
    }
}
