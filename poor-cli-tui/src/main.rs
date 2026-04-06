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
mod payloads;
mod env_editor;
mod rpc_wrappers;
mod submit;
mod workspace;
pub(crate) use payloads::*;
pub(crate) use env_editor::*;

#[allow(unused_imports)]
pub(crate) use workspace::*;

#[allow(unused_imports)]
pub(crate) use rpc_wrappers::*;

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
    #[arg(
        long,
        value_parser = [
            "default",
            "acceptEdits",
            "plan",
            "bypassPermissions",
            "dontAsk",
            "prompt",
            "auto-safe",
            "danger-full-access",
        ]
    )]
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
        Some("bypassPermissions".to_string())
    } else {
        cli.permission_mode.clone()
    };
    app.permission_mode_label = permission_mode
        .clone()
        .unwrap_or_else(|| "default".to_string());
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

fn format_relative_time(iso_str: &str) -> String {
    // parse "YYYY-MM-DDTHH:MM:SS" prefix from ISO 8601 timestamp
    fn parse_epoch(s: &str) -> Option<i64> {
        let s = s.trim();
        if s.len() < 19 { return None; }
        let year: i64 = s[..4].parse().ok()?;
        let month: i64 = s[5..7].parse().ok()?;
        let day: i64 = s[8..10].parse().ok()?;
        let hour: i64 = s[11..13].parse().ok()?;
        let min: i64 = s[14..16].parse().ok()?;
        let sec: i64 = s[17..19].parse().ok()?;
        // rough epoch (ignores leap seconds, good enough for relative display)
        let days = (year - 1970) * 365 + (year - 1969) / 4 - (year - 1901) / 100 + (year - 1601) / 400;
        let month_days: [i64; 12] = [0,31,59,90,120,151,181,212,243,273,304,334];
        let leap = if month > 2 && (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)) { 1 } else { 0 };
        let total_days = days + month_days[(month - 1) as usize] + day - 1 + leap;
        Some(total_days * 86400 + hour * 3600 + min * 60 + sec)
    }
    let Some(then) = parse_epoch(iso_str) else { return iso_str.to_string() };
    let now = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let secs = (now - then).max(0) as u64;
    match secs {
        0..=59 => "just now".to_string(),
        60..=3599 => format!("{}m ago", secs / 60),
        3600..=86399 => format!("{}h ago", secs / 3600),
        _ => format!("{}d ago", secs / 86400),
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
