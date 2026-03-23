//! PTY management: spawns and manages shell processes using portable-pty.

use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::Path;

use portable_pty::{native_pty_system, Child, CommandBuilder, MasterPty, PtySize, PtySystem};
use thiserror::Error;
use tracing::{debug, info, instrument};

use crate::shell::{shell_spawn_config, ShellType};
use crate::shell_integration::{apply_wsl_cwd, prepare_shell_bootstrap, ShellBootstrap};

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

    /// Failed to resize the PTY.
    #[error("failed to resize PTY: {0}")]
    ResizeFailed(String),

    /// Failed to prepare shell bootstrap files.
    #[error("failed to prepare shell bootstrap: {0}")]
    BootstrapFailed(String),
}

/// A spawned PTY with the handles needed by Walk's runtime.
pub struct SpawnedPty {
    /// The PTY master handle, retained for kernel-level resize.
    pub master: Box<dyn MasterPty + Send>,
    /// Read handle for PTY output.
    pub reader: Box<dyn Read + Send>,
    /// Write handle for PTY input.
    pub writer: Box<dyn Write + Send>,
    /// Child process running inside the PTY.
    pub child: Box<dyn Child + Send + Sync>,
    /// Temporary bootstrap files that must remain alive for the shell lifetime.
    pub shell_bootstrap: ShellBootstrap,
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
        env: &HashMap<String, String>,
        cwd: Option<&Path>,
    ) -> Result<SpawnedPty, PtyError> {
        let mut config = shell_spawn_config(shell_type);
        if let (ShellType::Wsl(_), Some(cwd)) = (shell_type, cwd) {
            apply_wsl_cwd(&mut config, cwd);
        }
        let shell_bootstrap = prepare_shell_bootstrap(shell_type, &mut config)
            .map_err(|e| PtyError::BootstrapFailed(e.to_string()))?;

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
        if let Some(cwd) = cwd {
            cmd.cwd(cwd);
        }

        // Set environment variables
        for (key, val) in &config.env {
            cmd.env(key, val);
        }
        for (key, val) in env {
            cmd.env(key, val);
        }

        info!(shell = %config.shell, "spawning shell process");
        let child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| PtyError::SpawnFailed {
                shell: config.shell.clone(),
                source: e.into(),
            })?;

        let reader = pair
            .master
            .try_clone_reader()
            .map_err(|e| PtyError::SystemCreation(format!("failed to clone PTY reader: {e}")))?;
        let writer = pair
            .master
            .take_writer()
            .map_err(|e| PtyError::SystemCreation(format!("failed to take PTY writer: {e}")))?;

        debug!("shell process spawned successfully");
        Ok(SpawnedPty {
            master: pair.master,
            reader,
            writer,
            child,
            shell_bootstrap,
        })
    }
}

impl Default for PtyManager {
    fn default() -> Self {
        Self::new()
    }
}
