// Tauri IPC command handlers — thin wrappers over JSON-RPC calls to poor-cli-server.

use crate::state::{AppState, BackendProcess};
use serde_json::{json, Value};
use tauri::State;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::Command;

async fn send_rpc(state: &AppState, method: &str, params: Value) -> Result<Value, String> {
    let mut backend = state.backend.lock().map_err(|e| e.to_string())?;
    let backend = backend.as_mut().ok_or("backend not initialized")?;
    let id = state.next_request_id();
    let request = json!({
        "jsonrpc": "2.0",
        "id": id,
        "method": method,
        "params": params,
    });
    let mut msg = serde_json::to_string(&request).map_err(|e| e.to_string())?;
    msg.push('\n');
    backend.stdin.write_all(msg.as_bytes()).await.map_err(|e| e.to_string())?;
    backend.stdin.flush().await.map_err(|e| e.to_string())?;
    let mut line = String::new();
    backend.stdout.read_line(&mut line).await.map_err(|e| e.to_string())?;
    let response: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
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
        let mut backend = state.backend.lock().map_err(|e| e.to_string())?;
        if backend.is_none() {
            let mut child = Command::new("poor-cli-server")
                .arg("--stdio")
                .stdin(std::process::Stdio::piped())
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::null())
                .spawn()
                .map_err(|e| format!("failed to spawn poor-cli-server: {e}"))?;
            let stdin = child.stdin.take().ok_or("failed to capture stdin")?;
            let stdout = child.stdout.take().ok_or("failed to capture stdout")?;
            *backend = Some(BackendProcess {
                child,
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
    let result = send_rpc(&state, "initialize", params).await?;
    *state.initialized.lock().map_err(|e| e.to_string())? = true;
    Ok(result)
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
