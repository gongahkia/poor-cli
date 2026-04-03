//! Lightweight daemon/session lifecycle management.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use crate::ipc::{read_frame, write_frame, ClientMessage, PaneInfo, ServerMessage};
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

struct DaemonPane {
    terminal: Terminal,
    cols: u16,
    rows: u16,
}

struct DaemonSession {
    name: String,
    shell: ShellType,
    env: HashMap<String, String>,
    panes: HashMap<u64, DaemonPane>,
    focused_pane: u64,
    next_pane_id: u64,
    attached_clients: usize,
    running: bool,
}

impl DaemonSession {
    fn new(
        name: &str,
        shell: &ShellType,
        env: HashMap<String, String>,
        terminal: Terminal,
    ) -> Self {
        let cols = terminal.cols();
        let rows = terminal.rows();
        let mut panes = HashMap::new();
        panes.insert(0, DaemonPane { terminal, cols, rows });
        Self {
            name: name.to_string(),
            shell: shell.clone(),
            env,
            panes,
            focused_pane: 0,
            next_pane_id: 1,
            attached_clients: 0,
            running: true,
        }
    }
    fn pane_count(&self) -> usize { self.panes.len() }
    fn process_pty_output(&mut self) {
        for pane in self.panes.values_mut() {
            pane.terminal.process_pty_output();
        }
    }
    fn snapshot(&self) -> serde_json::Value {
        let focused = self.panes.get(&self.focused_pane)
            .or_else(|| self.panes.values().next());
        let panes_json: Vec<_> = self.pane_ids().iter().map(|&id| {
            let pane = self.panes.get(&id).unwrap();
            serde_json::json!({
                "pane_id": id,
                "rows": pane.terminal.state.text_rows().into_iter().map(|row| {
                    serde_json::json!({
                        "absolute_row": row.absolute_row,
                        "viewport_row": row.viewport_row,
                        "text": row.text
                    })
                }).collect::<Vec<_>>(),
                "display_offset": pane.terminal.state.display_offset(),
                "cols": pane.terminal.cols(),
                "rows_visible": pane.terminal.rows()
            })
        }).collect();
        serde_json::json!({
            "session": self.name,
            "pane_count": self.pane_count(),
            "attached_clients": self.attached_clients,
            "rows": focused.map(|p| p.terminal.state.text_rows().into_iter().map(|row| {
                serde_json::json!({
                    "absolute_row": row.absolute_row,
                    "viewport_row": row.viewport_row,
                    "text": row.text
                })
            }).collect::<Vec<_>>()).unwrap_or_default(),
            "display_offset": focused.map(|p| p.terminal.state.display_offset()).unwrap_or(0),
            "cols": focused.map(|p| p.terminal.cols()).unwrap_or(80),
            "rows_visible": focused.map(|p| p.terminal.rows()).unwrap_or(24),
            "panes": panes_json
        })
    }
    fn handle_input(&self, pane_id: u64, data: &[u8]) -> ServerMessage {
        match self.panes.get(&pane_id) {
            Some(pane) => pane.terminal.send_input(data).map_or_else(
                |error| ServerMessage::Error { message: error.to_string() },
                |()| ServerMessage::Ack,
            ),
            None => ServerMessage::Error { message: format!("pane {pane_id} not found") },
        }
    }
    fn handle_resize(&mut self, pane_id: u64, cols: u16, rows: u16) -> ServerMessage {
        match self.panes.get_mut(&pane_id) {
            Some(pane) => {
                pane.cols = cols;
                pane.rows = rows;
                pane.terminal.resize(cols, rows).map_or_else(
                    |error| ServerMessage::Error { message: error.to_string() },
                    |()| ServerMessage::Ack,
                )
            }
            None => ServerMessage::Error { message: format!("pane {pane_id} not found") },
        }
    }
    fn create_pane(&mut self, _direction: &str) -> ServerMessage {
        let id = self.next_pane_id;
        self.next_pane_id += 1;
        match Terminal::new(&self.shell, 80, 24, 10_000, self.env.clone(), None) {
            Ok(terminal) => {
                let cols = terminal.cols();
                let rows = terminal.rows();
                self.panes.insert(id, DaemonPane { terminal, cols, rows });
                ServerMessage::PaneCreated { pane_id: id }
            }
            Err(e) => ServerMessage::Error { message: format!("failed to create pane: {e}") },
        }
    }
    fn close_pane(&mut self, pane_id: u64) -> ServerMessage {
        if self.panes.len() <= 1 {
            return ServerMessage::Error { message: "cannot close last pane".to_string() };
        }
        if self.panes.remove(&pane_id).is_some() {
            if self.focused_pane == pane_id {
                self.focused_pane = self.panes.keys().copied().min().unwrap_or(0);
            }
            ServerMessage::Ack
        } else {
            ServerMessage::Error { message: format!("pane {pane_id} not found") }
        }
    }
    fn pane_ids(&self) -> Vec<u64> {
        let mut ids: Vec<u64> = self.panes.keys().copied().collect();
        ids.sort_unstable();
        ids
    }
    fn pane_list(&self) -> Vec<PaneInfo> {
        self.pane_ids().iter().map(|&id| {
            let pane = self.panes.get(&id).unwrap();
            PaneInfo { pane_id: id, cols: pane.cols, rows: pane.rows }
        }).collect()
    }
}

#[cfg(unix)]
mod imp {
    use super::{
        read_frame, write_frame, ClientMessage, DaemonSession, Duration, Instant, PaneInfo, Path,
        PathBuf, ServerMessage, SessionSummary, ShellType, Terminal,
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

    fn daemon_terminal_env(name: &str) -> HashMap<String, String> {
        let mut env = HashMap::new();
        env.insert("WALK_SESSION".to_string(), name.to_string());
        env.insert(
            "WALK_SESSION_SOCKET".to_string(),
            session_socket_path(name).display().to_string(),
        );
        env
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

        let env = daemon_terminal_env(name);
        let terminal = Terminal::new(shell, 80, 24, 10_000, env.clone(), None)?;
        let mut session = DaemonSession::new(name, shell, env, terminal);
        let mut last_housekeeping = Instant::now();

        while session.running {
            session.process_pty_output();
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let response = match read_frame::<ClientMessage>(&mut stream) {
                        Ok(message) => match message {
                            ClientMessage::Attach { .. } => {
                                session.attached_clients = session.attached_clients.saturating_add(1);
                                ServerMessage::SessionState {
                                    session: name.to_string(),
                                    pane_count: session.pane_count(),
                                    attached_clients: session.attached_clients,
                                    running: true,
                                }
                            }
                            ClientMessage::Detach { .. } => {
                                session.attached_clients = session.attached_clients.saturating_sub(1);
                                ServerMessage::Ack
                            }
                            ClientMessage::SessionState { .. } => ServerMessage::SessionState {
                                session: name.to_string(),
                                pane_count: session.pane_count(),
                                attached_clients: session.attached_clients,
                                running: true,
                            },
                            ClientMessage::Kill { .. } => {
                                session.running = false;
                                ServerMessage::Ack
                            }
                            ClientMessage::Snapshot => ServerMessage::Snapshot {
                                payload: session.snapshot(),
                            },
                            ClientMessage::Input { pane_id, data } => {
                                session.handle_input(pane_id, &data)
                            }
                            ClientMessage::Resize { pane_id, cols, rows } => {
                                session.handle_resize(pane_id, cols, rows)
                            }
                            ClientMessage::CreatePane { direction } => {
                                session.create_pane(&direction)
                            }
                            ClientMessage::ClosePane { pane_id } => {
                                session.close_pane(pane_id)
                            }
                            ClientMessage::GetPanes => ServerMessage::Panes {
                                items: session.pane_list(),
                            },
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

    /// Create a new pane in a daemon session.
    pub fn create_pane(name: &str, direction: &str) -> Result<u64, Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(&mut stream, &ClientMessage::CreatePane { direction: direction.to_string() })?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::PaneCreated { pane_id } => Ok(pane_id),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// Close a pane in a daemon session.
    pub fn close_pane(name: &str, pane_id: u64) -> Result<(), Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(&mut stream, &ClientMessage::ClosePane { pane_id })?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Ack => Ok(()),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// List panes in a daemon session.
    pub fn list_panes(name: &str) -> Result<Vec<PaneInfo>, Box<dyn std::error::Error>> {
        let socket = session_socket_path(name);
        let mut stream = UnixStream::connect(&socket)?;
        write_frame(&mut stream, &ClientMessage::GetPanes)?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Panes { items } => Ok(items),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }
}

#[cfg(not(unix))]
mod imp {
    use super::{
        read_frame, write_frame, ClientMessage, DaemonSession, Duration, Instant, PaneInfo, Path,
        PathBuf, ServerMessage, SessionSummary, ShellType, Terminal,
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

    fn daemon_terminal_env(name: &str) -> HashMap<String, String> {
        let mut env = HashMap::new();
        env.insert("WALK_SESSION".to_string(), name.to_string());
        env.insert(
            "WALK_SESSION_ENDPOINT".to_string(),
            session_socket_path(name).display().to_string(),
        );
        env
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

        let env = daemon_terminal_env(name);
        let terminal = Terminal::new(shell, 80, 24, 10_000, env.clone(), None)?;
        let mut session = DaemonSession::new(name, shell, env, terminal);
        let mut last_housekeeping = Instant::now();

        while session.running {
            session.process_pty_output();
            match listener.accept() {
                Ok((mut stream, _)) => {
                    let response = match read_frame::<ClientMessage>(&mut stream) {
                        Ok(message) => match message {
                            ClientMessage::Attach { .. } => {
                                session.attached_clients = session.attached_clients.saturating_add(1);
                                ServerMessage::SessionState {
                                    session: name.to_string(),
                                    pane_count: session.pane_count(),
                                    attached_clients: session.attached_clients,
                                    running: true,
                                }
                            }
                            ClientMessage::Detach { .. } => {
                                session.attached_clients = session.attached_clients.saturating_sub(1);
                                ServerMessage::Ack
                            }
                            ClientMessage::SessionState { .. } => ServerMessage::SessionState {
                                session: name.to_string(),
                                pane_count: session.pane_count(),
                                attached_clients: session.attached_clients,
                                running: true,
                            },
                            ClientMessage::Kill { .. } => {
                                session.running = false;
                                ServerMessage::Ack
                            }
                            ClientMessage::Snapshot => ServerMessage::Snapshot {
                                payload: session.snapshot(),
                            },
                            ClientMessage::Input { pane_id, data } => {
                                session.handle_input(pane_id, &data)
                            }
                            ClientMessage::Resize { pane_id, cols, rows } => {
                                session.handle_resize(pane_id, cols, rows)
                            }
                            ClientMessage::CreatePane { direction } => {
                                session.create_pane(&direction)
                            }
                            ClientMessage::ClosePane { pane_id } => {
                                session.close_pane(pane_id)
                            }
                            ClientMessage::GetPanes => ServerMessage::Panes {
                                items: session.pane_list(),
                            },
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

    /// Create a new pane in a daemon session.
    pub fn create_pane(name: &str, direction: &str) -> Result<u64, Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
        write_frame(
            &mut stream,
            &ClientMessage::CreatePane { direction: direction.to_string() },
        )?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::PaneCreated { pane_id } => Ok(pane_id),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// Close a pane in a daemon session.
    pub fn close_pane(name: &str, pane_id: u64) -> Result<(), Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
        write_frame(&mut stream, &ClientMessage::ClosePane { pane_id })?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Ack => Ok(()),
            ServerMessage::Error { message } => Err(message.into()),
            _ => Err("unexpected daemon response".into()),
        }
    }

    /// List panes in a daemon session.
    pub fn list_panes(name: &str) -> Result<Vec<PaneInfo>, Box<dyn std::error::Error>> {
        let metadata = session_socket_path(name);
        let Some(port) = read_port(&metadata) else {
            return Err("session not found".into());
        };
        let mut stream = TcpStream::connect(("127.0.0.1", port))?;
        write_frame(&mut stream, &ClientMessage::GetPanes)?;
        match read_frame::<ServerMessage>(&mut stream)? {
            ServerMessage::Panes { items } => Ok(items),
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

/// Create a new pane in a daemon session.
pub fn create_pane(session: &str, direction: &str) -> Result<u64, Box<dyn std::error::Error>> {
    imp::create_pane(session, direction)
}

/// Close a pane in a daemon session.
pub fn close_pane(session: &str, pane_id: u64) -> Result<(), Box<dyn std::error::Error>> {
    imp::close_pane(session, pane_id)
}

/// List panes in a daemon session.
pub fn list_panes(session: &str) -> Result<Vec<crate::ipc::PaneInfo>, Box<dyn std::error::Error>> {
    imp::list_panes(session)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ipc::ServerMessage;

    fn make_session() -> DaemonSession {
        let shell = ShellType::Bash;
        let env = HashMap::new();
        let terminal = Terminal::new(&shell, 80, 24, 10_000, env.clone(), None)
            .expect("terminal should spawn");
        DaemonSession::new("test", &shell, env, terminal)
    }

    #[test]
    fn test_daemon_session_initial_state() {
        let session = make_session();
        assert_eq!(session.pane_count(), 1);
        assert_eq!(session.attached_clients, 0);
        assert!(session.running);
        assert_eq!(session.focused_pane, 0);
        assert_eq!(session.next_pane_id, 1);
    }

    #[test]
    fn test_daemon_session_create_pane() {
        let mut session = make_session();
        let response = session.create_pane("vertical");
        match response {
            ServerMessage::PaneCreated { pane_id } => {
                assert_eq!(pane_id, 1);
                assert_eq!(session.pane_count(), 2);
                assert_eq!(session.next_pane_id, 2);
            }
            _ => panic!("expected PaneCreated"),
        }
    }

    #[test]
    fn test_daemon_session_close_pane() {
        let mut session = make_session();
        session.create_pane("vertical");
        assert_eq!(session.pane_count(), 2);
        let response = session.close_pane(1);
        assert!(matches!(response, ServerMessage::Ack));
        assert_eq!(session.pane_count(), 1);
    }

    #[test]
    fn test_daemon_session_close_last_pane_fails() {
        let mut session = make_session();
        let response = session.close_pane(0);
        assert!(matches!(response, ServerMessage::Error { .. }));
        assert_eq!(session.pane_count(), 1);
    }

    #[test]
    fn test_daemon_session_close_nonexistent_pane() {
        let mut session = make_session();
        session.create_pane("vertical");
        let response = session.close_pane(99);
        assert!(matches!(response, ServerMessage::Error { .. }));
        assert_eq!(session.pane_count(), 2);
    }

    #[test]
    fn test_daemon_session_pane_list() {
        let mut session = make_session();
        session.create_pane("vertical");
        let list = session.pane_list();
        assert_eq!(list.len(), 2);
        assert!(list.iter().any(|p| p.pane_id == 0));
        assert!(list.iter().any(|p| p.pane_id == 1));
    }

    #[test]
    fn test_daemon_session_close_focused_pane_updates_focus() {
        let mut session = make_session();
        session.create_pane("vertical");
        session.focused_pane = 1;
        session.close_pane(1);
        assert_eq!(session.focused_pane, 0);
    }

    #[test]
    fn test_daemon_session_handle_input_nonexistent_pane() {
        let session = make_session();
        let response = session.handle_input(99, b"hello");
        assert!(matches!(response, ServerMessage::Error { .. }));
    }

    #[test]
    fn test_daemon_session_handle_resize_nonexistent_pane() {
        let mut session = make_session();
        let response = session.handle_resize(99, 100, 50);
        assert!(matches!(response, ServerMessage::Error { .. }));
    }

    #[test]
    fn test_daemon_session_snapshot_has_panes_array() {
        let session = make_session();
        let snap = session.snapshot();
        assert!(snap.get("panes").and_then(|v| v.as_array()).is_some());
        assert_eq!(snap["pane_count"], 1);
    }
}
