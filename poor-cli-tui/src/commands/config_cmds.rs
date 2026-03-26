use super::super::*;
use super::core::show_command_info_popup;

pub(super) fn handle_config_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    _tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    _launch: &BackendLaunchContext,
    _cancel_token: &Arc<AtomicBool>,
    _watch_state: &mut WatchState,
    _qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered == "/config" {
        match rpc_get_config_blocking(rpc_cmd_tx) {
            Ok(cfg) => {
                let config = format!(
                    "**Configuration:**\n\
Provider: {}\n\
Model: {}\n\
Theme: {}\n\
Streaming: {}\n\
Show Token Count: {}\n\
Markdown Rendering: {}\n\
Show Tool Calls: {}\n\
Verbose Logging: {}\n\
Plan Mode: {}\n\
Checkpointing: {}\n\
Permission Mode: {}\n\
Config File: {}\n\
Version: v{}",
                    cfg.get("provider")
                        .and_then(|v| v.as_str())
                        .unwrap_or(app.provider.name.as_str()),
                    cfg.get("model")
                        .and_then(|v| v.as_str())
                        .unwrap_or(app.provider.model.as_str()),
                    cfg.get("theme")
                        .and_then(|v| v.as_str())
                        .unwrap_or(app.theme_mode.as_str()),
                    if cfg
                        .get("streaming")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(true)
                    {
                        "enabled"
                    } else {
                        "disabled"
                    },
                    bool_label(
                        cfg.get("showTokenCount")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true),
                    ),
                    bool_label(
                        cfg.get("markdownRendering")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true),
                    ),
                    bool_label(
                        cfg.get("showToolCalls")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true),
                    ),
                    bool_label(
                        cfg.get("verboseLogging")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false),
                    ),
                    bool_label(
                        cfg.get("planMode")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true),
                    ),
                    bool_label(
                        cfg.get("checkpointing")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(true),
                    ),
                    cfg.get("permissionMode")
                        .and_then(|v| v.as_str())
                        .unwrap_or("prompt"),
                    cfg.get("configFile")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(unknown)"),
                    cfg.get("version")
                        .and_then(|v| v.as_str())
                        .unwrap_or(app.version.as_str())
                );
                show_command_info_popup(app, raw, config);
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to load config: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/settings" {
        match rpc_list_config_options_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                let options = payload
                    .get("options")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                let _config_file = payload
                    .get("configFile")
                    .and_then(|v| v.as_str())
                    .unwrap_or("(unknown)");

                if options.is_empty() {
                    show_command_info_popup(app, raw, "No editable settings found.".to_string());
                } else {
                    let items: Vec<ListSelectorItem> = options.iter().take(80).map(|opt| {
                        let key = opt.get("path").and_then(|v| v.as_str()).unwrap_or("unknown");
                        let typ = opt.get("type").and_then(|v| v.as_str()).unwrap_or("unknown");
                        let value = opt.get("value").cloned().unwrap_or(Value::Null);
                        let is_bool = opt.get("isBoolean").and_then(|v| v.as_bool()).unwrap_or(false);
                        let bool_hint = if is_bool { " (toggleable)" } else { "" };
                        ListSelectorItem {
                            label: format!("{key} [{typ}{bool_hint}] = {}", format_value_for_display(&value)),
                            value: key.to_string(),
                        }
                    }).collect();
                    app.open_list_selector(ListSelectorState {
                        title: format!("Settings ({})", options.len()),
                        items,
                        selected_idx: 0,
                        command_template: "/toggle {}".to_string(),
                        action_hint_override: None,
                    });
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to load settings: {e}"))),
        }
        return Some(false);
    }

    if lowered.starts_with("/toggle ") {
        let key = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if key.is_empty() {
            show_command_info_popup(app, raw, "Usage: /toggle <key>".to_string());
            return Some(false);
        }

        match rpc_toggle_config_blocking(rpc_cmd_tx, key) {
            Ok(result) => {
                let value = result.get("value").cloned().unwrap_or(Value::Null);
                show_command_info_popup(
                    app,
                    raw,
                    format!("Toggled `{key}` to `{}`", format_value_for_display(&value)),
                );
            }
            Err(e) => {
                app.push_message(ChatMessage::error(format!("Failed to toggle `{key}`: {e}")))
            }
        }
        return Some(false);
    }

    if lowered.starts_with("/set ") {
        let mut parts = raw.splitn(3, ' ');
        let _ = parts.next();
        let key = parts.next().unwrap_or("").trim();
        let raw_value = parts.next().unwrap_or("").trim();

        if key.is_empty() || raw_value.is_empty() {
            show_command_info_popup(app, raw, "Usage: /set <key> <value>".to_string());
            return Some(false);
        }

        let parsed_value = parse_value_literal(raw_value);
        match rpc_set_config_blocking(rpc_cmd_tx, key, parsed_value) {
            Ok(result) => {
                let value = result.get("value").cloned().unwrap_or(Value::Null);
                if key == "ui.theme" {
                    if let Some(theme_str) = value.as_str() {
                        app.theme_mode = ThemeMode::from_ui_theme(theme_str);
                    } else {
                        app.theme_mode = ThemeMode::from_ui_theme(raw_value);
                    }
                }
                show_command_info_popup(
                    app,
                    raw,
                    format!("Updated `{key}` = `{}`", format_value_for_display(&value)),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to set `{key}`: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/theme" {
        let themes = [("dark", "Dark theme"), ("light", "Light theme")];
        let items: Vec<ListSelectorItem> = themes.iter().map(|(name, desc)| {
            let active = if *name == app.theme_mode.as_str() { " (active)" } else { "" };
            ListSelectorItem { label: format!("{name}{active}: {desc}"), value: name.to_string() }
        }).collect();
        app.open_list_selector(ListSelectorState {
            title: "Theme".to_string(), items, selected_idx: 0,
            command_template: "/theme {}".to_string(),
            action_hint_override: None,
        });
        return Some(false);
    }

    if lowered.starts_with("/theme ") {
        let raw_mode = raw.split_whitespace().nth(1).unwrap_or("");
        let Some(theme_mode) = ThemeMode::from_user_input(raw_mode) else {
            app.push_message(ChatMessage::error(
                "Invalid theme mode. Use one of: dark, light.".to_string(),
            ));
            return Some(false);
        };

        match rpc_set_config_blocking(
            rpc_cmd_tx,
            "ui.theme",
            Value::String(theme_mode.as_str().to_string()),
        ) {
            Ok(result) => {
                let applied = result
                    .get("value")
                    .and_then(|v| v.as_str())
                    .unwrap_or(theme_mode.as_str());
                app.theme_mode = ThemeMode::from_ui_theme(applied);
                show_command_info_popup(
                    app,
                    raw,
                    format!("Theme set to **{}**.", app.theme_mode.as_str()),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to set theme: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/verbose" {
        match rpc_toggle_config_blocking(rpc_cmd_tx, "ui.verbose_logging") {
            Ok(result) => {
                let enabled = result
                    .get("value")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let message = if enabled {
                    "Verbose logging enabled (INFO/DEBUG messages will be shown)"
                } else {
                    "Verbose logging disabled (only WARNING/ERROR messages will be shown)"
                };
                show_command_info_popup(app, raw, message.to_string());
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to toggle verbose logging: {e}"
            ))),
        }
        return Some(false);
    }

    None
}
