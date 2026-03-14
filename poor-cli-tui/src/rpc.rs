/// JSON-RPC 2.0 client communicating with the Python `poor_cli.server` over stdio.
///
/// Supports both blocking request/response calls AND asynchronous server notifications
/// (for streaming, tool events, etc.).
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{self, Receiver, Sender, SyncSender};
use std::sync::{Arc, Mutex};
use std::thread;

// ── JSON-RPC message types ───────────────────────────────────────────

#[derive(Debug, Serialize)]
struct RpcRequest {
    jsonrpc: &'static str,
    id: u64,
    method: String,
    params: serde_json::Value,
}

#[derive(Debug, Serialize)]
struct RpcNotification {
    jsonrpc: &'static str,
    method: String,
    params: serde_json::Value,
}

#[derive(Debug, Deserialize)]
pub struct RpcResponse {
    #[allow(dead_code)]
    pub jsonrpc: Option<String>,
    #[allow(dead_code)]
    pub id: Option<u64>,
    pub result: Option<serde_json::Value>,
    pub error: Option<RpcError>,
    pub method: Option<String>,
    pub params: Option<serde_json::Value>,
}

#[derive(Debug, Deserialize, Clone)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
    pub data: Option<serde_json::Value>,
}

const MAX_RPC_ERROR_CHARS: usize = 360;

fn collapse_whitespace(value: &str) -> String {
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn trim_embedded_payload(value: &str) -> String {
    for marker in [
        " {'message':",
        " {\"message\":",
        " {'error':",
        " {\"error\":",
    ] {
        if let Some(idx) = value.find(marker) {
            return value[..idx].trim().to_string();
        }
    }
    value.to_string()
}

fn collect_quoted_values(input: &str, pattern: &str, quote_char: char) -> Vec<String> {
    let mut values = Vec::new();
    let mut offset = 0usize;

    while let Some(pos) = input[offset..].find(pattern) {
        let start = offset + pos + pattern.len();
        let remainder = &input[start..];
        if let Some(end_rel) = remainder.find(quote_char) {
            let raw_value = &remainder[..end_rel];
            let cleaned = collapse_whitespace(&raw_value.replace("\\n", " ").replace("\\t", " "));
            if !cleaned.is_empty() {
                values.push(cleaned);
            }
            offset = start + end_rel + 1;
        } else {
            break;
        }
    }

    values
}

fn contains_case_insensitive(haystack: &str, needle: &str) -> bool {
    haystack.to_lowercase().contains(&needle.to_lowercase())
}

fn extract_structured_message(raw: &str) -> Option<String> {
    let mut candidates = collect_quoted_values(raw, "\"message\": \"", '"');
    candidates.extend(collect_quoted_values(raw, "'message': '", '\''));

    candidates
        .into_iter()
        .find(|value| !value.starts_with('{') && !value.contains("\"error\":"))
}

fn extract_structured_reason(raw: &str) -> Option<String> {
    let mut candidates = collect_quoted_values(raw, "\"reason\": \"", '"');
    candidates.extend(collect_quoted_values(raw, "'reason': '", '\''));
    candidates.into_iter().next()
}

fn sanitize_rpc_error_message(raw: &str) -> String {
    let compact = collapse_whitespace(
        &raw.replace("\\n", " ")
            .replace("\\t", " ")
            .replace('\n', " "),
    );
    let mut message = trim_embedded_payload(&compact);

    if let Some(extracted_message) = extract_structured_message(raw) {
        if !contains_case_insensitive(&message, &extracted_message) {
            message = format!("{message}: {extracted_message}");
        }
    }

    if let Some(reason) = extract_structured_reason(raw) {
        if !contains_case_insensitive(&message, &reason) {
            message = format!("{message} ({reason})");
        }
    }

    if message.len() > MAX_RPC_ERROR_CHARS {
        let mut shortened = message
            .chars()
            .take(MAX_RPC_ERROR_CHARS - 3)
            .collect::<String>();
        shortened.push_str("...");
        return shortened;
    }

    message
}

impl std::fmt::Display for RpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "[{}] {}",
            self.code,
            sanitize_rpc_error_message(&self.message)
        )
    }
}

fn insert_context_file_params(
    params: &mut serde_json::Map<String, Value>,
    context_files: &[String],
    pinned_context_files: &[String],
) {
    if !context_files.is_empty() {
        let files: Vec<Value> = context_files
            .iter()
            .map(|f| Value::String(f.clone()))
            .collect();
        params.insert("contextFiles".into(), Value::Array(files));
    }
    if !pinned_context_files.is_empty() {
        let files: Vec<Value> = pinned_context_files
            .iter()
            .map(|f| Value::String(f.clone()))
            .collect();
        params.insert("pinnedContextFiles".into(), Value::Array(files));
    }
}

fn insert_context_budget_param(
    params: &mut serde_json::Map<String, Value>,
    context_budget_tokens: Option<usize>,
) {
    if let Some(tokens) = context_budget_tokens {
        params.insert(
            "contextBudgetTokens".into(),
            Value::Number(serde_json::Number::from(tokens as u64)),
        );
    }
}

// ── High-level response types ────────────────────────────────────────

#[derive(Debug, Clone, Deserialize)]
pub struct InitResult {
    pub server_name: Option<String>,
    pub version: Option<String>,
    pub capabilities: Option<serde_json::Value>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ChatResult {
    pub content: Option<String>,
    pub role: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProviderInfo {
    pub name: String,
    pub available: bool,
    #[serde(default)]
    pub models: Vec<String>,
}

// ── Server notification types ────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum ServerNotification {
    StreamChunk {
        request_id: String,
        chunk: String,
        done: bool,
        reason: Option<String>,
    },
    ToolEvent {
        request_id: String,
        event_type: String,
        tool_name: String,
        tool_args: Value,
        tool_result: String,
        diff: String,
        paths: Vec<String>,
        checkpoint_id: Option<String>,
        changed: Option<bool>,
        message: String,
        iteration_index: u32,
        iteration_cap: u32,
    },
    PermissionRequest {
        request_id: String,
        tool_name: String,
        tool_args: Value,
        prompt_id: String,
        operation: String,
        paths: Vec<String>,
        diff: String,
        checkpoint_id: Option<String>,
        changed: Option<bool>,
        message: String,
    },
    Progress {
        request_id: String,
        phase: String,
        message: String,
        iteration_index: u32,
        iteration_cap: u32,
    },
    CostUpdate {
        request_id: String,
        input_tokens: u64,
        output_tokens: u64,
        estimated_cost: f64,
    },
    RoomEvent {
        room: String,
        event_type: String,
        request_id: String,
        actor: String,
        queue_depth: u64,
        member_count: u64,
        active_connection_id: String,
        lobby_enabled: bool,
        preset: String,
        members: Value,
        details: Value,
    },
    MemberRoleUpdated {
        room: String,
        connection_id: String,
        role: String,
    },
    Suggestion {
        sender: String,
        text: String,
        room: String,
    },
}

// ── RPC Client ───────────────────────────────────────────────────────

pub struct RpcClient {
    child: Mutex<Child>,
    next_id: AtomicU64,
    pending_requests: Arc<Mutex<HashMap<u64, SyncSender<Result<Value, String>>>>>,
    notification_tx: Option<Sender<ServerNotification>>,
    #[allow(dead_code)]
    reader_handle: Option<thread::JoinHandle<()>>,
    stdin_lock: Arc<Mutex<()>>, // serialize writes
}

/// Read one Content-Length framed message from a BufReader.
fn read_one_message<R: Read>(reader: &mut BufReader<R>) -> Result<String, String> {
    let mut content_length: usize = 0;
    loop {
        let mut header_line = String::new();
        reader
            .read_line(&mut header_line)
            .map_err(|e| format!("Read header error: {e}"))?;
        if header_line.is_empty() {
            return Err("EOF".into());
        }
        let trimmed = header_line.trim();
        if trimmed.is_empty() {
            break;
        }
        if let Some(val) = trimmed.strip_prefix("Content-Length:") {
            content_length = val
                .trim()
                .parse()
                .map_err(|e| format!("Invalid Content-Length: {e}"))?;
        }
    }
    if content_length == 0 {
        return Err("No Content-Length in message".into());
    }
    let mut body_buf = vec![0u8; content_length];
    reader
        .read_exact(&mut body_buf)
        .map_err(|e| format!("Read body error: {e}"))?;
    String::from_utf8(body_buf).map_err(|e| format!("UTF-8 error: {e}"))
}

/// Parse a server notification from JSON-RPC method + params.
fn parse_notification(method: &str, params: &Value) -> Option<ServerNotification> {
    match method {
        "poor-cli/streamChunk" | "poor-cli/streamingChunk" => {
            Some(ServerNotification::StreamChunk {
                request_id: params
                    .get("requestId")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string(),
                chunk: params
                    .get("chunk")
                    .and_then(|v| v.as_str())
                    .or_else(|| params.get("content").and_then(|v| v.as_str()))
                    .unwrap_or("")
                    .to_string(),
                done: params
                    .get("done")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false),
                reason: params
                    .get("reason")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string()),
            })
        }
        "poor-cli/toolEvent" => Some(ServerNotification::ToolEvent {
            request_id: params
                .get("requestId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            event_type: params
                .get("eventType")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            tool_name: params
                .get("toolName")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            tool_args: params.get("toolArgs").cloned().unwrap_or(Value::Null),
            tool_result: params
                .get("toolResult")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            diff: params
                .get("diff")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            paths: params
                .get("paths")
                .and_then(|v| v.as_array())
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|item| item.as_str().map(|value| value.to_string()))
                        .collect()
                })
                .unwrap_or_default(),
            checkpoint_id: params
                .get("checkpointId")
                .and_then(|v| v.as_str())
                .map(|value| value.to_string()),
            changed: params.get("changed").and_then(|v| v.as_bool()),
            message: params
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            iteration_index: params
                .get("iterationIndex")
                .and_then(|v| v.as_u64())
                .unwrap_or(0) as u32,
            iteration_cap: params
                .get("iterationCap")
                .and_then(|v| v.as_u64())
                .unwrap_or(25) as u32,
        }),
        "poor-cli/permissionReq" => Some(ServerNotification::PermissionRequest {
            request_id: params
                .get("requestId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            tool_name: params
                .get("toolName")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            tool_args: params.get("toolArgs").cloned().unwrap_or(Value::Null),
            prompt_id: params
                .get("promptId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            operation: params
                .get("operation")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            paths: params
                .get("paths")
                .and_then(|v| v.as_array())
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|item| item.as_str().map(|value| value.to_string()))
                        .collect()
                })
                .unwrap_or_default(),
            diff: params
                .get("diff")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            checkpoint_id: params
                .get("checkpointId")
                .and_then(|v| v.as_str())
                .map(|value| value.to_string()),
            changed: params.get("changed").and_then(|v| v.as_bool()),
            message: params
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        }),
        "poor-cli/progress" => Some(ServerNotification::Progress {
            request_id: params
                .get("requestId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            phase: params
                .get("phase")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            message: params
                .get("message")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            iteration_index: params
                .get("iterationIndex")
                .and_then(|v| v.as_u64())
                .unwrap_or(0) as u32,
            iteration_cap: params
                .get("iterationCap")
                .and_then(|v| v.as_u64())
                .unwrap_or(25) as u32,
        }),
        "poor-cli/costUpdate" => Some(ServerNotification::CostUpdate {
            request_id: params
                .get("requestId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            input_tokens: params
                .get("inputTokens")
                .and_then(|v| v.as_u64())
                .unwrap_or(0),
            output_tokens: params
                .get("outputTokens")
                .and_then(|v| v.as_u64())
                .unwrap_or(0),
            estimated_cost: params
                .get("estimatedCost")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0),
        }),
        "poor-cli/roomEvent" => Some(ServerNotification::RoomEvent {
            room: params
                .get("room")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            event_type: params
                .get("eventType")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            request_id: params
                .get("requestId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            actor: params
                .get("actor")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            queue_depth: params
                .get("queueDepth")
                .and_then(|v| v.as_u64())
                .unwrap_or(0),
            member_count: params
                .get("memberCount")
                .and_then(|v| v.as_u64())
                .unwrap_or(0),
            active_connection_id: params
                .get("activeConnectionId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            lobby_enabled: params
                .get("lobbyEnabled")
                .and_then(|v| v.as_bool())
                .unwrap_or(false),
            preset: params
                .get("preset")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            members: params.get("members").cloned().unwrap_or(Value::Null),
            details: params.get("details").cloned().unwrap_or(Value::Null),
        }),
        "poor-cli/memberRoleUpdated" => Some(ServerNotification::MemberRoleUpdated {
            room: params
                .get("room")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            connection_id: params
                .get("connectionId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            role: params
                .get("role")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        }),
        "poor-cli/suggestion" => Some(ServerNotification::Suggestion {
            sender: params
                .get("sender")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            text: params
                .get("text")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            room: params
                .get("room")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        }),
        _ => None,
    }
}

impl RpcClient {
    fn build_server_command(
        python_bin: &str,
        cwd: Option<&str>,
        server_args: &[String],
        backend_log_file: Option<&str>,
    ) -> Command {
        let mut cmd = Command::new(python_bin);
        cmd.arg("-m")
            .arg("poor_cli.server")
            .args(server_args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        if let Some(log_path) = backend_log_file {
            cmd.env("POOR_CLI_SERVER_LOG_FILE", log_path);
        }

        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        }

        cmd
    }

    /// Spawn the Python JSON-RPC server as a child process.
    /// Returns the client and a notification receiver channel.
    pub fn spawn_with_notifications(
        python_bin: &str,
        cwd: Option<&str>,
    ) -> Result<(Self, Receiver<ServerNotification>), String> {
        Self::spawn_with_notifications_args(python_bin, cwd, &[], None)
    }

    /// Spawn the Python JSON-RPC server with extra command-line arguments.
    pub fn spawn_with_notifications_args(
        python_bin: &str,
        cwd: Option<&str>,
        server_args: &[String],
        backend_log_file: Option<&str>,
    ) -> Result<(Self, Receiver<ServerNotification>), String> {
        let mut child = Self::build_server_command(python_bin, cwd, server_args, backend_log_file)
            .spawn()
            .map_err(|e| format!("Failed to start Python server: {e}"))?;

        let stdout = child.stdout.take().ok_or("No stdout handle")?;
        let pending_requests: Arc<Mutex<HashMap<u64, SyncSender<Result<Value, String>>>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let (notification_tx, notification_rx) = mpsc::channel::<ServerNotification>();

        // Spawn continuous reader thread
        let pending_clone = pending_requests.clone();
        let notif_tx = notification_tx.clone();
        let reader_handle = thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            loop {
                match read_one_message(&mut reader) {
                    Ok(body_str) => {
                        let msg: RpcResponse = match serde_json::from_str(&body_str) {
                            Ok(m) => m,
                            Err(_) => continue,
                        };

                        // Check if this is a notification (no id, has method)
                        if msg.id.is_none() {
                            if let Some(method) = &msg.method {
                                let params = msg.params.as_ref().cloned().unwrap_or(Value::Null);
                                if let Some(notif) = parse_notification(method, &params) {
                                    let _ = notif_tx.send(notif);
                                }
                            }
                            continue;
                        }

                        // It's a response — route to pending request
                        if let Some(id) = msg.id {
                            if let Ok(mut pending) = pending_clone.lock() {
                                if let Some(sender) = pending.remove(&id) {
                                    let result = if let Some(err) = msg.error {
                                        Err(err.to_string())
                                    } else {
                                        msg.result
                                            .ok_or_else(|| "No result in response".to_string())
                                    };
                                    let _ = sender.send(result);
                                }
                            }
                        }
                    }
                    Err(_) => break, // EOF or read error
                }
            }
        });

        Ok((
            Self {
                child: Mutex::new(child),
                next_id: AtomicU64::new(1),
                pending_requests,
                notification_tx: Some(notification_tx),
                reader_handle: Some(reader_handle),
                stdin_lock: Arc::new(Mutex::new(())),
            },
            notification_rx,
        ))
    }

    /// Legacy spawn without notifications (falls back to blocking call()).
    pub fn spawn(python_bin: &str, cwd: Option<&str>) -> Result<Self, String> {
        let child = Self::build_server_command(python_bin, cwd, &[], None)
            .spawn()
            .map_err(|e| format!("Failed to start Python server: {e}"))?;

        Ok(Self {
            child: Mutex::new(child),
            next_id: AtomicU64::new(1),
            pending_requests: Arc::new(Mutex::new(HashMap::new())),
            notification_tx: None,
            reader_handle: None,
            stdin_lock: Arc::new(Mutex::new(())),
        })
    }

    /// Write a Content-Length framed message to stdin.
    fn write_raw(&self, body: &str) -> Result<(), String> {
        let _lock = self.stdin_lock.lock().map_err(|e| e.to_string())?;
        let mut child = self.child.lock().map_err(|e| e.to_string())?;
        let stdin = child
            .stdin
            .as_mut()
            .ok_or("No stdin handle on child process")?;
        let header = format!("Content-Length: {}\r\n\r\n{body}", body.len());
        write!(stdin, "{header}").map_err(|e| format!("Write error: {e}"))?;
        stdin.flush().map_err(|e| format!("Flush error: {e}"))?;
        Ok(())
    }

    /// Send a request and wait for response via the reader thread.
    /// Used when spawn_with_notifications was used.
    fn call_async(&self, method: &str, params: Value) -> Result<Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let request = RpcRequest {
            jsonrpc: "2.0",
            id,
            method: method.to_string(),
            params,
        };
        let body = serde_json::to_string(&request).map_err(|e| e.to_string())?;

        let (reply_tx, reply_rx) = mpsc::sync_channel(1);
        {
            let mut pending = self.pending_requests.lock().map_err(|e| e.to_string())?;
            pending.insert(id, reply_tx);
        }

        self.write_raw(&body)?;

        reply_rx
            .recv_timeout(std::time::Duration::from_secs(120))
            .map_err(|e| format!("RPC timeout/error: {e}"))?
    }

    /// Send a JSON-RPC request and read the response (blocking, inline reader).
    /// Used when spawn() (legacy) was used.
    fn call_blocking(&self, method: &str, params: Value) -> Result<Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let request = RpcRequest {
            jsonrpc: "2.0",
            id,
            method: method.to_string(),
            params,
        };

        let mut child = self.child.lock().map_err(|e| e.to_string())?;

        let stdin = child
            .stdin
            .as_mut()
            .ok_or("No stdin handle on child process")?;
        let body = serde_json::to_string(&request).map_err(|e| e.to_string())?;
        let header = format!("Content-Length: {}\r\n\r\n{body}", body.len());
        write!(stdin, "{header}").map_err(|e| format!("Write error: {e}"))?;
        stdin.flush().map_err(|e| format!("Flush error: {e}"))?;

        let stdout = child
            .stdout
            .as_mut()
            .ok_or("No stdout handle on child process")?;
        let mut reader = BufReader::new(stdout);

        let mut content_length: usize = 0;
        loop {
            let mut header_line = String::new();
            reader
                .read_line(&mut header_line)
                .map_err(|e| format!("Read header error: {e}"))?;
            let trimmed = header_line.trim();
            if trimmed.is_empty() {
                break;
            }
            if let Some(val) = trimmed.strip_prefix("Content-Length:") {
                content_length = val
                    .trim()
                    .parse()
                    .map_err(|e| format!("Invalid Content-Length: {e}"))?;
            }
        }

        if content_length == 0 {
            return Err("No Content-Length in response".into());
        }

        let mut body_buf = vec![0u8; content_length];
        reader
            .read_exact(&mut body_buf)
            .map_err(|e| format!("Read body error: {e}"))?;
        let body_str = String::from_utf8(body_buf).map_err(|e| format!("UTF-8 error: {e}"))?;

        let resp: RpcResponse =
            serde_json::from_str(&body_str).map_err(|e| format!("Parse error: {e}: {body_str}"))?;

        if let Some(err) = resp.error {
            return Err(err.to_string());
        }

        resp.result
            .ok_or_else(|| "No result in response".to_string())
    }

    /// Unified call: routes to async or blocking based on how client was spawned.
    pub fn call(&self, method: &str, params: Value) -> Result<Value, String> {
        if self.notification_tx.is_some() {
            self.call_async(method, params)
        } else {
            self.call_blocking(method, params)
        }
    }

    /// Send a JSON-RPC notification (no id, no response expected).
    pub fn send_notification(&self, method: &str, params: Value) -> Result<(), String> {
        let notification = RpcNotification {
            jsonrpc: "2.0",
            method: method.to_string(),
            params,
        };
        let body = serde_json::to_string(&notification).map_err(|e| e.to_string())?;
        self.write_raw(&body)
    }

    /// Initialize the server with provider/model info.
    pub fn initialize(
        &self,
        provider: Option<&str>,
        model: Option<&str>,
        api_key: Option<&str>,
        permission_mode: Option<&str>,
    ) -> Result<InitResult, String> {
        let mut params = serde_json::Map::new();
        if let Some(p) = provider {
            params.insert("provider".into(), Value::String(p.into()));
        }
        if let Some(m) = model {
            params.insert("model".into(), Value::String(m.into()));
        }
        if let Some(k) = api_key {
            params.insert("apiKey".into(), Value::String(k.into()));
        }
        if let Some(pm) = permission_mode {
            params.insert("permissionMode".into(), Value::String(pm.into()));
        }
        // Enable streaming notifications
        if self.notification_tx.is_some() {
            params.insert("streaming".into(), Value::Bool(true));
        }
        let val = self.call("initialize", Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// Send a chat message (non-streaming, legacy).
    pub fn chat(
        &self,
        message: &str,
        context_files: &[String],
        pinned_context_files: &[String],
        context_budget_tokens: Option<usize>,
    ) -> Result<ChatResult, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), Value::String(message.into()));
        insert_context_file_params(&mut params, context_files, pinned_context_files);
        insert_context_budget_param(&mut params, context_budget_tokens);
        let val = self.call("chat", Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// Send a streaming chat message. Notifications arrive via the notification channel.
    /// Returns the final accumulated result.
    pub fn chat_streaming(
        &self,
        message: &str,
        request_id: &str,
        context_files: &[String],
        pinned_context_files: &[String],
        context_budget_tokens: Option<usize>,
    ) -> Result<ChatResult, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), Value::String(message.into()));
        params.insert("requestId".into(), Value::String(request_id.into()));
        insert_context_file_params(&mut params, context_files, pinned_context_files);
        insert_context_budget_param(&mut params, context_budget_tokens);
        let val = self.call("poor-cli/chatStreaming", Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    pub fn preview_context(
        &self,
        message: &str,
        context_files: &[String],
        pinned_context_files: &[String],
        context_budget_tokens: Option<usize>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), Value::String(message.into()));
        insert_context_file_params(&mut params, context_files, pinned_context_files);
        insert_context_budget_param(&mut params, context_budget_tokens);
        self.call("poor-cli/previewContext", Value::Object(params))
    }

    pub fn preview_mutation(&self, tool_name: &str, tool_args: Value) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("toolName".into(), Value::String(tool_name.to_string()));
        params.insert("toolArgs".into(), tool_args);
        self.call("poor-cli/previewMutation", Value::Object(params))
    }

    /// Cancel an in-flight request.
    pub fn cancel_request(&self) -> Result<(), String> {
        let _ = self.call("poor-cli/cancelRequest", Value::Object(Default::default()))?;
        Ok(())
    }

    /// List available providers.
    pub fn list_providers(&self) -> Result<Vec<ProviderInfo>, String> {
        let val = self.call("listProviders", Value::Object(Default::default()))?;
        if let Some(arr) = val.as_array() {
            serde_json::from_value(Value::Array(arr.clone())).map_err(|e| e.to_string())
        } else if let Some(obj) = val.as_object() {
            let list: Vec<ProviderInfo> = obj
                .iter()
                .map(|(name, info)| {
                    let available = info
                        .get("available")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);
                    let models = info
                        .get("models")
                        .and_then(|v| v.as_array())
                        .map(|arr| {
                            arr.iter()
                                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                                .collect()
                        })
                        .unwrap_or_default();
                    ProviderInfo {
                        name: name.clone(),
                        available,
                        models,
                    }
                })
                .collect();
            Ok(list)
        } else {
            Ok(vec![])
        }
    }

    /// Switch to a different provider/model.
    pub fn switch_provider(&self, provider: &str, model: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("provider".into(), Value::String(provider.into()));
        if let Some(m) = model {
            params.insert("model".into(), Value::String(m.into()));
        }
        self.call("switchProvider", Value::Object(params))
    }

    pub fn get_config(&self) -> Result<HashMap<String, Value>, String> {
        let val = self.call("getConfig", Value::Object(Default::default()))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    pub fn get_config_value(&self) -> Result<Value, String> {
        self.call("getConfig", Value::Object(Default::default()))
    }

    pub fn get_provider_info(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getProviderInfo",
            Value::Object(Default::default()),
        )
    }

    pub fn get_tools(&self) -> Result<Value, String> {
        self.call("poor-cli/getTools", Value::Object(Default::default()))
    }

    pub fn list_config_options(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/listConfigOptions",
            Value::Object(Default::default()),
        )
    }

    pub fn set_config(&self, key_path: &str, value: Value) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("keyPath".into(), Value::String(key_path.to_string()));
        params.insert("value".into(), value);
        self.call("poor-cli/setConfig", Value::Object(params))
    }

    pub fn toggle_config(&self, key_path: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("keyPath".into(), Value::String(key_path.to_string()));
        self.call("poor-cli/toggleConfig", Value::Object(params))
    }

    pub fn set_api_key(
        &self,
        provider: &str,
        api_key: &str,
        persist: bool,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("provider".into(), Value::String(provider.to_string()));
        params.insert("apiKey".into(), Value::String(api_key.to_string()));
        params.insert("persist".into(), Value::Bool(persist));
        params.insert("reloadActiveProvider".into(), Value::Bool(true));
        self.call("poor-cli/setApiKey", Value::Object(params))
    }

    pub fn get_api_key_status(&self, provider: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(name) = provider {
            params.insert("provider".into(), Value::String(name.to_string()));
        }
        self.call("poor-cli/getApiKeyStatus", Value::Object(params))
    }

    pub fn execute_command(&self, command: &str, timeout: Option<u64>) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert("command".into(), Value::String(command.to_string()));
        if let Some(timeout_secs) = timeout {
            params.insert("timeout".into(), Value::Number(timeout_secs.into()));
        }
        let val = self.call("poor-cli/executeCommand", Value::Object(params))?;
        Ok(val
            .get("output")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    pub fn start_service(
        &self,
        name: &str,
        command: Option<&str>,
        cwd: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        if let Some(command_text) = command {
            params.insert("command".into(), Value::String(command_text.to_string()));
        }
        if let Some(cwd_text) = cwd {
            params.insert("cwd".into(), Value::String(cwd_text.to_string()));
        }
        self.call("poor-cli/startService", Value::Object(params))
    }

    pub fn stop_service(&self, name: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        self.call("poor-cli/stopService", Value::Object(params))
    }

    pub fn get_service_status(&self, name: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(service_name) = name {
            params.insert("name".into(), Value::String(service_name.to_string()));
        }
        self.call("poor-cli/getServiceStatus", Value::Object(params))
    }

    pub fn get_service_logs(&self, name: &str, lines: Option<u64>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("name".into(), Value::String(name.to_string()));
        if let Some(line_count) = lines {
            params.insert("lines".into(), Value::Number(line_count.into()));
        }
        self.call("poor-cli/getServiceLogs", Value::Object(params))
    }

    pub fn read_file(
        &self,
        file_path: &str,
        start_line: Option<u64>,
        end_line: Option<u64>,
    ) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert("filePath".into(), Value::String(file_path.to_string()));
        if let Some(start) = start_line {
            params.insert("startLine".into(), Value::Number(start.into()));
        }
        if let Some(end) = end_line {
            params.insert("endLine".into(), Value::Number(end.into()));
        }
        let val = self.call("poor-cli/readFile", Value::Object(params))?;
        Ok(val
            .get("content")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    pub fn clear_history(&self) -> Result<(), String> {
        let _ = self.call("poor-cli/clearHistory", Value::Object(Default::default()))?;
        Ok(())
    }

    pub fn compact_context(&self, strategy: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("strategy".into(), Value::String(strategy.to_string()));
        self.call("poor-cli/compactContext", Value::Object(params))
    }

    pub fn list_sessions(&self, limit: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/listSessions", Value::Object(params))
    }

    pub fn list_history(&self, count: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("count".into(), Value::Number(count.into()));
        self.call("poor-cli/listHistory", Value::Object(params))
    }

    pub fn search_history(&self, term: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("term".into(), Value::String(term.to_string()));
        self.call("poor-cli/searchHistory", Value::Object(params))
    }

    pub fn list_checkpoints(&self, limit: u64) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("limit".into(), Value::Number(limit.into()));
        self.call("poor-cli/listCheckpoints", Value::Object(params))
    }

    pub fn create_checkpoint(
        &self,
        description: &str,
        operation_type: &str,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("description".into(), Value::String(description.to_string()));
        params.insert(
            "operationType".into(),
            Value::String(operation_type.to_string()),
        );
        self.call("poor-cli/createCheckpoint", Value::Object(params))
    }

    pub fn restore_checkpoint(&self, checkpoint_id: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(id) = checkpoint_id {
            params.insert("checkpointId".into(), Value::String(id.to_string()));
        }
        self.call("poor-cli/restoreCheckpoint", Value::Object(params))
    }

    pub fn compare_files(&self, file1: &str, file2: &str) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert("file1".into(), Value::String(file1.to_string()));
        params.insert("file2".into(), Value::String(file2.to_string()));
        let val = self.call("poor-cli/compareFiles", Value::Object(params))?;
        Ok(val
            .get("diff")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    pub fn export_conversation(&self, export_format: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("format".into(), Value::String(export_format.to_string()));
        self.call("poor-cli/exportConversation", Value::Object(params))
    }

    pub fn start_host_server(&self, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/startHostServer", Value::Object(params))
    }

    pub fn get_host_server_status(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getHostServerStatus",
            Value::Object(Default::default()),
        )
    }

    pub fn stop_host_server(&self) -> Result<Value, String> {
        self.call("poor-cli/stopHostServer", Value::Object(Default::default()))
    }

    pub fn list_host_members(&self, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/listHostMembers", Value::Object(params))
    }

    pub fn list_room_members(&self, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/listRoomMembers", Value::Object(params))
    }

    pub fn remove_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/removeHostMember", Value::Object(params))
    }

    pub fn kick_member(&self, connection_id: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/kickMember", Value::Object(params))
    }

    pub fn set_host_member_role(
        &self,
        connection_id: &str,
        role: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        params.insert("role".into(), Value::String(role.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/setHostMemberRole", Value::Object(params))
    }

    pub fn set_host_lobby(&self, enabled: bool, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("enabled".into(), Value::Bool(enabled));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/setHostLobby", Value::Object(params))
    }

    pub fn approve_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/approveHostMember", Value::Object(params))
    }

    pub fn deny_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/denyHostMember", Value::Object(params))
    }

    pub fn rotate_host_token(
        &self,
        role: &str,
        room: Option<&str>,
        expires_in_seconds: Option<u64>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("role".into(), Value::String(role.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        if let Some(expires) = expires_in_seconds {
            params.insert("expiresInSeconds".into(), Value::Number(expires.into()));
        }
        self.call("poor-cli/rotateHostToken", Value::Object(params))
    }

    pub fn revoke_host_token(&self, value: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("value".into(), Value::String(value.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/revokeHostToken", Value::Object(params))
    }

    pub fn handoff_host_member(
        &self,
        connection_id: &str,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "connectionId".into(),
            Value::String(connection_id.to_string()),
        );
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/handoffHostMember", Value::Object(params))
    }

    pub fn set_host_preset(&self, preset: &str, room: Option<&str>) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("preset".into(), Value::String(preset.to_string()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/setHostPreset", Value::Object(params))
    }

    pub fn list_host_activity(
        &self,
        room: Option<&str>,
        limit: u64,
        event_type: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("limit".into(), Value::Number(limit.into()));
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        if let Some(event_name) = event_type {
            params.insert("eventType".into(), Value::String(event_name.to_string()));
        }
        self.call("poor-cli/listHostActivity", Value::Object(params))
    }

    pub fn pair_start(&self, lobby: bool) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if lobby {
            params.insert("lobby".into(), Value::Bool(true));
        }
        self.call("poor-cli/pairStart", Value::Object(params))
    }

    pub fn suggest_text(&self, text: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert("text".into(), Value::String(text.to_string()));
        self.call("poor-cli/suggestText", Value::Object(params))
    }

    pub fn pass_driver(
        &self,
        display_name: Option<&str>,
        connection_id: Option<&str>,
        room: Option<&str>,
    ) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        if let Some(name) = display_name {
            params.insert("displayName".into(), Value::String(name.to_string()));
        }
        if let Some(cid) = connection_id {
            params.insert("connectionId".into(), Value::String(cid.to_string()));
        }
        if let Some(room_name) = room {
            params.insert("room".into(), Value::String(room_name.to_string()));
        }
        self.call("poor-cli/passDriver", Value::Object(params))
    }

    pub fn shutdown(&self) -> Result<(), String> {
        let _ = self.call("shutdown", Value::Object(Default::default()));
        if let Ok(mut child) = self.child.lock() {
            let _ = child.kill();
        }
        Ok(())
    }
}

impl Drop for RpcClient {
    fn drop(&mut self) {
        let _ = self.shutdown();
    }
}

// ── RPC worker pattern ───────────────────────────────────────────────

pub enum RpcCommand {
    Chat {
        message: String,
        context_files: Vec<String>,
        pinned_context_files: Vec<String>,
        context_budget_tokens: Option<usize>,
        reply: SyncSender<Result<String, String>>,
    },
    ChatStreaming {
        message: String,
        request_id: String,
        context_files: Vec<String>,
        pinned_context_files: Vec<String>,
        context_budget_tokens: Option<usize>,
        reply: SyncSender<Result<String, String>>,
    },
    PreviewContext {
        message: String,
        context_files: Vec<String>,
        pinned_context_files: Vec<String>,
        context_budget_tokens: Option<usize>,
        reply: SyncSender<Result<Value, String>>,
    },
    PreviewMutation {
        tool_name: String,
        tool_args: Value,
        reply: SyncSender<Result<Value, String>>,
    },
    CancelRequest,
    SendNotification {
        method: String,
        params: Value,
    },
    ExecuteCommand {
        command: String,
        timeout: Option<u64>,
        reply: SyncSender<Result<String, String>>,
    },
    ReadFile {
        file_path: String,
        start_line: Option<u64>,
        end_line: Option<u64>,
        reply: SyncSender<Result<String, String>>,
    },
    GetConfig {
        reply: SyncSender<Result<Value, String>>,
    },
    GetProviderInfo {
        reply: SyncSender<Result<Value, String>>,
    },
    GetTools {
        reply: SyncSender<Result<Value, String>>,
    },
    ListConfigOptions {
        reply: SyncSender<Result<Value, String>>,
    },
    SetConfig {
        key_path: String,
        value: Value,
        reply: SyncSender<Result<Value, String>>,
    },
    ToggleConfig {
        key_path: String,
        reply: SyncSender<Result<Value, String>>,
    },
    SetApiKey {
        provider: String,
        api_key: String,
        persist: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    GetApiKeyStatus {
        provider: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ClearHistory {
        reply: SyncSender<Result<(), String>>,
    },
    CompactContext {
        strategy: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListSessions {
        limit: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    ListHistory {
        count: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    SearchHistory {
        term: String,
        reply: SyncSender<Result<Value, String>>,
    },
    ListCheckpoints {
        limit: u64,
        reply: SyncSender<Result<Value, String>>,
    },
    CreateCheckpoint {
        description: String,
        operation_type: String,
        reply: SyncSender<Result<Value, String>>,
    },
    RestoreCheckpoint {
        checkpoint_id: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    CompareFiles {
        file1: String,
        file2: String,
        reply: SyncSender<Result<String, String>>,
    },
    ExportConversation {
        format: String,
        reply: SyncSender<Result<Value, String>>,
    },
    StartHostServer {
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    GetHostServerStatus {
        reply: SyncSender<Result<Value, String>>,
    },
    StopHostServer {
        reply: SyncSender<Result<Value, String>>,
    },
    ListHostMembers {
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListRoomMembers {
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    RemoveHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    KickMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    SetHostMemberRole {
        connection_id: String,
        role: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    SetHostLobby {
        enabled: bool,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ApproveHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    DenyHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    RotateHostToken {
        role: String,
        room: Option<String>,
        expires_in_seconds: Option<u64>,
        reply: SyncSender<Result<Value, String>>,
    },
    RevokeHostToken {
        value: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    HandoffHostMember {
        connection_id: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    SetHostPreset {
        preset: String,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListHostActivity {
        room: Option<String>,
        limit: u64,
        event_type: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    StartService {
        name: String,
        command: Option<String>,
        cwd: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    StopService {
        name: String,
        reply: SyncSender<Result<Value, String>>,
    },
    GetServiceStatus {
        name: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    GetServiceLogs {
        name: String,
        lines: Option<u64>,
        reply: SyncSender<Result<Value, String>>,
    },
    ListProviders {
        reply: SyncSender<Result<Vec<ProviderInfo>, String>>,
    },
    SwitchProvider {
        provider: String,
        model: Option<String>,
        reply: SyncSender<Result<(String, String), String>>,
    },
    PairStart {
        lobby: bool,
        reply: SyncSender<Result<Value, String>>,
    },
    SuggestText {
        text: String,
        reply: SyncSender<Result<Value, String>>,
    },
    PassDriver {
        display_name: Option<String>,
        connection_id: Option<String>,
        room: Option<String>,
        reply: SyncSender<Result<Value, String>>,
    },
    Shutdown,
}

/// Blocks the calling thread, dispatching RPC commands until Shutdown or channel drop.
pub fn run_rpc_worker(client: RpcClient, rx: Receiver<RpcCommand>) {
    loop {
        match rx.recv() {
            Ok(RpcCommand::Chat {
                message,
                context_files,
                pinned_context_files,
                context_budget_tokens,
                reply,
            }) => {
                let result = client
                    .chat(
                        &message,
                        &context_files,
                        &pinned_context_files,
                        context_budget_tokens,
                    )
                    .map(|r| r.content.unwrap_or_default());
                let _ = reply.send(result);
            }
            Ok(RpcCommand::ChatStreaming {
                message,
                request_id,
                context_files,
                pinned_context_files,
                context_budget_tokens,
                reply,
            }) => {
                let result = client
                    .chat_streaming(
                        &message,
                        &request_id,
                        &context_files,
                        &pinned_context_files,
                        context_budget_tokens,
                    )
                    .map(|r| r.content.unwrap_or_default());
                let _ = reply.send(result);
            }
            Ok(RpcCommand::PreviewContext {
                message,
                context_files,
                pinned_context_files,
                context_budget_tokens,
                reply,
            }) => {
                let _ = reply.send(client.preview_context(
                    &message,
                    &context_files,
                    &pinned_context_files,
                    context_budget_tokens,
                ));
            }
            Ok(RpcCommand::PreviewMutation {
                tool_name,
                tool_args,
                reply,
            }) => {
                let _ = reply.send(client.preview_mutation(&tool_name, tool_args));
            }
            Ok(RpcCommand::CancelRequest) => {
                let _ = client.cancel_request();
            }
            Ok(RpcCommand::SendNotification { method, params }) => {
                let _ = client.send_notification(&method, params);
            }
            Ok(RpcCommand::ExecuteCommand {
                command,
                timeout,
                reply,
            }) => {
                let _ = reply.send(client.execute_command(&command, timeout));
            }
            Ok(RpcCommand::ReadFile {
                file_path,
                start_line,
                end_line,
                reply,
            }) => {
                let _ = reply.send(client.read_file(&file_path, start_line, end_line));
            }
            Ok(RpcCommand::GetConfig { reply }) => {
                let _ = reply.send(client.get_config_value());
            }
            Ok(RpcCommand::GetProviderInfo { reply }) => {
                let _ = reply.send(client.get_provider_info());
            }
            Ok(RpcCommand::GetTools { reply }) => {
                let _ = reply.send(client.get_tools());
            }
            Ok(RpcCommand::ListConfigOptions { reply }) => {
                let _ = reply.send(client.list_config_options());
            }
            Ok(RpcCommand::SetConfig {
                key_path,
                value,
                reply,
            }) => {
                let _ = reply.send(client.set_config(&key_path, value));
            }
            Ok(RpcCommand::ToggleConfig { key_path, reply }) => {
                let _ = reply.send(client.toggle_config(&key_path));
            }
            Ok(RpcCommand::SetApiKey {
                provider,
                api_key,
                persist,
                reply,
            }) => {
                let _ = reply.send(client.set_api_key(&provider, &api_key, persist));
            }
            Ok(RpcCommand::GetApiKeyStatus { provider, reply }) => {
                let _ = reply.send(client.get_api_key_status(provider.as_deref()));
            }
            Ok(RpcCommand::ClearHistory { reply }) => {
                let _ = reply.send(client.clear_history());
            }
            Ok(RpcCommand::CompactContext { strategy, reply }) => {
                let _ = reply.send(client.compact_context(&strategy));
            }
            Ok(RpcCommand::ListSessions { limit, reply }) => {
                let _ = reply.send(client.list_sessions(limit));
            }
            Ok(RpcCommand::ListHistory { count, reply }) => {
                let _ = reply.send(client.list_history(count));
            }
            Ok(RpcCommand::SearchHistory { term, reply }) => {
                let _ = reply.send(client.search_history(&term));
            }
            Ok(RpcCommand::ListCheckpoints { limit, reply }) => {
                let _ = reply.send(client.list_checkpoints(limit));
            }
            Ok(RpcCommand::CreateCheckpoint {
                description,
                operation_type,
                reply,
            }) => {
                let _ = reply.send(client.create_checkpoint(&description, &operation_type));
            }
            Ok(RpcCommand::RestoreCheckpoint {
                checkpoint_id,
                reply,
            }) => {
                let _ = reply.send(client.restore_checkpoint(checkpoint_id.as_deref()));
            }
            Ok(RpcCommand::CompareFiles {
                file1,
                file2,
                reply,
            }) => {
                let _ = reply.send(client.compare_files(&file1, &file2));
            }
            Ok(RpcCommand::ExportConversation { format, reply }) => {
                let _ = reply.send(client.export_conversation(&format));
            }
            Ok(RpcCommand::StartHostServer { room, reply }) => {
                let _ = reply.send(client.start_host_server(room.as_deref()));
            }
            Ok(RpcCommand::GetHostServerStatus { reply }) => {
                let _ = reply.send(client.get_host_server_status());
            }
            Ok(RpcCommand::StopHostServer { reply }) => {
                let _ = reply.send(client.stop_host_server());
            }
            Ok(RpcCommand::ListHostMembers { room, reply }) => {
                let _ = reply.send(client.list_host_members(room.as_deref()));
            }
            Ok(RpcCommand::ListRoomMembers { room, reply }) => {
                let _ = reply.send(client.list_room_members(room.as_deref()));
            }
            Ok(RpcCommand::RemoveHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.remove_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::KickMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.kick_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::SetHostMemberRole {
                connection_id,
                role,
                room,
                reply,
            }) => {
                let _ =
                    reply.send(client.set_host_member_role(&connection_id, &role, room.as_deref()));
            }
            Ok(RpcCommand::SetHostLobby {
                enabled,
                room,
                reply,
            }) => {
                let _ = reply.send(client.set_host_lobby(enabled, room.as_deref()));
            }
            Ok(RpcCommand::ApproveHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.approve_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::DenyHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.deny_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::RotateHostToken {
                role,
                room,
                expires_in_seconds,
                reply,
            }) => {
                let _ = reply.send(client.rotate_host_token(
                    &role,
                    room.as_deref(),
                    expires_in_seconds,
                ));
            }
            Ok(RpcCommand::RevokeHostToken { value, room, reply }) => {
                let _ = reply.send(client.revoke_host_token(&value, room.as_deref()));
            }
            Ok(RpcCommand::HandoffHostMember {
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.handoff_host_member(&connection_id, room.as_deref()));
            }
            Ok(RpcCommand::SetHostPreset {
                preset,
                room,
                reply,
            }) => {
                let _ = reply.send(client.set_host_preset(&preset, room.as_deref()));
            }
            Ok(RpcCommand::ListHostActivity {
                room,
                limit,
                event_type,
                reply,
            }) => {
                let _ = reply.send(client.list_host_activity(
                    room.as_deref(),
                    limit,
                    event_type.as_deref(),
                ));
            }
            Ok(RpcCommand::StartService {
                name,
                command,
                cwd,
                reply,
            }) => {
                let _ = reply.send(client.start_service(&name, command.as_deref(), cwd.as_deref()));
            }
            Ok(RpcCommand::StopService { name, reply }) => {
                let _ = reply.send(client.stop_service(&name));
            }
            Ok(RpcCommand::GetServiceStatus { name, reply }) => {
                let _ = reply.send(client.get_service_status(name.as_deref()));
            }
            Ok(RpcCommand::GetServiceLogs { name, lines, reply }) => {
                let _ = reply.send(client.get_service_logs(&name, lines));
            }
            Ok(RpcCommand::ListProviders { reply }) => {
                let _ = reply.send(client.list_providers());
            }
            Ok(RpcCommand::SwitchProvider {
                provider,
                model,
                reply,
            }) => {
                let p_clone = provider.clone();
                let m_clone = model.clone();
                let result = client
                    .switch_provider(&provider, model.as_deref())
                    .map(|val| {
                        let prov = val
                            .pointer("/provider/name")
                            .and_then(|v| v.as_str())
                            .unwrap_or(&p_clone)
                            .to_string();
                        let mdl = val
                            .pointer("/provider/model")
                            .and_then(|v| v.as_str())
                            .unwrap_or(m_clone.as_deref().unwrap_or("default"))
                            .to_string();
                        (prov, mdl)
                    });
                let _ = reply.send(result);
            }
            Ok(RpcCommand::PairStart { lobby, reply }) => {
                let _ = reply.send(client.pair_start(lobby));
            }
            Ok(RpcCommand::SuggestText { text, reply }) => {
                let _ = reply.send(client.suggest_text(&text));
            }
            Ok(RpcCommand::PassDriver {
                display_name,
                connection_id,
                room,
                reply,
            }) => {
                let _ = reply.send(client.pass_driver(
                    display_name.as_deref(),
                    connection_id.as_deref(),
                    room.as_deref(),
                ));
            }
            Ok(RpcCommand::Shutdown) | Err(_) => break,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn insert_context_file_params_serializes_explicit_and_pinned_files() {
        let mut params = serde_json::Map::new();
        insert_context_file_params(
            &mut params,
            &[String::from("/tmp/main.rs")],
            &[String::from("/tmp/README.md")],
        );

        assert_eq!(params.get("contextFiles"), Some(&json!(["/tmp/main.rs"])));
        assert_eq!(
            params.get("pinnedContextFiles"),
            Some(&json!(["/tmp/README.md"]))
        );
    }

    #[test]
    fn insert_context_budget_param_serializes_optional_budget() {
        let mut params = serde_json::Map::new();
        insert_context_budget_param(&mut params, Some(6000));

        assert_eq!(params.get("contextBudgetTokens"), Some(&json!(6000)));
    }

    #[test]
    fn parse_stream_chunk_notification() {
        let params = json!({"requestId": "r1", "chunk": "hello", "done": false});
        let n = parse_notification("poor-cli/streamChunk", &params)
            .expect("streamChunk notification should parse");
        match n {
            ServerNotification::StreamChunk {
                request_id,
                chunk,
                done,
                reason,
            } => {
                assert_eq!(request_id, "r1");
                assert_eq!(chunk, "hello");
                assert!(!done);
                assert!(reason.is_none());
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_streaming_chunk_notification() {
        let params = json!({"requestId": "r9", "content": "partial", "done": false});
        let n = parse_notification("poor-cli/streamingChunk", &params)
            .expect("streamingChunk notification should parse");
        match n {
            ServerNotification::StreamChunk {
                request_id,
                chunk,
                done,
                ..
            } => {
                assert_eq!(request_id, "r9");
                assert_eq!(chunk, "partial");
                assert!(!done);
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_stream_chunk_done() {
        let params = json!({"requestId": "r1", "chunk": "", "done": true, "reason": "complete"});
        let n = parse_notification("poor-cli/streamChunk", &params)
            .expect("streamChunk done notification should parse");
        match n {
            ServerNotification::StreamChunk { done, reason, .. } => {
                assert!(done);
                assert_eq!(reason.as_deref(), Some("complete"));
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_tool_event_with_diff() {
        let params = json!({
            "requestId": "r1", "eventType": "tool_result",
            "toolName": "edit_file", "toolArgs": {"path": "x"},
            "toolResult": "ok", "diff": "--- a\n+++ b",
            "paths": ["/tmp/x"], "checkpointId": "cp_123", "changed": true,
            "iterationIndex": 2, "iterationCap": 10,
        });
        let n = parse_notification("poor-cli/toolEvent", &params).expect("toolEvent should parse");
        match n {
            ServerNotification::ToolEvent {
                diff,
                paths,
                checkpoint_id,
                changed,
                iteration_index,
                iteration_cap,
                ..
            } => {
                assert_eq!(diff, "--- a\n+++ b");
                assert_eq!(paths, vec!["/tmp/x".to_string()]);
                assert_eq!(checkpoint_id.as_deref(), Some("cp_123"));
                assert_eq!(changed, Some(true));
                assert_eq!(iteration_index, 2);
                assert_eq!(iteration_cap, 10);
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_permission_request() {
        let params = json!({
            "requestId": "r1",
            "toolName": "bash",
            "toolArgs": {"cmd": "ls"},
            "promptId": "p1",
            "operation": "bash",
            "paths": ["/tmp/x"],
            "diff": "--- a\n+++ b",
            "checkpointId": "cp_123",
            "changed": true,
            "message": "Preview ready"
        });
        let n = parse_notification("poor-cli/permissionReq", &params)
            .expect("permissionReq should parse");
        match n {
            ServerNotification::PermissionRequest {
                prompt_id,
                tool_name,
                paths,
                checkpoint_id,
                changed,
                ..
            } => {
                assert_eq!(prompt_id, "p1");
                assert_eq!(tool_name, "bash");
                assert_eq!(paths, vec!["/tmp/x".to_string()]);
                assert_eq!(checkpoint_id.as_deref(), Some("cp_123"));
                assert_eq!(changed, Some(true));
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_progress() {
        let params = json!({"requestId": "r1", "phase": "thinking", "message": "analyzing", "iterationIndex": 3, "iterationCap": 25});
        let n = parse_notification("poor-cli/progress", &params).expect("progress should parse");
        match n {
            ServerNotification::Progress {
                phase,
                iteration_index,
                ..
            } => {
                assert_eq!(phase, "thinking");
                assert_eq!(iteration_index, 3);
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_cost_update() {
        let params = json!({"requestId": "r1", "inputTokens": 500, "outputTokens": 200, "estimatedCost": 0.05});
        let n =
            parse_notification("poor-cli/costUpdate", &params).expect("costUpdate should parse");
        match n {
            ServerNotification::CostUpdate {
                input_tokens,
                output_tokens,
                estimated_cost,
                ..
            } => {
                assert_eq!(input_tokens, 500);
                assert_eq!(output_tokens, 200);
                assert!((estimated_cost - 0.05).abs() < 1e-10);
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_room_event_notification() {
        let params = json!({
            "room": "dev",
            "eventType": "member_joined",
            "actor": "c-1",
            "requestId": "req-1",
            "queueDepth": 2,
            "memberCount": 3,
            "activeConnectionId": "c-1",
            "lobbyEnabled": true,
            "preset": "review",
            "members": [{"connectionId": "c-1", "role": "prompter"}]
        });
        let n = parse_notification("poor-cli/roomEvent", &params).expect("roomEvent should parse");
        match n {
            ServerNotification::RoomEvent {
                room,
                event_type,
                queue_depth,
                member_count,
                lobby_enabled,
                preset,
                ..
            } => {
                assert_eq!(room, "dev");
                assert_eq!(event_type, "member_joined");
                assert_eq!(queue_depth, 2);
                assert_eq!(member_count, 3);
                assert!(lobby_enabled);
                assert_eq!(preset, "review");
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_member_role_updated_notification() {
        let params = json!({
            "room": "dev",
            "connectionId": "c-2",
            "role": "viewer"
        });
        let n = parse_notification("poor-cli/memberRoleUpdated", &params)
            .expect("memberRoleUpdated should parse");
        match n {
            ServerNotification::MemberRoleUpdated {
                room,
                connection_id,
                role,
            } => {
                assert_eq!(room, "dev");
                assert_eq!(connection_id, "c-2");
                assert_eq!(role, "viewer");
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn parse_unknown_notification_returns_none() {
        let params = json!({});
        assert!(parse_notification("poor-cli/unknown", &params).is_none());
    }

    #[test]
    fn parse_notification_missing_fields_uses_defaults() {
        let params = json!({});
        let n = parse_notification("poor-cli/streamChunk", &params)
            .expect("defaulted streamChunk should parse");
        match n {
            ServerNotification::StreamChunk {
                request_id,
                chunk,
                done,
                ..
            } => {
                assert_eq!(request_id, "");
                assert_eq!(chunk, "");
                assert!(!done);
            }
            _ => panic!("wrong variant"),
        }
    }

    #[test]
    fn read_one_message_valid() {
        let body = r#"{"jsonrpc":"2.0","id":1,"result":"ok"}"#;
        let framed = format!("Content-Length: {}\r\n\r\n{}", body.len(), body);
        let mut reader = std::io::BufReader::new(framed.as_bytes());
        let result = read_one_message(&mut reader).expect("framed JSON-RPC payload should parse");
        assert_eq!(result, body);
    }

    #[test]
    fn sanitize_rpc_error_message_extracts_structured_details() {
        let raw = "Failed to send message: Gemini API error: 400 Bad Request. {'message': '{\\n  \"error\": {\\n    \"code\": 400,\\n    \"message\": \"API key not valid. Please pass a valid API key.\",\\n    \"details\": [{\"reason\": \"API_KEY_INVALID\"}]\\n  }\\n}', 'status': 'Bad Request'}";

        let cleaned = sanitize_rpc_error_message(raw);

        assert!(cleaned.contains("Failed to send message: Gemini API error: 400 Bad Request."));
        assert!(cleaned.contains("API key not valid. Please pass a valid API key."));
        assert!(cleaned.contains("API_KEY_INVALID"));
        assert!(!cleaned.contains("{'message':"));
    }

    #[test]
    fn sanitize_rpc_error_message_truncates_long_values() {
        let cleaned = sanitize_rpc_error_message(&"x".repeat(800));
        assert!(cleaned.len() <= 360);
        assert!(cleaned.ends_with("..."));
    }

    #[test]
    fn build_server_command_includes_extra_args() {
        let args = vec![
            "--bridge".to_string(),
            "--url".to_string(),
            "wss://example.test/rpc".to_string(),
            "--room".to_string(),
            "dev".to_string(),
            "--token".to_string(),
            "tok".to_string(),
        ];
        let cmd = RpcClient::build_server_command("python3", Some("/tmp"), &args, None);
        let collected = cmd
            .get_args()
            .map(|v| v.to_string_lossy().to_string())
            .collect::<Vec<_>>();
        assert_eq!(
            collected,
            vec![
                "-m",
                "poor_cli.server",
                "--bridge",
                "--url",
                "wss://example.test/rpc",
                "--room",
                "dev",
                "--token",
                "tok",
            ]
        );
    }
}
