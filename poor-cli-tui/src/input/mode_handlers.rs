use crate::app::{App, AppMode, ProviderSelectPane, QuickOpenItem};
use crossterm::event::{KeyCode, KeyEvent, KeyModifiers};
use super::{
    InputAction, autocomplete_command, navigate_command_matches,
    open_mutation_review_help, open_permission_help, open_plan_review_help, open_shortcuts_help,
    should_autocomplete_on_enter, sync_text_input_state,
};

pub(super) fn handle_key_normal(app: &mut App, key: KeyEvent) -> InputAction {
    // While waiting, Esc still cancels the active request, but normal input remains editable so
    // plain-text prompts can be queued for auto-send once the current request finishes.
    if app.waiting {
        if key.code == KeyCode::Esc {
            return InputAction::Cancel;
        }
    }

    if app.at_path_completion.active {
        match key.code {
            KeyCode::Up => {
                if app.move_at_path_selection(false) {
                    return InputAction::Redraw;
                }
            }
            KeyCode::Down => {
                if app.move_at_path_selection(true) {
                    return InputAction::Redraw;
                }
            }
            KeyCode::Tab => {
                if app.accept_at_path_completion() {
                    return InputAction::Redraw;
                }
            }
            KeyCode::Enter
                if !key.modifiers.contains(KeyModifiers::ALT)
                    && !key.modifiers.contains(KeyModifiers::SHIFT) =>
            {
                if app.accept_at_path_completion() {
                    return InputAction::Redraw;
                }
            }
            KeyCode::Esc => {
                app.clear_at_path_completion();
                return InputAction::Redraw;
            }
            _ => {}
        }
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
                app.refresh_at_path_completion();
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
            sync_text_input_state(app);
            InputAction::Redraw
        }
        KeyCode::Delete => {
            app.delete_char();
            sync_text_input_state(app);
            InputAction::Redraw
        }
        KeyCode::Left => {
            app.cursor_left();
            app.refresh_at_path_completion();
            InputAction::Redraw
        }
        KeyCode::Right => {
            app.cursor_right();
            app.refresh_at_path_completion();
            InputAction::Redraw
        }
        KeyCode::Home => {
            app.cursor_home();
            app.refresh_at_path_completion();
            InputAction::Redraw
        }
        KeyCode::End => {
            app.cursor_end();
            app.refresh_at_path_completion();
            InputAction::Redraw
        }
        KeyCode::Up => {
            if navigate_command_matches(app, false) {
                return InputAction::Redraw;
            }
            app.history_prev();
            sync_text_input_state(app);
            InputAction::Redraw
        }
        KeyCode::Down => {
            if navigate_command_matches(app, true) {
                return InputAction::Redraw;
            }
            app.history_next();
            sync_text_input_state(app);
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
            sync_text_input_state(app);
            InputAction::Redraw
        }
        KeyCode::Esc => {
            if !app.input_buffer.is_empty() {
                app.input_buffer.clear();
                app.input_cursor = 0;
                app.mode = AppMode::Normal;
            }
            app.command_match_index = 0;
            app.clear_at_path_completion();
            InputAction::Redraw
        }
        KeyCode::Char(c) => {
            if c == '?' && app.input_buffer.trim().is_empty() && !app.waiting {
                return open_shortcuts_help(app);
            }
            app.insert_char(c);
            sync_text_input_state(app);
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

pub(super) fn handle_key_provider_select(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Up => {
            let moved = if app.provider_select_pane == ProviderSelectPane::Models {
                app.move_provider_model_selection(false)
            } else {
                app.move_provider_selection(false)
            };
            if moved {
                InputAction::Redraw
            } else {
                InputAction::None
            }
        }
        KeyCode::Down => {
            let moved = if app.provider_select_pane == ProviderSelectPane::Models {
                app.move_provider_model_selection(true)
            } else {
                app.move_provider_selection(true)
            };
            if moved {
                InputAction::Redraw
            } else {
                InputAction::None
            }
        }
        KeyCode::Left => {
            if app.focus_provider_list() {
                InputAction::Redraw
            } else {
                InputAction::None
            }
        }
        KeyCode::Right => {
            if app.focus_provider_models() {
                InputAction::Redraw
            } else {
                InputAction::None
            }
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

pub(super) fn handle_key_compact_select(app: &mut App, key: KeyEvent) -> InputAction {
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

pub(super) fn extract_copyable_items(content: &str) -> Vec<String> {
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

pub(super) fn handle_key_info_popup(app: &mut App, key: KeyEvent) -> InputAction {
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

pub(super) fn api_key_editor_prev_boundary(text: &str, cursor: usize) -> usize {
    if cursor == 0 {
        return 0;
    }
    text[..cursor]
        .char_indices()
        .last()
        .map(|(idx, _)| idx)
        .unwrap_or(0)
}

pub(super) fn api_key_editor_next_boundary(text: &str, cursor: usize) -> usize {
    if cursor >= text.len() {
        return text.len();
    }
    text[cursor..]
        .char_indices()
        .nth(1)
        .map(|(idx, _)| cursor + idx)
        .unwrap_or(text.len())
}

pub(super) fn handle_key_api_key_editor(app: &mut App, key: KeyEvent) -> InputAction {
    let Some(state) = app.api_key_editor.as_mut() else {
        app.mode = AppMode::Normal;
        return InputAction::Redraw;
    };

    let field_count = state.fields.len();
    if field_count == 0 {
        app.close_api_key_editor();
        return InputAction::Redraw;
    }

    match key.code {
        KeyCode::Esc => {
            app.close_api_key_editor();
            InputAction::Redraw
        }
        KeyCode::Up | KeyCode::BackTab => {
            if state.selected_index > 0 {
                state.selected_index -= 1;
            }
            state.cursor = state.fields[state.selected_index].value.len();
            state.error.clear();
            InputAction::Redraw
        }
        KeyCode::Down | KeyCode::Tab => {
            if state.selected_index + 1 < field_count {
                state.selected_index += 1;
            }
            state.cursor = state.fields[state.selected_index].value.len();
            state.error.clear();
            InputAction::Redraw
        }
        KeyCode::Left => {
            let field = &state.fields[state.selected_index];
            state.cursor = api_key_editor_prev_boundary(&field.value, state.cursor);
            InputAction::Redraw
        }
        KeyCode::Right => {
            let field = &state.fields[state.selected_index];
            state.cursor = api_key_editor_next_boundary(&field.value, state.cursor);
            InputAction::Redraw
        }
        KeyCode::Home => {
            state.cursor = 0;
            InputAction::Redraw
        }
        KeyCode::End => {
            state.cursor = state.fields[state.selected_index].value.len();
            InputAction::Redraw
        }
        KeyCode::Backspace => {
            let field = &mut state.fields[state.selected_index];
            if state.cursor > 0 {
                let prev = api_key_editor_prev_boundary(&field.value, state.cursor);
                field.value.drain(prev..state.cursor);
                state.cursor = prev;
            }
            state.error.clear();
            state.status.clear();
            InputAction::Redraw
        }
        KeyCode::Delete => {
            let field = &mut state.fields[state.selected_index];
            if state.cursor < field.value.len() {
                let next = api_key_editor_next_boundary(&field.value, state.cursor);
                field.value.drain(state.cursor..next);
            }
            state.error.clear();
            state.status.clear();
            InputAction::Redraw
        }
        KeyCode::Enter => {
            if state.selected_index + 1 < field_count {
                state.selected_index += 1;
                state.cursor = state.fields[state.selected_index].value.len();
                InputAction::Redraw
            } else {
                InputAction::SaveApiKeyEditor
            }
        }
        KeyCode::Char(c) => {
            let field = &mut state.fields[state.selected_index];
            field.value.insert(state.cursor, c);
            state.cursor += c.len_utf8();
            state.error.clear();
            state.status.clear();
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}

pub(super) fn handle_key_join_wizard(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Esc => {
            app.join_wizard_active = false;
            app.join_wizard_step = 0;
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
            if input.is_empty() {
                app.join_wizard_error = "Paste a collaboration invite code.".to_string();
                return InputAction::Redraw;
            }

            let bootstrap = match crate::multiplayer::decode_invite_code(&input) {
                Ok(bootstrap) => bootstrap,
                Err(error) => {
                    app.join_wizard_error = error;
                    return InputAction::Redraw;
                }
            };

            match crate::multiplayer::preflight_join_endpoint(&bootstrap.signaling_url) {
                Ok(_) => {
                    app.join_wizard_active = false;
                    app.join_wizard_step = 0;
                    app.join_wizard_input.clear();
                    app.join_wizard_error.clear();
                    app.mode = AppMode::Normal;
                    InputAction::JoinWizardComplete(bootstrap)
                }
                Err(e) => {
                    app.join_wizard_error = format!("Preflight failed: {e}");
                    InputAction::Redraw
                }
            }
        }
        _ => InputAction::None,
    }
}

pub(super) fn handle_key_permission(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Char('?') => open_permission_help(app),
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

pub(super) fn handle_key_mutation_review(app: &mut App, key: KeyEvent) -> InputAction {
    if app.mutation_review.is_none() {
        app.mode = AppMode::Normal;
        return InputAction::Redraw;
    }

    match key.code {
        KeyCode::Char('?') => open_mutation_review_help(app),
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

pub(super) fn handle_key_context_inspector(app: &mut App, key: KeyEvent) -> InputAction {
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

pub(super) fn filtered_quick_open_items(app: &App) -> Vec<QuickOpenItem> {
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

pub(super) fn cycle_transcript_filters(app: &mut App, reverse: bool) {
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

pub(super) fn handle_key_quick_open(app: &mut App, key: KeyEvent) -> InputAction {
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

pub(super) fn handle_key_queue_manager(app: &mut App, key: KeyEvent) -> InputAction {
    if app.prompt_queue.is_empty() {
        match key.code {
            KeyCode::Esc | KeyCode::Enter | KeyCode::Char('q') | KeyCode::Char('Q') => {
                app.close_queue_manager();
                InputAction::Redraw
            }
            _ => InputAction::None,
        }
    } else {
        match key.code {
            KeyCode::Esc | KeyCode::Char('q') | KeyCode::Char('Q') => {
                app.close_queue_manager();
                InputAction::Redraw
            }
            KeyCode::Up => {
                if app.queue_manager.selected_index > 0 {
                    app.queue_manager.selected_index -= 1;
                }
                InputAction::Redraw
            }
            KeyCode::Down => {
                if app.queue_manager.selected_index + 1 < app.prompt_queue.len() {
                    app.queue_manager.selected_index += 1;
                }
                InputAction::Redraw
            }
            KeyCode::Char('u') | KeyCode::Char('k') => {
                let selected = app.queue_manager.selected_index;
                if selected > 0 {
                    app.prompt_queue.swap(selected - 1, selected);
                    app.queue_manager.selected_index -= 1;
                    app.set_status("Moved queued prompt up");
                }
                InputAction::Redraw
            }
            KeyCode::Char('j') => {
                let selected = app.queue_manager.selected_index;
                if selected + 1 < app.prompt_queue.len() {
                    app.prompt_queue.swap(selected, selected + 1);
                    app.queue_manager.selected_index += 1;
                    app.set_status("Moved queued prompt down");
                }
                InputAction::Redraw
            }
            KeyCode::Char('d') | KeyCode::Delete | KeyCode::Backspace => {
                let selected = app.queue_manager.selected_index;
                if let Some(prompt) = app.prompt_queue.remove(selected) {
                    app.set_status(format!("Dropped queued {} prompt", prompt.source));
                }
                app.sync_queue_selection();
                InputAction::Redraw
            }
            KeyCode::Char('c') | KeyCode::Char('C') => {
                let count = app.prompt_queue.len();
                app.prompt_queue.clear();
                app.queue_paused = false;
                app.sync_queue_selection();
                app.set_status(format!("Cleared {count} queued prompt(s)"));
                InputAction::Redraw
            }
            KeyCode::Char('e') | KeyCode::Char('E') => {
                let selected = app.queue_manager.selected_index;
                if let Some(prompt) = app.prompt_queue.remove(selected) {
                    app.close_queue_manager();
                    app.input_buffer = prompt.backend;
                    app.input_cursor = app.input_buffer.len();
                    sync_text_input_state(app);
                    app.sync_queue_selection();
                    app.set_status("Loaded queued prompt into composer");
                }
                InputAction::Redraw
            }
            KeyCode::Enter | KeyCode::Char('s') | KeyCode::Char('S') => {
                if app.waiting {
                    app.set_status("Wait for the active request before sending queued prompts");
                    return InputAction::Redraw;
                }

                let selected = app.queue_manager.selected_index;
                if let Some(prompt) = app.prompt_queue.remove(selected) {
                    app.queue_paused = false;
                    app.sync_queue_selection();
                    app.close_queue_manager();
                    return InputAction::QueueSendSelected(prompt);
                }
                InputAction::None
            }
            _ => InputAction::None,
        }
    }
}

pub(super) fn handle_key_timeline(app: &mut App, key: KeyEvent) -> InputAction {
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

pub(super) fn handle_key_transcript_search(app: &mut App, key: KeyEvent) -> InputAction {
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

pub(super) fn handle_key_plan_review(app: &mut App, key: KeyEvent) -> InputAction {
    match key.code {
        KeyCode::Char('?') => open_plan_review_help(app),
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
