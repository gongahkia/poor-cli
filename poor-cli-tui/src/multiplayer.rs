use super::*;
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

pub(super) fn build_backend_server_args(cli: &Cli) -> Result<Vec<String>, String> {
    match (&cli.remote_url, &cli.remote_room, &cli.remote_token) {
        (None, None, None) => Ok(vec![]),
        (Some(url), Some(room), Some(token)) => Ok(build_bridge_server_args(url, room, token)),
        _ => Err(
            "Remote mode requires all of: --remote-url, --remote-room, --remote-token".to_string(),
        ),
    }
}

fn build_bridge_server_args(url: &str, room: &str, token: &str) -> Vec<String> {
    vec![
        "--bridge".to_string(),
        "--url".to_string(),
        url.to_string(),
        "--room".to_string(),
        room.to_string(),
        "--token".to_string(),
        token.to_string(),
    ]
}

pub(super) fn should_attempt_remote_reconnect(message: &str) -> bool {
    let lowered = message.to_ascii_lowercase();
    [
        "websocket",
        "bridge",
        "connection closed",
        "connection reset",
        "connection refused",
        "broken pipe",
        "no route to host",
        "network is unreachable",
        "transport",
        "rpc worker unavailable",
        "backend response channel closed",
        "timed out waiting for backend response",
    ]
    .iter()
    .any(|needle| lowered.contains(needle))
}

pub(super) fn reconnect_to_remote_server(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    url: &str,
    room: &str,
    token: &str,
) {
    let bridge_args = build_bridge_server_args(url, room, token);
    write_session_log(
        launch.session_log.as_ref(),
        &format!("join_server_request url={url} room={room}"),
    );

    let _ = rpc_cmd_tx.send(RpcCommand::Shutdown);
    app.server_connected = false;
    app.finalize_streaming();
    app.stop_waiting();
    app.multiplayer_enabled = true;
    app.multiplayer_remote_url = url.to_string();
    app.multiplayer_remote_token = token.to_string();
    app.multiplayer_room = room.to_string();
    app.multiplayer_role.clear();
    app.push_message(ChatMessage::system(format!(
        "Joining multiplayer server `{url}` room `{room}`..."
    )));
    app.set_status("Reconnecting backend in join mode");

    *rpc_cmd_tx = spawn_backend_worker(tx, launch.clone(), bridge_args, None, None, None);
}

/// Decode a base64url-encoded invite code, or fall back to raw pipe-delimited format.
pub fn decode_invite_code(input: &str) -> Result<(String, String, String), String> {
    // try pipe-delimited first
    let parts: Vec<&str> = input.split('|').collect();
    if parts.len() == 3 && parts[0].starts_with("ws") {
        return Ok((
            parts[0].trim().to_string(),
            parts[1].trim().to_string(),
            parts[2].trim().to_string(),
        ));
    }
    // try base64url decode
    let mut padded = input.to_string();
    while padded.len() % 4 != 0 {
        padded.push('=');
    }
    let decoded = base64_url_decode(&padded).map_err(|_| {
        "Invalid invite code: not a valid base64 or pipe-delimited format.".to_string()
    })?;
    let text = String::from_utf8(decoded)
        .map_err(|_| "Invalid invite code: decoded bytes are not valid UTF-8.".to_string())?;
    let parts: Vec<&str> = text.split('|').collect();
    if parts.len() != 3 {
        return Err("Invalid invite code: expected url|room|token after decoding.".to_string());
    }
    Ok((
        parts[0].trim().to_string(),
        parts[1].trim().to_string(),
        parts[2].trim().to_string(),
    ))
}

fn base64_url_decode(input: &str) -> Result<Vec<u8>, ()> {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut lookup = [255u8; 256];
    for (i, &c) in TABLE.iter().enumerate() {
        lookup[c as usize] = i as u8;
    }
    // also accept + and / for standard base64
    lookup[b'+' as usize] = 62;
    lookup[b'/' as usize] = 63;
    let bytes: Vec<u8> = input.bytes().filter(|&b| b != b'=').collect();
    let mut out = Vec::with_capacity(bytes.len() * 3 / 4);
    for chunk in bytes.chunks(4) {
        let vals: Vec<u8> = chunk.iter().map(|&b| lookup[b as usize]).collect();
        if vals.iter().any(|&v| v == 255) {
            return Err(());
        }
        if vals.len() >= 2 {
            out.push((vals[0] << 2) | (vals[1] >> 4));
        }
        if vals.len() >= 3 {
            out.push((vals[1] << 4) | (vals[2] >> 2));
        }
        if vals.len() >= 4 {
            out.push((vals[2] << 6) | vals[3]);
        }
    }
    Ok(out)
}

pub(super) fn parse_join_server_args(raw: &str) -> Result<(String, String, String), String> {
    let usage = "Usage: /join-server\n       /join-server <invite-code>\n       /join-server <ws-url> <room> <token>\n       /join-server cancel";
    let args = raw
        .split_whitespace()
        .skip(1)
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .collect::<Vec<_>>();

    if args.is_empty() {
        return Err(usage.to_string());
    }

    let (url, room, token) = if args.len() == 1 {
        match decode_invite_code(args[0]) {
            Ok(tuple) => tuple,
            Err(e) => return Err(format!("{e}\n{usage}")),
        }
    } else if args.len() == 3 {
        (
            args[0].to_string(),
            args[1].to_string(),
            args[2].to_string(),
        )
    } else {
        return Err(usage.to_string());
    };

    if url.is_empty() || room.is_empty() || token.is_empty() {
        return Err(usage.to_string());
    }
    if !(url.starts_with("ws://") || url.starts_with("wss://")) {
        return Err("Join URL must start with ws:// or wss://".to_string());
    }

    Ok((url, room, token))
}

fn ws_url_host_port(url: &str) -> Result<(String, u16), String> {
    let trimmed = url.trim();
    let (without_scheme, default_port) = if let Some(rest) = trimmed.strip_prefix("ws://") {
        (rest, 80u16)
    } else if let Some(rest) = trimmed.strip_prefix("wss://") {
        (rest, 443u16)
    } else {
        return Err("URL must start with ws:// or wss://".to_string());
    };

    let authority = without_scheme.split('/').next().unwrap_or("").trim();
    if authority.is_empty() {
        return Err("URL is missing host".to_string());
    }

    if authority.starts_with('[') {
        if let Some(close_idx) = authority.find(']') {
            let host = authority[1..close_idx].to_string();
            let remainder = authority[close_idx + 1..].trim();
            let port = if let Some(port_text) = remainder.strip_prefix(':') {
                port_text
                    .parse::<u16>()
                    .map_err(|_| "Invalid URL port".to_string())?
            } else {
                default_port
            };
            return Ok((host, port));
        }
        return Err("Invalid IPv6 URL host".to_string());
    }

    if let Some((host, port_text)) = authority.rsplit_once(':') {
        if host.contains(':') {
            return Ok((authority.to_string(), default_port));
        }
        let port = port_text
            .parse::<u16>()
            .map_err(|_| "Invalid URL port".to_string())?;
        return Ok((host.to_string(), port));
    }

    Ok((authority.to_string(), default_port))
}

pub fn preflight_join_endpoint(url: &str) -> Result<String, String> {
    let (host, port) = ws_url_host_port(url)?;
    let addr_text = format!("{host}:{port}");
    let mut addrs = addr_text
        .to_socket_addrs()
        .map_err(|e| format!("Could not resolve `{host}`: {e}"))?;
    let target = addrs
        .next()
        .ok_or_else(|| format!("No reachable address found for `{host}`"))?;
    TcpStream::connect_timeout(&target, Duration::from_secs(2))
        .map_err(|e| format!("Could not reach {addr_text}: {e}"))?;
    Ok(format!("Preflight OK: reachable {addr_text}"))
}
