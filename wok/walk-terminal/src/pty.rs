//! PTY management: spawns and manages shell processes using portable-pty.

use std::collections::HashMap;

use portable_pty::{native_pty_system, CommandBuilder, PtyPair, PtySize, PtySystem};
use thiserror::Error;
use tracing::{debug, info, instrument};

use crate::shell::{shell_spawn_config, ShellType};

/// Errors that can occur during PTY operations.
#[derive(Debug, Error)]
pub enum PtyError {
    /// Failed to create the native PTY system.
    #[error("failed to create PTY pair: {0}")]
    SystemCreation(String),

    /// Failed to spawn the shell process.
    #[error("failed to spawn shell '{shell}': {source}")]
    SpawnFailed {
        /// The shell path that was attempted.
        shell: String,
        /// The underlying error.
        #[source]
        source: Box<dyn std::error::Error + Send + Sync>,
    },

    /// PTY I/O error.
    #[error("PTY I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// The PTY reader channel was disconnected.
    #[error("PTY reader channel disconnected")]
    ChannelDisconnected,
}

/// Manages creation of PTY processes.
pub struct PtyManager {
    pty_system: Box<dyn PtySystem + Send>,
}

impl PtyManager {
    /// Create a new PTY manager using the native PTY system.
    pub fn new() -> Self {
        Self {
            pty_system: native_pty_system(),
        }
    }

    /// Spawn a new shell process.
    ///
    /// # Errors
    ///
    /// Returns [`PtyError::SystemCreation`] if the PTY pair cannot be created,
    /// or [`PtyError::SpawnFailed`] if the shell process fails to start.
    #[instrument(skip(self, env), fields(shell = %shell_type))]
    pub fn spawn(
        &self,
        shell_type: &ShellType,
        cols: u16,
        rows: u16,
        env: HashMap<String, String>,
    ) -> Result<PtyPair, PtyError> {
        let config = shell_spawn_config(shell_type);

        let size = PtySize {
            rows,
            cols,
            pixel_width: 0,
            pixel_height: 0,
        };

        let pair = self
            .pty_system
            .openpty(size)
            .map_err(|e| PtyError::SystemCreation(e.to_string()))?;

        let mut cmd = CommandBuilder::new(&config.shell);
        for arg in &config.args {
            cmd.arg(arg);
        }

        // Set environment variables
        for (key, val) in &config.env {
            cmd.env(key, val);
        }
        for (key, val) in &env {
            cmd.env(key, val);
        }

        info!(shell = %config.shell, "spawning shell process");
        let _child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| PtyError::SpawnFailed {
                shell: config.shell.clone(),
                source: e.into(),
            })?;

        debug!("shell process spawned successfully");
        Ok(pair)
    }
}

impl Default for PtyManager {
    fn default() -> Self {
        Self::new()
    }
}
