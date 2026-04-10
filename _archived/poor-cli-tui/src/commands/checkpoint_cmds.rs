use super::super::*;
use super::core::show_command_info_popup;

pub(super) fn handle_checkpoint_commands(
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
    if lowered == "/checkpoints" || lowered.starts_with("/checkpoints ") {
        let limit = raw
            .split_whitespace()
            .nth(1)
            .and_then(|n| n.parse::<u64>().ok())
            .unwrap_or(20);

        match rpc_list_checkpoints_blocking(rpc_cmd_tx, limit) {
            Ok(payload) => {
                let available = payload
                    .get("available")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                if !available {
                    show_command_info_popup(
                        app,
                        raw,
                        "Checkpoint system not available.".to_string(),
                    );
                    return Some(false);
                }

                let checkpoints = payload
                    .get("checkpoints")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if checkpoints.is_empty() {
                    show_command_info_popup(app, raw, "No checkpoints available.".to_string());
                    return Some(false);
                }

                let items: Vec<ListSelectorItem> = checkpoints.iter().map(|cp| {
                    let id = cp.get("checkpointId").and_then(|v| v.as_str()).unwrap_or("unknown");
                    let short_id = if id.len() > 12 { &id[..12] } else { id };
                    let created = cp.get("createdAt").and_then(|v| v.as_str()).unwrap_or("-");
                    let rel_time = format_relative_time(created);
                    let description = cp.get("description").and_then(|v| v.as_str()).unwrap_or("");
                    let file_count = cp.get("fileCount").and_then(|v| v.as_u64()).unwrap_or(0);
                    let desc_display = if description.is_empty() { "-".to_string() } else { description.to_string() };
                    ListSelectorItem {
                        label: format!("{short_id} \u{2502} {rel_time} \u{2502} {file_count} files \u{2502} {desc_display}"),
                        value: id.to_string(),
                    }
                }).collect();
                app.open_list_selector(ListSelectorState {
                    title: format!("Checkpoints ({})", items.len()),
                    items,
                    selected_idx: 0,
                    command_template: "/checkpoint-preview {}".to_string(),
                    action_hint_override: Some("enter preview \u{2502} c copy \u{2502} esc close".to_string()),
                });
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to list checkpoints: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered.starts_with("/checkpoint-preview ") {
        let cp_id = raw.split_once(' ').map(|x| x.1).unwrap_or("").trim();
        if cp_id.is_empty() {
            show_command_info_popup(app, raw, "Usage: /checkpoint-preview <id>".to_string());
            return Some(false);
        }
        match rpc_preview_checkpoint_blocking(rpc_cmd_tx, cp_id) {
            Ok(payload) => {
                let files = payload.get("files").and_then(|v| v.as_array()).cloned().unwrap_or_default();
                let mut lines = Vec::new();
                let mut modified = 0u64;
                let mut deleted = 0u64;
                let mut unchanged = 0u64;
                for f in &files {
                    let path = f.get("filePath").and_then(|v| v.as_str()).unwrap_or("?");
                    let status = f.get("status").and_then(|v| v.as_str()).unwrap_or("?");
                    let marker = match status {
                        "modified" => { modified += 1; "M" }
                        "deleted" => { deleted += 1; "D" }
                        "unchanged" => { unchanged += 1; "\u{00b7}" }
                        _ => "?"
                    };
                    lines.push(format!("  {marker} {path}"));
                }
                let summary = format!(
                    "**Restore preview** \u{2014} checkpoint `{}`\n\n{} modified, {} deleted, {} unchanged\n\n{}\n\nRun `/undo {}` to restore.",
                    cp_id, modified, deleted, unchanged, lines.join("\n"), cp_id
                );
                app.pending_restore_checkpoint_id = Some(cp_id.to_string());
                show_command_info_popup(app, raw, summary);
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Preview failed: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/checkpoint" || lowered.starts_with("/checkpoint ") || lowered == "/save" || lowered.starts_with("/save ") {
        let name_arg = raw.split_once(' ').map(|x| x.1).unwrap_or("").trim();
        let name_arg = name_arg.trim_matches('"').trim_matches('\'');
        let description = if name_arg.is_empty() {
            if lowered.starts_with("/save") { "Quick save".to_string() } else { "Manual checkpoint".to_string() }
        } else {
            name_arg.to_string()
        };
        let operation_type = "manual".to_string();
        match rpc_create_checkpoint_blocking(rpc_cmd_tx, &description, &operation_type) {
            Ok(payload) => {
                let checkpoint_id = payload
                    .get("checkpointId")
                    .and_then(|v| v.as_str())
                    .unwrap_or("unknown");
                let file_count = payload
                    .get("fileCount")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                show_command_info_popup(
                    app,
                    raw,
                    format!("Created checkpoint `{checkpoint_id}` with {file_count} file(s)."),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to create checkpoint: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered.starts_with("/rewind") || lowered == "/restore" || lowered.starts_with("/restore ") || lowered == "/undo" || lowered.starts_with("/undo ") {
        let checkpoint_id = raw.split_whitespace()
            .nth(1)
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .or_else(|| Some("last".to_string()));

        match rpc_restore_checkpoint_blocking(rpc_cmd_tx, checkpoint_id.as_deref()) {
            Ok(payload) => {
                let restored = payload
                    .get("restoredFiles")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                let checkpoint_id = payload
                    .get("checkpointId")
                    .and_then(|v| v.as_str())
                    .unwrap_or("unknown");
                show_command_info_popup(
                    app,
                    raw,
                    format!("Restored checkpoint `{checkpoint_id}` ({restored} file(s) restored)."),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to restore checkpoint: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/gc" {
        match rpc_gc_checkpoints_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                let deleted = payload.get("deleted").and_then(|v| v.as_u64()).unwrap_or(0);
                let freed = payload.get("freed_bytes").and_then(|v| v.as_u64()).unwrap_or(0);
                let msg = if deleted == 0 {
                    "No stale checkpoints. Storage is clean.".to_string()
                } else {
                    format!("Removed {} checkpoint(s), freed {}", deleted, format_bytes(freed))
                };
                show_command_info_popup(app, raw, msg);
            }
            Err(e) => app.push_message(ChatMessage::error(format!("GC failed: {e}"))),
        }
        return Some(false);
    }

    None
}
