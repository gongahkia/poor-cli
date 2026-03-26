use super::*;

mod collab;
mod context;
mod core;
mod provider;
mod tasks;

mod automation_cmds;
mod checkpoint_cmds;
mod collab_cmds;
mod config_cmds;
mod context_cmds;
mod output_cmds;
mod provider_cmds;
mod review_cmds;
mod session_cmds;
mod system_cmds;

use core::resolve_close_slash_command;

// ── Slash command handler ─────────────────────────────────────────────

pub(super) fn handle_slash_command(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
    cmd: &str,
) -> bool {
    let mut normalized = cmd.trim().to_string();
    if let Some((rewritten, typed, resolved)) = resolve_close_slash_command(&normalized) {
        app.set_status(format!("Assuming `{resolved}` for `{typed}`"));
        normalized = rewritten;
    }

    let raw = normalized.as_str();
    let lowered = raw.to_lowercase();

    if let Some(v) = session_cmds::handle_session_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = provider_cmds::handle_provider_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = config_cmds::handle_config_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = context_cmds::handle_context_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = checkpoint_cmds::handle_checkpoint_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = review_cmds::handle_review_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = automation_cmds::handle_automation_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = system_cmds::handle_system_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = output_cmds::handle_output_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }
    if let Some(v) = collab_cmds::handle_collab_commands(app, raw, &lowered, tx, rpc_cmd_tx, launch, cancel_token, watch_state, qa_watch_state) { return v; }

    app.push_message(ChatMessage::error(format!(
        "Unknown command: {raw}\nType /help to see available commands"
    )));
    false
}

// ── Watch mode helpers ───────────────────────────────────────────────
