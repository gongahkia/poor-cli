/// Input handling: keyboard events, slash-command completion, etc.
use crate::app::{App, AppMode, QuickOpenItem};
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
    /// Compact context strategy selected.
    CompactStrategySelected(String),
    /// Copy text to clipboard.
    CopyToClipboard(String),
    /// Join wizard completed with (url, room, token).
    JoinWizardComplete(String, String, String),
    /// Open the backend-owned context inspector.
    OpenContextInspector,
    /// Open the combined quick-open palette.
    OpenQuickOpen,
    /// Open the agent timeline panel.
    OpenTimeline,
    /// Open transcript search and filter.
    OpenTranscriptSearch,
    /// Execute the selected quick-open item.
    QuickOpenSelected(QuickOpenItem),
    /// Restore the last mutation checkpoint.
    RestoreLastMutation,
    /// Open a file in the user's editor.
    OpenFileInEditor(String),
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
        command: "/onboarding",
        description: "Start guided CLI onboarding",
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
        command: "/queue",
        description: "Manage prompt queue (add/list/clear/drop)",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/compact",
        description: "Manage context (compact/compress/handoff)",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/permission-mode",
        description: "Show permission mode",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/collab",
        description: "Start, join, and manage collaboration sessions",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/pair",
        description: "Legacy pair alias for collaboration sessions",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/pass",
        description: "Hand driver role to the next collaborator",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/suggest",
        description: "Send suggestion to the active driver",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/leave",
        description: "Disconnect from collaboration session",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/host-server",
        description: "Legacy advanced host controls for collaboration",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/join-server",
        description: "Legacy join alias for invite/manual room entry",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/doctor",
        description: "Run environment and service health checks",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/mcp",
        description: "Inspect or control MCP servers and tools",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/instructions",
        description: "Inspect the active instruction stack",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/memory",
        description: "Show or update repo-local memory",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/policy",
        description: "Inspect repo-local hooks and audit status",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/focus",
        description: "Manage persistent coding focus state",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/resume",
        description: "Resume with branch/checkpoint/session summary",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/workspace-map",
        description: "Summarize repository layout and hotspots",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/bootstrap",
        description: "Detect project type and suggest quickstart commands",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/context-budget",
        description: "Rank context files against a token budget",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/context",
        description: "Open backend context inspector",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/timeline",
        description: "Open agent timeline and diffs",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/search",
        description: "Search transcript, tools, and diffs",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/autopilot",
        description: "Toggle bounded autonomous execution mode",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/qa",
        description: "Run background QA watch for lint/tests",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/profile",
        description: "Set execution profile (speed|safe|deep-review)",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/tasks",
        description: "Manage local task board",
        recommended: false,
    },
    SlashCommandSpec {
        command: "/explain-diff",
        description: "Explain behavior and risk in current diff",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/fix-failures",
        description: "Analyze latest test/lint failure output",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/service",
        description: "Manage local background services",
        recommended: true,
    },
    SlashCommandSpec {
        command: "/ollama",
        description: "Manage Ollama service and models",
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
        description: "Toggle plan-first execution guidance",
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

/// Check if a slash command token exactly matches a known command (case-insensitive).
pub fn is_known_slash_command(token: &str) -> bool {
    let normalized = token.trim().to_ascii_lowercase();
    if !normalized.starts_with('/') {
        return false;
    }
    SLASH_COMMANDS
        .iter()
        .any(|spec| spec.command == normalized.as_str())
}

/// Resolve a likely typo to a known slash command.
///
/// Returns `Some(command)` only when there is a single confident nearest match.
pub fn closest_slash_command(token: &str) -> Option<&'static str> {
    let normalized = token.trim().to_ascii_lowercase();
    if !normalized.starts_with('/') {
        return None;
    }

    if is_known_slash_command(&normalized) {
        return None;
    }

    let mut best: Option<(&'static str, usize, usize)> = None;
    let mut second_best_distance: Option<usize> = None;

    for spec in SLASH_COMMANDS {
        let distance = levenshtein_distance(&normalized, spec.command);
        let max_len = normalized.chars().count().max(spec.command.chars().count());
        let allowed_distance = match max_len {
            0..=4 => 1,
            5..=8 => 2,
            _ => 3,
        };
        if distance > allowed_distance {
            continue;
        }

        match best {
            None => best = Some((spec.command, distance, max_len)),
            Some((_, best_distance, best_len)) => {
                if (distance, max_len) < (best_distance, best_len) {
                    second_best_distance = Some(best_distance);
                    best = Some((spec.command, distance, max_len));
                } else if second_best_distance.is_none_or(|current| distance < current) {
                    second_best_distance = Some(distance);
                }
            }
        }
    }

    let (best_command, best_distance, _) = best?;
    if second_best_distance == Some(best_distance) {
        return None;
    }

    Some(best_command)
}

fn levenshtein_distance(a: &str, b: &str) -> usize {
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();

    if a_chars.is_empty() {
        return b_chars.len();
    }
    if b_chars.is_empty() {
        return a_chars.len();
    }

    let mut prev: Vec<usize> = (0..=b_chars.len()).collect();
    let mut curr = vec![0; b_chars.len() + 1];

    for (i, &a_char) in a_chars.iter().enumerate() {
        curr[0] = i + 1;
        for (j, &b_char) in b_chars.iter().enumerate() {
            let cost = if a_char == b_char { 0 } else { 1 };
            curr[j + 1] = (prev[j + 1] + 1).min(curr[j] + 1).min(prev[j] + cost);
        }
        std::mem::swap(&mut prev, &mut curr);
    }

    prev[b_chars.len()]
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
            KeyCode::Char('i') => {
                return InputAction::OpenContextInspector;
            }
            KeyCode::Char('p') => {
                return InputAction::OpenQuickOpen;
            }
            KeyCode::Char('t') => {
                return InputAction::OpenTimeline;
            }
            KeyCode::Char('f') => {
                return InputAction::OpenTranscriptSearch;
            }
            _ => {}
        }
    }

    // Mode-specific handling
    match app.mode {
        AppMode::Normal | AppMode::Command => handle_key_normal(app, key),
        AppMode::ProviderSelect => handle_key_provider_select(app, key),
        AppMode::CompactSelect => handle_key_compact_select(app, key),
        AppMode::InfoPopup => handle_key_info_popup(app, key),
        AppMode::PermissionPrompt => handle_key_permission(app, key),
        AppMode::MutationReview => handle_key_mutation_review(app, key),
        AppMode::ContextInspector => handle_key_context_inspector(app, key),
        AppMode::QuickOpen => handle_key_quick_open(app, key),
        AppMode::Timeline => handle_key_timeline(app, key),
        AppMode::TranscriptSearch => handle_key_transcript_search(app, key),
        AppMode::PlanReview => handle_key_plan_review(app, key),
        AppMode::JoinWizard => handle_key_join_wizard(app, key),
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

fn handle_key_compact_select(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Up => {
            if app.compact_select_idx > 0 {
                app.compact_select_idx -= 1;
            }
            InputAction::Redraw
        }
        KeyCode::Down => {
            if app.compact_select_idx + 1 < crate::app::COMPACT_STRATEGIES.len() {
                app.compact_select_idx += 1;
            }
            InputAction::Redraw
        }
        KeyCode::Enter => {
            let strategy = crate::app::COMPACT_STRATEGIES[app.compact_select_idx].0;
            app.mode = AppMode::Normal;
            InputAction::CompactStrategySelected(strategy.to_string())
        }
        KeyCode::Esc => {
            app.mode = AppMode::Normal;
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

fn extract_copyable_items(content: &str) -> Vec<String> {
    let mut items = Vec::new();
    for part in content.split('`') {
        // backtick-delimited: odd-indexed splits are inside backticks
        if items.len() % 2 == 0 {
            items.push(part.to_string()); // outside backtick — placeholder
        } else {
            items.push(part.to_string()); // inside backtick — copyable
        }
    }
    // keep only the odd-indexed (inside-backtick) entries, skip empty/trivial
    content
        .split('`')
        .enumerate()
        .filter(|(i, s)| i % 2 == 1 && !s.trim().is_empty())
        .map(|(_, s)| s.to_string())
        .collect()
}

fn handle_key_info_popup(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Esc | KeyCode::Enter | KeyCode::Char('q') | KeyCode::Char('Q') => {
            app.close_info_popup();
            InputAction::Redraw
        }
        KeyCode::Char('c') | KeyCode::Char('C') => {
            let items = extract_copyable_items(&app.info_popup_content);
            if !items.is_empty() {
                InputAction::CopyToClipboard(items.join("\n"))
            } else {
                InputAction::CopyToClipboard(app.info_popup_content.clone())
            }
        }
        KeyCode::Char(ch) if ch.is_ascii_digit() && ch != '0' => {
            let idx = (ch as usize) - ('1' as usize);
            let items = extract_copyable_items(&app.info_popup_content);
            if let Some(item) = items.get(idx) {
                InputAction::CopyToClipboard(item.clone())
            } else {
                InputAction::None
            }
        }
        KeyCode::Up => {
            app.scroll_info_popup_up(1);
            InputAction::Redraw
        }
        KeyCode::Down => {
            app.scroll_info_popup_down(1);
            InputAction::Redraw
        }
        KeyCode::PageUp => {
            app.scroll_info_popup_up(10);
            InputAction::Redraw
        }
        KeyCode::PageDown => {
            app.scroll_info_popup_down(10);
            InputAction::Redraw
        }
        KeyCode::Home => {
            app.info_popup_scroll = 0;
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

fn handle_key_join_wizard(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Esc => {
            app.join_wizard_active = false;
            app.join_wizard_step = 0;
            app.join_wizard_url.clear();
            app.join_wizard_room.clear();
            app.join_wizard_input.clear();
            app.join_wizard_error.clear();
            app.mode = AppMode::Normal;
            InputAction::Redraw
        }
        KeyCode::Char(c) => {
            app.join_wizard_input.push(c);
            app.join_wizard_error.clear();
            InputAction::Redraw
        }
        KeyCode::Backspace => {
            app.join_wizard_input.pop();
            InputAction::Redraw
        }
        KeyCode::Enter => {
            let input = app.join_wizard_input.trim().to_string();
            match app.join_wizard_step {
                0 => {
                    // Invite-first step. A raw ws:// URL falls back to manual room/token entry.
                    if input.is_empty() {
                        app.join_wizard_error =
                            "Paste an invite code or enter a ws:// / wss:// URL.".to_string();
                        return InputAction::Redraw;
                    }

                    if let Ok((url, room, token)) = crate::multiplayer::decode_invite_code(&input) {
                        match crate::multiplayer::preflight_join_endpoint(&url) {
                            Ok(_) => {
                                app.join_wizard_active = false;
                                app.join_wizard_step = 0;
                                app.join_wizard_url.clear();
                                app.join_wizard_room.clear();
                                app.join_wizard_input.clear();
                                app.join_wizard_error.clear();
                                app.mode = AppMode::Normal;
                                return InputAction::JoinWizardComplete(url, room, token);
                            }
                            Err(e) => {
                                app.join_wizard_error = format!("Preflight failed: {e}");
                                return InputAction::Redraw;
                            }
                        }
                    }

                    if !(input.starts_with("ws://") || input.starts_with("wss://")) {
                        app.join_wizard_error =
                            "Enter an invite code or a URL starting with ws:// or wss://."
                                .to_string();
                        return InputAction::Redraw;
                    }

                    match crate::multiplayer::preflight_join_endpoint(&input) {
                        Ok(_) => {
                            app.join_wizard_url = input;
                            app.join_wizard_input.clear();
                            app.join_wizard_error.clear();
                            app.join_wizard_step = 1;
                        }
                        Err(e) => {
                            app.join_wizard_error = format!("Preflight failed: {e}");
                        }
                    }
                    InputAction::Redraw
                }
                1 => {
                    // room step
                    if input.is_empty() {
                        app.join_wizard_error = "Room name cannot be empty.".to_string();
                        return InputAction::Redraw;
                    }
                    app.join_wizard_room = input;
                    app.join_wizard_input.clear();
                    app.join_wizard_error.clear();
                    app.join_wizard_step = 2;
                    InputAction::Redraw
                }
                2 => {
                    // token step
                    if input.is_empty() {
                        app.join_wizard_error = "Token cannot be empty.".to_string();
                        return InputAction::Redraw;
                    }
                    let url = app.join_wizard_url.clone();
                    let room = app.join_wizard_room.clone();
                    let token = input;
                    app.join_wizard_active = false;
                    app.join_wizard_step = 0;
                    app.join_wizard_url.clear();
                    app.join_wizard_room.clear();
                    app.join_wizard_input.clear();
                    app.join_wizard_error.clear();
                    app.mode = AppMode::Normal;
                    InputAction::JoinWizardComplete(url, room, token)
                }
                _ => {
                    app.mode = AppMode::Normal;
                    InputAction::Redraw
                }
            }
        }
        _ => InputAction::None,
    }
}

fn handle_key_permission(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Char('y') | KeyCode::Char('Y') | KeyCode::Enter => {
            app.permission_approved_paths.clear();
            app.permission_answer = Some(true);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(true)
        }
        KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => {
            app.permission_approved_paths.clear();
            app.permission_answer = Some(false);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(false)
        }
        _ => InputAction::None,
    }
}

fn handle_key_mutation_review(app: &mut App, key: KeyEvent) -> InputAction {
    if app.mutation_review.is_none() {
        app.mode = AppMode::Normal;
        return InputAction::Redraw;
    }

    match key.code {
        KeyCode::Tab | KeyCode::Right => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if review.supports_chunk_approval() && review.jump_to_file_group(false) {
                return InputAction::Redraw;
            }
            InputAction::None
        }
        KeyCode::BackTab | KeyCode::Left => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if review.supports_chunk_approval() && review.jump_to_file_group(true) {
                return InputAction::Redraw;
            }
            InputAction::None
        }
        KeyCode::Up => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if !review.chunks.is_empty() {
                review.selected_chunk_index = review.selected_chunk_index.saturating_sub(1);
                review.sync_selected_path_from_chunk();
            } else if review.selected_path_index > 0 {
                review.selected_path_index -= 1;
            }
            InputAction::Redraw
        }
        KeyCode::Down => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if !review.chunks.is_empty() {
                if review.selected_chunk_index + 1 < review.chunks.len() {
                    review.selected_chunk_index += 1;
                    review.sync_selected_path_from_chunk();
                }
            } else if review.selected_path_index + 1 < review.paths.len() {
                review.selected_path_index += 1;
            }
            InputAction::Redraw
        }
        KeyCode::Char(' ') => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if review.supports_chunk_approval() {
                let mut status_message: Option<String> = None;
                if let Some(chunk) = review.chunks.get_mut(review.selected_chunk_index) {
                    chunk.selected = !chunk.selected;
                    status_message = Some(format!(
                        "{} chunk {} for {}",
                        if chunk.selected {
                            "Selected"
                        } else {
                            "Cleared"
                        },
                        chunk.hunk_index + 1,
                        chunk.path
                    ));
                }
                if let Some(message) = status_message {
                    app.set_status(message);
                }
                return InputAction::Redraw;
            }
            InputAction::None
        }
        KeyCode::Char('a') | KeyCode::Char('A') => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if review.supports_chunk_approval() {
                for chunk in &mut review.chunks {
                    chunk.selected = true;
                }
                app.set_status("Selected all hunks in the pending patch");
                return InputAction::Redraw;
            }
            InputAction::None
        }
        KeyCode::Char('s') | KeyCode::Char('S') => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if review.supports_chunk_approval() {
                if let Some(path) = review.set_current_file_group_selection(true) {
                    app.set_status(format!("Selected all hunks for {path}"));
                    return InputAction::Redraw;
                }
            }
            InputAction::None
        }
        KeyCode::Char('r') | KeyCode::Char('R') => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if review.supports_chunk_approval() {
                if let Some(path) = review.set_current_file_group_selection(false) {
                    app.set_status(format!("Cleared hunk selection for {path}"));
                    return InputAction::Redraw;
                }
            }
            InputAction::None
        }
        KeyCode::Char('x') | KeyCode::Char('X') => {
            let review = app
                .mutation_review
                .as_mut()
                .expect("review state must exist");
            if review.supports_chunk_approval() {
                for chunk in &mut review.chunks {
                    chunk.selected = false;
                }
                app.set_status("Cleared hunk selection");
                return InputAction::Redraw;
            }
            InputAction::None
        }
        KeyCode::Char('c') | KeyCode::Char('C') => {
            let diff = app
                .mutation_review
                .as_ref()
                .map(|review| review.diff.clone())
                .unwrap_or_default();
            InputAction::CopyToClipboard(diff)
        }
        KeyCode::Char('o') | KeyCode::Char('O') => app
            .mutation_review
            .as_ref()
            .and_then(|review| {
                review
                    .selected_chunk()
                    .map(|chunk| chunk.path.clone())
                    .or_else(|| review.paths.get(review.selected_path_index).cloned())
            })
            .map(InputAction::OpenFileInEditor)
            .unwrap_or(InputAction::None),
        KeyCode::Char('u') | KeyCode::Char('U') => InputAction::RestoreLastMutation,
        KeyCode::Char('h') | KeyCode::Char('H') => {
            let supports_chunk_approval = app
                .mutation_review
                .as_ref()
                .map(|review| review.supports_chunk_approval())
                .unwrap_or(false);
            if !supports_chunk_approval {
                return InputAction::None;
            }
            let mut approved_chunks = app
                .mutation_review
                .as_ref()
                .map(|review| review.approved_chunks())
                .unwrap_or_default();
            if approved_chunks.is_empty() {
                if let Some(chunk) = app
                    .mutation_review
                    .as_ref()
                    .and_then(|review| review.selected_chunk())
                {
                    approved_chunks.push(crate::app::ApprovedReviewChunk {
                        path: chunk.path.clone(),
                        hunk_index: chunk.hunk_index,
                    });
                }
            }
            if approved_chunks.is_empty() {
                return InputAction::None;
            }
            app.permission_approved_paths.clear();
            app.permission_approved_chunks = approved_chunks;
            app.permission_answer = Some(true);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(true)
        }
        KeyCode::Char('f') | KeyCode::Char('F') => {
            if let Some(path) = app.mutation_review.as_ref().and_then(|review| {
                review
                    .selected_chunk()
                    .map(|chunk| chunk.path.clone())
                    .or_else(|| review.paths.get(review.selected_path_index).cloned())
            }) {
                app.permission_approved_paths = vec![path];
                app.permission_approved_chunks.clear();
                app.set_status("Approved selected file from the pending mutation");
            } else {
                app.permission_approved_paths.clear();
                app.permission_approved_chunks.clear();
            }
            app.permission_answer = Some(true);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(true)
        }
        KeyCode::Char('y') | KeyCode::Char('Y') | KeyCode::Enter => {
            app.permission_approved_paths.clear();
            app.permission_approved_chunks.clear();
            app.permission_answer = Some(true);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(true)
        }
        KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => {
            app.permission_approved_paths.clear();
            app.permission_approved_chunks.clear();
            app.permission_answer = Some(false);
            app.mode = AppMode::Normal;
            InputAction::PermissionAnswered(false)
        }
        _ => InputAction::None,
    }
}

fn handle_key_context_inspector(app: &mut App, key: KeyEvent) -> InputAction {
    if app.context_inspector.is_none() {
        app.mode = AppMode::Normal;
        return InputAction::Redraw;
    }

    match key.code {
        KeyCode::Up => {
            let inspector = app
                .context_inspector
                .as_mut()
                .expect("context inspector must exist");
            if inspector.selected_index > 0 {
                inspector.selected_index -= 1;
            }
            InputAction::Redraw
        }
        KeyCode::Down => {
            let inspector = app
                .context_inspector
                .as_mut()
                .expect("context inspector must exist");
            if inspector.selected_index + 1 < inspector.files.len() {
                inspector.selected_index += 1;
            }
            InputAction::Redraw
        }
        KeyCode::Char('c') | KeyCode::Char('C') => {
            let summary = app
                .context_inspector
                .as_ref()
                .map(|inspector| {
                    inspector
                        .files
                        .iter()
                        .map(|file| {
                            format!(
                                "{} [{}] ~{} tok",
                                file.path, file.source, file.estimated_tokens
                            )
                        })
                        .collect::<Vec<_>>()
                        .join("\n")
                })
                .unwrap_or_default();
            InputAction::CopyToClipboard(summary)
        }
        KeyCode::Char('d') | KeyCode::Char('D') => {
            let maybe_file = app
                .context_inspector
                .as_ref()
                .and_then(|inspector| inspector.files.get(inspector.selected_index).cloned());
            let selected_index = app
                .context_inspector
                .as_ref()
                .map(|inspector| inspector.selected_index)
                .unwrap_or(0);
            if let Some(file) = maybe_file {
                if let Some(spec) = file.explicit_spec {
                    if file.source == "pinned" {
                        app.pinned_context_files.retain(|entry| entry != &spec);
                        app.set_status(format!("Removed pinned context: {spec}"));
                    } else if file.source == "explicit" {
                        let quoted = format!("@\"{spec}\"");
                        let plain = format!("@{spec}");
                        if app.input_buffer.contains(&quoted) {
                            app.input_buffer = app.input_buffer.replacen(&quoted, "", 1);
                        } else if app.input_buffer.contains(&plain) {
                            app.input_buffer = app.input_buffer.replacen(&plain, "", 1);
                        }
                        app.input_buffer = app
                            .input_buffer
                            .split_whitespace()
                            .collect::<Vec<_>>()
                            .join(" ");
                        app.input_cursor = app.input_buffer.len();
                        app.set_status(format!("Removed attachment: {spec}"));
                    }
                    if let Some(inspector) = app.context_inspector.as_mut() {
                        if selected_index < inspector.files.len() {
                            inspector.files.remove(selected_index);
                        }
                        if inspector.selected_index >= inspector.files.len()
                            && inspector.selected_index > 0
                        {
                            inspector.selected_index -= 1;
                        }
                    }
                }
            }
            InputAction::Redraw
        }
        KeyCode::Esc | KeyCode::Enter => {
            app.close_context_inspector();
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

fn filtered_quick_open_items(app: &App) -> Vec<QuickOpenItem> {
    let query = app.quick_open.query.trim().to_lowercase();
    let mut items = app.quick_open.items.clone();
    if query.is_empty() {
        return items;
    }

    items.retain(|item| {
        item.label.to_lowercase().contains(&query)
            || item.detail.to_lowercase().contains(&query)
            || item.value.to_lowercase().contains(&query)
    });
    items
}

fn cycle_transcript_filters(app: &mut App, reverse: bool) {
    let current = (
        app.transcript_search.include_messages,
        app.transcript_search.include_tools,
        app.transcript_search.include_diffs,
    );
    let presets = [
        (true, true, true),
        (true, false, false),
        (false, true, false),
        (false, false, true),
    ];
    let index = presets
        .iter()
        .position(|preset| *preset == current)
        .unwrap_or(0);
    let next_index = if reverse {
        if index == 0 {
            presets.len() - 1
        } else {
            index - 1
        }
    } else {
        (index + 1) % presets.len()
    };
    let next = presets[next_index];
    app.transcript_search.include_messages = next.0;
    app.transcript_search.include_tools = next.1;
    app.transcript_search.include_diffs = next.2;
    app.transcript_search.selected_index = 0;
}

fn handle_key_quick_open(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Esc => {
            app.close_quick_open();
            InputAction::Redraw
        }
        KeyCode::Backspace => {
            app.quick_open.query.pop();
            app.quick_open.selected_index = 0;
            InputAction::Redraw
        }
        KeyCode::Char(c) => {
            app.quick_open.query.push(c);
            app.quick_open.selected_index = 0;
            InputAction::Redraw
        }
        KeyCode::Up => {
            if app.quick_open.selected_index > 0 {
                app.quick_open.selected_index -= 1;
            }
            InputAction::Redraw
        }
        KeyCode::Down => {
            let items = filtered_quick_open_items(app);
            if app.quick_open.selected_index + 1 < items.len() {
                app.quick_open.selected_index += 1;
            }
            InputAction::Redraw
        }
        KeyCode::Enter => {
            let items = filtered_quick_open_items(app);
            items
                .get(app.quick_open.selected_index)
                .cloned()
                .map(InputAction::QuickOpenSelected)
                .unwrap_or(InputAction::None)
        }
        _ => InputAction::None,
    }
}

fn handle_key_timeline(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Esc | KeyCode::Char('q') | KeyCode::Enter => {
            app.close_timeline();
            InputAction::Redraw
        }
        KeyCode::Up => {
            app.timeline_scroll = app.timeline_scroll.saturating_sub(1);
            InputAction::Redraw
        }
        KeyCode::Down => {
            app.timeline_scroll = app.timeline_scroll.saturating_add(1);
            InputAction::Redraw
        }
        KeyCode::Char('c') | KeyCode::Char('C') => {
            let latest_diff = app
                .timeline_entries
                .iter()
                .rev()
                .find(|entry| !entry.diff.is_empty())
                .map(|entry| entry.diff.clone())
                .unwrap_or_default();
            InputAction::CopyToClipboard(latest_diff)
        }
        KeyCode::Char('u') | KeyCode::Char('U') => InputAction::RestoreLastMutation,
        _ => InputAction::None,
    }
}

fn handle_key_transcript_search(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Esc | KeyCode::Enter => {
            app.close_transcript_search();
            InputAction::Redraw
        }
        KeyCode::Backspace => {
            app.transcript_search.query.pop();
            app.transcript_search.selected_index = 0;
            InputAction::Redraw
        }
        KeyCode::Tab => {
            cycle_transcript_filters(app, false);
            InputAction::Redraw
        }
        KeyCode::BackTab => {
            cycle_transcript_filters(app, true);
            InputAction::Redraw
        }
        KeyCode::Up => {
            app.transcript_search.selected_index =
                app.transcript_search.selected_index.saturating_sub(1);
            InputAction::Redraw
        }
        KeyCode::Down => {
            let items = app.transcript_search_items();
            if app.transcript_search.selected_index + 1 < items.len() {
                app.transcript_search.selected_index += 1;
            }
            InputAction::Redraw
        }
        KeyCode::Char(c) => {
            app.transcript_search.query.push(c);
            app.transcript_search.selected_index = 0;
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

fn handle_key_plan_review(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Enter => {
            app.mode = AppMode::Normal;
            if app.plan_review_read_only {
                InputAction::Redraw
            } else {
                InputAction::PlanApproved
            }
        }
        KeyCode::Esc | KeyCode::Char('q') => {
            app.mode = AppMode::Normal;
            if app.plan_review_read_only {
                InputAction::Redraw
            } else {
                InputAction::PlanCancelled
            }
        }
        _ => InputAction::None,
    }
}

fn handle_mouse(app: &mut App, mouse: MouseEvent) -> InputAction {
    match mouse.kind {
        MouseEventKind::ScrollUp => {
            if app.mode == AppMode::InfoPopup {
                app.scroll_info_popup_up(3);
            } else {
                app.scroll_up(3);
            }
            InputAction::Redraw
        }
        MouseEventKind::ScrollDown => {
            if app.mode == AppMode::InfoPopup {
                app.scroll_info_popup_down(3);
            } else {
                app.scroll_down(3);
            }
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

    // Exact command matches should submit immediately, even if a longer command
    // shares the same prefix (for example, /checkpoint vs /checkpoints).
    if SLASH_COMMANDS.iter().any(|spec| spec.command == trimmed) {
        return false;
    }

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
    use crate::app::{
        ChatMessage, MutationReviewState, QuickOpenItemKind, TimelineEntry, TimelineEntryKind,
    };

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
    fn enter_submits_exact_command_when_longer_variant_exists() {
        let mut app = App::new();
        app.input_buffer = "/checkpoint".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Command;

        let action = handle_key_normal(&mut app, key_enter());

        match action {
            InputAction::Submit(text) => assert_eq!(text, "/checkpoint"),
            _ => panic!("expected submit action"),
        }
    }

    #[test]
    fn enter_submits_exact_command_with_plural_variant() {
        let mut app = App::new();
        app.input_buffer = "/provider".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Command;

        let action = handle_key_normal(&mut app, key_enter());

        match action {
            InputAction::Submit(text) => assert_eq!(text, "/provider"),
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
        let matches = command_palette_matches("/pro");
        assert!(matches.len() >= 2);
        let expected = matches[1].command.to_string();

        handle_key_normal(&mut app, key_down());
        let action = handle_key_normal(&mut app, key_enter());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.input_buffer, expected);
    }

    #[test]
    fn known_command_match_is_case_insensitive() {
        assert!(is_known_slash_command("/HeLp"));
        assert!(is_known_slash_command("/CoLlAb"));
    }

    #[test]
    fn closest_command_resolves_simple_typo() {
        assert_eq!(closest_slash_command("/hepl"), Some("/help"));
        assert_eq!(closest_slash_command("/statuz"), Some("/status"));
    }

    #[test]
    fn closest_command_rejects_ambiguous_typo() {
        assert_eq!(closest_slash_command("/providerz"), None);
    }

    #[test]
    fn closest_command_rejects_distant_typo() {
        assert_eq!(closest_slash_command("/zzzzzz"), None);
    }

    #[test]
    fn command_palette_includes_collab() {
        let matches = command_palette_matches("/col");
        assert!(matches.iter().any(|spec| spec.command == "/collab"));
    }

    #[test]
    fn ctrl_i_requests_context_inspector() {
        let mut app = App::new();
        let action = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('i'), KeyModifiers::CONTROL),
        );
        assert!(matches!(action, InputAction::OpenContextInspector));
    }

    #[test]
    fn ctrl_f_requests_transcript_search() {
        let mut app = App::new();
        let action = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('f'), KeyModifiers::CONTROL),
        );
        assert!(matches!(action, InputAction::OpenTranscriptSearch));
    }

    #[test]
    fn mutation_review_enter_approves_permission() {
        let mut app = App::new();
        app.mode = AppMode::MutationReview;
        app.mutation_review = Some(MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "edit_file".to_string(),
            operation: "edit_file".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec!["/tmp/demo.py".to_string()],
            diff: "--- a\n+++ b".to_string(),
            checkpoint_id: None,
            changed: Some(true),
            message: "preview".to_string(),
            selected_path_index: 0,
            chunks: Vec::new(),
            selected_chunk_index: 0,
        });

        let action = handle_key(&mut app, key_enter());

        assert!(matches!(action, InputAction::PermissionAnswered(true)));
    }

    #[test]
    fn mutation_review_file_scope_tracks_selected_path() {
        let mut app = App::new();
        app.mode = AppMode::MutationReview;
        app.mutation_review = Some(MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec!["/tmp/demo.py".to_string(), "/tmp/other.py".to_string()],
            diff: "--- a\n+++ b".to_string(),
            checkpoint_id: None,
            changed: Some(true),
            message: "preview".to_string(),
            selected_path_index: 1,
            chunks: vec![
                crate::app::MutationReviewChunk {
                    path: "/tmp/demo.py".to_string(),
                    hunk_index: 0,
                    header: "@@ -1 +1 @@".to_string(),
                    diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                    selected: false,
                },
                crate::app::MutationReviewChunk {
                    path: "/tmp/other.py".to_string(),
                    hunk_index: 0,
                    header: "@@ -4 +4 @@".to_string(),
                    diff: "@@ -4 +4 @@\n-left\n+right".to_string(),
                    selected: false,
                },
            ],
            selected_chunk_index: 1,
        });

        let action = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('f'), KeyModifiers::NONE),
        );

        assert!(matches!(action, InputAction::PermissionAnswered(true)));
        assert_eq!(
            app.permission_approved_paths,
            vec!["/tmp/other.py".to_string()]
        );
    }

    #[test]
    fn mutation_review_chunk_scope_tracks_selected_hunk() {
        let mut app = App::new();
        app.mode = AppMode::MutationReview;
        app.mutation_review = Some(MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec!["/tmp/demo.py".to_string()],
            diff: "--- a/demo.py\n+++ b/demo.py\n@@ -1 +1 @@\n-old\n+new".to_string(),
            checkpoint_id: None,
            changed: Some(true),
            message: "preview".to_string(),
            selected_path_index: 0,
            chunks: vec![crate::app::MutationReviewChunk {
                path: "/tmp/demo.py".to_string(),
                hunk_index: 0,
                header: "@@ -1 +1 @@".to_string(),
                diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                selected: false,
            }],
            selected_chunk_index: 0,
        });

        let toggle = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char(' '), KeyModifiers::NONE),
        );
        assert!(matches!(toggle, InputAction::Redraw));
        assert!(app
            .mutation_review
            .as_ref()
            .and_then(|review| review.chunks.first())
            .map(|chunk| chunk.selected)
            .unwrap_or(false));

        let action = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('h'), KeyModifiers::NONE),
        );

        assert!(matches!(action, InputAction::PermissionAnswered(true)));
        assert_eq!(
            app.permission_approved_chunks,
            vec![crate::app::ApprovedReviewChunk {
                path: "/tmp/demo.py".to_string(),
                hunk_index: 0,
            }]
        );
    }

    #[test]
    fn mutation_review_tab_jumps_between_file_groups() {
        let mut app = App::new();
        app.mode = AppMode::MutationReview;
        app.mutation_review = Some(MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec!["/tmp/demo.py".to_string(), "/tmp/other.py".to_string()],
            diff: String::new(),
            checkpoint_id: None,
            changed: Some(true),
            message: "preview".to_string(),
            selected_path_index: 0,
            chunks: vec![
                crate::app::MutationReviewChunk {
                    path: "/tmp/demo.py".to_string(),
                    hunk_index: 0,
                    header: "@@ -1 +1 @@".to_string(),
                    diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                    selected: false,
                },
                crate::app::MutationReviewChunk {
                    path: "/tmp/demo.py".to_string(),
                    hunk_index: 1,
                    header: "@@ -4 +4 @@".to_string(),
                    diff: "@@ -4 +4 @@\n-left\n+right".to_string(),
                    selected: false,
                },
                crate::app::MutationReviewChunk {
                    path: "/tmp/other.py".to_string(),
                    hunk_index: 0,
                    header: "@@ -8 +8 @@".to_string(),
                    diff: "@@ -8 +8 @@\n-before\n+after".to_string(),
                    selected: false,
                },
            ],
            selected_chunk_index: 0,
        });

        let action = handle_key(&mut app, KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE));

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(
            app.mutation_review
                .as_ref()
                .map(|review| review.selected_chunk_index),
            Some(2)
        );
        assert_eq!(
            app.mutation_review
                .as_ref()
                .map(|review| review.selected_path_index),
            Some(1)
        );
    }

    #[test]
    fn mutation_review_file_group_shortcuts_select_and_clear_current_file() {
        let mut app = App::new();
        app.mode = AppMode::MutationReview;
        app.mutation_review = Some(MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "apply_patch_unified".to_string(),
            operation: "apply_patch_unified".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec!["/tmp/demo.py".to_string(), "/tmp/other.py".to_string()],
            diff: String::new(),
            checkpoint_id: None,
            changed: Some(true),
            message: "preview".to_string(),
            selected_path_index: 0,
            chunks: vec![
                crate::app::MutationReviewChunk {
                    path: "/tmp/demo.py".to_string(),
                    hunk_index: 0,
                    header: "@@ -1 +1 @@".to_string(),
                    diff: "@@ -1 +1 @@\n-old\n+new".to_string(),
                    selected: false,
                },
                crate::app::MutationReviewChunk {
                    path: "/tmp/demo.py".to_string(),
                    hunk_index: 1,
                    header: "@@ -4 +4 @@".to_string(),
                    diff: "@@ -4 +4 @@\n-left\n+right".to_string(),
                    selected: false,
                },
                crate::app::MutationReviewChunk {
                    path: "/tmp/other.py".to_string(),
                    hunk_index: 0,
                    header: "@@ -8 +8 @@".to_string(),
                    diff: "@@ -8 +8 @@\n-before\n+after".to_string(),
                    selected: false,
                },
            ],
            selected_chunk_index: 0,
        });

        let select_action = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('s'), KeyModifiers::NONE),
        );
        assert!(matches!(select_action, InputAction::Redraw));
        assert_eq!(
            app.mutation_review.as_ref().map(|review| {
                review
                    .chunks
                    .iter()
                    .map(|chunk| chunk.selected)
                    .collect::<Vec<_>>()
            }),
            Some(vec![true, true, false])
        );

        let clear_action = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('r'), KeyModifiers::NONE),
        );
        assert!(matches!(clear_action, InputAction::Redraw));
        assert_eq!(
            app.mutation_review.as_ref().map(|review| {
                review
                    .chunks
                    .iter()
                    .map(|chunk| chunk.selected)
                    .collect::<Vec<_>>()
            }),
            Some(vec![false, false, false])
        );
    }

    #[test]
    fn quick_open_enter_returns_selected_item() {
        let mut app = App::new();
        app.mode = AppMode::QuickOpen;
        app.quick_open.items = vec![
            crate::app::QuickOpenItem {
                kind: QuickOpenItemKind::Command,
                label: "/help".to_string(),
                detail: "Show help".to_string(),
                value: "/help".to_string(),
            },
            crate::app::QuickOpenItem {
                kind: QuickOpenItemKind::Prompt,
                label: "review auth".to_string(),
                detail: "recent prompt".to_string(),
                value: "review auth".to_string(),
            },
        ];
        app.quick_open.selected_index = 1;

        let action = handle_key(&mut app, key_enter());

        match action {
            InputAction::QuickOpenSelected(item) => assert_eq!(item.value, "review auth"),
            _ => panic!("expected quick-open selection"),
        }
    }

    #[test]
    fn transcript_search_filters_messages_and_diffs() {
        let mut app = App::new();
        app.messages
            .push(ChatMessage::assistant("fixed auth retry flow"));
        app.messages.push(ChatMessage::diff_view(
            "auth.rs",
            "--- a/auth.rs\n+++ b/auth.rs\n+retry",
        ));
        app.push_timeline_entry(TimelineEntry {
            kind: TimelineEntryKind::ToolResult,
            request_id: "req-1".to_string(),
            title: "edit_file".to_string(),
            detail: "Updated auth.rs".to_string(),
            diff: String::new(),
            paths: vec!["/tmp/auth.rs".to_string()],
            checkpoint_id: None,
            changed: Some(true),
            review_summary: None,
            timestamp: std::time::Instant::now(),
        });
        app.open_transcript_search();
        app.transcript_search.query = "retry".to_string();
        app.transcript_search.include_messages = false;
        app.transcript_search.include_tools = false;
        app.transcript_search.include_diffs = true;

        let items = app.transcript_search_items();
        assert_eq!(items.len(), 1);
        assert_eq!(items[0].label, "Diff / auth.rs");

        app.transcript_search.query = "auth".to_string();
        app.transcript_search.include_messages = false;
        app.transcript_search.include_tools = true;
        app.transcript_search.include_diffs = false;
        let tool_items = app.transcript_search_items();
        assert_eq!(tool_items.len(), 1);
        assert!(tool_items[0].label.contains("Tool result"));
    }
}
