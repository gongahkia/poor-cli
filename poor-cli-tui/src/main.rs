/// Entry point for the poor-cli Rust TUI.
use std::collections::{HashMap, HashSet, VecDeque};
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use clap::Parser;
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::prelude::*;
use serde::{Deserialize, Serialize};
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
    /// Remote multiplayer websocket URL (bridge mode)
    #[arg(long)]
    remote_url: Option<String>,
    /// Remote multiplayer room name (requires --remote-url and --remote-token)
    #[arg(long)]
    remote_room: Option<String>,
    /// Remote multiplayer invite token (requires --remote-url and --remote-room)
    #[arg(long)]
    remote_token: Option<String>,
}

// ── Background message from server thread ────────────────────────────

#[allow(dead_code)]
enum ServerMsg {
    Initialized {
        provider: String,
        model: String,
        version: String,
        multiplayer_room: Option<String>,
        multiplayer_role: Option<String>,
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
    RoomEvent {
        room: String,
        event_type: String,
        actor: String,
        request_id: String,
        queue_depth: u64,
        member_count: u64,
        active_connection_id: String,
        lobby_enabled: bool,
        preset: String,
        members: Value,
    },
    MemberRoleUpdated {
        room: String,
        connection_id: String,
        role: String,
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

#[derive(Default)]
struct QaWatchState {
    stop_flag: Option<Arc<AtomicBool>>,
    handle: Option<thread::JoinHandle<()>>,
    directory: Option<String>,
    command: Option<String>,
}

impl QaWatchState {
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
        self.command = None;
    }
}

type SessionLogWriter = Arc<Mutex<fs::File>>;

#[derive(Clone)]
struct BackendLaunchContext {
    python_bin: String,
    cwd: Option<String>,
    backend_log_path: Option<String>,
    session_log: Option<SessionLogWriter>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
struct FocusState {
    goal: String,
    constraints: String,
    definition_of_done: String,
    started_at: String,
    completed: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct TaskItem {
    id: u64,
    title: String,
    done: bool,
    created_at: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ProfileState {
    name: String,
}

fn unix_ts_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis())
        .unwrap_or(0)
}

fn setup_session_logs(cwd: &str) -> (Option<SessionLogWriter>, Option<PathBuf>, Option<PathBuf>) {
    let logs_dir = Path::new(cwd).join(".poor-cli").join("logs");
    if fs::create_dir_all(&logs_dir).is_err() {
        return (None, None, None);
    }

    let session_id = format!("{}-{}", unix_ts_millis(), std::process::id());
    let tui_log_path = logs_dir.join(format!("tui-{session_id}.log"));
    let backend_log_path = logs_dir.join(format!("backend-{session_id}.log"));

    let writer = match OpenOptions::new()
        .create(true)
        .append(true)
        .open(&tui_log_path)
    {
        Ok(file) => Some(Arc::new(Mutex::new(file))),
        Err(_) => None,
    };

    // Best-effort touch so the backend log path always exists for discovery.
    let _ = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&backend_log_path);

    (writer, Some(tui_log_path), Some(backend_log_path))
}

fn write_session_log(log_writer: Option<&SessionLogWriter>, message: &str) {
    let Some(writer) = log_writer else {
        return;
    };
    let mut guard = match writer.lock() {
        Ok(g) => g,
        Err(_) => return,
    };
    let _ = writeln!(&mut *guard, "{} {}", unix_ts_millis(), message);
    let _ = guard.flush();
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

fn build_backend_server_args(cli: &Cli) -> Result<Vec<String>, String> {
    match (&cli.remote_url, &cli.remote_room, &cli.remote_token) {
        (None, None, None) => Ok(vec![]),
        (Some(url), Some(room), Some(token)) => Ok(build_bridge_server_args(url, room, token)),
        _ => Err(
            "Remote mode requires all of: --remote-url, --remote-room, --remote-token".to_string(),
        ),
    }
}

fn build_bridge_server_args(url: &str, room: &str, token: &str) -> Vec<String> {
    vec![
        "--bridge".to_string(),
        "--url".to_string(),
        url.to_string(),
        "--room".to_string(),
        room.to_string(),
        "--token".to_string(),
        token.to_string(),
    ]
}

fn reconnect_to_remote_server(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    url: &str,
    room: &str,
    token: &str,
) {
    let bridge_args = build_bridge_server_args(url, room, token);
    write_session_log(
        launch.session_log.as_ref(),
        &format!("join_server_request url={url} room={room}"),
    );

    let _ = rpc_cmd_tx.send(RpcCommand::Shutdown);
    app.server_connected = false;
    app.finalize_streaming();
    app.stop_waiting();
    app.multiplayer_enabled = true;
    app.multiplayer_room = room.to_string();
    app.multiplayer_role.clear();
    app.push_message(ChatMessage::system(format!(
        "Joining multiplayer server `{url}` room `{room}`..."
    )));
    app.set_status("Reconnecting backend in join mode");

    *rpc_cmd_tx = spawn_backend_worker(tx, launch.clone(), bridge_args, None, None, None);
}

fn spawn_backend_worker(
    tx: &mpsc::Sender<ServerMsg>,
    launch: BackendLaunchContext,
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
        write_session_log(
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
                write_session_log(log_ctx.as_ref(), "backend_spawn_ok");

                thread::spawn(move || {
                    while let Ok(notif) = notification_rx.recv() {
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
                            ServerNotification::RoomEvent {
                                room,
                                event_type,
                                actor,
                                request_id,
                                queue_depth,
                                member_count,
                                active_connection_id,
                                lobby_enabled,
                                preset,
                                members,
                                ..
                            } => ServerMsg::RoomEvent {
                                room,
                                event_type,
                                actor,
                                request_id,
                                queue_depth,
                                member_count,
                                active_connection_id,
                                lobby_enabled,
                                preset,
                                members,
                            },
                            ServerNotification::MemberRoleUpdated {
                                room,
                                connection_id,
                                role,
                            } => ServerMsg::MemberRoleUpdated {
                                room,
                                connection_id,
                                role,
                            },
                        };
                        if tx_notif.send(msg).is_err() {
                            break;
                        }
                    }
                });

                match client.initialize(
                    provider.as_deref(),
                    model.as_deref(),
                    None,
                    permission_mode.as_deref(),
                ) {
                    Ok(init) => {
                        write_session_log(log_ctx.as_ref(), "backend_initialize_ok");
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
                        let multiplayer_room = init
                            .capabilities
                            .as_ref()
                            .and_then(|caps| caps.pointer("/multiplayer/room"))
                            .and_then(|v| v.as_str())
                            .map(|s| s.to_string());
                        let multiplayer_role = init
                            .capabilities
                            .as_ref()
                            .and_then(|caps| caps.pointer("/multiplayer/role"))
                            .and_then(|v| v.as_str())
                            .map(|s| s.to_string());
                        let _ = tx_init.send(ServerMsg::Initialized {
                            provider: prov,
                            model: mdl,
                            version: init.version.unwrap_or_else(|| "0.4.0".into()),
                            multiplayer_room,
                            multiplayer_role,
                        });
                        run_rpc_worker(client, rpc_cmd_rx);
                    }
                    Err(e) => {
                        write_session_log(
                            log_ctx.as_ref(),
                            &format!("backend_initialize_error {e}"),
                        );
                        let _ = tx_init.send(ServerMsg::Error {
                            message: format!("Initialization failed: {e}"),
                        });
                    }
                }
            }
            Err(e) => {
                write_session_log(log_ctx.as_ref(), &format!("backend_spawn_error {e}"));
                let _ = tx_init.send(ServerMsg::Error {
                    message: format!("Failed to start server: {e}"),
                });
            }
        }
    });

    rpc_cmd_tx
}

fn run_app(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    cli: Cli,
) -> Result<String, Box<dyn std::error::Error>> {
    let backend_server_args = build_backend_server_args(&cli)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;

    let mut app = App::new();
    app.cwd = cli.cwd.clone().unwrap_or_else(|| {
        std::env::current_dir()
            .ok()
            .and_then(|p| p.to_str().map(|s| s.to_string()))
            .unwrap_or_else(|| ".".into())
    });
    let (session_log, tui_log_path, backend_log_path) = setup_session_logs(&app.cwd);
    write_session_log(
        session_log.as_ref(),
        &format!(
            "tui_session_start cwd={} remote_mode={} python_bin={}",
            app.cwd,
            !backend_server_args.is_empty(),
            cli.python
        ),
    );

    let (tx, rx) = mpsc::channel::<ServerMsg>();
    let provider = cli.provider.clone();
    let model = cli.model.clone();
    let permission_mode = if cli.dangerously_skip_permissions {
        Some("danger-full-access".to_string())
    } else {
        cli.permission_mode.clone()
    };
    let backend_log_path_string = backend_log_path
        .as_ref()
        .map(|path| path.to_string_lossy().to_string());
    let launch = BackendLaunchContext {
        python_bin: cli.python.clone(),
        cwd: cli.cwd.clone(),
        backend_log_path: backend_log_path_string,
        session_log: session_log.clone(),
    };
    let mut rpc_cmd_tx = spawn_backend_worker(
        &tx,
        launch.clone(),
        backend_server_args.clone(),
        provider.clone(),
        model.clone(),
        permission_mode.clone(),
    );

    app.provider_name = cli.provider.unwrap_or_else(|| "gemini".into());
    app.model_name = cli.model.unwrap_or_else(|| "gemini-2.0-flash-exp".into());
    app.add_welcome();
    if let Ok(Some(saved_profile)) = load_profile_state(&app) {
        let _ = apply_execution_profile(&mut app, &rpc_cmd_tx, &saved_profile.name, false);
    }
    refresh_context_budget_state(&mut app);
    if let (Some(tui_path), Some(backend_path)) = (tui_log_path.as_ref(), backend_log_path.as_ref())
    {
        app.push_message(ChatMessage::system(format!(
            "Session logs:\n- TUI: `{}`\n- Backend: `{}`",
            tui_path.display(),
            backend_path.display()
        )));
    }

    let cancel_token: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));
    let mut watch_state = WatchState::default();
    let mut qa_watch_state = QaWatchState::default();

    loop {
        terminal.draw(|f| ui::draw(f, &app))?;

        while let Ok(msg) = rx.try_recv() {
            match msg {
                ServerMsg::Initialized {
                    provider,
                    model,
                    version,
                    multiplayer_room,
                    multiplayer_role,
                } => {
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
                        &mut rpc_cmd_tx,
                        &launch,
                        &cancel_token,
                        &mut watch_state,
                        &mut qa_watch_state,
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
    qa_watch_state.stop();
    let _ = rpc_cmd_tx.send(RpcCommand::Shutdown);
    write_session_log(session_log.as_ref(), "tui_session_end");
    Ok(app.session_summary_text())
}

// ── Submit handler ───────────────────────────────────────────────────

fn handle_submit(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
    text: &str,
) -> bool {
    let trimmed = text.trim();
    if trimmed.is_empty() {
        return false;
    }

    if app.join_wizard_active && !trimmed.starts_with('/') {
        match app.join_wizard_step {
            0 => {
                match preflight_join_endpoint(trimmed) {
                    Ok(ok_message) => {
                        app.join_wizard_url = trimmed.to_string();
                        app.join_wizard_step = 1;
                        app.push_message(ChatMessage::system(format!(
                            "{ok_message}\n\nStep 2/3: Enter room name."
                        )));
                    }
                    Err(e) => {
                        app.push_message(ChatMessage::error(format!(
                            "Join preflight failed: {e}\nRe-enter WebSocket URL (ws:// or wss://), or run `/join-server cancel`."
                        )));
                    }
                }
                return false;
            }
            1 => {
                if trimmed.is_empty() {
                    app.push_message(ChatMessage::system(
                        "Room name cannot be empty. Enter room name, or `/join-server cancel`."
                            .to_string(),
                    ));
                    return false;
                }
                app.join_wizard_room = trimmed.to_string();
                app.join_wizard_step = 2;
                app.push_message(ChatMessage::system(
                    "Step 3/3: Enter invite token.".to_string(),
                ));
                return false;
            }
            2 => {
                if trimmed.is_empty() {
                    app.push_message(ChatMessage::system(
                        "Invite token cannot be empty. Enter token, or `/join-server cancel`."
                            .to_string(),
                    ));
                    return false;
                }
                let url = app.join_wizard_url.clone();
                let room = app.join_wizard_room.clone();
                let token = trimmed.to_string();
                app.join_wizard_active = false;
                app.join_wizard_step = 0;
                app.join_wizard_url.clear();
                app.join_wizard_room.clear();
                reconnect_to_remote_server(app, tx, rpc_cmd_tx, launch, &url, &room, &token);
                return false;
            }
            _ => {
                app.join_wizard_active = false;
                app.join_wizard_step = 0;
            }
        }
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
        return handle_slash_command(
            app,
            tx,
            rpc_cmd_tx,
            launch,
            cancel_token,
            watch_state,
            qa_watch_state,
            trimmed,
        );
    }

    if let Some(bang_input) = parse_bang_command(trimmed) {
        match rpc_execute_command_with_timeout_blocking(
            rpc_cmd_tx,
            &bang_input.command,
            Some(BANG_COMMAND_TIMEOUT_SECS),
            BANG_COMMAND_RESPONSE_TIMEOUT_SECS,
        ) {
            Ok(output) => {
                app.last_command_output = Some(output.clone());
                let command_preview = truncate_block(&output, 1200);
                app.push_message(ChatMessage::system(format!(
                    "**Bash command executed:** `{}`\n```text\n{command_preview}\n```",
                    bang_input.command
                )));

                let prompt_from_bash = build_bang_command_prompt(
                    &bang_input.command,
                    &output,
                    bang_input.question.as_deref(),
                );
                let backend_message = with_pending_images(app, &prompt_from_bash);
                let backend_message =
                    apply_response_mode_to_user_input(app.response_mode, &backend_message);
                send_chat_request(
                    app,
                    tx,
                    rpc_cmd_tx,
                    cancel_token,
                    backend_message,
                    trimmed.to_string(),
                );
            }
            Err(e) => app.push_message(ChatMessage::error(format!(
                "Bash command failed: {e}\nTip: use `!<command> | <question>` to ask about command output, or `/run <command>` for raw output only."
            ))),
        }
        return false;
    }

    refresh_context_budget_state(app);
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

    if resolved.is_empty()
        && inline_specs.is_empty()
        && app.pinned_context_files.is_empty()
        && !app.context_budget_files.is_empty()
    {
        for relative in app.context_budget_files.iter().take(6) {
            let path = if Path::new(relative).is_absolute() {
                PathBuf::from(relative)
            } else {
                Path::new(&app.cwd).join(relative)
            };
            if !path.is_file() {
                continue;
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
    let source_label = if inline_specs.is_empty() && app.pinned_context_files.is_empty() {
        "auto-selected context budget files"
    } else {
        "@ references and pinned files"
    };
    if extra > 0 {
        app.set_status(format!(
            "Attached {} {} ({attached_summary}, +{extra} more)",
            attached.len(),
            source_label
        ));
    } else {
        app.set_status(format!(
            "Attached {} {} ({attached_summary})",
            attached.len(),
            source_label
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

const BANG_COMMAND_MAX_OUTPUT_CHARS: usize = 16_000;
const BANG_COMMAND_TIMEOUT_SECS: u64 = 120;
const BANG_COMMAND_RESPONSE_TIMEOUT_SECS: u64 = 150;

#[derive(Debug, Clone, PartialEq, Eq)]
struct BangCommandInput {
    command: String,
    question: Option<String>,
}

fn parse_bang_command(input: &str) -> Option<BangCommandInput> {
    let trimmed = input.trim();
    let payload = trimmed.strip_prefix('!')?.trim();
    if payload.is_empty() {
        None
    } else {
        let (command_raw, question_raw) = if let Some((command, question)) = payload.split_once('|')
        {
            (command.trim(), Some(question.trim()))
        } else {
            (payload, None)
        };

        if command_raw.is_empty() {
            return None;
        }

        let question = question_raw
            .filter(|value| !value.is_empty())
            .map(|value| value.to_string());

        Some(BangCommandInput {
            command: command_raw.to_string(),
            question,
        })
    }
}

fn build_bang_command_prompt(command: &str, output: &str, question: Option<&str>) -> String {
    let content = if output.trim().is_empty() {
        "(command produced no output)"
    } else {
        output
    };

    let mut prompt = format!(
        "I ran a local shell command and want help based on its output.\n\n\
Command: `{command}`\n\n\
Output:\n```text\n{}\n```",
        truncate_block(content, BANG_COMMAND_MAX_OUTPUT_CHARS)
    );

    if let Some(user_question) = question.filter(|value| !value.trim().is_empty()) {
        prompt.push_str(&format!("\n\nUser question: {user_question}"));
    }

    prompt
}

struct OnboardingStep {
    title: &'static str,
    objective: &'static str,
    commands: &'static [&'static str],
    try_now: &'static str,
}

const ONBOARDING_STEPS: &[OnboardingStep] = &[
    OnboardingStep {
        title: "Get Oriented",
        objective:
            "Start with visibility into your session and where to find command docs quickly.",
        commands: &[
            "/help",
            "/status",
            "/bootstrap",
            "/profile status",
            "/search <term>",
        ],
        try_now: "/bootstrap",
    },
    OnboardingStep {
        title: "Choose Provider + Model",
        objective: "Inspect your active model, switch when needed, and configure provider auth.",
        commands: &["/provider", "/providers", "/switch", "/api-key"],
        try_now: "/provider",
    },
    OnboardingStep {
        title: "Run Local Services",
        objective: "Control local dependencies from the TUI instead of shelling out.",
        commands: &[
            "/service status",
            "/service start <name> <command...>",
            "/service logs <name> [lines]",
            "/ollama start",
        ],
        try_now: "/service status",
    },
    OnboardingStep {
        title: "Host Multiplayer Sessions",
        objective: "Start a room, invite collaborators, and manage member access from host mode.",
        commands: &[
            "/host-server",
            "/host-server members [room]",
            "/host-server kick <connection-id> [room]",
            "/host-server role <connection-id> <viewer|prompter> [room]",
            "/join-server <code>",
        ],
        try_now: "/host-server",
    },
    OnboardingStep {
        title: "Daily Coding Workflow",
        objective: "Use these commands for context, review, tests, and quick rollback checkpoints.",
        commands: &[
            "/add <path>",
            "/files",
            "/review [file]",
            "/test <file>",
            "/checkpoint",
            "/rewind [id|last]",
        ],
        try_now: "/files",
    },
];

fn onboarding_step_count() -> usize {
    ONBOARDING_STEPS.len()
}

fn onboarding_navigation_hint() -> &'static str {
    "Navigation: `/onboarding next` • `/onboarding prev` • `/onboarding <step>` • `/onboarding exit`"
}

fn format_onboarding_step(step_index: usize) -> String {
    if ONBOARDING_STEPS.is_empty() {
        return "Onboarding is currently unavailable.".to_string();
    }

    let total = onboarding_step_count();
    let idx = step_index.min(total.saturating_sub(1));
    let step = &ONBOARDING_STEPS[idx];

    let mut lines = vec![
        format!("**Onboarding {}/{}: {}**", idx + 1, total, step.title),
        String::new(),
        step.objective.to_string(),
        String::new(),
        "**Core commands**".to_string(),
    ];

    lines.extend(step.commands.iter().map(|cmd| format!("- `{cmd}`")));
    lines.push(String::new());
    lines.push(format!("Try now: `{}`", step.try_now));

    if idx + 1 == total {
        lines.push(
            "You reached the final step. Run `/onboarding exit` to end this onboarding session."
                .to_string(),
        );
    }

    lines.push(String::new());
    lines.push(onboarding_navigation_hint().to_string());
    lines.join("\n")
}

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

// ── Slash command handler ─────────────────────────────────────────────

fn handle_slash_command(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    cancel_token: &Arc<AtomicBool>,
    watch_state: &mut WatchState,
    qa_watch_state: &mut QaWatchState,
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
  /onboarding ...      Start interactive onboarding (`next`, `prev`, `<step>`, `exit`)\n\
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
  /host-server ...     Start/share/manage host session and members\n\
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
                app.push_message(ChatMessage::system(summary));
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
                app.push_message(ChatMessage::system(
                    "Usage: /focus start <goal> [|| constraints || definition-of-done]".to_string(),
                ));
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
                Ok(()) => app.push_message(ChatMessage::system(format!(
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
                ))),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return false;
        }

        if subcommand == "done" {
            match load_focus_state(app) {
                Ok(Some(mut state)) => {
                    state.completed = true;
                    match save_focus_state(app, &state) {
                        Ok(()) => app.push_message(ChatMessage::system(
                            "Focus marked complete.".to_string(),
                        )),
                        Err(e) => app.push_message(ChatMessage::error(e)),
                    }
                }
                Ok(None) => app.push_message(ChatMessage::system(
                    "No active focus to complete.".to_string(),
                )),
                Err(e) => app.push_message(ChatMessage::error(e)),
            }
            return false;
        }

        app.push_message(ChatMessage::system(
            "Usage: /focus start|status|done".to_string(),
        ));
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
                    app.push_message(ChatMessage::system(
                        "Usage: /context-budget [token-budget]".to_string(),
                    ));
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
                        app.push_message(ChatMessage::system(
                            "Autopilot guardrail blocked start because permission mode is `danger-full-access`.\nUse `/permission-mode prompt` or rerun with `/autopilot start <cap> --allow-risky`."
                                .to_string(),
                        ));
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
            app.push_message(ChatMessage::system(format!(
                "Autopilot enabled with iteration cap {cap}."
            )));
            return false;
        }
        if subcommand == "stop" {
            app.autopilot_enabled = false;
            app.iteration_cap = 25;
            app.push_message(ChatMessage::system(
                "Autopilot disabled. Iteration cap reset to 25.".to_string(),
            ));
            return false;
        }
        app.push_message(ChatMessage::system(
            "Usage: /autopilot start [cap] [--allow-risky]\n       /autopilot stop\n       /autopilot status".to_string(),
        ));
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
                app.push_message(ChatMessage::system("Usage: /tasks add <title>".to_string()));
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
                app.push_message(ChatMessage::system("Usage: /tasks done <id>".to_string()));
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
                app.push_message(ChatMessage::system(format!("Task #{id} not found.")));
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
                app.push_message(ChatMessage::system("Usage: /tasks drop <id>".to_string()));
                return false;
            }
            let before = tasks.len();
            tasks.retain(|task| task.id != id);
            if tasks.len() == before {
                app.push_message(ChatMessage::system(format!("Task #{id} not found.")));
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

        app.push_message(ChatMessage::system(
            "Usage: /tasks [list]\n       /tasks add <title>\n       /tasks done <id>\n       /tasks drop <id>\n       /tasks clear".to_string(),
        ));
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
                    app.push_message(ChatMessage::system("No diff content found.".to_string()));
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
            app.push_message(ChatMessage::system(
                "No recent command/test output found.\nRun `/fix-failures <test-or-lint-command>` or execute a command first.".to_string(),
            ));
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
        );
        return false;
    }

    if lowered.starts_with("/run ") {
        let command = raw.splitn(2, ' ').nth(1).map(str::trim).unwrap_or("");
        if command.is_empty() {
            app.push_message(ChatMessage::system("Usage: /run <command>".to_string()));
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
            app.push_message(ChatMessage::system("Usage: /read <file>".to_string()));
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

    if lowered == "/join-server" || lowered.starts_with("/join-server ") {
        let args: Vec<&str> = raw.split_whitespace().collect();
        if args.len() == 1 {
            app.join_wizard_active = true;
            app.join_wizard_step = 0;
            app.join_wizard_url.clear();
            app.join_wizard_room.clear();
            app.push_message(ChatMessage::system(
                "**Join wizard started**\n\nStep 1/3: Enter WebSocket URL (ws://HOST:PORT/rpc or wss://...)\nUse `/join-server cancel` to abort."
                    .to_string(),
            ));
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
            app.push_message(ChatMessage::system("Join wizard cancelled.".to_string()));
            return false;
        }

        let (url, room, token) = match parse_join_server_args(raw) {
            Ok(values) => values,
            Err(error_message) => {
                app.push_message(ChatMessage::system(error_message));
                return false;
            }
        };

        if let Err(e) = preflight_join_endpoint(&url) {
            app.push_message(ChatMessage::error(format!(
                "Join preflight failed: {e}\nUse `/join-server` for wizard mode."
            )));
            return false;
        }

        reconnect_to_remote_server(app, tx, rpc_cmd_tx, launch, &url, &room, &token);
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
                    "Failed to fetch host server status: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "stop" {
            if args.len() > 2 {
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
                return false;
            }

            match rpc_stop_host_server_blocking(rpc_cmd_tx) {
                Ok(payload) => {
                    if payload
                        .get("stopped")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false)
                    {
                        app.push_message(ChatMessage::system(
                            "Multiplayer host stopped.".to_string(),
                        ));
                    } else {
                        app.push_message(ChatMessage::system(
                            "No multiplayer host is currently running.".to_string(),
                        ));
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
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
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
                    app.push_message(ChatMessage::system(lines.join("\n")));
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
                        app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
                        return false;
                    }
                    (args[2], args[3], args.get(4).copied())
                } else if lowered_subcommand == "promote" {
                    if args.len() < 3 || args.len() > 4 {
                        app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
                        return false;
                    }
                    (args[2], "prompter", args.get(3).copied())
                } else {
                    if args.len() < 3 || args.len() > 4 {
                        app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
                        return false;
                    }
                    (args[2], "viewer", args.get(3).copied())
                };

            let normalized_role = match role.to_ascii_lowercase().as_str() {
                "viewer" | "read" | "read-only" => "viewer",
                "prompter" | "writer" | "editor" | "admin" => "prompter",
                _ => {
                    app.push_message(ChatMessage::system(
                        "Invalid role. Use `viewer` or `prompter`.".to_string(),
                    ));
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
                    app.push_message(ChatMessage::system(lines.join("\n")));
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
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
                return false;
            }
            let enable = match args[2].to_ascii_lowercase().as_str() {
                "on" | "enable" | "enabled" | "true" => true,
                "off" | "disable" | "disabled" | "false" => false,
                _ => {
                    app.push_message(ChatMessage::system(
                        "Usage: /host-server lobby <on|off> [room]".to_string(),
                    ));
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
                    app.push_message(ChatMessage::system(format!(
                        "Lobby approvals {state} for room `{room_name}`."
                    )));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to update lobby mode: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "approve" {
            if args.len() < 3 || args.len() > 4 {
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
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
                    app.push_message(ChatMessage::system(format!(
                        "Approved `{connection_id}` in room `{room_name}`."
                    )));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to approve member `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "deny" {
            if args.len() < 3 || args.len() > 4 {
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
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
                    app.push_message(ChatMessage::system(format!(
                        "Denied `{connection_id}` in room `{room_name}`."
                    )));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to deny member `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "rotate-token" {
            if args.len() < 3 || args.len() > 5 {
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
                return false;
            }
            let role = args[2].to_ascii_lowercase();
            if role != "viewer" && role != "prompter" {
                app.push_message(ChatMessage::system(
                    "Usage: /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]"
                        .to_string(),
                ));
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
                        app.push_message(ChatMessage::system(
                            "Usage: /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]".to_string(),
                        ));
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
                    app.push_message(ChatMessage::system(lines.join("\n")));
                }
                Err(e) => {
                    app.push_message(ChatMessage::error(format!("Failed to rotate token: {e}")))
                }
            }
            return false;
        }

        if lowered_subcommand == "revoke" {
            if args.len() < 3 || args.len() > 4 {
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
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
                    app.push_message(ChatMessage::system(format!(
                        "Revoked `{value}` ({kind}) in room `{room_name}`."
                    )));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to revoke `{value}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "handoff" {
            if args.len() < 3 || args.len() > 4 {
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
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
                    app.push_message(ChatMessage::system(format!(
                        "Handed off prompter role to `{connection_id}` in room `{room_name}`."
                    )));
                }
                Err(e) => app.push_message(ChatMessage::error(format!(
                    "Failed to handoff to `{connection_id}`: {e}"
                ))),
            }
            return false;
        }

        if lowered_subcommand == "preset" {
            if args.len() < 3 || args.len() > 4 {
                app.push_message(ChatMessage::system(host_server_usage_text().to_string()));
                return false;
            }
            let preset = args[2].to_ascii_lowercase();
            if preset != "pairing" && preset != "mob" && preset != "review" {
                app.push_message(ChatMessage::system(
                    "Usage: /host-server preset <pairing|mob|review> [room]".to_string(),
                ));
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
                    app.push_message(ChatMessage::system(format!(
                        "Applied preset **{preset}** to room `{room_name}` (lobby: {}).",
                        if lobby_enabled { "on" } else { "off" }
                    )));
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
                app.push_message(ChatMessage::system(service_usage_text().to_string()));
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
                app.push_message(ChatMessage::system(service_usage_text().to_string()));
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
                app.push_message(ChatMessage::system(service_usage_text().to_string()));
                return false;
            }
            let service_name = args[2];
            let line_count = match args.get(3) {
                Some(raw_count) => match raw_count.parse::<u64>() {
                    Ok(parsed) => Some(parsed),
                    Err(_) => {
                        app.push_message(ChatMessage::system(
                            "lines must be an integer (e.g. `/service logs ollama 120`)"
                                .to_string(),
                        ));
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
                    show_command_info_popup(app, raw, format_service_status_payload(&payload))
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
                            app.push_message(ChatMessage::system(
                                "lines must be an integer (e.g. `/ollama logs 120`)".to_string(),
                            ));
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
                    app.push_message(ChatMessage::system(
                        "Usage: /ollama pull <model>".to_string(),
                    ));
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
                    Ok(output) => app.push_message(ChatMessage::system(format!(
                        "**Command:** `{command}`\n\n```text\n{}\n```",
                        truncate_block(&output, 3200)
                    ))),
                    Err(e) => app.push_message(ChatMessage::error(format!(
                        "Failed to pull Ollama model `{model}`: {e}"
                    ))),
                }
            }
            "list" | "list-models" => {
                match rpc_execute_command_with_timeout_blocking(
                    rpc_cmd_tx,
                    "ollama list",
                    Some(60),
                    75,
                ) {
                    Ok(output) => show_command_info_popup(
                        app,
                        raw,
                        format!(
                            "**Installed Ollama Models**\n```text\n{}\n```",
                            truncate_block(&output, 3200)
                        ),
                    ),
                    Err(e) => app.push_message(ChatMessage::error(format!(
                        "Failed to list Ollama models: {e}"
                    ))),
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
        show_command_info_popup(app, raw, text);
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
                app.push_message(ChatMessage::system("QA watch is not running.".to_string()));
            }
            return false;
        }

        if subcommand == "start" {
            if qa_watch_state.is_running() {
                app.push_message(ChatMessage::system(
                    "QA watch is already running. Use `/qa stop` first.".to_string(),
                ));
                return false;
            }

            let tail = raw
                .split_once(' ')
                .map(|(_, rest)| rest.trim())
                .and_then(|rest| rest.split_once(' ').map(|(_, after)| after.trim()))
                .unwrap_or("");
            let mut directory = app.cwd.clone();
            let mut command = default_qa_command_for_workspace(Path::new(&app.cwd));

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
            let handle =
                spawn_qa_watch_worker(directory.clone(), command.clone(), tx.clone(), stop.clone());
            qa_watch_state.stop_flag = Some(stop);
            qa_watch_state.handle = Some(handle);
            qa_watch_state.directory = Some(directory.clone());
            qa_watch_state.command = Some(command.clone());
            app.qa_mode_enabled = true;
            app.qa_command = command.clone();
            app.set_status(format!("QA watch started: `{command}` on `{directory}`"));
            return false;
        }

        app.push_message(ChatMessage::system(
            "Usage: /qa start [dir] [command...]\n       /qa stop\n       /qa status".to_string(),
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

fn default_qa_command_for_workspace(root: &Path) -> String {
    let traits = detect_project_traits(root);
    if traits.contains(&"rust") && traits.contains(&"python") {
        return "cargo test -q && pytest -q".to_string();
    }
    if traits.contains(&"rust") {
        return "cargo test -q".to_string();
    }
    if traits.contains(&"python") {
        return "pytest -q".to_string();
    }
    if traits.contains(&"javascript") {
        return "npm test -- --watch=false".to_string();
    }
    "make test".to_string()
}

fn run_qa_command(directory: &str, command: &str) -> Result<(i32, String), String> {
    let output = Command::new("sh")
        .arg("-lc")
        .arg(command)
        .current_dir(directory)
        .output()
        .map_err(|e| format!("Failed to run QA command `{command}`: {e}"))?;

    let exit_code = output.status.code().unwrap_or(1);
    let combined = format!(
        "{}{}{}",
        String::from_utf8_lossy(&output.stdout),
        if output.stdout.is_empty() || output.stderr.is_empty() {
            ""
        } else {
            "\n"
        },
        String::from_utf8_lossy(&output.stderr)
    );
    Ok((exit_code, truncate_block(&combined, 2800)))
}

fn spawn_qa_watch_worker(
    directory: String,
    command: String,
    tx: mpsc::Sender<ServerMsg>,
    stop: Arc<AtomicBool>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let root = PathBuf::from(&directory);
        let mut previous = snapshot_directory(&root);
        let mut last_success: Option<bool> = None;
        let mut last_signature = String::new();

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

            let change_preview = changed
                .iter()
                .take(6)
                .map(|path| format!("- {path}"))
                .collect::<Vec<_>>()
                .join("\n");

            match run_qa_command(&directory, &command) {
                Ok((exit_code, output)) => {
                    let success = exit_code == 0;
                    let signature = format!("{success}:{}", first_line(&output));
                    let changed_state = last_success != Some(success);
                    let changed_signature = signature != last_signature;
                    last_success = Some(success);
                    last_signature = signature;

                    if !changed_state && !changed_signature {
                        continue;
                    }

                    let status = if success { "PASS" } else { "FAIL" };
                    let mut lines = vec![
                        format!("**QA Watch** `{status}` (`{command}`)"),
                        format!("- Directory: `{directory}`"),
                        format!("- Changed files: {}", changed.len()),
                        change_preview,
                    ];

                    if !output.trim().is_empty() {
                        lines.push(String::new());
                        lines.push("```text".to_string());
                        lines.push(output);
                        lines.push("```".to_string());
                    }
                    let _ = tx.send(ServerMsg::SystemMessage {
                        content: lines.join("\n"),
                    });
                }
                Err(error) => {
                    let _ = tx.send(ServerMsg::Error {
                        message: format!("QA watch failed: {error}"),
                    });
                    break;
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

fn parse_join_server_args(raw: &str) -> Result<(String, String, String), String> {
    let usage = "Usage: /join-server\n       /join-server <invite-code>\n       /join-server <ws-url> <room> <token>\n       /join-server cancel";
    let args = raw
        .split_whitespace()
        .skip(1)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>();

    if args.is_empty() {
        return Err(usage.to_string());
    }

    let (url, room, token) = if args.len() == 1 {
        let parts = args[0].split('|').collect::<Vec<_>>();
        if parts.len() != 3 {
            return Err(usage.to_string());
        }
        (
            parts[0].trim().to_string(),
            parts[1].trim().to_string(),
            parts[2].trim().to_string(),
        )
    } else if args.len() == 3 {
        (
            args[0].to_string(),
            args[1].to_string(),
            args[2].to_string(),
        )
    } else {
        return Err(usage.to_string());
    };

    if url.is_empty() || room.is_empty() || token.is_empty() {
        return Err(usage.to_string());
    }
    if !(url.starts_with("ws://") || url.starts_with("wss://")) {
        return Err("Join URL must start with ws:// or wss://".to_string());
    }

    Ok((url, room, token))
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

fn format_host_server_payload(payload: &Value) -> String {
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !running {
        return "No multiplayer host is running.\nUse `/host-server` to start one.".to_string();
    }

    let created = payload
        .get("created")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let bind_host = payload
        .get("bindHost")
        .and_then(|v| v.as_str())
        .unwrap_or("0.0.0.0");
    let port = payload.get("port").and_then(|v| v.as_u64()).unwrap_or(0);
    let local_ws = payload
        .get("localWsUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let share_ws = payload
        .get("shareWsUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let public_ws = payload
        .get("publicWsUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");

    let mut lines = vec![
        if created {
            "Multiplayer host started.".to_string()
        } else {
            "Multiplayer host is already running.".to_string()
        },
        format!("Bind: `{bind_host}:{port}`"),
    ];

    if !local_ws.is_empty() {
        lines.push(format!("Local URL: `{local_ws}`"));
    }
    if !share_ws.is_empty() {
        lines.push(format!("LAN share URL: `{share_ws}`"));
        if bind_host == "0.0.0.0" && share_ws.contains("127.0.0.1") {
            lines.push(
                "LAN IP detection fell back to localhost. Replace `127.0.0.1` with your LAN IP before sharing."
                    .to_string(),
            );
        }
    }
    if !public_ws.is_empty() {
        lines.push(format!("Public URL: `{public_ws}`"));
    }

    let rooms = payload
        .get("rooms")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    if rooms.is_empty() {
        lines.push(String::new());
        lines.push("No multiplayer rooms are available yet.".to_string());
        return lines.join("\n");
    }

    for room in rooms {
        let name = room
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let viewer_token = room
            .get("viewerToken")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_token = room
            .get("prompterToken")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let viewer_join = room
            .get("viewerJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_join = room
            .get("prompterJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let viewer_code = room
            .get("viewerInviteCode")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let member_count = room
            .get("memberCount")
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        let lobby_enabled = room
            .get("lobbyEnabled")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let preset = room
            .get("preset")
            .and_then(|v| v.as_str())
            .unwrap_or("pairing");

        lines.push(String::new());
        lines.push(format!(
            "**Room `{name}`** ({member_count} member(s), lobby: {}, preset: `{preset}`)",
            if lobby_enabled { "on" } else { "off" }
        ));
        lines.push(format!("- Viewer token: `{viewer_token}`"));
        lines.push(format!("- Prompter token: `{prompter_token}`"));
        if !viewer_join.is_empty() {
            lines.push(format!("- Share viewer command: `{viewer_join}`"));
        }
        if !prompter_join.is_empty() {
            lines.push(format!("- Share prompter command: `{prompter_join}`"));
        }
        if !viewer_code.is_empty() {
            lines.push(format!("- Viewer invite code: `{viewer_code}`"));
        }
    }

    lines.join("\n")
}

fn format_host_share_payload(
    payload: &Value,
    role_filter: Option<&str>,
    room_filter: Option<&str>,
) -> String {
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !running {
        return "No multiplayer host is running.\nUse `/host-server` to start one.".to_string();
    }

    let rooms = payload
        .get("rooms")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    if rooms.is_empty() {
        return "No multiplayer rooms are available yet.".to_string();
    }

    let normalized_role = role_filter.map(|role| role.to_ascii_lowercase());
    let normalized_room = room_filter.map(|room| room.trim().to_string());
    let mut lines = vec!["**Host Share Payloads**".to_string()];
    let mut matched = 0usize;

    for room in rooms {
        let room_name = room
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        if let Some(filter) = &normalized_room {
            if filter != room_name {
                continue;
            }
        }

        let viewer_join = room
            .get("viewerJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_join = room
            .get("prompterJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let viewer_code = room
            .get("viewerInviteCode")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_code = room
            .get("prompterInviteCode")
            .and_then(|v| v.as_str())
            .unwrap_or("");

        lines.push(String::new());
        lines.push(format!("**Room `{room_name}`**"));

        if normalized_role.is_none() || normalized_role.as_deref() == Some("viewer") {
            matched += 1;
            lines.push("- Viewer share command:".to_string());
            if viewer_join.is_empty() {
                lines.push("```text\n(unavailable)\n```".to_string());
            } else {
                lines.push(format!("```text\n{viewer_join}\n```"));
            }
            if !viewer_code.is_empty() {
                lines.push(format!("- Viewer invite code: `{viewer_code}`"));
                lines.push(format!(
                    "- Viewer QR payload: `poor-cli://join?code={viewer_code}`"
                ));
            }
        }

        if normalized_role.is_none() || normalized_role.as_deref() == Some("prompter") {
            matched += 1;
            lines.push("- Prompter share command:".to_string());
            if prompter_join.is_empty() {
                lines.push("```text\n(unavailable)\n```".to_string());
            } else {
                lines.push(format!("```text\n{prompter_join}\n```"));
            }
            if !prompter_code.is_empty() {
                lines.push(format!("- Prompter invite code: `{prompter_code}`"));
                lines.push(format!(
                    "- Prompter QR payload: `poor-cli://join?code={prompter_code}`"
                ));
            }
        }
    }

    if matched == 0 {
        return "No share payloads matched your filters.\nUsage: `/host-server share [viewer|prompter] [room]`".to_string();
    }

    lines.push(String::new());
    lines.push("Tip: use `/copy` right after this to copy the latest share payload.".to_string());
    lines.join("\n")
}

fn host_server_usage_text() -> &'static str {
    "Usage: /host-server [room]\n\
       /host-server status\n\
       /host-server stop\n\
       /host-server share [viewer|prompter] [room]\n\
       /host-server members [room]\n\
       /host-server kick <connection-id> [room]\n\
       /host-server role <connection-id> <viewer|prompter> [room]\n\
       /host-server promote <connection-id> [room]\n\
       /host-server demote <connection-id> [room]\n\
       /host-server lobby <on|off> [room]\n\
       /host-server approve <connection-id> [room]\n\
       /host-server deny <connection-id> [room]\n\
       /host-server rotate-token <viewer|prompter> [room] [expiry-seconds]\n\
       /host-server revoke <token|connection-id> [room]\n\
       /host-server handoff <connection-id> [room]\n\
       /host-server preset <pairing|mob|review> [room]\n\
       /host-server activity [room] [limit] [event-type]"
}

fn format_host_activity_payload(payload: &Value) -> String {
    let room = payload
        .get("room")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown");
    let event_filter = payload
        .get("eventType")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let events = payload
        .get("events")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    if events.is_empty() {
        return format!("No activity events found for room `{room}`.");
    }

    let mut lines = vec![format!(
        "**Host Activity** room `{room}` ({})",
        events.len()
    )];
    if !event_filter.is_empty() {
        lines.push(format!("Filter: `{event_filter}`"));
    }
    for event in events {
        let timestamp = event
            .get("timestamp")
            .and_then(|v| v.as_str())
            .unwrap_or("-");
        let event_type = event
            .get("eventType")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let actor = event.get("actor").and_then(|v| v.as_str()).unwrap_or("");
        let request_id = event
            .get("requestId")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let mut line = format!("- `{timestamp}` **{event_type}**");
        if !actor.is_empty() {
            line.push_str(&format!(" actor=`{actor}`"));
        }
        if !request_id.is_empty() {
            line.push_str(&format!(" request=`{request_id}`"));
        }
        if let Some(details) = event.get("details").and_then(|v| v.as_object()) {
            if !details.is_empty() {
                let details_text = details
                    .iter()
                    .map(|(key, value)| format!("{key}={}", value))
                    .collect::<Vec<_>>()
                    .join(", ");
                line.push_str(&format!(" details: {details_text}"));
            }
        }
        lines.push(line);
    }
    lines.join("\n")
}

fn format_host_members_payload(payload: &Value) -> String {
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !running {
        return "No multiplayer host is running.\nUse `/host-server` to start one.".to_string();
    }

    let rooms = payload
        .get("rooms")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    if rooms.is_empty() {
        return "No active rooms found on host.".to_string();
    }

    let mut lines = vec!["**Host Members**".to_string()];
    for room in rooms {
        let room_name = room
            .get("name")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let member_count = room
            .get("memberCount")
            .and_then(|v| v.as_u64())
            .unwrap_or(0);
        let lobby_enabled = room
            .get("lobbyEnabled")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        let preset = room
            .get("preset")
            .and_then(|v| v.as_str())
            .unwrap_or("pairing");
        lines.push(String::new());
        lines.push(format!(
            "**Room `{room_name}`** ({member_count} member(s), lobby: {}, preset: `{preset}`)",
            if lobby_enabled { "on" } else { "off" }
        ));

        let members = room
            .get("members")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        if members.is_empty() {
            lines.push("- No connected members".to_string());
            continue;
        }

        for member in members {
            let connection_id = member
                .get("connectionId")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let role = member
                .get("role")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let client_name = member
                .get("clientName")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .trim();
            let active = member
                .get("active")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let connected = member
                .get("connected")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let joined_at = member
                .get("joinedAt")
                .and_then(|v| v.as_str())
                .unwrap_or("");
            let approved = member
                .get("approved")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);

            let state = if connected {
                "connected"
            } else {
                "disconnected"
            };
            let active_label = if active { ", active" } else { "" };
            let approved_label = if approved { "" } else { ", pending-approval" };
            let name_label = if client_name.is_empty() {
                String::new()
            } else {
                format!(" ({client_name})")
            };

            lines.push(format!(
                "- `{connection_id}`{name_label}: **{role}** ({state}{active_label}{approved_label})"
            ));
            if !joined_at.is_empty() {
                lines.push(format!("  joined: `{joined_at}`"));
            }
        }
    }

    lines.join("\n")
}

fn service_usage_text() -> &'static str {
    "Usage: /service status [name]\n\
       /service start <name> [command...]\n\
       /service stop <name>\n\
       /service logs <name> [lines]"
}

fn ollama_usage_text() -> &'static str {
    "Usage: /ollama start|stop|status\n\
       /ollama logs [lines]\n\
       /ollama pull <model>\n\
       /ollama list-models"
}

fn onboarding_usage_text() -> &'static str {
    "Usage: /onboarding\n\
       /onboarding start\n\
       /onboarding next\n\
       /onboarding prev\n\
       /onboarding <step-number>\n\
       /onboarding show\n\
       /onboarding exit"
}

fn format_single_service_payload(payload: &Value) -> String {
    let service_name = payload
        .get("service")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown");
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let managed = payload
        .get("managed")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let external = payload
        .get("external")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let created = payload
        .get("created")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    let stopped = payload
        .get("stopped")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);

    let mut lines = vec![format!("**Service:** `{service_name}`")];
    if running {
        if external {
            lines.push("- Status: running (external)".to_string());
        } else if managed {
            lines.push("- Status: running (managed)".to_string());
        } else {
            lines.push("- Status: running".to_string());
        }
    } else {
        lines.push("- Status: stopped".to_string());
    }

    if created {
        lines.push("- Action: started in this command".to_string());
    }
    if stopped {
        lines.push("- Action: stopped in this command".to_string());
    }

    if let Some(pid) = payload.get("pid").and_then(|v| v.as_u64()) {
        lines.push(format!("- PID: `{pid}`"));
    }
    if let Some(command) = payload.get("command").and_then(|v| v.as_str()) {
        if !command.is_empty() {
            lines.push(format!("- Command: `{command}`"));
        }
    }
    if let Some(cwd) = payload.get("cwd").and_then(|v| v.as_str()) {
        if !cwd.is_empty() {
            lines.push(format!("- CWD: `{cwd}`"));
        }
    }
    if let Some(started_at) = payload.get("startedAt").and_then(|v| v.as_str()) {
        if !started_at.is_empty() {
            lines.push(format!("- Started: `{started_at}`"));
        }
    }
    if let Some(exit_code) = payload.get("exitCode").and_then(|v| v.as_i64()) {
        lines.push(format!("- Last exit code: `{exit_code}`"));
    }
    if let Some(log_path) = payload.get("logPath").and_then(|v| v.as_str()) {
        if !log_path.is_empty() {
            lines.push(format!("- Logs: `{log_path}`"));
        }
    }

    if service_name == "ollama" {
        if let Some(base_url) = payload.get("baseUrl").and_then(|v| v.as_str()) {
            if !base_url.is_empty() {
                lines.push(format!("- Base URL: `{base_url}`"));
            }
        }
        if let Some(healthy) = payload.get("healthy").and_then(|v| v.as_bool()) {
            lines.push(format!(
                "- Health: {}",
                if healthy { "reachable" } else { "unreachable" }
            ));
        }
    }

    if let Some(message) = payload.get("message").and_then(|v| v.as_str()) {
        if !message.is_empty() {
            lines.push(String::new());
            lines.push(message.to_string());
        }
    }

    lines.join("\n")
}

fn format_service_status_payload(payload: &Value) -> String {
    if let Some(services) = payload.get("services").and_then(|v| v.as_array()) {
        if services.is_empty() {
            return "No managed services found.\nUse `/service start <name> <command...>`."
                .to_string();
        }

        let mut lines = vec!["**Services:**".to_string(), String::new()];
        for service in services {
            let name = service
                .get("service")
                .and_then(|v| v.as_str())
                .unwrap_or("unknown");
            let running = service
                .get("running")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let external = service
                .get("external")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let marker = if running { "✓" } else { "✗" };
            let state = if running { "running" } else { "stopped" };
            let scope = if external {
                "external"
            } else if service
                .get("managed")
                .and_then(|v| v.as_bool())
                .unwrap_or(false)
            {
                "managed"
            } else {
                "unmanaged"
            };
            lines.push(format!("- {marker} `{name}`: {state} ({scope})"));
        }
        lines.push(String::new());
        lines.push("Use `/service status <name>` for details.".to_string());
        return lines.join("\n");
    }

    format_single_service_payload(payload)
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

fn detect_project_traits(root: &Path) -> Vec<&'static str> {
    let mut traits = Vec::new();
    if root.join("Cargo.toml").is_file() {
        traits.push("rust");
    }
    if root.join("pyproject.toml").is_file()
        || root.join("requirements.txt").is_file()
        || root.join("setup.py").is_file()
    {
        traits.push("python");
    }
    if root.join("package.json").is_file() {
        traits.push("javascript");
    }
    traits
}

fn classify_project_kind(root: &Path) -> String {
    let traits = detect_project_traits(root);
    if traits.is_empty() {
        return "generic".to_string();
    }
    if traits.len() == 1 {
        return traits[0].to_string();
    }
    "mixed".to_string()
}

fn recommended_bootstrap_commands(root: &Path) -> Vec<String> {
    let traits = detect_project_traits(root);
    let mut commands = Vec::new();
    if traits.contains(&"rust") {
        commands.push("cargo test -q".to_string());
        commands.push("cargo check".to_string());
    }
    if traits.contains(&"python") {
        commands.push("pytest -q".to_string());
        commands.push("ruff check .".to_string());
    }
    if traits.contains(&"javascript") {
        commands.push("npm test -- --watch=false".to_string());
        commands.push("npm run lint".to_string());
    }
    if commands.is_empty() {
        commands.push("make test".to_string());
        commands.push("git status -sb".to_string());
    }
    commands
}

fn format_bootstrap_report(root: &Path) -> String {
    let project_kind = classify_project_kind(root);
    let commands = recommended_bootstrap_commands(root);
    let mut lines = vec![
        format!("**Solo Quickstart** (`{}`)", root.to_string_lossy()),
        format!("- Project type: `{project_kind}`"),
        String::new(),
        "**Recommended first commands**".to_string(),
    ];
    for command in commands {
        lines.push(format!("- `{command}`"));
    }
    lines.push(String::new());
    lines.push(
        "Suggested flow: `/doctor` -> `/focus start ...` -> `/workspace-map` -> `/resume`."
            .to_string(),
    );
    lines.push("Onboarding shortcut: `/onboarding 1`.".to_string());
    lines.join("\n")
}

fn estimate_token_cost(char_count: usize) -> usize {
    (char_count / 4).max(1)
}

fn is_binary_like_extension(ext: &str) -> bool {
    matches!(
        ext,
        "png"
            | "jpg"
            | "jpeg"
            | "gif"
            | "webp"
            | "bmp"
            | "ico"
            | "pdf"
            | "zip"
            | "gz"
            | "tar"
            | "jar"
            | "wasm"
            | "exe"
            | "dll"
            | "so"
            | "dylib"
            | "ttf"
            | "otf"
            | "woff"
            | "woff2"
            | "mp3"
            | "mp4"
            | "mov"
            | "avi"
    )
}

fn context_relevance_score(path: &Path) -> i32 {
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    let extension = path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();

    let mut score = match extension.as_str() {
        "rs" | "py" | "ts" | "tsx" | "js" | "jsx" | "go" | "java" | "kt" => 120,
        "toml" | "yaml" | "yml" | "json" => 80,
        "md" => 60,
        "sh" => 70,
        _ => 40,
    };

    if matches!(
        file_name.as_str(),
        "readme.md"
            | "cargo.toml"
            | "pyproject.toml"
            | "package.json"
            | "makefile"
            | "main.rs"
            | "main.py"
            | "app.py"
            | "index.ts"
            | "index.js"
    ) {
        score += 120;
    }
    if file_name.contains("test") {
        score += 40;
    }
    if file_name.contains("config") || file_name.ends_with(".env") {
        score += 30;
    }
    if file_name.contains(".lock") {
        score -= 40;
    }
    score
}

fn compute_context_budget_files(
    root: &Path,
    budget_tokens: usize,
    max_files: usize,
) -> (Vec<String>, usize) {
    let mut candidates = Vec::<(i32, String, usize)>::new();
    for path in collect_directory_files(root, 5000) {
        let extension = path
            .extension()
            .and_then(|value| value.to_str())
            .unwrap_or("")
            .to_ascii_lowercase();
        if is_binary_like_extension(&extension) {
            continue;
        }
        let byte_size = fs::metadata(&path)
            .ok()
            .map(|metadata| metadata.len() as usize)
            .unwrap_or(0);
        if byte_size == 0 {
            continue;
        }
        let relative = path
            .strip_prefix(root)
            .map(|rel| rel.to_string_lossy().to_string())
            .unwrap_or_else(|_| path.to_string_lossy().to_string());
        candidates.push((context_relevance_score(&path), relative, byte_size));
    }

    candidates.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.cmp(&b.1)));

    let mut selected = Vec::<String>::new();
    let mut used_tokens = 0usize;
    for (_, relative, byte_size) in candidates {
        if selected.len() >= max_files {
            break;
        }
        let estimated = estimate_token_cost(byte_size.min(12_000));
        if used_tokens + estimated > budget_tokens && !selected.is_empty() {
            break;
        }
        selected.push(relative);
        used_tokens += estimated;
    }

    (selected, used_tokens)
}

fn refresh_context_budget_state(app: &mut App) {
    let root = PathBuf::from(&app.cwd);
    if !root.is_dir() {
        app.context_budget_files.clear();
        app.context_budget_estimated_tokens = 0;
        return;
    }

    let (files, used_tokens) = compute_context_budget_files(&root, app.context_budget_tokens, 12);
    app.context_budget_files = files;
    app.context_budget_estimated_tokens = used_tokens;
}

fn format_context_budget_report(app: &App) -> String {
    let mut lines = vec![
        format!(
            "**Context Budget** (budget={} tok, used~{} tok)",
            app.context_budget_tokens, app.context_budget_estimated_tokens
        ),
        String::new(),
    ];
    if app.context_budget_files.is_empty() {
        lines.push("No candidate files selected.".to_string());
        return lines.join("\n");
    }

    for file in app.context_budget_files.iter().take(12) {
        lines.push(format!("- `{file}`"));
    }
    lines.push(String::new());
    lines.push(
        "Auto-selection is used when you send prompts without `@refs` or pinned files.".to_string(),
    );
    lines.join("\n")
}

fn command_data_dir(app: &App) -> PathBuf {
    Path::new(&app.cwd).join(".poor-cli")
}

fn focus_state_path(app: &App) -> PathBuf {
    command_data_dir(app).join("focus.json")
}

fn load_focus_state(app: &App) -> Result<Option<FocusState>, String> {
    let path = focus_state_path(app);
    if !path.exists() {
        return Ok(None);
    }
    let content =
        fs::read_to_string(&path).map_err(|e| format!("Failed to read focus state: {e}"))?;
    let state: FocusState =
        serde_json::from_str(&content).map_err(|e| format!("Invalid focus state: {e}"))?;
    Ok(Some(state))
}

fn save_focus_state(app: &App, state: &FocusState) -> Result<(), String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root).map_err(|e| format!("Failed to create data directory: {e}"))?;
    let path = focus_state_path(app);
    let serialized = serde_json::to_string_pretty(state)
        .map_err(|e| format!("Failed to serialize focus state: {e}"))?;
    fs::write(path, serialized).map_err(|e| format!("Failed to persist focus state: {e}"))
}

fn tasks_state_path(app: &App) -> PathBuf {
    command_data_dir(app).join("tasks.json")
}

fn load_tasks(app: &App) -> Result<Vec<TaskItem>, String> {
    let path = tasks_state_path(app);
    if !path.exists() {
        return Ok(vec![]);
    }
    let content = fs::read_to_string(path).map_err(|e| format!("Failed to read tasks: {e}"))?;
    let tasks: Vec<TaskItem> =
        serde_json::from_str(&content).map_err(|e| format!("Invalid tasks file: {e}"))?;
    Ok(tasks)
}

fn save_tasks(app: &App, tasks: &[TaskItem]) -> Result<(), String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root).map_err(|e| format!("Failed to create data directory: {e}"))?;
    let path = tasks_state_path(app);
    let serialized = serde_json::to_string_pretty(tasks)
        .map_err(|e| format!("Failed to serialize tasks: {e}"))?;
    fs::write(path, serialized).map_err(|e| format!("Failed to write tasks file: {e}"))
}

fn profile_state_path(app: &App) -> PathBuf {
    command_data_dir(app).join("profile.json")
}

fn load_profile_state(app: &App) -> Result<Option<ProfileState>, String> {
    let path = profile_state_path(app);
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(path).map_err(|e| format!("Failed to read profile: {e}"))?;
    let profile: ProfileState =
        serde_json::from_str(&content).map_err(|e| format!("Invalid profile state: {e}"))?;
    Ok(Some(profile))
}

fn save_profile_state(app: &App, profile: &ProfileState) -> Result<(), String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root).map_err(|e| format!("Failed to create data directory: {e}"))?;
    let path = profile_state_path(app);
    let serialized = serde_json::to_string_pretty(profile)
        .map_err(|e| format!("Failed to serialize profile: {e}"))?;
    fs::write(path, serialized).map_err(|e| format!("Failed to write profile: {e}"))
}

fn apply_execution_profile(
    app: &mut App,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    profile_name: &str,
    persist: bool,
) -> Result<String, String> {
    let normalized = profile_name.trim().to_ascii_lowercase();
    let (response_mode, context_budget, permission_mode, iteration_cap, notes) =
        match normalized.as_str() {
            "speed" => (
                ResponseMode::Poor,
                3200usize,
                "auto-safe",
                30u32,
                "Optimized for fast iteration and lower token usage.",
            ),
            "safe" => (
                ResponseMode::Rich,
                6000usize,
                "prompt",
                40u32,
                "Balanced defaults with safer execution prompts.",
            ),
            "deep-review" | "deep" => (
                ResponseMode::Rich,
                9000usize,
                "prompt",
                60u32,
                "Expanded context and deeper analysis defaults.",
            ),
            _ => return Err("Unknown profile. Use one of: speed, safe, deep-review".to_string()),
        };

    app.execution_profile = if normalized == "deep" {
        "deep-review".to_string()
    } else {
        normalized
    };
    app.response_mode = response_mode;
    app.context_budget_tokens = context_budget;
    app.iteration_cap = iteration_cap;

    let _ = rpc_set_config_blocking(
        rpc_cmd_tx,
        "security.permission_mode",
        Value::String(permission_mode.to_string()),
    );
    let _ = rpc_set_config_blocking(
        rpc_cmd_tx,
        "ui.response_mode",
        Value::String(app.response_mode.as_str().to_string()),
    );

    if persist {
        save_profile_state(
            app,
            &ProfileState {
                name: app.execution_profile.clone(),
            },
        )?;
    }

    Ok(format!(
        "Profile set to **{}**.\n- Response mode: `{}`\n- Permission mode: `{}`\n- Context budget: {} tokens\n- Iteration cap default: {}\n\n{}",
        app.execution_profile,
        app.response_mode.as_str(),
        permission_mode,
        app.context_budget_tokens,
        app.iteration_cap,
        notes
    ))
}

fn ws_url_host_port(url: &str) -> Result<(String, u16), String> {
    let trimmed = url.trim();
    let (without_scheme, default_port) = if let Some(rest) = trimmed.strip_prefix("ws://") {
        (rest, 80u16)
    } else if let Some(rest) = trimmed.strip_prefix("wss://") {
        (rest, 443u16)
    } else {
        return Err("URL must start with ws:// or wss://".to_string());
    };

    let authority = without_scheme.split('/').next().unwrap_or("").trim();
    if authority.is_empty() {
        return Err("URL is missing host".to_string());
    }

    if authority.starts_with('[') {
        if let Some(close_idx) = authority.find(']') {
            let host = authority[1..close_idx].to_string();
            let remainder = authority[close_idx + 1..].trim();
            let port = if let Some(port_text) = remainder.strip_prefix(':') {
                port_text
                    .parse::<u16>()
                    .map_err(|_| "Invalid URL port".to_string())?
            } else {
                default_port
            };
            return Ok((host, port));
        }
        return Err("Invalid IPv6 URL host".to_string());
    }

    if let Some((host, port_text)) = authority.rsplit_once(':') {
        if host.contains(':') {
            return Ok((authority.to_string(), default_port));
        }
        let port = port_text
            .parse::<u16>()
            .map_err(|_| "Invalid URL port".to_string())?;
        return Ok((host.to_string(), port));
    }

    Ok((authority.to_string(), default_port))
}

fn preflight_join_endpoint(url: &str) -> Result<String, String> {
    let (host, port) = ws_url_host_port(url)?;
    let addr_text = format!("{host}:{port}");
    let mut addrs = addr_text
        .to_socket_addrs()
        .map_err(|e| format!("Could not resolve `{host}`: {e}"))?;
    let target = addrs
        .next()
        .ok_or_else(|| format!("No reachable address found for `{host}`"))?;
    TcpStream::connect_timeout(&target, Duration::from_secs(2))
        .map_err(|e| format!("Could not reach {addr_text}: {e}"))?;
    Ok(format!("Preflight OK: reachable {addr_text}"))
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
    rpc_execute_command_with_timeout_blocking(rpc_cmd_tx, command, None, 60)
}

fn rpc_execute_command_with_timeout_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    command: &str,
    command_timeout_secs: Option<u64>,
    response_timeout_secs: u64,
) -> Result<String, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ExecuteCommand {
            command: command.to_string(),
            timeout: command_timeout_secs,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to send command to backend: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(response_timeout_secs))
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

fn rpc_set_api_key_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    provider: &str,
    api_key: &str,
    persist: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetApiKey {
            provider: provider.to_string(),
            api_key: api_key.to_string(),
            persist,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request API key update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for API key update".to_string())?
}

fn rpc_get_api_key_status_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    provider: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetApiKeyStatus {
            provider: provider.map(|s| s.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request API key status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for API key status".to_string())?
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

fn rpc_start_host_server_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StartHostServer {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host server start: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for host server start response".to_string())?
}

fn rpc_get_host_server_status_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetHostServerStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request host server status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for host server status response".to_string())?
}

fn rpc_stop_host_server_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StopHostServer { reply: reply_tx })
        .map_err(|e| format!("Failed to request host server stop: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host server stop response".to_string())?
}

fn rpc_list_host_members_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListHostMembers {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host members: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host members response".to_string())?
}

fn rpc_remove_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RemoveHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host member removal: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host member removal response".to_string())?
}

fn rpc_set_host_member_role_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    role: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHostMemberRole {
            connection_id: connection_id.to_string(),
            role: role.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host role update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host role update response".to_string())?
}

fn rpc_set_host_lobby_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    enabled: bool,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHostLobby {
            enabled,
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host lobby update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host lobby update response".to_string())?
}

fn rpc_approve_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ApproveHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host member approval: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host member approval response".to_string())?
}

fn rpc_deny_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::DenyHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host member denial: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host member denial response".to_string())?
}

fn rpc_rotate_host_token_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    role: &str,
    room: Option<&str>,
    expires_in_seconds: Option<u64>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RotateHostToken {
            role: role.to_string(),
            room: room.map(|value| value.to_string()),
            expires_in_seconds,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request token rotation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for token rotation response".to_string())?
}

fn rpc_revoke_host_token_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    value: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RevokeHostToken {
            value: value.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request token revocation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for token revocation response".to_string())?
}

fn rpc_handoff_host_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::HandoffHostMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request role handoff: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for role handoff response".to_string())?
}

fn rpc_set_host_preset_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    preset: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHostPreset {
            preset: preset.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request preset update: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for preset update response".to_string())?
}

fn rpc_list_host_activity_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
    limit: u64,
    event_type: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListHostActivity {
            room: room.map(|value| value.to_string()),
            limit,
            event_type: event_type.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request host activity: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for host activity response".to_string())?
}

fn rpc_start_service_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
    command: Option<&str>,
    cwd: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StartService {
            name: name.to_string(),
            command: command.map(|value| value.to_string()),
            cwd: cwd.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service start: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(90))
        .map_err(|_| "Timed out waiting for service start response".to_string())?
}

fn rpc_stop_service_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::StopService {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service stop: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(60))
        .map_err(|_| "Timed out waiting for service stop response".to_string())?
}

fn rpc_get_service_status_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetServiceStatus {
            name: name.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for service status response".to_string())?
}

fn rpc_get_service_logs_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
    lines: Option<u64>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetServiceLogs {
            name: name.to_string(),
            lines,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request service logs: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for service logs response".to_string())?
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
        return Err("No clipboard utility found. Install wl-copy, xclip, or xsel.".to_string());
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
    use clap::Parser;
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
    fn backend_server_args_empty_for_local_mode() {
        let cli = Cli::parse_from(["poor-cli-tui"]);
        let args = build_backend_server_args(&cli).expect("local mode args should build");
        assert!(args.is_empty());
    }

    #[test]
    fn backend_server_args_for_remote_mode() {
        let cli = Cli::parse_from([
            "poor-cli-tui",
            "--remote-url",
            "wss://example.test/rpc",
            "--remote-room",
            "dev",
            "--remote-token",
            "tok-123",
        ]);
        let args = build_backend_server_args(&cli).expect("remote args should build");
        assert_eq!(
            args,
            vec![
                "--bridge".to_string(),
                "--url".to_string(),
                "wss://example.test/rpc".to_string(),
                "--room".to_string(),
                "dev".to_string(),
                "--token".to_string(),
                "tok-123".to_string(),
            ]
        );
    }

    #[test]
    fn backend_server_args_require_complete_remote_triplet() {
        let cli = Cli::parse_from(["poor-cli-tui", "--remote-url", "wss://example.test/rpc"]);
        let err = build_backend_server_args(&cli).expect_err("should fail for partial remote args");
        assert!(err.contains("--remote-url"));
    }

    #[test]
    fn join_server_parser_accepts_invite_code() {
        let parsed = parse_join_server_args("/join-server ws://127.0.0.1:8765/rpc|dev|tok-abc")
            .expect("invite code should parse");
        assert_eq!(
            parsed,
            (
                "ws://127.0.0.1:8765/rpc".to_string(),
                "dev".to_string(),
                "tok-abc".to_string(),
            )
        );
    }

    #[test]
    fn join_server_parser_accepts_explicit_triplet() {
        let parsed = parse_join_server_args("/join-server wss://host.test/rpc docs tok-xyz")
            .expect("triplet should parse");
        assert_eq!(
            parsed,
            (
                "wss://host.test/rpc".to_string(),
                "docs".to_string(),
                "tok-xyz".to_string(),
            )
        );
    }

    #[test]
    fn join_server_parser_rejects_invalid_usage() {
        let err = parse_join_server_args("/join-server checkpoint")
            .expect_err("single non-code arg should fail");
        assert!(err.contains("Usage"));
    }

    #[test]
    fn onboarding_step_renderer_includes_navigation() {
        let rendered = format_onboarding_step(0);
        assert!(rendered.contains("Onboarding 1/"));
        assert!(rendered.contains("Navigation:"));
        assert!(rendered.contains("/onboarding next"));
    }

    #[test]
    fn onboarding_step_renderer_clamps_out_of_range_step() {
        let rendered = format_onboarding_step(usize::MAX);
        assert!(rendered.contains("Onboarding"));
        assert!(rendered.contains("final step"));
    }

    #[test]
    fn parse_bang_command_extracts_command_text() {
        assert_eq!(
            parse_bang_command("!cat README.md"),
            Some(BangCommandInput {
                command: "cat README.md".to_string(),
                question: None,
            })
        );
        assert_eq!(
            parse_bang_command("   !ls -la   "),
            Some(BangCommandInput {
                command: "ls -la".to_string(),
                question: None,
            })
        );
    }

    #[test]
    fn parse_bang_command_rejects_empty_or_non_bang_input() {
        assert_eq!(parse_bang_command("!"), None);
        assert_eq!(parse_bang_command("   !   "), None);
        assert_eq!(parse_bang_command("!   | explain this"), None);
        assert_eq!(parse_bang_command("/run ls"), None);
    }

    #[test]
    fn build_bang_command_prompt_includes_command_and_output() {
        let rendered = build_bang_command_prompt("cat file.txt", "hello\nworld", None);
        assert!(rendered.contains("Command: `cat file.txt`"));
        assert!(rendered.contains("hello"));
        assert!(rendered.contains("```text"));
    }

    #[test]
    fn parse_bang_command_extracts_optional_question() {
        assert_eq!(
            parse_bang_command("!cat README.md | summarize key points"),
            Some(BangCommandInput {
                command: "cat README.md".to_string(),
                question: Some("summarize key points".to_string()),
            })
        );
    }

    #[test]
    fn build_bang_command_prompt_includes_optional_question() {
        let rendered = build_bang_command_prompt("cat file.txt", "hello", Some("what is wrong?"));
        assert!(rendered.contains("User question: what is wrong?"));
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

    #[test]
    fn project_kind_detects_rust_python_mixed() {
        let root = create_temp_workspace("project-kind");
        fs::write(root.join("Cargo.toml"), "[package]\nname=\"x\"\n").expect("cargo file");
        fs::write(root.join("pyproject.toml"), "[project]\nname=\"x\"\n").expect("pyproject");
        assert_eq!(classify_project_kind(&root), "mixed");
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn context_budget_selection_respects_budget() {
        let root = create_temp_workspace("context-budget");
        fs::write(root.join("README.md"), "# app\n").expect("readme");
        fs::write(root.join("main.py"), "print('hello')\n".repeat(80)).expect("main py");
        fs::write(root.join("utils.py"), "def x():\n    return 1\n".repeat(50)).expect("utils py");

        let (files, used) = compute_context_budget_files(&root, 600, 12);
        assert!(!files.is_empty());
        assert!(used <= 600);
        assert!(files.iter().any(|path| path.ends_with("README.md")));
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn default_qa_command_prefers_python_when_pyproject_exists() {
        let root = create_temp_workspace("qa-default");
        fs::write(root.join("pyproject.toml"), "[project]\nname='x'\n").expect("pyproject");
        assert_eq!(default_qa_command_for_workspace(&root), "pytest -q");
        let _ = fs::remove_dir_all(root);
    }
}
