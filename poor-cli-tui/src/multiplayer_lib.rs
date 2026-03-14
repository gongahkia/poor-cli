/// Shared multiplayer helpers for the TUI library crate.
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

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
