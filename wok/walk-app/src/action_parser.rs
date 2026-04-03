//! Action parsing helpers shared by runtime and remote control paths.

use serde_json::Value;

use walk_app::keybindings::Action;

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

    match action {
        "new_tab" => Some(Action::NewTab),
        "close_tab" => Some(Action::CloseTab),
        "next_tab" => Some(Action::NextTab),
        "prev_tab" => Some(Action::PrevTab),
        "split_vertical" => Some(Action::SplitVertical),
        "split_horizontal" => Some(Action::SplitHorizontal),
        "close_split" | "close_pane" => Some(Action::CloseSplit),
        "focus_left" => Some(Action::FocusLeft),
        "focus_right" => Some(Action::FocusRight),
        "focus_up" => Some(Action::FocusUp),
        "focus_down" => Some(Action::FocusDown),
        "search_global" | "toggle_search" | "search" => Some(Action::SearchGlobal),
        "enter_vi_mode" | "vi_mode" => Some(Action::EnterViMode),
        "command_palette" | "palette" => Some(Action::CommandPalette),
        "command_search" | "history_search" => Some(Action::CommandSearch),
        "quick_select" => Some(Action::QuickSelect),
        "quick_select_block" => Some(Action::QuickSelectBlock),
        "toggle_broadcast" | "broadcast_toggle" => Some(Action::ToggleBroadcast),
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
        "block_find" | "block_search" | "search_in_block" | "find_in_block" => {
            Some(Action::BlockFind)
        }
        "block_filter" | "filter_block" => Some(Action::BlockFilter),
        "block_rerun" | "rerun_block" => Some(Action::BlockRerun),
        "zoom_in" => Some(Action::ZoomIn),
        "zoom_out" => Some(Action::ZoomOut),
        "zoom_reset" => Some(Action::ZoomReset),
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
}
