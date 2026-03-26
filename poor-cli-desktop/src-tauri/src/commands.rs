// Tauri IPC command handlers — thin wrappers over JSON-RPC calls to poor-cli-server.

use crate::state::{AppState, BackendProcess};
use serde_json::{json, Value};
use tauri::State;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::Command;

async fn send_rpc(state: &AppState, method: &str, params: Value) -> Result<Value, String> {
    let mut guard = state.backend.lock().await;
    let backend = guard.as_mut().ok_or("backend not initialized")?;
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
        let mut backend = state.backend.lock().await;
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
    let result = send_rpc(&state, "initialize", params).await?;
    *state.initialized.lock().await = true;
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
