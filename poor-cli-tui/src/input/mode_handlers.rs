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
            let moved = if app.provider.select_pane == ProviderSelectPane::Models {
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
            let moved = if app.provider.select_pane == ProviderSelectPane::Models {
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
            let idx = app.provider.select_idx;
            app.mode = AppMode::Normal;
            app.overlay_kind = None;
            InputAction::ProviderSelected(idx)
        }
        KeyCode::Esc => {
            app.mode = AppMode::Normal;
            app.overlay_kind = None;
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
    if app.onboarding_active {
        match key.code {
            KeyCode::Right | KeyCode::Tab => {
                if app.onboarding_total_steps > 0 && app.onboarding_step + 1 < app.onboarding_total_steps {
                    app.onboarding_step += 1;
                    // content update happens via Submit which re-enters the handler
                    app.close_info_popup();
                    return InputAction::Submit(format!("/onboarding {}", app.onboarding_step + 1));
                }
                return InputAction::Redraw;
            }
            KeyCode::Left | KeyCode::BackTab => {
                if app.onboarding_step > 0 {
                    app.onboarding_step -= 1;
                    app.close_info_popup();
                    return InputAction::Submit(format!("/onboarding {}", app.onboarding_step + 1));
                }
                return InputAction::Redraw;
            }
            KeyCode::Enter => {
                let try_now = if app.onboarding_try_now.is_empty() { "/help".to_string() } else { app.onboarding_try_now.clone() };
                app.close_info_popup();
                return InputAction::Submit(try_now);
            }
            KeyCode::Esc | KeyCode::Char('q') | KeyCode::Char('Q') => {
                app.onboarding_active = false;
                app.onboarding_step = 0;
                app.close_info_popup();
                return InputAction::Redraw;
            }
            _ => {} // fall through to normal info popup scrolling
        }
    }
    let items = extract_copyable_items(&app.info_popup_content);
    let item_count = items.len();
    match key.code {
        KeyCode::Esc | KeyCode::Char('q') | KeyCode::Char('Q') => {
            app.close_info_popup();
            InputAction::Redraw
        }
        KeyCode::Enter => {
            if let Some(item) = items.get(app.info_popup_selected_idx) {
                if item.starts_with('/') {
                    app.close_info_popup();
                    InputAction::Submit(item.clone())
                } else {
                    InputAction::CopyToClipboard(item.clone())
                }
            } else {
                app.close_info_popup();
                InputAction::Redraw
            }
        }
        KeyCode::Char('c') | KeyCode::Char('C') => {
            if !items.is_empty() {
                InputAction::CopyToClipboard(items.join("\n"))
            } else {
                InputAction::CopyToClipboard(app.info_popup_content.clone())
            }
        }
        KeyCode::Up => {
            if item_count > 0 {
                app.move_info_popup_selection(false, item_count);
            } else {
                app.scroll_info_popup_up(1);
            }
            InputAction::Redraw
        }
        KeyCode::Down => {
            if item_count > 0 {
                app.move_info_popup_selection(true, item_count);
            } else {
                app.scroll_info_popup_down(1);
            }
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

pub(super) fn handle_key_list_selector(app: &mut App, key: KeyEvent) -> InputAction {
    let Some(state) = app.list_selector.as_mut() else {
        return InputAction::None;
    };
    let count = state.items.len();
    match key.code {
        KeyCode::Esc | KeyCode::Char('q') | KeyCode::Char('Q') => {
            app.close_list_selector();
            InputAction::Redraw
        }
        KeyCode::Up | KeyCode::Char('k') => {
            if count > 0 {
                state.selected_idx = state.selected_idx.saturating_sub(1);
            }
            InputAction::Redraw
        }
        KeyCode::Down | KeyCode::Char('j') => {
            if count > 0 && state.selected_idx + 1 < count {
                state.selected_idx += 1;
            }
            InputAction::Redraw
        }
        KeyCode::Enter => {
            if let Some(item) = state.items.get(state.selected_idx) {
                let cmd = state.command_template.replace("{}", &item.value);
                app.close_list_selector();
                InputAction::Submit(cmd)
            } else {
                app.close_list_selector();
                InputAction::Redraw
            }
        }
        KeyCode::Char('c') | KeyCode::Char('C') => {
            if let Some(item) = state.items.get(state.selected_idx) {
                InputAction::CopyToClipboard(item.value.clone())
            } else {
                InputAction::None
            }
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
        app.overlay_kind = None;
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
            app.overlay_kind = None;
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
                    app.overlay_kind = None;
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

pub(super) fn handle_key_inline_approval(app: &mut App, key: KeyEvent) -> InputAction {
    // plan review gate is active
    let is_plan_review = app.plan.is_execution_gate && !app.plan.steps.is_empty();
    // mutation review has expanded diff
    let has_mutation_review = app.mutation_review.is_some();
    if is_plan_review && app.pending_approval.is_none() {
        return match key.code {
            KeyCode::Char('?') => open_plan_review_help(app),
            KeyCode::Char('y') | KeyCode::Char('Y') | KeyCode::Enter => {
                app.mode = AppMode::Normal;
                if app.plan.review_read_only {
                    InputAction::Redraw
                } else {
                    InputAction::PlanApproved
                }
            }
            KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc | KeyCode::Char('q') => {
                app.mode = AppMode::Normal;
                if app.plan.review_read_only {
                    InputAction::Redraw
                } else {
                    InputAction::PlanCancelled
                }
            }
            _ => InputAction::None,
        };
    }
    // mutation review mode (expanded diff with hunk selection)
    if has_mutation_review {
        return handle_key_mutation_review(app, key);
    }
    match key.code {
        KeyCode::Char('y') | KeyCode::Char('Y') => {
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
        KeyCode::Char('d') | KeyCode::Char('D') => {
            if let Some(approval) = app.pending_approval.as_mut() {
                approval.diff_expanded = !approval.diff_expanded;
            }
            InputAction::Redraw
        }
        KeyCode::Char('?') => {
            open_permission_help(app);
            InputAction::Redraw
        }
        _ => InputAction::None,
    }
}
