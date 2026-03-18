use super::*;
pub use poor_cli_tui::multiplayer::RemoteBootstrap;
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

fn display_target(bootstrap: &RemoteBootstrap) -> &str {
    if bootstrap.invite.is_empty() {
        &bootstrap.signaling_url
    } else {
        &bootstrap.room
    }
}

pub(super) fn build_backend_server_args(cli: &Cli) -> Result<Vec<String>, String> {
    match (
        cli.remote_invite.as_ref(),
        cli.remote_url.as_ref(),
        cli.remote_room.as_ref(),
        cli.remote_token.as_ref(),
    ) {
        (Some(invite), None, None, None) => Ok(vec![
            "--bridge".to_string(),
            "--invite".to_string(),
            invite.to_string(),
        ]),
        (None, None, None, None) => Ok(vec![]),
        (None, Some(url), Some(room), Some(token)) => {
            Ok(build_bridge_server_args(&RemoteBootstrap::from_triplet(
                url, room, token,
            )))
        }
        (Some(_), _, _, _) => Err(
            "Remote mode accepts either --remote-invite or the full --remote-url --remote-room --remote-token triplet."
                .to_string(),
        ),
        _ => Err(
            "Remote mode requires either --remote-invite or all of: --remote-url, --remote-room, --remote-token"
                .to_string(),
        ),
    }
}

fn build_bridge_server_args(bootstrap: &RemoteBootstrap) -> Vec<String> {
    if !bootstrap.invite.is_empty() {
        return vec![
            "--bridge".to_string(),
            "--invite".to_string(),
            bootstrap.invite.clone(),
        ];
    }
    vec![
        "--bridge".to_string(),
        "--url".to_string(),
        bootstrap.signaling_url.clone(),
        "--room".to_string(),
        bootstrap.room.clone(),
        "--token".to_string(),
        bootstrap.token.clone(),
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
        "signaling request failed",
        "invalid invite",
        "data channel",
        "datachannel",
        "peer connection",
    ]
    .iter()
    .any(|needle| lowered.contains(needle))
}

pub(super) fn reconnect_to_remote_server(
    app: &mut App,
    tx: &mpsc::Sender<ServerMsg>,
    rpc_cmd_tx: &mut mpsc::Sender<RpcCommand>,
    launch: &BackendLaunchContext,
    bootstrap: &RemoteBootstrap,
) {
    let bridge_args = build_bridge_server_args(bootstrap);
    write_session_log(
        launch.session_log.as_ref(),
        &format!(
            "join_server_request signaling_url={} room={} invite={}",
            bootstrap.signaling_url,
            bootstrap.room,
            !bootstrap.invite.is_empty()
        ),
    );

    let _ = rpc_cmd_tx.send(RpcCommand::Shutdown);
    app.server_connected = false;
    app.finalize_streaming();
    app.stop_waiting();
    app.multiplayer_enabled = true;
    app.multiplayer_remote_invite = bootstrap.invite.clone();
    app.multiplayer_remote_url = bootstrap.signaling_url.clone();
    app.multiplayer_remote_token = bootstrap.token.clone();
    app.multiplayer_room = bootstrap.room.clone();
    app.multiplayer_role.clear();
    app.push_message(ChatMessage::system(if bootstrap.invite.is_empty() {
        format!(
            "Joining multiplayer server `{}` room `{}`...",
            bootstrap.signaling_url, bootstrap.room
        )
    } else {
        format!("Joining multiplayer session `{}` via invite...", display_target(bootstrap))
    }));
    app.set_status("Reconnecting backend in join mode");

    *rpc_cmd_tx = spawn_backend_worker(tx, launch.clone(), bridge_args, None, None, None);
}

pub fn decode_invite_code(input: &str) -> Result<RemoteBootstrap, String> {
    let trimmed = input.trim();
    let parts: Vec<&str> = trimmed.split('|').collect();
    if parts.len() == 3 && is_supported_endpoint_scheme(parts[0].trim()) {
        return Ok(RemoteBootstrap::from_triplet(
            parts[0].trim(),
            parts[1].trim(),
            parts[2].trim(),
        ));
    }

    let mut padded = trimmed.to_string();
    while padded.len() % 4 != 0 {
        padded.push('=');
    }
    let decoded = base64_url_decode(&padded).map_err(|_| {
        "Invalid invite code: not a valid base64 or pipe-delimited format.".to_string()
    })?;

    if let Ok(envelope) = serde_json::from_slice::<Value>(&decoded) {
        let payload = envelope.get("payload").and_then(Value::as_object).ok_or_else(|| {
            "Invalid invite code: missing payload envelope.".to_string()
        })?;
        let signaling_url = payload
            .get("signalingUrl")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        let room = payload
            .get("sessionId")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        let token = payload
            .get("token")
            .and_then(Value::as_str)
            .unwrap_or("")
            .trim()
            .to_string();
        if signaling_url.is_empty() || room.is_empty() || token.is_empty() {
            return Err("Invalid invite code: missing signalingUrl, sessionId, or token.".to_string());
        }
        return Ok(RemoteBootstrap {
            invite: trimmed.to_string(),
            signaling_url,
            room,
            token,
        });
    }

    let text = String::from_utf8(decoded)
        .map_err(|_| "Invalid invite code: decoded bytes are not valid UTF-8.".to_string())?;
    let parts: Vec<&str> = text.split('|').collect();
    if parts.len() != 3 {
        return Err("Invalid invite code: expected either a signed invite payload or url|room|token after decoding.".to_string());
    }
    Ok(RemoteBootstrap::from_triplet(
        parts[0].trim(),
        parts[1].trim(),
        parts[2].trim(),
    ))
}

fn base64_url_decode(input: &str) -> Result<Vec<u8>, ()> {
    const TABLE: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    let mut lookup = [255u8; 256];
    for (i, &c) in TABLE.iter().enumerate() {
        lookup[c as usize] = i as u8;
    }
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

pub(super) fn parse_join_server_args(raw: &str) -> Result<RemoteBootstrap, String> {
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

    let bootstrap = if args.len() == 1 {
        decode_invite_code(args[0]).map_err(|e| format!("{e}\n{usage}"))?
    } else if args.len() == 3 {
        RemoteBootstrap::from_triplet(args[0], args[1], args[2])
    } else {
        return Err(usage.to_string());
    };

    if bootstrap.signaling_url.is_empty() || bootstrap.room.is_empty() || bootstrap.token.is_empty()
    {
        return Err(usage.to_string());
    }
    if !is_supported_endpoint_scheme(&bootstrap.signaling_url) {
        return Err("Join URL must start with ws://, wss://, http://, or https://".to_string());
    }

    Ok(bootstrap)
}

fn is_supported_endpoint_scheme(url: &str) -> bool {
    url.starts_with("ws://")
        || url.starts_with("wss://")
        || url.starts_with("http://")
        || url.starts_with("https://")
}

fn endpoint_host_port(url: &str) -> Result<(String, u16), String> {
    let trimmed = url.trim();
    let (without_scheme, default_port) = if let Some(rest) = trimmed.strip_prefix("ws://") {
        (rest, 80u16)
    } else if let Some(rest) = trimmed.strip_prefix("wss://") {
        (rest, 443u16)
    } else if let Some(rest) = trimmed.strip_prefix("http://") {
        (rest, 80u16)
    } else if let Some(rest) = trimmed.strip_prefix("https://") {
        (rest, 443u16)
    } else {
        return Err("URL must start with ws://, wss://, http://, or https://".to_string());
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
    let (host, port) = endpoint_host_port(url)?;
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
