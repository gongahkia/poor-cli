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
use std::sync::mpsc::{self, Receiver, SyncSender};
use std::sync::{Arc, Mutex};
use std::thread;

mod commands;
pub use commands::RpcCommand;
mod worker;
pub use worker::run_rpc_worker;
mod client_methods;

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
    pub ready: bool,
    #[serde(default)]
    pub status_label: String,
    #[serde(default)]
    pub models: Vec<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct StartupState {
    pub provider: String,
    pub model: String,
}

// ── Server notification types ────────────────────────────────────────

#[derive(Debug, Clone)]
pub enum ServerNotification {
    ThinkingChunk {
        request_id: String,
        chunk: String,
    },
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
    PlanRequest {
        request_id: String,
        prompt_id: String,
        summary: String,
        original_request: String,
        steps: Vec<String>,
    },
    Progress {
        request_id: String,
        phase: String,
        message: String,
        iteration_index: u32,
        iteration_cap: u32,
        nodes: Vec<(String, Vec<String>)>,
    },
    CostUpdate {
        request_id: String,
        input_tokens: u64,
        output_tokens: u64,
        estimated_cost: f64,
        system_tokens: u64,
        history_tokens: u64,
        tool_result_tokens: u64,
    },
    ContextPressure {
        request_id: String,
        used_tokens: u64,
        max_tokens: u64,
        pressure_pct: f32,
    },
    RoomEvent {
        room: String,
        mode: String,
        event_type: String,
        request_id: String,
        actor: String,
        queue_depth: u64,
        member_count: u64,
        active_connection_id: String,
        lobby_enabled: bool,
        preset: String,
        agenda_summary: Value,
        members: Value,
        details: Value,
    },
    MemberRoleUpdated {
        room: String,
        connection_id: String,
        role: String,
        ui_role: String,
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
    use_async: bool, // true when reader thread handles responses (spawn_with_notifications path)
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
        "poor-cli/thinkingChunk" => Some(ServerNotification::ThinkingChunk {
            request_id: params
                .get("requestId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            chunk: params
                .get("chunk")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        }),
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
        "poor-cli/planReq" => Some(ServerNotification::PlanRequest {
            request_id: params
                .get("requestId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            prompt_id: params
                .get("promptId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            summary: params
                .get("summary")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            original_request: params
                .get("originalRequest")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            steps: params
                .get("steps")
                .and_then(|v| v.as_array())
                .map(|items| {
                    items
                        .iter()
                        .filter_map(|item| item.as_str().map(|value| value.to_string()))
                        .collect()
                })
                .unwrap_or_default(),
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
            nodes: params
                .get("nodes")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|item| {
                            let name = item.get("name")?.as_str()?.to_string();
                            let children = item
                                .get("children")
                                .and_then(|c| c.as_array())
                                .map(|ca| {
                                    ca.iter()
                                        .filter_map(|s| s.as_str().map(|s| s.to_string()))
                                        .collect()
                                })
                                .unwrap_or_default();
                            Some((name, children))
                        })
                        .collect()
                })
                .unwrap_or_default(),
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
            system_tokens: params.get("systemTokens").and_then(|v| v.as_u64()).unwrap_or(0),
            history_tokens: params.get("historyTokens").and_then(|v| v.as_u64()).unwrap_or(0),
            tool_result_tokens: params.get("toolResultTokens").and_then(|v| v.as_u64()).unwrap_or(0),
        }),
        "poor-cli/contextPressure" => Some(ServerNotification::ContextPressure {
            request_id: params.get("requestId").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            used_tokens: params.get("usedTokens").and_then(|v| v.as_u64()).unwrap_or(0),
            max_tokens: params.get("maxTokens").and_then(|v| v.as_u64()).unwrap_or(0),
            pressure_pct: params.get("pressurePct").and_then(|v| v.as_f64()).unwrap_or(0.0) as f32,
        }),
        "poor-cli/roomEvent" => Some(ServerNotification::RoomEvent {
            room: params
                .get("room")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            mode: params
                .get("mode")
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
            agenda_summary: params.get("agendaSummary").cloned().unwrap_or(Value::Null),
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
            ui_role: params
                .get("uiRole")
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
            while let Ok(body_str) = read_one_message(&mut reader) {
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
        });

        Ok((
            Self {
                child: Mutex::new(child),
                next_id: AtomicU64::new(1),
                pending_requests,
                use_async: true,
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
            use_async: false,
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
        let reply_rx = self.send_request_nonblocking(method, params)?;
        reply_rx
            .recv_timeout(std::time::Duration::from_secs(120))
            .map_err(|e| format!("RPC timeout/error: {e}"))?
    }

    /// Send a JSON-RPC request without waiting for the response.
    /// Returns a receiver that will deliver the result when the backend responds.
    pub fn send_request_nonblocking(
        &self,
        method: &str,
        params: Value,
    ) -> Result<mpsc::Receiver<Result<Value, String>>, String> {
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
        Ok(reply_rx)
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
        if self.use_async {
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
}

// remaining impl RpcClient methods (initialize, chat, shutdown, etc.) are in client_methods.rs

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
            "role": "viewer",
            "uiRole": "reviewer"
        });
        let n = parse_notification("poor-cli/memberRoleUpdated", &params)
            .expect("memberRoleUpdated should parse");
        match n {
            ServerNotification::MemberRoleUpdated {
                room,
                connection_id,
                role,
                ui_role,
            } => {
                assert_eq!(room, "dev");
                assert_eq!(connection_id, "c-2");
                assert_eq!(role, "viewer");
                assert_eq!(ui_role, "reviewer");
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
            "--invite".to_string(),
            "invite-code".to_string(),
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
                "--invite",
                "invite-code",
            ]
        );
    }
}
