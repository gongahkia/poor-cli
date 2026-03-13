use super::*;
fn popup_title_from_command(raw: &str) -> String {
    let token = raw
        .split_whitespace()
        .next()
        .unwrap_or("/info")
        .trim_start_matches('/')
        .trim();
    if token.is_empty() {
        return "Info".to_string();
    }
    token
        .split('-')
        .map(|segment| {
            let mut chars = segment.chars();
            match chars.next() {
                Some(first) => {
                    let mut titled = first.to_uppercase().collect::<String>();
                    titled.push_str(chars.as_str());
                    titled
                }
                None => String::new(),
            }
        })
        .collect::<Vec<_>>()
        .join(" ")
}

fn show_command_info_popup(app: &mut App, raw: &str, body: impl Into<String>) {
    app.open_info_popup(popup_title_from_command(raw), body.into());
}

fn resolve_close_slash_command(raw: &str) -> Option<(String, String, String)> {
    let command_end = raw
        .char_indices()
        .find(|(_, ch)| ch.is_whitespace())
        .map(|(index, _)| index)
        .unwrap_or(raw.len());
    if command_end == 0 {
        return None;
    }

    let typed_command = &raw[..command_end];
    if input::is_known_slash_command(typed_command) {
        return None;
    }

    let resolved = input::closest_slash_command(typed_command)?;
    let rewritten = format!("{resolved}{}", &raw[command_end..]);
    Some((rewritten, typed_command.to_string(), resolved.to_string()))
}

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

    if lowered == "/quit" || lowered == "/exit" {
        return true;
    }

    if lowered == "/help" {
        let help = "\
**Available Commands:**\n\n\
Type `@path/to/file` in any message to attach file context.\n\
Use quoted refs for spaces: `@\"docs/My File.md\"` or `@'docs/My File.md'`.\n\
\n\
**Session Management:**\n\
  /help                Show this help message\n\
  /onboarding ...      Start interactive onboarding (`next`, `prev`, `<step>`, `exit`)\n\
  /quit, /exit         Exit poor-cli and print session summary\n\
  /clear               Clear conversation history\n\
  /clear-output        Clear visible output, keep backend history\n\
  /history [N]         Show recent session messages\n\
  /sessions            List recent sessions\n\
  /new-session         Start a fresh session\n\
  /compact             Manage context window (compact/compress/handoff)\n\
  /queue ...           Manage prompt queue (`add|list|clear|drop`)\n\
  /export [format]     Export active session (json|md|txt)\n\
  /retry               Retry your last message\n\
  /search <term>       Search messages in this session\n\
  /edit-last           Put last message back into input\n\n\
**Checkpoints & Undo:**\n\
  /checkpoints         List checkpoints\n\
  /checkpoint          Create manual checkpoint\n\
  /save                Quick checkpoint alias\n\
  /rewind [id|last]    Restore checkpoint by id (default: last)\n\
  /restore             Restore latest checkpoint\n\
  /undo                Restore latest checkpoint (alias)\n\
  /diff <f1> <f2>      Compare two files\n\n\
**Provider Management:**\n\
  /provider            Show current provider capabilities\n\
  /providers           List available providers\n\
  /switch              Switch provider/model\n\
  /api-key             Show or set provider API keys\n\
  /model-info          Show provider-specific model notes\n\
  /permission-mode [mode]  Show or set backend permission mode\n\n\
**Configuration:**\n\
  /config              Show backend config snapshot\n\
  /settings            List editable config settings\n\
  /toggle <key>        Toggle a boolean config option\n\
  /set <key> <value>   Set a config option value\n\
  /theme [dark|light]  Show or set UI + code-block theme\n\
  /broke               Set response mode to terse, token-minimal output\n\
  /my-treat            Set response mode to rich, comprehensive output\n\
  /verbose             Toggle verbose logging\n\
  /plan-mode           Toggle plan mode\n\n\
**Git Integration:**\n\
  /commit              Generate commit message from staged diff\n\
  /review [file]       Review a file or staged diff\n\n\
**Code Tools:**\n\
  /test <file>         Generate tests for a file\n\
  /fix-failures [cmd]  Analyze latest (or fresh) test/lint failures\n\
  /explain-diff [file] Explain behavior/risk/test gaps in git diff\n\
  /image <path>        Queue image for next prompt\n\
  /watch <dir>         Watch directory and analyze changes\n\
  /unwatch             Stop active watch mode\n\
  /tools               List backend tool declarations\n\
  /cost                Show token and estimated cost usage\n\n\
**Context Files:**\n\
  /add <path>          Pin file/directory as persistent context\n\
  /drop <path>         Remove pinned context file\n\
  /files               List currently pinned context files\n\
  /clear-files         Remove all pinned context files\n\n\
**Prompt Library:**\n\
  /save-prompt <name> <text>  Save reusable prompt text immediately\n\
  /save-prompt <name>         Capture next input as prompt text\n\
  /use <name>                 Load and send saved prompt\n\
  /prompts                    List saved prompts\n\n\
**Utilities:**\n\
  !<command> [| question]  Run local bash and optionally ask about output\n\
  /doctor              Run environment/provider/service diagnostics\n\
  /bootstrap           Detect project type and show solo quickstart\n\
  /focus ...           Manage persistent focus goal (`start|status|done`)\n\
  /resume              Summarize last session + branch/checkpoint state\n\
  /workspace-map [path] Build repository file/entrypoint map\n\
  /context-budget [tokens] Rank and preview auto-selected context files\n\
  /autopilot ...       Toggle bounded autonomous execution mode\n\
  /qa ...              Background incremental QA watch (`start|stop|status`)\n\
  /profile ...         Apply execution profile (`speed|safe|deep-review`)\n\
  /tasks ...           Manage local task board (`add|done|drop|clear`)\n\
  /copy                Copy last assistant response to clipboard\n\
  /onboarding ...      Guided walkthrough of core commands\n\
  /pair                Start pair session (host) or join with invite code\n\
  /pair <invite-code>  Join a pair session using invite code\n\
  /pass                Hand driver role to next navigator\n\
  /pass @name          Hand driver role to specific person\n\
  /suggest <text>      Send suggestion to driver (navigator)\n\
  /leave               Disconnect from pair session\n\
  /who [room]          Show connected users and roles\n\
  /host-server ...     Start/share/manage host session (advanced)\n\
  /kick <connection-id> [room]  Kick member in current/target multiplayer room\n\
  /members [room]      Alias for /who\n\
  /host-server share [viewer|prompter] [room]  Print role-specific join payloads\n\
  /host-server members [room]               List connected room members\n\
  /host-server kick <connection-id> [room]  Remove a connected member\n\
  /host-server role <id> <viewer|prompter> [room]  Change member role\n\
  /host-server lobby <on|off> [room]        Toggle lobby approval mode\n\
  /host-server approve <id> [room]           Approve pending member\n\
  /host-server deny <id> [room]              Deny pending member\n\
  /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]  Rotate invite token\n\
  /host-server revoke <token|id> [room]      Revoke token or disconnect member\n\
  /host-server handoff <id> [room]           Transfer prompter role\n\
  /host-server preset <pairing|mob|review> [room]  Apply room collaboration preset\n\
  /host-server activity [room] [limit] [event-type]  Show room activity log\n\
  /join-server <code>  Join host using invite code or url/room/token\n\
  /join-server         Launch interactive join wizard\n\
  /service ...         Manage local background services (start/stop/status/logs)\n\
  /ollama ...          Convenience wrapper for Ollama lifecycle/model commands\n\
  /run <command>       Run shell command through backend\n\
  /read <file>         Read a file from backend\n\
  /pwd                 Show current working directory\n\
  /ls [path]           List files (default: current directory)\n\
  /status              Show quick session status";
        show_command_info_popup(app, raw, help);
        return false;
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
            return false;
        }

        if subcommand.is_empty()
            || subcommand == "start"
            || subcommand == "begin"
            || subcommand == "restart"
        {
            app.onboarding_active = true;
            app.onboarding_step = 0;
            show_command_info_popup(
                app,
                raw,
                format!(
                    "**Interactive onboarding started.**\n\n{}",
                    format_onboarding_step(app.onboarding_step)
                ),
            );
            return false;
        }

        if subcommand == "help" {
            show_command_info_popup(app, raw, onboarding_usage_text().to_string());
            return false;
        }

        if subcommand == "exit" || subcommand == "done" || subcommand == "quit" {
            app.onboarding_active = false;
            app.onboarding_step = 0;
            show_command_info_popup(
                app,
                raw,
                "Onboarding ended.\nRun `/onboarding` anytime to start again.".to_string(),
            );
            return false;
        }

        if subcommand == "show" || subcommand == "repeat" || subcommand == "resume" {
            if !app.onboarding_active {
                app.onboarding_active = true;
                app.onboarding_step = 0;
            }
            show_command_info_popup(app, raw, format_onboarding_step(app.onboarding_step));
            return false;
        }

        if subcommand == "next" {
            if !app.onboarding_active {
                app.onboarding_active = true;
                app.onboarding_step = 0;
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "No active onboarding session found; started at step 1.\n\n{}",
                        format_onboarding_step(app.onboarding_step)
                    ),
                );
                return false;
            }

            if app.onboarding_step + 1 >= total_steps {
                show_command_info_popup(
                    app,
                    raw,
                    "You are already at the last onboarding step.\nUse `/onboarding exit` to end the onboarding session.".to_string(),
                );
                return false;
            }

            app.onboarding_step += 1;
            show_command_info_popup(app, raw, format_onboarding_step(app.onboarding_step));
            return false;
        }

        if subcommand == "prev" || subcommand == "previous" || subcommand == "back" {
            if !app.onboarding_active {
                app.onboarding_active = true;
                app.onboarding_step = 0;
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "No active onboarding session found; started at step 1.\n\n{}",
                        format_onboarding_step(app.onboarding_step)
                    ),
                );
                return false;
            }

            if app.onboarding_step == 0 {
                show_command_info_popup(
                    app,
                    raw,
                    "You are already at the first onboarding step.".to_string(),
                );
                return false;
            }

            app.onboarding_step -= 1;
            show_command_info_popup(app, raw, format_onboarding_step(app.onboarding_step));
            return false;
        }

        if let Ok(step_number) = subcommand.parse::<usize>() {
            if step_number == 0 || step_number > total_steps {
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "Step must be between 1 and {total_steps}.\n{}",
                        onboarding_usage_text()
                    ),
                );
                return false;
            }
            app.onboarding_active = true;
            app.onboarding_step = step_number - 1;
            show_command_info_popup(app, raw, format_onboarding_step(app.onboarding_step));
            return false;
        }

        show_command_info_popup(app, raw, onboarding_usage_text().to_string());
        return false;
    }

    if lowered == "/queue" || lowered.starts_with("/queue ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let sub = args.get(1).copied().unwrap_or("list");
        match sub {
            "add" | "a" => {
                if let Some(text) = args.get(2) {
                    let text = text.trim();
                    if text.is_empty() {
                        app.set_status("Usage: /queue add <prompt text>");
                    } else {
                        app.prompt_queue.push_back(text.to_string());
                        app.set_status(format!("Queued ({} total)", app.prompt_queue.len()));
                    }
                } else {
                    app.set_status("Usage: /queue add <prompt text>");
                }
            }
            "list" | "ls" | "l" => {
                if app.prompt_queue.is_empty() {
                    show_command_info_popup(app, raw, "Prompt queue is empty.");
                } else {
                    let mut lines = vec![format!("**Prompt Queue** ({} items)\n", app.prompt_queue.len())];
                    for (i, prompt) in app.prompt_queue.iter().enumerate() {
                        let preview = if prompt.len() > 60 { &prompt[..60] } else { prompt };
                        lines.push(format!("  {}. {}", i + 1, preview));
                    }
                    show_command_info_popup(app, raw, lines.join("\n"));
                }
            }
            "clear" | "c" => {
                let count = app.prompt_queue.len();
                app.prompt_queue.clear();
                app.set_status(format!("Cleared {count} queued prompt(s)"));
            }
            "drop" | "d" => {
                if let Some(idx_str) = args.get(2) {
                    if let Ok(idx) = idx_str.trim().parse::<usize>() {
                        if idx >= 1 && idx <= app.prompt_queue.len() {
                            app.prompt_queue.remove(idx - 1);
                            app.set_status(format!("Dropped item {idx} ({} remaining)", app.prompt_queue.len()));
                        } else {
                            app.set_status(format!("Invalid index (1-{})", app.prompt_queue.len()));
                        }
                    } else {
                        app.set_status("Usage: /queue drop <number>");
                    }
                } else if !app.prompt_queue.is_empty() {
                    app.prompt_queue.pop_back();
                    app.set_status(format!("Dropped last ({} remaining)", app.prompt_queue.len()));
                } else {
                    app.set_status("Queue is empty");
                }
            }
            _ => {
                show_command_info_popup(app, raw,
                    "**Queue Commands**\n\n\
                    /queue add <text>   Add prompt to queue\n\
                    /queue list         Show queued prompts\n\
                    /queue clear        Clear all queued prompts\n\
                    /queue drop [N]     Drop item N (or last)");
            }
        }
        return false;
    }

    if lowered == "/compact" {
        app.compact_select_idx = 0;
        app.mode = AppMode::CompactSelect;
        return false;
    }

    if lowered == "/clear" {
        app.messages.clear();
        app.add_welcome();
        app.last_user_message = None;
        app.onboarding_active = false;
        app.onboarding_step = 0;
        app.join_wizard_active = false;
        app.join_wizard_step = 0;
        app.join_wizard_url.clear();
        app.join_wizard_room.clear();
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
        return false;
    }

    if lowered == "/clear-output" {
        app.messages.clear();
        app.add_welcome();
        app.set_status("Output cleared");
        return false;
    }

    if lowered == "/new-session" {
        app.messages.clear();
        app.add_welcome();
        app.last_user_message = None;
        app.onboarding_active = false;
        app.onboarding_step = 0;
        app.join_wizard_active = false;
        app.join_wizard_step = 0;
        app.join_wizard_url.clear();
        app.join_wizard_room.clear();
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
        return false;
    }

    if lowered == "/broke" {
        app.response_mode = ResponseMode::Poor;
        show_command_info_popup(
            app,
            raw,
            "Response mode set to **poor**.\nReplies will be terse and token-minimal.".to_string(),
        );
        return false;
    }

    if lowered == "/my-treat" {
        app.response_mode = ResponseMode::Rich;
        show_command_info_popup(
            app,
            raw,
            "Response mode set to **rich**.\nReplies will prioritize completeness and quality."
                .to_string(),
        );
        return false;
    }

    if lowered == "/provider" {
        match rpc_get_provider_info_blocking(rpc_cmd_tx) {
            Ok(value) => {
                let provider = value
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or(app.provider_name.as_str());
                let model = value
                    .get("model")
                    .and_then(|v| v.as_str())
                    .unwrap_or(app.model_name.as_str());
                let caps = value.get("capabilities").unwrap_or(&Value::Null);
                let streaming = bool_icon(caps.get("streaming").and_then(|v| v.as_bool()));
                let function_calling =
                    bool_icon(caps.get("function_calling").and_then(|v| v.as_bool()));
                let vision = bool_icon(caps.get("vision").and_then(|v| v.as_bool()));

                let info = format!(
                    "**Current Provider:** {provider}\n\
**Model:** {model}\n\n\
**Capabilities:**\n\
  Streaming: {streaming}\n\
  Function Calling: {function_calling}\n\
  Vision: {vision}"
                );
                show_command_info_popup(app, raw, info);
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch provider info: {e}"
            ))),
        }
        return false;
    }

    if lowered == "/api-key" {
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
                    return false;
                }

                let mut names = providers.keys().cloned().collect::<Vec<_>>();
                names.sort();

                let mut lines = vec!["**API Key Status**".to_string(), String::new()];

                for provider in names {
                    let Some(entry) = providers.get(&provider) else {
                        continue;
                    };
                    let configured = entry
                        .get("configured")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let status_icon = if configured { "✓" } else { "✗" };
                    let active = if entry
                        .get("active")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false)
                    {
                        " (active)"
                    } else {
                        ""
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
                lines.push("Set or rotate with `/api-key <provider> <api-key>`".to_string());
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch API key status: {e}"
            ))),
        }
        return false;
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
                "Usage: /api-key <provider> <api-key>\nInspect status only: /api-key".to_string(),
            );
            return false;
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
        return false;
    }

    if lowered == "/providers" {
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        let _ = rpc_cmd_tx.send(RpcCommand::ListProviders { reply: reply_tx });
        match reply_rx.recv_timeout(Duration::from_secs(15)) {
            Ok(Ok(providers)) => {
                let mut info = "**Available Providers:**\n\n".to_string();
                for p in &providers {
                    let status = if p.available { "✓" } else { "✗" };
                    let local = if p.name == "ollama" { " [local]" } else { "" };
                    let models = if p.models.is_empty() {
                        String::new()
                    } else {
                        format!(" ({})", p.models.join(", "))
                    };
                    info.push_str(&format!("  {status} **{}**{local}{models}\n", p.name));
                }
                info.push_str("\nUse /switch to change provider/model");
                show_command_info_popup(app, raw, info);
            }
            Ok(Err(e)) => {
                app.push_message(ChatMessage::error(format!("Failed to list providers: {e}")))
            }
            Err(_) => app.push_message(ChatMessage::error("Failed to list providers".to_string())),
        }
        return false;
    }

    if lowered == "/switch" {
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        let _ = rpc_cmd_tx.send(RpcCommand::ListProviders { reply: reply_tx });
        let tx2 = tx.clone();
        thread::spawn(move || {
            if let Ok(Ok(providers)) = reply_rx.recv() {
                let _ = tx2.send(ServerMsg::Providers {
                    providers: providers
                        .into_iter()
                        .map(|p| ProviderEntry {
                            name: p.name,
                            available: p.available,
                            models: p.models,
                        })
                        .collect(),
                });
            }
        });
        return false;
    }

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
                        .unwrap_or(app.provider_name.as_str()),
                    cfg.get("model")
                        .and_then(|v| v.as_str())
                        .unwrap_or(app.model_name.as_str()),
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
        return false;
    }

    if lowered == "/settings" {
        match rpc_list_config_options_blocking(rpc_cmd_tx) {
            Ok(payload) => {
                let options = payload
                    .get("options")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                let config_file = payload
                    .get("configFile")
                    .and_then(|v| v.as_str())
                    .unwrap_or("(unknown)");

                let mut lines = vec![
                    format!("**Editable Settings** ({})", options.len()),
                    format!("Config file: `{config_file}`"),
                    String::new(),
                    "Quick actions: `/toggle <key>` or `/set <key> <value>`".to_string(),
                    String::new(),
                ];

                for opt in options.iter().take(80) {
                    let key = opt
                        .get("path")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let typ = opt
                        .get("type")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let value = opt.get("value").cloned().unwrap_or(Value::Null);
                    let is_bool = opt
                        .get("isBoolean")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let bool_hint = if is_bool { " (toggleable)" } else { "" };
                    lines.push(format!(
                        "- `{key}` [{typ}{bool_hint}] = `{}`",
                        format_value_for_display(&value)
                    ));
                }
                if options.len() > 80 {
                    lines.push(format!(
                        "\n... and {} more settings. Narrow with `/set <key> <value>`.",
                        options.len() - 80
                    ));
                }

                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to load settings: {e}"))),
        }
        return false;
    }

    if lowered.starts_with("/toggle ") {
        let key = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if key.is_empty() {
            show_command_info_popup(app, raw, "Usage: /toggle <key>".to_string());
            return false;
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
        return false;
    }

    if lowered.starts_with("/set ") {
        let mut parts = raw.splitn(3, ' ');
        let _ = parts.next();
        let key = parts.next().unwrap_or("").trim();
        let raw_value = parts.next().unwrap_or("").trim();

        if key.is_empty() || raw_value.is_empty() {
            show_command_info_popup(app, raw, "Usage: /set <key> <value>".to_string());
            return false;
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
        return false;
    }

    if lowered == "/theme" {
        show_command_info_popup(
            app,
            raw,
            format!(
                "Current theme: **{}**\nUse `/theme dark` or `/theme light`.",
                app.theme_mode.as_str()
            ),
        );
        return false;
    }

    if lowered.starts_with("/theme ") {
        let raw_mode = raw.split_whitespace().nth(1).unwrap_or("");
        let Some(theme_mode) = ThemeMode::from_user_input(raw_mode) else {
            app.push_message(ChatMessage::error(
                "Invalid theme mode. Use one of: dark, light.".to_string(),
            ));
            return false;
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
        return false;
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
        return false;
    }

    if lowered == "/plan-mode" {
        match rpc_toggle_config_blocking(rpc_cmd_tx, "plan_mode.enabled") {
            Ok(result) => {
                let enabled = result
                    .get("value")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(true);
                let message = if enabled {
                    "Plan mode enabled (preview before execution)"
                } else {
                    "Plan mode disabled (direct execution)"
                };
                show_command_info_popup(app, raw, message.to_string());
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to toggle plan mode: {e}"
            ))),
        }
        return false;
    }

    if lowered.starts_with("/permission-mode") {
        let maybe_mode = raw.split_whitespace().nth(1);
        if let Some(mode) = maybe_mode {
            let normalized = mode.trim().to_lowercase();
            if !matches!(
                normalized.as_str(),
                "prompt" | "auto-safe" | "danger-full-access"
            ) {
                app.push_message(ChatMessage::error(
                    "Invalid mode. Use one of: prompt, auto-safe, danger-full-access".to_string(),
                ));
                return false;
            }

            match rpc_set_config_blocking(
                rpc_cmd_tx,
                "security.permission_mode",
                Value::String(normalized.clone()),
            ) {
                Ok(_) => show_command_info_popup(
                    app,
                    raw,
                    format!("Permission mode set to **{normalized}**"),
                ),
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to set permission mode: {e}"
                ))),
            }
            return false;
        }

        match rpc_get_config_blocking(rpc_cmd_tx) {
            Ok(cfg) => {
                let mode = cfg
                    .get("permissionMode")
                    .and_then(|v| v.as_str())
                    .unwrap_or("prompt");
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "Current permission mode: **{mode}**\nAvailable: prompt, auto-safe, danger-full-access\nSet with: `/permission-mode <mode>`"
                    ),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch permission mode: {e}"
            ))),
        }
        return false;
    }

    if lowered == "/model-info" {
        match rpc_get_provider_info_blocking(rpc_cmd_tx) {
            Ok(value) => {
                let provider = value
                    .get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or(app.provider_name.as_str());
                let model = value
                    .get("model")
                    .and_then(|v| v.as_str())
                    .unwrap_or(app.model_name.as_str());
                let caps = value.get("capabilities").unwrap_or(&Value::Null);
                let streaming = bool_icon(caps.get("streaming").and_then(|v| v.as_bool()));
                let function_calling =
                    bool_icon(caps.get("function_calling").and_then(|v| v.as_bool()));
                let vision = bool_icon(caps.get("vision").and_then(|v| v.as_bool()));
                let max_context = caps
                    .get("max_context_tokens")
                    .and_then(|v| v.as_u64())
                    .map(|v| v.to_string())
                    .unwrap_or_else(|| "unknown".to_string());

                let provider_notes = match provider {
                    "gemini" => "Gemini models offer a free tier, fast inference, and strong code generation.",
                    "openai" => "OpenAI models provide strong reasoning and broad tool-calling support.",
                    "anthropic" | "claude" => "Anthropic models are strong at analysis and long-form reasoning.",
                    "ollama" => "Ollama runs models locally with no API costs and better data locality.",
                    _ => "No provider-specific notes available.",
                };

                let info = format!(
                    "**Current Model Configuration**\n\n\
Provider: {provider}\n\
Model: {model}\n\n\
**Capabilities**\n\
Streaming: {streaming}\n\
Function Calling: {function_calling}\n\
Vision: {vision}\n\
Context Window: {max_context} tokens\n\n\
**Notes**\n\
{provider_notes}"
                );
                show_command_info_popup(app, raw, info);
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch model information: {e}"
            ))),
        }
        return false;
    }

    if lowered == "/tools" {
        match rpc_get_tools_blocking(rpc_cmd_tx) {
            Ok(value) => {
                let tools = value
                    .get("tools")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();

                if tools.is_empty() {
                    show_command_info_popup(
                        app,
                        raw,
                        "No tool declarations returned by backend.".to_string(),
                    );
                    return false;
                }

                let mut lines = Vec::new();
                lines.push("**Available Tools:**".to_string());
                lines.push(String::new());

                for tool in tools {
                    let name = tool
                        .get("name")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown-tool");
                    let desc = tool
                        .get("description")
                        .and_then(|v| v.as_str())
                        .unwrap_or("No description");
                    lines.push(format!("- **{name}**: {desc}"));
                }

                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch tools: {e}"))),
        }
        return false;
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
                    return false;
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
        return false;
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
                    return false;
                }

                let mut lines = vec!["**Recent Sessions:**".to_string(), String::new()];
                for session in sessions {
                    let session_id = session
                        .get("sessionId")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let started = session
                        .get("startedAt")
                        .and_then(|v| v.as_str())
                        .unwrap_or("-");
                    let message_count = session
                        .get("messageCount")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    let active = session
                        .get("isActive")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let marker = if active { " (active)" } else { "" };
                    lines.push(format!(
                        "- `{session_id}`{marker} • {started} • {message_count} message(s)"
                    ));
                }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to list sessions: {e}"))),
        }
        return false;
    }

    if lowered == "/retry" {
        if let Some(last) = app.last_user_message.clone() {
            send_chat_request(
                app,
                tx,
                rpc_cmd_tx,
                cancel_token,
                last.clone(),
                format!("/retry {last}"),
                launch.session_log.as_ref(),
            );
        } else {
            show_command_info_popup(app, raw, "No previous request to retry.".to_string());
        }
        return false;
    }

    if lowered.starts_with("/search") {
        let term = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if term.is_empty() {
            show_command_info_popup(app, raw, "Usage: /search <term>".to_string());
            return false;
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
                    return false;
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
        return false;
    }

    if lowered == "/edit-last" {
        if let Some(last) = app.last_user_message.clone() {
            app.input_buffer = last;
            app.input_cursor = app.input_buffer.len();
            app.mode = if app.input_buffer.starts_with('/') {
                poor_cli_tui::app::AppMode::Command
            } else {
                poor_cli_tui::app::AppMode::Normal
            };
            app.set_status("Loaded last message into input");
        } else {
            show_command_info_popup(app, raw, "No previous request to edit.".to_string());
        }
        return false;
    }

    if lowered.starts_with("/add ") {
        let spec = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if spec.is_empty() {
            show_command_info_popup(app, raw, "Usage: /add <path>".to_string());
            return false;
        }

        let resolved = resolve_context_spec(app, spec);
        if resolved.is_empty() {
            app.push_message(ChatMessage::error(format!("No files matched: {spec}")));
            return false;
        }

        let mut added = 0usize;
        for path in resolved {
            let display = display_project_path(app, &path);
            if !app.pinned_context_files.contains(&display) {
                app.pinned_context_files.push(display);
                added += 1;
            }
        }
        app.pinned_context_files.sort();
        app.pinned_context_files.dedup();

        if added == 0 {
            show_command_info_popup(
                app,
                raw,
                "All matched files were already pinned.".to_string(),
            );
        } else {
            app.set_status(format!(
                "Pinned {added} context file(s); total: {}",
                app.pinned_context_files.len()
            ));
        }
        return false;
    }

    if lowered.starts_with("/drop ") {
        let spec = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if spec.is_empty() {
            show_command_info_popup(app, raw, "Usage: /drop <path>".to_string());
            return false;
        }

        let before = app.pinned_context_files.len();
        app.pinned_context_files
            .retain(|p| p != spec && !p.ends_with(&format!("/{spec}")));
        let removed = before.saturating_sub(app.pinned_context_files.len());

        if removed == 0 {
            show_command_info_popup(app, raw, format!("No pinned file matched: {spec}"));
        } else {
            app.set_status(format!(
                "Removed {removed} pinned file(s); total: {}",
                app.pinned_context_files.len()
            ));
        }
        return false;
    }

    if lowered == "/files" {
        if app.pinned_context_files.is_empty() {
            show_command_info_popup(
                app,
                raw,
                "No pinned context files.\nUse /add <path> or @path in a prompt.".to_string(),
            );
        } else {
            let mut lines = vec![
                format!(
                    "**Pinned Context Files ({}):**",
                    app.pinned_context_files.len()
                ),
                String::new(),
            ];
            for file in &app.pinned_context_files {
                lines.push(format!("- {file}"));
            }
            show_command_info_popup(app, raw, lines.join("\n"));
        }
        return false;
    }

    if lowered == "/clear-files" {
        let removed = app.pinned_context_files.len();
        app.pinned_context_files.clear();
        app.set_status(format!("Cleared {removed} pinned context file(s)"));
        return false;
    }

    if lowered == "/doctor" {
        let mut lines = vec!["**poor-cli Doctor**".to_string(), String::new()];

        match rpc_get_config_blocking(rpc_cmd_tx) {
            Ok(cfg) => {
                let mode = cfg
                    .get("permissionMode")
                    .and_then(|v| v.as_str())
                    .unwrap_or("unknown");
                lines.push(format!("- Permission mode: `{mode}`"));
                if mode == "danger-full-access" {
                    lines.push("- Warning: running in `danger-full-access`.".to_string());
                }
            }
            Err(e) => lines.push(format!("- Permission mode check failed: {e}")),
        }

        match rpc_get_api_key_status_blocking(rpc_cmd_tx, None) {
            Ok(payload) => {
                let providers = payload
                    .get("providers")
                    .and_then(|v| v.as_object())
                    .cloned()
                    .unwrap_or_default();
                let configured = providers
                    .values()
                    .filter(|entry| {
                        entry
                            .get("configured")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false)
                    })
                    .count();
                lines.push(format!(
                    "- API keys configured: {configured}/{} provider(s)",
                    providers.len()
                ));
            }
            Err(e) => lines.push(format!("- API key status check failed: {e}")),
        }

        match rpc_get_service_status_blocking(rpc_cmd_tx, None) {
            Ok(payload) => {
                let services = payload
                    .get("services")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                let running = services
                    .iter()
                    .filter(|entry| {
                        entry
                            .get("running")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false)
                    })
                    .count();
                lines.push(format!(
                    "- Managed services running: {running}/{}",
                    services.len()
                ));
            }
            Err(e) => lines.push(format!("- Service check failed: {e}")),
        }

        match rpc_execute_command_with_timeout_blocking(
            rpc_cmd_tx,
            "git rev-parse --abbrev-ref HEAD",
            Some(15),
            20,
        ) {
            Ok(branch) => lines.push(format!("- Git branch: `{}`", first_line(&branch))),
            Err(_) => lines.push("- Git branch: unavailable (not a git repo?)".to_string()),
        }

        lines.push(String::new());
        lines.push("If anything is degraded: check `/api-key`, `/permission-mode`, `/service status`, and `/status`.".to_string());
        show_command_info_popup(app, raw, lines.join("\n"));
        return false;
    }

    if lowered == "/bootstrap" || lowered.starts_with("/bootstrap ") {
        let root_raw = raw
            .splitn(2, ' ')
            .nth(1)
            .map(str::trim)
            .filter(|value| !value.is_empty());
        let root = root_raw
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(&app.cwd));
        show_command_info_popup(app, raw, format_bootstrap_report(&root));
        return false;
    }

    if lowered == "/profile" || lowered.starts_with("/profile ") {
        let selected = raw
            .split_whitespace()
            .nth(1)
            .map(|value| value.trim().to_ascii_lowercase())
            .unwrap_or_else(|| "status".to_string());
        if selected == "status" {
            show_command_info_popup(
                app,
                raw,
                format!(
                    "**Execution Profile**\n- Active: `{}`\n- Response mode: `{}`\n- Context budget: {} tokens\n\nAvailable profiles:\n- `speed`: smaller context, terse output, faster loop\n- `safe`: balanced defaults, review-oriented safety\n- `deep-review`: larger context, richer analysis depth\n\nSet with `/profile <name>`",
                    app.execution_profile,
                    app.response_mode.as_str(),
                    app.context_budget_tokens
                ),
            );
            return false;
        }

        match apply_execution_profile(app, rpc_cmd_tx, &selected, true) {
            Ok(summary) => {
                refresh_context_budget_state(app);
                show_command_info_popup(app, raw, summary);
            }
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return false;
    }

    if lowered == "/focus" || lowered.starts_with("/focus ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("status")
            .trim()
            .to_ascii_lowercase();

        if subcommand == "status" {
            match load_focus_state(app) {
                Ok(Some(state)) => {
                    show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "**Focus Status**\n- Goal: {}\n- Constraints: {}\n- Definition of done: {}\n- Started: {}\n- Completed: {}",
                            if state.goal.is_empty() { "(none)" } else { &state.goal },
                            if state.constraints.is_empty() {
                                "(none)"
                            } else {
                                &state.constraints
                            },
                            if state.definition_of_done.is_empty() {
                                "(none)"
                            } else {
                                &state.definition_of_done
                            },
                            if state.started_at.is_empty() {
                                "(unknown)"
                            } else {
                                &state.started_at
                            },
                            if state.completed { "yes" } else { "no" }
                        ),
                    );
                }
                Ok(None) => show_command_info_popup(
                    app,
                    raw,
                    "No active focus.\nUse `/focus start <goal> [|| constraints || definition-of-done]`."
                        .to_string(),
                ),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return false;
        }

        if subcommand == "start" {
            let payload = raw.splitn(3, ' ').nth(2).map(str::trim).unwrap_or("");
            if payload.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /focus start <goal> [|| constraints || definition-of-done]".to_string(),
                );
                return false;
            }
            let parts = payload.split("||").map(str::trim).collect::<Vec<_>>();
            let state = FocusState {
                goal: parts.first().copied().unwrap_or("").to_string(),
                constraints: parts.get(1).copied().unwrap_or("").to_string(),
                definition_of_done: parts.get(2).copied().unwrap_or("").to_string(),
                started_at: format!("{}", unix_ts_millis()),
                completed: false,
            };
            match save_focus_state(app, &state) {
                Ok(()) => show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "Focus started.\n- Goal: {}\n- Constraints: {}\n- Definition of done: {}",
                        if state.goal.is_empty() {
                            "(none)"
                        } else {
                            &state.goal
                        },
                        if state.constraints.is_empty() {
                            "(none)"
                        } else {
                            &state.constraints
                        },
                        if state.definition_of_done.is_empty() {
                            "(none)"
                        } else {
                            &state.definition_of_done
                        }
                    ),
                ),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return false;
        }

        if subcommand == "done" {
            match load_focus_state(app) {
                Ok(Some(mut state)) => {
                    state.completed = true;
                    match save_focus_state(app, &state) {
                        Ok(()) => {
                            show_command_info_popup(app, raw, "Focus marked complete.".to_string())
                        }
                        Err(e) => app.push_message(ChatMessage::error(e)),
                    }
                }
                Ok(None) => {
                    show_command_info_popup(app, raw, "No active focus to complete.".to_string())
                }
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return false;
        }

        show_command_info_popup(app, raw, "Usage: /focus start|status|done".to_string());
        return false;
    }

    if lowered == "/resume" {
        let mut lines = vec!["**Resume Snapshot**".to_string(), String::new()];
        if let Ok(Some(state)) = load_focus_state(app) {
            if !state.goal.is_empty() {
                lines.push(format!("- Focus goal: {}", state.goal));
            }
            if !state.completed {
                lines.push("- Focus status: active".to_string());
            }
        }

        match rpc_list_sessions_blocking(rpc_cmd_tx, 1) {
            Ok(payload) => {
                let sessions = payload
                    .get("sessions")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if let Some(first) = sessions.first() {
                    let session_id = first
                        .get("sessionId")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(unknown)");
                    let model = first
                        .get("model")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(unknown)");
                    let message_count = first
                        .get("messageCount")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    lines.push(format!(
                        "- Last session: `{session_id}` on `{model}` ({message_count} messages)"
                    ));
                }
            }
            Err(e) => lines.push(format!("- Session lookup failed: {e}")),
        }

        match rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, "git status -sb", Some(20), 25)
        {
            Ok(status) => lines.push(format!("- Git status: `{}`", first_line(&status))),
            Err(e) => lines.push(format!("- Git status unavailable: {e}")),
        }

        match rpc_list_checkpoints_blocking(rpc_cmd_tx, 5) {
            Ok(payload) => {
                let checkpoints = payload
                    .get("checkpoints")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                lines.push(format!("- Recent checkpoints: {}", checkpoints.len()));
            }
            Err(e) => lines.push(format!("- Checkpoint lookup failed: {e}")),
        }

        lines.push(String::new());
        lines.push(
            "Suggested next steps: `/status`, `/history 10`, `/checkpoints`, `/review`."
                .to_string(),
        );
        show_command_info_popup(app, raw, lines.join("\n"));
        return false;
    }

    if lowered == "/context-budget" || lowered.starts_with("/context-budget ") {
        if let Some(raw_budget) = raw.split_whitespace().nth(1) {
            match raw_budget.parse::<usize>() {
                Ok(value) => {
                    app.context_budget_tokens = value.clamp(1000, 20000);
                }
                Err(_) => {
                    show_command_info_popup(
                        app,
                        raw,
                        "Usage: /context-budget [token-budget]".to_string(),
                    );
                    return false;
                }
            }
        }

        refresh_context_budget_state(app);
        show_command_info_popup(app, raw, format_context_budget_report(app));
        return false;
    }

    if lowered == "/workspace-map" || lowered.starts_with("/workspace-map ") {
        let root_raw = raw
            .splitn(2, ' ')
            .nth(1)
            .map(str::trim)
            .filter(|value| !value.is_empty());
        let root = root_raw
            .map(PathBuf::from)
            .unwrap_or_else(|| PathBuf::from(&app.cwd));
        let files = collect_directory_files(&root, 4000);
        if files.is_empty() {
            show_command_info_popup(app, raw, "No files found for workspace map.".to_string());
            return false;
        }

        let mut ext_counts = HashMap::<String, usize>::new();
        let mut entrypoints = Vec::<String>::new();
        for file in &files {
            if let Some(ext) = file.extension().and_then(|v| v.to_str()) {
                *ext_counts.entry(ext.to_string()).or_insert(0) += 1;
            }
            if let Some(name) = file.file_name().and_then(|v| v.to_str()) {
                if matches!(
                    name,
                    "Cargo.toml"
                        | "pyproject.toml"
                        | "package.json"
                        | "Makefile"
                        | "main.rs"
                        | "main.py"
                ) {
                    entrypoints.push(file.to_string_lossy().to_string());
                }
            }
        }
        let mut ext_pairs = ext_counts.into_iter().collect::<Vec<_>>();
        ext_pairs.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
        let ext_summary = ext_pairs
            .into_iter()
            .take(8)
            .map(|(ext, count)| format!("{ext}:{count}"))
            .collect::<Vec<_>>()
            .join(", ");
        let mut lines = vec![
            format!("**Workspace Map:** `{}`", root.to_string_lossy()),
            format!("- Total files indexed: {}", files.len()),
            format!("- Top extensions: {ext_summary}"),
        ];
        if !entrypoints.is_empty() {
            lines.push("- Entrypoints:".to_string());
            for entry in entrypoints.into_iter().take(10) {
                lines.push(format!("  - `{entry}`"));
            }
        }
        show_command_info_popup(app, raw, lines.join("\n"));
        return false;
    }

    if lowered == "/autopilot" || lowered.starts_with("/autopilot ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("status")
            .trim()
            .to_ascii_lowercase();
        if subcommand == "status" {
            show_command_info_popup(
                app,
                raw,
                format!(
                    "Autopilot: {}\nIteration cap: {}",
                    if app.autopilot_enabled {
                        "enabled"
                    } else {
                        "disabled"
                    },
                    app.iteration_cap
                ),
            );
            return false;
        }
        if subcommand == "start" {
            let allow_risky = args
                .iter()
                .any(|value| value.trim().eq_ignore_ascii_case("--allow-risky"));
            if !allow_risky {
                if let Ok(cfg) = rpc_get_config_blocking(rpc_cmd_tx) {
                    let mode = cfg
                        .get("permissionMode")
                        .and_then(|value| value.as_str())
                        .unwrap_or("prompt");
                    if mode == "danger-full-access" {
                        show_command_info_popup(
                            app,
                            raw,
                            "Autopilot guardrail blocked start because permission mode is `danger-full-access`.\nUse `/permission-mode prompt` or rerun with `/autopilot start <cap> --allow-risky`."
                                .to_string(),
                        );
                        return false;
                    }
                }
            }
            let cap = args
                .get(2)
                .and_then(|raw| raw.parse::<u32>().ok())
                .unwrap_or_else(|| {
                    if app.execution_profile == "speed" {
                        30
                    } else if app.execution_profile == "deep-review" {
                        60
                    } else {
                        40
                    }
                })
                .clamp(5, 120);
            app.autopilot_enabled = true;
            app.iteration_cap = cap;
            show_command_info_popup(
                app,
                raw,
                format!("Autopilot enabled with iteration cap {cap}."),
            );
            return false;
        }
        if subcommand == "stop" {
            app.autopilot_enabled = false;
            app.iteration_cap = 25;
            show_command_info_popup(
                app,
                raw,
                "Autopilot disabled. Iteration cap reset to 25.".to_string(),
            );
            return false;
        }
        show_command_info_popup(
            app,
            raw,
            "Usage: /autopilot start [cap] [--allow-risky]\n       /autopilot stop\n       /autopilot status".to_string(),
        );
        return false;
    }

    if lowered == "/tasks" || lowered.starts_with("/tasks ") {
        let args: Vec<&str> = raw.splitn(3, ' ').collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("list")
            .trim()
            .to_ascii_lowercase();
        let mut tasks = match load_tasks(app) {
            Ok(tasks) => tasks,
            Err(e) => {
                app.push_message(ChatMessage::error(e));
                return false;
            }
        };

        if subcommand == "list" {
            if tasks.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "No tasks.\nUse `/tasks add <title>`.".to_string(),
                );
                return false;
            }
            let mut lines = vec![format!("**Tasks ({})**", tasks.len()), String::new()];
            tasks.sort_by_key(|task| task.id);
            for task in tasks {
                lines.push(format!(
                    "- [{}] #{} {}",
                    if task.done { "x" } else { " " },
                    task.id,
                    task.title
                ));
            }
            show_command_info_popup(app, raw, lines.join("\n"));
            return false;
        }

        if subcommand == "add" {
            let title = args.get(2).copied().unwrap_or("").trim();
            if title.is_empty() {
                show_command_info_popup(app, raw, "Usage: /tasks add <title>".to_string());
                return false;
            }
            let next_id = tasks.iter().map(|task| task.id).max().unwrap_or(0) + 1;
            tasks.push(TaskItem {
                id: next_id,
                title: title.to_string(),
                done: false,
                created_at: format!("{}", unix_ts_millis()),
            });
            if let Err(e) = save_tasks(app, &tasks) {
                app.push_message(ChatMessage::error(e));
                return false;
            }
            app.set_status(format!("Task #{next_id} added"));
            return false;
        }

        if subcommand == "done" {
            let id = args
                .get(2)
                .and_then(|raw| raw.trim().parse::<u64>().ok())
                .unwrap_or(0);
            if id == 0 {
                show_command_info_popup(app, raw, "Usage: /tasks done <id>".to_string());
                return false;
            }
            let mut found = false;
            for task in &mut tasks {
                if task.id == id {
                    task.done = true;
                    found = true;
                    break;
                }
            }
            if !found {
                show_command_info_popup(app, raw, format!("Task #{id} not found."));
                return false;
            }
            if let Err(e) = save_tasks(app, &tasks) {
                app.push_message(ChatMessage::error(e));
                return false;
            }
            app.set_status(format!("Task #{id} marked done"));
            return false;
        }

        if subcommand == "drop" {
            let id = args
                .get(2)
                .and_then(|raw| raw.trim().parse::<u64>().ok())
                .unwrap_or(0);
            if id == 0 {
                show_command_info_popup(app, raw, "Usage: /tasks drop <id>".to_string());
                return false;
            }
            let before = tasks.len();
            tasks.retain(|task| task.id != id);
            if tasks.len() == before {
                show_command_info_popup(app, raw, format!("Task #{id} not found."));
                return false;
            }
            if let Err(e) = save_tasks(app, &tasks) {
                app.push_message(ChatMessage::error(e));
                return false;
            }
            app.set_status(format!("Task #{id} removed"));
            return false;
        }

        if subcommand == "clear" {
            if let Err(e) = save_tasks(app, &[]) {
                app.push_message(ChatMessage::error(e));
                return false;
            }
            app.set_status("Cleared task list");
            return false;
        }

        show_command_info_popup(
            app,
            raw,
            "Usage: /tasks [list]\n       /tasks add <title>\n       /tasks done <id>\n       /tasks drop <id>\n       /tasks clear".to_string(),
        );
        return false;
    }

    if lowered == "/explain-diff" || lowered.starts_with("/explain-diff ") {
        let target = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        let command = if target.is_empty() {
            "git diff".to_string()
        } else {
            format!("git diff -- {}", shell_escape_single_quotes(target))
        };
        match rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, &command, Some(60), 75) {
            Ok(diff) => {
                if diff.trim().is_empty() {
                    show_command_info_popup(app, raw, "No diff content found.".to_string());
                    return false;
                }
                let prompt = format!(
                    "Analyze this git diff and produce:\n1) behavior changes\n2) regression risks\n3) missing tests\n4) quick validation steps.\n\n```diff\n{}\n```",
                    truncate_block(&diff, 12000)
                );
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    apply_response_mode_to_user_input(app.response_mode, &prompt),
                    raw.to_string(),
                    launch.session_log.as_ref(),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to collect diff: {e}"))),
        }
        return false;
    }

    if lowered == "/fix-failures" || lowered.starts_with("/fix-failures ") {
        let command_hint = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        let failure_output = if !command_hint.is_empty() {
            match rpc_execute_command_with_timeout_blocking(
                rpc_cmd_tx,
                command_hint,
                Some(300),
                320,
            ) {
                Ok(output) => {
                    app.last_command_output = Some(output.clone());
                    output
                }
                Err(e) => {
                    app.push_message(ChatMessage::error(format!(
                        "Failed to run `{command_hint}`: {e}"
                    )));
                    return false;
                }
            }
        } else if let Some(previous) = app.last_command_output.clone() {
            previous
        } else {
            show_command_info_popup(
                app,
                raw,
                "No recent command/test output found.\nRun `/fix-failures <test-or-lint-command>` or execute a command first.".to_string(),
            );
            return false;
        };

        let prompt = format!(
            "Given this failure output, rank likely root causes and propose an efficient fix plan.\nInclude: immediate fix, verification command, and fallback options.\n\n```text\n{}\n```",
            truncate_block(&failure_output, 12000)
        );
        send_chat_request(
            app,
            tx,
            rpc_cmd_tx,
            cancel_token,
            apply_response_mode_to_user_input(app.response_mode, &prompt),
            raw.to_string(),
            launch.session_log.as_ref(),
        );
        return false;
    }

    if lowered.starts_with("/run ") {
        let command = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if command.is_empty() {
            show_command_info_popup(app, raw, "Usage: /run <command>".to_string());
            return false;
        }

        match rpc_execute_command_blocking(rpc_cmd_tx, command) {
            Ok(output) => {
                app.last_command_output = Some(output.clone());
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "**Command:** `{command}`\n\n{}",
                        truncate_block(&output, 1600)
                    ),
                )
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Command failed: {e}"))),
        }
        return false;
    }

    if lowered.starts_with("/read ") {
        let file_path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if file_path.is_empty() {
            show_command_info_popup(app, raw, "Usage: /read <file>".to_string());
            return false;
        }

        match rpc_read_file_blocking(rpc_cmd_tx, file_path) {
            Ok(content) => {
                let language = detect_language_from_path(file_path);
                show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "File: `{file_path}`\n```{language}\n{}\n```",
                        truncate_block(&content, 3200)
                    ),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Read failed: {e}"))),
        }
        return false;
    }

    if lowered == "/pwd" {
        show_command_info_popup(app, raw, format!("Current directory: `{}`", app.cwd));
        return false;
    }

    if lowered == "/ls" || lowered.starts_with("/ls ") {
        let path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or(".");
        let command = format!("ls -la {}", shell_escape_single_quotes(path));
        match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
            Ok(output) => show_command_info_popup(
                app,
                raw,
                format!("**Listing:** `{path}`\n\n{}", truncate_block(&output, 1600)),
            ),
            Err(e) => app.push_message(ChatMessage::error(format!("ls failed: {e}"))),
        }
        return false;
    }

    // ── Pair mode commands ─────────────────────────────────────────────
    if lowered == "/pair" || lowered.starts_with("/pair ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        // pair host subcommands: /pair status, /pair members, /pair kick, /pair share
        if args.len() >= 2 && app.pair_mode_active && app.pair_is_host {
            let sub = args[1].to_ascii_lowercase();
            match sub.as_str() {
                "status" => {
                    match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                        Ok(payload) => show_command_info_popup(app, raw, format_host_server_payload(&payload)),
                        Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch status: {e}"))),
                    }
                    return false;
                }
                "members" | "who" => {
                    let room = if app.multiplayer_room.is_empty() { None } else { Some(app.multiplayer_room.as_str()) };
                    match rpc_list_room_members_blocking(rpc_cmd_tx, room) {
                        Ok(payload) => show_command_info_popup(app, raw, format_room_members_payload(&payload)),
                        Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch members: {e}"))),
                    }
                    return false;
                }
                "kick" => {
                    if args.len() < 3 {
                        show_command_info_popup(app, raw, "Usage: /pair kick <connection-id|number>".to_string());
                        return false;
                    }
                    let target = args[2];
                    let cid = if let Ok(num) = target.parse::<usize>() {
                        if num >= 1 && num <= app.connected_users.len() {
                            app.connected_users[num - 1].connection_id.clone()
                        } else {
                            show_command_info_popup(app, raw, format!("Invalid user number. Use 1-{}.", app.connected_users.len()));
                            return false;
                        }
                    } else {
                        target.to_string()
                    };
                    let room = if app.multiplayer_room.is_empty() { None } else { Some(app.multiplayer_room.as_str()) };
                    match rpc_kick_member_blocking(rpc_cmd_tx, &cid, room) {
                        Ok(_) => show_command_info_popup(app, raw, format!("Kicked `{cid}` from session.")),
                        Err(e) => app.push_message(ChatMessage::error(format!("Failed to kick: {e}"))),
                    }
                    return false;
                }
                "share" => {
                    match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                        Ok(payload) => {
                            let role = args.get(2).copied();
                            let room = if app.multiplayer_room.is_empty() { None } else { Some(app.multiplayer_room.as_str()) };
                            show_command_info_popup(app, raw, format_host_share_payload(&payload, role, room));
                        }
                        Err(e) => app.push_message(ChatMessage::error(format!("Failed to fetch share info: {e}"))),
                    }
                    return false;
                }
                _ => {} // fall through to normal /pair logic
            }
        }
        if args.len() == 1 {
            // host mode: start pair session
            let lobby = false;
            match rpc_pair_start_blocking(rpc_cmd_tx, lobby) {
                Ok(payload) => {
                    let short_code = payload.get("shortCode").and_then(|v| v.as_str()).unwrap_or("");
                    let invite_code = payload.get("inviteCode").and_then(|v| v.as_str()).unwrap_or("");
                    app.pair_mode_active = true;
                    app.pair_is_host = true;
                    app.pair_short_code = short_code.to_string();
                    app.pair_invite_code = invite_code.to_string();
                    app.multiplayer_enabled = true;
                    app.multiplayer_room = short_code.to_string();
                    app.multiplayer_role = "prompter".to_string();
                    // best-effort clipboard copy
                    let _ = std::process::Command::new("pbcopy")
                        .stdin(std::process::Stdio::piped())
                        .spawn()
                        .and_then(|mut child| {
                            use std::io::Write;
                            if let Some(ref mut stdin) = child.stdin {
                                let _ = stdin.write_all(invite_code.as_bytes());
                            }
                            child.wait()
                        });
                    app.push_message(ChatMessage::system(format!(
                        "Pair session started! Room: {short_code}\nInvite code copied to clipboard.\nShare it with: /pair <invite-code>"
                    )));
                    app.set_status(format!("Pair session: {short_code}"));
                }
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to start pair session: {e}\nCheck that no other session is running. Try /leave first."))),
            }
            return false;
        }
        // check --lobby flag
        let has_lobby = args.iter().any(|a| *a == "--lobby");
        if args.len() == 2 && has_lobby {
            match rpc_pair_start_blocking(rpc_cmd_tx, true) {
                Ok(payload) => {
                    let short_code = payload.get("shortCode").and_then(|v| v.as_str()).unwrap_or("");
                    let invite_code = payload.get("inviteCode").and_then(|v| v.as_str()).unwrap_or("");
                    app.pair_mode_active = true;
                    app.pair_is_host = true;
                    app.pair_short_code = short_code.to_string();
                    app.pair_invite_code = invite_code.to_string();
                    app.multiplayer_enabled = true;
                    app.multiplayer_room = short_code.to_string();
                    app.multiplayer_role = "prompter".to_string();
                    app.multiplayer_lobby_enabled = true;
                    let _ = std::process::Command::new("pbcopy")
                        .stdin(std::process::Stdio::piped())
                        .spawn()
                        .and_then(|mut child| {
                            use std::io::Write;
                            if let Some(ref mut stdin) = child.stdin {
                                let _ = stdin.write_all(invite_code.as_bytes());
                            }
                            child.wait()
                        });
                    app.push_message(ChatMessage::system(format!(
                        "Pair session started (lobby mode)! Room: {short_code}\nInvite code copied to clipboard."
                    )));
                }
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to start pair session: {e}\nCheck that no other session is running. Try /leave first."))),
            }
            return false;
        }
        // join mode: /pair <invite-code>
        let invite = args[1];
        let (url, room, token) = match multiplayer::decode_invite_code(invite) {
            Ok((u, r, t)) => (u, r, t),
            Err(e) => {
                show_command_info_popup(
                    app,
                    raw,
                    format!("{e}\nUse `/pair` to host, or paste the invite code from the host."),
                );
                return false;
            }
        };
        app.set_status("Connecting to endpoint...");
        if let Err(e) = multiplayer::preflight_join_endpoint(&url) {
            app.push_message(ChatMessage::error(format!(
                "Join preflight failed: {e}\nCheck the invite code and try again."
            )));
            return false;
        }
        app.pair_mode_active = true;
        app.pair_is_host = false;
        app.pair_short_code = room.clone();
        app.multiplayer_room = room.clone();
        app.multiplayer_role = "viewer".to_string();
        multiplayer::reconnect_to_remote_server(app, tx, rpc_cmd_tx, launch, &url, &room, &token);
        app.push_message(ChatMessage::system(format!("Joining pair session: {room}")));
        return false;
    }

    if lowered == "/pass" || lowered.starts_with("/pass ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let (display_name, connection_id): (Option<String>, Option<String>) = if args.len() > 1 {
            let target = args[1..].join(" ");
            if let Ok(num) = target.parse::<usize>() { // numeric index from presence bar
                if num >= 1 && num <= app.connected_users.len() {
                    (None, Some(app.connected_users[num - 1].connection_id.clone()))
                } else {
                    app.push_message(ChatMessage::error(format!(
                        "Invalid user number {num}. Use 1-{} per the presence bar.",
                        app.connected_users.len()
                    )));
                    return false;
                }
            } else if target.starts_with('@') {
                (Some(target[1..].to_string()), None)
            } else {
                (Some(target.clone()), None)
            }
        } else {
            (None, None) // pass to next navigator
        };
        let room = if app.multiplayer_room.is_empty() { None } else { Some(app.multiplayer_room.as_str()) };
        match rpc_pass_driver_blocking(rpc_cmd_tx, display_name.as_deref(), connection_id.as_deref(), room) {
            Ok(payload) => {
                let target_id = payload.get("connectionId").and_then(|v| v.as_str()).unwrap_or("someone");
                app.push_message(ChatMessage::system(format!("Driver role passed to `{target_id}`.")));
                app.set_status("Driver role handed off");
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to pass driver: {e}\nEnsure you are the driver. Use /who to check roles."))),
        }
        return false;
    }

    if lowered.starts_with("/suggest ") {
        let text = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if text.is_empty() {
            show_command_info_popup(app, raw, "Usage: /suggest <text>".to_string());
            return false;
        }
        match rpc_suggest_text_blocking(rpc_cmd_tx, text) {
            Ok(_) => app.set_status("Suggestion sent"),
            Err(e) => app.push_message(ChatMessage::error(format!("Suggest failed: {e}\nEnsure you are connected to a pair session."))),
        }
        return false;
    }
    if lowered == "/suggest" {
        show_command_info_popup(app, raw, "Usage: /suggest <text>\nSend a suggestion visible to the driver.".to_string());
        return false;
    }

    if lowered == "/leave" {
        if app.pair_is_host {
            match rpc_stop_host_server_blocking(rpc_cmd_tx) {
                Ok(_) => app.push_message(ChatMessage::system("Pair session stopped.".to_string())),
                Err(e) => app.push_message(ChatMessage::error(format!("Failed to stop pair session: {e}\nThe session may have already ended."))),
            }
        } else {
            app.push_message(ChatMessage::system("Disconnected from pair session.".to_string()));
        }
        app.reset_pair_state();
        app.multiplayer_enabled = false;
        app.multiplayer_room.clear();
        app.multiplayer_role.clear();
        return false;
    }

    if lowered == "/join-server" || lowered.starts_with("/join-server ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() == 1 {
            app.join_wizard_active = true;
            app.join_wizard_step = 0;
            app.join_wizard_url.clear();
            app.join_wizard_room.clear();
            app.join_wizard_input.clear();
            app.join_wizard_error.clear();
            app.mode = AppMode::JoinWizard;
            return false;
        }

        if args.len() == 2
            && matches!(
                args[1].to_ascii_lowercase().as_str(),
                "cancel" | "abort" | "stop"
            )
        {
            app.join_wizard_active = false;
            app.join_wizard_step = 0;
            app.join_wizard_url.clear();
            app.join_wizard_room.clear();
            show_command_info_popup(app, raw, "Join wizard cancelled.".to_string());
            return false;
        }

        let (url, room, token) = match multiplayer::parse_join_server_args(raw) {
            Ok(values) => values,
            Err(error_message) => {
                show_command_info_popup(app, raw, error_message);
                return false;
            }
        };

        app.set_status("Connecting to endpoint...");
        if let Err(e) = multiplayer::preflight_join_endpoint(&url) {
            app.push_message(ChatMessage::error(format!(
                "Join preflight failed: {e}\nUse `/join-server` for wizard mode."
            )));
            return false;
        }

        multiplayer::reconnect_to_remote_server(app, tx, rpc_cmd_tx, launch, &url, &room, &token);
        return false;
    }

    if lowered == "/kick" || lowered.starts_with("/kick ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() < 2 || args.len() > 3 {
            show_command_info_popup(
                app,
                raw,
                "Usage: /kick <connection-id> [room]\nIf room is omitted, the current multiplayer room is used."
                    .to_string(),
            );
            return false;
        }

        let connection_id = args[1];
        let room = if let Some(explicit_room) = args.get(2).copied() {
            Some(explicit_room)
        } else if app.multiplayer_room.is_empty() {
            None
        } else {
            Some(app.multiplayer_room.as_str())
        };

        match rpc_kick_member_blocking(rpc_cmd_tx, connection_id, room) {
            Ok(payload) => {
                let room_name = payload
                    .get("room")
                    .and_then(|value| value.as_str())
                    .or(room)
                    .unwrap_or("");
                show_command_info_popup(
                    app,
                    raw,
                    format!("Kicked `{connection_id}` from room `{room_name}`."),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to kick `{connection_id}`: {e}\nUse /who to verify the connection-id."
            ))),
        }
        return false;
    }

    if lowered == "/who"
        || lowered.starts_with("/who ")
        || lowered == "/members"
        || lowered.starts_with("/members ")
    {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() > 2 {
            show_command_info_popup(app, raw, "Usage: /who [room]".to_string());
            return false;
        }

        let room = if let Some(explicit_room) = args.get(1).copied() {
            Some(explicit_room)
        } else if app.multiplayer_room.is_empty() {
            None
        } else {
            Some(app.multiplayer_room.as_str())
        };

        match rpc_list_room_members_blocking(rpc_cmd_tx, room) {
            Ok(payload) => show_command_info_popup(app, raw, format_room_members_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch room members: {e}\nEnsure a multiplayer session is active."
            ))),
        }
        return false;
    }

    if lowered == "/host-server" || lowered.starts_with("/host-server ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args.get(1).copied().unwrap_or("").trim();
        let lowered_subcommand = subcommand.to_ascii_lowercase();

        if lowered_subcommand == "status" {
            if args.len() > 2 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }

            match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_host_server_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to fetch host server status: {e}\nUse /host-server to start a server first."
                ))),
            }
            return false;
        }

        if lowered_subcommand == "stop" {
            if args.len() > 2 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }

            match rpc_stop_host_server_blocking(rpc_cmd_tx) {
                Ok(payload) => {
                    if payload
                        .get("stopped")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false)
                    {
                        show_command_info_popup(app, raw, "Multiplayer host stopped.".to_string());
                    } else {
                        show_command_info_popup(
                            app,
                            raw,
                            "No multiplayer host is currently running.".to_string(),
                        );
                    }
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to stop host server: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "members" || lowered_subcommand == "users" {
            if args.len() > 3 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }

            let room = args.get(2).copied();
            match rpc_list_host_members_blocking(rpc_cmd_tx, room) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_host_members_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to fetch host members: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "kick" || lowered_subcommand == "remove" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }

            let connection_id = args[2];
            let room = args.get(3).copied();
            match rpc_remove_host_member_blocking(rpc_cmd_tx, connection_id, room) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    let mut lines = vec![format!(
                        "Removed connection `{connection_id}` from room `{room_name}`."
                    )];
                    if let Ok(updated) = rpc_list_host_members_blocking(
                        rpc_cmd_tx,
                        if room_name.is_empty() {
                            None
                        } else {
                            Some(room_name)
                        },
                    ) {
                        lines.push(String::new());
                        lines.push(format_host_members_payload(&updated));
                    }
                    show_command_info_popup(app, raw, lines.join("\n"));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to remove `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "role"
            || lowered_subcommand == "promote"
            || lowered_subcommand == "demote"
        {
            let (connection_id, role, room): (&str, &str, Option<&str>) =
                if lowered_subcommand == "role" {
                    if args.len() < 4 || args.len() > 5 {
                        show_command_info_popup(app, raw, host_server_usage_text().to_string());
                        return false;
                    }
                    (args[2], args[3], args.get(4).copied())
                } else if lowered_subcommand == "promote" {
                    if args.len() < 3 || args.len() > 4 {
                        show_command_info_popup(app, raw, host_server_usage_text().to_string());
                        return false;
                    }
                    (args[2], "prompter", args.get(3).copied())
                } else {
                    if args.len() < 3 || args.len() > 4 {
                        show_command_info_popup(app, raw, host_server_usage_text().to_string());
                        return false;
                    }
                    (args[2], "viewer", args.get(3).copied())
                };

            let normalized_role = match role.to_ascii_lowercase().as_str() {
                "viewer" | "read" | "read-only" => "viewer",
                "prompter" | "writer" | "editor" | "admin" => "prompter",
                _ => {
                    show_command_info_popup(
                        app,
                        raw,
                        "Invalid role. Use `viewer` or `prompter`.".to_string(),
                    );
                    return false;
                }
            };

            match rpc_set_host_member_role_blocking(
                rpc_cmd_tx,
                connection_id,
                normalized_role,
                room,
            ) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    let mut lines = vec![format!(
                        "Updated `{connection_id}` to role **{normalized_role}** in room `{room_name}`."
                    )];
                    if let Ok(updated) = rpc_list_host_members_blocking(
                        rpc_cmd_tx,
                        if room_name.is_empty() {
                            None
                        } else {
                            Some(room_name)
                        },
                    ) {
                        lines.push(String::new());
                        lines.push(format_host_members_payload(&updated));
                    }
                    show_command_info_popup(app, raw, lines.join("\n"));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to update role for `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "share" {
            if args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let mut role_filter: Option<&str> = None;
            let mut room_filter: Option<&str> = None;
            if let Some(first) = args.get(2).copied() {
                let first_lower = first.to_ascii_lowercase();
                if first_lower == "viewer" || first_lower == "prompter" {
                    role_filter = Some(first);
                    room_filter = args.get(3).copied();
                } else {
                    room_filter = Some(first);
                    if let Some(second) = args.get(3).copied() {
                        let second_lower = second.to_ascii_lowercase();
                        if second_lower == "viewer" || second_lower == "prompter" {
                            role_filter = Some(second);
                        }
                    }
                }
            }

            match rpc_get_host_server_status_blocking(rpc_cmd_tx) {
                Ok(payload) => show_command_info_popup(
                    app,
                    raw,
                    format_host_share_payload(&payload, role_filter, room_filter),
                ),
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to get host share details: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "lobby" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let enable = match args[2].to_ascii_lowercase().as_str() {
                "on" | "enable" | "enabled" | "true" => true,
                "off" | "disable" | "disabled" | "false" => false,
                _ => {
                    show_command_info_popup(
                        app,
                        raw,
                        "Usage: /host-server lobby <on|off> [room]".to_string(),
                    );
                    return false;
                }
            };
            let room = args.get(3).copied();
            match rpc_set_host_lobby_blocking(rpc_cmd_tx, enable, room) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    let state = if enable { "enabled" } else { "disabled" };
                    show_command_info_popup(
                        app,
                        raw,
                        format!("Lobby approvals {state} for room `{room_name}`."),
                    );
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to update lobby mode: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "approve" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let connection_id = args[2];
            let room = args.get(3).copied();
            match rpc_approve_host_member_blocking(rpc_cmd_tx, connection_id, room) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    show_command_info_popup(
                        app,
                        raw,
                        format!("Approved `{connection_id}` in room `{room_name}`."),
                    );
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to approve member `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "deny" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let connection_id = args[2];
            let room = args.get(3).copied();
            match rpc_deny_host_member_blocking(rpc_cmd_tx, connection_id, room) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    show_command_info_popup(
                        app,
                        raw,
                        format!("Denied `{connection_id}` in room `{room_name}`."),
                    );
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to deny member `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "rotate-token" {
            if args.len() < 3 || args.len() > 5 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let role = args[2].to_ascii_lowercase();
            if role != "viewer" && role != "prompter" {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]"
                        .to_string(),
                );
                return false;
            }
            let mut room: Option<&str> = None;
            let mut expiry_seconds: Option<u64> = None;
            if let Some(arg3) = args.get(3).copied() {
                if let Ok(parsed) = arg3.parse::<u64>() {
                    expiry_seconds = Some(parsed);
                } else {
                    room = Some(arg3);
                }
            }
            if let Some(arg4) = args.get(4).copied() {
                match arg4.parse::<u64>() {
                    Ok(parsed) => expiry_seconds = Some(parsed),
                    Err(_) => {
                        show_command_info_popup(
                            app,
                            raw,
                            "Usage: /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]".to_string(),
                        );
                        return false;
                    }
                }
            }
            match rpc_rotate_host_token_blocking(rpc_cmd_tx, &role, room, expiry_seconds) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    let token = payload.get("token").and_then(|v| v.as_str()).unwrap_or("");
                    let join_command = payload
                        .get("joinCommand")
                        .and_then(|v| v.as_str())
                        .unwrap_or("");
                    let invite_code = payload
                        .get("inviteCode")
                        .and_then(|v| v.as_str())
                        .unwrap_or("");
                    let mut lines = vec![format!(
                        "Rotated **{role}** token for room `{room_name}`: `{token}`"
                    )];
                    if !join_command.is_empty() {
                        lines.push(format!("- Join command: `{join_command}`"));
                    }
                    if !invite_code.is_empty() {
                        lines.push(format!("- Invite code: `{invite_code}`"));
                    }
                    if let Some(expires_at) = payload.get("expiresAt").and_then(|v| v.as_str()) {
                        if !expires_at.is_empty() {
                            lines.push(format!("- Expires at: `{expires_at}`"));
                        }
                    }
                    show_command_info_popup(app, raw, lines.join("\n"));
                }
                Err(e) => {
                    app.push_message(ChatMessage::error(format!("Failed to rotate token: {e}")))
                }
            }
            return false;
        }

        if lowered_subcommand == "revoke" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let value = args[2];
            let room = args.get(3).copied();
            match rpc_revoke_host_token_blocking(rpc_cmd_tx, value, room) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    let kind = payload
                        .get("kind")
                        .and_then(|v| v.as_str())
                        .unwrap_or("token");
                    show_command_info_popup(
                        app,
                        raw,
                        format!("Revoked `{value}` ({kind}) in room `{room_name}`."),
                    );
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to revoke `{value}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "handoff" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let connection_id = args[2];
            let room = args.get(3).copied();
            match rpc_handoff_host_member_blocking(rpc_cmd_tx, connection_id, room) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "Handed off prompter role to `{connection_id}` in room `{room_name}`."
                        ),
                    );
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to handoff to `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "preset" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let preset = args[2].to_ascii_lowercase();
            if preset != "pairing" && preset != "mob" && preset != "review" {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /host-server preset <pairing|mob|review> [room]".to_string(),
                );
                return false;
            }
            let room = args.get(3).copied();
            match rpc_set_host_preset_blocking(rpc_cmd_tx, &preset, room) {
                Ok(payload) => {
                    let room_name = payload
                        .get("room")
                        .and_then(|v| v.as_str())
                        .unwrap_or(room.unwrap_or(""));
                    let lobby_enabled = payload
                        .get("lobbyEnabled")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "Applied preset **{preset}** to room `{room_name}` (lobby: {}).",
                            if lobby_enabled { "on" } else { "off" }
                        ),
                    );
                }
                Err(e) => {
                    app.push_message(ChatMessage::error(format!("Failed to set preset: {e}")))
                }
            }
            return false;
        }

        if lowered_subcommand == "activity" {
            if args.len() > 5 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            let mut room: Option<&str> = None;
            let mut limit: u64 = 30;
            let mut event_type: Option<&str> = None;
            let mut idx = 2usize;
            if let Some(arg) = args.get(idx).copied() {
                if arg.parse::<u64>().is_err() {
                    room = Some(arg);
                    idx += 1;
                }
            }
            if let Some(arg) = args.get(idx).copied() {
                if let Ok(parsed) = arg.parse::<u64>() {
                    limit = parsed;
                    idx += 1;
                }
            }
            if let Some(arg) = args.get(idx).copied() {
                event_type = Some(arg);
                idx += 1;
            }
            if idx < args.len() {
                show_command_info_popup(
                    app,
                    raw,
                    "Usage: /host-server activity [room] [limit] [event-type]".to_string(),
                );
                return false;
            }
            match rpc_list_host_activity_blocking(rpc_cmd_tx, room, limit, event_type) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_host_activity_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to fetch host activity: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "help" {
            show_command_info_popup(app, raw, host_server_usage_text().to_string());
            return false;
        }

        let room = if subcommand.is_empty() {
            None
        } else {
            if args.len() > 2 {
                show_command_info_popup(app, raw, host_server_usage_text().to_string());
                return false;
            }
            Some(subcommand)
        };

        match rpc_start_host_server_blocking(rpc_cmd_tx, room) {
            Ok(payload) => show_command_info_popup(app, raw, format_host_server_payload(&payload)),
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to start host server: {e}"
            ))),
        }
        return false;
    }

    if lowered == "/service" || lowered.starts_with("/service ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("status")
            .trim()
            .to_ascii_lowercase();

        if subcommand.is_empty() || subcommand == "help" {
            show_command_info_popup(app, raw, service_usage_text().to_string());
            return false;
        }

        if subcommand == "status" || subcommand == "list" {
            if args.len() > 3 {
                show_command_info_popup(app, raw, service_usage_text().to_string());
                return false;
            }
            let service_name = args.get(2).copied();
            match rpc_get_service_status_blocking(rpc_cmd_tx, service_name) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_service_status_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to fetch service status: {e}"
                ))),
            }
            return false;
        }

        if subcommand == "start" {
            let mut split = raw.splitn(4, ' ');
            let _ = split.next();
            let _ = split.next();
            let service_name = split.next().unwrap_or("").trim();
            let command_text = split
                .next()
                .map(str::trim)
                .filter(|value| !value.is_empty());
            if service_name.is_empty() {
                show_command_info_popup(app, raw, service_usage_text().to_string());
                return false;
            }
            match rpc_start_service_blocking(rpc_cmd_tx, service_name, command_text, None) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_service_status_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to start service `{service_name}`: {e}"
                ))),
            }
            return false;
        }

        if subcommand == "stop" {
            if args.len() != 3 {
                show_command_info_popup(app, raw, service_usage_text().to_string());
                return false;
            }
            let service_name = args[2];
            match rpc_stop_service_blocking(rpc_cmd_tx, service_name) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_service_status_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to stop service `{service_name}`: {e}"
                ))),
            }
            return false;
        }

        if subcommand == "logs" {
            if args.len() < 3 || args.len() > 4 {
                show_command_info_popup(app, raw, service_usage_text().to_string());
                return false;
            }
            let service_name = args[2];
            let line_count = match args.get(3) {
                Some(raw_count) => match raw_count.parse::<u64>() {
                    Ok(parsed) => Some(parsed),
                    Err(_) => {
                        show_command_info_popup(
                            app,
                            raw,
                            "lines must be an integer (e.g. `/service logs ollama 120`)"
                                .to_string(),
                        );
                        return false;
                    }
                },
                None => None,
            };

            match rpc_get_service_logs_blocking(rpc_cmd_tx, service_name, line_count) {
                Ok(payload) => {
                    let status_block = payload
                        .get("status")
                        .map(format_service_status_payload)
                        .unwrap_or_else(|| format!("**Service:** `{service_name}`"));
                    let log_path = payload
                        .get("logPath")
                        .and_then(|v| v.as_str())
                        .unwrap_or("(unknown)");
                    let content = payload
                        .get("content")
                        .and_then(|v| v.as_str())
                        .unwrap_or("");

                    if content.is_empty() {
                        show_command_info_popup(
                            app,
                            raw,
                            format!("{status_block}\n\nNo logs available yet at `{log_path}`."),
                        );
                    } else {
                        app.last_command_output = Some(content.to_string());
                        show_command_info_popup(
                            app,
                            raw,
                            format!(
                                "{status_block}\n\n**Log Tail:** `{log_path}`\n```text\n{}\n```",
                                truncate_block(content, 3200)
                            ),
                        );
                    }
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to fetch logs for `{service_name}`: {e}"
                ))),
            }
            return false;
        }

        show_command_info_popup(app, raw, service_usage_text().to_string());
        return false;
    }

    if lowered == "/ollama" || lowered.starts_with("/ollama ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("status")
            .trim()
            .to_ascii_lowercase();

        match subcommand.as_str() {
            "" | "status" => match rpc_get_service_status_blocking(rpc_cmd_tx, Some("ollama")) {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_service_status_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to fetch Ollama status: {e}"
                ))),
            },
            "start" => match rpc_start_service_blocking(rpc_cmd_tx, "ollama", None, None) {
                Ok(payload) => {
                    let running = payload
                        .get("running")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let healthy = payload
                        .get("healthy")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);

                    let mut lines = vec![format_service_status_payload(&payload)];
                    lines.push(String::new());
                    if running && healthy {
                        lines.push("Next steps:".to_string());
                        lines.push("- `/switch` and choose `ollama`.".to_string());
                        lines.push("- If model is missing: `/ollama pull <model>`.".to_string());
                    } else if running {
                        lines.push(
                            "Ollama process started but endpoint is not ready yet. Check `/ollama status`."
                                .to_string(),
                        );
                    } else {
                        lines.push(
                            "Ollama did not report as running. Check `/ollama logs`.".to_string(),
                        );
                    }
                    show_command_info_popup(app, raw, lines.join("\n"));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to start Ollama service: {e}"
                ))),
            },
            "stop" => match rpc_stop_service_blocking(rpc_cmd_tx, "ollama") {
                Ok(payload) => {
                    show_command_info_popup(app, raw, format_service_status_payload(&payload))
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to stop Ollama service: {e}"
                ))),
            },
            "logs" => {
                let line_count = match args.get(2) {
                    Some(raw_count) => match raw_count.parse::<u64>() {
                        Ok(parsed) => Some(parsed),
                        Err(_) => {
                            show_command_info_popup(
                                app,
                                raw,
                                "lines must be an integer (e.g. `/ollama logs 120`)".to_string(),
                            );
                            return false;
                        }
                    },
                    None => Some(120),
                };

                match rpc_get_service_logs_blocking(rpc_cmd_tx, "ollama", line_count) {
                    Ok(payload) => {
                        let status_block = payload
                            .get("status")
                            .map(format_service_status_payload)
                            .unwrap_or_else(|| "**Service:** `ollama`".to_string());
                        let log_path = payload
                            .get("logPath")
                            .and_then(|v| v.as_str())
                            .unwrap_or("(unknown)");
                        let content = payload
                            .get("content")
                            .and_then(|v| v.as_str())
                            .unwrap_or("");
                        if content.is_empty() {
                            show_command_info_popup(
                                app,
                                raw,
                                format!("{status_block}\n\nNo logs available yet at `{log_path}`."),
                            );
                        } else {
                            app.last_command_output = Some(content.to_string());
                            show_command_info_popup(
                                app,
                                raw,
                                format!(
                                    "{status_block}\n\n**Log Tail:** `{log_path}`\n```text\n{}\n```",
                                    truncate_block(content, 3200)
                                ),
                            );
                        }
                    }
                    Err(e) => app.push_message(ChatMessage::error(format!(
                        "Failed to fetch Ollama logs: {e}"
                    ))),
                }
            }
            "pull" => {
                if args.len() != 3 {
                    show_command_info_popup(app, raw, "Usage: /ollama pull <model>".to_string());
                    return false;
                }

                let model = args[2];
                let command = format!("ollama pull {model}");
                match rpc_execute_command_with_timeout_blocking(
                    rpc_cmd_tx,
                    &command,
                    Some(1800),
                    1815,
                ) {
                    Ok(output) => show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "**Command:** `{command}`\n\n```text\n{}\n```",
                            truncate_block(&output, 3200)
                        ),
                    ),
                    Err(e) => app.push_message(ChatMessage::error(format!(
                        "Failed to pull Ollama model `{model}`: {e}"
                    ))),
                }
            }
            "list" | "list-models" => {
                let (reply_tx, reply_rx) = mpsc::sync_channel(1);
                let _ = rpc_cmd_tx.send(RpcCommand::ListProviders { reply: reply_tx });
                match reply_rx.recv_timeout(Duration::from_secs(20)) {
                    Ok(Ok(providers)) => {
                        let ollama = providers
                            .iter()
                            .find(|provider| provider.name.eq_ignore_ascii_case("ollama"));
                        if let Some(provider) = ollama {
                            if provider.models.is_empty() {
                                show_command_info_popup(
                                    app,
                                    raw,
                                    "No installed Ollama models were detected.\n\nTry `/ollama pull <model>`."
                                        .to_string(),
                                );
                            } else {
                                let mut lines = vec!["**Installed Ollama Models**".to_string()];
                                lines.extend(
                                    provider.models.iter().map(|model| format!("- `{model}`")),
                                );
                                show_command_info_popup(app, raw, lines.join("\n"));
                            }
                        } else {
                            app.push_message(ChatMessage::error(
                                "Failed to list Ollama models: provider metadata unavailable"
                                    .to_string(),
                            ));
                        }
                    }
                    Ok(Err(e)) => app.push_message(ChatMessage::error(format!(
                        "Failed to list Ollama models: {e}"
                    ))),
                    Err(_) => app.push_message(ChatMessage::error(
                        "Failed to list Ollama models: timed out waiting for provider metadata"
                            .to_string(),
                    )),
                }
            }
            "ps" => {
                match rpc_execute_command_with_timeout_blocking(
                    rpc_cmd_tx,
                    "ollama ps",
                    Some(60),
                    75,
                ) {
                    Ok(output) => show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "**Ollama Running Models**\n```text\n{}\n```",
                            truncate_block(&output, 3200)
                        ),
                    ),
                    Err(e) => app.push_message(ChatMessage::error(format!(
                        "Failed to inspect Ollama running models: {e}"
                    ))),
                }
            }
            _ => show_command_info_popup(app, raw, ollama_usage_text().to_string()),
        }

        return false;
    }

    if lowered == "/status" {
        refresh_context_budget_state(app);
        let onboarding_state = if app.onboarding_active {
            format!(
                "active ({}/{})",
                app.onboarding_step.saturating_add(1),
                onboarding_step_count()
            )
        } else {
            "inactive".to_string()
        };
        let multiplayer_state = if app.multiplayer_enabled {
            format!(
                "room=`{}` role=`{}` members={} queue={} active=`{}` lobby={} preset={}",
                if app.multiplayer_room.is_empty() {
                    "unknown"
                } else {
                    &app.multiplayer_room
                },
                if app.multiplayer_role.is_empty() {
                    "unknown"
                } else {
                    &app.multiplayer_role
                },
                app.multiplayer_member_count,
                app.multiplayer_queue_depth,
                if app.multiplayer_active_connection_id.is_empty() {
                    "-"
                } else {
                    &app.multiplayer_active_connection_id
                },
                if app.multiplayer_lobby_enabled {
                    "on"
                } else {
                    "off"
                },
                if app.multiplayer_preset.is_empty() {
                    "-"
                } else {
                    &app.multiplayer_preset
                },
            )
        } else {
            "inactive".to_string()
        };
        let status = format!(
            "**Session Status:**\n\
Provider: {}/{}\n\
CWD: {}\n\
Response mode: {}\n\
Profile: {}\n\
Autopilot: {}\n\
Context budget: {} tok ({} file(s), ~{} tok used)\n\
QA watch: {}\n\
Pinned files: {}\n\
Queued images: {}\n\
Watch mode: {}\n\
Onboarding: {}\n\
Multiplayer: {}",
            app.provider_name,
            app.model_name,
            app.cwd,
            app.response_mode.as_str(),
            app.execution_profile,
            if app.autopilot_enabled {
                "enabled"
            } else {
                "disabled"
            },
            app.context_budget_tokens,
            app.context_budget_files.len(),
            app.context_budget_estimated_tokens,
            if qa_watch_state.is_running() {
                "running"
            } else {
                "stopped"
            },
            app.pinned_context_files.len(),
            app.pending_images.len(),
            if watch_state.is_running() {
                "active"
            } else {
                "inactive"
            },
            onboarding_state,
            multiplayer_state
        );
        show_command_info_popup(app, raw, status);
        return false;
    }

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
                    return false;
                }

                let checkpoints = payload
                    .get("checkpoints")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if checkpoints.is_empty() {
                    show_command_info_popup(app, raw, "No checkpoints available.".to_string());
                    return false;
                }

                let storage_bytes = payload
                    .get("storageSizeBytes")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(0);
                let storage_path = payload
                    .get("storagePath")
                    .and_then(|v| v.as_str())
                    .unwrap_or("");

                let mut lines = vec![
                    format!("**Checkpoints ({}):**", checkpoints.len()),
                    format!("Storage: {} ({storage_path})", format_bytes(storage_bytes)),
                    String::new(),
                ];
                for cp in checkpoints {
                    let id = cp
                        .get("checkpointId")
                        .and_then(|v| v.as_str())
                        .unwrap_or("unknown");
                    let created = cp.get("createdAt").and_then(|v| v.as_str()).unwrap_or("-");
                    let description = cp.get("description").and_then(|v| v.as_str()).unwrap_or("");
                    let file_count = cp.get("fileCount").and_then(|v| v.as_u64()).unwrap_or(0);
                    let total_size = cp
                        .get("totalSizeBytes")
                        .and_then(|v| v.as_u64())
                        .unwrap_or(0);
                    lines.push(format!(
                        "- `{id}` • {created} • {file_count} file(s) • {} • {description}",
                        format_bytes(total_size)
                    ));
                }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to list checkpoints: {e}"
            ))),
        }
        return false;
    }

    if lowered == "/checkpoint" || lowered == "/save" {
        let (description, operation_type) = if lowered == "/save" {
            ("Quick save".to_string(), "manual".to_string())
        } else {
            ("Manual checkpoint".to_string(), "manual".to_string())
        };

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
        return false;
    }

    if lowered.starts_with("/rewind") || lowered == "/restore" || lowered == "/undo" {
        let checkpoint_id = if lowered == "/restore" || lowered == "/undo" {
            Some("last".to_string())
        } else {
            raw.split_whitespace()
                .nth(1)
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty())
                .or_else(|| Some("last".to_string()))
        };

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
        return false;
    }

    if lowered.starts_with("/diff") {
        let parts: Vec<&str> = raw.split_whitespace().collect();
        if parts.len() < 3 {
            show_command_info_popup(app, raw, "Usage: /diff <file1> <file2>".to_string());
            return false;
        }

        match rpc_compare_files_blocking(rpc_cmd_tx, parts[1], parts[2]) {
            Ok(diff) => {
                if diff.trim() == "(No differences)" {
                    show_command_info_popup(app, raw, diff);
                } else {
                    app.push_message(ChatMessage::diff_view(
                        format!("{} vs {}", parts[1], parts[2]),
                        truncate_block(&diff, 20_000),
                    ));
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to compare files: {e}"))),
        }
        return false;
    }

    if lowered == "/export" || lowered.starts_with("/export ") {
        let export_format = raw
            .split_whitespace()
            .nth(1)
            .unwrap_or("json")
            .to_lowercase();
        if !matches!(export_format.as_str(), "json" | "md" | "txt" | "markdown") {
            show_command_info_popup(app, raw, "Usage: /export [json|md|txt]".to_string());
            return false;
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
        return false;
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
        return false;
    }

    if lowered == "/cost" {
        let provider = app.provider_name.to_lowercase();
        let model = app.model_name.to_lowercase();

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

        // Use real token counts if available, else estimates
        let (in_tokens, out_tokens) =
            if app.cumulative_input_tokens > 0 || app.cumulative_output_tokens > 0 {
                (
                    app.cumulative_input_tokens as f64,
                    app.cumulative_output_tokens as f64,
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

        let real_label = if app.cumulative_input_tokens > 0 {
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
            app.provider_name,
            app.model_name,
            input_cost,
            output_cost,
            total
        );
        show_command_info_popup(app, raw, text);
        return false;
    }

    if lowered == "/commit --apply-last" {
        if let Some(last) = last_assistant_message(app) {
            let subject = first_line(&last);
            if subject.is_empty() {
                show_command_info_popup(
                    app,
                    raw,
                    "Last assistant response was empty; nothing to commit.".to_string(),
                );
                return false;
            }

            let command = format!("git commit -m {}", shell_escape_single_quotes(&subject));
            match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
                Ok(output) => show_command_info_popup(
                    app,
                    raw,
                    format!(
                        "Commit executed with message: `{subject}`\n\n{}",
                        truncate_block(&output, 1200)
                    ),
                ),
                Err(e) => app.push_message(ChatMessage::error(format!("Commit failed: {e}"))),
            }
        } else {
            show_command_info_popup(
                app,
                raw,
                "No assistant response found to apply as commit message.".to_string(),
            );
        }
        return false;
    }

    if lowered.starts_with("/commit --apply ") {
        let msg = raw.splitn(3, ' ').nth(2).map(str::trim).unwrap_or("");
        if msg.is_empty() {
            show_command_info_popup(app, raw, "Usage: /commit --apply <message>".to_string());
            return false;
        }
        let command = format!("git commit -m {}", shell_escape_single_quotes(msg));
        match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
            Ok(output) => show_command_info_popup(
                app,
                raw,
                format!("Commit executed.\n\n{}", truncate_block(&output, 1200)),
            ),
            Err(e) => app.push_message(ChatMessage::error(format!("Commit failed: {e}"))),
        }
        return false;
    }

    if lowered == "/commit" {
        match rpc_execute_command_blocking(rpc_cmd_tx, "git diff --staged") {
            Ok(diff) => {
                if diff.trim().is_empty() || diff.trim() == "(No output)" {
                    show_command_info_popup(
                        app,
                        raw,
                        "No staged changes. Stage files with `git add` first.".to_string(),
                    );
                    return false;
                }
                let prompt = build_commit_prompt(&diff);
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    prompt,
                    "/commit".to_string(),
                    launch.session_log.as_ref(),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Unable to read staged diff: {e}"
            ))),
        }
        return false;
    }

    if lowered.starts_with("/review") {
        let maybe_path = raw
            .splitn(2, ' ')
            .nth(1)
            .map(str::trim)
            .filter(|s| !s.is_empty());

        let (language, code) = if let Some(path) = maybe_path {
            match rpc_read_file_blocking(rpc_cmd_tx, path) {
                Ok(content) => (detect_language_from_path(path).to_string(), content),
                Err(e) => {
                    app.push_message(ChatMessage::error(format!(
                        "Failed to read file for review: {e}"
                    )));
                    return false;
                }
            }
        } else {
            match rpc_execute_command_blocking(rpc_cmd_tx, "git diff --staged") {
                Ok(diff) => ("diff".to_string(), diff),
                Err(e) => {
                    app.push_message(ChatMessage::error(format!(
                        "Unable to read staged diff: {e}"
                    )));
                    return false;
                }
            }
        };

        if code.trim().is_empty() || code.trim() == "(No output)" {
            show_command_info_popup(app, raw, "Nothing to review.".to_string());
            return false;
        }

        let prompt = build_review_prompt(&language, &code);
        send_chat_request(
            app,
            tx,
            rpc_cmd_tx,
            cancel_token,
            prompt,
            raw.to_string(),
            launch.session_log.as_ref(),
        );
        return false;
    }

    if lowered == "/test" {
        show_command_info_popup(app, raw, "Usage: /test <file>".to_string());
        return false;
    }

    if lowered.starts_with("/test ") {
        let file_path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if file_path.is_empty() {
            show_command_info_popup(app, raw, "Usage: /test <file>".to_string());
            return false;
        }

        let content = match rpc_read_file_blocking(rpc_cmd_tx, file_path) {
            Ok(content) => content,
            Err(e) => {
                app.push_message(ChatMessage::error(format!(
                    "Failed to read file for test generation: {e}"
                )));
                return false;
            }
        };

        let prompt = build_test_prompt(detect_language_from_path(file_path), &content);
        send_chat_request(
            app,
            tx,
            rpc_cmd_tx,
            cancel_token,
            prompt,
            raw.to_string(),
            launch.session_log.as_ref(),
        );
        return false;
    }

    if lowered.starts_with("/save-prompt ") {
        let mut parts = raw.splitn(3, ' ');
        let _ = parts.next();
        let name = parts.next().unwrap_or("").trim();
        let content = parts.next().unwrap_or("").trim();

        if name.is_empty() {
            show_command_info_popup(app, raw, "Usage: /save-prompt <name> [text]".to_string());
            return false;
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
            return false;
        }

        match save_prompt(app, name, content) {
            Ok(path) => app.set_status(format!("Saved prompt: {}", path.display())),
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return false;
    }

    if lowered.starts_with("/use ") {
        let name = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if name.is_empty() {
            show_command_info_popup(app, raw, "Usage: /use <name>".to_string());
            return false;
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
        return false;
    }

    if lowered == "/prompts" {
        match list_prompts(app) {
            Ok(entries) if entries.is_empty() => {
                show_command_info_popup(app, raw, "No saved prompts.".to_string());
            }
            Ok(entries) => {
                let mut lines = vec!["**Saved Prompts:**".to_string(), String::new()];
                for (name, preview) in entries {
                    lines.push(format!("- **{name}**: {preview}"));
                }
                show_command_info_popup(app, raw, lines.join("\n"));
            }
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return false;
    }

    if lowered.starts_with("/image ") {
        let image_path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if image_path.is_empty() {
            show_command_info_popup(app, raw, "Usage: /image <path>".to_string());
            return false;
        }
        let path = Path::new(image_path);
        if !path.is_file() {
            app.push_message(ChatMessage::error(format!(
                "Image file not found: {image_path}"
            )));
            return false;
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
            return false;
        }

        app.pending_images.push(image_path.to_string());
        app.set_status(format!(
            "Image queued: {image_path} (will be attached to next message)"
        ));
        return false;
    }

    if lowered == "/qa" || lowered.starts_with("/qa ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        let subcommand = args
            .get(1)
            .copied()
            .unwrap_or("status")
            .trim()
            .to_ascii_lowercase();

        if subcommand == "status" {
            let status = if qa_watch_state.is_running() {
                "running"
            } else {
                "stopped"
            };
            show_command_info_popup(
                app,
                raw,
                format!(
                    "**QA Watch**\n- Status: {status}\n- Directory: {}\n- Command: {}",
                    qa_watch_state
                        .directory
                        .as_deref()
                        .unwrap_or(app.cwd.as_str()),
                    qa_watch_state.command.as_deref().unwrap_or("(not set)")
                ),
            );
            return false;
        }

        if subcommand == "stop" {
            if qa_watch_state.is_running() {
                qa_watch_state.stop();
                app.qa_mode_enabled = false;
                app.qa_command.clear();
                app.set_status("QA watch stopped");
            } else {
                show_command_info_popup(app, raw, "QA watch is not running.".to_string());
            }
            return false;
        }

        if subcommand == "start" {
            if qa_watch_state.is_running() {
                show_command_info_popup(
                    app,
                    raw,
                    "QA watch is already running. Use `/qa stop` first.".to_string(),
                );
                return false;
            }

            let tail = raw
                .split_once(' ')
                .map(|(_, rest)| rest.trim())
                .and_then(|rest| rest.split_once(' ').map(|(_, after)| after.trim()))
                .unwrap_or("");
            let mut directory = app.cwd.clone();
            let mut command = watcher::default_qa_command_for_workspace(Path::new(&app.cwd));

            if !tail.is_empty() {
                let mut parts = tail.split_whitespace();
                if let Some(first) = parts.next() {
                    if Path::new(first).is_dir() {
                        directory = first.to_string();
                        let rest = parts.collect::<Vec<_>>().join(" ");
                        if !rest.trim().is_empty() {
                            command = rest.trim().to_string();
                        }
                    } else {
                        command = tail.to_string();
                    }
                }
            }

            if !Path::new(&directory).is_dir() {
                app.push_message(ChatMessage::error(format!(
                    "Directory not found: {directory}"
                )));
                return false;
            }

            let stop = Arc::new(AtomicBool::new(false));
            let watch_tx = watch_msg_sender(&tx);
            let handle = watcher::spawn_qa_watch_worker(
                directory.clone(),
                command.clone(),
                watch_tx,
                stop.clone(),
            );
            qa_watch_state.stop_flag = Some(stop);
            qa_watch_state.handle = Some(handle);
            qa_watch_state.directory = Some(directory.clone());
            qa_watch_state.command = Some(command.clone());
            app.qa_mode_enabled = true;
            app.qa_command = command.clone();
            app.set_status(format!("QA watch started: `{command}` on `{directory}`"));
            return false;
        }

        show_command_info_popup(
            app,
            raw,
            "Usage: /qa start [dir] [command...]\n       /qa stop\n       /qa status".to_string(),
        );
        return false;
    }

    if lowered.starts_with("/watch ") {
        let directory = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if directory.is_empty() {
            show_command_info_popup(app, raw, "Usage: /watch <dir>".to_string());
            return false;
        }
        if !Path::new(directory).is_dir() {
            app.push_message(ChatMessage::error(format!(
                "Directory not found: {directory}"
            )));
            return false;
        }
        if watch_state.is_running() {
            show_command_info_popup(
                app,
                raw,
                "Watch mode is already active. Use /unwatch first.".to_string(),
            );
            return false;
        }

        let stop = Arc::new(AtomicBool::new(false));
        let watch_tx = watch_msg_sender(&tx);
        let handle = watcher::spawn_watch_worker(
            directory.to_string(),
            "Explain the changes in these files".to_string(),
            watch_tx,
            rpc_cmd_tx.clone(),
            stop.clone(),
        );

        watch_state.stop_flag = Some(stop);
        watch_state.handle = Some(handle);
        watch_state.directory = Some(directory.to_string());
        app.set_status(format!("Watching {directory} for changes"));
        return false;
    }

    if lowered == "/unwatch" {
        if watch_state.is_running() {
            watch_state.stop();
            app.set_status("Watch mode stopped");
        } else {
            show_command_info_popup(app, raw, "No active watch task.".to_string());
        }
        return false;
    }

    if lowered.starts_with("/plan ") {
        const PLAN_REPLY_TIMEOUT_SECS: u64 = 130;

        let request = raw.splitn(2, ' ').nth(1).unwrap_or("").trim().to_string();
        if request.is_empty() {
            show_command_info_popup(app, raw, "Usage: /plan <task description>".to_string());
            return false;
        }
        // Ask the AI to generate a plan
        let plan_prompt = format!(
            "Generate a step-by-step plan for the following task. \
Return ONLY a numbered list (1. step, 2. step, etc.) with no other text.\n\n\
Task: {request}"
        );
        app.plan_original_request = request.clone();
        app.push_message(ChatMessage::user(format!("/plan {request}")));
        app.start_waiting();
        let tx2 = tx.clone();
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        if rpc_cmd_tx
            .send(RpcCommand::ChatStreaming {
                message: plan_prompt,
                request_id: app.next_request_id(),
                reply: reply_tx,
            })
            .is_err()
        {
            app.stop_waiting();
            app.push_message(ChatMessage::error(
                "Failed to send /plan request: RPC worker unavailable",
            ));
            return false;
        }
        let request_clone = request.clone();
        thread::spawn(move || {
            match reply_rx.recv_timeout(Duration::from_secs(PLAN_REPLY_TIMEOUT_SECS)) {
                Ok(Ok(content)) => {
                    // Parse numbered steps
                    let steps: Vec<String> = content
                        .lines()
                        .filter(|l| {
                            let t = l.trim();
                            !t.is_empty()
                                && t.chars()
                                    .next()
                                    .map(|c| c.is_ascii_digit())
                                    .unwrap_or(false)
                        })
                        .map(|l| {
                            // strip "1. " prefix
                            let t = l.trim();
                            t.find(". ")
                                .map(|i| t[i + 2..].to_string())
                                .unwrap_or_else(|| t.to_string())
                        })
                        .collect();
                    if steps.is_empty() {
                        let _ = tx2.send(ServerMsg::Error {
                            message: format!(
                                "Could not parse plan steps from response:\n{content}"
                            ),
                        });
                    } else {
                        let _ = tx2.send(ServerMsg::SystemMessage {
                            content: format!("__PLAN__:{request_clone}:{}", steps.join("\n")),
                        });
                    }
                }
                Ok(Err(e)) => {
                    let _ = tx2.send(ServerMsg::Error { message: e });
                }
                Err(mpsc::RecvTimeoutError::Timeout) => {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "Timed out waiting for /plan response".into(),
                    });
                }
                Err(mpsc::RecvTimeoutError::Disconnected) => {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "RPC unavailable".into(),
                    });
                }
            }
        });
        return false;
    }

    app.push_message(ChatMessage::error(format!(
        "Unknown command: {raw}\nType /help to see available commands"
    )));
    false
}

// ── Watch mode helpers ───────────────────────────────────────────────
