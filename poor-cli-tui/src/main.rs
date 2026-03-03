/// Entry point for the poor-cli Rust TUI.
///
/// Spawns the Python JSON-RPC server, initializes the TUI, and runs the main
/// event loop. Closely mirrors the UX of Claude Code and Codex.
use std::io;
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use clap::Parser;
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::prelude::*;

use poor_cli_tui::app::{App, AppMode, ChatMessage, ProviderEntry};
use poor_cli_tui::input::{self, InputAction};
use poor_cli_tui::rpc::RpcClient;
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
    Initialized {
        provider: String,
        model: String,
        version: String,
    },
    ChatResponse {
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
}

// ── Main ─────────────────────────────────────────────────────────────

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let cli = Cli::parse();

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let result = run_app(&mut terminal, cli);

    // Restore terminal
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

    // Channel for server communication
    let (tx, rx) = mpsc::channel::<ServerMsg>();

    // Spawn Python server in background
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
                // Initialize
                match client.initialize(
                    provider.as_deref(),
                    model.as_deref(),
                    None,
                    permission_mode.as_deref(),
                ) {
                    Ok(init) => {
                        let _ = tx_init.send(ServerMsg::Initialized {
                            provider: provider.unwrap_or_else(|| "gemini".into()),
                            model: model.unwrap_or_else(|| "gemini-2.0-flash-exp".into()),
                            version: init.version.unwrap_or_else(|| "0.4.0".into()),
                        });
                    }
                    Err(e) => {
                        let _ = tx_init.send(ServerMsg::Error {
                            message: format!("Initialization failed: {e}"),
                        });
                    }
                }

                // Keep client alive — in a real impl we'd store it for later use.
                // For now, just park the thread until the app exits.
                // The client handle can be stashed in a global or passed via Arc.
                // Simplified: just keep the connection alive.
                loop {
                    thread::sleep(Duration::from_secs(60));
                }
            }
            Err(e) => {
                let _ = tx_init.send(ServerMsg::Error {
                    message: format!("Failed to start server: {e}"),
                });
            }
        }
    });

    // Show initial state
    app.provider_name = cli.provider.unwrap_or_else(|| "gemini".into());
    app.model_name = cli.model.unwrap_or_else(|| "gemini-2.0-flash-exp".into());
    app.add_welcome();

    // Main event loop
    loop {
        // Draw
        terminal.draw(|f| ui::draw(f, &app))?;

        // Check for server messages (non-blocking)
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
                    app.set_status("Connected to Python backend");
                }
                ServerMsg::ChatResponse { content } => {
                    app.stop_waiting();
                    app.push_message(ChatMessage::assistant(content));
                }
                ServerMsg::Providers { providers } => {
                    app.providers = providers;
                    app.provider_select_idx = 0;
                    app.mode = AppMode::ProviderSelect;
                }
                ServerMsg::ProviderSwitched { provider, model } => {
                    app.provider_name = provider;
                    app.model_name = model;
                    app.set_status("Provider switched successfully");
                }
                ServerMsg::Error { message } => {
                    app.stop_waiting();
                    app.push_message(ChatMessage::error(message));
                }
            }
        }

        // Clear old status messages
        app.clear_old_status();

        // Tick spinner
        app.tick_spinner();

        // Poll for events with a short timeout (for spinner animation)
        if event::poll(Duration::from_millis(100))? {
            let ev = event::read()?;
            match input::handle_event(&mut app, ev) {
                InputAction::Submit(text) => {
                    handle_submit(&mut app, &tx, &text);
                }
                InputAction::Quit => {
                    break;
                }
                InputAction::ProviderSelected(idx) => {
                    if let Some(provider) = app.providers.get(idx) {
                        let name = provider.name.clone();
                        app.set_status(format!("Switching to {name}..."));
                        let tx2 = tx.clone();
                        thread::spawn(move || {
                            // In a full impl, we'd call the RPC client here.
                            // For now, just send a success message.
                            let _ = tx2.send(ServerMsg::ProviderSwitched {
                                provider: name.clone(),
                                model: "default".into(),
                            });
                        });
                    }
                }
                InputAction::PermissionAnswered(_allowed) => {
                    // Would forward to the pending tool execution
                }
                InputAction::Redraw => {}
                InputAction::None => {}
            }
        }
    }

    Ok(())
}

/// Handle user input submission (chat message or slash command).
fn handle_submit(app: &mut App, tx: &mpsc::Sender<ServerMsg>, text: &str) {
    let trimmed = text.trim();

    // Handle slash commands locally
    if trimmed.starts_with('/') {
        handle_slash_command(app, tx, trimmed);
        return;
    }

    // Regular chat message
    app.push_message(ChatMessage::user(trimmed));
    app.start_waiting();

    // In a full implementation, we'd send this to the RPC client in a background thread.
    // For now, we show a mock response to demonstrate the UI.
    let tx2 = tx.clone();
    let message = trimmed.to_string();
    thread::spawn(move || {
        // Simulate some thinking time
        thread::sleep(Duration::from_millis(800));
        let _ = tx2.send(ServerMsg::ChatResponse {
            content: format!(
                "I received your message: *\"{message}\"*\n\n\
                 **Note:** The Rust TUI is connected but full RPC chat integration is pending.\n\n\
                 To complete the integration, the Python server needs the `chat` method wired up \
                 with streaming support.\n\n\
                 ```rust\n\
                 // The RPC client in rpc.rs has the chat() method ready:\n\
                 // client.chat(\"{message}\", &[])\n\
                 ```"
            ),
        });
    });
}

/// Handle slash commands.
fn handle_slash_command(app: &mut App, tx: &mpsc::Sender<ServerMsg>, cmd: &str) {
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
            // Show built-in provider list
            let providers_info = "\
**Available Providers:**\n\n\
  ✓ **gemini** — Google Gemini (free tier available)\n\
  ✓ **openai** — OpenAI GPT-4 / GPT-3.5\n\
  ✓ **anthropic** — Anthropic Claude\n\
  ✓ **ollama** — Local models [local] (Llama 3, CodeLlama, Mistral, etc.)\n\n\
*Use /switch to change providers*";
            app.push_message(ChatMessage::system(providers_info));
        }
        "/switch" => {
            // Populate providers list and switch to select mode
            app.providers = vec![
                ProviderEntry {
                    name: "gemini".into(),
                    available: true,
                    models: vec!["gemini-2.0-flash-exp".into(), "gemini-1.5-pro".into()],
                },
                ProviderEntry {
                    name: "openai".into(),
                    available: true,
                    models: vec!["gpt-4o".into(), "gpt-4-turbo".into(), "gpt-3.5-turbo".into()],
                },
                ProviderEntry {
                    name: "anthropic".into(),
                    available: true,
                    models: vec!["claude-sonnet-4-20250514".into(), "claude-3-haiku".into()],
                },
                ProviderEntry {
                    name: "ollama".into(),
                    available: true,
                    models: vec!["llama3".into(), "codellama".into(), "mistral".into()],
                },
            ];
            // In a full impl, we'd call list_providers via RPC here.
            app.provider_select_idx = 0;
            app.mode = AppMode::ProviderSelect;
        }
        "/config" => {
            let config = format!(
                "**Configuration:**\n\n\
                 Provider: {}\n\
                 Model: {}\n\
                 Streaming: {}\n\
                 Version: v{}",
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
