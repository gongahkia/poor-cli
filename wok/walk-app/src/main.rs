//! Walk terminal emulator entry point.

use std::error::Error;

use tracing::info;
use walk_app::event_loop::run_event_loop;
use walk_app::handler::AppHandler;
use walk_app::window::WindowConfig;

/// Minimal app handler that logs events for initial testing.
struct MinimalHandler;

impl AppHandler for MinimalHandler {
    fn on_redraw(&mut self) {}

    fn on_close_requested(&mut self) {
        info!("window close requested");
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| {
                    if cfg!(debug_assertions) {
                        "debug".into()
                    } else {
                        "warn".into()
                    }
                }),
        )
        .init();

    info!("starting Walk terminal");
    let config = WindowConfig::default();
    run_event_loop(config, MinimalHandler)?;
    Ok(())
}
