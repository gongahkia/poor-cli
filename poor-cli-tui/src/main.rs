/// Entry point for the poor-cli Rust TUI.
use std::collections::{HashMap, HashSet, VecDeque};
use std::fs;
use std::io;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::{Duration, UNIX_EPOCH};

use clap::Parser;
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::prelude::*;
use serde_json::Value;

use poor_cli_tui::app::{App, ChatMessage, MessageRole, ProviderEntry, ResponseMode, ThemeMode};
use poor_cli_tui::input::{self, InputAction};
use poor_cli_tui::rpc::{run_rpc_worker, RpcClient, RpcCommand, ServerNotification};
use poor_cli_tui::ui;

// ── CLI arguments ────────────────────────────────────────────────────

#[derive(Parser, Debug)]
#[command(name = "poor-cli-tui", about = "poor-cli TUI — AI coding assistant")]
struct Cli {
    /// Override provider for this session (gemini, openai, anthropic, ollama)
    #[arg(long)]
    provider: Option<String>,
    /// Override model for this session
    #[arg(long)]
    model: Option<String>,
    /// Run poor-cli in a specific working directory
    #[arg(long)]
    cwd: Option<String>,
    /// Permission behavior for tool execution
    #[arg(long, value_parser = ["prompt", "auto-safe", "danger-full-access"])]
    permission_mode: Option<String>,
    /// Disable permission prompts and allow all operations
    #[arg(long)]
    dangerously_skip_permissions: bool,
    /// Python binary to use (default: python3)
    #[arg(long, default_value = "python3")]
    python: String,
}

// ── Background message from server thread ────────────────────────────

#[allow(dead_code)]
enum ServerMsg {
    Initialized {
        provider: String,
        model: String,
        version: String,
    },
    ChatResponse {
        content: String,
    },
    SystemMessage {
        content: String,
    },
    Providers {
        providers: Vec<ProviderEntry>,
    },
    ProviderSwitched {
        provider: String,
        model: String,
    },
    Error {
        message: String,
    },
    // ── Streaming notifications ───
    StreamChunk {
        chunk: String,
        done: bool,
        reason: Option<String>,
    },
    ToolEvent {
        event_type: String,
        tool_name: String,
        tool_args: Value,
        tool_result: String,
        diff: String,
        iteration_index: u32,
        iteration_cap: u32,
    },
    PermissionRequest {
        tool_name: String,
        tool_args: Value,
        prompt_id: String,
    },
    Progress {
        phase: String,
        message: String,
        iteration_index: u32,
        iteration_cap: u32,
    },
    CostUpdate {
        input_tokens: u64,
        output_tokens: u64,
    },
}

#[derive(Default)]
struct WatchState {
    stop_flag: Option<Arc<AtomicBool>>,
    handle: Option<thread::JoinHandle<()>>,
    directory: Option<String>,
}

impl WatchState {
    fn is_running(&self) -> bool {
        self.handle.is_some()
    }

    fn stop(&mut self) {
        if let Some(flag) = &self.stop_flag {
            flag.store(true, Ordering::SeqCst);
        }
        if let Some(handle) = self.handle.take() {
            let _ = handle.join();
        }
        self.stop_flag = None;
        self.directory = None;
    }
}

// ── Main ─────────────────────────────────────────────────────────────

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;
    let result = run_app(&mut terminal, cli);

    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    match result {
        Ok(summary) => {
            if !summary.is_empty() {
                println!("\n{summary}");
            }
            Ok(())
        }
        Err(err) => {
            eprintln!("Error: {err}");
            std::process::exit(1);
        }
    }
}

fn run_app(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    cli: Cli,
) -> Result<String, Box<dyn std::error::Error>> {
    let mut app = App::new();
    app.cwd = cli.cwd.clone().unwrap_or_else(|| {
        std::env::current_dir()
            .ok()
            .and_then(|p| p.to_str().map(|s| s.to_string()))
            .unwrap_or_else(|| ".".into())
    });

    let (tx, rx) = mpsc::channel::<ServerMsg>();
    let (rpc_cmd_tx, rpc_cmd_rx) = mpsc::channel::<RpcCommand>();

    let python_bin = cli.python.clone();
    let cwd = cli.cwd.clone();
    let provider = cli.provider.clone();
    let model = cli.model.clone();
    let permission_mode = if cli.dangerously_skip_permissions {
        Some("danger-full-access".to_string())
    } else {
        cli.permission_mode.clone()
    };

    let tx_init = tx.clone();
    let tx_notif = tx.clone();
    thread::spawn(
        move || match RpcClient::spawn_with_notifications(&python_bin, cwd.as_deref()) {
            Ok((client, notification_rx)) => {
                // Spawn notification reader thread → maps ServerNotification → ServerMsg
                thread::spawn(move || loop {
                    match notification_rx.recv() {
                        Ok(notif) => {
                            let msg = match notif {
                                ServerNotification::StreamChunk {
                                    chunk,
                                    done,
                                    reason,
                                    ..
                                } => ServerMsg::StreamChunk {
                                    chunk,
                                    done,
                                    reason,
                                },
                                ServerNotification::ToolEvent {
                                    event_type,
                                    tool_name,
                                    tool_args,
                                    tool_result,
                                    diff,
                                    iteration_index,
                                    iteration_cap,
                                    ..
                                } => ServerMsg::ToolEvent {
                                    event_type,
                                    tool_name,
                                    tool_args,
                                    tool_result,
                                    diff,
                                    iteration_index,
                                    iteration_cap,
                                },
                                ServerNotification::PermissionRequest {
                                    tool_name,
                                    tool_args,
                                    prompt_id,
                                    ..
                                } => ServerMsg::PermissionRequest {
                                    tool_name,
                                    tool_args,
                                    prompt_id,
                                },
                                ServerNotification::Progress {
                                    phase,
                                    message,
                                    iteration_index,
                                    iteration_cap,
                                    ..
                                } => ServerMsg::Progress {
                                    phase,
                                    message,
                                    iteration_index,
                                    iteration_cap,
                                },
                                ServerNotification::CostUpdate {
                                    input_tokens,
                                    output_tokens,
                                    ..
                                } => ServerMsg::CostUpdate {
                                    input_tokens,
                                    output_tokens,
                                },
                            };
                            if tx_notif.send(msg).is_err() {
                                break;
                            }
                        }
                        Err(_) => break,
                    }
                });

                match client.initialize(
                    provider.as_deref(),
                    model.as_deref(),
                    None,
                    permission_mode.as_deref(),
                ) {
                    Ok(init) => {
                        let (prov, mdl) = if let Some(caps) = &init.capabilities {
                            let prov = caps
                                .pointer("/providerInfo/name")
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string())
                                .unwrap_or_else(|| {
                                    provider.clone().unwrap_or_else(|| "gemini".into())
                                });
                            let mdl = caps
                                .pointer("/providerInfo/model")
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string())
                                .unwrap_or_else(|| {
                                    model
                                        .clone()
                                        .unwrap_or_else(|| "gemini-2.0-flash-exp".into())
                                });
                            (prov, mdl)
                        } else {
                            (
                                provider.clone().unwrap_or_else(|| "gemini".into()),
                                model
                                    .clone()
                                    .unwrap_or_else(|| "gemini-2.0-flash-exp".into()),
                            )
                        };
                        let _ = tx_init.send(ServerMsg::Initialized {
                            provider: prov,
                            model: mdl,
                            version: init.version.unwrap_or_else(|| "0.4.0".into()),
                        });
                        run_rpc_worker(client, rpc_cmd_rx);
                    }
                    Err(e) => {
                        let _ = tx_init.send(ServerMsg::Error {
                            message: format!("Initialization failed: {e}"),
                        });
                    }
                }
            }
            Err(e) => {
                let _ = tx_init.send(ServerMsg::Error {
                    message: format!("Failed to start server: {e}"),
                });
            }
        },
    );

    app.provider_name = cli.provider.unwrap_or_else(|| "gemini".into());
    app.model_name = cli.model.unwrap_or_else(|| "gemini-2.0-flash-exp".into());
    app.add_welcome();

    let cancel_token: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));
    let mut watch_state = WatchState::default();

    loop {
        terminal.draw(|f| ui::draw(f, &app))?;

        while let Ok(msg) = rx.try_recv() {
            match msg {
                ServerMsg::Initialized {
                    provider,
                    model,
                    version,
                } => {
                    app.provider_name = provider;
                    app.model_name = model;
                    app.version = version;
                    app.server_connected = true;
                    app.is_local_provider = app.provider_name == "ollama";
                    app.update_welcome();
                    if let Ok(cfg) = rpc_get_config_blocking(&rpc_cmd_tx) {
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
                        // Parse plan steps from internal format
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
                    app.push_message(ChatMessage::error(message));
                }
                ServerMsg::StreamChunk {
                    chunk,
                    done,
                    reason: _,
                } => {
                    if done {
                        app.finalize_streaming();
                        app.stop_waiting();
                        // Advance plan if we're executing plan steps
                        if !app.plan_steps.is_empty()
                            && app.plan_current_step < app.plan_steps.len()
                        {
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
            }
        }

        app.clear_old_status();
        app.tick_spinner();

        if event::poll(Duration::from_millis(100))? {
            let ev = event::read()?;
            match input::handle_event(&mut app, ev) {
                InputAction::Submit(text) => {
                    if handle_submit(
                        &mut app,
                        &tx,
                        &rpc_cmd_tx,
                        &cancel_token,
                        &mut watch_state,
                        &text,
                    ) {
                        break;
                    }
                }
                InputAction::Cancel => {
                    cancel_token.store(true, Ordering::SeqCst);
                    let _ = rpc_cmd_tx.send(RpcCommand::CancelRequest);
                    app.finalize_streaming();
                    app.stop_waiting();
                    app.set_status("Request cancelled");
                }
                InputAction::Quit => break,
                InputAction::ProviderSelected(idx) => {
                    if let Some(provider) = app.providers.get(idx) {
                        let name = provider.name.clone();
                        let model = provider.models.first().cloned();
                        app.set_status(format!("Switching to {name}..."));
                        let tx2 = tx.clone();
                        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
                        let _ = rpc_cmd_tx.send(RpcCommand::SwitchProvider {
                            provider: name,
                            model,
                            reply: reply_tx,
                        });
                        thread::spawn(move || {
                            if let Ok(Ok((prov, mdl))) = reply_rx.recv() {
                                let _ = tx2.send(ServerMsg::ProviderSwitched {
                                    provider: prov,
                                    model: mdl,
                                });
                            }
                        });
                    }
                }
                InputAction::PermissionAnswered(allowed) => {
                    let prompt_id = std::mem::take(&mut app.permission_prompt_id);
                    let _ = rpc_cmd_tx.send(RpcCommand::SendNotification {
                        method: "poor-cli/permissionRes".into(),
                        params: serde_json::json!({
                            "promptId": prompt_id,
                            "allowed": allowed,
                        }),
                    });
                }
                InputAction::PlanApproved => {
                    let step_idx = app.plan_current_step;
                    let step_desc = app.current_plan_step_description().map(|s| s.to_string());
                    let orig = app.plan_original_request.clone();
                    if let Some(desc) = step_desc {
                        let exec_msg = format!(
                            "Execute step {} of my plan: {}\n\nOriginal request: {}",
                            step_idx + 1,
                            desc,
                            orig,
                        );
                        let display = format!("[plan step {}] {}", step_idx + 1, desc);
                        if step_idx < app.plan_steps.len() {
                            app.plan_steps[step_idx].status =
                                poor_cli_tui::app::PlanStepStatus::Running;
                        }
                        send_chat_request(
                            &mut app,
                            &tx,
                            &rpc_cmd_tx,
                            &cancel_token,
                            exec_msg,
                            display,
                        );
                    }
                }
                InputAction::PlanCancelled => {
                    app.clear_plan();
                    app.set_status("Plan cancelled");
                }
                InputAction::Redraw => {}
                InputAction::None => {}
            }
        }
    }

    watch_state.stop();
    let _ = rpc_cmd_tx.send(RpcCommand::Shutdown);
    Ok(app.session_summary_text())
}

// ── Submit handler ───────────────────────────────────────────────────

fn handle_submit(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    text: &str,
) -> bool {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return false;
    }

    if let Some(prompt_name) = app.pending_prompt_save_name.clone() {
        if !trimmed.starts_with('/') {
            app.pending_prompt_save_name = None;
            match save_prompt(app, &prompt_name, trimmed) {
                Ok(path) => app.set_status(format!("Saved prompt: {}", path.display())),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return false;
        }

        app.pending_prompt_save_name = None;
        app.set_status("Prompt capture cancelled");
    }

    if trimmed.starts_with('/') {
        return handle_slash_command(app, tx, rpc_cmd_tx, cancel_token, watch_state, trimmed);
    }

    let backend_with_files = match with_context_files(app, trimmed) {
        Ok(message) => message,
        Err(error_message) => {
            app.push_message(ChatMessage::error(error_message));
            return false;
        }
    };
    let backend_message = with_pending_images(app, &backend_with_files);
    let backend_message = apply_response_mode_to_user_input(app.response_mode, &backend_message);
    send_chat_request(
        app,
        tx,
        rpc_cmd_tx,
        cancel_token,
        backend_message,
        trimmed.to_string(),
    );
    false
}

fn send_chat_request(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cancel_token: &Arc<AtomicBool>,
    backend_message: String,
    display_message: String,
) {
    const STREAM_REPLY_TIMEOUT_SECS: u64 = 130;

    cancel_token.store(false, Ordering::SeqCst);
    app.record_user_input(&display_message);
    app.push_message(ChatMessage::user(display_message));
    app.start_waiting();
    app.turn_input_tokens = 0;
    app.turn_output_tokens = 0;

    // Use streaming endpoint — notifications arrive via the notification channel
    let request_id = app.next_request_id();
    let tx2 = tx.clone();
    let cancel = cancel_token.clone();
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    if rpc_cmd_tx
        .send(RpcCommand::ChatStreaming {
            message: backend_message,
            request_id,
            reply: reply_tx,
        })
        .is_err()
    {
        app.stop_waiting();
        app.push_message(ChatMessage::error(
            "Failed to send request: RPC worker unavailable",
        ));
        return;
    }

    thread::spawn(move || {
        match reply_rx.recv_timeout(Duration::from_secs(STREAM_REPLY_TIMEOUT_SECS)) {
            Ok(Ok(_content)) => {
                // Streaming already delivered chunks via notifications.
                // The final result is ignored since finalize_streaming handles it.
            }
            Ok(Err(e)) => {
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error { message: e });
                }
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "Timed out waiting for backend response".into(),
                    });
                }
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error {
                        message: "RPC worker reply channel disconnected".into(),
                    });
                }
            }
        }
    });
}

const MAX_CONTEXT_FILES_PER_REQUEST: usize = 12;
const MAX_CONTEXT_BYTES_PER_FILE: usize = 32_000;
const MAX_CONTEXT_TOTAL_BYTES: usize = 180_000;

fn with_context_files(app: &mut App, message: &str) -> Result<String, String> {
    let inline_specs = extract_at_references(message)?;

    let mut resolved = Vec::<PathBuf>::new();
    let mut seen_paths = HashSet::<String>::new();
    let mut unresolved_refs = Vec::<String>::new();
    let mut ambiguous_refs = Vec::<String>::new();

    for spec in &inline_specs {
        let matches = resolve_context_spec(app, spec);
        if matches.is_empty() {
            unresolved_refs.push(spec.clone());
            continue;
        }

        if matches.len() > 1 {
            let preview = matches
                .iter()
                .take(3)
                .map(|path| format!("`{}`", display_project_path(app, path)))
                .collect::<Vec<_>>()
                .join(", ");
            ambiguous_refs.push(format!("`{spec}` -> {preview}"));
            continue;
        }

        let path = matches[0].clone();
        let key = path.to_string_lossy().to_string();
        if seen_paths.insert(key) {
            resolved.push(path);
        }
    }

    if !unresolved_refs.is_empty() || !ambiguous_refs.is_empty() {
        let mut lines =
            vec!["Cannot send message because one or more `@` references are invalid.".to_string()];
        if !unresolved_refs.is_empty() {
            lines.push(format!(
                "Unresolved: {}",
                unresolved_refs
                    .iter()
                    .map(|spec| format!("`@{spec}`"))
                    .collect::<Vec<_>>()
                    .join(", ")
            ));
        }
        if !ambiguous_refs.is_empty() {
            lines.push(format!("Ambiguous: {}", ambiguous_refs.join(" ; ")));
            lines.push(
                "Use a more specific path (or quote it) so each `@` maps to exactly one file."
                    .to_string(),
            );
        }
        lines
            .push("Tip: paths with spaces must be quoted like `@\"docs/My File.md\"`.".to_string());
        return Err(lines.join("\n"));
    }

    if !app.pinned_context_files.is_empty() {
        let pinned_resolved = resolve_context_specs(
            app,
            &app.pinned_context_files,
            MAX_CONTEXT_FILES_PER_REQUEST,
        );
        for path in pinned_resolved {
            if resolved.len() >= MAX_CONTEXT_FILES_PER_REQUEST {
                break;
            }
            let key = path.to_string_lossy().to_string();
            if seen_paths.insert(key) {
                resolved.push(path);
            }
        }
    }

    if resolved.is_empty() {
        return Ok(message.to_string());
    }

    let mut total_bytes = 0usize;
    let mut attached = Vec::new();
    let mut sections = Vec::new();

    for path in resolved {
        let bytes = match fs::read(&path) {
            Ok(bytes) => bytes,
            Err(_) => continue,
        };
        if bytes.contains(&0) {
            continue;
        }

        let content = if bytes.len() > MAX_CONTEXT_BYTES_PER_FILE {
            String::from_utf8_lossy(&bytes[..MAX_CONTEXT_BYTES_PER_FILE]).to_string()
        } else {
            String::from_utf8_lossy(&bytes).to_string()
        };

        if content.trim().is_empty() {
            continue;
        }

        let increment = content.len();
        if total_bytes + increment > MAX_CONTEXT_TOTAL_BYTES {
            break;
        }
        total_bytes += increment;

        let display = display_project_path(app, &path);
        let language = detect_language_from_path(&display);
        attached.push(display.clone());
        sections.push(format!(
            "File: {display}\n```{language}\n{}\n```",
            truncate_block(&content, MAX_CONTEXT_BYTES_PER_FILE)
        ));
    }

    if sections.is_empty() {
        return Ok(message.to_string());
    }

    let attached_summary = attached
        .iter()
        .take(3)
        .cloned()
        .collect::<Vec<_>>()
        .join(", ");
    let extra = attached.len().saturating_sub(3);
    if extra > 0 {
        app.set_status(format!(
            "Attached {} file refs via @ and pinned files ({attached_summary}, +{extra} more)",
            attached.len()
        ));
    } else {
        app.set_status(format!(
            "Attached {} file refs via @ and pinned files ({attached_summary})",
            attached.len()
        ));
    }

    Ok(format!(
        "{message}\n\nReferenced project files:\n\n{}",
        sections.join("\n\n")
    ))
}

fn extract_at_references(message: &str) -> Result<Vec<String>, String> {
    let mut seen = HashSet::new();
    let mut refs = Vec::new();
    let mut parse_errors = Vec::new();
    let chars: Vec<char> = message.chars().collect();
    let mut idx = 0usize;

    while idx < chars.len() {
        if chars[idx] != '@' {
            idx += 1;
            continue;
        }

        if !is_reference_boundary(idx.checked_sub(1).and_then(|i| chars.get(i).copied())) {
            idx += 1;
            continue;
        }

        let next_idx = idx + 1;
        if next_idx >= chars.len() || chars[next_idx].is_whitespace() {
            idx += 1;
            continue;
        }

        if chars[next_idx] == '"' || chars[next_idx] == '\'' {
            let quote = chars[next_idx];
            let mut end_idx = next_idx + 1;
            while end_idx < chars.len() && chars[end_idx] != quote {
                end_idx += 1;
            }
            if end_idx >= chars.len() {
                parse_errors.push("unterminated quoted @ reference".to_string());
                break;
            }

            let spec = chars[next_idx + 1..end_idx]
                .iter()
                .collect::<String>()
                .trim()
                .to_string();
            if spec.is_empty() {
                parse_errors.push("empty quoted @ reference".to_string());
            } else if seen.insert(spec.clone()) {
                refs.push(spec);
            }

            idx = end_idx + 1;
            continue;
        }

        let mut end_idx = next_idx;
        while end_idx < chars.len() && is_unquoted_reference_char(chars[end_idx]) {
            end_idx += 1;
        }

        let spec = chars[next_idx..end_idx]
            .iter()
            .collect::<String>()
            .trim()
            .to_string();
        if !spec.is_empty() && seen.insert(spec.clone()) {
            refs.push(spec);
        }

        idx = if end_idx > idx { end_idx } else { idx + 1 };
    }

    if parse_errors.is_empty() {
        Ok(refs)
    } else {
        Err(format!(
            "Invalid @ reference syntax: {}",
            parse_errors.join("; ")
        ))
    }
}

fn is_reference_boundary(previous: Option<char>) -> bool {
    match previous {
        None => true,
        Some(ch) => ch.is_whitespace() || matches!(ch, '(' | '[' | '{' | ',' | ';' | ':' | '<'),
    }
}

fn is_unquoted_reference_char(ch: char) -> bool {
    !ch.is_whitespace()
        && !matches!(
            ch,
            '"' | '\'' | '`' | ',' | ';' | ':' | ')' | ']' | '}' | '(' | '[' | '{'
        )
}

fn resolve_context_specs(app: &App, specs: &[String], limit: usize) -> Vec<PathBuf> {
    let mut out = Vec::new();
    let mut seen = HashSet::new();

    for spec in specs {
        for path in resolve_context_spec(app, spec) {
            let key = path.to_string_lossy().to_string();
            if seen.insert(key) {
                out.push(path);
            }
            if out.len() >= limit {
                return out;
            }
        }
    }

    out
}

fn resolve_context_spec(app: &App, spec: &str) -> Vec<PathBuf> {
    let cwd = Path::new(&app.cwd);
    let raw_path = PathBuf::from(spec);
    let candidate = if raw_path.is_absolute() {
        raw_path
    } else {
        cwd.join(raw_path)
    };

    if candidate.is_file() {
        return vec![candidate];
    }

    if candidate.is_dir() {
        return collect_directory_files(&candidate, 8);
    }

    find_suffix_matches(cwd, spec, 5)
}

fn collect_directory_files(root: &Path, limit: usize) -> Vec<PathBuf> {
    let mut queue = VecDeque::from([root.to_path_buf()]);
    let mut files = Vec::new();

    while let Some(dir) = queue.pop_front() {
        let entries = match fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };

        let mut sorted_entries = entries.flatten().collect::<Vec<_>>();
        sorted_entries.sort_by_key(|entry| entry.file_name().to_string_lossy().to_string());

        for entry in sorted_entries {
            let path = entry.path();
            if path.is_dir() {
                let name = entry.file_name().to_string_lossy().to_string();
                if should_skip_dir(&name) {
                    continue;
                }
                queue.push_back(path);
                continue;
            }

            if path.is_file() {
                files.push(path);
                if files.len() >= limit {
                    return files;
                }
            }
        }
    }

    files
}

fn find_suffix_matches(root: &Path, suffix: &str, limit: usize) -> Vec<PathBuf> {
    let mut queue = VecDeque::from([root.to_path_buf()]);
    let mut matches = Vec::new();
    let normalized = suffix.trim_start_matches("./");

    while let Some(dir) = queue.pop_front() {
        let entries = match fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };

        let mut sorted_entries = entries.flatten().collect::<Vec<_>>();
        sorted_entries.sort_by_key(|entry| entry.file_name().to_string_lossy().to_string());

        for entry in sorted_entries {
            let path = entry.path();
            if path.is_dir() {
                let name = entry.file_name().to_string_lossy().to_string();
                if should_skip_dir(&name) {
                    continue;
                }
                queue.push_back(path);
                continue;
            }

            if !path.is_file() {
                continue;
            }

            let rel = path
                .strip_prefix(root)
                .ok()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_else(|| path.to_string_lossy().to_string());
            if rel == normalized || rel.ends_with(normalized) {
                matches.push(path);
                if matches.len() >= limit {
                    return matches;
                }
            }
        }
    }

    matches
}

fn display_project_path(app: &App, path: &Path) -> String {
    let cwd = Path::new(&app.cwd);
    path.strip_prefix(cwd)
        .ok()
        .map(|p| p.to_string_lossy().to_string())
        .unwrap_or_else(|| path.to_string_lossy().to_string())
}

fn with_pending_images(app: &mut App, message: &str) -> String {
    if app.pending_images.is_empty() {
        return message.to_string();
    }

    let queued = std::mem::take(&mut app.pending_images);
    let attachment_lines = queued
        .iter()
        .map(|p| format!("- {p}"))
        .collect::<Vec<_>>()
        .join("\n");

    format!(
        "{message}\n\nAttached image files (paths):\n{attachment_lines}\n\nUse these images as context when possible."
    )
}

fn apply_response_mode_to_user_input(mode: ResponseMode, user_input: &str) -> String {
    let mode_instruction = match mode {
        ResponseMode::Poor => {
            "Response mode is poor. Keep the answer as short as possible while still correct. \
Use minimal tokens and avoid extra explanation unless explicitly requested."
        }
        ResponseMode::Rich => {
            "Response mode is rich. Prioritize quality, completeness, and clear structure. \
Cover important reasoning and tradeoffs when relevant."
        }
    };

    format!("{mode_instruction}\n\nUser request:\n{user_input}")
}

// ── Slash command handler ─────────────────────────────────────────────

fn handle_slash_command(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    cmd: &str,
) -> bool {
    let raw = cmd.trim();
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
  /quit, /exit         Exit poor-cli and print session summary\n\
  /clear               Clear conversation history\n\
  /clear-output        Clear visible output, keep backend history\n\
  /history [N]         Show recent session messages\n\
  /sessions            List recent sessions\n\
  /new-session         Start a fresh session\n\
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
  /copy                Copy last assistant response to clipboard\n\
  /run <command>       Run shell command through backend\n\
  /read <file>         Read a file from backend\n\
  /pwd                 Show current working directory\n\
  /ls [path]           List files (default: current directory)\n\
  /status              Show quick session status";
        app.push_message(ChatMessage::system(help));
        return false;
    }

    if lowered == "/clear" {
        app.messages.clear();
        app.add_welcome();
        app.last_user_message = None;
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
        app.push_message(ChatMessage::system(
            "Response mode set to **poor**.\nReplies will be terse and token-minimal.".to_string(),
        ));
        return false;
    }

    if lowered == "/my-treat" {
        app.response_mode = ResponseMode::Rich;
        app.push_message(ChatMessage::system(
            "Response mode set to **rich**.\nReplies will prioritize completeness and quality."
                .to_string(),
        ));
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
                app.push_message(ChatMessage::system(info));
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to fetch provider info: {e}"
            ))),
        }
        return false;
    }

    if lowered == "/providers" {
        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        let _ = rpc_cmd_tx.send(RpcCommand::ListProviders { reply: reply_tx });
        let tx2 = tx.clone();
        thread::spawn(move || match reply_rx.recv() {
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
                let _ = tx2.send(ServerMsg::SystemMessage { content: info });
            }
            Ok(Err(e)) => {
                let _ = tx2.send(ServerMsg::Error {
                    message: format!("Failed to list providers: {e}"),
                });
            }
            Err(_) => {
                let _ = tx2.send(ServerMsg::Error {
                    message: "Failed to list providers".into(),
                });
            }
        });
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
                app.push_message(ChatMessage::system(config));
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

                app.push_message(ChatMessage::system(lines.join("\n")));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to load settings: {e}"))),
        }
        return false;
    }

    if lowered.starts_with("/toggle ") {
        let key = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if key.is_empty() {
            app.push_message(ChatMessage::system("Usage: /toggle <key>".to_string()));
            return false;
        }

        match rpc_toggle_config_blocking(rpc_cmd_tx, key) {
            Ok(result) => {
                let value = result.get("value").cloned().unwrap_or(Value::Null);
                app.push_message(ChatMessage::system(format!(
                    "Toggled `{key}` to `{}`",
                    format_value_for_display(&value)
                )));
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
            app.push_message(ChatMessage::system("Usage: /set <key> <value>".to_string()));
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
                app.push_message(ChatMessage::system(format!(
                    "Updated `{key}` = `{}`",
                    format_value_for_display(&value)
                )));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Failed to set `{key}`: {e}"))),
        }
        return false;
    }

    if lowered == "/theme" {
        app.push_message(ChatMessage::system(format!(
            "Current theme: **{}**\nUse `/theme dark` or `/theme light`.",
            app.theme_mode.as_str()
        )));
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
                app.push_message(ChatMessage::system(format!(
                    "Theme set to **{}**.",
                    app.theme_mode.as_str()
                )));
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
                app.push_message(ChatMessage::system(message.to_string()));
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
                app.push_message(ChatMessage::system(message.to_string()));
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
                Ok(_) => app.push_message(ChatMessage::system(format!(
                    "Permission mode set to **{normalized}**"
                ))),
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
                app.push_message(ChatMessage::system(format!(
                    "Current permission mode: **{mode}**\nAvailable: prompt, auto-safe, danger-full-access\nSet with: `/permission-mode <mode>`"
                )));
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
                app.push_message(ChatMessage::system(info));
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
                    app.push_message(ChatMessage::system(
                        "No tool declarations returned by backend.".to_string(),
                    ));
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

                app.push_message(ChatMessage::system(lines.join("\n")));
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
                    app.push_message(ChatMessage::system(
                        "No messages in this session.".to_string(),
                    ));
                    return false;
                }

                let mut lines = Vec::new();
                for msg in messages {
                    let role = msg.get("role").and_then(|v| v.as_str()).unwrap_or("unknown");
                    let role_name = if role == "user" { "You" } else { "Assistant" };
                    let timestamp = msg.get("timestamp").and_then(|v| v.as_str()).unwrap_or("-");
                    let content = msg.get("content").and_then(|v| v.as_str()).unwrap_or("");
                    lines.push(format!(
                        "**{role_name}** ({timestamp})\n{}",
                        truncate_line(content, 260)
                    ));
                }

                app.push_message(ChatMessage::system(format!(
                    "**History (last {} messages):**\n\n{}",
                    lines.len(),
                    lines.join("\n\n")
                )));
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
                    app.push_message(ChatMessage::system("No previous sessions found.".to_string()));
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
                app.push_message(ChatMessage::system(lines.join("\n")));
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to list sessions: {e}"
            ))),
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
            );
        } else {
            app.push_message(ChatMessage::system(
                "No previous request to retry.".to_string(),
            ));
        }
        return false;
    }

    if lowered.starts_with("/search") {
        let term = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if term.is_empty() {
            app.push_message(ChatMessage::system("Usage: /search <term>".to_string()));
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
                    app.push_message(ChatMessage::system(format!("No matches for: {term}")));
                    return false;
                }

                let mut lines = Vec::new();
                for msg in matches {
                    let role = msg.get("role").and_then(|v| v.as_str()).unwrap_or("unknown");
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
                    response.push_str(&format!("\n\nShowing {} of {total_matches} matches.", lines.len()));
                }
                app.push_message(ChatMessage::system(response));
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
            app.push_message(ChatMessage::system(
                "No previous request to edit.".to_string(),
            ));
        }
        return false;
    }

    if lowered.starts_with("/add ") {
        let spec = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if spec.is_empty() {
            app.push_message(ChatMessage::system("Usage: /add <path>".to_string()));
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
            app.push_message(ChatMessage::system(
                "All matched files were already pinned.".to_string(),
            ));
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
            app.push_message(ChatMessage::system("Usage: /drop <path>".to_string()));
            return false;
        }

        let before = app.pinned_context_files.len();
        app.pinned_context_files
            .retain(|p| p != spec && !p.ends_with(&format!("/{spec}")));
        let removed = before.saturating_sub(app.pinned_context_files.len());

        if removed == 0 {
            app.push_message(ChatMessage::system(format!(
                "No pinned file matched: {spec}"
            )));
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
            app.push_message(ChatMessage::system(
                "No pinned context files.\nUse /add <path> or @path in a prompt.".to_string(),
            ));
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
            app.push_message(ChatMessage::system(lines.join("\n")));
        }
        return false;
    }

    if lowered == "/clear-files" {
        let removed = app.pinned_context_files.len();
        app.pinned_context_files.clear();
        app.set_status(format!("Cleared {removed} pinned context file(s)"));
        return false;
    }

    if lowered.starts_with("/run ") {
        let command = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if command.is_empty() {
            app.push_message(ChatMessage::system("Usage: /run <command>".to_string()));
            return false;
        }

        match rpc_execute_command_blocking(rpc_cmd_tx, command) {
            Ok(output) => app.push_message(ChatMessage::system(format!(
                "**Command:** `{command}`\n\n{}",
                truncate_block(&output, 1600)
            ))),
            Err(e) => app.push_message(ChatMessage::error(format!("Command failed: {e}"))),
        }
        return false;
    }

    if lowered.starts_with("/read ") {
        let file_path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if file_path.is_empty() {
            app.push_message(ChatMessage::system("Usage: /read <file>".to_string()));
            return false;
        }

        match rpc_read_file_blocking(rpc_cmd_tx, file_path) {
            Ok(content) => {
                let language = detect_language_from_path(file_path);
                app.push_message(ChatMessage::system(format!(
                    "File: `{file_path}`\n```{language}\n{}\n```",
                    truncate_block(&content, 3200)
                )));
            }
            Err(e) => app.push_message(ChatMessage::error(format!("Read failed: {e}"))),
        }
        return false;
    }

    if lowered == "/pwd" {
        app.push_message(ChatMessage::system(format!(
            "Current directory: `{}`",
            app.cwd
        )));
        return false;
    }

    if lowered == "/ls" || lowered.starts_with("/ls ") {
        let path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or(".");
        let command = format!("ls -la {}", shell_escape_single_quotes(path));
        match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
            Ok(output) => app.push_message(ChatMessage::system(format!(
                "**Listing:** `{path}`\n\n{}",
                truncate_block(&output, 1600)
            ))),
            Err(e) => app.push_message(ChatMessage::error(format!("ls failed: {e}"))),
        }
        return false;
    }

    if lowered == "/status" {
        let status = format!(
            "**Session Status:**\n\
Provider: {}/{}\n\
CWD: {}\n\
Response mode: {}\n\
Pinned files: {}\n\
Queued images: {}\n\
Watch mode: {}",
            app.provider_name,
            app.model_name,
            app.cwd,
            app.response_mode.as_str(),
            app.pinned_context_files.len(),
            app.pending_images.len(),
            if watch_state.is_running() {
                "active"
            } else {
                "inactive"
            }
        );
        app.push_message(ChatMessage::system(status));
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
                    app.push_message(ChatMessage::system(
                        "Checkpoint system not available.".to_string(),
                    ));
                    return false;
                }

                let checkpoints = payload
                    .get("checkpoints")
                    .and_then(|v| v.as_array())
                    .cloned()
                    .unwrap_or_default();
                if checkpoints.is_empty() {
                    app.push_message(ChatMessage::system(
                        "No checkpoints available.".to_string(),
                    ));
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
                    let description = cp
                        .get("description")
                        .and_then(|v| v.as_str())
                        .unwrap_or("");
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
                app.push_message(ChatMessage::system(lines.join("\n")));
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
                let file_count = payload.get("fileCount").and_then(|v| v.as_u64()).unwrap_or(0);
                app.push_message(ChatMessage::system(format!(
                    "Created checkpoint `{checkpoint_id}` with {file_count} file(s)."
                )));
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
                app.push_message(ChatMessage::system(format!(
                    "Restored checkpoint `{checkpoint_id}` ({restored} file(s) restored)."
                )));
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
            app.push_message(ChatMessage::system(
                "Usage: /diff <file1> <file2>".to_string(),
            ));
            return false;
        }

        match rpc_compare_files_blocking(rpc_cmd_tx, parts[1], parts[2]) {
            Ok(diff) => {
                if diff.trim() == "(No differences)" {
                    app.push_message(ChatMessage::system(diff));
                } else {
                    app.push_message(ChatMessage::diff_view(
                        format!("{} vs {}", parts[1], parts[2]),
                        truncate_block(&diff, 20_000),
                    ));
                }
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Failed to compare files: {e}"
            ))),
        }
        return false;
    }

    if lowered == "/export" || lowered.starts_with("/export ") {
        let export_format = raw.split_whitespace().nth(1).unwrap_or("json").to_lowercase();
        if !matches!(export_format.as_str(), "json" | "md" | "txt" | "markdown") {
            app.push_message(ChatMessage::system(
                "Usage: /export [json|md|txt]".to_string(),
            ));
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
                let size_bytes = payload.get("sizeBytes").and_then(|v| v.as_u64()).unwrap_or(0);
                app.push_message(ChatMessage::system(format!(
                    "Export complete.\n\nFile: `{file_path}`\nFormat: `{format_value}`\nMessages: {message_count}\nSize: {}",
                    format_bytes(size_bytes)
                )));
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
            app.push_message(ChatMessage::system(
                "No assistant response to copy.".to_string(),
            ));
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
        app.push_message(ChatMessage::system(text));
        return false;
    }

    if lowered == "/commit --apply-last" {
        if let Some(last) = last_assistant_message(app) {
            let subject = first_line(&last);
            if subject.is_empty() {
                app.push_message(ChatMessage::system(
                    "Last assistant response was empty; nothing to commit.".to_string(),
                ));
                return false;
            }

            let command = format!("git commit -m {}", shell_escape_single_quotes(&subject));
            match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
                Ok(output) => app.push_message(ChatMessage::system(format!(
                    "Commit executed with message: `{subject}`\n\n{}",
                    truncate_block(&output, 1200)
                ))),
                Err(e) => app.push_message(ChatMessage::error(format!("Commit failed: {e}"))),
            }
        } else {
            app.push_message(ChatMessage::system(
                "No assistant response found to apply as commit message.".to_string(),
            ));
        }
        return false;
    }

    if lowered.starts_with("/commit --apply ") {
        let msg = raw.splitn(3, ' ').nth(2).map(str::trim).unwrap_or("");
        if msg.is_empty() {
            app.push_message(ChatMessage::system(
                "Usage: /commit --apply <message>".to_string(),
            ));
            return false;
        }
        let command = format!("git commit -m {}", shell_escape_single_quotes(msg));
        match rpc_execute_command_blocking(rpc_cmd_tx, &command) {
            Ok(output) => app.push_message(ChatMessage::system(format!(
                "Commit executed.\n\n{}",
                truncate_block(&output, 1200)
            ))),
            Err(e) => app.push_message(ChatMessage::error(format!("Commit failed: {e}"))),
        }
        return false;
    }

    if lowered == "/commit" {
        match rpc_execute_command_blocking(rpc_cmd_tx, "git diff --staged") {
            Ok(diff) => {
                if diff.trim().is_empty() || diff.trim() == "(No output)" {
                    app.push_message(ChatMessage::system(
                        "No staged changes. Stage files with `git add` first.".to_string(),
                    ));
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
            app.push_message(ChatMessage::system("Nothing to review.".to_string()));
            return false;
        }

        let prompt = build_review_prompt(&language, &code);
        send_chat_request(app, tx, rpc_cmd_tx, cancel_token, prompt, raw.to_string());
        return false;
    }

    if lowered == "/test" {
        app.push_message(ChatMessage::system("Usage: /test <file>".to_string()));
        return false;
    }

    if lowered.starts_with("/test ") {
        let file_path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if file_path.is_empty() {
            app.push_message(ChatMessage::system("Usage: /test <file>".to_string()));
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
        send_chat_request(app, tx, rpc_cmd_tx, cancel_token, prompt, raw.to_string());
        return false;
    }

    if lowered.starts_with("/save-prompt ") {
        let mut parts = raw.splitn(3, ' ');
        let _ = parts.next();
        let name = parts.next().unwrap_or("").trim();
        let content = parts.next().unwrap_or("").trim();

        if name.is_empty() {
            app.push_message(ChatMessage::system(
                "Usage: /save-prompt <name> [text]".to_string(),
            ));
            return false;
        }

        if content.is_empty() {
            app.pending_prompt_save_name = Some(name.to_string());
            app.push_message(ChatMessage::system(format!(
                "Enter prompt text and press Enter to save as **{name}**.\n\
Submitting any slash command will cancel capture."
            )));
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
            app.push_message(ChatMessage::system("Usage: /use <name>".to_string()));
            return false;
        }

        match load_prompt(app, name) {
            Ok(content) => {
                app.push_message(ChatMessage::system(format!("Loaded prompt: {name}")));
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    content,
                    format!("/use {name}"),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return false;
    }

    if lowered == "/prompts" {
        match list_prompts(app) {
            Ok(entries) if entries.is_empty() => {
                app.push_message(ChatMessage::system("No saved prompts.".to_string()));
            }
            Ok(entries) => {
                let mut lines = vec!["**Saved Prompts:**".to_string(), String::new()];
                for (name, preview) in entries {
                    lines.push(format!("- **{name}**: {preview}"));
                }
                app.push_message(ChatMessage::system(lines.join("\n")));
            }
            Err(e) => app.push_message(ChatMessage::error(e)),
        }
        return false;
    }

    if lowered.starts_with("/image ") {
        let image_path = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if image_path.is_empty() {
            app.push_message(ChatMessage::system("Usage: /image <path>".to_string()));
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

    if lowered.starts_with("/watch ") {
        let directory = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if directory.is_empty() {
            app.push_message(ChatMessage::system("Usage: /watch <dir>".to_string()));
            return false;
        }
        if !Path::new(directory).is_dir() {
            app.push_message(ChatMessage::error(format!(
                "Directory not found: {directory}"
            )));
            return false;
        }
        if watch_state.is_running() {
            app.push_message(ChatMessage::system(
                "Watch mode is already active. Use /unwatch first.".to_string(),
            ));
            return false;
        }

        let stop = Arc::new(AtomicBool::new(false));
        let handle = spawn_watch_worker(
            directory.to_string(),
            "Explain the changes in these files".to_string(),
            tx.clone(),
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
            app.push_message(ChatMessage::system("No active watch task.".to_string()));
        }
        return false;
    }

    if lowered.starts_with("/plan ") {
        const PLAN_REPLY_TIMEOUT_SECS: u64 = 130;

        let request = raw.splitn(2, ' ').nth(1).unwrap_or("").trim().to_string();
        if request.is_empty() {
            app.push_message(ChatMessage::system(
                "Usage: /plan <task description>".to_string(),
            ));
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

fn spawn_watch_worker(
    directory: String,
    prompt: String,
    tx: mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: mpsc::Sender<RpcCommand>,
    stop: Arc<AtomicBool>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let root = PathBuf::from(&directory);
        let mut previous = snapshot_directory(&root);

        while !stop.load(Ordering::SeqCst) {
            thread::sleep(Duration::from_secs(2));
            if stop.load(Ordering::SeqCst) {
                break;
            }

            let current = snapshot_directory(&root);
            let changed = detect_changed_files(&previous, &current);
            previous = current;

            if changed.is_empty() {
                continue;
            }

            let preview = changed
                .iter()
                .take(8)
                .map(|p| format!("- {p}"))
                .collect::<Vec<_>>()
                .join("\n");
            let _ = tx.send(ServerMsg::SystemMessage {
                content: format!(
                    "Watch mode detected {} changed file(s) in `{directory}`:\n{preview}",
                    changed.len()
                ),
            });

            let chat_prompt = build_watch_prompt(&changed, &prompt);
            let (reply_tx, reply_rx) = mpsc::sync_channel(1);
            if rpc_cmd_tx
                .send(RpcCommand::Chat {
                    message: chat_prompt,
                    reply: reply_tx,
                })
                .is_err()
            {
                let _ = tx.send(ServerMsg::Error {
                    message: "Watch mode stopped: RPC worker unavailable".to_string(),
                });
                break;
            }

            let mut waited_secs = 0u64;
            loop {
                if stop.load(Ordering::SeqCst) {
                    break;
                }

                match reply_rx.recv_timeout(Duration::from_secs(1)) {
                    Ok(Ok(content)) => {
                        let _ = tx.send(ServerMsg::ChatResponse { content });
                        break;
                    }
                    Ok(Err(e)) => {
                        let _ = tx.send(ServerMsg::Error {
                            message: format!("Watch mode analysis failed: {e}"),
                        });
                        break;
                    }
                    Err(mpsc::RecvTimeoutError::Timeout) => {
                        waited_secs += 1;
                        if waited_secs >= 240 {
                            let _ = tx.send(ServerMsg::Error {
                                message: "Watch mode timed out waiting for backend response"
                                    .to_string(),
                            });
                            break;
                        }
                    }
                    Err(mpsc::RecvTimeoutError::Disconnected) => {
                        let _ = tx.send(ServerMsg::Error {
                            message: "Watch mode lost backend reply channel".to_string(),
                        });
                        break;
                    }
                }
            }
        }
    })
}

fn snapshot_directory(root: &Path) -> HashMap<String, u64> {
    let mut snapshot = HashMap::new();
    let mut stack = vec![root.to_path_buf()];

    while let Some(dir) = stack.pop() {
        let entries = match fs::read_dir(&dir) {
            Ok(entries) => entries,
            Err(_) => continue,
        };

        for entry in entries.flatten() {
            let path = entry.path();
            let file_name = entry.file_name();
            let name = file_name.to_string_lossy();

            if path.is_dir() {
                if should_skip_dir(&name) {
                    continue;
                }
                stack.push(path);
                continue;
            }

            if !path.is_file() {
                continue;
            }

            let modified = entry
                .metadata()
                .ok()
                .and_then(|m| m.modified().ok())
                .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);

            snapshot.insert(path.to_string_lossy().to_string(), modified);
        }
    }

    snapshot
}

fn should_skip_dir(name: &str) -> bool {
    matches!(
        name,
        ".git" | "target" | "node_modules" | ".venv" | "venv" | "__pycache__"
    )
}

fn detect_changed_files(
    previous: &HashMap<String, u64>,
    current: &HashMap<String, u64>,
) -> Vec<String> {
    let mut changed = current
        .iter()
        .filter_map(|(path, mtime)| {
            if previous.get(path).copied() != Some(*mtime) {
                Some(path.clone())
            } else {
                None
            }
        })
        .collect::<Vec<_>>();
    changed.sort();
    changed
}

fn build_watch_prompt(changed: &[String], user_prompt: &str) -> String {
    let mut sections = vec![
        "The following files changed. Analyze what changed, why it matters, and any risks."
            .to_string(),
    ];

    for path in changed.iter().take(5) {
        let content = match fs::read(path) {
            Ok(bytes) => {
                if bytes.len() > 250_000 {
                    format!(
                        "(file too large to include fully: {} bytes, showing first 250000 bytes)\n{}",
                        bytes.len(),
                        String::from_utf8_lossy(&bytes[..250_000])
                    )
                } else {
                    String::from_utf8_lossy(&bytes).to_string()
                }
            }
            Err(e) => format!("(unable to read file: {e})"),
        };

        sections.push(format!(
            "File: {path}\n```\n{}\n```",
            truncate_block(&content, 4000)
        ));
    }

    sections.push(format!("User request: {user_prompt}"));
    sections.join("\n\n")
}

// ── Prompt builders and parsing helpers ──────────────────────────────

fn detect_language_from_path(file_path: &str) -> &'static str {
    let ext = Path::new(file_path)
        .extension()
        .and_then(|e| e.to_str())
        .map(|e| e.to_lowercase())
        .unwrap_or_default();

    match ext.as_str() {
        "py" => "python",
        "js" => "javascript",
        "ts" | "tsx" => "typescript",
        "jsx" => "javascript",
        "rs" => "rust",
        "go" => "go",
        "java" => "java",
        "c" | "h" => "c",
        "cpp" | "cc" | "hpp" => "cpp",
        "rb" => "ruby",
        "php" => "php",
        "swift" => "swift",
        "kt" => "kotlin",
        "scala" => "scala",
        "lua" => "lua",
        "sh" => "bash",
        "sql" => "sql",
        "html" => "html",
        "css" => "css",
        "json" => "json",
        "yaml" | "yml" => "yaml",
        "toml" => "toml",
        "md" => "markdown",
        _ => "text",
    }
}

fn build_commit_prompt(diff: &str) -> String {
    format!(
        "You are generating a git commit message.\n\
Generate a concise Conventional Commit message based on the staged diff.\n\
Return ONLY the commit message text, with no explanation.\n\n\
Staged diff:\n```diff\n{diff}\n```"
    )
}

fn build_review_prompt(language: &str, code: &str) -> String {
    format!(
        "You are an expert code reviewer.\n\
Review the following {language} code. Focus on bugs, regressions, security issues, and maintainability risks.\n\
Provide findings ordered by severity, then concise recommendations.\n\n\
Code:\n```{language}\n{code}\n```"
    )
}

fn build_test_prompt(language: &str, code: &str) -> String {
    format!(
        "Generate high-quality unit tests for the following {language} code.\n\
Prioritize behavior coverage, edge cases, and failure paths.\n\
Return test code only unless explanation is required for clarity.\n\n\
Code:\n```{language}\n{code}\n```"
    )
}

fn bool_icon(value: Option<bool>) -> &'static str {
    if value.unwrap_or(false) {
        "✓"
    } else {
        "✗"
    }
}

fn bool_label(value: bool) -> &'static str {
    if value {
        "on"
    } else {
        "off"
    }
}

fn format_value_for_display(value: &Value) -> String {
    match value {
        Value::Null => "null".to_string(),
        Value::Bool(b) => b.to_string(),
        Value::Number(n) => n.to_string(),
        Value::String(s) => s.clone(),
        Value::Array(_) | Value::Object(_) => {
            serde_json::to_string(value).unwrap_or_else(|_| "<unserializable>".to_string())
        }
    }
}

fn parse_value_literal(raw: &str) -> Value {
    let lower = raw.trim().to_lowercase();
    match lower.as_str() {
        "true" | "on" | "yes" | "enabled" => return Value::Bool(true),
        "false" | "off" | "no" | "disabled" => return Value::Bool(false),
        _ => {}
    }

    if let Ok(n) = raw.parse::<i64>() {
        return Value::Number(serde_json::Number::from(n));
    }
    if let Ok(f) = raw.parse::<f64>() {
        if let Some(num) = serde_json::Number::from_f64(f) {
            return Value::Number(num);
        }
    }
    if (raw.starts_with('{') && raw.ends_with('}')) || (raw.starts_with('[') && raw.ends_with(']'))
    {
        if let Ok(parsed) = serde_json::from_str::<Value>(raw) {
            return parsed;
        }
    }

    Value::String(raw.to_string())
}

fn first_line(text: &str) -> String {
    text.lines().next().unwrap_or("").trim().to_string()
}

fn truncate_line(text: &str, max_chars: usize) -> String {
    let mut out = String::new();
    for (i, ch) in text.chars().enumerate() {
        if i >= max_chars {
            out.push('…');
            return out;
        }
        out.push(ch);
    }
    out
}

fn truncate_block(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }

    let mut out = String::new();
    for (i, ch) in text.chars().enumerate() {
        if i >= max_chars {
            out.push_str("\n... (truncated)");
            break;
        }
        out.push(ch);
    }
    out
}

fn last_assistant_message(app: &App) -> Option<String> {
    app.messages
        .iter()
        .rev()
        .find(|m| matches!(m.role, MessageRole::Assistant))
        .map(|m| m.content.clone())
}

fn shell_escape_single_quotes(input: &str) -> String {
    format!("'{}'", input.replace('\'', "'\"'\"'"))
}

// ── Prompt library helpers ───────────────────────────────────────────

fn prompt_library_dir(app: &App) -> PathBuf {
    Path::new(&app.cwd).join(".poor-cli").join("prompts")
}

fn sanitize_prompt_name(name: &str) -> Result<String, String> {
    let trimmed = name.trim();
    if trimmed.is_empty() {
        return Err("Prompt name cannot be empty".to_string());
    }

    if !trimmed
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-')
    {
        return Err(
            "Prompt name must use only letters, numbers, '-' or '_' characters".to_string(),
        );
    }

    Ok(trimmed.to_string())
}

fn save_prompt(app: &App, name: &str, content: &str) -> Result<PathBuf, String> {
    let name = sanitize_prompt_name(name)?;
    let dir = prompt_library_dir(app);
    fs::create_dir_all(&dir).map_err(|e| format!("Failed to create prompts directory: {e}"))?;

    let path = dir.join(format!("{name}.txt"));
    fs::write(&path, content).map_err(|e| format!("Failed to save prompt: {e}"))?;
    Ok(path)
}

fn load_prompt(app: &App, name: &str) -> Result<String, String> {
    let name = sanitize_prompt_name(name)?;
    let path = prompt_library_dir(app).join(format!("{name}.txt"));
    fs::read_to_string(&path).map_err(|_| format!("Prompt not found: {name}"))
}

fn list_prompts(app: &App) -> Result<Vec<(String, String)>, String> {
    let dir = prompt_library_dir(app);
    if !dir.exists() {
        return Ok(vec![]);
    }

    let mut entries = vec![];
    for entry in fs::read_dir(&dir).map_err(|e| format!("Failed to read prompts directory: {e}"))? {
        let entry = entry.map_err(|e| format!("Failed to inspect prompt entry: {e}"))?;
        let path = entry.path();
        if path.extension().and_then(|e| e.to_str()) != Some("txt") {
            continue;
        }

        let name = path
            .file_stem()
            .and_then(|s| s.to_str())
            .unwrap_or("unknown")
            .to_string();
        let preview = fs::read_to_string(&path)
            .unwrap_or_else(|_| "(unable to read)".to_string())
            .replace('\n', " ");
        entries.push((name, truncate_line(preview.trim(), 60)));
    }

    entries.sort_by(|a, b| a.0.cmp(&b.0));
    Ok(entries)
}

// ── Blocking RPC helpers ─────────────────────────────────────────────

fn rpc_execute_command_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    command: &str,
) -> Result<String, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ExecuteCommand {
            command: command.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to send command to backend: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for backend command response".to_string())?
}

fn rpc_read_file_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    file_path: &str,
) -> Result<String, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ReadFile {
            file_path: file_path.to_string(),
            start_line: None,
            end_line: None,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to send read_file request: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for backend file read".to_string())?
}

fn rpc_get_config_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetConfig { reply: reply_tx })
        .map_err(|e| format!("Failed to request config: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for backend config".to_string())?
}

fn rpc_get_provider_info_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetProviderInfo { reply: reply_tx })
        .map_err(|e| format!("Failed to request provider info: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for provider info".to_string())?
}

fn rpc_get_tools_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetTools { reply: reply_tx })
        .map_err(|e| format!("Failed to request tools: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for tools".to_string())?
}

fn rpc_list_config_options_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListConfigOptions { reply: reply_tx })
        .map_err(|e| format!("Failed to request config options: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for config options".to_string())?
}

fn rpc_set_config_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    key_path: &str,
    value: Value,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetConfig {
            key_path: key_path.to_string(),
            value,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request config update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for config update".to_string())?
}

fn rpc_toggle_config_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    key_path: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ToggleConfig {
            key_path: key_path.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request config toggle: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for config toggle".to_string())?
}

fn rpc_clear_history_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<(), String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ClearHistory { reply: reply_tx })
        .map_err(|e| format!("Failed to request history clear: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for clear history response".to_string())?
}

fn rpc_list_sessions_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListSessions {
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request sessions: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for sessions response".to_string())?
}

fn rpc_list_history_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    count: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListHistory {
            count,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request history: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for history response".to_string())?
}

fn rpc_search_history_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    term: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SearchHistory {
            term: term.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request search: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for search response".to_string())?
}

fn rpc_list_checkpoints_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListCheckpoints {
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request checkpoints: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for checkpoints response".to_string())?
}

fn rpc_create_checkpoint_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    description: &str,
    operation_type: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CreateCheckpoint {
            description: description.to_string(),
            operation_type: operation_type.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request checkpoint creation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for checkpoint creation".to_string())?
}

fn rpc_restore_checkpoint_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    checkpoint_id: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RestoreCheckpoint {
            checkpoint_id: checkpoint_id.map(|s| s.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request checkpoint restore: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for checkpoint restore".to_string())?
}

fn rpc_compare_files_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    file1: &str,
    file2: &str,
) -> Result<String, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CompareFiles {
            file1: file1.to_string(),
            file2: file2.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request file comparison: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for file diff response".to_string())?
}

fn rpc_export_conversation_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    export_format: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ExportConversation {
            format: export_format.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request conversation export: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for export response".to_string())?
}

fn copy_to_clipboard(content: &str) -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        return copy_with_command("pbcopy", &[], content);
    }

    #[cfg(target_os = "windows")]
    {
        return copy_with_command("clip", &[], content);
    }

    #[cfg(target_os = "linux")]
    {
        for (bin, args) in [
            ("wl-copy", Vec::<&str>::new()),
            ("xclip", vec!["-selection", "clipboard"]),
            ("xsel", vec!["--clipboard", "--input"]),
        ] {
            if copy_with_command(bin, &args, content).is_ok() {
                return Ok(());
            }
        }
        return Err(
            "No clipboard utility found. Install wl-copy, xclip, or xsel.".to_string(),
        );
    }

    #[allow(unreachable_code)]
    Err("Clipboard is not supported on this platform.".to_string())
}

fn copy_with_command(bin: &str, args: &[&str], content: &str) -> Result<(), String> {
    let mut child = Command::new(bin)
        .args(args)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("Failed to run `{bin}`: {e}"))?;

    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write as _;
        stdin
            .write_all(content.as_bytes())
            .map_err(|e| format!("Failed writing to `{bin}` stdin: {e}"))?;
    }

    let status = child
        .wait()
        .map_err(|e| format!("Failed waiting for `{bin}`: {e}"))?;
    if status.success() {
        Ok(())
    } else {
        Err(format!("`{bin}` exited with status {status}"))
    }
}

fn format_bytes(bytes: u64) -> String {
    const UNITS: [&str; 5] = ["B", "KB", "MB", "GB", "TB"];
    let mut value = bytes as f64;
    let mut unit = 0usize;
    while value >= 1024.0 && unit < UNITS.len() - 1 {
        value /= 1024.0;
        unit += 1;
    }
    if unit == 0 {
        format!("{bytes} {}", UNITS[unit])
    } else {
        format!("{value:.1} {}", UNITS[unit])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn create_temp_workspace(prefix: &str) -> PathBuf {
        let ts = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time should move forward")
            .as_nanos();
        let root = std::env::temp_dir().join(format!("poor-cli-{prefix}-{ts}"));
        fs::create_dir_all(&root).expect("temp workspace should be created");
        root
    }

    fn build_app_for_root(root: &Path) -> App {
        let mut app = App::new();
        app.cwd = root.to_string_lossy().to_string();
        app
    }

    #[test]
    fn extract_at_references_supports_quotes_and_punctuation() {
        let refs = extract_at_references(
            r#"check (@src/main.rs), @"docs/My File.md" and @'notes/with spaces.md' a@b.com"#,
        )
        .expect("refs should parse");

        assert_eq!(
            refs,
            vec![
                "src/main.rs".to_string(),
                "docs/My File.md".to_string(),
                "notes/with spaces.md".to_string()
            ]
        );
    }

    #[test]
    fn extract_at_references_rejects_unterminated_quotes() {
        let error = extract_at_references(r#"read @"docs/missing quote.md"#)
            .expect_err("unterminated quote should error");
        assert!(error.contains("Invalid @ reference syntax"));
    }

    #[test]
    fn with_context_files_blocks_on_unresolved_or_ambiguous_refs() {
        let root = create_temp_workspace("refs-error");
        fs::create_dir_all(root.join("src")).expect("src dir");
        fs::create_dir_all(root.join("tests")).expect("tests dir");
        fs::write(root.join("src").join("main.rs"), "fn main() {}\n").expect("main src");
        fs::write(root.join("tests").join("main.rs"), "#[test]\nfn ok() {}\n").expect("main tests");

        let mut app = build_app_for_root(&root);
        let ambiguous = with_context_files(&mut app, "review @main.rs");
        assert!(ambiguous.is_err());

        let unresolved = with_context_files(&mut app, "review @missing.rs");
        assert!(unresolved.is_err());

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn with_context_files_accepts_quoted_paths_with_spaces() {
        let root = create_temp_workspace("refs-spaces");
        fs::create_dir_all(root.join("docs")).expect("docs dir");
        fs::write(root.join("docs").join("My File.md"), "# Title\n").expect("docs file");

        let mut app = build_app_for_root(&root);
        let merged = with_context_files(&mut app, r#"summarize @"docs/My File.md""#)
            .expect("quoted path should resolve");
        assert!(merged.contains("Referenced project files"));
        assert!(merged.contains("docs/My File.md"));

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn collect_directory_files_is_deterministic() {
        let root = create_temp_workspace("deterministic-dir");
        let dir = root.join("dir");
        fs::create_dir_all(&dir).expect("dir");
        fs::write(dir.join("b.txt"), "b").expect("b");
        fs::write(dir.join("a.txt"), "a").expect("a");
        fs::write(dir.join("c.txt"), "c").expect("c");

        let first = collect_directory_files(&dir, 10);
        let second = collect_directory_files(&dir, 10);
        assert_eq!(first, second);

        let names = first
            .iter()
            .map(|path| {
                path.file_name()
                    .and_then(|name| name.to_str())
                    .unwrap_or("")
                    .to_string()
            })
            .collect::<Vec<_>>();
        assert_eq!(names, vec!["a.txt", "b.txt", "c.txt"]);

        let _ = fs::remove_dir_all(root);
    }
}
