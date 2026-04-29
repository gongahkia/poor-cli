//! Centralized subprocess primitives for Wok.
//!
//! All non-PTY child-process spawning should go through this crate so env
//! scrubbing, error mapping, and Windows quoting stay consistent.
//!
//! PTY-backed shell spawning still belongs in `wok-terminal` because it goes
//! through `portable-pty::CommandBuilder`, not `std::process::Command`.

mod blocking;
#[cfg(unix)]
mod unix;
#[cfg(windows)]
mod windows;

pub use blocking::{run, run_with, sh, spawn_detached, Cmd, Output};

use thiserror::Error;

/// Errors emitted by `wok-process` operations.
#[derive(Debug, Error)]
pub enum ProcessError {
    /// Failed to spawn the requested program.
    #[error("failed to spawn {program}: {source}")]
    Spawn {
        /// Program path or name that was attempted.
        program: String,
        /// Underlying I/O error.
        #[source]
        source: std::io::Error,
    },

    /// Underlying I/O error during wait/read.
    #[error("process I/O error: {0}")]
    Io(#[from] std::io::Error),

    /// The child exited with a non-success status.
    #[error("{program} exited with status {status}")]
    NonZeroExit {
        /// Program path or name.
        program: String,
        /// Exit status string ("exit code 1", "signal 9", ...).
        status: String,
        /// Captured stdout, if any.
        stdout: Vec<u8>,
        /// Captured stderr, if any.
        stderr: Vec<u8>,
    },
}

/// Open a URL with the OS default handler. Fire-and-forget; ignores failures.
///
/// macOS uses `open`, Linux uses `xdg-open`, Windows uses `cmd /c start`.
pub fn open_url(url: &str) {
    #[cfg(target_os = "macos")]
    let _ = spawn_detached(Cmd::new("open").arg(url));
    #[cfg(target_os = "linux")]
    let _ = spawn_detached(Cmd::new("xdg-open").arg(url));
    #[cfg(target_os = "windows")]
    let _ = spawn_detached(Cmd::new("cmd").args(["/c", "start", url]));
    #[cfg(not(any(target_os = "macos", target_os = "linux", target_os = "windows")))]
    {
        let _ = url;
    }
}

/// A system desktop notification request.
#[derive(Debug, Clone)]
pub struct Notification<'a> {
    /// Notification title.
    pub title: &'a str,
    /// Notification body.
    pub message: &'a str,
    /// Optional subtitle (macOS only — ignored elsewhere).
    pub subtitle: Option<&'a str>,
}

/// Send a system desktop notification via the platform's CLI tool.
///
/// macOS: `osascript`. Linux+other unix: `notify-send`. Windows: no-op (Ok).
pub fn notify(notification: &Notification<'_>) -> Result<(), ProcessError> {
    #[cfg(target_os = "macos")]
    {
        let subtitle = notification
            .subtitle
            .filter(|s| !s.trim().is_empty())
            .map(|s| format!(" subtitle \"{}\"", escape_applescript(s)))
            .unwrap_or_default();
        let script = format!(
            "display notification \"{}\" with title \"{}\"{}",
            escape_applescript(notification.message),
            escape_applescript(notification.title),
            subtitle,
        );
        run(Cmd::new("/usr/bin/osascript").arg("-e").arg(script)).map(|_| ())
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        run(Cmd::new("notify-send")
            .arg(notification.title)
            .arg(notification.message))
        .map(|_| ())
    }
    #[cfg(not(unix))]
    {
        let _ = notification;
        Ok(())
    }
}

#[cfg(target_os = "macos")]
fn escape_applescript(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn notification_struct_is_clone() {
        let n = Notification {
            title: "t",
            message: "m",
            subtitle: Some("s"),
        };
        let _c = n.clone();
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn applescript_escapes_quotes_and_backslashes() {
        assert_eq!(escape_applescript("a\"b\\c"), "a\\\"b\\\\c");
    }
}
