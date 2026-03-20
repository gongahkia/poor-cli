/// Input handling: keyboard events, slash-command completion, etc.
mod mode_handlers;

use crate::app::{App, AppMode, OverlayKind, QuickOpenItem};
pub use crate::command_manifest::{help_markdown, SlashCommandSpec, SLASH_COMMANDS};
use crossterm::event::{Event, KeyCode, KeyEvent, KeyModifiers, MouseEvent, MouseEventKind};

/// Outcome of processing one input event.
pub enum InputAction {
    None,
    Submit(String),
    Quit,
    Redraw,
    ProviderSelected(usize),
    PermissionAnswered(bool),
    Cancel,
    PlanApproved,
    PlanCancelled,
    CompactStrategySelected(String),
    CopyToClipboard(String),
    JoinWizardComplete(crate::multiplayer::RemoteBootstrap),
    SaveApiKeyEditor,
    OpenQuickOpen,
    QuickOpenSelected(QuickOpenItem),
    RestoreLastMutation,
    OpenFileInEditor(String),
}

pub fn command_palette_matches(prefix: &str) -> Vec<&'static SlashCommandSpec> {
    let trimmed = prefix.trim();
    if !trimmed.starts_with('/') {
        return Vec::new();
    }

    if trimmed == "/" {
        return SLASH_COMMANDS
            .iter()
            .filter(|spec| spec.recommended && !spec.hidden)
            .collect();
    }

    SLASH_COMMANDS
        .iter()
        .filter(|spec| !spec.hidden && spec.command.starts_with(trimmed))
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

    for spec in SLASH_COMMANDS.iter() {
        let command = spec.command.as_str();
        let distance = levenshtein_distance(&normalized, command);
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
            None => best = Some((command, distance, max_len)),
            Some((_, best_distance, best_len)) => {
                if (distance, max_len) < (best_distance, best_len) {
                    second_best_distance = Some(best_distance);
                    best = Some((command, distance, max_len));
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
            KeyCode::Char('p') => {
                return InputAction::OpenQuickOpen;
            }
            KeyCode::Char('s') if app.overlay_kind == Some(OverlayKind::ApiKeyEditor) => {
                return InputAction::SaveApiKeyEditor;
            }
            _ => {}
        }
    }

    // Mode-specific handling
    match app.mode {
        AppMode::Normal => mode_handlers::handle_key_normal(app, key),
        AppMode::Overlay => match app.overlay_kind {
            Some(OverlayKind::ProviderSelect) => mode_handlers::handle_key_provider_select(app, key),
            Some(OverlayKind::InfoPopup) => mode_handlers::handle_key_info_popup(app, key),
            Some(OverlayKind::ApiKeyEditor) => mode_handlers::handle_key_api_key_editor(app, key),
            Some(OverlayKind::JoinWizard) => mode_handlers::handle_key_join_wizard(app, key),
            Some(OverlayKind::GraphOverlay) => {
                if matches!(key.code, KeyCode::Esc) {
                    app.graph_overlay.active = false;
                    app.overlay_kind = None;
                    app.mode = AppMode::Normal;
                }
                InputAction::Redraw
            }
            None => {
                app.mode = AppMode::Normal;
                InputAction::Redraw
            }
        },
        AppMode::QuickOpen => mode_handlers::handle_key_quick_open(app, key),
        AppMode::InlineApproval => mode_handlers::handle_key_inline_approval(app, key),
        AppMode::Quitting => InputAction::Quit,
    }
}

fn sync_text_input_state(app: &mut App) {
    app.mode = AppMode::Normal;
    app.command_match_index = 0;
    app.refresh_at_path_completion();
    clamp_command_match_index(app);
}

fn open_shortcuts_help(app: &mut App) -> InputAction {
    app.open_info_popup_with_return(
        "Shortcuts",
        help_markdown().to_string(),
        Some(AppMode::Normal),
    );
    InputAction::Redraw
}

fn open_permission_help(app: &mut App) -> InputAction {
    let mut lines = vec![
        "# Approval Help".to_string(),
        "PoorCLI paused because this request needs explicit approval before it can continue."
            .to_string(),
        String::new(),
        "## Pending request".to_string(),
    ];

    if app.permission_message.trim().is_empty() {
        lines.push("No additional request details were provided.".to_string());
    } else {
        lines.push("```text".to_string());
        lines.push(app.permission_message.clone());
        lines.push("```".to_string());
    }

    lines.push(String::new());
    lines.push("## Keys".to_string());
    lines.push("- `y` or `Enter`: allow this request once".to_string());
    lines.push("- `n` or `Esc`: deny this request".to_string());
    lines.push("- `?`: reopen this help".to_string());

    app.open_info_popup_with_return(
        "Approval Help",
        lines.join("\n"),
        Some(AppMode::InlineApproval),
    );
    InputAction::Redraw
}

fn open_mutation_review_help(app: &mut App) -> InputAction {
    let Some(review) = app.mutation_review.as_ref() else {
        return InputAction::None;
    };

    let mut lines = vec![
        "# Mutation Review Help".to_string(),
        "PoorCLI is showing the exact file changes before it applies them.".to_string(),
        String::new(),
        "## Pending mutation".to_string(),
        format!("- Tool: `{}`", review.tool_name),
        format!("- Operation: `{}`", review.operation),
    ];

    if !review.paths.is_empty() {
        lines.push(format!("- Files: {}", review.paths.join(", ")));
    }
    if let Some(checkpoint_id) = review
        .checkpoint_id
        .as_ref()
        .filter(|value| !value.is_empty())
    {
        lines.push(format!("- Checkpoint: `{checkpoint_id}`"));
    }

    lines.push(String::new());
    lines.push("## Keys".to_string());
    lines.push("- `y` or `Enter`: approve the current review selection".to_string());
    lines.push("- `n` or `Esc`: reject the mutation".to_string());
    if review.supports_chunk_approval() {
        lines.push("- `Space`: toggle the current hunk".to_string());
        lines.push("- `h`: approve the selected hunks".to_string());
        lines.push("- `f`: approve all hunks in the current file".to_string());
    }
    lines.push("- `o`: open the selected file in your editor".to_string());
    lines.push("- `u`: restore the last mutation checkpoint".to_string());
    lines.push("- `?`: reopen this help".to_string());

    app.open_info_popup_with_return(
        "Mutation Review Help",
        lines.join("\n"),
        Some(AppMode::InlineApproval),
    );
    InputAction::Redraw
}

fn open_plan_review_help(app: &mut App) -> InputAction {
    let mut lines = vec![
        "# Plan Review Help".to_string(),
        "PoorCLI pauses here so you can inspect the plan before it executes the next stage."
            .to_string(),
    ];

    if !app.plan.summary.trim().is_empty() {
        lines.push(String::new());
        lines.push("## Summary".to_string());
        lines.push(app.plan.summary.clone());
    }

    if !app.plan.original_request.trim().is_empty() {
        lines.push(String::new());
        lines.push(format!("Request: `{}`", app.plan.original_request));
    }

    lines.push(String::new());
    lines.push("## Keys".to_string());
    if app.plan.review_read_only {
        lines.push("- `Enter`: close this review".to_string());
        lines.push("- `Esc`: dismiss this review".to_string());
    } else if app.plan.is_execution_gate {
        lines.push("- `Enter`: approve the plan".to_string());
        lines.push("- `Esc`: reject the plan".to_string());
    } else {
        lines.push("- `Enter`: execute the plan".to_string());
        lines.push("- `Esc`: cancel execution".to_string());
    }
    lines.push("- `?`: reopen this help".to_string());

    app.open_info_popup_with_return(
        "Plan Review Help",
        lines.join("\n"),
        Some(AppMode::InlineApproval),
    );
    InputAction::Redraw
}

fn handle_mouse(app: &mut App, mouse: MouseEvent) -> InputAction {
    match mouse.kind {
        MouseEventKind::ScrollUp => {
            if app.overlay_kind == Some(OverlayKind::InfoPopup) {
                app.scroll_info_popup_up(3);
            } else {
                app.scroll_up(3);
            }
            InputAction::Redraw
        }
        MouseEventKind::ScrollDown => {
            if app.overlay_kind == Some(OverlayKind::InfoPopup) {
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
    use super::mode_handlers::*;
    use crate::app::{
        ChatMessage, MutationReviewState, OverlayKind, ProviderEntry, ProviderSelectPane,
        QueuedPrompt, QuickOpenItemKind, TimelineEntry, TimelineEntryKind,
    };
    use std::fs;
    use std::path::PathBuf;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn key_enter() -> KeyEvent {
        KeyEvent::new(KeyCode::Enter, KeyModifiers::NONE)
    }

    fn key_up() -> KeyEvent {
        KeyEvent::new(KeyCode::Up, KeyModifiers::NONE)
    }

    fn key_down() -> KeyEvent {
        KeyEvent::new(KeyCode::Down, KeyModifiers::NONE)
    }

    fn key_left() -> KeyEvent {
        KeyEvent::new(KeyCode::Left, KeyModifiers::NONE)
    }

    fn key_right() -> KeyEvent {
        KeyEvent::new(KeyCode::Right, KeyModifiers::NONE)
    }

    fn key_esc() -> KeyEvent {
        KeyEvent::new(KeyCode::Esc, KeyModifiers::NONE)
    }

    fn key_question() -> KeyEvent {
        KeyEvent::new(KeyCode::Char('?'), KeyModifiers::NONE)
    }

    fn create_temp_workspace(prefix: &str) -> PathBuf {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time should move forward")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("poor-cli-input-{prefix}-{ts}"));
        fs::create_dir_all(&root).expect("temp workspace should be created");
        root
    }

    #[test]
    fn enter_autocompletes_partial_command() {
        let mut app = App::new();
        app.input_buffer = "/new-ses".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Normal;

        let action = handle_key_normal(&mut app, key_enter());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.input_buffer, "/new-session");
    }

    #[test]
    fn enter_submits_exact_command() {
        let mut app = App::new();
        app.input_buffer = "/new-session".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Normal;

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
        app.mode = AppMode::Normal;

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
        app.mode = AppMode::Normal;

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
        app.mode = AppMode::Normal;

        let action = handle_key_normal(&mut app, key_enter());

        match action {
            InputAction::Submit(text) => assert_eq!(text, "/theme da"),
            _ => panic!("expected submit action"),
        }
    }

    #[test]
    fn arrow_keys_navigate_command_matches() {
        let mut app = App::new();
        app.input_buffer = "/co".to_string(); // matches multiple visible commands
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Normal;

        let down = handle_key_normal(&mut app, key_down());
        assert!(matches!(down, InputAction::Redraw));
        assert_eq!(app.command_match_index, 1);

        let up = handle_key_normal(&mut app, key_up());
        assert!(matches!(up, InputAction::Redraw));
        assert_eq!(app.command_match_index, 0);
    }

    #[test]
    fn provider_select_right_focuses_model_pane() {
        let mut app = App::new();
        app.mode = AppMode::Overlay;
        app.overlay_kind = Some(OverlayKind::ProviderSelect);
        app.provider.list = vec![ProviderEntry {
            name: "openai".to_string(),
            available: true,
            ready: true,
            status_label: "API key configured".to_string(),
            models: vec![
                crate::provider_catalog::default_model("openai").to_string(),
                "gpt-5-mini".to_string(),
            ],
        }];
        app.open_provider_select();

        let action = handle_key_provider_select(&mut app, key_right());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.provider.select_pane, ProviderSelectPane::Models);
        assert_eq!(
            app.selected_provider_model().as_deref(),
            Some(crate::provider_catalog::default_model("openai"))
        );
    }

    #[test]
    fn provider_select_up_down_navigate_models_when_model_pane_is_focused() {
        let mut app = App::new();
        app.provider.list = vec![ProviderEntry {
            name: "openai".to_string(),
            available: true,
            ready: true,
            status_label: "API key configured".to_string(),
            models: vec![
                crate::provider_catalog::default_model("openai").to_string(),
                "gpt-5".to_string(),
                "gpt-5-mini".to_string(),
            ],
        }];
        app.open_provider_select();
        app.provider.select_pane = ProviderSelectPane::Models;

        let down = handle_key_provider_select(&mut app, key_down());
        assert!(matches!(down, InputAction::Redraw));
        assert_eq!(app.selected_provider_model().as_deref(), Some("gpt-5"));

        let up = handle_key_provider_select(&mut app, key_up());
        assert!(matches!(up, InputAction::Redraw));
        assert_eq!(
            app.selected_provider_model().as_deref(),
            Some(crate::provider_catalog::default_model("openai"))
        );
    }

    #[test]
    fn provider_select_left_returns_to_provider_pane() {
        let mut app = App::new();
        app.provider.list = vec![ProviderEntry {
            name: "openai".to_string(),
            available: true,
            ready: true,
            status_label: "API key configured".to_string(),
            models: vec![crate::provider_catalog::default_model("openai").to_string()],
        }];
        app.open_provider_select();
        app.provider.select_pane = ProviderSelectPane::Models;

        let action = handle_key_provider_select(&mut app, key_left());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.provider.select_pane, ProviderSelectPane::Providers);
    }

    #[test]
    fn question_mark_opens_shortcuts_when_input_is_empty() {
        let mut app = App::new();

        let action = handle_key_normal(&mut app, key_question());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.mode, AppMode::Overlay);
        assert_eq!(app.overlay_kind, Some(OverlayKind::InfoPopup));
        assert_eq!(app.info_popup_title, "Shortcuts");
        assert_eq!(app.info_popup_return_mode, Some(AppMode::Normal));
    }

    #[test]
    fn permission_prompt_question_mark_opens_help_and_returns() {
        let mut app = App::new();
        app.mode = AppMode::InlineApproval;
        app.permission_message = "write_file: {\"file_path\":\"/tmp/demo.txt\"}".to_string();

        let action = open_permission_help(&mut app);

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.mode, AppMode::Overlay);
        assert_eq!(app.overlay_kind, Some(OverlayKind::InfoPopup));
        assert_eq!(app.info_popup_title, "Approval Help");

        let close = handle_key_info_popup(&mut app, key_esc());

        assert!(matches!(close, InputAction::Redraw));
        assert_eq!(app.mode, AppMode::InlineApproval);
    }

    #[test]
    fn mutation_review_question_mark_opens_help_and_returns() {
        let mut app = App::new();
        app.open_mutation_review(MutationReviewState {
            request_id: "req-1".to_string(),
            tool_name: "write_file".to_string(),
            operation: "write_file".to_string(),
            prompt_id: "prompt-1".to_string(),
            paths: vec!["/tmp/demo.txt".to_string()],
            diff: "@@ -0,0 +1 @@\n+hello".to_string(),
            checkpoint_id: Some("cp-1".to_string()),
            changed: Some(true),
            message: "Preview write".to_string(),
            selected_path_index: 0,
            chunks: Vec::new(),
            selected_chunk_index: 0,
        });

        let action = handle_key_mutation_review(&mut app, key_question());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.mode, AppMode::Overlay);
        assert_eq!(app.overlay_kind, Some(OverlayKind::InfoPopup));
        assert_eq!(app.info_popup_title, "Mutation Review Help");

        let close = handle_key_info_popup(&mut app, key_esc());

        assert!(matches!(close, InputAction::Redraw));
        assert_eq!(app.mode, AppMode::InlineApproval);
    }

    #[test]
    fn plan_review_question_mark_opens_help_and_returns() {
        let mut app = App::new();
        app.mode = AppMode::InlineApproval;
        app.plan.summary = "Need approval before mutating files.".to_string();
        app.plan.original_request = "Update the config".to_string();
        app.plan.is_execution_gate = true;
        app.plan.steps = vec![crate::app::PlanStep {
            description: "step1".to_string(),
            status: crate::app::PlanStepStatus::Pending,
        }];

        let action = handle_key_inline_approval(&mut app, key_question());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.mode, AppMode::Overlay);
        assert_eq!(app.overlay_kind, Some(OverlayKind::InfoPopup));
        assert_eq!(app.info_popup_title, "Plan Review Help");

        let close = handle_key_info_popup(&mut app, key_esc());

        assert!(matches!(close, InputAction::Redraw));
        assert_eq!(app.mode, AppMode::InlineApproval);
    }

    #[test]
    fn enter_confirms_selected_match_when_multiple_exist() {
        let mut app = App::new();
        app.input_buffer = "/co".to_string(); // matches multiple visible commands
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Normal;
        let matches = command_palette_matches("/co");
        assert!(matches.len() >= 2);
        let expected = matches[1].command.to_string();

        handle_key_normal(&mut app, key_down());
        let action = handle_key_normal(&mut app, key_enter());

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.input_buffer, expected);
    }

    #[test]
    fn tab_accepts_at_path_completion() {
        let root = create_temp_workspace("at-path");
        fs::create_dir_all(root.join("src")).expect("src dir");
        fs::write(root.join("src").join("main.rs"), "fn main() {}\n").expect("main file");

        let mut app = App::new();
        app.cwd = root.to_string_lossy().to_string();
        app.input_buffer = "@src/ma".to_string();
        app.input_cursor = app.input_buffer.len();
        app.mode = AppMode::Normal;
        app.refresh_at_path_completion();

        let action = handle_key_normal(&mut app, KeyEvent::new(KeyCode::Tab, KeyModifiers::NONE));

        assert!(matches!(action, InputAction::Redraw));
        assert_eq!(app.input_buffer, "@src/main.rs ");

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn queue_manager_opens_info_popup() {
        let mut app = App::new();
        app.prompt_queue
            .push_back(QueuedPrompt::user("first prompt"));
        app.prompt_queue
            .push_back(QueuedPrompt::user("second prompt"));
        app.open_queue_manager();

        assert_eq!(app.mode, AppMode::Overlay);
        assert_eq!(app.overlay_kind, Some(OverlayKind::InfoPopup));
        assert!(app.info_popup_content.contains("first prompt"));
        assert!(app.info_popup_content.contains("second prompt"));
    }

    #[test]
    fn waiting_state_still_allows_typing_and_submit() {
        let mut app = App::new();
        app.waiting = true;
        app.mode = AppMode::Normal;

        let typed = handle_key_normal(
            &mut app,
            KeyEvent::new(KeyCode::Char('q'), KeyModifiers::NONE),
        );
        assert!(matches!(typed, InputAction::Redraw));
        assert_eq!(app.input_buffer, "q");

        let action = handle_key_normal(&mut app, key_enter());
        match action {
            InputAction::Submit(text) => assert_eq!(text, "q"),
            _ => panic!("expected submit action while waiting"),
        }
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
    fn ctrl_p_requests_quick_open() {
        let mut app = App::new();
        let action = handle_key(
            &mut app,
            KeyEvent::new(KeyCode::Char('p'), KeyModifiers::CONTROL),
        );
        assert!(matches!(action, InputAction::OpenQuickOpen));
    }

    #[test]
    fn mutation_review_enter_approves_permission() {
        let mut app = App::new();
        app.mode = AppMode::InlineApproval;
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
        app.mode = AppMode::InlineApproval;
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
        app.mode = AppMode::InlineApproval;
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
        app.mode = AppMode::InlineApproval;
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
        app.mode = AppMode::InlineApproval;
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
