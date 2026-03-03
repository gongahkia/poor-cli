/// JSON-RPC 2.0 client communicating with the Python `poor_cli.server` over stdio.
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Read, Write};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{Receiver, SyncSender};
use std::sync::Mutex;

// ── JSON-RPC message types ───────────────────────────────────────────

#[derive(Debug, Serialize)]
struct RpcRequest {
    jsonrpc: &'static str,
    id: u64,
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
}

#[derive(Debug, Deserialize, Clone)]
pub struct RpcError {
    pub code: i64,
    pub message: String,
    pub data: Option<serde_json::Value>,
}

impl std::fmt::Display for RpcError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "[{}] {}", self.code, self.message)
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

// ── RPC Client ───────────────────────────────────────────────────────

pub struct RpcClient {
    child: Mutex<Child>,
    next_id: AtomicU64,
}

impl RpcClient {
    /// Spawn the Python JSON-RPC server as a child process.
    pub fn spawn(python_bin: &str, cwd: Option<&str>) -> Result<Self, String> {
        let mut cmd = Command::new(python_bin);
        cmd.arg("-m")
            .arg("poor_cli.server")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());

        if let Some(dir) = cwd {
            cmd.current_dir(dir);
        }

        let child = cmd
            .spawn()
            .map_err(|e| format!("Failed to start Python server: {e}"))?;

        Ok(Self {
            child: Mutex::new(child),
            next_id: AtomicU64::new(1),
        })
    }

    /// Send a JSON-RPC request and read the response (blocking).
    ///
    /// Uses LSP-style `Content-Length` header framing to match the Python server.
    pub fn call(
        &self,
        method: &str,
        params: serde_json::Value,
    ) -> Result<serde_json::Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::SeqCst);
        let request = RpcRequest {
            jsonrpc: "2.0",
            id,
            method: method.to_string(),
            params,
        };

        let mut child = self.child.lock().map_err(|e| e.to_string())?;

        // Write request with Content-Length header
        let stdin = child
            .stdin
            .as_mut()
            .ok_or("No stdin handle on child process")?;
        let body = serde_json::to_string(&request).map_err(|e| e.to_string())?;
        let header = format!("Content-Length: {}\r\n\r\n{body}", body.len());
        write!(stdin, "{header}").map_err(|e| format!("Write error: {e}"))?;
        stdin.flush().map_err(|e| format!("Flush error: {e}"))?;

        // Read response with Content-Length header
        let stdout = child
            .stdout
            .as_mut()
            .ok_or("No stdout handle on child process")?;
        let mut reader = BufReader::new(stdout);

        // Read headers until empty line
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

        // Read exactly content_length bytes
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
            params.insert("provider".into(), serde_json::Value::String(p.into()));
        }
        if let Some(m) = model {
            params.insert("model".into(), serde_json::Value::String(m.into()));
        }
        if let Some(k) = api_key {
            params.insert("apiKey".into(), serde_json::Value::String(k.into()));
        }
        if let Some(pm) = permission_mode {
            params.insert(
                "permissionMode".into(),
                serde_json::Value::String(pm.into()),
            );
        }
        let val = self.call("initialize", serde_json::Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// Send a chat message and get the response.
    pub fn chat(&self, message: &str, context_files: &[String]) -> Result<ChatResult, String> {
        let mut params = serde_json::Map::new();
        params.insert("message".into(), serde_json::Value::String(message.into()));
        if !context_files.is_empty() {
            let files: Vec<serde_json::Value> = context_files
                .iter()
                .map(|f| serde_json::Value::String(f.clone()))
                .collect();
            params.insert("contextFiles".into(), serde_json::Value::Array(files));
        }
        let val = self.call("chat", serde_json::Value::Object(params))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// List available providers.
    pub fn list_providers(&self) -> Result<Vec<ProviderInfo>, String> {
        let val = self.call(
            "listProviders",
            serde_json::Value::Object(Default::default()),
        )?;
        // The server may return a map or array. Handle both.
        if let Some(arr) = val.as_array() {
            serde_json::from_value(serde_json::Value::Array(arr.clone())).map_err(|e| e.to_string())
        } else if let Some(obj) = val.as_object() {
            // Convert map to vec
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
    pub fn switch_provider(
        &self,
        provider: &str,
        model: Option<&str>,
    ) -> Result<serde_json::Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "provider".into(),
            serde_json::Value::String(provider.into()),
        );
        if let Some(m) = model {
            params.insert("model".into(), serde_json::Value::String(m.into()));
        }
        self.call("switchProvider", serde_json::Value::Object(params))
    }

    /// Get current config from the server.
    pub fn get_config(&self) -> Result<HashMap<String, serde_json::Value>, String> {
        let val = self.call("getConfig", serde_json::Value::Object(Default::default()))?;
        serde_json::from_value(val).map_err(|e| e.to_string())
    }

    /// Get current config as raw JSON value.
    pub fn get_config_value(&self) -> Result<Value, String> {
        self.call("getConfig", serde_json::Value::Object(Default::default()))
    }

    /// Get current provider information.
    pub fn get_provider_info(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getProviderInfo",
            serde_json::Value::Object(Default::default()),
        )
    }

    /// Get tool declarations from server.
    pub fn get_tools(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/getTools",
            serde_json::Value::Object(Default::default()),
        )
    }

    /// List editable config options.
    pub fn list_config_options(&self) -> Result<Value, String> {
        self.call(
            "poor-cli/listConfigOptions",
            serde_json::Value::Object(Default::default()),
        )
    }

    /// Set one config value by key path.
    pub fn set_config(&self, key_path: &str, value: Value) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "keyPath".into(),
            serde_json::Value::String(key_path.to_string()),
        );
        params.insert("value".into(), value);
        self.call("poor-cli/setConfig", serde_json::Value::Object(params))
    }

    /// Toggle a boolean config value by key path.
    pub fn toggle_config(&self, key_path: &str) -> Result<Value, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "keyPath".into(),
            serde_json::Value::String(key_path.to_string()),
        );
        self.call("poor-cli/toggleConfig", serde_json::Value::Object(params))
    }

    /// Execute a shell command through the backend.
    pub fn execute_command(&self, command: &str) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "command".into(),
            serde_json::Value::String(command.to_string()),
        );
        let val = self.call("poor-cli/executeCommand", serde_json::Value::Object(params))?;
        Ok(val
            .get("output")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    /// Read a file through the backend.
    pub fn read_file(
        &self,
        file_path: &str,
        start_line: Option<u64>,
        end_line: Option<u64>,
    ) -> Result<String, String> {
        let mut params = serde_json::Map::new();
        params.insert(
            "filePath".into(),
            serde_json::Value::String(file_path.to_string()),
        );
        if let Some(start) = start_line {
            params.insert("startLine".into(), serde_json::Value::Number(start.into()));
        }
        if let Some(end) = end_line {
            params.insert("endLine".into(), serde_json::Value::Number(end.into()));
        }

        let val = self.call("poor-cli/readFile", serde_json::Value::Object(params))?;
        Ok(val
            .get("content")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .to_string())
    }

    /// Clear backend conversation history.
    pub fn clear_history(&self) -> Result<(), String> {
        let _ = self.call(
            "poor-cli/clearHistory",
            serde_json::Value::Object(Default::default()),
        )?;
        Ok(())
    }

    /// Shutdown the server.
    pub fn shutdown(&self) -> Result<(), String> {
        let _ = self.call("shutdown", serde_json::Value::Object(Default::default()));
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
        reply: SyncSender<Result<String, String>>,
    },
    ExecuteCommand {
        command: String,
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
    ClearHistory {
        reply: SyncSender<Result<(), String>>,
    },
    ListProviders {
        reply: SyncSender<Result<Vec<ProviderInfo>, String>>,
    },
    SwitchProvider {
        provider: String,
        model: Option<String>,
        reply: SyncSender<Result<(String, String), String>>,
    },
    Shutdown,
}

/// Blocks the calling thread, dispatching RPC commands until Shutdown or channel drop.
pub fn run_rpc_worker(client: RpcClient, rx: Receiver<RpcCommand>) {
    loop {
        match rx.recv() {
            Ok(RpcCommand::Chat { message, reply }) => {
                let result = client
                    .chat(&message, &[])
                    .map(|r| r.content.unwrap_or_default());
                let _ = reply.send(result);
            }
            Ok(RpcCommand::ExecuteCommand { command, reply }) => {
                let _ = reply.send(client.execute_command(&command));
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
            Ok(RpcCommand::ClearHistory { reply }) => {
                let _ = reply.send(client.clear_history());
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
            Ok(RpcCommand::Shutdown) | Err(_) => break,
        }
    }
}
