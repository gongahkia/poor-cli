//! Universal input surface — one buffer, one cursor, multiple modes.
//!
//! Rather than the current trio of near-duplicate buffers (shell input,
//! command palette, search), an [`InputSurface`] owns a single text buffer +
//! cursor and exposes a [`SurfaceMode`] tag that callers route on. The
//! palette / search / find views become thin presenters over the same state.
//!
//! The state machine is deliberately tiny and operates on bytes-as-chars.
//! Heavy editor concerns (gap buffer, undo stack, syntax highlight) stay in
//! `editor.rs`; consumers can mount an `editor::Editor` *inside* a surface
//! when they need them.
//!
//! Pure: no I/O, no allocation beyond the returned action list.

use std::collections::HashMap;

/// Surface mode — selects which routing the application performs on
/// `Submit` / `Cancel` and which view paints the buffer.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum SurfaceMode {
    /// Shell command line.
    Shell,
    /// Command palette (action picker).
    Palette,
    /// Output search (regex / literal across blocks).
    Search,
    /// In-line find within current block.
    Find,
}

/// Action emitted to the caller.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SurfaceAction {
    /// Buffer text changed.
    Changed,
    /// Submit current buffer (Enter).
    Submit {
        /// Active mode at submit time.
        mode: SurfaceMode,
        /// Buffer contents (cloned for the consumer).
        text: String,
    },
    /// Cancel current operation (Esc). Mode-specific cleanup belongs to the caller.
    Cancel {
        /// Active mode at cancel time.
        mode: SurfaceMode,
    },
    /// Mode changed.
    ModeChanged {
        /// The mode now active.
        mode: SurfaceMode,
    },
}

/// One per-mode buffer slot.
#[derive(Debug, Clone, Default)]
struct ModeSlot {
    text: String,
    cursor: usize,
}

/// Universal input surface. One value per process; route input via mode.
#[derive(Debug, Clone)]
pub struct InputSurface {
    mode: SurfaceMode,
    slots: HashMap<SurfaceMode, ModeSlot>,
}

impl Default for InputSurface {
    fn default() -> Self {
        Self::new(SurfaceMode::Shell)
    }
}

impl InputSurface {
    /// Build a surface starting in `mode`.
    pub fn new(mode: SurfaceMode) -> Self {
        let mut slots = HashMap::new();
        for m in [
            SurfaceMode::Shell,
            SurfaceMode::Palette,
            SurfaceMode::Search,
            SurfaceMode::Find,
        ] {
            slots.insert(m, ModeSlot::default());
        }
        Self { mode, slots }
    }

    /// Active mode.
    pub fn mode(&self) -> SurfaceMode {
        self.mode
    }

    /// Switch mode (preserves per-mode buffers). Returns a `ModeChanged`
    /// action.
    pub fn set_mode(&mut self, mode: SurfaceMode) -> Vec<SurfaceAction> {
        if self.mode == mode {
            return Vec::new();
        }
        self.mode = mode;
        vec![SurfaceAction::ModeChanged { mode }]
    }

    /// Borrow active buffer text.
    pub fn text(&self) -> &str {
        self.slot().text.as_str()
    }

    /// Cursor byte position in the active buffer.
    pub fn cursor(&self) -> usize {
        self.slot().cursor
    }

    /// Replace the active buffer (cursor moves to end).
    pub fn set_text(&mut self, text: impl Into<String>) -> Vec<SurfaceAction> {
        let s = text.into();
        let slot = self.slot_mut();
        slot.cursor = s.len();
        slot.text = s;
        vec![SurfaceAction::Changed]
    }

    /// Insert one character at the cursor.
    pub fn insert_char(&mut self, c: char) -> Vec<SurfaceAction> {
        let mut buf = [0u8; 4];
        let s = c.encode_utf8(&mut buf);
        let slot = self.slot_mut();
        slot.text.insert_str(slot.cursor, s);
        slot.cursor += s.len();
        vec![SurfaceAction::Changed]
    }

    /// Delete the character to the left of the cursor.
    pub fn backspace(&mut self) -> Vec<SurfaceAction> {
        let slot = self.slot_mut();
        if slot.cursor == 0 {
            return Vec::new();
        }
        // step back one char boundary
        let mut new_cursor = slot.cursor - 1;
        while new_cursor > 0 && !slot.text.is_char_boundary(new_cursor) {
            new_cursor -= 1;
        }
        slot.text.replace_range(new_cursor..slot.cursor, "");
        slot.cursor = new_cursor;
        vec![SurfaceAction::Changed]
    }

    /// Move cursor by `delta` bytes (clamped to buffer + char boundaries).
    pub fn move_cursor(&mut self, delta: isize) -> Vec<SurfaceAction> {
        let slot = self.slot_mut();
        let mut new_cursor =
            (slot.cursor as isize + delta).clamp(0, slot.text.len() as isize) as usize;
        // step to nearest valid char boundary in delta direction
        if delta >= 0 {
            while new_cursor < slot.text.len() && !slot.text.is_char_boundary(new_cursor) {
                new_cursor += 1;
            }
        } else {
            while new_cursor > 0 && !slot.text.is_char_boundary(new_cursor) {
                new_cursor -= 1;
            }
        }
        slot.cursor = new_cursor;
        Vec::new()
    }

    /// Submit current buffer; returns a `Submit` action and clears the buffer.
    pub fn submit(&mut self) -> Vec<SurfaceAction> {
        let mode = self.mode;
        let slot = self.slot_mut();
        let text = std::mem::take(&mut slot.text);
        slot.cursor = 0;
        vec![SurfaceAction::Submit { mode, text }]
    }

    /// Cancel current operation; returns a `Cancel` action and clears the
    /// buffer.
    pub fn cancel(&mut self) -> Vec<SurfaceAction> {
        let mode = self.mode;
        let slot = self.slot_mut();
        slot.text.clear();
        slot.cursor = 0;
        vec![SurfaceAction::Cancel { mode }]
    }

    fn slot(&self) -> &ModeSlot {
        self.slots
            .get(&self.mode)
            .expect("slot map covers every variant")
    }

    fn slot_mut(&mut self) -> &mut ModeSlot {
        self.slots
            .get_mut(&self.mode)
            .expect("slot map covers every variant")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_starts_in_shell_mode() {
        let s = InputSurface::default();
        assert_eq!(s.mode(), SurfaceMode::Shell);
        assert!(s.text().is_empty());
    }

    #[test]
    fn insert_char_appends_at_cursor() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        let acts = s.insert_char('l');
        assert_eq!(acts, vec![SurfaceAction::Changed]);
        s.insert_char('s');
        assert_eq!(s.text(), "ls");
        assert_eq!(s.cursor(), 2);
    }

    #[test]
    fn backspace_at_start_is_noop() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        assert!(s.backspace().is_empty());
    }

    #[test]
    fn backspace_handles_multibyte_chars() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        s.insert_char('é');
        s.insert_char('a');
        assert_eq!(s.text(), "éa");
        s.backspace();
        assert_eq!(s.text(), "é");
        s.backspace();
        assert_eq!(s.text(), "");
    }

    #[test]
    fn switch_mode_emits_change_and_preserves_buffers() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        s.insert_char('a');
        let acts = s.set_mode(SurfaceMode::Palette);
        assert_eq!(
            acts,
            vec![SurfaceAction::ModeChanged {
                mode: SurfaceMode::Palette
            }]
        );
        assert_eq!(s.text(), "");
        s.insert_char('b');
        s.set_mode(SurfaceMode::Shell);
        // shell buffer survived
        assert_eq!(s.text(), "a");
    }

    #[test]
    fn switch_to_same_mode_is_noop() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        assert!(s.set_mode(SurfaceMode::Shell).is_empty());
    }

    #[test]
    fn submit_returns_text_and_clears_buffer() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        s.set_text("ls -la");
        let acts = s.submit();
        assert_eq!(
            acts,
            vec![SurfaceAction::Submit {
                mode: SurfaceMode::Shell,
                text: "ls -la".into(),
            }]
        );
        assert!(s.text().is_empty());
        assert_eq!(s.cursor(), 0);
    }

    #[test]
    fn cancel_clears_buffer() {
        let mut s = InputSurface::new(SurfaceMode::Search);
        s.set_text("abc");
        let acts = s.cancel();
        assert_eq!(
            acts,
            vec![SurfaceAction::Cancel {
                mode: SurfaceMode::Search
            }]
        );
        assert!(s.text().is_empty());
    }

    #[test]
    fn move_cursor_clamps_and_respects_bounds() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        s.set_text("hi");
        s.move_cursor(-100);
        assert_eq!(s.cursor(), 0);
        s.move_cursor(100);
        assert_eq!(s.cursor(), 2);
    }

    #[test]
    fn move_cursor_skips_to_char_boundary() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        s.set_text("é"); // 2 bytes
        s.move_cursor(-1); // would land mid-char, must skip back to 0
        assert_eq!(s.cursor(), 0);
    }

    #[test]
    fn set_text_emits_changed() {
        let mut s = InputSurface::new(SurfaceMode::Shell);
        let acts = s.set_text("hello");
        assert_eq!(acts, vec![SurfaceAction::Changed]);
        assert_eq!(s.cursor(), 5);
    }
}
