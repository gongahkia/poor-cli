//! Pure ANSI/CSI/DCS/OSC/APC parser helpers.
//!
//! Lifted out of `terminal.rs` so the boundary "parsing vs state mutation"
//! is explicit. Every function here is stateless, deterministic, and free of
//! I/O. State mutations live in `state.rs`; sequence dispatch + buffering
//! lives in `terminal.rs`.
//!
//! Reference: `warp/ESCAPE_SEQUENCES.md` (read-only spec corpus).

use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;

use base64::Engine;
use tracing::warn;

/// Return `(payload_end_idx, terminator_len)` for the first OSC terminator
/// (BEL or ESC `\`) at or after `start`. `payload_end_idx` is the offset of
/// the BEL or the ESC.
pub(crate) fn find_osc_terminator(bytes: &[u8], start: usize) -> Option<(usize, usize)> {
    let mut idx = start;
    while idx < bytes.len() {
        if bytes[idx] == 0x07 {
            return Some((idx, 1));
        }
        if bytes[idx] == 0x1b && bytes.get(idx + 1) == Some(&b'\\') {
            return Some((idx, 2));
        }
        idx += 1;
    }
    None
}

/// Like [`find_osc_terminator`] but accepts only `ESC \` (APC has no BEL form).
pub(crate) fn find_apc_terminator(bytes: &[u8], start: usize) -> Option<(usize, usize)> {
    let mut idx = start;
    while idx < bytes.len() {
        if bytes[idx] == 0x1b && bytes.get(idx + 1) == Some(&b'\\') {
            return Some((idx, 2));
        }
        idx += 1;
    }
    None
}

/// DCS terminator: `ESC \` or single-byte `ST` (`0x9c`).
pub(crate) fn find_dcs_terminator(bytes: &[u8], start: usize) -> Option<(usize, usize)> {
    let mut idx = start;
    while idx < bytes.len() {
        if bytes[idx] == 0x1b && bytes.get(idx + 1) == Some(&b'\\') {
            return Some((idx, 2));
        }
        if bytes[idx] == 0x9c {
            return Some((idx, 1));
        }
        idx += 1;
    }
    None
}

/// Index of the CSI final byte (`@..~`).
pub(crate) fn find_csi_terminator(bytes: &[u8], start: usize) -> Option<usize> {
    let mut idx = start;
    while idx < bytes.len() {
        let byte = bytes[idx];
        if (0x40..=0x7e).contains(&byte) {
            return Some(idx);
        }
        idx += 1;
    }
    None
}

/// Kitty progressive-keyboard control sequence variant.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum KittyKeyboardControl {
    /// `?` — query current flags.
    Query,
    /// `>N` — push flags.
    Push(u32),
    /// `<` — pop flags.
    Pop,
}

/// Parse a kitty keyboard CSI payload into a control variant.
pub(crate) fn parse_kitty_keyboard_control(params: &str) -> Option<KittyKeyboardControl> {
    let trimmed = params.trim();
    match trimmed {
        "?" => Some(KittyKeyboardControl::Query),
        "<" => Some(KittyKeyboardControl::Pop),
        _ => {
            let rest = trimmed.strip_prefix('>')?;
            let flags_text = rest.split(';').next().unwrap_or_default().trim();
            if flags_text.is_empty() {
                return Some(KittyKeyboardControl::Push(0));
            }
            match flags_text.parse::<u32>() {
                Ok(flags) => Some(KittyKeyboardControl::Push(flags)),
                Err(error) => {
                    warn!("ignoring invalid kitty keyboard flags '{flags_text}': {error}");
                    None
                }
            }
        }
    }
}

/// Decode a kitty image transmission payload into RGBA8 bytes + dimensions.
pub(crate) fn decode_kitty_image_data(
    format: u32,
    transmission: char,
    encoded: &str,
    source_width: u32,
    source_height: u32,
) -> Result<(u32, u32, Vec<u8>), String> {
    let bytes = match transmission {
        'd' => base64::engine::general_purpose::STANDARD
            .decode(encoded.as_bytes())
            .map_err(|error| format!("invalid kitty base64 payload: {error}"))?,
        'f' | 't' => {
            let path = parse_kitty_file_path(encoded)?;
            let bytes = fs::read(&path).map_err(|error| {
                format!(
                    "failed to read kitty image file {}: {error}",
                    path.display()
                )
            })?;
            if transmission == 't' {
                if let Err(error) = fs::remove_file(&path) {
                    warn!("failed to remove kitty temp image {path:?}: {error}");
                }
            }
            bytes
        }
        other => {
            return Err(format!(
                "unsupported kitty transmission mode '{other}' (expected d/f/t)"
            ));
        }
    };

    match format {
        24 => {
            let width = source_width.max(1);
            let height = source_height.max(1);
            let expected = (width as usize)
                .saturating_mul(height as usize)
                .saturating_mul(3);
            if bytes.len() < expected {
                return Err("kitty RGB payload shorter than declared dimensions".to_string());
            }
            let mut rgba = Vec::with_capacity((width as usize) * (height as usize) * 4);
            for chunk in bytes[..expected].chunks_exact(3) {
                rgba.push(chunk[0]);
                rgba.push(chunk[1]);
                rgba.push(chunk[2]);
                rgba.push(255);
            }
            Ok((width, height, rgba))
        }
        32 => {
            let width = source_width.max(1);
            let height = source_height.max(1);
            let expected = (width as usize)
                .saturating_mul(height as usize)
                .saturating_mul(4);
            if bytes.len() < expected {
                return Err("kitty RGBA payload shorter than declared dimensions".to_string());
            }
            Ok((width, height, bytes[..expected].to_vec()))
        }
        100 => {
            let image = image::load_from_memory(&bytes)
                .map_err(|error| format!("failed to decode kitty image payload: {error}"))?
                .to_rgba8();
            Ok((image.width(), image.height(), image.into_raw()))
        }
        other => Err(format!(
            "unsupported kitty format '{other}' (expected 24/32/100)"
        )),
    }
}

/// Decode a kitty `f`/`t` file-path payload (base64 or raw).
pub(crate) fn parse_kitty_file_path(encoded: &str) -> Result<PathBuf, String> {
    let decoded = base64::engine::general_purpose::STANDARD
        .decode(encoded.as_bytes())
        .ok()
        .and_then(|bytes| String::from_utf8(bytes).ok())
        .unwrap_or_else(|| encoded.to_string());
    let cleaned = decoded.trim_matches('\0').trim();
    if cleaned.is_empty() {
        return Err("empty kitty file transmission path".to_string());
    }
    Ok(PathBuf::from(cleaned))
}

/// Split an OSC 8 hyperlink param list (`key=value:key=value;...`) into a map.
pub(crate) fn parse_osc8_params(params: &str) -> HashMap<String, String> {
    let mut parsed = HashMap::new();
    for token in params
        .split(':')
        .flat_map(|segment| segment.split(';'))
        .filter(|segment| !segment.trim().is_empty())
    {
        if let Some((key, value)) = token.split_once('=') {
            parsed.insert(key.trim().to_string(), value.trim().to_string());
        }
    }
    parsed
}

/// Convert a sixel pixel size into terminal cells using fixed 8x16 cell pixels.
pub(crate) fn sixel_display_size(width: u32, height: u32) -> (u16, u16) {
    const CELL_PIXEL_WIDTH: u32 = 8;
    const CELL_PIXEL_HEIGHT: u32 = 16;

    let cols = width.div_ceil(CELL_PIXEL_WIDTH).max(1);
    let rows = height.div_ceil(CELL_PIXEL_HEIGHT).max(1);
    (
        cols.min(u32::from(u16::MAX)) as u16,
        rows.min(u32::from(u16::MAX)) as u16,
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn osc_terminator_supports_bel_and_st() {
        let bel = b"\x1b]8;;https://example.com\x07";
        let st = b"\x1b]8;;https://example.com\x1b\\";
        assert_eq!(find_osc_terminator(bel, 2), Some((24, 1)));
        assert_eq!(find_osc_terminator(st, 2), Some((24, 2)));
    }

    #[test]
    fn osc_terminator_returns_none_at_eof() {
        assert_eq!(find_osc_terminator(b"\x1b]8;;abc", 2), None);
    }

    #[test]
    fn apc_terminator_requires_st() {
        assert_eq!(find_apc_terminator(b"\x1b_Gabc\x07", 2), None);
        assert_eq!(find_apc_terminator(b"\x1b_Gabc\x1b\\", 2), Some((6, 2)));
    }

    #[test]
    fn dcs_terminator_accepts_st_or_single_byte_9c() {
        assert_eq!(find_dcs_terminator(b"\x1bPdata\x1b\\", 2), Some((6, 2)));
        assert_eq!(find_dcs_terminator(b"\x1bPdata\x9c", 2), Some((6, 1)));
        assert_eq!(find_dcs_terminator(b"\x1bPdata\x07", 2), None);
    }

    #[test]
    fn csi_terminator_finds_final_byte_in_at_to_tilde_range() {
        let csi_m = b"\x1b[31m";
        assert_eq!(find_csi_terminator(csi_m, 2), Some(4));
        let csi_h = b"\x1b[?2026h";
        assert_eq!(find_csi_terminator(csi_h, 2), Some(7));
        assert_eq!(find_csi_terminator(b"\x1b[31", 2), None);
    }

    #[test]
    fn parse_osc8_params_extracts_id() {
        let params = parse_osc8_params("id=abc123:foo=bar");
        assert_eq!(params.get("id"), Some(&"abc123".to_string()));
        assert_eq!(params.get("foo"), Some(&"bar".to_string()));
    }

    #[test]
    fn parse_osc8_params_skips_blank_tokens() {
        let params = parse_osc8_params(":id=x: :");
        assert_eq!(params.get("id"), Some(&"x".to_string()));
        assert_eq!(params.len(), 1);
    }

    #[test]
    fn sixel_display_size_rounds_up_cells() {
        assert_eq!(sixel_display_size(1, 1), (1, 1));
        assert_eq!(sixel_display_size(16, 32), (2, 2));
        assert_eq!(sixel_display_size(17, 33), (3, 3));
    }

    #[test]
    fn parse_kitty_file_path_accepts_raw_and_base64() {
        let raw = parse_kitty_file_path("/tmp/a.png").expect("raw path");
        assert_eq!(raw, PathBuf::from("/tmp/a.png"));
        let encoded = base64::engine::general_purpose::STANDARD.encode("/tmp/b.png");
        let decoded = parse_kitty_file_path(&encoded).expect("base64 path");
        assert_eq!(decoded, PathBuf::from("/tmp/b.png"));
    }

    #[test]
    fn parse_kitty_file_path_rejects_empty() {
        assert!(parse_kitty_file_path("").is_err());
        assert!(parse_kitty_file_path("\0\0").is_err());
    }

    #[test]
    fn parse_kitty_keyboard_control_variants() {
        assert_eq!(
            parse_kitty_keyboard_control("?"),
            Some(KittyKeyboardControl::Query)
        );
        assert_eq!(
            parse_kitty_keyboard_control("<"),
            Some(KittyKeyboardControl::Pop)
        );
        assert_eq!(
            parse_kitty_keyboard_control(">5"),
            Some(KittyKeyboardControl::Push(5))
        );
        assert_eq!(
            parse_kitty_keyboard_control(">5;1"),
            Some(KittyKeyboardControl::Push(5))
        );
        assert_eq!(
            parse_kitty_keyboard_control(">"),
            Some(KittyKeyboardControl::Push(0))
        );
    }

    #[test]
    fn parse_kitty_keyboard_control_rejects_invalid_flags() {
        assert_eq!(parse_kitty_keyboard_control(">abc"), None);
        assert_eq!(parse_kitty_keyboard_control(""), None);
    }

    #[test]
    fn decode_kitty_image_data_rgb_pads_alpha_channel() {
        let pixels: Vec<u8> = vec![10, 20, 30, 40, 50, 60];
        let encoded = base64::engine::general_purpose::STANDARD.encode(&pixels);
        let (w, h, out) = decode_kitty_image_data(24, 'd', &encoded, 2, 1).unwrap();
        assert_eq!((w, h), (2, 1));
        assert_eq!(out, vec![10, 20, 30, 255, 40, 50, 60, 255]);
    }

    #[test]
    fn decode_kitty_image_data_rejects_short_payload() {
        let encoded = base64::engine::general_purpose::STANDARD.encode([0u8, 0, 0]);
        let err = decode_kitty_image_data(24, 'd', &encoded, 2, 2).unwrap_err();
        assert!(err.contains("shorter than declared"), "got: {err}");
    }

    #[test]
    fn decode_kitty_image_data_rejects_unknown_format() {
        let encoded = base64::engine::general_purpose::STANDARD.encode([0u8]);
        let err = decode_kitty_image_data(7, 'd', &encoded, 1, 1).unwrap_err();
        assert!(err.contains("unsupported kitty format"));
    }
}
