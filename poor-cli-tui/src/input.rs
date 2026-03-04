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
    /// User cancelled an in-flight request (Ctrl+C / Esc while waiting).
    Cancel,
    /// Plan approved — execute it.
    PlanApproved,
    /// Plan cancelled.
    PlanCancelled,
}

/// Metadata for slash-command completion and palette rendering.
#[derive(Clone, Copy)]
pub struct SlashCommandSpec {
    pub command: &'static str,
    pub description: &'static str,
    pub recommended: bool,
}

/// Slash commands available in the Rust TUI.
pub const SLASH_COMMANDS: &[SlashCommandSpec] = &[
    SlashCommandSpec {
        command: "/help",
        description: "Show all available commands",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/review",
        description: "Review code or staged diff",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/test",
        description: "Generate tests for a file",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/provider",
        description: "Show active provider",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/switch",
        description: "Switch provider/model",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/history",
        description: "Show recent messages",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/sessions",
        description: "List recent sessions",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/files",
        description: "List pinned context files",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/new-session",
        description: "Start a fresh session",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/permission-mode",
        description: "Show permission mode",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/broke",
        description: "Set poor mode (terse responses)",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/my-treat",
        description: "Set rich mode (comprehensive responses)",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/settings",
        description: "List editable config settings",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/api-key",
        description: "Set or inspect provider API keys",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/quit",
        description: "Exit the TUI",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/exit",
        description: "Exit the TUI (alias)",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/clear",
        description: "Clear conversation history",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/clear-output",
        description: "Clear screen output only",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/providers",
        description: "List providers and models",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/config",
        description: "Show active configuration",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/model-info",
        description: "Show model capabilities",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/cost",
        description: "Show usage and cost estimate",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/verbose",
        description: "Toggle verbose logging",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/plan-mode",
        description: "Toggle plan mode",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/toggle",
        description: "Toggle boolean config value",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/set",
        description: "Set config key to a value",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/theme",
        description: "Show or set UI theme (dark/light)",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/tools",
        description: "List backend tools",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/retry",
        description: "Retry last request",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/search",
        description: "Search session messages",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/edit-last",
        description: "Edit and resend last prompt",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/copy",
        description: "Copy last assistant response",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/add",
        description: "Pin file/directory for context",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/drop",
        description: "Unpin context file",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/clear-files",
        description: "Clear all pinned context files",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/commit",
        description: "Create commit message from staged diff",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/checkpoints",
        description: "List available checkpoints",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/checkpoint",
        description: "Create manual checkpoint",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/save",
        description: "Quick checkpoint alias",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/rewind",
        description: "Restore checkpoint by id or latest",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/restore",
        description: "Restore latest checkpoint",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/diff",
        description: "Compare two files",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/export",
        description: "Export conversation history",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/image",
        description: "Queue image for next message",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/watch",
        description: "Watch directory for changes",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/unwatch",
        description: "Stop watch mode",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/save-prompt",
        description: "Save reusable prompt",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/use",
        description: "Load and run saved prompt",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/prompts",
        description: "List saved prompts",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/run",
        description: "Run shell command via backend",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/read",
        description: "Read file through backend",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/pwd",
        description: "Show current working directory",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/ls",
        description: "List files in directory",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/status",
        description: "Show session status summary",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/undo",
        description: "Undo last file change (checkpoint)",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/plan",
        description: "Generate a plan before executing",
        recommended: true,
    },
];

pub fn command_palette_matches(prefix: &str) -> Vec<&'static SlashCommandSpec> {
    let trimmed = prefix.trim();
    if !trimmed.starts_with('/') {
        return Vec::new();
    }

    if trimmed == "/" {
        return SLASH_COMMANDS
            .iter()
            .filter(|spec| spec.recommended)
            .collect();
    }

    SLASH_COMMANDS
        .iter()
        .filter(|spec| spec.command.starts_with(trimmed))
        .collect()
}

fn visible_command_palette_matches(prefix: &str) -> Vec<&'static SlashCommandSpec> {
    command_palette_matches(prefix)
        .into_iter()
        .take(8)
        .collect()
}

fn command_completion_matches(prefix: &str) -> Vec<&'static SlashCommandSpec> {
    let trimmed = prefix.trim();
    command_palette_matches(trimmed)
        .into_iter()
        .filter(|spec| spec.command != trimmed)
        .collect()
}

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
                    return InputAction::Cancel;
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
        AppMode::PlanReview => handle_key_plan_review(app, key),
        AppMode::Quitting => InputAction::Quit,
    }
}

fn handle_key_normal(app: &mut App, key: KeyEvent) -> InputAction {
    // While waiting, only Esc cancels — everything else is ignored
    if app.waiting {
        if key.code == KeyCode::Esc {
            return InputAction::Cancel;
        }
        return InputAction::None;
    }

    match key.code {
        KeyCode::Enter => {
            // Alt+Enter or Shift+Enter inserts a newline for multi-line input
            if key.modifiers.contains(KeyModifiers::ALT)
                || key.modifiers.contains(KeyModifiers::SHIFT)
            {
                app.insert_char('\n');
                return InputAction::Redraw;
            }

            // If a slash command token is still being typed, prioritize completion over submit.
            if should_autocomplete_on_enter(app) && autocomplete_command(app) {
                return InputAction::Redraw;
            }

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
                app.command_match_index = 0;
            } else {
                app.mode = AppMode::Normal;
                app.command_match_index = 0;
            }
            clamp_command_match_index(app);
            InputAction::Redraw
        }
        KeyCode::Delete => {
            app.delete_char();
            app.command_match_index = 0;
            clamp_command_match_index(app);
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
            if navigate_command_matches(app, false) {
                return InputAction::Redraw;
            }
            app.history_prev();
            InputAction::Redraw
        }
        KeyCode::Down => {
            if navigate_command_matches(app, true) {
                return InputAction::Redraw;
            }
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
            clamp_command_match_index(app);
            InputAction::Redraw
        }
        KeyCode::Esc => {
            if !app.input_buffer.is_empty() {
                app.input_buffer.clear();
                app.input_cursor = 0;
                app.mode = AppMode::Normal;
            }
            app.command_match_index = 0;
            InputAction::Redraw
        }
        KeyCode::Char(c) => {
            app.insert_char(c);
            // Check if entering command mode
            if app.input_buffer.starts_with('/') {
                app.mode = AppMode::Command;
                app.command_match_index = 0;
            } else {
                app.mode = AppMode::Normal;
                app.command_match_index = 0;
            }
            clamp_command_match_index(app);
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

fn handle_key_plan_review(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Enter => {
            app.mode = AppMode::Normal;
            InputAction::PlanApproved
        }
        KeyCode::Esc | KeyCode::Char('q') => {
            app.mode = AppMode::Normal;
            InputAction::PlanCancelled
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

fn should_autocomplete_on_enter(app: &App) -> bool {
    let trimmed = app.input_buffer.trim();
    if !trimmed.starts_with('/') {
        return false;
    }

    // Only auto-complete the command token, not argument input.
    if trimmed.contains(char::is_whitespace) {
        return false;
    }

    // If the command is already exact, submit immediately.
    !command_completion_matches(trimmed).is_empty()
}

/// Auto-complete the slash command in the input buffer.
fn autocomplete_command(app: &mut App) -> bool {
    let matches = command_completion_matches(app.input_buffer.as_str());

    if matches.is_empty() {
        return false;
    }

    if matches.len() == 1 {
        // Single match: complete it
        app.input_buffer = matches[0].command.to_string();
        app.input_cursor = app.input_buffer.len();
        app.command_match_index = 0;
        return true;
    }

    // Multiple matches: confirm currently selected candidate from visible palette.
    let visible_matches = visible_command_palette_matches(app.input_buffer.as_str());
    if visible_matches.is_empty() {
        return false;
    }

    let selected_idx = app
        .command_match_index
        .min(visible_matches.len().saturating_sub(1));
    app.input_buffer = visible_matches[selected_idx].command.to_string();
    app.input_cursor = app.input_buffer.len();
    app.command_match_index = 0;
    true
}

fn clamp_command_match_index(app: &mut App) {
    let matches = visible_command_palette_matches(app.input_buffer.as_str());
    if matches.is_empty() {
        app.command_match_index = 0;
    } else if app.command_match_index >= matches.len() {
        app.command_match_index = 0;
    }
}

fn navigate_command_matches(app: &mut App, forward: bool) -> bool {
    let trimmed = app.input_buffer.trim();
    if !trimmed.starts_with('/') || trimmed.contains(char::is_whitespace) {
        return false;
    }

    let matches = visible_command_palette_matches(trimmed);
    if matches.len() <= 1 {
        return false;
    }

    clamp_command_match_index(app);
    if forward {
        app.command_match_index = (app.command_match_index + 1) % matches.len();
    } else if app.command_match_index == 0 {
        app.command_match_index = matches.len() - 1;
    } else {
        app.command_match_index -= 1;
    }

    let selected = matches[app.command_match_index];
    app.set_status(format!(
        "Selected {} - {}",
        selected.command, selected.description
    ));
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    fn key_enter() -> KeyEvent {
        KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE)
    }

    fn key_up() -> KeyEvent {
        KeyEvent::new(KeyCode::Up, KeyModifiers::NONE)
    }

    fn key_down() -> KeyEvent {
        KeyEvent::new(KeyCode::Down, KeyModifiers::NONE)
    }

    #[test]
    fn enter_autocompletes_partial_command() {
        let mut app = App::new();
        app.input_buffer = "/new-ses".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Command;

        let action = handle_key_normal(&mut app, key_enter());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.input_buffer, "/new-session");
    }

    #[test]
    fn enter_submits_exact_command() {
        let mut app = App::new();
        app.input_buffer = "/new-session".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Command;

        let action = handle_key_normal(&mut app, key_enter());

        match action {
            InputAction::Submit(text) => assert_eq!(text, "/new-session"),
            _ => panic!("expected submit action"),
        }
    }

    #[test]
    fn enter_does_not_autocomplete_command_arguments() {
        let mut app = App::new();
        app.input_buffer = "/theme da".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Command;

        let action = handle_key_normal(&mut app, key_enter());

        match action {
            InputAction::Submit(text) => assert_eq!(text, "/theme da"),
            _ => panic!("expected submit action"),
        }
    }

    #[test]
    fn arrow_keys_navigate_command_matches() {
        let mut app = App::new();
        app.input_buffer = "/pro".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Command;

        let down = handle_key_normal(&mut app, key_down());
        assert!(matches!(down, InputAction::Redraw));
        assert_eq!(app.command_match_index, 1);

        let up = handle_key_normal(&mut app, key_up());
        assert!(matches!(up, InputAction::Redraw));
        assert_eq!(app.command_match_index, 0);
    }

    #[test]
    fn enter_confirms_selected_match_when_multiple_exist() {
        let mut app = App::new();
        app.input_buffer = "/pro".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Command;

        // `/pro` currently has: /provider, /providers, /prompts.
        handle_key_normal(&mut app, key_down());
        let action = handle_key_normal(&mut app, key_enter());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.input_buffer, "/providers");
    }
}
