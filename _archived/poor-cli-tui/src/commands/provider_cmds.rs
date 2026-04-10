use super::super::*;
use super::core::show_command_info_popup;

pub(super) fn handle_provider_commands(
    app: &mut App,
    raw: &str,
    lowered: &str,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    _launch: &BackendLaunchContext,
    _cancel_token: &Arc<AtomicBool>,
    _watch_state: &mut WatchState,
    _qa_watch_state: &mut QaWatchState,
) -> Option<bool> {
    if lowered == "/broke" {
        app.response_mode = ResponseMode::Poor;
        show_command_info_popup(
            app,
            raw,
            "Response mode set to **poor**.\nReplies will be terse and token-minimal.".to_string(),
        );
        return Some(false);
    }

    if lowered == "/my-treat" {
        app.response_mode = ResponseMode::Rich;
        show_command_info_popup(
            app,
            raw,
            "Response mode set to **rich**.\nReplies will prioritize completeness and quality."
                .to_string(),
        );
        return Some(false);
    }

    if lowered == "/provider" || lowered == "/model-info" {
        match rpc_get_provider_info_blocking(rpc_cmd_tx) {
            Ok(value) => {
                let provider = value.get("name").and_then(|v| v.as_str()).unwrap_or(app.provider.name.as_str());
                let model = value.get("model").and_then(|v| v.as_str()).unwrap_or(app.provider.model.as_str());
                let caps = value.get("capabilities").unwrap_or(&Value::Null);
                let streaming = bool_icon(caps.get("streaming").and_then(|v| v.as_bool()));
                let function_calling = bool_icon(caps.get("function_calling").and_then(|v| v.as_bool()));
                let vision = bool_icon(caps.get("vision").and_then(|v| v.as_bool()));
                let models_section = if let Some(entry) = app.provider.list.iter().find(|p| p.name == provider) {
                    if entry.models.is_empty() { String::new() } else {
                        let list = entry.models.iter()
                            .map(|m| if *m == model { format!("- **{m}** (active)") } else { format!("- {m}") })
                            .collect::<Vec<_>>().join("\n");
                        format!("\n\n**Available Models:**\n{list}")
                    }
                } else {
                    "\n\nRun `/provider switch` to load available models.".to_string()
                };
                let info = format!(
                    "**Current Provider:** {provider}\n**Model:** {model}\n\n\
**Capabilities:**\n  Streaming: {streaming}\n  Function Calling: {function_calling}\n  Vision: {vision}\
{models_section}\n\nSwitch: `/provider switch` or F2"
                );
                show_command_info_popup(app, raw, info);
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch provider info: {e}"))),
        }
        return Some(false);
    }

    if lowered == "/provider switch" || lowered.starts_with("/provider switch ") {
        // falls through to the /switch handler below
    } else if lowered.starts_with("/provider ") {
        let args: Vec<&str> = raw.split_whitespace().skip(1).collect();
        let target_provider = args.first().unwrap_or(&"").to_string();
        let target_model = args.get(1).map(|s| s.to_string());
        if target_provider.is_empty() {
            show_command_info_popup(app, raw, "Usage: `/provider <name> [model]` or `/provider switch`".to_string());
            return Some(false);
        }
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        if rpc_cmd_tx.send(RpcCommand::SwitchProvider {
            provider: target_provider.clone(), model: target_model, reply: reply_tx,
        }).is_err() {
            app.push_message(ChatMessage::error("RPC unavailable"));
            return Some(false);
        }
        app.set_status(format!("Switching to {target_provider}..."));
        let tx2 = tx.clone();
        thread::spawn(move || {
            match reply_rx.recv_timeout(Duration::from_secs(30)) {
                Ok(Ok((p, m))) => { let _ = tx2.send(ServerMsg::ProviderSwitched { provider: p, model: m }); }
                Ok(Err(e)) => { let _ = tx2.send(ServerMsg::SystemMessage { content: format!("\u{26a0} Switch failed: {e}") }); }
                Err(_) => { let _ = tx2.send(ServerMsg::SystemMessage { content: "\u{26a0} Timed out switching provider".to_string() }); }
            }
        });
        return Some(false);
    }

    if lowered == "/setup" {
        match open_api_key_setup_editor(app, None) {
            Ok(()) => app.set_status("Opened setup editor"),
            Err(error) => app.push_message(ChatMessage::error(format!(
                "Failed to open setup editor: {error}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/env" || lowered == "/api-key" || lowered == "/api-key edit" {
        match open_api_key_setup_editor(app, None) {
            Ok(()) => {}
            Err(error) => app.push_message(ChatMessage::error(format!(
                "Failed to open setup editor: {error}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/api-key status" {
        match rpc_get_api_key_status_blocking(rpc_cmd_tx, None) {
            Ok(payload) => {
                let providers = payload
                    .get("providers")
                    .and_then(|v| v.as_object())
                    .cloned()
                    .unwrap_or_default();

                if providers.is_empty() {
                    show_command_info_popup(
                        app,
                        raw,
                        "No provider API key status available.".to_string(),
                    );
                    return Some(false);
                }

                let mut names = providers.keys().cloned().collect::<Vec<_>>();
                names.sort_by(|a, b| {
                    let a_active = providers.get(a).and_then(|e| e.get("active")).and_then(|v| v.as_bool()).unwrap_or(false);
                    let b_active = providers.get(b).and_then(|e| e.get("active")).and_then(|v| v.as_bool()).unwrap_or(false);
                    b_active.cmp(&a_active).then(a.cmp(b))
                });

                let mut lines = vec!["**API Key Status**".to_string(), String::new()];

                for provider in names {
                    let Some(entry) = providers.get(&provider) else {
                        continue;
                    };
                    let configured = entry
                        .get("configured")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let status_icon = if configured { "\u{2713}" } else { "\u{2717}" };
                    let is_active = entry.get("active").and_then(|v| v.as_bool()).unwrap_or(false);
                    let active = if is_active {
                        format!(" (active \u{2014} {})", app.provider.model)
                    } else {
                        String::new()
                    };
                    let masked = entry
                        .get("masked")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(not set)");
                    let source = entry
                        .get("source")
                        .and_then(|v| v.as_str())
                        .unwrap_or("none");
                    let env_var = entry
                        .get("envVar")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(unknown)");
                    let persisted = if entry
                        .get("persisted")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false)
                    {
                        "yes"
                    } else {
                        "no"
                    };

                    lines.push(format!(
                        "- {status_icon} **{provider}**{active}: `{masked}` (source: {source}; env: `{env_var}`; persisted: {persisted})"
                    ));
                }

                lines.push(String::new());
                lines.push("Edit with `/setup`. Direct set: `/api-key <provider> <key>`.".to_string());
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch API key status: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered.starts_with("/api-key ") {
        let mut parts = raw.splitn(3, ' ');
        let _ = parts.next();
        let provider = parts.next().unwrap_or("").trim();
        let api_key = parts.next().unwrap_or("").trim();

        if provider.is_empty() || api_key.is_empty() {
            show_command_info_popup(
                app,
                raw,
                "Usage: /setup\n       /env\n       /api-key\n       /api-key status\n       /api-key <provider> <api-key>".to_string(),
            );
            return Some(false);
        }

        match rpc_set_api_key_blocking(rpc_cmd_tx, provider, api_key, true) {
            Ok(result) => {
                let resolved_provider = result
                    .get("provider")
                    .and_then(|v| v.as_str())
                    .unwrap_or(provider);
                let env_var = result
                    .get("envVar")
                    .and_then(|v| v.as_str())
                    .unwrap_or("(unknown)");
                let masked_key = result
                    .get("maskedKey")
                    .and_then(|v| v.as_str())
                    .unwrap_or("********");
                let persisted = result
                    .get("persisted")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                let active_reloaded = result
                    .get("activeProviderReloaded")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);

                let mut lines = vec![format!(
                    "Stored API key for **{resolved_provider}** (`{env_var}` = `{masked_key}`)."
                )];
                if persisted {
                    lines.push("Persisted to secure local key storage.".to_string());
                }
                if active_reloaded {
                    lines.push("Reloaded the active provider with the updated key.".to_string());
                } else {
                    lines.push("Switch providers with `/switch` when needed.".to_string());
                }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to set API key for `{provider}`: {e}"
            ))),
        }
        return Some(false);
    }

    if lowered == "/switch" || lowered == "/providers" || lowered.starts_with("/switch ") || lowered.starts_with("/providers ") || lowered == "/provider switch" || lowered.starts_with("/provider switch ") {
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        if rpc_cmd_tx.send(RpcCommand::ListProviders { reply: reply_tx }).is_err() {
            app.push_message(ChatMessage::error("Failed to list providers: RPC worker unavailable"));
            return Some(false);
        }
        let tx2 = tx.clone();
        thread::spawn(move || {
            match reply_rx.recv_timeout(Duration::from_secs(15)) {
                Ok(Ok(providers)) => {
                    let _ = tx2.send(ServerMsg::Providers {
                        providers: providers
                            .into_iter()
                            .map(|p| ProviderEntry {
                                name: p.name,
                                available: p.available,
                                ready: p.ready,
                                status_label: p.status_label,
                                models: p.models,
                            })
                            .collect(),
                    });
                }
                Ok(Err(e)) => {
                    let _ = tx2.send(ServerMsg::SystemMessage {
                        content: format!("\u{26a0}\u{fe0f} Failed to list providers: {e}"),
                    });
                }
                Err(_) => {
                    let _ = tx2.send(ServerMsg::SystemMessage {
                        content: "\u{26a0}\u{fe0f} Timed out listing providers".to_string(),
                    });
                }
            }
        });
        return Some(false);
    }

    if lowered == "/ollama-models" {
        match rpc_list_ollama_models_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                let models = payload.get("models")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if models.is_empty() {
                    show_command_info_popup(app, raw, "No Ollama models found.".to_string());
                } else {
                    let items: Vec<ListSelectorItem> = models.iter()
                        .filter_map(|m| m.as_str())
                        .map(|name| ListSelectorItem {
                            label: name.to_string(),
                            value: name.to_string(),
                        }).collect();
                    app.open_list_selector(ListSelectorState {
                        title: "Ollama Models".to_string(), items, selected_idx: 0,
                        command_template: "/switch ollama {}".to_string(),
                        action_hint_override: None,
                    });
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to list Ollama models: {e}"))),
        }
        return Some(false);
    }

    None
}
