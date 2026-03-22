//! Terminal state: wraps alacritty_terminal::Term for terminal emulation.

use std::sync::{Arc, Mutex};

use alacritty_terminal::event::{Event, EventListener};
use alacritty_terminal::grid::{Dimensions, Grid};
use alacritty_terminal::term::cell::Cell;
use alacritty_terminal::term::test::TermSize;
use alacritty_terminal::term::{self, Config, Term};
use alacritty_terminal::vte::ansi;

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
        for &byte in bytes {
            self.parser.advance(&mut self.term, byte);
        }
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
}
