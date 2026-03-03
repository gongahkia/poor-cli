/// Input handling: keyboard events, slash-command completion, etc.
use crate::app::{App, AppMode};
use crossterm::event::{Event, KeyCode, KeyEvent, KeyModifiers, MouseEvent, MouseEventKind};

/// Outcome of processing one input event.
pub enum InputAction {
    /// Nothing happened.
    None,
    /// The user submitted their input text (Enter pressed).
    Submit(String),
    /// User wants to quit.
    Quit,
    /// Redraw required.
    Redraw,
    /// Provider select confirmed (index).
    ProviderSelected(usize),
    /// Permission prompt answered.
    PermissionAnswered(bool),
}

/// Slash commands available for auto-complete.
pub const SLASH_COMMANDS: &[&str] = &[
    "/help",
    "/quit",
    "/exit",
    "/clear",
    "/clear-output",
    "/history",
    "/sessions",
    "/new-session",
    "/retry",
    "/search",
    "/edit-last",
    "/copy",
    "/checkpoints",
    "/checkpoint",
    "/save",
    "/rewind",
    "/undo",
    "/restore",
    "/diff",
    "/provider",
    "/providers",
    "/switch",
    "/export",
    "/config",
    "/verbose",
    "/plan-mode",
    "/cost",
    "/model-info",
    "/permission-mode",
];

/// Process a crossterm event and update app state.
pub fn handle_event(app: &mut App, event: Event) -> InputAction {
    match event {
        Event::Key(key) => handle_key(app, key),
        Event::Mouse(mouse) => handle_mouse(app, mouse),
        Event::Resize(_, _) => InputAction::Redraw,
        _ => InputAction::None,
    }
}

fn handle_key(app: &mut App, key: KeyEvent) -> InputAction {
    // Global keybindings
    if key.modifiers.contains(KeyModifiers::CONTROL) {
        match key.code {
            KeyCode::Char('c') => {
                if app.waiting {
                    app.stop_waiting();
                    app.set_status("Request cancelled");
                    return InputAction::Redraw;
                }
                if app.input_buffer.is_empty() {
                    return InputAction::Quit;
                }
                app.input_buffer.clear();
                app.input_cursor = 0;
                return InputAction::Redraw;
            }
            KeyCode::Char('d') => {
                if app.input_buffer.is_empty() {
                    return InputAction::Quit;
                }
                return InputAction::None;
            }
            KeyCode::Char('a') => {
                app.cursor_home();
                return InputAction::Redraw;
            }
            KeyCode::Char('e') => {
                app.cursor_end();
                return InputAction::Redraw;
            }
            KeyCode::Char('u') => {
                // Delete to start of line
                app.input_buffer.drain(..app.input_cursor);
                app.input_cursor = 0;
                return InputAction::Redraw;
            }
            KeyCode::Char('k') => {
                // Delete to end of line
                app.input_buffer.truncate(app.input_cursor);
                return InputAction::Redraw;
            }
            KeyCode::Char('w') => {
                // Delete previous word
                if app.input_cursor > 0 {
                    let before = &app.input_buffer[..app.input_cursor];
                    let trimmed = before.trim_end();
                    let word_start = trimmed
                        .rfind(|c: char| c.is_whitespace())
                        .map(|i| i + 1)
                        .unwrap_or(0);
                    app.input_buffer.drain(word_start..app.input_cursor);
                    app.input_cursor = word_start;
                }
                return InputAction::Redraw;
            }
            _ => {}
        }
    }

    // Mode-specific handling
    match app.mode {
        AppMode::Normal | AppMode::Command => handle_key_normal(app, key),
        AppMode::ProviderSelect => handle_key_provider_select(app, key),
        AppMode::PermissionPrompt => handle_key_permission(app, key),
        AppMode::Quitting => InputAction::Quit,
    }
}

fn handle_key_normal(app: &mut App, key: KeyEvent) -> InputAction {
    // Don't accept input while waiting
    if app.waiting {
        return InputAction::None;
    }

    match key.code {
        KeyCode::Enter => {
            let text = app.take_input();
            if text.is_empty() {
                return InputAction::None;
            }
            InputAction::Submit(text)
        }
        KeyCode::Backspace => {
            app.backspace();
            // Check mode switch
            if app.input_buffer.starts_with('/') {
                app.mode = AppMode::Command;
            } else {
                app.mode = AppMode::Normal;
            }
            InputAction::Redraw
        }
        KeyCode::Delete => {
            app.delete_char();
            InputAction::Redraw
        }
        KeyCode::Left => {
            app.cursor_left();
            InputAction::Redraw
        }
        KeyCode::Right => {
            app.cursor_right();
            InputAction::Redraw
        }
        KeyCode::Home => {
            app.cursor_home();
            InputAction::Redraw
        }
        KeyCode::End => {
            app.cursor_end();
            InputAction::Redraw
        }
        KeyCode::Up => {
            app.history_prev();
            InputAction::Redraw
        }
        KeyCode::Down => {
            app.history_next();
            InputAction::Redraw
        }
        KeyCode::PageUp => {
            app.scroll_up(10);
            InputAction::Redraw
        }
        KeyCode::PageDown => {
            app.scroll_down(10);
            InputAction::Redraw
        }
        KeyCode::Tab => {
            // Slash command auto-complete
            if app.input_buffer.starts_with('/') {
                autocomplete_command(app);
            }
            InputAction::Redraw
        }
        KeyCode::Esc => {
            if !app.input_buffer.is_empty() {
                app.input_buffer.clear();
                app.input_cursor = 0;
                app.mode = AppMode::Normal;
            }
            InputAction::Redraw
        }
        KeyCode::Char(c) => {
            app.insert_char(c);
            // Check if entering command mode
            if app.input_buffer.starts_with('/') {
                app.mode = AppMode::Command;
            } else {
                app.mode = AppMode::Normal;
            }
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

fn handle_key_provider_select(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Up => {
            if app.provider_select_idx > 0 {
                app.provider_select_idx -= 1;
            }
            InputAction::Redraw
        }
        KeyCode::Down => {
            if app.provider_select_idx + 1 < app.providers.len() {
                app.provider_select_idx += 1;
            }
            InputAction::Redraw
        }
        KeyCode::Enter => {
            let idx = app.provider_select_idx;
            app.mode = AppMode::Normal;
            InputAction::ProviderSelected(idx)
        }
        KeyCode::Esc => {
            app.mode = AppMode::Normal;
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

fn handle_key_permission(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Char('y') | KeyCode::Char('Y') | KeyCode::Enter => {
            app.permission_answer = Some(true);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(true)
        }
        KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => {
            app.permission_answer = Some(false);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(false)
        }
        _ => InputAction::None,
    }
}

fn handle_mouse(app: &mut App, mouse: MouseEvent) -> InputAction {
    match mouse.kind {
        MouseEventKind::ScrollUp => {
            app.scroll_up(3);
            InputAction::Redraw
        }
        MouseEventKind::ScrollDown => {
            app.scroll_down(3);
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

/// Auto-complete the slash command in the input buffer.
fn autocomplete_command(app: &mut App) {
    let prefix = app.input_buffer.as_str();
    let matches: Vec<&&str> = SLASH_COMMANDS
        .iter()
        .filter(|cmd| cmd.starts_with(prefix) && **cmd != prefix)
        .collect();

    if matches.len() == 1 {
        // Single match: complete it
        app.input_buffer = matches[0].to_string();
        app.input_cursor = app.input_buffer.len();
    } else if matches.len() > 1 {
        // Multiple matches: find common prefix
        let first = matches[0];
        let common_len = first
            .char_indices()
            .take_while(|(i, c)| matches.iter().all(|m| m.as_bytes().get(*i) == Some(&(*c as u8))))
            .last()
            .map(|(i, c)| i + c.len_utf8())
            .unwrap_or(prefix.len());

        if common_len > prefix.len() {
            app.input_buffer = first[..common_len].to_string();
            app.input_cursor = app.input_buffer.len();
        }
        // Show completions as status
        let completions: Vec<&str> = matches.iter().map(|s| **s).collect();
        app.set_status(completions.join("  "));
    }
}
