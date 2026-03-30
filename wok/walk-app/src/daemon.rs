//! Lightweight daemon/session lifecycle management.

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::ipc::{read_frame, write_frame, ClientMessage, ServerMessage};

/// Daemon session summary for `walk list`.
#[derive(Debug, Clone)]
pub struct SessionSummary {
    /// Session name.
    pub name: String,
    /// Number of panes tracked by the daemon.
    pub pane_count: usize,
    /// Number of attached clients.
    pub attached_clients: usize,
    /// Whether daemon is running.
    pub running: bool,
}

#[cfg(unix)]
mod imp {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::{UnixListener, UnixStream};

    fn runtime_dir() -> PathBuf {
        std::env::var("XDG_RUNTIME_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| std::env::temp_dir())
            .join("walk")
    }

    /// Build the Unix domain socket path for one session.
    pub fn session_socket_path(name: &str) -> PathBuf {
        runtime_dir().join(format!("{name}.sock"))
    }

    /// Run a daemon loop for one named session.
    pub fn run_daemon(name: &str) -> Result<(), Box<dyn std::error::Error>> {
        let dir = runtime_dir();
        fs::create_dir_all(&dir)?;
        let socket = session_socket_path(name);
        if socket.exists() {
            fs::remove_file(&socket)?;
        }
        let listener = UnixListener::bind(&socket)?;
        fs::set_permissions(&socket, fs::Permissions::from_mode(0o600))?;
        listener.set_nonblocking(true)?;

        let mut attached_clients = 0usize;
        let pane_count = 1usize;
        let mut running = true;
        let mut last_housekeeping = Instant::now();

        while running {
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let response = match read_frame::<ClientMessage>(&mut stream) {
                        Ok(message) => match message {
                            ClientMessage::Attach { .. } => {
                                attached_clients = attached_clients.saturating_add(1);
                                ServerMessage::SessionState {
                                    session: name.to_string(),
                                    pane_count,
                                    attached_clients,
                                    running: true,
                                }
                            }
                            ClientMessage::Detach { .. } => {
                                attached_clients = attached_clients.saturating_sub(1);
                                ServerMessage::Ack
                            }
                            ClientMessage::SessionState { .. } => ServerMessage::SessionState {
                                session: name.to_string(),
                                pane_count,
                                attached_clients,
                                running: true,
                            },
                            ClientMessage::Kill { .. } => {
                                running = false;
                                ServerMessage::Ack
                            }
                            ClientMessage::Snapshot => ServerMessage::Snapshot {
                                payload: serde_json::json!({
                                    "session": name,
                                    "pane_count": pane_count,
                                    "attached_clients": attached_clients
                                }),
                            },
                            ClientMessage::Input { .. } | ClientMessage::Resize { .. } => {
                                ServerMessage::Ack
                            }
                        },
                        Err(error) => ServerMessage::Error {
                            message: error.to_string(),
                        },
                    };
                    let _ = write_frame(&mut stream, &response);
                }
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    std::thread::sleep(Duration::from_millis(20));
                }
                Err(error) => return Err(Box::new(error)),
            }

            if last_housekeeping.elapsed() > Duration::from_secs(10) {
                last_housekeeping = Instant::now();
            }
        }

        if socket.exists() {
            fs::remove_file(&socket).ok();
        }
        Ok(())
    }

    /// Query one daemon session.
    pub fn query_session(name: &str) -> Option<SessionSummary> {
        let socket = session_socket_path(name);
        query_session_socket(name, &socket)
    }

    fn query_session_socket(name: &str, socket: &Path) -> Option<SessionSummary> {
        let mut stream = UnixStream::connect(socket).ok()?;
        write_frame(
            &mut stream,
            &ClientMessage::SessionState {
                session: name.to_string(),
            },
        )
        .ok()?;
        let response: ServerMessage = read_frame(&mut stream).ok()?;
        match response {
            ServerMessage::SessionState {
                pane_count,
                attached_clients,
                running,
                ..
            } => Some(SessionSummary {
                name: name.to_string(),
                pane_count,
                attached_clients,
                running,
            }),
            _ => None,
        }
    }

    /// List sessions discovered in the runtime directory.
    pub fn list_sessions() -> Vec<SessionSummary> {
        let dir = runtime_dir();
        let Ok(entries) = fs::read_dir(&dir) else {
            return Vec::new();
        };
        let mut sessions = Vec::new();
        for entry in entries.flatten() {
            let path = entry.path();
            if path.extension().and_then(|ext| ext.to_str()) != Some("sock") {
                continue;
            }
            let Some(name) = path.file_stem().and_then(|stem| stem.to_str()) else {
                continue;
            };
            if let Some(summary) = query_session_socket(name, &path) {
                sessions.push(summary);
            }
        }
        sessions.sort_by(|left, right| left.name.cmp(&right.name));
        sessions
    }

    /// Send a shutdown request to one session.
    pub fn kill_session(name: &str) -> Result<(), Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(
            &mut stream,
            &ClientMessage::Kill {
                session: name.to_string(),
            },
        )?;
        let _: ServerMessage = read_frame(&mut stream)?;
        Ok(())
    }

    /// Send an attach request for one session.
    pub fn attach_session(name: &str) -> Result<SessionSummary, Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(
            &mut stream,
            &ClientMessage::Attach {
                session: name.to_string(),
            },
        )?;
        let response: ServerMessage = read_frame(&mut stream)?;
        match response {
            ServerMessage::SessionState {
                pane_count,
                attached_clients,
                running,
                ..
            } => Ok(SessionSummary {
                name: name.to_string(),
                pane_count,
                attached_clients,
                running,
            }),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }
}

#[cfg(not(unix))]
mod imp {
    use super::*;

    /// Build a placeholder socket path.
    pub fn session_socket_path(_name: &str) -> PathBuf {
        PathBuf::from("walk-daemon-not-supported.sock")
    }

    /// Unsupported daemon startup on this platform.
    pub fn run_daemon(_name: &str) -> Result<(), Box<dyn std::error::Error>> {
        Err("daemon mode is currently supported on Unix only".into())
    }

    /// Unsupported session query on this platform.
    pub fn query_session(_name: &str) -> Option<SessionSummary> {
        None
    }

    /// Unsupported session list on this platform.
    pub fn list_sessions() -> Vec<SessionSummary> {
        Vec::new()
    }

    /// Unsupported session kill on this platform.
    pub fn kill_session(_name: &str) -> Result<(), Box<dyn std::error::Error>> {
        Err("daemon mode is currently supported on Unix only".into())
    }

    /// Unsupported session attach on this platform.
    pub fn attach_session(_name: &str) -> Result<SessionSummary, Box<dyn std::error::Error>> {
        Err("daemon mode is currently supported on Unix only".into())
    }
}

/// Return the socket path for a named session.
pub fn session_socket_path(name: &str) -> PathBuf {
    imp::session_socket_path(name)
}

/// Run a named daemon session until killed.
pub fn run_daemon(name: &str) -> Result<(), Box<dyn std::error::Error>> {
    imp::run_daemon(name)
}

/// Query one session by name.
pub fn query_session(name: &str) -> Option<SessionSummary> {
    imp::query_session(name)
}

/// List currently running sessions.
pub fn list_sessions() -> Vec<SessionSummary> {
    imp::list_sessions()
}

/// Send a kill request to a named session.
pub fn kill_session(name: &str) -> Result<(), Box<dyn std::error::Error>> {
    imp::kill_session(name)
}

/// Attach to a named session and return its current summary.
pub fn attach_session(name: &str) -> Result<SessionSummary, Box<dyn std::error::Error>> {
    imp::attach_session(name)
}
