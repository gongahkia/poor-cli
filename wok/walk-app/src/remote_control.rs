//! JSON-RPC remote control server for external automation.

use std::io::{Read, Write};
use std::path::{Path, PathBuf};

use serde::Deserialize;
use serde_json::{json, Value};
use tracing::warn;

/// Maximum number of concurrent remote-control clients.
pub const MAX_CLIENTS: usize = 8;

/// One decoded JSON-RPC request ready for runtime handling.
#[derive(Debug, Clone)]
pub struct RemoteRequest {
    /// Unique in-process client id.
    pub client_id: u64,
    /// Optional JSON-RPC id for request/response correlation.
    pub id: Option<Value>,
    /// JSON-RPC method name.
    pub method: String,
    /// JSON-RPC params payload.
    pub params: Value,
}

#[derive(Debug, Clone, Deserialize)]
struct RawRequest {
    jsonrpc: Option<String>,
    method: String,
    #[serde(default)]
    params: Value,
    id: Option<Value>,
}

#[cfg(unix)]
mod imp {
    use super::*;
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::{UnixListener, UnixStream};

    #[derive(Debug)]
    struct ClientConnection {
        id: u64,
        stream: UnixStream,
        buffer: Vec<u8>,
        closed: bool,
    }

    /// Non-blocking JSON-RPC server bound to a per-process Unix socket.
    pub struct RemoteControlServer {
        listener: UnixListener,
        socket_path: PathBuf,
        clients: Vec<ClientConnection>,
        next_client_id: u64,
    }

    impl RemoteControlServer {
        /// Start a non-blocking server at a process-scoped socket path.
        pub fn bind_default() -> Result<Self, std::io::Error> {
            let socket_path = default_socket_path();
            if let Some(parent) = socket_path.parent() {
                fs::create_dir_all(parent)?;
            }
            if socket_path.exists() {
                fs::remove_file(&socket_path)?;
            }

            let listener = UnixListener::bind(&socket_path)?;
            listener.set_nonblocking(true)?;
            fs::set_permissions(&socket_path, fs::Permissions::from_mode(0o600))?;

            Ok(Self {
                listener,
                socket_path,
                clients: Vec::new(),
                next_client_id: 1,
            })
        }

        /// Return the current remote-control socket path.
        pub fn socket_path(&self) -> &Path {
            &self.socket_path
        }

        /// Poll listener + client streams and return decoded requests.
        pub fn poll_requests(&mut self) -> Vec<RemoteRequest> {
            self.accept_new_clients();

            let mut requests = Vec::new();
            let mut remove_ids = Vec::new();

            for client in &mut self.clients {
                match Self::read_client(client, &mut requests) {
                    Ok(()) => {}
                    Err(error) => {
                        warn!("remote control read error for client {}: {error}", client.id);
                        remove_ids.push(client.id);
                    }
                }

                if client.closed && client.buffer.is_empty() {
                    remove_ids.push(client.id);
                }
            }

            if !remove_ids.is_empty() {
                self.clients.retain(|client| !remove_ids.contains(&client.id));
            }

            requests
        }

        /// Send one JSON response to a connected client.
        pub fn send_response(&mut self, client_id: u64, payload: &Value) {
            let mut remove = false;

            if let Some(client) = self.clients.iter_mut().find(|client| client.id == client_id) {
                match serde_json::to_vec(payload) {
                    Ok(mut bytes) => {
                        bytes.push(b'\n');
                        if let Err(error) = client.stream.write_all(&bytes) {
                            warn!("remote control write error for client {client_id}: {error}");
                            remove = true;
                        }
                    }
                    Err(error) => {
                        warn!("failed to encode remote response for client {client_id}: {error}");
                    }
                }
                if client.closed {
                    remove = true;
                }
            }

            if remove {
                self.clients.retain(|client| client.id != client_id);
            }
        }

        fn accept_new_clients(&mut self) {
            loop {
                match self.listener.accept() {
                    Ok((stream, _addr)) => {
                        if self.clients.len() >= MAX_CLIENTS {
                            let payload = super::error_response(
                                None,
                                -32000,
                                "too many remote control clients",
                            );
                            let mut stream = stream;
                            if let Ok(mut bytes) = serde_json::to_vec(&payload) {
                                bytes.push(b'\n');
                                let _ = stream.write_all(&bytes);
                            }
                            continue;
                        }

                        if let Err(error) = stream.set_nonblocking(true) {
                            warn!("failed to set remote client nonblocking mode: {error}");
                            continue;
                        }

                        let client = ClientConnection {
                            id: self.next_client_id,
                            stream,
                            buffer: Vec::new(),
                            closed: false,
                        };
                        self.next_client_id = self.next_client_id.saturating_add(1);
                        self.clients.push(client);
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => break,
                    Err(error) => {
                        warn!("remote listener accept error: {error}");
                        break;
                    }
                }
            }
        }

        fn read_client(
            client: &mut ClientConnection,
            requests: &mut Vec<RemoteRequest>,
        ) -> Result<(), std::io::Error> {
            let mut scratch = [0u8; 4_096];
            loop {
                match client.stream.read(&mut scratch) {
                    Ok(0) => {
                        client.closed = true;
                        break;
                    }
                    Ok(bytes_read) => {
                        client.buffer.extend_from_slice(&scratch[..bytes_read]);
                        if client.buffer.len() > 1_048_576 {
                            client.buffer.clear();
                            client.closed = true;
                            break;
                        }
                    }
                    Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => break,
                    Err(error) => return Err(error),
                }
            }

            while let Some(newline_idx) = client.buffer.iter().position(|byte| *byte == b'\n') {
                let raw = client.buffer.drain(..=newline_idx).collect::<Vec<_>>();
                let line = raw
                    .into_iter()
                    .filter(|byte| *byte != b'\n' && *byte != b'\r')
                    .collect::<Vec<_>>();
                if line.is_empty() {
                    continue;
                }
                Self::decode_request(client.id, &line, requests);
            }

            if client.closed && !client.buffer.is_empty() {
                let trailing = std::mem::take(&mut client.buffer);
                let start = trailing
                    .iter()
                    .position(|byte| !byte.is_ascii_whitespace())
                    .unwrap_or(trailing.len());
                let end = trailing
                    .iter()
                    .rposition(|byte| !byte.is_ascii_whitespace())
                    .map_or(0, |idx| idx + 1);
                let trimmed = if start >= end {
                    Vec::new()
                } else {
                    trailing[start..end].to_vec()
                };
                if !trimmed.is_empty() {
                    Self::decode_request(client.id, &trimmed, requests);
                }
            }

            Ok(())
        }

        fn decode_request(client_id: u64, line: &[u8], requests: &mut Vec<RemoteRequest>) {
            match serde_json::from_slice::<RawRequest>(line) {
                Ok(request) => {
                    if request.jsonrpc.as_deref().is_some_and(|version| version != "2.0") {
                        return;
                    }
                    requests.push(RemoteRequest {
                        client_id,
                        id: request.id,
                        method: request.method,
                        params: request.params,
                    });
                }
                Err(error) => {
                    warn!("ignoring malformed remote-control JSON payload: {error}");
                }
            }
        }
    }

    impl Drop for RemoteControlServer {
        fn drop(&mut self) {
            if self.socket_path.exists() {
                let _ = fs::remove_file(&self.socket_path);
            }
        }
    }

    fn default_socket_path() -> PathBuf {
        let pid = std::process::id();
        let base = std::env::var_os("XDG_RUNTIME_DIR")
            .map(PathBuf::from)
            .or_else(|| std::env::var_os("TMPDIR").map(PathBuf::from))
            .unwrap_or_else(std::env::temp_dir);
        base.join(format!("walk-{pid}.sock"))
    }

    /// Platform-specific remote-control server implementation.
    pub type PlatformServer = RemoteControlServer;
}

#[cfg(not(unix))]
mod imp {
    use super::*;

    /// Placeholder remote-control server for unsupported platforms.
    pub struct PlatformServer;

    impl PlatformServer {
        /// Return an unsupported-platform error.
        pub fn bind_default() -> Result<Self, std::io::Error> {
            Err(std::io::Error::new(
                std::io::ErrorKind::Unsupported,
                "remote control is currently supported on Unix only",
            ))
        }

        /// Unused placeholder.
        pub fn socket_path(&self) -> &Path {
            Path::new("")
        }

        /// Unused placeholder.
        pub fn poll_requests(&mut self) -> Vec<RemoteRequest> {
            Vec::new()
        }

        /// Unused placeholder.
        pub fn send_response(&mut self, _client_id: u64, _payload: &Value) {}
    }
}

pub use imp::PlatformServer as RemoteControlServer;

/// Build a successful JSON-RPC response.
pub fn result_response(id: Option<Value>, result: Value) -> Value {
    json!({
        "jsonrpc": "2.0",
        "result": result,
        "id": id.unwrap_or(Value::Null)
    })
}

/// Build an error JSON-RPC response.
pub fn error_response(id: Option<Value>, code: i64, message: impl Into<String>) -> Value {
    json!({
        "jsonrpc": "2.0",
        "error": {
            "code": code,
            "message": message.into()
        },
        "id": id.unwrap_or(Value::Null)
    })
}
