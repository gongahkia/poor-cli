use super::*;

pub(super) fn handle_server_message(
    app: &mut App,
    msg: ServerMsg,
    rpc_cmd_tx: &RefCell<mpsc::Sender<RpcCommand>>,
    remote_reconnect_state: &RefCell<(u32, Option<std::time::Instant>, bool)>,
    max_remote_reconnect_attempts: u32,
) -> Result<LoopControl, Box<dyn std::error::Error>> {
    match msg {
        ServerMsg::Initialized {
            provider,
            model,
            version,
            multiplayer_room,
            multiplayer_role,
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
            app.update_welcome();
            if let Ok(cfg) = rpc_get_config_blocking(&rpc_cmd_tx.borrow()) {
                if let Some(raw_theme) = cfg.get("theme").and_then(|v| v.as_str()) {
                    app.theme_mode = ThemeMode::from_ui_theme(raw_theme);
                }
            }
            app.set_status("Connected to Python backend");
        }
        ServerMsg::ChatResponse { content } => {
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
        ServerMsg::Providers { providers } => {
            app.providers = providers;
            app.provider_select_idx = 0;
            app.mode = poor_cli_tui::app::AppMode::ProviderSelect;
        }
        ServerMsg::ProviderSwitched { provider, model } => {
            app.provider_name = provider;
            app.model_name = model;
            app.is_local_provider = app.provider_name == "ollama";
            app.set_status("Provider switched successfully");
        }
        ServerMsg::Error { message } => {
            app.finalize_streaming();
            app.active_tool = None;
            app.stop_waiting();
            let remote_reconnect_configured = !app.multiplayer_remote_url.is_empty()
                && !app.multiplayer_remote_token.is_empty()
                && !app.multiplayer_room.is_empty();
            let mut state = remote_reconnect_state.borrow_mut();
            if remote_reconnect_configured
                && should_attempt_remote_reconnect(&message)
                && state.1.is_none()
            {
                if state.0 < max_remote_reconnect_attempts {
                    let delay_secs = (1u64 << state.0).min(30);
                    state.0 += 1;
                    state.1 = Some(std::time::Instant::now() + Duration::from_secs(delay_secs));
                    state.2 = true;
                    app.push_message(ChatMessage::system(format!(
                        "Multiplayer connection lost. Reconnecting in {delay_secs}s (attempt {}/{max_remote_reconnect_attempts}).",
                        state.0
                    )));
                    app.set_status("Scheduling multiplayer reconnect");
                } else if state.2 {
                    state.2 = false;
                    app.push_message(ChatMessage::error(format!(
                        "Auto-reconnect exhausted after {max_remote_reconnect_attempts} attempts: {message}"
                    )));
                }
            }
            if app.provider_name.eq_ignore_ascii_case("ollama") {
                if let Some((title, content)) = ollama_recovery_popup(&message, &app.model_name) {
                    app.open_info_popup(title, content);
                }
            }
            app.push_message(ChatMessage::error(message));
        }
        ServerMsg::StreamChunk { chunk, done, reason: _ } => {
            if done {
                app.finalize_streaming();
                app.stop_waiting();
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
                if app.streaming_message.is_none() {
                    app.start_streaming_message();
                }
                app.append_streaming_chunk(&chunk);
            }
        }
        ServerMsg::ToolEvent {
            event_type,
            tool_name,
            tool_args,
            tool_result,
            diff,
            iteration_index,
            iteration_cap,
        } => {
            app.current_iteration = iteration_index;
            app.iteration_cap = iteration_cap;
            if event_type == "tool_call_start" {
                app.active_tool = Some(tool_name.clone());
                let args_str = serde_json::to_string_pretty(&tool_args).unwrap_or_default();
                app.push_message(ChatMessage::tool_call(&tool_name, args_str));
            } else if event_type == "tool_result" {
                app.active_tool = None;
                if !diff.is_empty() {
                    app.push_message(ChatMessage::diff_view(&tool_name, diff));
                } else {
                    app.push_message(ChatMessage::tool_result(&tool_name, tool_result));
                }
            }
        }
        ServerMsg::PermissionRequest {
            tool_name,
            tool_args,
            prompt_id,
        } => {
            let args_str = serde_json::to_string_pretty(&tool_args).unwrap_or_default();
            app.permission_message = format!("{tool_name}: {args_str}");
            app.permission_prompt_id = prompt_id;
            app.mode = poor_cli_tui::app::AppMode::PermissionPrompt;
        }
        ServerMsg::Progress {
            phase: _,
            message: _,
            iteration_index,
            iteration_cap,
        } => {
            app.current_iteration = iteration_index;
            app.iteration_cap = iteration_cap;
        }
        ServerMsg::CostUpdate {
            input_tokens,
            output_tokens,
        } => {
            app.turn_input_tokens += input_tokens;
            app.turn_output_tokens += output_tokens;
            app.cumulative_input_tokens += input_tokens;
            app.cumulative_output_tokens += output_tokens;
        }
        ServerMsg::RoomEvent {
            room,
            event_type,
            actor,
            request_id: _,
            queue_depth,
            member_count,
            active_connection_id,
            lobby_enabled,
            preset,
            members,
        } => {
            app.multiplayer_enabled = true;
            app.multiplayer_room = room;
            app.multiplayer_queue_depth = queue_depth;
            app.multiplayer_member_count = member_count;
            app.multiplayer_active_connection_id = active_connection_id;
            app.multiplayer_lobby_enabled = lobby_enabled;
            app.multiplayer_preset = preset;
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
                    let approved = entry
                        .get("approved")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(true);
                    let active = entry
                        .get("active")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let mut label = format!("{connection_id}:{role}");
                    if !approved {
                        label.push_str(" (pending)");
                    }
                    if active {
                        label.push_str(" *");
                    }
                    summaries.push(label);
                }
                app.multiplayer_member_roles = summaries;
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
                _ => format!("Room event: {event_type}"),
            };
            app.set_status(status);
        }
        ServerMsg::MemberRoleUpdated {
            room,
            connection_id,
            role,
        } => {
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
                app.multiplayer_member_roles
                    .push(format!("{connection_id}:{role}"));
            }
            app.set_status(format!("Role updated: `{connection_id}` -> {role}"));
        }
    }

    Ok(LoopControl::Continue)
}
