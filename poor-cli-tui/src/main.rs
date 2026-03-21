use std::cell::RefCell;
/// Entry point for the poor-cli Rust TUI.
use std::collections::{HashMap, HashSet, VecDeque};
use std::fs::{self, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc, Mutex};
use std::thread;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use clap::Parser;
use crossterm::{
    event::{DisableMouseCapture, EnableMouseCapture},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::prelude::*;
use serde::{Deserialize, Serialize};
use serde_json::Value;

use poor_cli_tui::app::{
    ApiKeyEditorField, ApiKeyEditorState, App, AppMode, ChatMessage,
    ContextInspectorFile, ContextInspectorState, ListSelectorItem, ListSelectorState,
    MessageRole, OverlayKind, ProviderEntry,
    QueuedPrompt, QuickOpenItem, QuickOpenItemKind, ResponseMode, ThemeMode, TimelineEntry,
    TimelineEntryKind,
};
use poor_cli_tui::event as app_event;
use poor_cli_tui::event::LoopControl;
use poor_cli_tui::helpers::{
    classify_project_kind, detect_project_traits, first_line, should_skip_dir, truncate_block,
    truncate_line,
};
use poor_cli_tui::input::{self, InputAction};
use poor_cli_tui::provider_catalog;
use poor_cli_tui::rpc::{
    run_rpc_worker, InitResult, ProviderInfo, RpcClient, RpcCommand, ServerNotification,
    StartupState,
};
use poor_cli_tui::watcher::{self, QaWatchState, WatchMsg, WatchState};

mod backend;
mod commands;
mod handler;
mod multiplayer;
mod session;
mod submit;

// re-export submodule items so `use super::*;` in commands/handler/multiplayer still finds them
#[allow(unused_imports)]
pub(crate) use session::{
    BackendLaunchContext, FocusState, ManagedEnvField, PreparedContextRequest, ProfileState,
    SessionLogWriter, StartupSelection,
};
#[allow(unused_imports)]
pub(crate) use session::{
    chat_display_kind, managed_env_fields, setup_session_logs, unix_ts_millis, write_session_log,
};
#[allow(unused_imports)]
pub(crate) use backend::{
    configured_startup_model, normalize_model_name, provider_default_model, provider_is_ready,
    resolve_startup_selection, server_msg_from_init_result, spawn_backend_worker,
};
#[allow(unused_imports)]
pub(crate) use submit::{
    apply_response_mode_to_user_input, build_bang_command_prompt, collect_directory_files,
    dispatch_next_queued_prompt, display_project_path, extract_at_references,
    find_suffix_matches, format_onboarding_step, handle_submit, is_startup_first_launch,
    mark_startup_first_launch_seen, onboarding_navigation_hint, onboarding_step_count,
    parse_bang_command, prepare_context_request, resolve_context_spec, resolve_context_specs,
    send_chat_request, send_chat_request_with_context, start_startup_onboarding_intro,
    status_view_has_unconfigured_provider, status_view_ready_provider_count,
    with_pending_images, BangCommandInput, OnboardingStep, ONBOARDING_STEPS,
    BANG_COMMAND_MAX_OUTPUT_CHARS, BANG_COMMAND_TIMEOUT_SECS, BANG_COMMAND_RESPONSE_TIMEOUT_SECS,
};

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
    /// Remote multiplayer invite code
    #[arg(long)]
    remote_invite: Option<String>,
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
        multiplayer_ui_role: Option<String>,
        multiplayer_mode: Option<String>,
        multiplayer_connection_id: Option<String>,
        multiplayer_display_name: Option<String>,
        multiplayer_approval_state: Option<String>,
    },
    ChatResponse {
        content: String,
    },
    SystemMessage {
        content: String,
    },
    AutomationPrompt {
        display: String,
        prompt: String,
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
    ThinkingChunk {
        request_id: String,
        chunk: String,
    },
    StreamChunk {
        request_id: String,
        chunk: String,
        done: bool,
        reason: Option<String>,
    },
    ToolEvent {
        request_id: String,
        event_type: String,
        tool_name: String,
        tool_args: Value,
        tool_result: String,
        diff: String,
        paths: Vec<String>,
        checkpoint_id: Option<String>,
        changed: Option<bool>,
        message: String,
        iteration_index: u32,
        iteration_cap: u32,
    },
    PermissionRequest {
        request_id: String,
        tool_name: String,
        tool_args: Value,
        prompt_id: String,
        operation: String,
        paths: Vec<String>,
        diff: String,
        checkpoint_id: Option<String>,
        changed: Option<bool>,
        message: String,
    },
    PlanRequest {
        request_id: String,
        prompt_id: String,
        summary: String,
        original_request: String,
        steps: Vec<String>,
    },
    Progress {
        request_id: String,
        phase: String,
        message: String,
        iteration_index: u32,
        iteration_cap: u32,
        nodes: Vec<(String, Vec<String>)>,
    },
    CostUpdate {
        request_id: String,
        input_tokens: u64,
        output_tokens: u64,
    },
    RoomEvent {
        room: String,
        mode: String,
        event_type: String,
        actor: String,
        request_id: String,
        queue_depth: u64,
        member_count: u64,
        active_connection_id: String,
        lobby_enabled: bool,
        preset: String,
        agenda_summary: Value,
        members: Value,
    },
    MemberRoleUpdated {
        room: String,
        connection_id: String,
        role: String,
        ui_role: String,
    },
    Suggestion {
        sender: String,
        text: String,
    },
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
    const MAX_REMOTE_RECONNECT_ATTEMPTS: u32 = 10;

    let backend_server_args = multiplayer::build_backend_server_args(&cli)
        .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;

    let mut app = App::new();
    app.cwd = cli.cwd.clone().unwrap_or_else(|| {
        std::env::current_dir()
            .ok()
            .and_then(|p| p.to_str().map(|s| s.to_string()))
            .unwrap_or_else(|| ".".into())
    });
    if let Some(invite) = cli.remote_invite.as_ref() {
        app.multiplayer.remote_invite = invite.clone();
        if let Ok(bootstrap) = multiplayer::decode_invite_code(invite) {
            app.multiplayer.room = bootstrap.room;
            app.multiplayer.enabled = true;
        }
    }
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
    app.permission_mode_label = permission_mode
        .clone()
        .unwrap_or_else(|| "prompt".to_string());
    let backend_log_path_string = backend_log_path
        .as_ref()
        .map(|path| path.to_string_lossy().to_string());
    let launch = BackendLaunchContext {
        python_bin: cli.python.clone(),
        cwd: cli.cwd.clone(),
        backend_log_path: backend_log_path_string,
        session_log: session_log.clone(),
    };
    let rpc_cmd_tx = RefCell::new(spawn_backend_worker(
        &tx,
        launch.clone(),
        backend_server_args.clone(),
        provider.clone(),
        model.clone(),
        permission_mode.clone(),
    ));

    app.provider.name = cli.provider.unwrap_or_else(|| "select provider".into());
    app.provider.model = cli.model.unwrap_or_default();
    app.startup_first_launch = is_startup_first_launch(&app);
    app.add_welcome();
    if let Ok(Some(saved_profile)) = load_profile_state(&app) {
        let _ = apply_execution_profile(&mut app, &rpc_cmd_tx.borrow(), &saved_profile.name, false);
    }
    refresh_context_budget_state(&mut app);
    if let (Some(tui_path), Some(backend_path)) = (tui_log_path.as_ref(), backend_log_path.as_ref())
    {
        app.set_status("Session logs ready");
        write_session_log(
            session_log.as_ref(),
            &format!(
                "session_logs_ready tui_path={} backend_path={}",
                tui_path.display(),
                backend_path.display()
            ),
        );
    }

    let cancel_token: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));
    let mut watch_state = WatchState::default();
    let mut qa_watch_state = QaWatchState::default();
    let remote_reconnect_state = RefCell::new((0u32, None::<std::time::Instant>, false));
    let tx_for_queue = tx.clone();
    let cancel_for_queue = cancel_token.clone();

    app_event::run_event_loop(
        terminal,
        &mut app,
        &rx,
        |app| {
            let mut reconnect: Option<(u32, multiplayer::RemoteBootstrap)> = None;
            let mut state = remote_reconnect_state.borrow_mut();
            if let Some(deadline) = state.1 {
                if std::time::Instant::now() >= deadline {
                    state.1 = None;
                    let attempt_label = state.0;
                    match multiplayer::decode_invite_code(&app.multiplayer.remote_invite) {
                        Ok(bootstrap) => reconnect = Some((attempt_label, bootstrap)),
                        Err(error) => {
                            state.2 = false;
                            app.push_message(ChatMessage::error(format!(
                                "Multiplayer reconnect cancelled: {error}"
                            )));
                        }
                    }
                }
            }
            drop(state);
            if let Some((attempt_label, bootstrap)) = reconnect {
                app.push_message(ChatMessage::system(format!(
                    "Attempting multiplayer reconnect ({attempt_label}/{MAX_REMOTE_RECONNECT_ATTEMPTS}) to session `{}`...",
                    bootstrap.room
                )));
                multiplayer::reconnect_to_remote_server(
                    app,
                    &tx,
                    &mut rpc_cmd_tx.borrow_mut(),
                    &launch,
                    &bootstrap,
                );
            }
            Ok(LoopControl::Continue)
        },
        |app, msg| {
            let result = handler::handle_server_message(
                app,
                msg,
                &rpc_cmd_tx,
                &remote_reconnect_state,
                MAX_REMOTE_RECONNECT_ATTEMPTS,
                session_log.as_ref(),
            )?;
            // auto-dispatch next queued prompt when AI finishes
            if !app.waiting
                && !app.prompt_queue.is_empty()
                && !app.queue_paused
                && app.plan.steps.is_empty()
            {
                dispatch_next_queued_prompt(
                    app,
                    &tx_for_queue,
                    &rpc_cmd_tx.borrow(),
                    &cancel_for_queue,
                    session_log.as_ref(),
                );
            }
            Ok(result)
        },
        |app, input_action| {
            match input_action {
                InputAction::Submit(text) => {
                    write_session_log(
                        session_log.as_ref(),
                        &format!(
                            "input_submit chars={} slash={} bang={}",
                            text.len(),
                            text.trim_start().starts_with('/'),
                            text.trim_start().starts_with('!')
                        ),
                    );
                    if handle_submit(
                        app,
                        &tx,
                        &mut rpc_cmd_tx.borrow_mut(),
                        &launch,
                        &cancel_token,
                        &mut watch_state,
                        &mut qa_watch_state,
                        &text,
                    ) {
                        return Ok(LoopControl::Break);
                    }
                }
                InputAction::Cancel => {
                    write_session_log(
                        session_log.as_ref(),
                        &format!("input_cancel active_request_id={}", app.streaming.active_request_id),
                    );
                    cancel_token.store(true, Ordering::SeqCst);
                    let _ = rpc_cmd_tx.borrow().send(RpcCommand::CancelRequest);
                    app.finalize_streaming();
                    app.streaming.active_request_id.clear();
                    app.streaming.active_request_started_at = None;
                    app.stop_waiting();
                    app.set_status("Request cancelled");
                }
                InputAction::Quit => {
                    write_session_log(session_log.as_ref(), "input_quit");
                    return Ok(LoopControl::Break);
                }
                InputAction::ProviderSelected(idx) => {
                    if let Some(provider) = app.provider.list.get(idx) {
                        let name = provider.name.clone();
                        let model = if idx == app.provider.select_idx {
                            app.selected_provider_switch_model()
                        } else {
                            provider.models.first().cloned()
                        };
                        write_session_log(
                            session_log.as_ref(),
                            &format!(
                                "provider_switch_request provider={} model={}",
                                name,
                                model.clone().unwrap_or_default()
                            ),
                        );
                        app.set_status(format!("Switching to {name}..."));
                        let tx2 = tx.clone();
                        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
                        if rpc_cmd_tx.borrow().send(RpcCommand::SwitchProvider {
                            provider: name.clone(),
                            model,
                            reply: reply_tx,
                        }).is_err() {
                            app.push_message(ChatMessage::error(
                                format!("Failed to switch provider `{name}`: RPC worker unavailable")
                            ));
                        } else {
                            thread::spawn(move || match reply_rx.recv_timeout(Duration::from_secs(30)) {
                                Ok(Ok((prov, mdl))) => {
                                    let _ = tx2.send(ServerMsg::ProviderSwitched {
                                        provider: prov,
                                        model: mdl,
                                    });
                                }
                                Ok(Err(error)) => {
                                    let mut message =
                                        format!("Failed to switch provider `{name}`: {error}");
                                    if name.eq_ignore_ascii_case("ollama") {
                                        message.push_str(
                                            "\nTry `/ollama start`, then `/ollama pull <model>`, and switch again.",
                                        );
                                    }
                                    let _ = tx2.send(ServerMsg::SystemMessage {
                                        content: format!("⚠ {message}"),
                                    });
                                }
                                Err(_) => {
                                    let _ = tx2.send(ServerMsg::SystemMessage {
                                        content: format!(
                                            "⚠ Timed out switching provider `{name}`"
                                        ),
                                    });
                                }
                            });
                        }
                    }
                }
                InputAction::PermissionAnswered(allowed) => {
                    // prefer inline approval state, fall back to legacy fields
                    let inline_approval = app.pending_approval.take();
                    let review_state = if let Some(ref ia) = inline_approval {
                        ia.mutation_review.clone()
                    } else {
                        app.mutation_review.clone()
                    };
                    let prompt_id = if let Some(ref ia) = inline_approval {
                        ia.prompt_id.clone()
                    } else {
                        std::mem::take(&mut app.permission_prompt_id)
                    };
                    let approved_paths = if allowed {
                        std::mem::take(&mut app.permission_approved_paths)
                    } else {
                        app.permission_approved_paths.clear();
                        Vec::new()
                    };
                    let approved_chunks = if allowed {
                        std::mem::take(&mut app.permission_approved_chunks)
                    } else {
                        app.permission_approved_chunks.clear();
                        Vec::new()
                    };
                    if let Some(review) = review_state.as_ref() {
                        let review_summary = review.build_decision_summary(
                            allowed,
                            &approved_paths,
                            &approved_chunks,
                        );
                        app.push_timeline_entry(TimelineEntry {
                            kind: TimelineEntryKind::Permission,
                            request_id: review.request_id.clone(),
                            title: if allowed {
                                "Review accepted".to_string()
                            } else {
                                "Review rejected".to_string()
                            },
                            detail: review_summary.headline(),
                            diff: String::new(),
                            paths: review
                                .paths
                                .iter()
                                .cloned()
                                .chain(review_summary.files.iter().map(|file| file.path.clone()))
                                .collect::<std::collections::BTreeSet<_>>()
                                .into_iter()
                                .collect(),
                            checkpoint_id: review.checkpoint_id.clone(),
                            changed: review.changed,
                            review_summary: Some(review_summary),
                            timestamp: std::time::Instant::now(),
                        });
                    }
                    app.close_mutation_review();
                    app.mode = AppMode::Normal;
                    write_session_log(
                        session_log.as_ref(),
                        &format!(
                            "permission_answer prompt_id={} allowed={}",
                            prompt_id, allowed
                        ),
                    );
                    let _ = rpc_cmd_tx.borrow().send(RpcCommand::SendNotification {
                        method: "poor-cli/permissionRes".into(),
                        params: serde_json::json!({
                            "promptId": prompt_id,
                            "allowed": allowed,
                            "approvedPaths": approved_paths,
                            "approvedChunks": approved_chunks
                                .into_iter()
                                .map(|chunk| serde_json::json!({
                                    "path": chunk.path,
                                    "index": chunk.hunk_index,
                                }))
                                .collect::<Vec<_>>(),
                        }),
                    });
                }
                InputAction::PlanApproved => {
                    if !app.plan.prompt_id.is_empty() && app.plan.is_execution_gate {
                        let prompt_id = app.plan.prompt_id.clone();
                        let _ = rpc_cmd_tx.borrow().send(RpcCommand::SendNotification {
                            method: "poor-cli/planRes".into(),
                            params: serde_json::json!({
                                "promptId": prompt_id,
                                "allowed": true,
                            }),
                        });
                        write_session_log(session_log.as_ref(), "plan_gate_approved");
                        app.clear_plan();
                        app.set_status("Plan approved");
                    } else {
                        let step_idx = app.plan.current_step;
                        let step_desc = app.current_plan_step_description().map(|s| s.to_string());
                        let orig = app.plan.original_request.clone();
                        if let Some(desc) = step_desc {
                            write_session_log(
                                session_log.as_ref(),
                                &format!(
                                    "plan_step_approved step_index={} step_desc_chars={}",
                                    step_idx,
                                    desc.len()
                                ),
                            );
                            let exec_msg = format!(
                                "Execute step {} of my plan: {}\n\nOriginal request: {}",
                                step_idx + 1,
                                desc,
                                orig,
                            );
                            let display = format!("[plan step {}] {}", step_idx + 1, desc);
                            if step_idx < app.plan.steps.len() {
                                app.plan.steps[step_idx].status =
                                    poor_cli_tui::app::PlanStepStatus::Running;
                            }
                            send_chat_request(
                                app,
                                &tx,
                                &rpc_cmd_tx.borrow(),
                                &cancel_token,
                                exec_msg,
                                display,
                                session_log.as_ref(),
                            );
                        }
                    }
                }
                InputAction::PlanCancelled => {
                    if !app.plan.prompt_id.is_empty() && app.plan.is_execution_gate {
                        let prompt_id = app.plan.prompt_id.clone();
                        let _ = rpc_cmd_tx.borrow().send(RpcCommand::SendNotification {
                            method: "poor-cli/planRes".into(),
                            params: serde_json::json!({
                                "promptId": prompt_id,
                                "allowed": false,
                            }),
                        });
                        write_session_log(session_log.as_ref(), "plan_gate_rejected");
                        app.clear_plan();
                        app.set_status("Plan rejected");
                    } else {
                        write_session_log(session_log.as_ref(), "plan_cancelled");
                        app.clear_plan();
                        app.set_status("Plan cancelled");
                    }
                }
                InputAction::CompactStrategySelected(strategy) => {
                    app.set_status(format!("Applying context strategy: {strategy}..."));
                    let rpc = rpc_cmd_tx.borrow().clone();
                    let tx_clone = tx.clone();
                    thread::spawn(move || {
                        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
                        let _ = rpc.send(RpcCommand::CompactContext {
                            strategy: strategy.clone(),
                            reply: reply_tx,
                        });
                        match reply_rx.recv_timeout(Duration::from_secs(60)) {
                            Ok(Ok(val)) => {
                                let summary = val
                                    .get("summary")
                                    .and_then(|v| v.as_str())
                                    .unwrap_or("done");
                                let before = val
                                    .get("messages_before")
                                    .and_then(|v| v.as_u64())
                                    .unwrap_or(0);
                                let after = val
                                    .get("messages_after")
                                    .and_then(|v| v.as_u64())
                                    .unwrap_or(0);
                                let msg = format!(
                                    "**Context {strategy}** applied: {before} -> {after} messages\n\n{summary}"
                                );
                                let _ = tx_clone.send(ServerMsg::SystemMessage { content: msg });
                            }
                            Ok(Err(e)) => {
                                let _ = tx_clone.send(ServerMsg::SystemMessage {
                                    content: format!("Context strategy failed: {e}"),
                                });
                            }
                            Err(_) => {
                                let _ = tx_clone.send(ServerMsg::SystemMessage {
                                    content: "Context strategy timed out".into(),
                                });
                            }
                        }
                    });
                }
                InputAction::JoinWizardComplete(bootstrap) => {
                    multiplayer::reconnect_to_remote_server(
                        app,
                        &tx,
                        &mut rpc_cmd_tx.borrow_mut(),
                        &launch,
                        &bootstrap,
                    );
                }
                InputAction::SaveApiKeyEditor => {
                    match save_api_key_editor(app, &tx, &rpc_cmd_tx.borrow()) {
                        Ok(message) => {
                            if let Some(editor) = app.api_key_editor.as_mut() {
                                editor.status = message;
                                editor.error.clear();
                            } else {
                                app.set_status("Saved API key configuration");
                            }
                        }
                        Err(error) => {
                            if let Some(editor) = app.api_key_editor.as_mut() {
                                editor.error = error;
                                editor.status.clear();
                            } else {
                                app.push_message(ChatMessage::error(error));
                            }
                        }
                    }
                }
                InputAction::CopyToClipboard(text) => match copy_to_clipboard(&text) {
                    Ok(()) => {
                        let preview = if text.len() > 40 {
                            format!("{}...", &text[..40])
                        } else {
                            text.clone()
                        };
                        app.set_status(format!("Copied: {preview}"));
                    }
                    Err(e) => app.set_status(format!("Copy failed: {e}")),
                },
                InputAction::OpenQuickOpen => {
                    let items = build_quick_open_items(app, &rpc_cmd_tx.borrow());
                    app.open_quick_open(items);
                }
                InputAction::QuickOpenSelected(item) => {
                    app.close_quick_open();
                    match item.kind {
                        QuickOpenItemKind::Command | QuickOpenItemKind::Prompt => {
                            app.input_buffer = item.value;
                            app.input_cursor = app.input_buffer.len();
                            app.mode = AppMode::Normal;
                        }
                        QuickOpenItemKind::File => {
                            let rendered = if item.value.contains(char::is_whitespace) {
                                format!("@\"{}\"", item.value)
                            } else {
                                format!("@{}", item.value)
                            };
                            if app.input_buffer.is_empty() {
                                app.input_buffer = format!("{rendered} ");
                            } else {
                                app.input_buffer.push_str(&format!(" {rendered} "));
                            }
                            app.input_cursor = app.input_buffer.len();
                            app.mode = AppMode::Normal;
                        }
                        QuickOpenItemKind::Checkpoint => {
                            match rpc_restore_checkpoint_blocking(
                                &rpc_cmd_tx.borrow(),
                                Some(&item.value),
                            ) {
                                Ok(payload) => {
                                    let checkpoint_id = payload
                                        .get("checkpointId")
                                        .and_then(|v| v.as_str())
                                        .unwrap_or(&item.value);
                                    app.remember_recent_checkpoint(checkpoint_id);
                                    refresh_workspace_status(app);
                                    refresh_resume_dashboard(app, &rpc_cmd_tx.borrow());
                                    app.push_message(ChatMessage::system(format!(
                                        "Restored checkpoint `{checkpoint_id}` from quick open."
                                    )));
                                }
                                Err(error) => app.push_message(ChatMessage::error(format!(
                                    "Failed to restore checkpoint `{}`: {error}",
                                    item.value
                                ))),
                            }
                        }
                    }
                }
                InputAction::RestoreLastMutation => {
                    let Some(checkpoint_id) = app.last_mutation_checkpoint_id.clone() else {
                        app.set_status("No recent mutation checkpoint available");
                        return Ok(LoopControl::Continue);
                    };
                    match rpc_restore_checkpoint_blocking(
                        &rpc_cmd_tx.borrow(),
                        Some(&checkpoint_id),
                    ) {
                        Ok(payload) => {
                            let restored = payload
                                .get("restoredFiles")
                                .and_then(|v| v.as_u64())
                                .unwrap_or(0);
                            refresh_workspace_status(app);
                            refresh_resume_dashboard(app, &rpc_cmd_tx.borrow());
                            app.push_message(ChatMessage::system(format!(
                                "Restored checkpoint `{checkpoint_id}` ({restored} file(s))."
                            )));
                        }
                        Err(error) => app.push_message(ChatMessage::error(format!(
                            "Failed to restore `{checkpoint_id}`: {error}"
                        ))),
                    }
                }
                InputAction::OpenFileInEditor(path) => match open_file_in_editor(&path) {
                    Ok(()) => app.set_status(format!("Opened `{path}`")),
                    Err(error) => app.push_message(ChatMessage::error(error)),
                },
                InputAction::Redraw => {}
                InputAction::None => {}
            }
            Ok(LoopControl::Continue)
        },
    )?;

    watch_state.stop();
    qa_watch_state.stop();
    let _ = rpc_cmd_tx.borrow().send(RpcCommand::Shutdown);
    write_session_log(session_log.as_ref(), "tui_session_end");
    Ok(app.session_summary_text())
}

fn watch_msg_sender(tx: &mpsc::Sender<ServerMsg>) -> mpsc::Sender<WatchMsg> {
    let (watch_tx, watch_rx) = mpsc::channel();
    let tx = tx.clone();
    thread::spawn(move || {
        for msg in watch_rx {
            let server_msg = match msg {
                WatchMsg::System(content) => ServerMsg::SystemMessage { content },
                WatchMsg::AutomationPrompt { display, prompt } => {
                    ServerMsg::AutomationPrompt { display, prompt }
                }
                WatchMsg::Error(message) => ServerMsg::Error { message },
            };
            if tx.send(server_msg).is_err() {
                break;
            }
        }
    });
    watch_tx
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

fn format_host_server_payload(payload: &Value) -> String {
    let running = payload
        .get("running")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !running {
        return "No collaboration host is running.\nUse `/collab start mob` to start one.".to_string();
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
    let local_signaling = payload
        .get("localSignalingUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let share_signaling = payload
        .get("shareSignalingUrl")
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let public_signaling = payload
        .get("publicSignalingUrl")
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

    if !local_signaling.is_empty() {
        lines.push(format!("Local signaling: `{local_signaling}`"));
    }
    if !share_signaling.is_empty() {
        lines.push(format!("LAN signaling: `{share_signaling}`"));
        if bind_host == "0.0.0.0" && share_signaling.contains("127.0.0.1") {
            lines.push(
                "**⚠ ACTION REQUIRED:** LAN IP detection fell back to localhost. Replace `127.0.0.1` with your actual LAN IP before sharing."
                    .to_string(),
            );
        }
    }
    if !public_signaling.is_empty() {
        lines.push(format!("Public signaling: `{public_signaling}`"));
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
        let viewer_join = room
            .get("viewerJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let prompter_join = room
            .get("prompterJoinCommand")
            .and_then(|v| v.as_str())
            .unwrap_or("");
        let signaling_url = room
            .get("signalingUrl")
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
        if !signaling_url.is_empty() {
            lines.push(format!("- Signaling endpoint: `{signaling_url}`"));
        }
        if !viewer_join.is_empty() {
            lines.push(format!("- Share viewer command: `{viewer_join}`"));
        }
        if !prompter_join.is_empty() {
            lines.push(format!("- Share prompter command: `{prompter_join}`"));
        }
        if !viewer_code.is_empty() {
            lines.push(format!("- Viewer invite code: `{viewer_code}`"));
        }
        if !prompter_code.is_empty() {
            lines.push(format!("- Prompter invite code: `{prompter_code}`"));
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
        return "No collaboration host is running.\nUse `/collab start mob` to start one.".to_string();
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
        return "No collaboration host is running.\nUse `/collab start mob` to start one.".to_string();
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

fn format_room_members_payload(payload: &Value) -> String {
    let room = payload
        .get("room")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let mode = payload
        .get("mode")
        .and_then(|value| value.as_str())
        .unwrap_or("pair");
    let agenda_summary = payload
        .get("agendaSummary")
        .and_then(|value| value.as_object())
        .cloned()
        .unwrap_or_default();
    let agenda_open = agenda_summary
        .get("open")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let agenda_total = agenda_summary
        .get("total")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let hands_raised = payload
        .get("handsRaised")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();
    let members = payload
        .get("members")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();

    let mut lines = vec![
        format!("**Collaboration Status** room `{room}`"),
        format!("- Mode: `{mode}`"),
        format!("- Members: {}", members.len()),
    ];
    if agenda_total > 0 {
        lines.push(format!(
            "- Agenda: {agenda_open} open / {agenda_total} total"
        ));
    }
    if !hands_raised.is_empty() {
        let raised = hands_raised
            .iter()
            .filter_map(|value| value.as_str())
            .collect::<Vec<_>>()
            .join(", ");
        if !raised.is_empty() {
            lines.push(format!("- Hands raised: {raised}"));
        }
    }

    if members.is_empty() {
        lines.push("- No members connected".to_string());
        return lines.join("\n");
    }

    lines.push(String::new());
    lines.push("**Members**".to_string());
    for member in members {
        let connection_id = member
            .get("connection_id")
            .or_else(|| member.get("connectionId"))
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let display_name = member
            .get("display_name")
            .or_else(|| member.get("displayName"))
            .and_then(|value| value.as_str())
            .unwrap_or(connection_id);
        let role = member
            .get("ui_role")
            .or_else(|| member.get("uiRole"))
            .or_else(|| member.get("role"))
            .and_then(|value| value.as_str())
            .unwrap_or("unknown");
        let approval_state = member
            .get("approval_state")
            .or_else(|| member.get("approvalState"))
            .and_then(|value| value.as_str())
            .unwrap_or("approved");
        let active_prompter = member
            .get("is_active_prompter")
            .or_else(|| member.get("active"))
            .and_then(|value| value.as_bool())
            .unwrap_or(false);
        let hand_raised = member
            .get("hand_raised")
            .or_else(|| member.get("handRaised"))
            .and_then(|value| value.as_bool())
            .unwrap_or(false);
        let queue_position = member
            .get("queue_position")
            .or_else(|| member.get("queuePosition"))
            .and_then(|value| value.as_u64())
            .unwrap_or(0);

        let mut tags = vec![format!("role=`{role}`")];
        if active_prompter {
            tags.push("active".to_string());
        }
        if approval_state != "approved" {
            tags.push(format!("approval=`{approval_state}`"));
        }
        if hand_raised {
            if queue_position > 0 {
                tags.push(format!("hand-raised#{}", queue_position));
            } else {
                tags.push("hand-raised".to_string());
            }
        }
        lines.push(format!(
            "- `{display_name}` (`{connection_id}`) {}",
            tags.join(" ")
        ));
    }
    lines.join("\n")
}

fn format_agenda_payload(payload: &Value) -> String {
    let room = payload
        .get("room")
        .and_then(|value| value.as_str())
        .unwrap_or("unknown");
    let agenda_summary = payload
        .get("agendaSummary")
        .and_then(|value| value.as_object())
        .cloned()
        .unwrap_or_default();
    let agenda_open = agenda_summary
        .get("open")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let agenda_total = agenda_summary
        .get("total")
        .and_then(|value| value.as_u64())
        .unwrap_or(0);
    let items = payload
        .get("items")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default();

    let mut lines = vec![format!("**Shared Agenda** room `{room}`")];
    if agenda_total > 0 {
        lines.push(format!("- {agenda_open} open / {agenda_total} total"));
    }
    if items.is_empty() {
        lines.push("- No agenda items yet".to_string());
        return lines.join("\n");
    }

    for item in items {
        let item_id = item
            .get("id")
            .and_then(|value| value.as_u64())
            .map(|value| value.to_string())
            .unwrap_or_else(|| "?".to_string());
        let text = item
            .get("text")
            .and_then(|value| value.as_str())
            .unwrap_or("(untitled)");
        let author = item
            .get("author")
            .and_then(|value| value.as_str())
            .unwrap_or("");
        let resolved = item
            .get("resolved")
            .and_then(|value| value.as_bool())
            .unwrap_or(false);
        let status = if resolved { "done" } else { "open" };
        if author.is_empty() {
            lines.push(format!("- #{item_id} [{status}] {text}"));
        } else {
            lines.push(format!("- #{item_id} [{status}] {text} ({author})"));
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

fn ollama_recovery_popup(error_message: &str, model_name: &str) -> Option<(String, String)> {
    let lowered = error_message.to_ascii_lowercase();

    if lowered.contains("cannot connect to host")
        || lowered.contains("ollama server not available")
        || lowered.contains("connect call failed")
    {
        return Some((
            "Ollama Not Reachable".to_string(),
            "The Ollama server is not reachable at `http://localhost:11434`.\n\n\
Run:\n\
- `/ollama start`\n\
- `/ollama status`\n\
- `/ollama logs`\n\n\
If startup fails, run `/service status ollama` to verify the executable path and logs."
                .to_string(),
        ));
    }

    if lowered.contains("model")
        && lowered.contains("not found")
        && (lowered.contains("ollama") || lowered.contains("/api/chat"))
    {
        return Some((
            "Ollama Model Missing".to_string(),
            format!(
                "Your active Ollama model is missing locally.\n\n\
Model: `{model_name}`\n\n\
Run:\n\
- `/ollama pull {model_name}`\n\
- `/ollama list-models`\n\
- `/switch` (reselect Ollama model if needed)"
            ),
        ));
    }

    None
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
    if let Some(available) = payload.get("available").and_then(|v| v.as_bool()) {
        lines.push(format!(
            "- Executable: {}",
            if available { "found" } else { "not found" }
        ));
    }
    if let Some(executable) = payload.get("executable").and_then(|v| v.as_str()) {
        if !executable.is_empty() {
            lines.push(format!("- Executable path: `{executable}`"));
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
        let available = payload
            .get("available")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);
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
        if !available {
            lines.push(
                "- Install Ollama or expose it in PATH. You can also set `OLLAMA_BIN=/absolute/path/to/ollama`."
                    .to_string(),
            );
        }
        if !running {
            lines.push("- Start with `/ollama start`.".to_string());
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
            let available = service
                .get("available")
                .and_then(|v| v.as_bool())
                .unwrap_or(true);
            let availability = if available {
                ""
            } else {
                " [missing executable]"
            };
            lines.push(format!(
                "- {marker} `{name}`: {state} ({scope}){availability}"
            ));
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

fn refresh_workspace_status(app: &mut App) {
    if app.cwd.is_empty() {
        return;
    }

    let output = Command::new("git")
        .args(["-C", &app.cwd, "status", "-sb"])
        .output();
    let Ok(output) = output else {
        app.git_branch.clear();
        app.git_dirty = false;
        if app.resume_dashboard.git_summary.is_empty() {
            app.resume_dashboard.git_summary = "(git unavailable)".to_string();
        }
        return;
    };
    if !output.status.success() {
        app.git_branch.clear();
        app.git_dirty = false;
        app.resume_dashboard.git_summary = "(not a git repository)".to_string();
        return;
    }

    let status = String::from_utf8_lossy(&output.stdout).to_string();
    let mut lines = status.lines();
    let branch_line = lines
        .next()
        .unwrap_or("")
        .trim()
        .trim_start_matches("## ")
        .to_string();
    app.git_dirty = lines.next().is_some();
    app.git_branch = branch_line
        .split("...")
        .next()
        .unwrap_or(branch_line.as_str())
        .trim()
        .to_string();
    app.resume_dashboard.git_summary = if branch_line.is_empty() {
        "(git unavailable)".to_string()
    } else if app.git_dirty {
        format!("{branch_line} *dirty*")
    } else {
        branch_line
    };
}

fn refresh_resume_dashboard(app: &mut App, rpc_cmd_tx: &mpsc::Sender<RpcCommand>) {
    let mut dashboard = app.resume_dashboard.clone();
    dashboard.recent_edits = app.recent_edited_files.iter().take(5).cloned().collect();
    dashboard.git_summary = app.resume_dashboard.git_summary.clone();

    if let Ok(payload) = rpc_list_sessions_blocking(rpc_cmd_tx, 1) {
        let sessions = payload
            .get("sessions")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        if let Some(first) = sessions.first() {
            let session_id = first
                .get("sessionId")
                .and_then(|value| value.as_str())
                .unwrap_or("(unknown)");
            let model = first
                .get("model")
                .and_then(|value| value.as_str())
                .unwrap_or("(unknown)");
            let message_count = first
                .get("messageCount")
                .and_then(|value| value.as_u64())
                .unwrap_or(0);
            dashboard.last_session_summary =
                format!("{session_id} on {model} ({message_count} messages)");
        }
    }

    if let Ok(payload) = rpc_list_checkpoints_blocking(rpc_cmd_tx, 5) {
        let checkpoints = payload
            .get("checkpoints")
            .and_then(|value| value.as_array())
            .cloned()
            .unwrap_or_default();
        dashboard.recent_checkpoints = checkpoints
            .iter()
            .filter_map(|entry| entry.get("checkpointId").and_then(|value| value.as_str()))
            .take(5)
            .map(|value| value.to_string())
            .collect();
    }

    if let Ok(payload) = rpc_get_service_status_blocking(rpc_cmd_tx, None) {
        if let Some(services) = payload.get("services").and_then(|value| value.as_array()) {
            dashboard.active_services = services
                .iter()
                .filter(|entry| {
                    entry
                        .get("running")
                        .and_then(|value| value.as_bool())
                        .unwrap_or(false)
                })
                .filter_map(|entry| entry.get("name").and_then(|value| value.as_str()))
                .take(5)
                .map(|value| value.to_string())
                .collect();
        }
    }

    app.set_resume_dashboard(dashboard);
}

fn refresh_workspace_panels(_app: &mut App, _rpc_cmd_tx: &mpsc::Sender<RpcCommand>) {
    // workspace panels removed; nothing to refresh
}

fn resolve_explicit_context_map(
    app: &App,
    message: &str,
) -> Result<HashMap<String, String>, String> {
    let inline_specs = extract_at_references(message)?;
    let mut mapping = HashMap::new();
    for spec in inline_specs {
        let matches = resolve_context_spec(app, &spec);
        if matches.len() == 1 {
            mapping.insert(matches[0].to_string_lossy().to_string(), spec);
        }
    }
    Ok(mapping)
}

fn resolve_pinned_context_map(app: &App) -> HashMap<String, String> {
    let mut mapping = HashMap::new();
    for spec in &app.pinned_context_files {
        let matches = resolve_context_spec(app, spec);
        if matches.len() == 1 {
            mapping.insert(matches[0].to_string_lossy().to_string(), spec.clone());
        }
    }
    mapping
}

fn open_context_inspector_for_message(
    app: &mut App,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    message: String,
) -> Result<(), String> {
    let prepared = prepare_context_request(app, &message)?;
    let preview = rpc_get_context_explain_blocking(
        rpc_cmd_tx,
        &prepared.message,
        &prepared.explicit_files,
        &prepared.pinned_files,
        Some(app.context_budget_tokens),
    )?;

    let explicit_map = resolve_explicit_context_map(app, &message)?;
    let pinned_map = resolve_pinned_context_map(app);
    let files = preview
        .get("files")
        .and_then(|value| value.as_array())
        .cloned()
        .unwrap_or_default()
        .into_iter()
        .filter_map(|entry| {
            let path = entry
                .get("path")
                .and_then(|value| value.as_str())?
                .to_string();
            let source = entry
                .get("source")
                .and_then(|value| value.as_str())
                .unwrap_or("auto")
                .to_string();
            Some(ContextInspectorFile {
                explicit_spec: if source == "explicit" {
                    explicit_map.get(&path).cloned()
                } else if source == "pinned" {
                    pinned_map.get(&path).cloned()
                } else {
                    None
                },
                path: path.clone(),
                source,
                estimated_tokens: entry
                    .get("estimatedTokens")
                    .and_then(|value| value.as_u64())
                    .unwrap_or(0) as usize,
                reason: entry
                    .get("reason")
                    .and_then(|value| value.as_str())
                    .unwrap_or("")
                    .to_string(),
                include_full_content: entry
                    .get("includeFullContent")
                    .and_then(|value| value.as_bool())
                    .unwrap_or(false),
            })
        })
        .collect::<Vec<_>>();

    app.context_budget_files = files.iter().map(|file| file.path.clone()).collect();
    app.context_budget_estimated_tokens = preview
        .get("totalTokens")
        .and_then(|value| value.as_u64())
        .unwrap_or(0) as usize;
    app.open_context_inspector(ContextInspectorState {
        request_message: prepared.message,
        total_tokens: app.context_budget_estimated_tokens,
        budget_tokens: app.context_budget_tokens,
        truncated: preview
            .get("truncated")
            .and_then(|value| value.as_bool())
            .unwrap_or(false),
        message: preview
            .get("message")
            .and_then(|value| value.as_str())
            .unwrap_or("")
            .to_string(),
        keywords: preview
            .get("keywords")
            .and_then(|value| value.as_array())
            .map(|items| {
                items
                    .iter()
                    .filter_map(|item| item.as_str().map(|value| value.to_string()))
                    .collect()
            })
            .unwrap_or_default(),
        files,
        selected_index: 0,
    });
    Ok(())
}

fn build_quick_open_items(app: &App, rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Vec<QuickOpenItem> {
    let mut items = Vec::new();

    for spec in input::SLASH_COMMANDS.iter().take(24) {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::Command,
            label: spec.command.to_string(),
            detail: spec.description.to_string(),
            value: spec.command.to_string(),
        });
    }

    for file in &app.pinned_context_files {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::File,
            label: file.clone(),
            detail: "pinned file".to_string(),
            value: file.clone(),
        });
    }

    for file in app.recent_edited_files.iter().take(10) {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::File,
            label: file.clone(),
            detail: "recent edit".to_string(),
            value: file.clone(),
        });
    }

    if let Ok(payload) = rpc_list_checkpoints_blocking(rpc_cmd_tx, 8) {
        if let Some(checkpoints) = payload
            .get("checkpoints")
            .and_then(|value| value.as_array())
        {
            for checkpoint in checkpoints.iter().take(8) {
                if let Some(checkpoint_id) = checkpoint
                    .get("checkpointId")
                    .and_then(|value| value.as_str())
                {
                    let description = checkpoint
                        .get("description")
                        .and_then(|value| value.as_str())
                        .unwrap_or("checkpoint");
                    items.push(QuickOpenItem {
                        kind: QuickOpenItemKind::Checkpoint,
                        label: checkpoint_id.to_string(),
                        detail: description.to_string(),
                        value: checkpoint_id.to_string(),
                    });
                }
            }
        }
    }

    for prompt in app.recent_prompts.iter().take(10) {
        items.push(QuickOpenItem {
            kind: QuickOpenItemKind::Prompt,
            label: truncate_line(prompt, 42),
            detail: "recent prompt".to_string(),
            value: prompt.clone(),
        });
    }

    items
}

fn open_file_in_editor(path: &str) -> Result<(), String> {
    let editor = std::env::var("EDITOR").unwrap_or_else(|_| "vi".to_string());
    let mut parts = editor.split_whitespace();
    let Some(program) = parts.next() else {
        return Err("EDITOR is empty".to_string());
    };

    let mut command = Command::new(program);
    for arg in parts {
        command.arg(arg);
    }
    command.arg(path);

    command
        .spawn()
        .map_err(|error| format!("Failed to open `{path}` in {editor}: {error}"))?;
    Ok(())
}

fn command_data_dir(app: &App) -> PathBuf {
    Path::new(&app.cwd).join(".poor-cli")
}

fn focus_state_path(app: &App) -> PathBuf {
    command_data_dir(app).join("focus.json")
}

fn repo_memory_path(app: &App) -> PathBuf {
    command_data_dir(app).join("memory.md")
}

fn load_repo_memory(app: &App) -> Result<Option<String>, String> {
    let path = repo_memory_path(app);
    if !path.exists() {
        return Ok(None);
    }
    let content = fs::read_to_string(&path)
        .map_err(|error| format!("Failed to read repo memory: {error}"))?;
    Ok(Some(content))
}

fn save_repo_memory(app: &App, content: &str) -> Result<PathBuf, String> {
    let root = command_data_dir(app);
    fs::create_dir_all(&root)
        .map_err(|error| format!("Failed to create data directory: {error}"))?;
    let path = repo_memory_path(app);
    fs::write(&path, content).map_err(|error| format!("Failed to write repo memory: {error}"))?;
    Ok(path)
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
    app.streaming.iteration_cap = iteration_cap;

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
    let _ = rpc_set_config_blocking(
        rpc_cmd_tx,
        "agentic.max_iterations",
        Value::Number(serde_json::Number::from(iteration_cap)),
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
        app.streaming.iteration_cap,
        notes
    ))
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

fn rpc_get_instruction_stack_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    referenced_files: &[String],
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetInstructionStack {
            referenced_files: referenced_files.to_vec(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request instruction stack: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for instruction stack".to_string())?
}

fn rpc_get_status_view_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetStatusView { reply: reply_tx })
        .map_err(|e| format!("Failed to request status view: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for status view".to_string())?
}

fn rpc_get_trust_view_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetTrustView { reply: reply_tx })
        .map_err(|e| format!("Failed to request trust view: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for trust view".to_string())?
}

fn rpc_get_doctor_report_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetDoctorReport { reply: reply_tx })
        .map_err(|e| format!("Failed to request doctor report: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for doctor report".to_string())?
}

fn rpc_get_policy_status_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetPolicyStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request policy status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for policy status".to_string())?
}

fn rpc_get_sandbox_status_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetSandboxStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request sandbox status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for sandbox status".to_string())?
}

fn rpc_get_mcp_status_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetMcpStatus { reply: reply_tx })
        .map_err(|e| format!("Failed to request MCP status: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for MCP status".to_string())?
}

fn rpc_gc_checkpoints_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GcCheckpoints { reply: reply_tx })
        .map_err(|e| format!("Failed to request GC: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for GC".to_string())?
}

fn rpc_mcp_health_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::McpHealthCheck { reply: reply_tx })
        .map_err(|e| format!("Failed to request MCP health: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for MCP health".to_string())?
}

fn rpc_get_economy_savings_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetEconomySavings { reply: reply_tx })
        .map_err(|e| format!("Failed to request economy savings: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for economy savings".to_string())?
}

fn rpc_set_economy_preset_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>, preset: &str) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetEconomyPreset { preset: preset.to_string(), reply: reply_tx })
        .map_err(|e| format!("Failed to set economy preset: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for economy preset".to_string())?
}

fn rpc_list_ollama_models_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListOllamaModels { reply: reply_tx })
        .map_err(|e| format!("Failed to request Ollama models: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for Ollama models".to_string())?
}

fn rpc_save_session_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SaveSession { reply: reply_tx })
        .map_err(|e| format!("Failed to save session: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out saving session".to_string())?
}

fn rpc_restore_session_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RestoreSession { reply: reply_tx })
        .map_err(|e| format!("Failed to restore session: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out restoring session".to_string())?
}

fn rpc_list_skills_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListSkills { reply: reply_tx })
        .map_err(|e| format!("Failed to request skills: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for skills".to_string())?
}

fn rpc_get_skill_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetSkill {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request skill: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for skill".to_string())?
}

fn rpc_list_custom_commands_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListCustomCommands { reply: reply_tx })
        .map_err(|e| format!("Failed to request custom commands: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for custom commands".to_string())?
}

fn rpc_get_custom_command_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetCustomCommand {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request custom command: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for custom command".to_string())?
}

fn rpc_run_custom_command_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
    args_text: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RunCustomCommand {
            name: name.to_string(),
            args_text: args_text.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to run custom command: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(120))
        .map_err(|_| "Timed out waiting for custom command".to_string())?
}

fn rpc_get_context_explain_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    message: &str,
    context_files: &[String],
    pinned_context_files: &[String],
    context_budget_tokens: Option<usize>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetContextExplain {
            message: message.to_string(),
            context_files: context_files.to_vec(),
            pinned_context_files: pinned_context_files.to_vec(),
            context_budget_tokens,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request context explanation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for context explanation".to_string())?
}

fn rpc_list_runs_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    source_kind: Option<&str>,
    source_id: Option<&str>,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListRuns {
            source_kind: source_kind.map(|value| value.to_string()),
            source_id: source_id.map(|value| value.to_string()),
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request runs: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for runs".to_string())?
}

fn rpc_list_workflows_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListWorkflows { reply: reply_tx })
        .map_err(|e| format!("Failed to request workflows: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for workflows".to_string())?
}

fn rpc_get_workflow_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    name: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetWorkflow {
            name: name.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request workflow: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for workflow".to_string())?
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

fn rpc_initialize_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    provider: Option<&str>,
    model: Option<&str>,
) -> Result<InitResult, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::Initialize {
            provider: provider.map(|value| value.to_string()),
            model: model.map(|value| value.to_string()),
            permission_mode: None,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request backend initialization: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for backend initialization".to_string())?
}

fn workspace_env_paths(app: &App) -> (PathBuf, PathBuf) {
    let root = if app.cwd.trim().is_empty() {
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
    } else {
        PathBuf::from(&app.cwd)
    };
    (root.join(".env"), root.join(".env.example"))
}

fn parse_env_line_key(line: &str) -> Option<String> {
    let mut trimmed = line.trim_start();
    if let Some(rest) = trimmed.strip_prefix('#') {
        trimmed = rest.trim_start();
    }
    if let Some(rest) = trimmed.strip_prefix("export ") {
        trimmed = rest.trim_start();
    }
    let (key, _) = trimmed.split_once('=')?;
    let key = key.trim();
    if key.is_empty()
        || !key.chars().enumerate().all(|(idx, ch)| {
            if idx == 0 {
                ch == '_' || ch.is_ascii_alphabetic()
            } else {
                ch == '_' || ch.is_ascii_alphanumeric()
            }
        })
    {
        return None;
    }
    Some(key.to_string())
}

fn parse_env_assignments(contents: &str) -> HashMap<String, String> {
    let mut values = HashMap::new();
    for line in contents.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let mut working = trimmed;
        if let Some(rest) = working.strip_prefix("export ") {
            working = rest.trim_start();
        }
        let Some((key, raw_value)) = working.split_once('=') else {
            continue;
        };
        let key = key.trim();
        if key.is_empty() {
            continue;
        }
        let mut value = raw_value.trim().to_string();
        if value.len() >= 2 {
            let quoted = (value.starts_with('"') && value.ends_with('"'))
                || (value.starts_with('\'') && value.ends_with('\''));
            if quoted {
                value = value[1..value.len() - 1].to_string();
            }
        }
        values.insert(key.to_string(), value);
    }
    values
}

fn format_env_value(value: &str) -> String {
    if value.is_empty() {
        return String::new();
    }
    if value
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.' | '/' | ':' | '+'))
    {
        return value.to_string();
    }
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

fn update_env_file_contents(base: &str, updates: &HashMap<String, String>) -> String {
    let mut seen = HashSet::new();
    let mut rendered = Vec::new();
    let managed_env_fields = managed_env_fields();
    for line in base.lines() {
        if let Some(key) = parse_env_line_key(line) {
            if let Some(value) = updates.get(&key) {
                rendered.push(format!("{key}={}", format_env_value(value)));
                seen.insert(key);
                continue;
            }
        }
        rendered.push(line.to_string());
    }

    for spec in &managed_env_fields {
        if seen.contains(spec.env_var) {
            continue;
        }
        if let Some(value) = updates.get(spec.env_var) {
            rendered.push(format!("{}={}", spec.env_var, format_env_value(value)));
        }
    }

    let mut output = rendered.join("\n");
    if !output.ends_with('\n') {
        output.push('\n');
    }
    output
}

fn build_api_key_editor_state(
    app: &App,
    init_error: Option<&str>,
) -> Result<ApiKeyEditorState, String> {
    let (env_path, template_path) = workspace_env_paths(app);
    let env_exists = env_path.exists();

    let env_values = if env_exists {
        let content = fs::read_to_string(&env_path)
            .map_err(|e| format!("Failed to read {}: {e}", env_path.display()))?;
        parse_env_assignments(&content)
    } else {
        HashMap::new()
    };

    let mut fields = Vec::new();
    let mut selected_index = 0usize;
    let managed_env_fields = managed_env_fields();
    for (idx, spec) in managed_env_fields.iter().enumerate() {
        let value = env_values
            .get(spec.env_var)
            .cloned()
            .or_else(|| std::env::var(spec.env_var).ok())
            .unwrap_or_default();
        if spec.provider == Some(app.provider.name.as_str()) {
            selected_index = idx;
        }
        fields.push(ApiKeyEditorField {
            label: spec.label.to_string(),
            provider: spec.provider.map(str::to_string),
            env_var: spec.env_var.to_string(),
            help: spec.help.to_string(),
            value,
        });
    }

    Ok(ApiKeyEditorState {
        env_path: env_path.display().to_string(),
        template_path: template_path.display().to_string(),
        env_exists,
        selected_index,
        cursor: fields
            .get(selected_index)
            .map(|field| field.value.len())
            .unwrap_or(0),
        fields,
        status: if env_exists {
            "Edit keys and press Ctrl+S to save.".to_string()
        } else {
            "No .env found. Saving will create one from .env.example.".to_string()
        },
        error: String::new(),
        init_error: init_error.unwrap_or("").to_string(),
        target_provider: app.provider.name.clone(),
        target_model: app.provider.model.clone(),
    })
}

fn open_api_key_setup_editor(app: &mut App, init_error: Option<&str>) -> Result<(), String> {
    let state = build_api_key_editor_state(app, init_error)?;
    app.open_api_key_editor(state);
    Ok(())
}

fn select_setup_provider_model(editor: &ApiKeyEditorState) -> (String, String) {
    let managed_env_fields = managed_env_fields();
    let active_has_key = managed_env_fields.iter().any(|spec| {
        spec.provider == Some(editor.target_provider.as_str())
            && editor
                .fields
                .iter()
                .find(|field| field.env_var == spec.env_var)
                .map(|field| !field.value.trim().is_empty())
                .unwrap_or(false)
    });

    if editor.target_provider.eq_ignore_ascii_case("ollama") || active_has_key {
        return (editor.target_provider.clone(), editor.target_model.clone());
    }

    for spec in &managed_env_fields {
        let Some(provider) = spec.provider else {
            continue;
        };
        let has_value = editor
            .fields
            .iter()
            .find(|field| field.env_var == spec.env_var)
            .map(|field| !field.value.trim().is_empty())
            .unwrap_or(false);
        if has_value {
            return (provider.to_string(), spec.default_model.to_string());
        }
    }

    (editor.target_provider.clone(), editor.target_model.clone())
}

fn save_api_key_editor(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
) -> Result<String, String> {
    let editor = app
        .api_key_editor
        .clone()
        .ok_or_else(|| "Setup editor is not open.".to_string())?;
    let env_path = PathBuf::from(&editor.env_path);
    let template_path = PathBuf::from(&editor.template_path);

    let base = if env_path.exists() {
        fs::read_to_string(&env_path)
            .map_err(|e| format!("Failed to read {}: {e}", env_path.display()))?
    } else if template_path.exists() {
        fs::read_to_string(&template_path)
            .map_err(|e| format!("Failed to read {}: {e}", template_path.display()))?
    } else {
        "# Generated by poor-cli /setup\n".to_string()
    };

    let mut updates = HashMap::new();
    for field in &editor.fields {
        updates.insert(field.env_var.clone(), field.value.trim().to_string());
    }

    let rendered = update_env_file_contents(&base, &updates);
    if let Some(parent) = env_path.parent() {
        fs::create_dir_all(parent)
            .map_err(|e| format!("Failed to prepare {}: {e}", parent.display()))?;
    }
    fs::write(&env_path, rendered)
        .map_err(|e| format!("Failed to write {}: {e}", env_path.display()))?;

    for field in &editor.fields {
        let value = field.value.trim();
        if value.is_empty() {
            std::env::remove_var(&field.env_var);
        } else {
            std::env::set_var(&field.env_var, value);
        }
    }

    for field in &editor.fields {
        if let Some(provider) = field.provider.as_deref() {
            let value = field.value.trim();
            if value.is_empty() {
                continue;
            }
            rpc_set_api_key_blocking(rpc_cmd_tx, provider, value, true).map_err(|e| {
                format!(
                    "Saved .env but failed to store `{}` in backend: {e}",
                    field.env_var
                )
            })?;
        }
    }

    let (provider, model) = select_setup_provider_model(&editor);
    let init = rpc_initialize_blocking(rpc_cmd_tx, Some(&provider), Some(&model))
        .map_err(|e| format!("Saved .env but backend initialization still failed: {e}"))?;
    tx.send(server_msg_from_init_result(
        init,
        &Some(provider.clone()),
        &Some(model.clone()),
    ))
    .map_err(|e| format!("Saved .env but failed to apply initialization result: {e}"))?;

    Ok(format!(
        "Saved {} and retried backend initialization.",
        env_path.display()
    ))
}

fn should_offer_api_key_setup(message: &str) -> bool {
    let lowered = message.to_ascii_lowercase();
    lowered.contains("api key")
        || lowered.contains("set environment variable")
        || lowered.contains("no api key found")
        || lowered.contains("initialization failed")
        || lowered.contains("auth")
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

fn rpc_create_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    title: &str,
    prompt: &str,
    sandbox_preset: &str,
    source: &str,
    auto_start: bool,
    requires_approval: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CreateTask {
            title: title.to_string(),
            prompt: prompt.to_string(),
            sandbox_preset: sandbox_preset.to_string(),
            source: source.to_string(),
            auto_start,
            requires_approval,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to create task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task creation".to_string())?
}

fn rpc_list_tasks_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    inbox_only: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListTasks {
            inbox_only,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to list tasks: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task list".to_string())?
}

fn rpc_get_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to get task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task".to_string())?
}

fn rpc_approve_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ApproveTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to approve task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task approval".to_string())?
}

fn rpc_cancel_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::CancelTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to cancel task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task cancel".to_string())?
}

fn rpc_retry_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::RetryTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to retry task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task retry".to_string())?
}

fn rpc_replay_task_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    task_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ReplayTask {
            task_id: task_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to replay task: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for task replay".to_string())?
}


fn rpc_get_automation_history_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    automation_id: &str,
    limit: u64,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetAutomationHistory {
            automation_id: automation_id.to_string(),
            limit,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request automation history: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for automation history".to_string())?
}

fn rpc_replay_automation_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    automation_id: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ReplayAutomation {
            automation_id: automation_id.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to replay automation: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for automation replay".to_string())?
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

fn rpc_get_collab_summary_blocking(rpc_cmd_tx: &mpsc::Sender<RpcCommand>) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::GetCollabSummary { reply: reply_tx })
        .map_err(|e| format!("Failed to request collaboration summary: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for collaboration summary".to_string())?
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

fn rpc_list_room_members_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListRoomMembers {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request room members: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for room members response".to_string())?
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

fn rpc_kick_member_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    connection_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::KickMember {
            connection_id: connection_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request member kick: {e}"))?;

    reply_rx
        .recv_timeout(Duration::from_secs(45))
        .map_err(|_| "Timed out waiting for member kick response".to_string())?
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

fn rpc_pair_start_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    lobby: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::PairStart {
            lobby,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request pair start: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(30))
        .map_err(|_| "Timed out waiting for pair start response".to_string())?
}

fn rpc_suggest_text_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    text: &str,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SuggestText {
            text: text.to_string(),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to send suggestion: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for suggest response".to_string())?
}

fn rpc_add_agenda_item_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    text: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::AddAgendaItem {
            text: text.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to add agenda item: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for agenda add response".to_string())?
}

fn rpc_list_agenda_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
    include_resolved: bool,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ListAgenda {
            room: room.map(|value| value.to_string()),
            include_resolved,
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to list agenda: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for agenda list response".to_string())?
}

fn rpc_resolve_agenda_item_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    item_id: &str,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::ResolveAgendaItem {
            item_id: item_id.to_string(),
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to resolve agenda item: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for agenda resolve response".to_string())?
}

fn rpc_set_hand_raised_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    raised: bool,
    room: Option<&str>,
    connection_id: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::SetHandRaised {
            raised,
            room: room.map(|value| value.to_string()),
            connection_id: connection_id.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to update hand raise state: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(10))
        .map_err(|_| "Timed out waiting for hand raise response".to_string())?
}

fn rpc_next_driver_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::NextDriver {
            room: room.map(|value| value.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request next driver: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(15))
        .map_err(|_| "Timed out waiting for next driver response".to_string())?
}

fn rpc_pass_driver_blocking(
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    display_name: Option<&str>,
    connection_id: Option<&str>,
    room: Option<&str>,
) -> Result<Value, String> {
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    rpc_cmd_tx
        .send(RpcCommand::PassDriver {
            display_name: display_name.map(|s| s.to_string()),
            connection_id: connection_id.map(|s| s.to_string()),
            room: room.map(|s| s.to_string()),
            reply: reply_tx,
        })
        .map_err(|e| format!("Failed to request pass driver: {e}"))?;
    reply_rx
        .recv_timeout(Duration::from_secs(15))
        .map_err(|_| "Timed out waiting for pass driver response".to_string())?
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
        let args =
            multiplayer::build_backend_server_args(&cli).expect("local mode args should build");
        assert!(args.is_empty());
    }

    #[test]
    fn backend_server_args_for_remote_mode() {
        let cli = Cli::parse_from(["poor-cli-tui", "--remote-invite", "invite-code"]);
        let args = multiplayer::build_backend_server_args(&cli).expect("remote args should build");
        assert_eq!(
            args,
            vec![
                "--bridge".to_string(),
                "--invite".to_string(),
                "invite-code".to_string(),
            ]
        );
    }

    #[test]
    fn backend_server_args_support_remote_invite() {
        let cli = Cli::parse_from(["poor-cli-tui", "--remote-invite", "invite-code"]);
        let args =
            multiplayer::build_backend_server_args(&cli).expect("remote invite args should build");
        assert_eq!(
            args,
            vec![
                "--bridge".to_string(),
                "--invite".to_string(),
                "invite-code".to_string(),
            ]
        );
    }

    #[test]
    fn join_server_parser_accepts_signed_invite_code() {
        let parsed = multiplayer::parse_join_server_args(
            "/join-server eyJwYXlsb2FkIjp7InYiOjEsImtpbmQiOiJwb29yLWNsaS1wMnAiLCJzaWduYWxpbmdVcmwiOiJodHRwczovL2hvc3QudGVzdC9ycGMiLCJzZXNzaW9uSWQiOiJkb2NzIiwidG9rZW4iOiJ0b2steHl6Iiwicm9sZSI6InZpZXdlciJ9LCJzaWciOiJzaWcifQ",
        )
        .expect("signed invite should parse");
        assert_eq!(
            parsed,
            multiplayer::RemoteBootstrap {
                invite: "eyJwYXlsb2FkIjp7InYiOjEsImtpbmQiOiJwb29yLWNsaS1wMnAiLCJzaWduYWxpbmdVcmwiOiJodHRwczovL2hvc3QudGVzdC9ycGMiLCJzZXNzaW9uSWQiOiJkb2NzIiwidG9rZW4iOiJ0b2steHl6Iiwicm9sZSI6InZpZXdlciJ9LCJzaWciOiJzaWcifQ".to_string(),
                signaling_url: "https://host.test/rpc".to_string(),
                room: "docs".to_string(),
                token: "tok-xyz".to_string(),
            }
        );
    }

    #[test]
    fn join_server_parser_rejects_legacy_triplet() {
        let err =
            multiplayer::parse_join_server_args("/join-server wss://host.test/rpc docs tok-xyz")
                .expect_err("legacy triplet should fail");
        assert!(err.contains("Usage"));
    }

    #[test]
    fn join_server_parser_rejects_invalid_usage() {
        let err = multiplayer::parse_join_server_args("/join-server checkpoint")
            .expect_err("single non-code arg should fail");
        assert!(err.contains("Usage"));
    }

    #[test]
    fn remote_reconnect_classifier_accepts_signaling_and_datachannel_errors() {
        assert!(multiplayer::should_attempt_remote_reconnect(
            "Signaling request failed (500): owner unavailable"
        ));
        assert!(multiplayer::should_attempt_remote_reconnect(
            "data channel is not open"
        ));
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
    fn update_env_file_contents_rewrites_template_and_preserves_other_entries() {
        let base = "\
# example\n\
GEMINI_API_KEY=old-gemini\n\
# OPENAI_API_KEY=your-openai-key-here\n\
CUSTOM_FLAG=yes\n";
        let updates = HashMap::from([
            ("GEMINI_API_KEY".to_string(), "new-gemini".to_string()),
            ("OPENAI_API_KEY".to_string(), "sk-openai".to_string()),
        ]);

        let rendered = update_env_file_contents(base, &updates);

        assert!(rendered.contains("GEMINI_API_KEY=new-gemini"));
        assert!(rendered.contains("OPENAI_API_KEY=sk-openai"));
        assert!(rendered.contains("CUSTOM_FLAG=yes"));
    }

    #[test]
    fn select_setup_provider_model_falls_back_to_first_configured_provider() {
        let editor = ApiKeyEditorState {
            target_provider: "gemini".to_string(),
            target_model: provider_catalog::default_model("gemini").to_string(),
            fields: vec![
                ApiKeyEditorField {
                    label: "Gemini".to_string(),
                    provider: Some("gemini".to_string()),
                    env_var: "GEMINI_API_KEY".to_string(),
                    help: String::new(),
                    value: String::new(),
                },
                ApiKeyEditorField {
                    label: "OpenAI".to_string(),
                    provider: Some("openai".to_string()),
                    env_var: "OPENAI_API_KEY".to_string(),
                    help: String::new(),
                    value: "sk-openai".to_string(),
                },
            ],
            ..ApiKeyEditorState::default()
        };

        let (provider, model) = select_setup_provider_model(&editor);

        assert_eq!(provider, "openai");
        assert_eq!(model, provider_catalog::default_model("openai"));
    }

    #[test]
    fn startup_selection_prefers_configured_ready_provider() {
        let selection = resolve_startup_selection(
            None,
            None,
            Some(&StartupState {
                provider: "openai".to_string(),
                model: "gpt-5.1".to_string(),
            }),
            &[
                ProviderInfo {
                    name: "openai".to_string(),
                    available: true,
                    ready: true,
                    status_label: "API key configured".to_string(),
                    models: vec!["gpt-5.1".to_string()],
                },
                ProviderInfo {
                    name: "anthropic".to_string(),
                    available: true,
                    ready: true,
                    status_label: "API key configured".to_string(),
                    models: vec!["claude-sonnet-4-20250514".to_string()],
                },
            ],
        );

        assert_eq!(selection.provider.as_deref(), Some("openai"));
        assert_eq!(selection.model.as_deref(), Some("gpt-5.1"));
    }

    #[test]
    fn startup_selection_ignores_empty_configured_model() {
        let selection = resolve_startup_selection(
            None,
            Some("   ".to_string()),
            Some(&StartupState {
                provider: "openai".to_string(),
                model: String::new(),
            }),
            &[ProviderInfo {
                name: "openai".to_string(),
                available: true,
                ready: true,
                status_label: "API key configured".to_string(),
                models: vec!["gpt-5.1".to_string()],
            }],
        );

        assert_eq!(selection.provider.as_deref(), Some("openai"));
        assert_eq!(selection.model.as_deref(), Some("gpt-5.1"));
    }

    #[test]
    fn startup_selection_falls_back_to_first_ready_provider_when_default_is_unready() {
        let selection = resolve_startup_selection(
            None,
            None,
            Some(&StartupState {
                provider: "gemini".to_string(),
                model: "gemini-2.5-flash".to_string(),
            }),
            &[
                ProviderInfo {
                    name: "gemini".to_string(),
                    available: true,
                    ready: false,
                    status_label: "missing GEMINI_API_KEY".to_string(),
                    models: vec!["gemini-2.5-flash".to_string()],
                },
                ProviderInfo {
                    name: "openai".to_string(),
                    available: true,
                    ready: true,
                    status_label: "API key configured".to_string(),
                    models: vec!["gpt-5.1".to_string()],
                },
            ],
        );

        assert_eq!(selection.provider.as_deref(), Some("openai"));
        assert_eq!(selection.model.as_deref(), Some("gpt-5.1"));
    }

    #[test]
    fn startup_selection_leaves_provider_unset_when_nothing_is_ready() {
        let selection = resolve_startup_selection(
            None,
            None,
            Some(&StartupState {
                provider: "gemini".to_string(),
                model: "gemini-2.5-flash".to_string(),
            }),
            &[ProviderInfo {
                name: "gemini".to_string(),
                available: true,
                ready: false,
                status_label: "missing GEMINI_API_KEY".to_string(),
                models: vec!["gemini-2.5-flash".to_string()],
            }],
        );

        assert!(selection.provider.is_none());
    }

    #[test]
    fn build_api_key_editor_state_loads_existing_env_values() {
        let root = create_temp_workspace("api-key-editor");
        fs::write(
            root.join(".env"),
            "GEMINI_API_KEY=gm-live\nOPENAI_API_KEY=sk-live\n",
        )
        .expect(".env should be written");
        fs::write(root.join(".env.example"), "# template\n").expect("template should be written");

        let mut app = build_app_for_root(&root);
        app.provider.name = "openai".to_string();
        app.provider.model = provider_catalog::default_model("openai").to_string();

        let state = build_api_key_editor_state(&app, Some("Initialization failed"))
            .expect("editor state should build");

        assert!(state.env_exists);
        assert_eq!(state.init_error, "Initialization failed");
        assert_eq!(
            state
                .fields
                .iter()
                .find(|field| field.env_var == "GEMINI_API_KEY")
                .map(|field| field.value.as_str()),
            Some("gm-live")
        );
        assert_eq!(
            state
                .fields
                .iter()
                .find(|field| field.env_var == "OPENAI_API_KEY")
                .map(|field| field.value.as_str()),
            Some("sk-live")
        );
        assert_eq!(state.selected_index, 1);
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
    fn prepare_context_request_blocks_on_unresolved_or_ambiguous_refs() {
        let root = create_temp_workspace("refs-error");
        fs::create_dir_all(root.join("src")).expect("src dir");
        fs::create_dir_all(root.join("tests")).expect("tests dir");
        fs::write(root.join("src").join("main.rs"), "fn main() {}\n").expect("main src");
        fs::write(root.join("tests").join("main.rs"), "#[test]\nfn ok() {}\n").expect("main tests");

        let mut app = build_app_for_root(&root);
        let ambiguous = prepare_context_request(&mut app, "review @main.rs");
        assert!(ambiguous.is_err());

        let unresolved = prepare_context_request(&mut app, "review @missing.rs");
        assert!(unresolved.is_err());

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn prepare_context_request_resolves_absolute_paths_without_prompt_stuffing() {
        let root = create_temp_workspace("refs-spaces");
        fs::create_dir_all(root.join("docs")).expect("docs dir");
        fs::write(root.join("docs").join("My File.md"), "# Title\n").expect("docs file");

        let mut app = build_app_for_root(&root);
        let request = prepare_context_request(&mut app, r#"summarize @"docs/My File.md""#)
            .expect("quoted path should resolve");
        assert_eq!(request.message, r#"summarize @"docs/My File.md""#);
        assert_eq!(request.explicit_files.len(), 1);
        assert!(Path::new(&request.explicit_files[0]).is_absolute());
        assert!(request.explicit_files[0].ends_with("docs/My File.md"));
        assert!(request.pinned_files.is_empty());

        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn prepare_context_request_includes_pinned_files_as_backend_paths() {
        let root = create_temp_workspace("refs-pinned");
        fs::create_dir_all(root.join("src")).expect("src dir");
        fs::write(
            root.join("src").join("lib.rs"),
            "pub fn answer() -> u32 { 42 }\n",
        )
        .expect("lib file");

        let mut app = build_app_for_root(&root);
        app.pinned_context_files.push("src/lib.rs".to_string());

        let request = prepare_context_request(&mut app, "review this change")
            .expect("pinned files should resolve");
        assert!(request.explicit_files.is_empty());
        assert_eq!(request.pinned_files.len(), 1);
        assert!(Path::new(&request.pinned_files[0]).is_absolute());
        assert!(request.pinned_files[0].ends_with("src/lib.rs"));

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
        assert_eq!(
            watcher::default_qa_command_for_workspace(&root),
            "pytest -q"
        );
        let _ = fs::remove_dir_all(root);
    }
}
