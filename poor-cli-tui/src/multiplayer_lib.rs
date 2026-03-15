/// Shared multiplayer helpers for the TUI library crate.
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

/// Decode a base64url invite code, or fall back to raw `url|room|token` format.
pub fn decode_invite_code(input: &str) -> Result<(String, String, String), String> {
    let parts: Vec<&str> = input.split('|').collect();
    if parts.len() == 3 && parts[0].starts_with("ws") {
        return Ok((
            parts[0].trim().to_string(),
            parts[1].trim().to_string(),
            parts[2].trim().to_string(),
        ));
    }

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

#[cfg(test)]
mod tests {
    use super::decode_invite_code;

    #[test]
    fn decode_invite_code_accepts_pipe_delimited_values() {
        let decoded = decode_invite_code("ws://127.0.0.1:8765/rpc|dev|tok-abc")
            .expect("pipe-delimited invite should decode");
        assert_eq!(
            decoded,
            (
                "ws://127.0.0.1:8765/rpc".to_string(),
                "dev".to_string(),
                "tok-abc".to_string(),
            )
        );
    }

    #[test]
    fn decode_invite_code_accepts_base64_values() {
        let decoded = decode_invite_code("d3M6Ly8xMjcuMC4wLjE6ODc2NS9ycGN8ZGV2fHRvay1hYmM")
            .expect("base64 invite should decode");
        assert_eq!(
            decoded,
            (
                "ws://127.0.0.1:8765/rpc".to_string(),
                "dev".to_string(),
                "tok-abc".to_string(),
            )
        );
    }
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
