use super::*;

pub(crate) fn spawn_backend_worker(
    tx: &mpsc::Sender<ServerMsg>,
    launch: session::BackendLaunchContext,
    server_args: Vec<String>,
    provider: Option<String>,
    model: Option<String>,
    permission_mode: Option<String>,
) -> mpsc::Sender<RpcCommand> {
    let (rpc_cmd_tx, rpc_cmd_rx) = mpsc::channel::<RpcCommand>();
    let tx_init = tx.clone();
    let tx_notif = tx.clone();
    let log_ctx = launch.session_log.clone();
    let mode_label = if server_args.is_empty() {
        "local".to_string()
    } else {
        format!("bridge args={}", server_args.join(" "))
    };

    thread::spawn(move || {
        session::write_session_log(
            log_ctx.as_ref(),
            &format!("backend_spawn_attempt mode={mode_label}"),
        );
        match RpcClient::spawn_with_notifications_args(
            &launch.python_bin,
            launch.cwd.as_deref(),
            &server_args,
            launch.backend_log_path.as_deref(),
        ) {
            Ok((client, notification_rx)) => {
                session::write_session_log(log_ctx.as_ref(), "backend_spawn_ok");
                let startup_state = client.get_startup_state().ok();
                let startup_providers = client.list_providers().unwrap_or_default();
                let startup_selection = resolve_startup_selection(
                    provider.clone(),
                    model.clone(),
                    startup_state.as_ref(),
                    &startup_providers,
                );
                session::write_session_log(
                    log_ctx.as_ref(),
                    &format!(
                        "startup_selection provider={} model={}",
                        startup_selection
                            .provider
                            .as_deref()
                            .unwrap_or("(none)"),
                        startup_selection.model.as_deref().unwrap_or("(none)")
                    ),
                );
                let notification_log_ctx = log_ctx.clone();

                thread::spawn(move || {
                    while let Ok(notif) = notification_rx.recv() {
                        let msg = match notif {
                            ServerNotification::ThinkingChunk { request_id, chunk } => {
                                ServerMsg::ThinkingChunk { request_id, chunk }
                            }
                            ServerNotification::StreamChunk {
                                request_id,
                                chunk,
                                done,
                                reason,
                                ..
                            } => {
                                if done {
                                    let reason_label = reason.as_deref().unwrap_or("complete");
                                    session::write_session_log(
                                        notification_log_ctx.as_ref(),
                                        &format!(
                                            "notif_stream_done request_id={} reason={reason_label}",
                                            request_id
                                        ),
                                    );
                                } else if !chunk.is_empty() {
                                    session::write_session_log(
                                        notification_log_ctx.as_ref(),
                                        &format!(
                                            "notif_stream_chunk request_id={} chars={}",
                                            request_id,
                                            chunk.chars().count()
                                        ),
                                    );
                                }
                                ServerMsg::StreamChunk {
                                    request_id,
                                    chunk,
                                    done,
                                    reason,
                                }
                            }
                            ServerNotification::ToolEvent {
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
                                ..
                            } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!(
                                        "notif_tool_event request_id={} type={} tool={} iter={}/{}",
                                        request_id,
                                        event_type,
                                        tool_name,
                                        iteration_index,
                                        iteration_cap
                                    ),
                                );
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
                                }
                            }
                            ServerNotification::PermissionRequest {
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
                                ..
                            } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!(
                                        "notif_permission_request request_id={} tool={} prompt_id={}",
                                        request_id, tool_name, prompt_id
                                    ),
                                );
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
                                }
                            }
                            ServerNotification::PlanRequest {
                                request_id,
                                prompt_id,
                                summary,
                                original_request,
                                steps,
                            } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!(
                                        "notif_plan_request request_id={} prompt_id={} steps={}",
                                        request_id,
                                        prompt_id,
                                        steps.len()
                                    ),
                                );
                                ServerMsg::PlanRequest {
                                    request_id,
                                    prompt_id,
                                    summary,
                                    original_request,
                                    steps,
                                }
                            }
                            ServerNotification::Progress {
                                request_id,
                                phase,
                                message,
                                iteration_index,
                                iteration_cap,
                                ..
                            } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!(
                                        "notif_progress request_id={} phase={} iter={}/{}",
                                        request_id, phase, iteration_index, iteration_cap
                                    ),
                                );
                                ServerMsg::Progress {
                                    request_id,
                                    phase,
                                    message,
                                    iteration_index,
                                    iteration_cap,
                                }
                            }
                            ServerNotification::CostUpdate {
                                request_id,
                                input_tokens,
                                output_tokens,
                                ..
                            } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!(
                                        "notif_cost_update request_id={} input_tokens={} output_tokens={}",
                                        request_id, input_tokens, output_tokens
                                    ),
                                );
                                ServerMsg::CostUpdate {
                                    request_id,
                                    input_tokens,
                                    output_tokens,
                                }
                            }
                            ServerNotification::RoomEvent {
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
                                ..
                            } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!(
                                        "notif_room_event room={} type={} actor={} request_id={}",
                                        room, event_type, actor, request_id
                                    ),
                                );
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
                                }
                            }
                            ServerNotification::MemberRoleUpdated {
                                room,
                                connection_id,
                                role,
                                ui_role,
                            } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!(
                                        "notif_member_role_updated room={} connection_id={} role={}",
                                        room, connection_id, role
                                    ),
                                );
                                ServerMsg::MemberRoleUpdated {
                                    room,
                                    connection_id,
                                    role,
                                    ui_role,
                                }
                            }
                            ServerNotification::Suggestion { sender, text, .. } => {
                                session::write_session_log(
                                    notification_log_ctx.as_ref(),
                                    &format!("notif_suggestion sender={}", sender),
                                );
                                ServerMsg::Suggestion { sender, text }
                            }
                        };
                        if tx_notif.send(msg).is_err() {
                            session::write_session_log(
                                notification_log_ctx.as_ref(),
                                "notification_forward_channel_closed",
                            );
                            break;
                        }
                    }
                    session::write_session_log(notification_log_ctx.as_ref(), "notification_reader_stopped");
                });

                match client.initialize(
                    startup_selection.provider.as_deref(),
                    startup_selection.model.as_deref(),
                    None,
                    permission_mode.as_deref(),
                ) {
                    Ok(init) => {
                        session::write_session_log(log_ctx.as_ref(), "backend_initialize_ok");
                        let _ = tx_init.send(server_msg_from_init_result(
                            init,
                            &startup_selection.provider,
                            &startup_selection.model,
                        ));
                        run_rpc_worker(client, rpc_cmd_rx);
                    }
                    Err(e) => {
                        session::write_session_log(
                            log_ctx.as_ref(),
                            &format!("backend_initialize_error {e}"),
                        );
                        let _ = tx_init.send(ServerMsg::Error {
                            message: format!("Initialization failed: {e}"),
                        });
                        run_rpc_worker(client, rpc_cmd_rx);
                    }
                }
            }
            Err(e) => {
                session::write_session_log(log_ctx.as_ref(), &format!("backend_spawn_error {e}"));
                let _ = tx_init.send(ServerMsg::Error {
                    message: format!("Failed to start server: {e}"),
                });
            }
        }
    });

    rpc_cmd_tx
}

pub(crate) fn server_msg_from_init_result(
    init: InitResult,
    provider_fallback: &Option<String>,
    model_fallback: &Option<String>,
) -> ServerMsg {
    let (provider, model) = if let Some(caps) = &init.capabilities {
        let provider = caps
            .pointer("/providerInfo/name")
            .and_then(|value| value.as_str())
            .map(|value| value.to_string())
            .unwrap_or_else(|| provider_fallback.clone().unwrap_or_else(|| "gemini".into()));
        let model = caps
            .pointer("/providerInfo/model")
            .and_then(|value| value.as_str())
            .map(|value| value.to_string())
            .unwrap_or_else(|| {
                model_fallback
                    .clone()
                    .unwrap_or_else(|| provider_catalog::default_model("gemini").into())
            });
        (provider, model)
    } else {
        (
            provider_fallback.clone().unwrap_or_else(|| "gemini".into()),
            model_fallback
                .clone()
                .unwrap_or_else(|| provider_catalog::default_model("gemini").into()),
        )
    };

    ServerMsg::Initialized {
        provider,
        model,
        version: init.version.unwrap_or_else(|| "0.4.0".into()),
        multiplayer_room: init
            .capabilities
            .as_ref()
            .and_then(|caps| caps.pointer("/multiplayer/room"))
            .and_then(|value| value.as_str())
            .map(|value| value.to_string()),
        multiplayer_role: init
            .capabilities
            .as_ref()
            .and_then(|caps| caps.pointer("/multiplayer/role"))
            .and_then(|value| value.as_str())
            .map(|value| value.to_string()),
        multiplayer_ui_role: init
            .capabilities
            .as_ref()
            .and_then(|caps| caps.pointer("/multiplayer/uiRole"))
            .and_then(|value| value.as_str())
            .map(|value| value.to_string()),
        multiplayer_mode: init
            .capabilities
            .as_ref()
            .and_then(|caps| caps.pointer("/multiplayer/mode"))
            .and_then(|value| value.as_str())
            .map(|value| value.to_string()),
        multiplayer_connection_id: init
            .capabilities
            .as_ref()
            .and_then(|caps| caps.pointer("/multiplayer/connectionId"))
            .and_then(|value| value.as_str())
            .map(|value| value.to_string()),
        multiplayer_display_name: init
            .capabilities
            .as_ref()
            .and_then(|caps| caps.pointer("/multiplayer/displayName"))
            .and_then(|value| value.as_str())
            .map(|value| value.to_string()),
        multiplayer_approval_state: init
            .capabilities
            .as_ref()
            .and_then(|caps| caps.pointer("/multiplayer/approvalState"))
            .and_then(|value| value.as_str())
            .map(|value| value.to_string()),
    }
}

pub(crate) fn provider_is_ready(providers: &[ProviderInfo], provider_name: &str) -> bool {
    providers
        .iter()
        .any(|provider| provider.ready && provider.name.eq_ignore_ascii_case(provider_name))
}

pub(crate) fn normalize_model_name(model_name: Option<String>) -> Option<String> {
    model_name.and_then(|model_name| {
        if model_name.trim().is_empty() {
            None
        } else {
            Some(model_name)
        }
    })
}

pub(crate) fn configured_startup_model(
    startup_state: Option<&StartupState>,
    provider_name: &str,
) -> Option<String> {
    startup_state.and_then(|state| {
        if state.provider.eq_ignore_ascii_case(provider_name) && !state.model.trim().is_empty() {
            Some(state.model.clone())
        } else {
            None
        }
    })
}

pub(crate) fn provider_default_model(
    providers: &[ProviderInfo],
    provider_name: &str,
    startup_state: Option<&StartupState>,
) -> Option<String> {
    if let Some(provider) = providers
        .iter()
        .find(|provider| provider.name.eq_ignore_ascii_case(provider_name))
    {
        if let Some(model) = provider.models.first() {
            return Some(model.clone());
        }
    }

    configured_startup_model(startup_state, provider_name)
}

pub(crate) fn resolve_startup_selection(
    requested_provider: Option<String>,
    requested_model: Option<String>,
    startup_state: Option<&StartupState>,
    providers: &[ProviderInfo],
) -> session::StartupSelection {
    let requested_model = normalize_model_name(requested_model);

    if let Some(provider) = requested_provider {
        let model = requested_model
            .clone()
            .or_else(|| provider_default_model(providers, &provider, startup_state));
        return session::StartupSelection {
            provider: Some(provider),
            model,
        };
    }

    if let Some(state) = startup_state {
        if provider_is_ready(providers, &state.provider) {
            return session::StartupSelection {
                provider: Some(state.provider.clone()),
                model: requested_model.clone()
                    .or_else(|| configured_startup_model(startup_state, &state.provider))
                    .or_else(|| provider_default_model(providers, &state.provider, startup_state)),
            };
        }
    }

    if let Some(provider) = providers.iter().find(|provider| provider.ready) {
        return session::StartupSelection {
            provider: Some(provider.name.clone()),
            model: requested_model
                .or_else(|| provider_default_model(providers, &provider.name, startup_state)),
        };
    }

    session::StartupSelection {
        provider: None,
        model: requested_model,
    }
}
