// Tauri IPC command handlers — thin wrappers over JSON-RPC calls to poor-cli-server.

use crate::state::{AppState, BackendProcess};
use serde_json::{json, Value};
use std::path::PathBuf;
use std::time::Duration;
use tauri::State;
use tokio::io::{AsyncReadExt, AsyncWriteExt, BufReader};
use tokio::process::Command;
use tokio::time::timeout;

fn find_project_root() -> Option<PathBuf> { // walk up from cwd looking for pyproject.toml
    let mut dir = std::env::current_dir().ok()?;
    for _ in 0..10 {
        if dir.join("pyproject.toml").exists() {
            return Some(dir);
        }
        if !dir.pop() { break; }
    }
    None
}

fn find_server_command() -> (String, Vec<String>) { // resolve poor-cli-server location
    if let Some(root) = find_project_root() {
        let venv_python = root.join(".venv").join("bin").join("python");
        if venv_python.exists() {
            return (venv_python.to_string_lossy().into_owned(), vec!["-m".into(), "poor_cli.server".into(), "--stdio".into()]);
        }
    }
    if which_exists("poor-cli-server") {
        return ("poor-cli-server".into(), vec!["--stdio".into()]);
    }
    ("python3".into(), vec!["-m".into(), "poor_cli.server".into(), "--stdio".into()])
}

fn which_exists(name: &str) -> bool {
    std::process::Command::new("which").arg(name).output().map(|o| o.status.success()).unwrap_or(false)
}

const RPC_TIMEOUT: Duration = Duration::from_secs(10);

async fn send_rpc(state: &AppState, method: &str, params: Value) -> Result<Value, String> {
    let fut = send_rpc_inner(state, method, params);
    timeout(RPC_TIMEOUT, fut).await.map_err(|_| format!("rpc timeout: {method}"))? // bail after 10s
}

async fn send_rpc_inner(state: &AppState, method: &str, params: Value) -> Result<Value, String> {
    let mut guard = state.backend.lock().await;
    let backend = guard.as_mut().ok_or("backend not initialized")?;
    let id = state.next_request_id();
    let request = json!({
        "jsonrpc": "2.0",
        "id": id,
        "method": method,
        "params": params,
    });
    let body = serde_json::to_string(&request).map_err(|e| e.to_string())?;
    let header = format!("Content-Length: {}\r\n\r\n", body.len()); // LSP-style framing
    backend.stdin.write_all(header.as_bytes()).await.map_err(|e| e.to_string())?;
    backend.stdin.write_all(body.as_bytes()).await.map_err(|e| e.to_string())?;
    backend.stdin.flush().await.map_err(|e| e.to_string())?;
    // read Content-Length header from response
    let mut header_buf = String::new();
    loop {
        let mut byte = [0u8; 1];
        backend.stdout.read_exact(&mut byte).await.map_err(|e| e.to_string())?;
        header_buf.push(byte[0] as char);
        if header_buf.ends_with("\r\n\r\n") || header_buf.ends_with("\n\n") { break; }
        if header_buf.len() > 256 { return Err("malformed response header".into()); }
    }
    let content_length: usize = header_buf.lines()
        .find(|l| l.to_lowercase().starts_with("content-length:"))
        .and_then(|l| l.split(':').nth(1)?.trim().parse().ok())
        .ok_or("missing Content-Length in response")?;
    let mut body_buf = vec![0u8; content_length];
    backend.stdout.read_exact(&mut body_buf).await.map_err(|e| e.to_string())?;
    let response: Value = serde_json::from_slice(&body_buf).map_err(|e| e.to_string())?;
    if let Some(error) = response.get("error") {
        return Err(error.to_string());
    }
    Ok(response.get("result").cloned().unwrap_or(Value::Null))
}

#[tauri::command]
pub async fn initialize_backend(
    state: State<'_, AppState>,
    provider: Option<String>,
    model: Option<String>,
) -> Result<Value, String> {
    // spawn poor-cli-server if not already running
    {
        let mut backend = state.backend.lock().await;
        if backend.is_none() {
            let (cmd, args) = find_server_command();
            let mut child = Command::new(&cmd)
                .args(&args)
                .stdin(std::process::Stdio::piped())
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::null())
                .spawn()
                .map_err(|e| format!("failed to spawn poor-cli-server: {e}"))?;
            let stdin = child.stdin.take().ok_or("failed to capture stdin")?;
            let stdout = child.stdout.take().ok_or("failed to capture stdout")?;
            *backend = Some(BackendProcess {
                _child: child,
                stdin,
                stdout: BufReader::new(stdout),
            });
        }
    }
    let mut params = json!({});
    if let Some(p) = provider {
        params["provider"] = json!(p);
    }
    if let Some(m) = model {
        params["model"] = json!(m);
    }
    match send_rpc(&state, "initialize", params).await {
        Ok(result) => {
            *state.initialized.lock().await = true;
            Ok(result)
        }
        Err(e) => { // backend spawned but not responding — tear it down
            *state.backend.lock().await = None;
            Err(e)
        }
    }
}

#[tauri::command]
pub async fn send_chat(state: State<'_, AppState>, message: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/chat", json!({"message": message})).await
}

#[tauri::command]
pub async fn get_provider_info(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getProviderInfo", json!({})).await
}

#[tauri::command]
pub async fn switch_provider(
    state: State<'_, AppState>,
    provider: String,
    model: Option<String>,
) -> Result<Value, String> {
    send_rpc(
        &state,
        "poor-cli/switchProvider",
        json!({"provider": provider, "model": model}),
    )
    .await
}

#[tauri::command]
pub async fn clear_history(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/clearHistory", json!({})).await
}

#[tauri::command]
pub async fn list_sessions(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listMuxSessions", json!({})).await
}

#[tauri::command]
pub async fn create_session(
    state: State<'_, AppState>,
    label: Option<String>,
) -> Result<Value, String> {
    send_rpc(
        &state,
        "poor-cli/createSession",
        json!({"label": label.unwrap_or_default()}),
    )
    .await
}

#[tauri::command]
pub async fn destroy_session(
    state: State<'_, AppState>,
    session_id: String,
) -> Result<Value, String> {
    send_rpc(
        &state,
        "poor-cli/destroySession",
        json!({"sessionId": session_id}),
    )
    .await
}

#[tauri::command]
pub async fn get_status_view(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getStatusView", json!({})).await
}

#[tauri::command]
pub async fn list_providers(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listProviders", json!({})).await
}

#[tauri::command]
pub async fn rename_session(state: State<'_, AppState>, session_id: String, label: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/renameSession", json!({"sessionId": session_id, "label": label})).await
}

#[tauri::command]
pub async fn get_config(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getConfig", json!({})).await
}

#[tauri::command]
pub async fn set_config(state: State<'_, AppState>, key_path: String, value: Value) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/setConfig", json!({"keyPath": key_path, "value": value})).await
}

#[tauri::command]
pub async fn list_config_options(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listConfigOptions", json!({})).await
}

#[tauri::command]
pub async fn get_api_key_status(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getApiKeyStatus", json!({})).await
}

#[tauri::command]
pub async fn list_skills(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listSkills", json!({})).await
}

#[tauri::command]
pub async fn list_automations(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listAutomations", json!({})).await
}

#[tauri::command]
pub async fn preview_mutation(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/previewMutation", json!({})).await
}

#[tauri::command]
pub async fn save_session(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/saveSession", json!({})).await
}

#[tauri::command]
pub async fn restore_session(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/restoreSession", json!({})).await
}

#[tauri::command]
pub async fn list_history(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listHistory", json!({})).await
}

#[tauri::command]
pub async fn search_history(state: State<'_, AppState>, term: String, limit: Option<u32>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/searchHistory", json!({"term": term, "limit": limit.unwrap_or(20)})).await
}

#[tauri::command]
pub async fn get_session_cost(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getSessionCost", json!({})).await
}
