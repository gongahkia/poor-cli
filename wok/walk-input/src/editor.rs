//! Input editor: coordinates buffer, cursor ops, highlighting, and history.

use crate::brackets::find_matching_bracket;
use crate::buffer::InputBuffer;
use crate::cursor_ops;
use crate::highlighter::{self, HighlightSpan};

use walk_terminal::shell::ShellType;

/// Position of the input editor in the UI.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputPosition {
    /// Above the terminal viewport.
    Top,
    /// Below the terminal viewport.
    Bottom,
}

/// Action produced by the editor when handling a key event.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum EditorAction {
    /// User pressed Enter to submit the command.
    Submit(String),
    /// User pressed Ctrl+D on an empty buffer (send EOF).
    SendEof,
    /// No action to take.
    None,
}

/// Key actions the editor understands.
#[derive(Debug, Clone)]
pub enum EditorKey {
    /// A regular character.
    Char(char),
    /// Enter key.
    Enter,
    /// Shift+Enter (insert newline).
    ShiftEnter,
    /// Backspace.
    Backspace,
    /// Delete.
    Delete,
    /// Arrow left.
    Left,
    /// Arrow right.
    Right,
    /// Arrow up.
    Up,
    /// Arrow down.
    Down,
    /// Ctrl+Left (word left).
    WordLeft,
    /// Ctrl+Right (word right).
    WordRight,
    /// Home.
    Home,
    /// End.
    End,
    /// Ctrl+D.
    CtrlD,
    /// Ctrl+U.
    CtrlU,
    /// Escape clears the current draft.
    Escape,
    /// Ctrl+A (select all).
    SelectAll,
    /// Tab.
    Tab,
}

/// Data needed to render the input editor.
#[derive(Debug, Clone)]
pub struct InputRenderData {
    /// Lines of text.
    pub lines: Vec<String>,
    /// Syntax highlight spans.
    pub highlights: Vec<HighlightSpan>,
    /// Cursor positions as (row, col).
    pub cursors: Vec<(usize, usize)>,
    /// Matching bracket position, if any.
    pub bracket_match: Option<(usize, usize)>,
    /// Input position (top or bottom).
    pub position: InputPosition,
}

/// The input editor coordinates all input-related subsystems.
pub struct InputEditor {
    /// Text buffer with gap buffer backing.
    pub buffer: InputBuffer,
    /// Whether the editor is active (receiving input).
    pub is_active: bool,
    /// UI position.
    position: InputPosition,
    /// Shell type for syntax highlighting.
    shell: ShellType,
}

impl InputEditor {
    /// Create a new input editor.
    pub fn new(shell: ShellType, position: InputPosition) -> Self {
        Self {
            buffer: InputBuffer::new(),
            is_active: true,
            position,
            shell,
        }
    }

    /// Handle a key event and return the resulting action.
    pub fn handle_key(&mut self, key: EditorKey) -> EditorAction {
        match key {
            EditorKey::Char(ch) => {
                self.buffer.insert_at(0, &ch.to_string()).ok();
                EditorAction::None
            }
            EditorKey::Enter => {
                let text = self.buffer.text();
                if text.trim().is_empty() {
                    return EditorAction::Submit(String::new());
                }
                self.buffer.clear();
                EditorAction::Submit(text)
            }
            EditorKey::ShiftEnter => {
                self.buffer.insert_at(0, "\n").ok();
                EditorAction::None
            }
            EditorKey::Backspace => {
                let pos = self.buffer.cursors()[0].position;
                if pos > 0 {
                    self.buffer.delete_range(pos - 1, pos).ok();
                }
                EditorAction::None
            }
            EditorKey::Delete => {
                let pos = self.buffer.cursors()[0].position;
                let len = self.buffer.len();
                if pos < len {
                    self.buffer.delete_range(pos, pos + 1).ok();
                }
                EditorAction::None
            }
            EditorKey::Left => {
                cursor_ops::move_left(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::Right => {
                cursor_ops::move_right(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::Up => {
                cursor_ops::move_up(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::Down => {
                cursor_ops::move_down(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::WordLeft => {
                cursor_ops::move_word_left(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::WordRight => {
                cursor_ops::move_word_right(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::Home => {
                cursor_ops::move_line_start(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::End => {
                cursor_ops::move_line_end(&mut self.buffer, 0, false);
                EditorAction::None
            }
            EditorKey::CtrlD => {
                if self.buffer.is_empty() {
                    EditorAction::SendEof
                } else {
                    EditorAction::None
                }
            }
            EditorKey::CtrlU | EditorKey::Escape => {
                self.buffer.clear();
                EditorAction::None
            }
            EditorKey::SelectAll => {
                cursor_ops::select_all(&mut self.buffer);
                EditorAction::None
            }
            EditorKey::Tab => {
                self.buffer.insert_at(0, "\t").ok();
                EditorAction::None
            }
        }
    }

    /// Get rendering data for the input editor.
    pub fn render_data(&self) -> InputRenderData {
        let text = self.buffer.text();
        let lines: Vec<String> = text.split('\n').map(String::from).collect();
        let highlights = highlighter::highlight(&text, &self.shell);
        let cursors = self.buffer.cursor_positions();

        let bracket_match = if let Some(cursor) = self.buffer.cursors().first() {
            find_matching_bracket(&text, cursor.position).map(|match_pos| {
                // Convert to (row, col)
                let mut row = 0;
                let mut col = 0;
                for (i, ch) in text.chars().enumerate() {
                    if i == match_pos {
                        break;
                    }
                    if ch == '\n' {
                        row += 1;
                        col = 0;
                    } else {
                        col += 1;
                    }
                }
                (row, col)
            })
        } else {
            None
        };

        InputRenderData {
            lines,
            highlights,
            cursors,
            bracket_match,
            position: self.position,
        }
    }

    /// Set the editor position (top or bottom).
    pub fn set_position(&mut self, pos: InputPosition) {
        self.position = pos;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_editor() -> InputEditor {
        InputEditor::new(ShellType::Bash, InputPosition::Bottom)
    }

    #[test]
    fn test_submit_on_enter() {
        let mut editor = make_editor();
        editor.handle_key(EditorKey::Char('e'));
        editor.handle_key(EditorKey::Char('c'));
        editor.handle_key(EditorKey::Char('h'));
        editor.handle_key(EditorKey::Char('o'));
        let action = editor.handle_key(EditorKey::Enter);
        assert_eq!(action, EditorAction::Submit("echo".to_string()));
        assert!(editor.buffer.is_empty());
    }

    #[test]
    fn test_shift_enter_inserts_newline() {
        let mut editor = make_editor();
        editor.handle_key(EditorKey::Char('a'));
        editor.handle_key(EditorKey::ShiftEnter);
        editor.handle_key(EditorKey::Char('b'));
        assert_eq!(editor.buffer.text(), "a\nb");
    }

    #[test]
    fn test_ctrl_d_on_empty() {
        let mut editor = make_editor();
        assert_eq!(editor.handle_key(EditorKey::CtrlD), EditorAction::SendEof);
    }

    #[test]
    fn test_position() {
        let mut editor = make_editor();
        editor.set_position(InputPosition::Top);
        let data = editor.render_data();
        assert_eq!(data.position, InputPosition::Top);
    }
}
