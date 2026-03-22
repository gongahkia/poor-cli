//! Walk terminal emulator entry point.

use std::error::Error;

use clap::Parser;
use tracing::info;
use walk_app::app::WalkApp;
use walk_app::config::WalkConfig;
use walk_app::event_loop::run_event_loop;
use walk_app::handler::AppHandler;
use walk_app::input::InputEvent;
use walk_app::keybindings::KeyCombo;
use walk_app::scripting::LuaRuntime;
use walk_app::window::WindowConfig;
use walk_terminal::shell::ShellType;
use winit::dpi::PhysicalSize;

/// Walk — a GPU-accelerated terminal emulator with Blocks.
#[derive(Parser, Debug)]
#[command(name = "walk", version, about)]
struct Cli {
    /// Override the default shell.
    #[arg(long)]
    shell: Option<String>,

    /// Override the config file path.
    #[arg(long)]
    config: Option<String>,

    /// Window title.
    #[arg(long, default_value = "Walk")]
    title: String,

    /// Initial working directory.
    #[arg(long)]
    working_dir: Option<String>,
}

/// Walk application handler implementing the AppHandler trait.
struct WalkHandler {
    app: WalkApp,
}

impl AppHandler for WalkHandler {
    fn on_redraw(&mut self) {
        // Process PTY output, render, etc.
    }

    fn on_resize(&mut self, _new_size: PhysicalSize<u32>) {
        // Recompute layout, resize terminals
    }

    fn on_key_event(&mut self, event: InputEvent) {
        // Resolve keybinding
        let combo = KeyCombo {
            key: event.action.clone(),
            modifiers: event.modifiers,
        };
        let context = walk_app::keybindings::Context::Terminal;

        if let Some(action) = self.app.keybindings.resolve(&combo, &context).cloned() {
            self.app.handle_action(&action);
        }
    }

    fn on_focus_change(&mut self, _focused: bool) {}

    fn on_close_requested(&mut self) {
        info!("walk closing");
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    // Set up panic handler
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        eprintln!("Walk panicked: {info}");
        default_hook(info);
    }));

    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| {
                if cfg!(debug_assertions) {
                    "debug".into()
                } else {
                    "warn".into()
                }
            }),
        )
        .init();

    let cli = Cli::parse();

    info!("starting Walk terminal");

    // Load config
    let mut config = WalkConfig::load();

    // Apply CLI overrides
    if let Some(shell) = cli.shell {
        config.shell = match shell.as_str() {
            "bash" => ShellType::Bash,
            "zsh" => ShellType::Zsh,
            "fish" => ShellType::Fish,
            "powershell" => ShellType::PowerShell,
            _ => config.shell,
        };
    }

    if let Some(ref dir) = cli.working_dir {
        std::env::set_current_dir(dir)?;
    }

    // Initialize Lua runtime
    let mut lua = LuaRuntime::new()?;
    let config_dir = WalkConfig::config_dir();
    if let Err(e) = lua.init(&config_dir) {
        eprintln!("Warning: Lua init error: {e}");
    }

    // Create application
    let app = WalkApp::new(config);
    let handler = WalkHandler { app };

    let window_config = WindowConfig {
        title: cli.title,
        ..WindowConfig::default()
    };

    run_event_loop(window_config, handler)?;
    Ok(())
}
