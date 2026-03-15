use super::*;

pub(super) fn handle_server_message(
    app: &mut App,
    msg: ServerMsg,
    rpc_cmd_tx: &RefCell<mpsc::Sender<RpcCommand>>,
    remote_reconnect_state: &RefCell<(u32, Option<std::time::Instant>, bool)>,
    max_remote_reconnect_attempts: u32,
    session_log: Option<&SessionLogWriter>,
) -> Result<LoopControl, Box<dyn std::error::Error>> {
    match msg {
        ServerMsg::Initialized {
            provider,
            model,
            version,
            multiplayer_room,
            multiplayer_role,
            multiplayer_ui_role,
            multiplayer_mode,
            multiplayer_connection_id,
            multiplayer_display_name,
            multiplayer_approval_state,
        } => {
            let mut state = remote_reconnect_state.borrow_mut();
            if state.2 {
                app.push_message(ChatMessage::system(
                    "Multiplayer bridge reconnected successfully.".to_string(),
                ));
            }
            state.0 = 0;
            state.1 = None;
            state.2 = false;
            app.reconnect_message_idx = None;
            app.provider_name = provider;
            app.model_name = model;
            app.version = version;
            app.server_connected = true;
            app.is_local_provider = app.provider_name == "ollama";
            app.multiplayer_enabled = multiplayer_room.is_some();
            if let Some(room_name) = multiplayer_room {
                app.multiplayer_room = room_name;
            }
            if let Some(role_name) = multiplayer_role {
                app.multiplayer_role = role_name;
            }
            if let Some(ui_role) = multiplayer_ui_role {
                app.multiplayer_ui_role = ui_role;
            }
            if let Some(mode_name) = multiplayer_mode {
                app.multiplayer_mode = mode_name;
            }
            if let Some(connection_id) = multiplayer_connection_id {
                app.multiplayer_connection_id = connection_id;
            }
            if let Some(display_name) = multiplayer_display_name {
                app.multiplayer_display_name = display_name;
            }
            if let Some(approval_state) = multiplayer_approval_state {
                app.multiplayer_approval_state = approval_state;
            }
            app.update_welcome();
            if let Ok(cfg) = rpc_get_config_blocking(&rpc_cmd_tx.borrow()) {
                if let Some(raw_theme) = cfg.get("theme").and_then(|v| v.as_str()) {
                    app.theme_mode = ThemeMode::from_ui_theme(raw_theme);
                }
            }
            refresh_workspace_status(app);
            refresh_resume_dashboard(app, &rpc_cmd_tx.borrow());
            write_session_log(
                session_log,
                &format!(
                    "server_initialized provider={} model={} version={}",
                    app.provider_name, app.model_name, app.version
                ),
            );
            app.set_status("Connected to Python backend");
        }
        ServerMsg::ChatResponse { content } => {
            write_session_log(
                session_log,
                &format!("chat_response_nonstream chars={}", content.chars().count()),
            );
            app.stop_waiting();
            app.record_assistant_output(&content);
            app.push_message(ChatMessage::assistant(content));
        }
        ServerMsg::SystemMessage { content } => {
            if content.starts_with("__PLAN__:") {
                let rest = &content["__PLAN__:".len()..];
                if let Some(colon_pos) = rest.find(':') {
                    let request = rest[..colon_pos].to_string();
                    let steps: Vec<String> = rest[colon_pos + 1..]
                        .lines()
                        .filter(|l| !l.trim().is_empty())
                        .map(|l| l.to_string())
                        .collect();
                    if !steps.is_empty() {
                        app.stop_waiting();
                        app.finalize_streaming();
                        app.set_plan(steps, request);
                    }
                }
            } else {
                app.push_message(ChatMessage::system(content));
            }
        }
        ServerMsg::AutomationPrompt { display, prompt } => {
            app.prompt_queue
                .push_back(poor_cli_tui::app::QueuedPrompt::automation(
                    display.clone(),
                    prompt,
                ));
            let queued = app.prompt_queue.len();
            app.push_message(ChatMessage::system(format!(
                "Queued automation task: {display} ({queued} queued)"
            )));
        }
        ServerMsg::Providers { providers } => {
            app.providers = providers;
            app.provider_select_idx = 0;
            app.mode = poor_cli_tui::app::AppMode::ProviderSelect;
        }
        ServerMsg::ProviderSwitched { provider, model } => {
            app.provider_name = provider;
            app.model_name = model;
            app.is_local_provider = app.provider_name == "ollama";
            write_session_log(
                session_log,
                &format!(
                    "provider_switch_success provider={} model={}",
                    app.provider_name, app.model_name
                ),
            );
            app.set_status("Provider switched successfully");
        }
        ServerMsg::Error { message } => {
            let active_request_id = app.active_request_id.clone();
            let elapsed_ms = app
                .active_request_started_at
                .map(|started| started.elapsed().as_millis())
                .unwrap_or(0);
            write_session_log(
                session_log,
                &format!(
                    "server_error active_request_id={} duration_ms={} message={}",
                    if active_request_id.is_empty() {
                        "none"
                    } else {
                        active_request_id.as_str()
                    },
                    elapsed_ms,
                    truncate_line(&message.replace('\n', " "), 220)
                ),
            );
            app.finalize_streaming();
            app.active_tool = None;
            app.stop_waiting();
            let remote_reconnect_configured = !app.multiplayer_remote_url.is_empty()
                && !app.multiplayer_remote_token.is_empty()
                && !app.multiplayer_room.is_empty();
            let mut state = remote_reconnect_state.borrow_mut();
            if remote_reconnect_configured
                && multiplayer::should_attempt_remote_reconnect(&message)
                && state.1.is_none()
            {
                if state.0 < max_remote_reconnect_attempts {
                    let delay_secs = (1u64 << state.0).min(30);
                    state.0 += 1;
                    state.1 = Some(std::time::Instant::now() + Duration::from_secs(delay_secs));
                    state.2 = true;
                    let reconnect_text = format!(
                        "Multiplayer connection lost. Reconnecting in {delay_secs}s (attempt {}/{max_remote_reconnect_attempts}).",
                        state.0
                    );
                    if let Some(idx) = app.reconnect_message_idx {
                        if let Some(msg) = app.messages.get_mut(idx) {
                            msg.content = reconnect_text; // update in-place
                        }
                    } else {
                        app.push_message(ChatMessage::system(reconnect_text));
                        app.reconnect_message_idx = Some(app.messages.len() - 1);
                    }
                    app.set_status("Scheduling multiplayer reconnect");
                } else if state.2 {
                    state.2 = false;
                    app.reconnect_message_idx = None;
                    app.push_message(ChatMessage::error(format!(
                        "Auto-reconnect exhausted after {max_remote_reconnect_attempts} attempts: {message}\nCheck network, then retry with `/join-server` or `/pair <code>`."
                    )));
                }
            }
            if app.provider_name.eq_ignore_ascii_case("ollama") {
                if let Some((title, content)) = ollama_recovery_popup(&message, &app.model_name) {
                    app.open_info_popup(title, content);
                }
            }
            app.push_message(ChatMessage::error(message));
            app.active_request_id.clear();
            app.active_request_started_at = None;
        }
        ServerMsg::StreamChunk {
            request_id,
            chunk,
            done,
            reason,
        } => {
            let request_id_for_log = if request_id.is_empty() {
                app.active_request_id.clone()
            } else {
                request_id
            };
            if done {
                let response_chars = app
                    .streaming_message
                    .and_then(|idx| app.messages.get(idx))
                    .map(|msg| msg.content.chars().count())
                    .unwrap_or(0);
                let elapsed_ms = app
                    .active_request_started_at
                    .map(|started| started.elapsed().as_millis())
                    .unwrap_or(0);
                let done_reason = reason.as_deref().unwrap_or("complete");
                write_session_log(
                    session_log,
                    &format!(
                        "chat_request_done request_id={} reason={} response_chars={} duration_ms={}",
                        request_id_for_log, done_reason, response_chars, elapsed_ms
                    ),
                );
                app.finalize_streaming();
                app.stop_waiting();
                app.active_request_id.clear();
                app.active_request_started_at = None;
                if !app.plan_steps.is_empty() && app.plan_current_step < app.plan_steps.len() {
                    app.advance_plan_step();
                    if app.plan_current_step < app.plan_steps.len() {
                        app.mode = poor_cli_tui::app::AppMode::PlanReview;
                    } else {
                        app.push_message(ChatMessage::system("Plan complete.".to_string()));
                        app.clear_plan();
                    }
                }
            } else if !chunk.is_empty() {
                write_session_log(
                    session_log,
                    &format!(
                        "chat_request_chunk request_id={} chars={}",
                        request_id_for_log,
                        chunk.chars().count()
                    ),
                );
                if app.streaming_message.is_none() {
                    app.start_streaming_message();
                }
                app.append_streaming_chunk(&chunk);
            }
        }
        ServerMsg::ToolEvent {
            request_id,
            event_type,
            tool_name,
            tool_args,
            tool_result,
            diff,
            paths,
            checkpoint_id,
            changed,
            message,
            iteration_index,
            iteration_cap,
        } => {
            write_session_log(
                session_log,
                &format!(
                    "chat_request_tool_event request_id={} type={} tool={} iter={}/{}",
                    request_id, event_type, tool_name, iteration_index, iteration_cap
                ),
            );
            app.current_iteration = iteration_index;
            app.iteration_cap = iteration_cap;
            if event_type == "tool_call_start" {
                app.active_tool = Some(tool_name.clone());
                let args_str = serde_json::to_string_pretty(&tool_args).unwrap_or_default();
                app.push_message(ChatMessage::tool_call(&tool_name, args_str));
                app.push_timeline_entry(poor_cli_tui::app::TimelineEntry {
                    kind: poor_cli_tui::app::TimelineEntryKind::ToolCall,
                    request_id,
                    title: tool_name,
                    detail: serde_json::to_string_pretty(&tool_args).unwrap_or_default(),
                    diff: String::new(),
                    paths,
                    checkpoint_id: None,
                    changed: None,
                    review_summary: None,
                    timestamp: std::time::Instant::now(),
                });
            } else if event_type == "tool_result" {
                app.active_tool = None;
                if !diff.is_empty() {
                    app.push_message(ChatMessage::diff_view(&tool_name, diff.clone()));
                } else {
                    app.push_message(ChatMessage::tool_result(&tool_name, tool_result.clone()));
                }
                if let Some(ref checkpoint) = checkpoint_id {
                    app.last_mutation_checkpoint_id = Some(checkpoint.clone());
                    app.remember_recent_checkpoint(checkpoint);
                }
                if !diff.is_empty() {
                    app.last_mutation_diff = diff.clone();
                }
                for path in &paths {
                    app.remember_recent_edit(path);
                }
                refresh_workspace_status(app);
                refresh_resume_dashboard(app, &rpc_cmd_tx.borrow());
                app.push_timeline_entry(poor_cli_tui::app::TimelineEntry {
                    kind: if diff.is_empty() {
                        poor_cli_tui::app::TimelineEntryKind::ToolResult
                    } else {
                        poor_cli_tui::app::TimelineEntryKind::Diff
                    },
                    request_id,
                    title: tool_name,
                    detail: if message.is_empty() {
                        tool_result
                    } else {
                        message
                    },
                    diff,
                    paths,
                    checkpoint_id,
                    changed,
                    review_summary: None,
                    timestamp: std::time::Instant::now(),
                });
            }
        }
        ServerMsg::PermissionRequest {
            request_id,
            tool_name,
            tool_args,
            prompt_id,
            operation,
            paths,
            diff,
            checkpoint_id,
            changed,
            message,
        } => {
            write_session_log(
                session_log,
                &format!(
                    "chat_request_permission request_id={} tool={} prompt_id={}",
                    request_id, tool_name, prompt_id
                ),
            );
            let args_str = serde_json::to_string_pretty(&tool_args).unwrap_or_default();
            app.permission_message = format!("{tool_name}: {args_str}");
            app.permission_prompt_id = prompt_id.clone();
            app.permission_review_read_only = !app.can_control_multiplayer_reviews();
            app.push_timeline_entry(poor_cli_tui::app::TimelineEntry {
                kind: poor_cli_tui::app::TimelineEntryKind::Permission,
                request_id: request_id.clone(),
                title: tool_name.clone(),
                detail: if message.is_empty() {
                    "Awaiting permission".to_string()
                } else {
                    message.clone()
                },
                diff: diff.clone(),
                paths: paths.clone(),
                checkpoint_id: checkpoint_id.clone(),
                changed,
                review_summary: None,
                timestamp: std::time::Instant::now(),
            });
            if app.permission_review_read_only {
                app.info_popup_title = "Driver Review In Progress".to_string();
                app.info_popup_content = if message.is_empty() {
                    format!(
                        "The active driver is reviewing `{tool_name}`.\n\nThis client is read-only for approval prompts. Use `/suggest <text>` or `/collab agenda add <text>` to give input."
                    )
                } else {
                    format!(
                        "{message}\n\nThe active driver is reviewing `{tool_name}`.\nThis client is read-only for approval prompts. Use `/suggest <text>` or `/collab agenda add <text>` to give input."
                    )
                };
                app.info_popup_scroll = 0;
                app.mode = poor_cli_tui::app::AppMode::InfoPopup;
            } else if !diff.is_empty() || !paths.is_empty() {
                app.open_mutation_review(poor_cli_tui::app::MutationReviewState {
                    request_id,
                    tool_name,
                    operation,
                    prompt_id,
                    paths,
                    diff,
                    checkpoint_id,
                    changed,
                    message,
                    selected_path_index: 0,
                    chunks: Vec::new(),
                    selected_chunk_index: 0,
                });
            } else {
                app.mode = poor_cli_tui::app::AppMode::PermissionPrompt;
            }
        }
        ServerMsg::PlanRequest {
            request_id,
            prompt_id,
            summary,
            original_request,
            steps,
        } => {
            write_session_log(
                session_log,
                &format!(
                    "chat_request_plan request_id={} prompt_id={} steps={}",
                    request_id,
                    prompt_id,
                    steps.len()
                ),
            );
            app.push_timeline_entry(poor_cli_tui::app::TimelineEntry {
                kind: poor_cli_tui::app::TimelineEntryKind::Phase,
                request_id,
                title: "Plan review".to_string(),
                detail: if summary.is_empty() {
                    "Awaiting plan approval".to_string()
                } else {
                    summary.clone()
                },
                diff: String::new(),
                paths: Vec::new(),
                checkpoint_id: None,
                changed: None,
                review_summary: None,
                timestamp: std::time::Instant::now(),
            });
            let read_only = !app.can_control_multiplayer_reviews();
            app.set_plan_review(steps, original_request, summary, prompt_id, true, read_only);
        }
        ServerMsg::Progress {
            request_id,
            phase,
            message,
            iteration_index,
            iteration_cap,
        } => {
            write_session_log(
                session_log,
                &format!(
                    "chat_request_progress request_id={} phase={} message={} iter={}/{}",
                    request_id,
                    phase,
                    truncate_line(&message.replace('\n', " "), 120),
                    iteration_index,
                    iteration_cap
                ),
            );
            app.current_iteration = iteration_index;
            app.iteration_cap = iteration_cap;
            app.push_timeline_entry(poor_cli_tui::app::TimelineEntry {
                kind: poor_cli_tui::app::TimelineEntryKind::Phase,
                request_id,
                title: phase,
                detail: message,
                diff: String::new(),
                paths: Vec::new(),
                checkpoint_id: None,
                changed: None,
                review_summary: None,
                timestamp: std::time::Instant::now(),
            });
        }
        ServerMsg::CostUpdate {
            request_id,
            input_tokens,
            output_tokens,
        } => {
            write_session_log(
                session_log,
                &format!(
                    "chat_request_cost request_id={} input_tokens={} output_tokens={}",
                    request_id, input_tokens, output_tokens
                ),
            );
            app.turn_input_tokens += input_tokens;
            app.turn_output_tokens += output_tokens;
            app.cumulative_input_tokens += input_tokens;
            app.cumulative_output_tokens += output_tokens;
            app.push_timeline_entry(poor_cli_tui::app::TimelineEntry {
                kind: poor_cli_tui::app::TimelineEntryKind::Cost,
                request_id,
                title: "Token usage".to_string(),
                detail: format!("input={} output={}", input_tokens, output_tokens),
                diff: String::new(),
                paths: Vec::new(),
                checkpoint_id: None,
                changed: None,
                review_summary: None,
                timestamp: std::time::Instant::now(),
            });
        }
        ServerMsg::RoomEvent {
            room,
            mode,
            event_type,
            actor,
            request_id,
            queue_depth,
            member_count,
            active_connection_id,
            lobby_enabled,
            preset,
            agenda_summary,
            members,
        } => {
            write_session_log(
                session_log,
                &format!(
                    "room_event room={} type={} actor={} request_id={} queue_depth={} member_count={}",
                    room, event_type, actor, request_id, queue_depth, member_count
                ),
            );
            app.multiplayer_enabled = true;
            app.multiplayer_room = room;
            app.multiplayer_mode = mode;
            app.multiplayer_queue_depth = queue_depth;
            app.multiplayer_member_count = member_count;
            app.multiplayer_active_connection_id = active_connection_id;
            app.multiplayer_lobby_enabled = lobby_enabled;
            app.multiplayer_preset = preset;
            if let Some(summary) = agenda_summary.as_object() {
                app.update_agenda_from_summary(summary);
            }
            if let Some(items) = members.as_array() {
                let mut summaries = Vec::new();
                for entry in items.iter().take(10) {
                    let connection_id = entry
                        .get("connectionId")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let role = entry
                        .get("role")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let ui_role = entry.get("uiRole").and_then(|v| v.as_str()).unwrap_or("");
                    let approved = entry
                        .get("approved")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(true);
                    let active = entry
                        .get("active")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let mut label = if ui_role.is_empty() {
                        format!("{connection_id}:{role}")
                    } else {
                        format!("{connection_id}:{role}/{ui_role}")
                    };
                    if !approved {
                        label.push_str(" (pending)");
                    }
                    if active {
                        label.push_str(" *");
                    }
                    summaries.push(label);
                }
                app.multiplayer_member_roles = summaries;
                let mut pair_users = Vec::new();
                for entry in items.iter().take(20) {
                    let cid = entry
                        .get("connectionId")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let ui_role = entry
                        .get("uiRole")
                        .and_then(|v| v.as_str())
                        .unwrap_or("navigator");
                    let name = entry
                        .get("displayName")
                        .and_then(|v| v.as_str())
                        .or_else(|| entry.get("clientName").and_then(|v| v.as_str()))
                        .unwrap_or(cid);
                    let active = entry
                        .get("active")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    pair_users.push(poor_cli_tui::app::PairUser {
                        name: name.to_string(),
                        connection_id: cid.to_string(),
                        role: poor_cli_tui::app::PairRole::from_ui_role(ui_role),
                        is_active: active,
                    });
                    if app.multiplayer_connection_id == cid {
                        app.multiplayer_role = entry
                            .get("role")
                            .and_then(|v| v.as_str())
                            .unwrap_or(&app.multiplayer_role)
                            .to_string();
                        app.multiplayer_ui_role = ui_role.to_string();
                        app.multiplayer_display_name = name.to_string();
                        app.multiplayer_approval_state = entry
                            .get("approvalState")
                            .and_then(|v| v.as_str())
                            .unwrap_or("approved")
                            .to_string();
                        app.multiplayer_hand_raised = entry
                            .get("handRaised")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);
                        app.multiplayer_queue_position = entry
                            .get("queuePosition")
                            .and_then(|v| v.as_u64())
                            .unwrap_or(0);
                    }
                }
                app.connected_users = pair_users;
            }
            let status = match event_type.as_str() {
                "queued" => format!("Room queue depth: {queue_depth}"),
                "started" => format!("Request started by `{actor}`"),
                "finished" => format!("Request finished by `{actor}`"),
                "member_joined" => format!("Member joined: `{actor}`"),
                "member_left" => format!("Member left: `{actor}`"),
                "member_pending" => format!("Pending approval: `{actor}`"),
                "member_approved" => format!("Member approved: `{actor}`"),
                "member_denied" => format!("Member denied: `{actor}`"),
                "agenda_added" => format!(
                    "Agenda updated ({} open)",
                    app.multiplayer_agenda_open_count
                ),
                "agenda_resolved" => format!(
                    "Agenda resolved ({} open)",
                    app.multiplayer_agenda_open_count
                ),
                "hand_raised" => format!("Hand raised: `{actor}`"),
                "hand_lowered" => format!("Hand lowered: `{actor}`"),
                _ => format!("Room event: {event_type}"),
            };
            app.set_status(status);
        }
        ServerMsg::Suggestion { sender, text } => {
            write_session_log(
                session_log,
                &format!("suggestion sender={} text_len={}", sender, text.len()),
            );
            app.push_suggestion(sender.clone(), text.clone());
            app.push_message(ChatMessage::system(format!("[{sender} suggests]: {text}")));
        }
        ServerMsg::MemberRoleUpdated {
            room,
            connection_id,
            role,
            ui_role,
        } => {
            write_session_log(
                session_log,
                &format!(
                    "member_role_updated room={} connection_id={} role={}",
                    room, connection_id, role
                ),
            );
            app.multiplayer_enabled = true;
            if !room.is_empty() {
                app.multiplayer_room = room;
            }
            let prefix = format!("{connection_id}:");
            let mut updated = false;
            for entry in &mut app.multiplayer_member_roles {
                if entry.starts_with(&prefix) {
                    *entry = format!("{connection_id}:{role}");
                    updated = true;
                    break;
                }
            }
            if !updated {
                if ui_role.is_empty() {
                    app.multiplayer_member_roles
                        .push(format!("{connection_id}:{role}"));
                } else {
                    app.multiplayer_member_roles
                        .push(format!("{connection_id}:{role}/{ui_role}"));
                }
            }
            if connection_id == app.multiplayer_connection_id {
                app.multiplayer_role = role.clone();
                if !ui_role.is_empty() {
                    app.multiplayer_ui_role = ui_role.clone();
                }
            }
            app.set_status(format!(
                "Role updated: `{connection_id}` -> {}",
                if ui_role.is_empty() { role } else { ui_role }
            ));
        }
    }

    Ok(LoopControl::Continue)
}
