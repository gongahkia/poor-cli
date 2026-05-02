//! Local JSON-RPC CLI helpers for `wok rpc ...`.

use std::error::Error;
use std::path::Path;

use serde_json::{json, Value};

/// Execute one remote JSON-RPC request and optionally return a response payload.
pub fn execute_rpc_command(
    method: String,
    params: String,
    socket: Option<String>,
    token: Option<String>,
    id: Option<String>,
    notify: bool,
) -> Result<Option<Value>, Box<dyn Error>> {
    let params_value: Value = serde_json::from_str(&params).map_err(|error| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            format!("invalid --params JSON: {error}"),
        )
    })?;

    let socket_path = socket
        .or_else(|| std::env::var("WOK_SOCKET").ok())
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "missing remote-control socket; pass --socket or set WOK_SOCKET",
            )
        })?;
    let auth_token = token
        .or_else(|| std::env::var("WOK_RPC_TOKEN").ok())
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());

    let mut request_map = serde_json::Map::new();
    request_map.insert("jsonrpc".to_string(), Value::String("2.0".to_string()));
    request_map.insert("method".to_string(), Value::String(method));
    request_map.insert("params".to_string(), params_value);
    if let Some(auth_token) = auth_token {
        request_map.insert("auth_token".to_string(), Value::String(auth_token));
    }

    if !notify {
        let id_value = id.map_or_else(
            || Value::from(1_u64),
            |raw| serde_json::from_str::<Value>(&raw).unwrap_or(Value::String(raw)),
        );
        request_map.insert("id".to_string(), id_value);
    }

    let request = Value::Object(request_map);
    send_remote_rpc_request(Path::new(&socket_path), &request, !notify)
}

/// Execute `wok.get_git_status` and return the result payload.
pub fn execute_git_status_command(
    pane_id: Option<u64>,
    socket: Option<String>,
    token: Option<String>,
) -> Result<Value, Box<dyn Error>> {
    let params = pane_id
        .map(|pane_id| json!({ "pane_id": pane_id }).to_string())
        .unwrap_or_else(|| "null".to_string());
    let response = execute_rpc_command(
        "wok.get_git_status".to_string(),
        params,
        socket,
        token,
        None,
        false,
    )?
    .ok_or_else(|| {
        std::io::Error::new(
            std::io::ErrorKind::UnexpectedEof,
            "remote control server did not return a response",
        )
    })?;

    if let Some(error) = response.get("error") {
        return Err(std::io::Error::other(format!("remote RPC error: {error}")).into());
    }

    Ok(response.get("result").cloned().unwrap_or(response))
}

#[cfg(unix)]
fn send_remote_rpc_request(
    socket_path: &Path,
    request: &Value,
    expect_response: bool,
) -> Result<Option<Value>, Box<dyn Error>> {
    use std::io::{BufRead, BufReader, Write};
    use std::os::unix::net::UnixStream;

    let mut stream = UnixStream::connect(socket_path)?;
    let mut payload = serde_json::to_vec(request)?;
    payload.push(b'\n');
    stream.write_all(&payload)?;
    stream.flush()?;

    if !expect_response {
        return Ok(None);
    }

    let mut reader = BufReader::new(stream);
    let mut line = String::new();
    if reader.read_line(&mut line)? == 0 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::UnexpectedEof,
            "remote control server closed without a response",
        )
        .into());
    }
    let response: Value = serde_json::from_str(line.trim())?;
    Ok(Some(response))
}

#[cfg(not(unix))]
fn send_remote_rpc_request(
    _socket_path: &Path,
    _request: &Value,
    _expect_response: bool,
) -> Result<Option<Value>, Box<dyn Error>> {
    Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "wok rpc is currently supported on Unix only",
    )
    .into())
}

#[cfg(test)]
mod tests {
    use super::{execute_git_status_command, execute_rpc_command};

    #[test]
    fn test_execute_rpc_command_rejects_invalid_params_json() {
        let error = execute_rpc_command(
            "wok.get_panes".to_string(),
            "{not json}".to_string(),
            Some("/tmp/not-used.sock".to_string()),
            None,
            None,
            false,
        )
        .expect_err("invalid JSON params should fail");
        assert!(error.to_string().contains("invalid --params JSON"));
    }

    #[test]
    fn test_execute_git_status_requires_socket() {
        let error = execute_git_status_command(Some(7), None, None)
            .expect_err("missing socket should fail before connecting");
        assert!(error.to_string().contains("missing remote-control socket"));
    }
}
