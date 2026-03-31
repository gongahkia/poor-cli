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
const RPC_TIMEOUT_LONG: Duration = Duration::from_secs(60); // tasks, checkpoints, automations

async fn send_rpc(state: &AppState, method: &str, params: Value) -> Result<Value, String> {
    let fut = send_rpc_inner(state, method, params);
    timeout(RPC_TIMEOUT, fut).await.map_err(|_| format!("rpc timeout: {method}"))? // bail after 10s
}

async fn send_rpc_long(state: &AppState, method: &str, params: Value) -> Result<Value, String> {
    let fut = send_rpc_inner(state, method, params);
    timeout(RPC_TIMEOUT_LONG, fut).await.map_err(|_| format!("rpc timeout (long): {method}"))?
}

async fn read_one_message(backend: &mut BackendProcess) -> Result<Value, String> {
    let mut header_buf = String::new();
    loop {
        let mut byte = [0u8; 1];
        match backend.stdout.read_exact(&mut byte).await {
            Ok(_) => {}
            Err(e) if e.kind() == std::io::ErrorKind::UnexpectedEof => {
                // server process died — try to get stderr for context
                let mut err_msg = String::from("server process died");
                if let Some(mut se) = backend.stderr.take() {
                    let mut buf = String::new();
                    let _ = se.read_to_string(&mut buf).await;
                    if let Some(line) = buf.lines().rev().find(|l| !l.trim().is_empty()) {
                        err_msg = format!("server crashed: {line}");
                    }
                }
                return Err(err_msg);
            }
            Err(e) => return Err(e.to_string()),
        }
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
    serde_json::from_slice(&body_buf).map_err(|e| e.to_string())
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
    eprintln!("[rpc:req] id={id} method={method}");
    let header = format!("Content-Length: {}\r\n\r\n", body.len());
    backend.stdin.write_all(header.as_bytes()).await.map_err(|e| e.to_string())?;
    backend.stdin.write_all(body.as_bytes()).await.map_err(|e| e.to_string())?;
    backend.stdin.flush().await.map_err(|e| e.to_string())?;
    loop { // read messages until we find the response matching our request id
        let response = read_one_message(backend).await?;
        if response.get("id").is_none() { // notification — skip
            eprintln!("[rpc:notify] method={}", response.get("method").and_then(|v| v.as_str()).unwrap_or("?"));
            continue;
        }
        let resp_id = response.get("id").and_then(|v| v.as_u64()).unwrap_or(0);
        if resp_id != id {
            eprintln!("[rpc:skip] expected id={id} got id={resp_id}");
            continue;
        }
        if let Some(error) = response.get("error") {
            eprintln!("[rpc:err] id={id} method={method} error={error}");
            return Err(error.to_string());
        }
        let result = response.get("result").cloned().unwrap_or(Value::Null);
        eprintln!("[rpc:res] id={id} method={method} result_size={}", result.to_string().len());
        return Ok(result);
    }
}

#[tauri::command]
pub async fn initialize_backend(
    state: State<'_, AppState>,
    provider: Option<String>,
    model: Option<String>,
    env_keys: Option<std::collections::HashMap<String, String>>,
) -> Result<Value, String> {
    // spawn poor-cli-server if not already running
    {
        let mut backend = state.backend.lock().await;
        if backend.is_none() {
            let (cmd, args) = find_server_command();
            let mut cmd_builder = Command::new(&cmd);
            cmd_builder.args(&args)
                .stdin(std::process::Stdio::piped())
                .stdout(std::process::Stdio::piped())
                .stderr(std::process::Stdio::piped());
            if let Some(ref keys) = env_keys { // pass API keys as env vars
                for (k, v) in keys { cmd_builder.env(k, v); }
            }
            eprintln!("[backend] spawning: {cmd} {}", args.join(" "));
            let mut child = cmd_builder.spawn()
                .map_err(|e| format!("failed to spawn poor-cli-server ({cmd}): {e}"))?;
            let stdin = child.stdin.take().ok_or("failed to capture stdin")?;
            let stdout = child.stdout.take().ok_or("failed to capture stdout")?;
            let stderr = child.stderr.take();
            // brief health check — if the process dies instantly (e.g. import error), report it
            tokio::time::sleep(Duration::from_millis(300)).await;
            if let Ok(Some(status)) = child.try_wait() {
                let mut err_output = String::new();
                if let Some(mut se) = stderr {
                    let _ = se.read_to_string(&mut err_output).await;
                }
                let msg = if err_output.is_empty() {
                    format!("server exited immediately ({status})")
                } else {
                    // extract the last meaningful line (usually the exception)
                    let last_line = err_output.lines().rev()
                        .find(|l| !l.trim().is_empty())
                        .unwrap_or(&err_output);
                    format!("server crashed: {last_line}")
                };
                return Err(msg);
            }
            *backend = Some(BackendProcess {
                child,
                stdin,
                stdout: BufReader::new(stdout),
                stderr,
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
pub async fn switch_session(state: State<'_, AppState>, session_id: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/switchSession", json!({"sessionId": session_id})).await
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
pub async fn set_api_key(
    state: State<'_, AppState>,
    provider: String,
    api_key: String,
    persist: Option<bool>,
    reload_active_provider: Option<bool>,
) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/setApiKey", json!({
        "provider": provider,
        "apiKey": api_key,
        "persist": persist.unwrap_or(true),
        "reloadActiveProvider": reload_active_provider.unwrap_or(true),
    })).await
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

// workspace file search
#[tauri::command]
pub async fn search_workspace_files(_state: State<'_, AppState>, query: String, limit: Option<usize>) -> Result<Value, String> {
    let limit = limit.unwrap_or(20);
    let cwd = std::env::current_dir().map_err(|e| e.to_string())?;
    let mut results = Vec::new();
    collect_files(&cwd, &cwd, &query.to_lowercase(), limit, &mut results);
    Ok(json!({"files": results}))
}

fn collect_files(root: &std::path::Path, dir: &std::path::Path, query: &str, limit: usize, results: &mut Vec<String>) {
    if results.len() >= limit { return; }
    let entries = match std::fs::read_dir(dir) { Ok(e) => e, Err(_) => return };
    for entry in entries.flatten() {
        if results.len() >= limit { return; }
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().to_string();
        if name.starts_with('.') || name == "node_modules" || name == "__pycache__" || name == "target" || name == ".venv" { continue; }
        let rel = path.strip_prefix(root).unwrap_or(&path).to_string_lossy().to_string();
        if query.is_empty() || rel.to_lowercase().contains(query) || name.to_lowercase().contains(query) {
            results.push(rel.clone());
        }
        if path.is_dir() { collect_files(root, &path, query, limit, results); }
    }
}

// multiplayer — hosting
#[tauri::command]
pub async fn start_host_server(state: State<'_, AppState>, room: Option<String>, preset: Option<String>, lobby: Option<bool>) -> Result<Value, String> {
    let mut p = json!({});
    if let Some(r) = room { p["room"] = json!(r); }
    if let Some(pr) = preset { p["preset"] = json!(pr); }
    if let Some(l) = lobby { p["lobby"] = json!(l); }
    send_rpc(&state, "poor-cli/startHostServer", p).await
}
#[tauri::command]
pub async fn stop_host_server(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/stopHostServer", json!({})).await
}
#[tauri::command]
pub async fn get_host_server_status(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getHostServerStatus", json!({})).await
}
#[tauri::command]
pub async fn pair_start(state: State<'_, AppState>, lobby: Option<bool>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/pairStart", json!({"lobby": lobby.unwrap_or(false)})).await
}
#[tauri::command]
pub async fn join_remote_session(state: State<'_, AppState>, invite: String) -> Result<Value, String> {
    // kill current backend and restart in bridge mode
    {
        let mut backend = state.backend.lock().await;
        *backend = None; // drop existing process
        *state.initialized.lock().await = false;
    }
    let (cmd, args) = find_bridge_command(&invite);
    let mut cmd_builder = Command::new(&cmd);
    cmd_builder.args(&args)
        .stdin(std::process::Stdio::piped())
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null());
    let mut child = cmd_builder.spawn()
        .map_err(|e| format!("failed to spawn bridge: {e}"))?;
    let stdin = child.stdin.take().ok_or("failed to capture bridge stdin")?;
    let stdout = child.stdout.take().ok_or("failed to capture bridge stdout")?;
    {
        let mut backend = state.backend.lock().await;
        *backend = Some(BackendProcess {
            child,
            stdin,
            stdout: BufReader::new(stdout),
            stderr: None,
        });
    }
    // initialize the bridge connection
    match send_rpc(&state, "initialize", json!({})).await {
        Ok(result) => {
            *state.initialized.lock().await = true;
            Ok(result)
        }
        Err(e) => {
            *state.backend.lock().await = None;
            Err(e)
        }
    }
}
#[tauri::command]
pub async fn leave_remote_session(state: State<'_, AppState>) -> Result<Value, String> {
    // kill bridge process and restart normal stdio server
    {
        let mut backend = state.backend.lock().await;
        *backend = None;
        *state.initialized.lock().await = false;
    }
    // respawn normal server (will be re-initialized on next RPC call)
    Ok(json!({"left": true}))
}

fn find_bridge_command(invite: &str) -> (String, Vec<String>) {
    if let Some(root) = find_project_root() {
        let venv_python = root.join(".venv").join("bin").join("python");
        if venv_python.exists() {
            return (venv_python.to_string_lossy().into_owned(), vec!["-m".into(), "poor_cli.server".into(), "--bridge".into(), "--invite".into(), invite.into()]);
        }
    }
    if which_exists("poor-cli-server") {
        return ("poor-cli-server".into(), vec!["--bridge".into(), "--invite".into(), invite.into()]);
    }
    ("python3".into(), vec!["-m".into(), "poor_cli.server".into(), "--bridge".into(), "--invite".into(), invite.into()])
}

// multiplayer — invites
#[tauri::command]
pub async fn rotate_host_token(state: State<'_, AppState>, role: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/rotateHostToken", json!({"role": role, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn revoke_host_token(state: State<'_, AppState>, value: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/revokeHostToken", json!({"value": value, "room": room.unwrap_or_default()})).await
}

// multiplayer — members
#[tauri::command]
pub async fn list_host_members(state: State<'_, AppState>, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listHostMembers", json!({"room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn remove_host_member(state: State<'_, AppState>, connection_id: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/removeHostMember", json!({"connectionId": connection_id, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn set_host_member_role(state: State<'_, AppState>, connection_id: String, role: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/setHostMemberRole", json!({"connectionId": connection_id, "role": role, "room": room.unwrap_or_default()})).await
}

// multiplayer — lobby
#[tauri::command]
pub async fn set_host_lobby(state: State<'_, AppState>, enabled: bool, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/setHostLobby", json!({"enabled": enabled, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn approve_host_member(state: State<'_, AppState>, connection_id: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/approveHostMember", json!({"connectionId": connection_id, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn deny_host_member(state: State<'_, AppState>, connection_id: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/denyHostMember", json!({"connectionId": connection_id, "room": room.unwrap_or_default()})).await
}

// multiplayer — driver control
#[tauri::command]
pub async fn handoff_host_member(state: State<'_, AppState>, connection_id: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/handoffHostMember", json!({"connectionId": connection_id, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn next_driver(state: State<'_, AppState>, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/nextDriver", json!({"room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn pass_driver(state: State<'_, AppState>, connection_id: Option<String>, display_name: Option<String>, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/passDriver", json!({"connectionId": connection_id.unwrap_or_default(), "displayName": display_name.unwrap_or_default(), "room": room.unwrap_or_default()})).await
}

// multiplayer — session features
#[tauri::command]
pub async fn set_host_preset(state: State<'_, AppState>, preset: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/setHostPreset", json!({"preset": preset, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn list_host_activity(state: State<'_, AppState>, room: Option<String>, limit: Option<u32>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listHostActivity", json!({"room": room.unwrap_or_default(), "limit": limit.unwrap_or(20)})).await
}
#[tauri::command]
pub async fn suggest_text(state: State<'_, AppState>, text: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/suggestText", json!({"text": text, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn set_hand_raised(state: State<'_, AppState>, connection_id: String, raised: bool, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/setHandRaised", json!({"connectionId": connection_id, "raised": raised, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn add_agenda_item(state: State<'_, AppState>, text: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/addAgendaItem", json!({"text": text, "room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn list_agenda(state: State<'_, AppState>, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listAgenda", json!({"room": room.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn resolve_agenda_item(state: State<'_, AppState>, item_id: String, room: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/resolveAgendaItem", json!({"itemId": item_id, "room": room.unwrap_or_default()})).await
}

// --- tasks ---
#[tauri::command]
pub async fn create_task(state: State<'_, AppState>, title: Option<String>, prompt: String, sandbox_preset: Option<String>, requires_approval: Option<bool>) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/createTask", json!({"title": title.unwrap_or_default(), "prompt": prompt, "sandboxPreset": sandbox_preset, "requiresApproval": requires_approval.unwrap_or(false)})).await
}
#[tauri::command]
pub async fn list_tasks(state: State<'_, AppState>, status_filter: Option<String>) -> Result<Value, String> {
    let mut p = json!({});
    if let Some(s) = status_filter { p["status"] = json!(s); }
    send_rpc(&state, "poor-cli/listTasks", p).await
}
#[tauri::command]
pub async fn get_task(state: State<'_, AppState>, task_id: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getTask", json!({"taskId": task_id})).await
}
#[tauri::command]
pub async fn start_task(state: State<'_, AppState>, task_id: String) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/startTask", json!({"taskId": task_id})).await
}
#[tauri::command]
pub async fn approve_task(state: State<'_, AppState>, task_id: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/approveTask", json!({"taskId": task_id})).await
}
#[tauri::command]
pub async fn cancel_task(state: State<'_, AppState>, task_id: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/cancelTask", json!({"taskId": task_id})).await
}
#[tauri::command]
pub async fn retry_task(state: State<'_, AppState>, task_id: String) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/retryTask", json!({"taskId": task_id})).await
}
#[tauri::command]
pub async fn replay_task(state: State<'_, AppState>, task_id: String) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/replayTask", json!({"taskId": task_id})).await
}

// --- checkpoints ---
#[tauri::command]
pub async fn list_checkpoints(state: State<'_, AppState>, limit: Option<u32>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listCheckpoints", json!({"limit": limit.unwrap_or(50)})).await
}
#[tauri::command]
pub async fn create_checkpoint(state: State<'_, AppState>, description: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/createCheckpoint", json!({"description": description.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn restore_checkpoint(state: State<'_, AppState>, checkpoint_id: String) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/restoreCheckpoint", json!({"checkpointId": checkpoint_id})).await
}
#[tauri::command]
pub async fn preview_checkpoint(state: State<'_, AppState>, checkpoint_id: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/previewCheckpoint", json!({"checkpointId": checkpoint_id})).await
}

// --- automation CRUD ---
#[tauri::command]
pub async fn create_automation(state: State<'_, AppState>, name: String, prompt: String, schedule_type: Option<String>, interval_minutes: Option<u32>, requires_approval: Option<bool>) -> Result<Value, String> {
    let mut p = json!({"name": name, "prompt": prompt, "requiresApproval": requires_approval.unwrap_or(false)});
    let stype = schedule_type.unwrap_or_else(|| "interval".into());
    p["schedule"] = json!({"type": stype, "intervalMinutes": interval_minutes.unwrap_or(60)});
    send_rpc_long(&state, "poor-cli/createAutomation", p).await
}
#[tauri::command]
pub async fn get_automation(state: State<'_, AppState>, automation_id: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getAutomation", json!({"automationId": automation_id})).await
}
#[tauri::command]
pub async fn set_automation_enabled(state: State<'_, AppState>, automation_id: String, enabled: bool) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/setAutomationEnabled", json!({"automationId": automation_id, "enabled": enabled})).await
}
#[tauri::command]
pub async fn run_automation_now(state: State<'_, AppState>, automation_id: String) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/runAutomationNow", json!({"automationId": automation_id})).await
}
#[tauri::command]
pub async fn get_automation_history(state: State<'_, AppState>, automation_id: String, limit: Option<u32>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getAutomationHistory", json!({"automationId": automation_id, "limit": limit.unwrap_or(20)})).await
}
#[tauri::command]
pub async fn replay_automation(state: State<'_, AppState>, automation_id: String) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/replayAutomation", json!({"automationId": automation_id})).await
}

// --- custom commands ---
#[tauri::command]
pub async fn list_custom_commands(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listCustomCommands", json!({})).await
}
#[tauri::command]
pub async fn get_custom_command(state: State<'_, AppState>, name: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getCustomCommand", json!({"name": name})).await
}
#[tauri::command]
pub async fn run_custom_command(state: State<'_, AppState>, name: String, args: Option<String>) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/runCustomCommand", json!({"name": name, "args": args.unwrap_or_default()})).await
}

// --- runs/timeline ---
#[tauri::command]
pub async fn list_runs(state: State<'_, AppState>, source_kind: Option<String>, source_id: Option<String>, limit: Option<u32>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listRuns", json!({"sourceKind": source_kind, "sourceId": source_id, "limit": limit})).await
}

// --- workflows ---
#[tauri::command]
pub async fn list_workflows(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/listWorkflows", json!({})).await
}
#[tauri::command]
pub async fn get_workflow(state: State<'_, AppState>, name: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getWorkflow", json!({"name": name})).await
}

// --- tools & MCP ---
#[tauri::command]
pub async fn get_tools(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getTools", json!({})).await
}
#[tauri::command]
pub async fn get_mcp_status(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getMcpStatus", json!({})).await
}

// --- diagnostics ---
#[tauri::command]
pub async fn get_doctor_report(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getDoctorReport", json!({})).await
}
#[tauri::command]
pub async fn get_policy_status(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getPolicyStatus", json!({})).await
}
#[tauri::command]
pub async fn get_trust_view(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getTrustView", json!({})).await
}
#[tauri::command]
pub async fn get_sandbox_status(state: State<'_, AppState>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getSandboxStatus", json!({})).await
}

// --- export ---
#[tauri::command]
pub async fn export_conversation(state: State<'_, AppState>, format: Option<String>) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/exportConversation", json!({"format": format.unwrap_or_else(|| "markdown".into())})).await
}

// --- git (local) ---
#[tauri::command]
pub async fn git_status(_state: State<'_, AppState>) -> Result<Value, String> {
    let out = Command::new("git").args(["status", "-sb"]).output().await.map_err(|e| e.to_string())?;
    Ok(json!({"output": String::from_utf8_lossy(&out.stdout).to_string(), "error": String::from_utf8_lossy(&out.stderr).to_string()}))
}
#[tauri::command]
pub async fn git_log(_state: State<'_, AppState>, count: Option<u32>) -> Result<Value, String> {
    let n = count.unwrap_or(20).to_string();
    let out = Command::new("git").args(["log", "--oneline", "--graph", "--decorate", "-n", &n]).output().await.map_err(|e| e.to_string())?;
    Ok(json!({"output": String::from_utf8_lossy(&out.stdout).to_string(), "error": String::from_utf8_lossy(&out.stderr).to_string()}))
}
#[tauri::command]
pub async fn git_diff(_state: State<'_, AppState>, staged: Option<bool>) -> Result<Value, String> {
    let mut args = vec!["diff", "--stat"];
    if staged.unwrap_or(false) { args.push("--cached"); }
    let out = Command::new("git").args(&args).output().await.map_err(|e| e.to_string())?;
    Ok(json!({"output": String::from_utf8_lossy(&out.stdout).to_string(), "error": String::from_utf8_lossy(&out.stderr).to_string()}))
}
#[tauri::command]
pub async fn git_diff_full(_state: State<'_, AppState>, staged: Option<bool>) -> Result<Value, String> {
    let mut args = vec!["diff"];
    if staged.unwrap_or(false) { args.push("--cached"); }
    let out = Command::new("git").args(&args).output().await.map_err(|e| e.to_string())?;
    Ok(json!({"output": String::from_utf8_lossy(&out.stdout).to_string(), "error": String::from_utf8_lossy(&out.stderr).to_string()}))
}
#[tauri::command]
pub async fn git_branches(_state: State<'_, AppState>) -> Result<Value, String> {
    let out = Command::new("git").args(["branch", "-a", "--no-color"]).output().await.map_err(|e| e.to_string())?;
    Ok(json!({"output": String::from_utf8_lossy(&out.stdout).to_string()}))
}
#[tauri::command]
pub async fn git_graph(_state: State<'_, AppState>, count: Option<u32>) -> Result<Value, String> {
    let n = count.unwrap_or(60).to_string();
    let out = Command::new("git").args(["log", "--all", "--format=%H|%P|%s|%D", "-n", &n]).output().await.map_err(|e| e.to_string())?;
    Ok(json!({"output": String::from_utf8_lossy(&out.stdout).to_string(), "error": String::from_utf8_lossy(&out.stderr).to_string()}))
}

// --- services ---
#[tauri::command]
pub async fn start_service(state: State<'_, AppState>, name: String, options: Option<Value>) -> Result<Value, String> {
    send_rpc_long(&state, "poor-cli/startService", json!({"name": name, "options": options.unwrap_or(json!({}))})).await
}
#[tauri::command]
pub async fn stop_service(state: State<'_, AppState>, name: String) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/stopService", json!({"name": name})).await
}
#[tauri::command]
pub async fn get_service_status(state: State<'_, AppState>, name: Option<String>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getServiceStatus", json!({"name": name.unwrap_or_default()})).await
}
#[tauri::command]
pub async fn get_service_logs(state: State<'_, AppState>, name: String, lines: Option<u32>) -> Result<Value, String> {
    send_rpc(&state, "poor-cli/getServiceLogs", json!({"name": name, "lines": lines.unwrap_or(50)})).await
}
