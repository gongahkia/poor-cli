//! Parse iTerm2 OSC 1337 inline-image payloads.
//!
//! Wire format (between OSC `]1337;` and the BEL/ST terminator):
//! ```text
//! File=key1=val1;key2=val2;...:base64-encoded-file-bytes
//! ```
//!
//! Recognised keys (subset — extend as consumers need):
//!   - `name=<base64>`        original filename
//!   - `size=<bytes>`         total decoded byte count (informational)
//!   - `width=<n>{auto|N|Npx|Nch}`  display width
//!   - `height=<n>{auto|N|Npx|Nch}` display height
//!   - `preserveAspectRatio=<0|1>`
//!   - `inline=<0|1>`         must be 1 for inline display
//!
//! This module decodes the parameter envelope only. Image-byte decoding is
//! left to image consumers (PNG/JPEG/GIF crates) so we don't pull a heavy
//! dependency for what is just a delimited-key parser.

use base64::engine::general_purpose::STANDARD as B64;
use base64::Engine;

/// Parsed iTerm OSC 1337 image payload.
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct ItermImagePayload {
    /// Decoded original filename (if `name=` was present).
    pub name: Option<String>,
    /// Caller-asserted byte count.
    pub size: Option<u64>,
    /// Display width spec.
    pub width: Option<DisplayDim>,
    /// Display height spec.
    pub height: Option<DisplayDim>,
    /// `preserveAspectRatio=1` — default is true per iTerm docs.
    pub preserve_aspect: bool,
    /// `inline=1` — required for inline display.
    pub inline: bool,
    /// Base64-decoded image bytes.
    pub bytes: Vec<u8>,
}

/// Display dimension specifier.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DisplayDim {
    /// Auto-size (image native).
    Auto,
    /// Cells.
    Cells(u32),
    /// Pixels.
    Pixels(u32),
    /// Percentage of viewport.
    Percent(u32),
}

/// Parse an OSC 1337 payload (the bytes between `]1337;` and the terminator).
pub fn parse(payload: &str) -> Result<ItermImagePayload, String> {
    let stripped = payload
        .strip_prefix("File=")
        .ok_or_else(|| "missing 'File=' prefix".to_string())?;
    let (envelope, b64) = stripped
        .split_once(':')
        .ok_or_else(|| "missing ':' between params and data".to_string())?;
    let mut out = ItermImagePayload {
        preserve_aspect: true, // iTerm default
        ..Default::default()
    };

    for kv in envelope.split(';').filter(|s| !s.is_empty()) {
        let (key, value) = kv.split_once('=').unwrap_or((kv, ""));
        match key.trim() {
            "name" => {
                out.name = B64
                    .decode(value)
                    .ok()
                    .and_then(|b| String::from_utf8(b).ok());
            }
            "size" => {
                out.size = value.parse().ok();
            }
            "width" => {
                out.width = parse_dim(value);
            }
            "height" => {
                out.height = parse_dim(value);
            }
            "preserveAspectRatio" => {
                out.preserve_aspect = value.trim() != "0";
            }
            "inline" => {
                out.inline = value.trim() == "1";
            }
            _ => {} // forward-compat: ignore unknown keys
        }
    }

    out.bytes = B64
        .decode(b64.as_bytes())
        .map_err(|e| format!("base64 decode failed: {e}"))?;
    Ok(out)
}

fn parse_dim(value: &str) -> Option<DisplayDim> {
    let v = value.trim();
    if v.eq_ignore_ascii_case("auto") {
        return Some(DisplayDim::Auto);
    }
    if let Some(num) = v.strip_suffix('%') {
        return num.parse().ok().map(DisplayDim::Percent);
    }
    if let Some(num) = v.strip_suffix("px") {
        return num.parse().ok().map(DisplayDim::Pixels);
    }
    // bare number → cells per iTerm spec
    v.parse().ok().map(DisplayDim::Cells)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn b64(s: &str) -> String {
        B64.encode(s)
    }

    #[test]
    fn parse_minimal_payload() {
        let raw = format!("File=inline=1:{}", b64("hi"));
        let parsed = parse(&raw).unwrap();
        assert!(parsed.inline);
        assert!(parsed.preserve_aspect);
        assert_eq!(parsed.bytes, b"hi");
    }

    #[test]
    fn parse_full_envelope() {
        let raw = format!(
            "File=name={};size=2;inline=1;width=auto;height=24px;preserveAspectRatio=0:{}",
            b64("img.png"),
            b64("ab")
        );
        let p = parse(&raw).unwrap();
        assert_eq!(p.name.as_deref(), Some("img.png"));
        assert_eq!(p.size, Some(2));
        assert!(p.inline);
        assert_eq!(p.width, Some(DisplayDim::Auto));
        assert_eq!(p.height, Some(DisplayDim::Pixels(24)));
        assert!(!p.preserve_aspect);
        assert_eq!(p.bytes, b"ab");
    }

    #[test]
    fn missing_file_prefix_errors() {
        assert!(parse("inline=1:aGk=").is_err());
    }

    #[test]
    fn missing_colon_errors() {
        assert!(parse("File=inline=1").is_err());
    }

    #[test]
    fn invalid_base64_errors() {
        assert!(parse("File=inline=1:!!!").is_err());
    }

    #[test]
    fn unknown_keys_ignored() {
        let raw = format!("File=inline=1;futurekey=foo:{}", b64("x"));
        assert_eq!(parse(&raw).unwrap().bytes, b"x");
    }

    #[test]
    fn dim_variants() {
        assert_eq!(parse_dim("auto"), Some(DisplayDim::Auto));
        assert_eq!(parse_dim("AUTO"), Some(DisplayDim::Auto));
        assert_eq!(parse_dim("80"), Some(DisplayDim::Cells(80)));
        assert_eq!(parse_dim("100px"), Some(DisplayDim::Pixels(100)));
        assert_eq!(parse_dim("50%"), Some(DisplayDim::Percent(50)));
        assert_eq!(parse_dim("garbage"), None);
    }

    #[test]
    fn empty_envelope_treats_inline_false() {
        let raw = format!("File=:{}", b64("x"));
        let p = parse(&raw).unwrap();
        assert!(!p.inline);
        assert_eq!(p.bytes, b"x");
    }
}
