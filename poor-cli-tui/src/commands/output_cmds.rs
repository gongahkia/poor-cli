use super::super::*;
use super::core::show_command_info_popup;

pub(super) fn handle_output_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    _watch_state: &mut WatchState,
    _qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered == "/export" || lowered.starts_with("/export ") {
        let export_format = raw
            .split_whitespace()
            .nth(1)
            .unwrap_or("")
            .to_lowercase();
        if export_format.is_empty() {
            let items = vec![
                ListSelectorItem { label: "json: JSON format".into(), value: "json".into() },
                ListSelectorItem { label: "md: Markdown format".into(), value: "md".into() },
                ListSelectorItem { label: "txt: Plain text format".into(), value: "txt".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "Export Format".into(), items, selected_idx: 0,
                command_template: "/export {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }
        if !matches!(export_format.as_str(), "json" | "md" | "txt" | "markdown") {
            show_command_info_popup(app, raw, "Usage: /export [json|md|txt]".to_string());
            return Some(false);
        }

        match rpc_export_conversation_blocking(rpc_cmd_tx, &export_format) {
            Ok(payload) => {
                let file_path = payload
                    .get("filePath")
                    .and_then(|v| v.as_str())
                    .unwrap_or("(unknown)");
                let format_value = payload
                    .get("format")
                    .and_then(|v| v.as_str())
                    .unwrap_or(export_format.as_str());
                let message_count = payload
                    .get("messageCount")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                let size_bytes = payload
                    .get("sizeBytes")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "Export complete.\n\nFile: `{file_path}`\nFormat: `{format_value}`\nMessages: {message_count}\nSize: {}",
                        format_bytes(size_bytes)
                    ),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to export conversation: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/copy" {
        if let Some(content) = last_assistant_message(app) {
            match copy_to_clipboard(&content) {
                Ok(()) => app.set_status(format!(
                    "Copied {} characters to clipboard",
                    content.chars().count()
                )),
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to copy response to clipboard: {e}"
                ))),
            }
        } else {
            show_command_info_popup(app, raw, "No assistant response to copy.".to_string());
        }
        return Some(false);
    }

    if lowered == "/cost" {
        let provider = app.provider.name.to_lowercase();
        let model = app.provider.model.to_lowercase();

        let (input_per_million, output_per_million) =
            if provider == "gemini" || provider == "ollama" {
                (0.0, 0.0)
            } else if provider == "openai" {
                if model.contains("gpt-4") {
                    (30.0, 60.0)
                } else {
                    (0.5, 1.5)
                }
            } else if provider == "anthropic" {
                (3.0, 15.0)
            } else {
                (30.0, 60.0)
            };

        let (in_tokens, out_tokens) =
            if app.tokens.cumulative_input_tokens > 0 || app.tokens.cumulative_output_tokens > 0 {
                (
                    app.tokens.cumulative_input_tokens as f64,
                    app.tokens.cumulative_output_tokens as f64,
                )
            } else {
                (
                    app.input_tokens_estimate as f64,
                    app.output_tokens_estimate as f64,
                )
            };
        let input_cost = (in_tokens / 1_000_000.0) * input_per_million;
        let output_cost = (out_tokens / 1_000_000.0) * output_per_million;
        let total = input_cost + output_cost;

        let real_label = if app.tokens.cumulative_input_tokens > 0 {
            ""
        } else {
            " (estimated)"
        };
        let text = format!(
            "**Session Usage Statistics:**\n\n\
Requests: {}\n\
Input: {} chars ({} tokens{real_label})\n\
Output: {} chars ({} tokens{real_label})\n\n\
**Estimated Cost:**\n\
Provider: {} ({})\n\
Input Cost: ${:.4}\n\
Output Cost: ${:.4}\n\
Total: **${:.4}**",
            app.session_requests,
            app.input_chars,
            in_tokens as u64,
            app.output_chars,
            out_tokens as u64,
            app.provider.name,
            app.provider.model,
            input_cost,
            output_cost,
            total
        );
        show_command_info_popup(app, raw, text);
        return Some(false);
    }

    if lowered.starts_with("/save-prompt ") {
        let mut parts = raw.splitn(3, ' ');
        let _ = parts.next();
        let name = parts.next().unwrap_or("").trim();
        let content = parts.next().unwrap_or("").trim();

        if name.is_empty() {
            show_command_info_popup(app, raw, "Usage: /save-prompt <name> [text]".to_string());
            return Some(false);
        }

        if content.is_empty() {
            app.pending_prompt_save_name = Some(name.to_string());
            show_command_info_popup(
                app,
                raw,
                format!(
                    "Enter prompt text and press Enter to save as **{name}**.\n\
Submitting any slash command will cancel capture."
                ),
            );
            return Some(false);
        }

        match save_prompt(app, name, content) {
            Ok(path) => app.set_status(format!("Saved prompt: {}", path.display())),
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return Some(false);
    }

    if lowered.starts_with("/use ") {
        let name = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if name.is_empty() {
            show_command_info_popup(app, raw, "Usage: /use <name>".to_string());
            return Some(false);
        }

        match load_prompt(app, name) {
            Ok(content) => {
                show_command_info_popup(app, raw, format!("Loaded prompt: {name}"));
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    content,
                    format!("/use {name}"),
                    launch.session_log.as_ref(),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return Some(false);
    }

    if lowered == "/prompts" {
        match list_prompts(app) {
            Ok(entries) if entries.is_empty() => {
                show_command_info_popup(app, raw, "No saved prompts.".to_string());
            }
            Ok(entries) => {
                let items: Vec<ListSelectorItem> = entries.iter().map(|(name, preview)| {
                    ListSelectorItem { label: format!("{name}: {preview}"), value: name.clone() }
                }).collect();
                app.open_list_selector(ListSelectorState {
                    title: format!("Saved Prompts ({})", items.len()),
                    items, selected_idx: 0,
                    command_template: "/use {}".to_string(),
                    action_hint_override: None,
                });
            }
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return Some(false);
    }

    if lowered.starts_with("/image ") {
        let image_path = raw.split_once(' ').map(|x| x.1).map(str::trim).unwrap_or("");
        if image_path.is_empty() {
            show_command_info_popup(app, raw, "Usage: /image <path>".to_string());
            return Some(false);
        }
        let path = Path::new(image_path);
        if !path.is_file() {
            app.push_message(ChatMessage::error(format!(
                "Image file not found: {image_path}"
            )));
            return Some(false);
        }

        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_lowercase())
            .unwrap_or_default();
        let allowed = ["png", "jpg", "jpeg", "gif", "webp", "bmp"];
        if !allowed.contains(&ext.as_str()) {
            app.push_message(ChatMessage::error(format!(
                "Unsupported image extension: .{ext}"
            )));
            return Some(false);
        }

        app.pending_images.push(image_path.to_string());
        app.set_status(format!(
            "Image queued: {image_path} (will be attached to next message)"
        ));
        return Some(false);
    }

    if lowered == "/economy" || lowered.starts_with("/economy ") {
        let arg = lowered.strip_prefix("/economy").unwrap_or("").trim();
        if arg.is_empty() {
            let presets = [("frugal", "minimize token usage"),
                ("balanced", "balance cost and quality"),
                ("quality", "maximize response quality")];
            let items: Vec<ListSelectorItem> = presets.iter().map(|(name, desc)| {
                ListSelectorItem { label: format!("{name}: {desc}"), value: name.to_string() }
            }).collect();
            app.open_list_selector(ListSelectorState {
                title: "Economy Preset".to_string(), items, selected_idx: 0,
                command_template: "/economy {}".to_string(),
                action_hint_override: None,
            });
        } else {
            match rpc_set_economy_preset_blocking(rpc_cmd_tx, arg) {
                Ok(payload) => {
                    let msg = serde_json::to_string_pretty(&payload).unwrap_or_else(|_| format!("{payload:?}"));
                    show_command_info_popup(app, raw, format!("**Economy preset set to `{arg}`:**\n```\n{msg}\n```"));
                }
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to set economy preset: {e}"))),
            }
        }
        return Some(false);
    }

    if lowered == "/savings" {
        match rpc_get_economy_savings_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                let msg = serde_json::to_string_pretty(&payload).unwrap_or_else(|_| format!("{payload:?}"));
                show_command_info_popup(app, raw, format!("**Economy Savings:**\n```\n{msg}\n```"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to get savings: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/save-session" {
        match rpc_save_session_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                let path = payload.get("path").and_then(|v| v.as_str()).unwrap_or("(unknown)");
                show_command_info_popup(app, raw, format!("Session saved to:\n{path}"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to save session: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/restore-session" || lowered.starts_with("/restore-session ") {
        let session_id = raw.split_whitespace().nth(1);
        match rpc_restore_session_blocking(rpc_cmd_tx, session_id) {
            Ok(payload) => {
                let restored = payload.get("restored").and_then(|v| v.as_bool()).unwrap_or(false);
                let restored_id = payload
                    .get("sessionId")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");
                let msg = if restored {
                    if restored_id.is_empty() {
                        "Session restored successfully.".to_string()
                    } else {
                        format!("Session restored successfully: `{restored_id}`")
                    }
                } else {
                    "No saved session found to restore.".to_string()
                };
                show_command_info_popup(app, raw, msg);
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to restore session: {e}"))),
        }
        return Some(false);
    }

    None
}
