//! Action parsing helpers shared by runtime and remote control paths.

use serde_json::Value;

use wok_app::keybindings::Action;

/// Normalize remote action names from mixed naming styles to snake_case.
pub(crate) fn normalize_remote_action_name(action_name: &str) -> String {
    let normalized = action_name.trim().replace(['-', ' '], "_");
    if normalized.contains('_') {
        return normalized.to_ascii_lowercase();
    }

    let mut snake = String::new();
    for (index, ch) in normalized.chars().enumerate() {
        if ch.is_ascii_uppercase() {
            if index > 0 {
                snake.push('_');
            }
            snake.push(ch.to_ascii_lowercase());
        } else {
            snake.push(ch.to_ascii_lowercase());
        }
    }
    snake
}

/// Parse remote action requests, optionally using explicit JSON-RPC params.
pub(crate) fn parse_remote_action_with_params(
    action_name: &str,
    params: Option<&Value>,
) -> Option<Action> {
    if let Some(action) = parse_lua_action(action_name) {
        return Some(action);
    }

    match action_name {
        "save_session" => {
            let name = params.and_then(jsonrpc_string_like_value)?;
            Some(Action::SaveSession(name))
        }
        "load_session" => {
            let name = params.and_then(jsonrpc_string_like_value)?;
            Some(Action::LoadSession(name))
        }
        "switch_to_tab" => {
            let index = params.and_then(jsonrpc_tab_index_value)?;
            Some(Action::SwitchToTab(index))
        }
        _ => None,
    }
}

/// Parse one Lua action string into a runtime action.
pub(crate) fn parse_lua_action(action: &str) -> Option<Action> {
    if let Some(name) = action.strip_prefix("save_session:") {
        return (!name.trim().is_empty()).then(|| Action::SaveSession(name.trim().to_string()));
    }
    if let Some(name) = action.strip_prefix("load_session:") {
        return (!name.trim().is_empty()).then(|| Action::LoadSession(name.trim().to_string()));
    }
    if let Some(rest) = action.strip_prefix("switch_to_tab:") {
        let n: u8 = rest.trim().parse().ok()?;
        return (1..=9).contains(&n).then_some(Action::SwitchToTab(n));
    }
    if let Some(rest) = action.strip_prefix("workspace_switch:") {
        let n: u8 = rest.trim().parse().ok()?;
        return (1..=9).contains(&n).then_some(Action::WorkspaceSwitch(n));
    }

    match action {
        "new_tab" => Some(Action::NewTab),
        "close_tab" => Some(Action::CloseTab),
        "next_tab" => Some(Action::NextTab),
        "prev_tab" => Some(Action::PrevTab),
        "workspace_new" | "new_workspace" => Some(Action::WorkspaceNew),
        "workspace_next" | "next_workspace" => Some(Action::WorkspaceNext),
        "workspace_prev" | "prev_workspace" | "workspace_previous" => Some(Action::WorkspacePrev),
        "surface_new" | "new_surface" => Some(Action::SurfaceNew),
        "surface_next" | "next_surface" => Some(Action::SurfaceNext),
        "surface_prev" | "prev_surface" | "surface_previous" => Some(Action::SurfacePrev),
        "surface_close" | "close_surface" => Some(Action::SurfaceClose),
        "split_vertical" => Some(Action::SplitVertical),
        "split_horizontal" => Some(Action::SplitHorizontal),
        "close_split" | "close_pane" => Some(Action::CloseSplit),
        "focus_left" => Some(Action::FocusLeft),
        "focus_right" => Some(Action::FocusRight),
        "focus_up" => Some(Action::FocusUp),
        "focus_down" => Some(Action::FocusDown),
        "focus_prev_pane" | "prev_pane" => Some(Action::FocusPrevPane),
        "focus_next_pane" | "next_pane" => Some(Action::FocusNextPane),
        "search_global" | "toggle_search" | "search" => Some(Action::SearchGlobal),
        "enter_vi_mode" | "vi_mode" => Some(Action::EnterViMode),
        "command_palette" | "palette" => Some(Action::CommandPalette),
        "command_search" | "history_search" => Some(Action::CommandSearch),
        "keybinding_editor" | "edit_keybindings" | "rebind_keys" => Some(Action::KeybindingEditor),
        "quick_select" => Some(Action::QuickSelect),
        "quick_select_block" => Some(Action::QuickSelectBlock),
        "toggle_broadcast" | "broadcast_toggle" => Some(Action::ToggleBroadcast),
        "toggle_typewriter_effect" | "typewriter_toggle" | "typewriter_effect" => {
            Some(Action::ToggleTypewriterEffect)
        }
        "cycle_visual_effect" | "visual_effect_cycle" | "next_visual_effect" => {
            Some(Action::CycleVisualEffect)
        }
        "close_media_preview" | "media_preview_close" | "close_preview" => {
            Some(Action::CloseMediaPreview)
        }
        "toggle_media_preview_playback"
        | "media_play_pause"
        | "media_pause"
        | "preview_play_pause" => Some(Action::ToggleMediaPreviewPlayback),
        "seek_media_preview_backward" | "media_seek_backward" | "media_back" => {
            Some(Action::SeekMediaPreviewBackward)
        }
        "seek_media_preview_forward" | "media_seek_forward" | "media_forward" => {
            Some(Action::SeekMediaPreviewForward)
        }
        "slow_media_preview_playback" | "media_slower" => Some(Action::SlowMediaPreviewPlayback),
        "fast_media_preview_playback" | "media_faster" => Some(Action::FastMediaPreviewPlayback),
        "step_media_preview_backward" | "media_step_backward" => {
            Some(Action::StepMediaPreviewBackward)
        }
        "step_media_preview_forward" | "media_step_forward" => {
            Some(Action::StepMediaPreviewForward)
        }
        "toggle_media_preview_mute" | "media_mute" => Some(Action::ToggleMediaPreviewMute),
        "preview_path_under_cursor" | "preview_file_under_cursor" | "preview_path" => {
            Some(Action::PreviewPathUnderCursor)
        }
        "open_path_under_cursor" | "open_file_under_cursor" | "open_path" => {
            Some(Action::OpenPathUnderCursor)
        }
        "copy_path_under_cursor" | "copy_file_path_under_cursor" | "copy_path" => {
            Some(Action::CopyPathUnderCursor)
        }
        "reveal_path_under_cursor" | "reveal_file_under_cursor" | "reveal_path" => {
            Some(Action::RevealPathUnderCursor)
        }
        "tail_path_under_cursor" | "tail_file_under_cursor" | "tail_path" => {
            Some(Action::TailPathUnderCursor)
        }
        "open_scratch_buffer" | "scratch_buffer" | "scratch" => Some(Action::OpenScratchBuffer),
        "open_scratch_palette" | "scratch_palette" | "scratch_picker" => {
            Some(Action::OpenScratchPalette)
        }
        "toggle_search_regex" | "search_regex_toggle" | "regex_search" => {
            Some(Action::ToggleSearchRegex)
        }
        "cycle_search_scope" | "search_scope_cycle" | "next_search_scope" => {
            Some(Action::CycleSearchScope)
        }
        "open_search_results" | "search_results" | "show_search_results" => {
            Some(Action::OpenSearchResults)
        }
        "save_current_search" | "save_search" => Some(Action::SaveCurrentSearch),
        "open_saved_searches" | "saved_searches" => Some(Action::OpenSavedSearches),
        "open_block_inspector" | "block_inspector" | "inspect_block" => {
            Some(Action::OpenBlockInspector)
        }
        "open_block_rerun_history" | "block_rerun_history" | "rerun_history" => {
            Some(Action::OpenBlockRerunHistory)
        }
        "insert_scratch_selection_into_input" | "insert_scratch" | "send_scratch_to_input" => {
            Some(Action::InsertScratchSelectionIntoInput)
        }
        "send_scratch_selection_to_pane" | "run_scratch" | "send_scratch" => {
            Some(Action::SendScratchSelectionToPane)
        }
        "open_workspace_browser" | "workspace_browser" | "workspace_picker" => {
            Some(Action::OpenWorkspaceBrowser)
        }
        "open_block_rerun_comparison" | "block_rerun_comparison" | "compare_reruns" => {
            Some(Action::OpenBlockRerunComparison)
        }
        "new_floating_pane" | "floating_new" => Some(Action::NewFloatingPane),
        "toggle_floating_pane" | "toggle_floating" | "floating_toggle" => {
            Some(Action::ToggleFloatingPane)
        }
        "close_floating_pane" | "floating_close" => Some(Action::CloseFloatingPane),
        "next_layout" | "layout_next" => Some(Action::NextLayout),
        "prev_layout" | "layout_prev" | "previous_layout" => Some(Action::PrevLayout),
        "block_prev" => Some(Action::BlockPrev),
        "block_next" => Some(Action::BlockNext),
        "block_copy" | "copy_block" => Some(Action::BlockCopy),
        "block_copy_command" | "copy_block_command" => Some(Action::BlockCopyCommand),
        "block_copy_output" | "copy_block_output" => Some(Action::BlockCopyOutput),
        "block_collapse" | "collapse_block" => Some(Action::BlockCollapse),
        "block_toggle_bookmark" | "toggle_block_bookmark" => Some(Action::BlockToggleBookmark),
        "block_prev_bookmark" => Some(Action::BlockPrevBookmark),
        "block_next_bookmark" => Some(Action::BlockNextBookmark),
        "block_prev_failed" | "prev_failed_block" | "failure_prev" => Some(Action::BlockPrevFailed),
        "block_next_failed" | "next_failed_block" | "failure_next" => Some(Action::BlockNextFailed),
        "block_find" | "block_search" | "search_in_block" | "find_in_block" => {
            Some(Action::BlockFind)
        }
        "block_filter" | "filter_block" => Some(Action::BlockFilter),
        "block_diff" | "diff_block" | "block_compare" => Some(Action::BlockDiff),
        "block_rerun" | "rerun_block" => Some(Action::BlockRerun),
        "block_rerun_in_split" | "rerun_block_split" | "block_rerun_split" => {
            Some(Action::BlockRerunInSplit)
        }
        "block_save_workflow" | "save_block_workflow" | "block_workflow_save" => {
            Some(Action::BlockSaveWorkflow)
        }
        "block_export_markdown" | "export_block_markdown" | "block_export_md" => {
            Some(Action::BlockExportMarkdown)
        }
        "block_export_json" | "export_block_json" | "block_export_js" => {
            Some(Action::BlockExportJson)
        }
        "block_context_menu" | "block_actions" => Some(Action::BlockContextMenu),
        "block_scroll_top" | "block_top" => Some(Action::BlockScrollTop),
        "block_scroll_bottom" | "block_bottom" => Some(Action::BlockScrollBottom),
        "toggle_failure_trends_panel" | "failure_trends_panel" | "failure_trends" => {
            Some(Action::ToggleFailureTrendsPanel)
        }
        "toggle_workspace_insights_panel" | "workspace_insights_panel" | "workspace_insights" => {
            Some(Action::ToggleWorkspaceInsightsPanel)
        }
        "toggle_block_foot_strip" | "block_foot_strip" | "block_footer" => {
            Some(Action::ToggleBlockFootStrip)
        }
        "git_changes" | "git_status" | "changed_files" => Some(Action::GitChanges),
        "git_worktrees" | "git_worktree" | "worktree_switcher" => Some(Action::GitWorktrees),
        "zoom_in" => Some(Action::ZoomIn),
        "zoom_out" => Some(Action::ZoomOut),
        "zoom_reset" => Some(Action::ZoomReset),
        "open_settings" | "settings" | "open_config" | "config" => Some(Action::OpenSettings),
        "reset_settings" | "settings_reset" | "reset_config" => Some(Action::ResetSettings),
        "notification_popover" | "notifications" => Some(Action::NotificationPopover),
        "clear_screen" => Some(Action::ClearScreen),
        "send_eof" => Some(Action::SendEof),
        _ => None,
    }
}

fn jsonrpc_string_like_value(value: &Value) -> Option<String> {
    if let Some(text) = value.as_str() {
        return Some(text.to_string());
    }
    if let Some(items) = value.as_array() {
        return items.first().and_then(Value::as_str).map(str::to_string);
    }
    value
        .as_object()
        .and_then(|items| items.get("name"))
        .and_then(Value::as_str)
        .map(str::to_string)
}

fn jsonrpc_tab_index_value(value: &Value) -> Option<u8> {
    if let Some(index) = value.as_u64().and_then(|index| u8::try_from(index).ok()) {
        return (index > 0).then_some(index);
    }

    if let Some(items) = value.as_array() {
        if let Some(index) = items
            .first()
            .and_then(Value::as_u64)
            .and_then(|index| u8::try_from(index).ok())
        {
            return (index > 0).then_some(index);
        }
    }

    value
        .as_object()
        .and_then(|items| items.get("index"))
        .and_then(Value::as_u64)
        .and_then(|index| u8::try_from(index).ok())
        .filter(|index| *index > 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn test_normalize_remote_action_name_handles_camel_and_snake() {
        assert_eq!(
            normalize_remote_action_name("SplitVertical"),
            "split_vertical"
        );
        assert_eq!(
            normalize_remote_action_name("split_vertical"),
            "split_vertical"
        );
        assert_eq!(
            normalize_remote_action_name("Split Vertical"),
            "split_vertical"
        );
    }

    #[test]
    fn test_parse_remote_action_with_params_supports_named_forms() {
        assert_eq!(
            parse_remote_action_with_params("save_session", Some(&json!("demo"))),
            Some(Action::SaveSession("demo".to_string()))
        );
        assert_eq!(
            parse_remote_action_with_params("load_session", Some(&json!({"name": "nightly"}))),
            Some(Action::LoadSession("nightly".to_string()))
        );
        assert_eq!(
            parse_remote_action_with_params("switch_to_tab", Some(&json!({"index": 3}))),
            Some(Action::SwitchToTab(3))
        );
    }

    #[test]
    fn test_parse_lua_action_supports_block_diff_aliases() {
        assert_eq!(parse_lua_action("block_diff"), Some(Action::BlockDiff));
        assert_eq!(parse_lua_action("diff_block"), Some(Action::BlockDiff));
        assert_eq!(
            parse_lua_action("block_prev_failed"),
            Some(Action::BlockPrevFailed)
        );
        assert_eq!(
            parse_lua_action("next_failed_block"),
            Some(Action::BlockNextFailed)
        );
        assert_eq!(
            parse_lua_action("rerun_block_split"),
            Some(Action::BlockRerunInSplit)
        );
        assert_eq!(
            parse_lua_action("save_block_workflow"),
            Some(Action::BlockSaveWorkflow)
        );
        assert_eq!(
            parse_lua_action("export_block_markdown"),
            Some(Action::BlockExportMarkdown)
        );
        assert_eq!(
            parse_lua_action("block_export_json"),
            Some(Action::BlockExportJson)
        );
        assert_eq!(
            parse_lua_action("failure_trends"),
            Some(Action::ToggleFailureTrendsPanel)
        );
        assert_eq!(
            parse_lua_action("workspace_insights"),
            Some(Action::ToggleWorkspaceInsightsPanel)
        );
        assert_eq!(parse_lua_action("git_changes"), Some(Action::GitChanges));
        assert_eq!(parse_lua_action("git_status"), Some(Action::GitChanges));
        assert_eq!(
            parse_lua_action("git_worktrees"),
            Some(Action::GitWorktrees)
        );
    }
}
