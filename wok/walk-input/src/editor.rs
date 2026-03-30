//! Input editor: coordinates buffer, cursor ops, highlighting, and history.

use crate::brackets::find_matching_bracket;
use crate::buffer::InputBuffer;
use crate::cursor_ops;
use crate::highlighter::{self, HighlightSpan};
use crate::workflows::Workflow;

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
    /// Shift+Tab.
    ShiftTab,
}

/// Placeholder span tracked while parameter fill mode is active.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlaceholderSpan {
    /// Start offset (inclusive).
    pub start: usize,
    /// End offset (exclusive).
    pub end: usize,
}

/// Parameter-fill mode state for workflow templates.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ParameterFillMode {
    /// Placeholder spans discovered in the current buffer.
    pub placeholders: Vec<PlaceholderSpan>,
    /// Active placeholder index.
    pub current: usize,
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
    /// Active placeholder range while parameter fill mode is enabled.
    pub parameter_placeholder: Option<(usize, usize, usize)>,
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
    /// Active parameter fill mode, if any.
    pub parameter_fill_mode: Option<ParameterFillMode>,
}

impl InputEditor {
    /// Create a new input editor.
    pub fn new(shell: ShellType, position: InputPosition) -> Self {
        Self {
            buffer: InputBuffer::new(),
            is_active: true,
            position,
            shell,
            parameter_fill_mode: None,
        }
    }

    /// Handle a key event and return the resulting action.
    pub fn handle_key(&mut self, key: EditorKey) -> EditorAction {
        match key {
            EditorKey::Char(ch) => {
                self.buffer.insert_at(0, &ch.to_string()).ok();
                self.refresh_parameter_fill_mode();
                EditorAction::None
            }
            EditorKey::Enter => {
                if self.parameter_fill_mode.is_some() {
                    self.refresh_parameter_fill_mode();
                    if self.parameter_fill_mode.is_some() {
                        self.move_to_next_placeholder();
                        return EditorAction::None;
                    }
                }
                let text = self.buffer.text();
                if text.trim().is_empty() {
                    return EditorAction::Submit(String::new());
                }
                self.buffer.clear();
                self.parameter_fill_mode = None;
                EditorAction::Submit(text)
            }
            EditorKey::ShiftEnter => {
                self.buffer.insert_at(0, "\n").ok();
                self.refresh_parameter_fill_mode();
                EditorAction::None
            }
            EditorKey::Backspace => {
                let pos = self.buffer.cursors()[0].position;
                if pos > 0 {
                    self.buffer.delete_range(pos - 1, pos).ok();
                }
                self.refresh_parameter_fill_mode();
                EditorAction::None
            }
            EditorKey::Delete => {
                let pos = self.buffer.cursors()[0].position;
                let len = self.buffer.len();
                if pos < len {
                    self.buffer.delete_range(pos, pos + 1).ok();
                }
                self.refresh_parameter_fill_mode();
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
                self.parameter_fill_mode = None;
                EditorAction::None
            }
            EditorKey::SelectAll => {
                cursor_ops::select_all(&mut self.buffer);
                EditorAction::None
            }
            EditorKey::Tab => {
                if self.parameter_fill_mode.is_some() {
                    self.move_to_next_placeholder();
                    EditorAction::None
                } else {
                    self.buffer.insert_at(0, "\t").ok();
                    EditorAction::None
                }
            }
            EditorKey::ShiftTab => {
                if self.parameter_fill_mode.is_some() {
                    self.move_to_prev_placeholder();
                }
                EditorAction::None
            }
        }
    }

    /// Load a workflow template into the editor and enter parameter-fill mode.
    pub fn load_workflow(&mut self, workflow: &Workflow) {
        self.buffer.set_text(&workflow.render_with_defaults());
        self.activate_parameter_fill_mode();
    }

    /// Activate parameter-fill mode by scanning placeholders in the current buffer.
    pub fn activate_parameter_fill_mode(&mut self) {
        self.parameter_fill_mode = Some(ParameterFillMode {
            placeholders: collect_placeholders(&self.buffer.text()),
            current: 0,
        });
        self.refresh_parameter_fill_mode();
    }

    fn refresh_parameter_fill_mode(&mut self) {
        let Some(mode) = self.parameter_fill_mode.as_mut() else {
            return;
        };
        mode.placeholders = collect_placeholders(&self.buffer.text());
        if mode.placeholders.is_empty() {
            self.parameter_fill_mode = None;
            return;
        }
        mode.current = mode.current.min(mode.placeholders.len().saturating_sub(1));
        self.select_current_placeholder();
    }

    fn move_to_next_placeholder(&mut self) {
        let Some(mode) = self.parameter_fill_mode.as_mut() else {
            return;
        };
        if mode.placeholders.is_empty() {
            self.parameter_fill_mode = None;
            return;
        }
        mode.current = (mode.current + 1) % mode.placeholders.len();
        self.select_current_placeholder();
    }

    fn move_to_prev_placeholder(&mut self) {
        let Some(mode) = self.parameter_fill_mode.as_mut() else {
            return;
        };
        if mode.placeholders.is_empty() {
            self.parameter_fill_mode = None;
            return;
        }
        if mode.current == 0 {
            mode.current = mode.placeholders.len().saturating_sub(1);
        } else {
            mode.current -= 1;
        }
        self.select_current_placeholder();
    }

    fn select_current_placeholder(&mut self) {
        let Some(mode) = self.parameter_fill_mode.as_ref() else {
            return;
        };
        let Some(span) = mode.placeholders.get(mode.current) else {
            return;
        };
        let len = self.buffer.len();
        if let Some(cursor) = self.buffer.cursors_mut().first_mut() {
            cursor.position = span.end.min(len);
            cursor.anchor = Some(span.start.min(len));
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
            parameter_placeholder: self.parameter_fill_mode.as_ref().and_then(|mode| {
                mode.placeholders.get(mode.current).map(|span| {
                    let (start_row, start_col) = index_to_row_col(&text, span.start);
                    let (_, end_col) = index_to_row_col(&text, span.end);
                    (start_row, start_col, end_col)
                })
            }),
        }
    }

    /// Set the editor position (top or bottom).
    pub fn set_position(&mut self, pos: InputPosition) {
        self.position = pos;
    }
}

fn collect_placeholders(text: &str) -> Vec<PlaceholderSpan> {
    let chars = text.chars().collect::<Vec<_>>();
    let mut spans = Vec::new();
    let mut idx = 0usize;

    while idx < chars.len() {
        if chars[idx] != '$' {
            idx += 1;
            continue;
        }

        if chars.get(idx + 1) == Some(&'{') {
            let mut end = idx + 2;
            while end < chars.len() && chars[end] != '}' {
                end += 1;
            }
            if end < chars.len() && end > idx + 2 {
                spans.push(PlaceholderSpan {
                    start: idx,
                    end: end + 1,
                });
                idx = end + 1;
                continue;
            }
        }

        let mut end = idx + 1;
        while end < chars.len() && chars[end].is_ascii_digit() {
            end += 1;
        }
        if end > idx + 1 {
            spans.push(PlaceholderSpan { start: idx, end });
            idx = end;
            continue;
        }

        idx += 1;
    }

    spans
}

fn index_to_row_col(text: &str, index: usize) -> (usize, usize) {
    let mut row = 0usize;
    let mut col = 0usize;
    for (idx, ch) in text.chars().enumerate() {
        if idx == index {
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
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::workflows::{Workflow, WorkflowParam};

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

    #[test]
    fn test_parameter_fill_mode_tabs_between_placeholders() {
        let mut editor = make_editor();
        editor.buffer.set_text("echo ${branch} --host ${host}");
        editor.activate_parameter_fill_mode();

        let first = editor.render_data().parameter_placeholder;
        editor.handle_key(EditorKey::Tab);
        let second = editor.render_data().parameter_placeholder;

        assert!(first.is_some());
        assert!(second.is_some());
        assert_ne!(first, second);
    }

    #[test]
    fn test_load_workflow_applies_defaults() {
        let mut editor = make_editor();
        let workflow = Workflow {
            name: "deploy".to_string(),
            description: String::new(),
            template: "git push origin ${branch}".to_string(),
            params: vec![WorkflowParam {
                name: "branch".to_string(),
                placeholder: "main".to_string(),
                default: Some("main".to_string()),
                description: String::new(),
            }],
        };

        editor.load_workflow(&workflow);
        assert_eq!(editor.buffer.text(), "git push origin main");
    }
}
