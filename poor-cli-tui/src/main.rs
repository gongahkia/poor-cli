/// Entry point for the poor-cli Rust TUI.
use std::io;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{mpsc, Arc};
use std::thread;
use std::time::Duration;

use clap::Parser;
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::prelude::*;

use poor_cli_tui::app::{App, AppMode, ChatMessage, ProviderEntry};
use poor_cli_tui::input::{self, InputAction};
use poor_cli_tui::rpc::{run_rpc_worker, RpcClient, RpcCommand};
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

enum ServerMsg {
    Initialized { provider: String, model: String, version: String },
    ChatResponse { content: String },
    SystemMessage { content: String },
    Providers { providers: Vec<ProviderEntry> },
    ProviderSwitched { provider: String, model: String },
    Error { message: String },
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
    if let Err(err) = result {
        eprintln!("Error: {err}");
        std::process::exit(1);
    }
    Ok(())
}

fn run_app(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    cli: Cli,
) -> Result<(), Box<dyn std::error::Error>> {
    let mut app = App::new();
    app.cwd = std::env::current_dir()
        .ok()
        .and_then(|p| p.to_str().map(|s| s.to_string()))
        .unwrap_or_else(|| ".".into());

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
    thread::spawn(move || {
        match RpcClient::spawn(&python_bin, cwd.as_deref()) {
            Ok(client) => {
                match client.initialize(
                    provider.as_deref(),
                    model.as_deref(),
                    None,
                    permission_mode.as_deref(),
                ) {
                    Ok(init) => {
                        let (prov, mdl) = if let Some(caps) = &init.capabilities {
                            let prov = caps.pointer("/providerInfo/name")
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string())
                                .unwrap_or_else(|| provider.clone().unwrap_or_else(|| "gemini".into()));
                            let mdl = caps.pointer("/providerInfo/model")
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string())
                                .unwrap_or_else(|| model.clone().unwrap_or_else(|| "gemini-2.0-flash-exp".into()));
                            (prov, mdl)
                        } else {
                            (
                                provider.clone().unwrap_or_else(|| "gemini".into()),
                                model.clone().unwrap_or_else(|| "gemini-2.0-flash-exp".into()),
                            )
                        };
                        let _ = tx_init.send(ServerMsg::Initialized {
                            provider: prov,
                            model: mdl,
                            version: init.version.unwrap_or_else(|| "0.4.0".into()),
                        });
                        // init thread becomes the RPC worker (blocks here)
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
        }
    });

    app.provider_name = cli.provider.unwrap_or_else(|| "gemini".into());
    app.model_name = cli.model.unwrap_or_else(|| "gemini-2.0-flash-exp".into());
    app.add_welcome();

    // Shared cancel flag; set to true to discard the next in-flight reply.
    let cancel_token: Arc<AtomicBool> = Arc::new(AtomicBool::new(false));

    loop {
        terminal.draw(|f| ui::draw(f, &app))?;

        while let Ok(msg) = rx.try_recv() {
            match msg {
                ServerMsg::Initialized { provider, model, version } => {
                    app.provider_name = provider;
                    app.model_name = model;
                    app.version = version;
                    app.server_connected = true;
                    app.is_local_provider = app.provider_name == "ollama";
                    app.update_welcome();
                    app.set_status("Connected to Python backend");
                }
                ServerMsg::ChatResponse { content } => {
                    app.stop_waiting();
                    app.push_message(ChatMessage::assistant(content));
                }
                ServerMsg::SystemMessage { content } => {
                    app.push_message(ChatMessage::system(content));
                }
                ServerMsg::Providers { providers } => {
                    app.providers = providers;
                    app.provider_select_idx = 0;
                    app.mode = AppMode::ProviderSelect;
                }
                ServerMsg::ProviderSwitched { provider, model } => {
                    app.provider_name = provider;
                    app.model_name = model;
                    app.is_local_provider = app.provider_name == "ollama";
                    app.set_status("Provider switched successfully");
                }
                ServerMsg::Error { message } => {
                    app.stop_waiting();
                    app.push_message(ChatMessage::error(message));
                }
            }
        }

        app.clear_old_status();
        app.tick_spinner();

        if event::poll(Duration::from_millis(100))? {
            let ev = event::read()?;
            match input::handle_event(&mut app, ev) {
                InputAction::Submit(text) => {
                    handle_submit(&mut app, &tx, &rpc_cmd_tx, &cancel_token, &text);
                }
                InputAction::Cancel => {
                    cancel_token.store(true, Ordering::SeqCst);
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
                InputAction::PermissionAnswered(_allowed) => {}
                InputAction::Redraw => {}
                InputAction::None => {}
            }
        }
    }

    Ok(())
}

// ── Submit handler ───────────────────────────────────────────────────

fn handle_submit(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cancel_token: &Arc<AtomicBool>,
    text: &str,
) {
    let trimmed = text.trim();
    if trimmed.starts_with('/') {
        handle_slash_command(app, tx, rpc_cmd_tx, trimmed);
        return;
    }
    // Reset cancel flag before each new request.
    cancel_token.store(false, Ordering::SeqCst);
    app.push_message(ChatMessage::user(trimmed));
    app.start_waiting();
    let tx2 = tx.clone();
    let message = trimmed.to_string();
    let cancel = cancel_token.clone();
    let (reply_tx, reply_rx) = mpsc::sync_channel(1);
    let _ = rpc_cmd_tx.send(RpcCommand::Chat { message, reply: reply_tx });
    thread::spawn(move || {
        match reply_rx.recv() {
            Ok(Ok(content)) => {
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::ChatResponse { content });
                }
            }
            Ok(Err(e)) => {
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error { message: e });
                }
            }
            Err(_) => {
                if !cancel.load(Ordering::SeqCst) {
                    let _ = tx2.send(ServerMsg::Error { message: "RPC worker gone".into() });
                }
            }
        }
    });
}

// ── Slash command handler ─────────────────────────────────────────────

fn handle_slash_command(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mpsc::Sender<RpcCommand>,
    cmd: &str,
) {
    match cmd {
        "/quit" | "/exit" => {
            app.mode = AppMode::Quitting;
        }
        "/help" => {
            let help = "\
**Available Commands:**\n\n\
**Session Management:**\n\
  /help          Show this help message\n\
  /quit          Exit the REPL\n\
  /clear         Clear current conversation\n\
  /history [N]   Show recent messages\n\
  /sessions      List all previous sessions\n\
  /new-session   Start fresh conversation\n\
  /retry         Retry last request\n\n\
**Checkpoints & Undo:**\n\
  /checkpoints   List all checkpoints\n\
  /checkpoint    Create manual checkpoint\n\
  /rewind [ID]   Restore checkpoint\n\
  /undo          Quick restore last checkpoint\n\n\
**Provider Management:**\n\
  /provider      Show current provider info\n\
  /providers     List all available providers\n\
  /switch        Switch AI provider\n\n\
**Configuration:**\n\
  /config        Show current configuration\n\
  /verbose       Toggle verbose logging\n\
  /plan-mode     Toggle plan mode\n\
  /cost          Show API usage estimates";
            app.push_message(ChatMessage::system(help));
        }
        "/clear" => {
            app.messages.clear();
            app.set_status("Conversation cleared");
        }
        "/provider" => {
            let info = format!(
                "**Current Provider:** {}\n**Model:** {}\n**Streaming:** {}",
                app.provider_name,
                app.model_name,
                if app.streaming_enabled { "✓ Enabled" } else { "✗ Disabled" }
            );
            app.push_message(ChatMessage::system(info));
        }
        "/providers" => {
            let (reply_tx, reply_rx) = mpsc::sync_channel(1);
            let _ = rpc_cmd_tx.send(RpcCommand::ListProviders { reply: reply_tx });
            let tx2 = tx.clone();
            thread::spawn(move || {
                match reply_rx.recv() {
                    Ok(Ok(providers)) => {
                        let mut info = "**Available Providers:**\n\n".to_string();
                        for p in &providers {
                            let status = if p.available { "✓" } else { "✗" };
                            let local = if p.name == "ollama" { " [local]" } else { "" };
                            info.push_str(&format!("  {status} **{}**{local}\n", p.name));
                        }
                        info.push_str("\n*Use /switch to change providers*");
                        let _ = tx2.send(ServerMsg::SystemMessage { content: info });
                    }
                    _ => {
                        let _ = tx2.send(ServerMsg::Error {
                            message: "Failed to list providers".into(),
                        });
                    }
                }
            });
        }
        "/switch" => {
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
        }
        "/config" => {
            let config = format!(
                "**Configuration:**\n\nProvider: {}\nModel: {}\nStreaming: {}\nVersion: v{}",
                app.provider_name,
                app.model_name,
                if app.streaming_enabled { "enabled" } else { "disabled" },
                app.version,
            );
            app.push_message(ChatMessage::system(config));
        }
        "/model-info" => {
            let info = match app.provider_name.as_str() {
                "gemini" => "**Gemini Models:**\n  • Free tier available\n  • Fast inference\n  • Good at code generation\n  • Strong multilingual support",
                "openai" => "**OpenAI Models:**\n  • GPT-4: Most capable, slower, higher cost\n  • GPT-3.5: Fast, cost-effective\n  • Strong reasoning and instruction following",
                "anthropic" => "**Anthropic Models:**\n  • Claude 3.5 Sonnet: Balanced capability\n  • Strong at analysis and code review\n  • Large context windows (200k tokens)",
                "ollama" => "**Ollama (Local):**\n  • Runs entirely on your machine\n  • No API costs\n  • Privacy-focused (no data sent externally)\n  • Speed depends on hardware",
                _ => "No detailed info available for this provider.",
            };
            app.push_message(ChatMessage::system(info.to_string()));
        }
        _ => {
            app.push_message(ChatMessage::error(format!(
                "Unknown command: {cmd}\nType /help to see available commands"
            )));
        }
    }
}
