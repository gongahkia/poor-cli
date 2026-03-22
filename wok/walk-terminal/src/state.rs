//! Terminal state: wraps alacritty_terminal::Term for terminal emulation.

use std::sync::{Arc, Mutex};

use alacritty_terminal::event::{Event, EventListener};
use alacritty_terminal::grid::{Dimensions, Grid};
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

    /// Get the number of visible screen lines.
    pub fn screen_lines(&self) -> usize {
        self.term.grid().screen_lines()
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

    /// Read a cell at the given (row, col) and return its rendering data.
    pub fn cell_at(&self, row: usize, col: usize) -> CellRenderData {
        let grid = self.term.grid();
        let line = Line(row as i32);
        let column = Column(col);
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
}

/// Rendering data for a single terminal cell.
#[derive(Debug, Clone, Copy)]
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
#[derive(Debug, Clone, Copy)]
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
