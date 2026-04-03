//! Lightweight daemon/session lifecycle management.

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::ipc::{read_frame, write_frame, ClientMessage, ServerMessage};
use walk_terminal::shell::ShellType;
use walk_terminal::terminal::Terminal;

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
    use super::{
        read_frame, write_frame, ClientMessage, Duration, Instant, Path, PathBuf, ServerMessage,
        SessionSummary, ShellType, Terminal,
    };
    use std::collections::HashMap;
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
    pub fn run_daemon(name: &str, shell: &ShellType) -> Result<(), Box<dyn std::error::Error>> {
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
        let mut terminal = Terminal::new(shell, 80, 24, 10_000, HashMap::new(), None)?;

        while running {
            terminal.process_pty_output();
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
                                    "attached_clients": attached_clients,
                                    "rows": terminal.state.text_rows().into_iter().map(|row| {
                                        serde_json::json!({
                                            "absolute_row": row.absolute_row,
                                            "viewport_row": row.viewport_row,
                                            "text": row.text
                                        })
                                    }).collect::<Vec<_>>(),
                                    "display_offset": terminal.state.display_offset(),
                                    "cols": terminal.cols(),
                                    "rows_visible": terminal.rows()
                                }),
                            },
                            ClientMessage::Input { data, .. } => {
                                terminal.send_input(&data).map_or_else(
                                    |error| ServerMessage::Error {
                                        message: error.to_string(),
                                    },
                                    |()| ServerMessage::Ack,
                                )
                            }
                            ClientMessage::Resize { cols, rows, .. } => {
                                terminal.resize(cols, rows).map_or_else(
                                    |error| ServerMessage::Error {
                                        message: error.to_string(),
                                    },
                                    |()| ServerMessage::Ack,
                                )
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

    /// Send a detach request for one session.
    pub fn detach_session(name: &str) -> Result<(), Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(
            &mut stream,
            &ClientMessage::Detach {
                session: name.to_string(),
            },
        )?;
        let _: ServerMessage = read_frame(&mut stream)?;
        Ok(())
    }

    /// Send raw input bytes to a session pane.
    pub fn send_input(
        name: &str,
        pane_id: u64,
        data: &[u8],
    ) -> Result<(), Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(
            &mut stream,
            &ClientMessage::Input {
                pane_id,
                data: data.to_vec(),
            },
        )?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Ack => Ok(()),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// Resize a session pane.
    pub fn resize_pane(
        name: &str,
        pane_id: u64,
        cols: u16,
        rows: u16,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(
            &mut stream,
            &ClientMessage::Resize {
                pane_id,
                cols,
                rows,
            },
        )?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Ack => Ok(()),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// Fetch a snapshot payload for one session.
    pub fn snapshot_session(name: &str) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(&mut stream, &ClientMessage::Snapshot)?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Snapshot { payload } => Ok(payload),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }
}

#[cfg(not(unix))]
mod imp {
    use super::{
        read_frame, write_frame, ClientMessage, Duration, Instant, Path, PathBuf, ServerMessage,
        SessionSummary, ShellType, Terminal,
    };
    use std::collections::HashMap;
    use std::fs;
    use std::net::{TcpListener, TcpStream};

    fn runtime_dir() -> PathBuf {
        std::env::temp_dir().join("walk")
    }

    /// Build the local session endpoint metadata path.
    pub fn session_socket_path(name: &str) -> PathBuf {
        runtime_dir().join(format!("{name}.port"))
    }

    /// Run a daemon loop for one named session.
    pub fn run_daemon(name: &str, shell: &ShellType) -> Result<(), Box<dyn std::error::Error>> {
        let dir = runtime_dir();
        fs::create_dir_all(&dir)?;
        let metadata = session_socket_path(name);
        if metadata.exists() {
            fs::remove_file(&metadata)?;
        }

        let listener = TcpListener::bind(("127.0.0.1", 0))?;
        listener.set_nonblocking(true)?;
        let port = listener.local_addr()?.port();
        fs::write(&metadata, port.to_string())?;

        let mut attached_clients = 0usize;
        let pane_count = 1usize;
        let mut running = true;
        let mut last_housekeeping = Instant::now();
        let mut terminal = Terminal::new(shell, 80, 24, 10_000, HashMap::new(), None)?;

        while running {
            terminal.process_pty_output();
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
                                    "attached_clients": attached_clients,
                                    "rows": terminal.state.text_rows().into_iter().map(|row| {
                                        serde_json::json!({
                                            "absolute_row": row.absolute_row,
                                            "viewport_row": row.viewport_row,
                                            "text": row.text
                                        })
                                    }).collect::<Vec<_>>(),
                                    "display_offset": terminal.state.display_offset(),
                                    "cols": terminal.cols(),
                                    "rows_visible": terminal.rows()
                                }),
                            },
                            ClientMessage::Input { data, .. } => {
                                terminal.send_input(&data).map_or_else(
                                    |error| ServerMessage::Error {
                                        message: error.to_string(),
                                    },
                                    |()| ServerMessage::Ack,
                                )
                            }
                            ClientMessage::Resize { cols, rows, .. } => {
                                terminal.resize(cols, rows).map_or_else(
                                    |error| ServerMessage::Error {
                                        message: error.to_string(),
                                    },
                                    |()| ServerMessage::Ack,
                                )
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

        if metadata.exists() {
            fs::remove_file(&metadata).ok();
        }
        Ok(())
    }

    /// Query one daemon session.
    pub fn query_session(name: &str) -> Option<SessionSummary> {
        let metadata = session_socket_path(name);
        query_session_metadata(name, &metadata)
    }

    fn read_port(metadata: &Path) -> Option<u16> {
        let raw = fs::read_to_string(metadata).ok()?;
        raw.trim().parse::<u16>().ok()
    }

    fn query_session_metadata(name: &str, metadata: &Path) -> Option<SessionSummary> {
        let port = read_port(metadata)?;
        let mut stream = TcpStream::connect(("127.0.0.1", port)).ok()?;
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
            if path.extension().and_then(|ext| ext.to_str()) != Some("port") {
                continue;
            }
            let Some(name) = path.file_stem().and_then(|stem| stem.to_str()) else {
                continue;
            };
            if let Some(summary) = query_session_metadata(name, &path) {
                sessions.push(summary);
            }
        }
        sessions.sort_by(|left, right| left.name.cmp(&right.name));
        sessions
    }

    /// Send a shutdown request to one session.
    pub fn kill_session(name: &str) -> Result<(), Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
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
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
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

    /// Send a detach request for one session.
    pub fn detach_session(name: &str) -> Result<(), Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
        write_frame(
            &mut stream,
            &ClientMessage::Detach {
                session: name.to_string(),
            },
        )?;
        let _: ServerMessage = read_frame(&mut stream)?;
        Ok(())
    }

    /// Send raw input bytes to a session pane.
    pub fn send_input(
        name: &str,
        pane_id: u64,
        data: &[u8],
    ) -> Result<(), Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
        write_frame(
            &mut stream,
            &ClientMessage::Input {
                pane_id,
                data: data.to_vec(),
            },
        )?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Ack => Ok(()),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// Resize a session pane.
    pub fn resize_pane(
        name: &str,
        pane_id: u64,
        cols: u16,
        rows: u16,
    ) -> Result<(), Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
        write_frame(
            &mut stream,
            &ClientMessage::Resize {
                pane_id,
                cols,
                rows,
            },
        )?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Ack => Ok(()),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// Fetch a snapshot payload for one session.
    pub fn snapshot_session(name: &str) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
        write_frame(&mut stream, &ClientMessage::Snapshot)?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Snapshot { payload } => Ok(payload),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }
}

/// Return the socket path for a named session.
pub fn session_socket_path(name: &str) -> PathBuf {
    imp::session_socket_path(name)
}

/// Run a named daemon session until killed.
pub fn run_daemon(name: &str) -> Result<(), Box<dyn std::error::Error>> {
    imp::run_daemon(name, &ShellType::Bash)
}

/// Run a named daemon session with an explicit shell type.
pub fn run_daemon_with_shell(
    name: &str,
    shell: &ShellType,
) -> Result<(), Box<dyn std::error::Error>> {
    imp::run_daemon(name, shell)
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

/// Detach from a named session.
pub fn detach_session(name: &str) -> Result<(), Box<dyn std::error::Error>> {
    imp::detach_session(name)
}

/// Send input bytes to a daemon pane.
pub fn send_input(
    session: &str,
    pane_id: u64,
    data: &[u8],
) -> Result<(), Box<dyn std::error::Error>> {
    imp::send_input(session, pane_id, data)
}

/// Resize a daemon pane.
pub fn resize_pane(
    session: &str,
    pane_id: u64,
    cols: u16,
    rows: u16,
) -> Result<(), Box<dyn std::error::Error>> {
    imp::resize_pane(session, pane_id, cols, rows)
}

/// Fetch one daemon snapshot payload.
pub fn snapshot_session(session: &str) -> Result<serde_json::Value, Box<dyn std::error::Error>> {
    imp::snapshot_session(session)
}
