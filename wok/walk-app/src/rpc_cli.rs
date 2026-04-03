//! Local JSON-RPC CLI helpers for `walk rpc ...`.

use std::error::Error;
use std::path::Path;

use serde_json::Value;

/// Execute one remote JSON-RPC request and optionally return a response payload.
pub fn execute_rpc_command(
    method: String,
    params: String,
    socket: Option<String>,
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
        .or_else(|| std::env::var("WALK_SOCKET").ok())
        .ok_or_else(|| {
            std::io::Error::new(
                std::io::ErrorKind::NotFound,
                "missing remote-control socket; pass --socket or set WALK_SOCKET",
            )
        })?;

    let mut request_map = serde_json::Map::new();
    request_map.insert("jsonrpc".to_string(), Value::String("2.0".to_string()));
    request_map.insert("method".to_string(), Value::String(method));
    request_map.insert("params".to_string(), params_value);

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
        "walk rpc is currently supported on Unix only",
    )
    .into())
}

#[cfg(test)]
mod tests {
    use super::execute_rpc_command;

    #[test]
    fn test_execute_rpc_command_rejects_invalid_params_json() {
        let error = execute_rpc_command(
            "walk.get_panes".to_string(),
            "{not json}".to_string(),
            Some("/tmp/not-used.sock".to_string()),
            None,
            false,
        )
        .expect_err("invalid JSON params should fail");
        assert!(error.to_string().contains("invalid --params JSON"));
    }
}
