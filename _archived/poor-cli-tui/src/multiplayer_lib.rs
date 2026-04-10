/// Shared multiplayer helpers for the TUI library crate.
use serde_json::Value;
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RemoteBootstrap {
    pub invite: String,
    pub signaling_url: String,
    pub room: String,
    pub token: String,
}

pub fn decode_invite_code(input: &str) -> Result<RemoteBootstrap, String> {
    let trimmed = input.trim();
    let mut padded = trimmed.to_string();
    while !padded.len().is_multiple_of(4) {
        padded.push('=');
    }
    let decoded = base64_url_decode(&padded)
        .map_err(|_| "Invalid invite code: not a valid signed invite envelope.".to_string())?;

    if let Ok(envelope) = serde_json::from_slice::<Value>(&decoded) {
        let payload = envelope
            .get("payload")
            .and_then(Value::as_object)
            .ok_or_else(|| "Invalid invite code: missing payload envelope.".to_string())?;
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
            return Err(
                "Invalid invite code: missing signalingUrl, sessionId, or token.".to_string(),
            );
        }
        return Ok(RemoteBootstrap {
            invite: trimmed.to_string(),
            signaling_url,
            room,
            token,
        });
    }

    let _ = String::from_utf8(decoded)
        .map_err(|_| "Invalid invite code: decoded bytes are not valid UTF-8.".to_string())?;
    Err("Invalid invite code: expected a signed P2P invite payload.".to_string())
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
        if vals.contains(&255) {
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

pub fn is_supported_endpoint_scheme(url: &str) -> bool {
    url.starts_with("http://") || url.starts_with("https://")
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

#[cfg(test)]
mod tests {
    use super::{decode_invite_code, RemoteBootstrap};

    #[test]
    fn decode_invite_code_accepts_signed_values() {
        let decoded = decode_invite_code(
            "eyJwYXlsb2FkIjp7InYiOjEsImtpbmQiOiJwb29yLWNsaS1wMnAiLCJzaWduYWxpbmdVcmwiOiJodHRwczovL2hvc3QudGVzdC9ycGMiLCJzZXNzaW9uSWQiOiJkb2NzIiwidG9rZW4iOiJ0b2steHl6Iiwicm9sZSI6InZpZXdlciJ9LCJzaWciOiJzaWcifQ",
        )
        .expect("signed invite should decode");
        assert_eq!(
            decoded,
            RemoteBootstrap {
                invite: "eyJwYXlsb2FkIjp7InYiOjEsImtpbmQiOiJwb29yLWNsaS1wMnAiLCJzaWduYWxpbmdVcmwiOiJodHRwczovL2hvc3QudGVzdC9ycGMiLCJzZXNzaW9uSWQiOiJkb2NzIiwidG9rZW4iOiJ0b2steHl6Iiwicm9sZSI6InZpZXdlciJ9LCJzaWciOiJzaWcifQ".to_string(),
                signaling_url: "https://host.test/rpc".to_string(),
                room: "docs".to_string(),
                token: "tok-xyz".to_string(),
            }
        );
    }
}
