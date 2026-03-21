use super::super::*;
use super::core::show_command_info_popup;

fn open_onboarding_at(app: &mut App, step: usize) {
    app.open_onboarding(step);
}

pub(super) fn handle_session_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    _launch: &BackendLaunchContext,
    _cancel_token: &Arc<AtomicBool>,
    _watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered == "/quit" || lowered == "/exit" {
        return Some(true);
    }

    if lowered == "/help" {
        show_command_info_popup(app, raw, input::help_markdown().to_string());
        return Some(false);
    }

    if lowered == "/onboarding" || lowered.starts_with("/onboarding ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("")
            .trim()
            .to_ascii_lowercase();
        let total_steps = onboarding_step_count();

        if total_steps == 0 {
            show_command_info_popup(app, raw, "Onboarding is currently unavailable.".to_string());
            return Some(false);
        }

        if subcommand.is_empty() {
            let step = if app.onboarding_active { app.onboarding_step } else { 0 };
            open_onboarding_at(app, step);
            return Some(false);
        }

        if subcommand == "start" || subcommand == "begin" || subcommand == "restart" {
            open_onboarding_at(app, 0);
            return Some(false);
        }

        if subcommand == "help" {
            show_command_info_popup(app, raw, onboarding_usage_text().to_string());
            return Some(false);
        }

        if subcommand == "exit" || subcommand == "done" || subcommand == "quit" {
            app.close_onboarding();
            app.set_status("Onboarding ended. Run /onboarding anytime to restart.");
            return Some(false);
        }

        if subcommand == "show" || subcommand == "repeat" || subcommand == "resume" {
            let step = if app.onboarding_active { app.onboarding_step } else { 0 };
            open_onboarding_at(app, step);
            return Some(false);
        }

        if subcommand == "next" {
            let step = if app.onboarding_active { (app.onboarding_step + 1).min(total_steps.saturating_sub(1)) } else { 0 };
            open_onboarding_at(app, step);
            return Some(false);
        }

        if subcommand == "prev" || subcommand == "previous" || subcommand == "back" {
            let step = if app.onboarding_active { app.onboarding_step.saturating_sub(1) } else { 0 };
            open_onboarding_at(app, step);
            return Some(false);
        }

        if let Ok(step_number) = subcommand.parse::<usize>() {
            if step_number == 0 || step_number > total_steps {
                show_command_info_popup(app, raw, format!("Step must be between 1 and {total_steps}.\n{}", onboarding_usage_text()));
                return Some(false);
            }
            open_onboarding_at(app, step_number - 1);
            return Some(false);
        }

        show_command_info_popup(app, raw, onboarding_usage_text().to_string());
        return Some(false);
    }

    if lowered == "/queue" || lowered.starts_with("/queue ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let sub = args.get(1).copied().unwrap_or("");
        if sub.is_empty() {
            let items = vec![
                ListSelectorItem { label: "list: Open queue manager".into(), value: "list".into() },
                ListSelectorItem { label: "add: Add prompt to queue".into(), value: "add".into() },
                ListSelectorItem { label: "clear: Clear all queued prompts".into(), value: "clear".into() },
                ListSelectorItem { label: "drop: Drop last queued prompt".into(), value: "drop".into() },
            ];
            app.open_list_selector(ListSelectorState {
                title: "Queue".into(), items, selected_idx: 0,
                command_template: "/queue {}".to_string(),
                action_hint_override: None,
            });
            return Some(false);
        }
        match sub {
            "add" | "a" => {
                if let Some(text) = args.get(2) {
                    let text = text.trim();
                    if text.is_empty() {
                        app.set_status("Usage: /queue add <prompt text>");
                    } else {
                        app.prompt_queue
                            .push_back(poor_cli_tui::app::QueuedPrompt::user(text));
                        app.sync_queue_selection();
                        app.set_status(format!("Queued ({} total)", app.prompt_queue.len()));
                    }
                } else {
                    app.set_status("Usage: /queue add <prompt text>");
                }
            }
            "list" | "ls" | "l" => {
                app.open_queue_manager();
            }
            "clear" | "c" => {
                let count = app.prompt_queue.len();
                app.prompt_queue.clear();
                app.queue_paused = false;
                app.sync_queue_selection();
                app.set_status(format!("Cleared {count} queued prompt(s)"));
            }
            "drop" | "d" => {
                if let Some(idx_str) = args.get(2) {
                    if let Ok(idx) = idx_str.trim().parse::<usize>() {
                        if idx >= 1 && idx <= app.prompt_queue.len() {
                            app.prompt_queue.remove(idx - 1);
                            app.sync_queue_selection();
                            app.set_status(format!(
                                "Dropped item {idx} ({} remaining)",
                                app.prompt_queue.len()
                            ));
                        } else {
                            app.set_status(format!("Invalid index (1-{})", app.prompt_queue.len()));
                        }
                    } else {
                        app.set_status("Usage: /queue drop <number>");
                    }
                } else if !app.prompt_queue.is_empty() {
                    app.prompt_queue.pop_back();
                    app.sync_queue_selection();
                    app.set_status(format!(
                        "Dropped last ({} remaining)",
                        app.prompt_queue.len()
                    ));
                } else {
                    app.set_status("Queue is empty");
                }
            }
            _ => {
                show_command_info_popup(
                    app,
                    raw,
                    "**Queue Commands**\n\n\
                    /queue              Open queue manager modal\n\
                    /queue add <text>   Add prompt to queue\n\
                    /queue list         Open queue manager modal\n\
                    /queue clear        Clear all queued prompts\n\
                    /queue drop [N]     Drop item N (or last)",
                );
            }
        }
        return Some(false);
    }

    if lowered == "/compact" {
        let items = vec![
            ListSelectorItem { label: "compact: summarize conversation in-place".into(), value: "compact".into() },
            ListSelectorItem { label: "compress: strip tool calls, keep text only".into(), value: "compress".into() },
            ListSelectorItem { label: "handoff: new session with context summary".into(), value: "handoff".into() },
        ];
        app.open_list_selector(ListSelectorState {
            title: "Compact Strategy".into(), items, selected_idx: 0,
            command_template: "/compact {}".to_string(),
            action_hint_override: None,
        });
        return Some(false);
    }

    if lowered.starts_with("/compact ") {
        let arg = raw.split_whitespace().nth(1).unwrap_or("compact");
        let strategy = match arg { "compress" => "compress", "handoff" => "handoff", _ => "compact" }.to_string();
        app.set_status(format!("Applying context strategy: {strategy}..."));
        let rpc = rpc_cmd_tx.clone();
        let tx_clone = tx.clone();
        thread::spawn(move || {
            let (reply_tx, reply_rx) = mpsc::sync_channel(1);
            let _ = rpc.send(RpcCommand::CompactContext { strategy: strategy.clone(), reply: reply_tx });
            match reply_rx.recv_timeout(Duration::from_secs(60)) {
                Ok(Ok(val)) => {
                    let summary = val.get("summary").and_then(|v| v.as_str()).unwrap_or("done");
                    let before = val.get("messages_before").and_then(|v| v.as_u64()).unwrap_or(0);
                    let after = val.get("messages_after").and_then(|v| v.as_u64()).unwrap_or(0);
                    let _ = tx_clone.send(ServerMsg::SystemMessage {
                        content: format!("**Context {strategy}** applied: {before} -> {after} messages\n\n{summary}"),
                    });
                }
                Ok(Err(e)) => { let _ = tx_clone.send(ServerMsg::SystemMessage { content: format!("Compact failed: {e}") }); }
                Err(_) => { let _ = tx_clone.send(ServerMsg::SystemMessage { content: "Compact timed out".into() }); }
            }
        });
        return Some(false);
    }

    if lowered == "/clear" {
        app.messages.clear();
        app.add_welcome();
        app.last_user_message = None;
        app.onboarding_active = false;
        app.onboarding_step = 0;
        app.join_wizard_active = false;
        app.join_wizard_step = 0;
        app.join_wizard_input.clear();
        app.join_wizard_error.clear();
        if qa_watch_state.is_running() {
            qa_watch_state.stop();
            app.qa_mode_enabled = false;
            app.qa_command.clear();
        }
        match rpc_clear_history_blocking(rpc_cmd_tx) {
            Ok(()) => app.set_status("Conversation history cleared"),
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Local history cleared, backend clear failed: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/clear-output" {
        app.messages.clear();
        app.add_welcome();
        app.set_status("Output cleared");
        return Some(false);
    }

    if lowered == "/new-session" {
        app.messages.clear();
        app.add_welcome();
        app.last_user_message = None;
        app.onboarding_active = false;
        app.onboarding_step = 0;
        app.join_wizard_active = false;
        app.join_wizard_step = 0;
        app.join_wizard_input.clear();
        app.join_wizard_error.clear();
        if qa_watch_state.is_running() {
            qa_watch_state.stop();
            app.qa_mode_enabled = false;
            app.qa_command.clear();
        }
        match rpc_clear_history_blocking(rpc_cmd_tx) {
            Ok(()) => app.set_status("Started new session"),
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Started local session, backend reset failed: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/retry" {
        if let Some(last) = app.last_user_message.clone() {
            send_chat_request(
                app,
                tx,
                rpc_cmd_tx,
                _cancel_token,
                last.clone(),
                format!("/retry {last}"),
                _launch.session_log.as_ref(),
            );
        } else {
            show_command_info_popup(app, raw, "No previous request to retry.".to_string());
        }
        return Some(false);
    }

    if lowered == "/edit-last" {
        if let Some(last) = app.last_user_message.clone() {
            app.input_buffer = last;
            app.input_cursor = app.input_buffer.len();
            app.mode = poor_cli_tui::app::AppMode::Normal;
            app.set_status("Loaded last message into input");
        } else {
            show_command_info_popup(app, raw, "No previous request to edit.".to_string());
        }
        return Some(false);
    }

    if lowered.starts_with("/history") {
        let count = raw
            .split_whitespace()
            .nth(1)
            .and_then(|n| n.parse::<usize>().ok())
            .unwrap_or(10);

        match rpc_list_history_blocking(rpc_cmd_tx, count as u64) {
            Ok(payload) => {
                let messages = payload
                    .get("messages")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if messages.is_empty() {
                    show_command_info_popup(app, raw, "No messages in this session.".to_string());
                    return Some(false);
                }

                let mut lines = Vec::new();
                for msg in messages {
                    let role = msg
                        .get("role")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let role_name = if role == "user" { "You" } else { "Assistant" };
                    let timestamp = msg.get("timestamp").and_then(|v| v.as_str()).unwrap_or("-");
                    let content = msg.get("content").and_then(|v| v.as_str()).unwrap_or("");
                    lines.push(format!(
                        "**{role_name}** ({timestamp})\n{}",
                        truncate_line(content, 260)
                    ));
                }

                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "**History (last {} messages):**\n\n{}",
                        lines.len(),
                        lines.join("\n\n")
                    ),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to load session history: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/sessions" {
        match rpc_list_sessions_blocking(rpc_cmd_tx, 10) {
            Ok(payload) => {
                let sessions = payload
                    .get("sessions")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if sessions.is_empty() {
                    show_command_info_popup(app, raw, "No previous sessions found.".to_string());
                    return Some(false);
                }

                let items: Vec<ListSelectorItem> = sessions.iter().map(|session| {
                    let session_id = session.get("sessionId").and_then(|v| v.as_str()).unwrap_or("unknown");
                    let started = session.get("startedAt").and_then(|v| v.as_str()).unwrap_or("-");
                    let message_count = session.get("messageCount").and_then(|v| v.as_u64()).unwrap_or(0);
                    let active = session.get("isActive").and_then(|v| v.as_bool()).unwrap_or(false);
                    let marker = if active { " (active)" } else { "" };
                    ListSelectorItem {
                        label: format!("{session_id}{marker} • {started} • {message_count} message(s)"),
                        value: session_id.to_string(),
                    }
                }).collect();
                app.open_list_selector(ListSelectorState {
                    title: "Recent Sessions".to_string(),
                    items,
                    selected_idx: 0,
                    command_template: "/restore-session {}".to_string(),
                    action_hint_override: None,
                });
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to list sessions: {e}"))),
        }
        return Some(false);
    }

    if lowered.starts_with("/search") {
        let term = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if term.is_empty() {
            show_command_info_popup(app, raw, "Usage: /search <term>".to_string());
            return Some(false);
        }

        match rpc_search_history_blocking(rpc_cmd_tx, term) {
            Ok(payload) => {
                let total_matches = payload
                    .get("totalMatches")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                let matches = payload
                    .get("matches")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if matches.is_empty() {
                    show_command_info_popup(app, raw, format!("No matches for: {term}"));
                    return Some(false);
                }

                let mut lines = Vec::new();
                for msg in matches {
                    let role = msg
                        .get("role")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let role_name = if role == "user" { "You" } else { "Assistant" };
                    let timestamp = msg.get("timestamp").and_then(|v| v.as_str()).unwrap_or("-");
                    let content = msg.get("content").and_then(|v| v.as_str()).unwrap_or("");
                    lines.push(format!(
                        "- **{role_name}** ({timestamp}): {}",
                        truncate_line(content, 180)
                    ));
                }

                let mut response = format!(
                    "**Search results for '{term}' ({total_matches} matches):**\n\n{}",
                    lines.join("\n")
                );
                if total_matches > lines.len() as u64 {
                    response.push_str(&format!(
                        "\n\nShowing {} of {total_matches} matches.",
                        lines.len()
                    ));
                }
                show_command_info_popup(app, raw, response);
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to search session history: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/search" {
        app.open_transcript_search();
        return Some(false);
    }

    if lowered == "/timeline" {
        app.open_timeline();
        return Some(false);
    }

    if lowered == "/mascot" {
        app.mascot_enabled = !app.mascot_enabled;
        app.set_status(if app.mascot_enabled { "Penny enabled" } else { "Penny disabled" });
        return Some(false);
    }

    None
}
