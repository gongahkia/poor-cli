use super::*;
use poor_cli_tui::multiplayer as multiplayer_lib;
pub use poor_cli_tui::multiplayer::RemoteBootstrap;
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

fn display_target(bootstrap: &RemoteBootstrap) -> &str {
    &bootstrap.room
}

pub(super) fn build_backend_server_args(cli: &Cli) -> Result<Vec<String>, String> {
    match cli.remote_invite.as_ref() {
        Some(invite) => Ok(vec![
            "--bridge".to_string(),
            "--invite".to_string(),
            invite.to_string(),
        ]),
        None => Ok(vec![]),
    }
}

fn build_bridge_server_args(bootstrap: &RemoteBootstrap) -> Vec<String> {
    vec![
        "--bridge".to_string(),
        "--invite".to_string(),
        bootstrap.invite.clone(),
    ]
}

pub(super) fn should_attempt_remote_reconnect(message: &str) -> bool {
    let lowered = message.to_ascii_lowercase();
    [
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
    app.multiplayer_room = bootstrap.room.clone();
    app.multiplayer_role.clear();
    app.push_message(ChatMessage::system(format!(
        "Joining multiplayer session `{}` via invite...",
        display_target(bootstrap)
    )));
    app.set_status("Reconnecting backend in join mode");

    *rpc_cmd_tx = spawn_backend_worker(tx, launch.clone(), bridge_args, None, None, None);
}

pub fn decode_invite_code(input: &str) -> Result<RemoteBootstrap, String> {
    multiplayer_lib::decode_invite_code(input)
}

pub(super) fn parse_join_server_args(raw: &str) -> Result<RemoteBootstrap, String> {
    let usage =
        "Usage: /join-server\n       /join-server <invite-code>\n       /join-server cancel";
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
    } else {
        return Err(usage.to_string());
    };

    if bootstrap.signaling_url.is_empty() || bootstrap.room.is_empty() || bootstrap.token.is_empty()
    {
        return Err(usage.to_string());
    }
    if !multiplayer_lib::is_supported_endpoint_scheme(&bootstrap.signaling_url) {
        return Err("Invite signaling URL must start with http:// or https://".to_string());
    }

    Ok(bootstrap)
}

fn endpoint_host_port(url: &str) -> Result<(String, u16), String> {
    let trimmed = url.trim();
    let (without_scheme, default_port) = if let Some(rest) = trimmed.strip_prefix("http://") {
        (rest, 80u16)
    } else if let Some(rest) = trimmed.strip_prefix("https://") {
        (rest, 443u16)
    } else {
        return Err("URL must start with http:// or https://".to_string());
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
