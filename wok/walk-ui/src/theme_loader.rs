//! Theme loader: loads and parses TOML theme files.

use std::path::{Path, PathBuf};

use serde::Deserialize;
use thiserror::Error;

use crate::theme::{Color, Theme};

/// Errors during theme loading.
#[derive(Debug, Error)]
pub enum ThemeError {
    /// Failed to read the theme file.
    #[error("failed to read theme file: {0}")]
    Io(#[from] std::io::Error),

    /// Failed to parse the theme TOML.
    #[error("failed to parse theme: {0}")]
    Parse(#[from] toml::de::Error),

    /// Invalid color format.
    #[error("invalid color format: {0}")]
    InvalidColor(String),
}

/// TOML-deserializable theme with all fields optional.
#[derive(Debug, Default, Deserialize)]
struct ThemeToml {
    name: Option<String>,
    background: Option<String>,
    foreground: Option<String>,
    cursor: Option<String>,
    selection: Option<String>,
    opacity: Option<f32>,
    font_family: Option<String>,
    font_size: Option<f32>,
    background_image: Option<String>,
    ansi: Option<AnsiToml>,
    syntax: Option<SyntaxToml>,
    tab_bar_bg: Option<String>,
    tab_active_bg: Option<String>,
    tab_inactive_bg: Option<String>,
    status_bar_bg: Option<String>,
    input_bg: Option<String>,
}

/// ANSI color overrides.
#[derive(Debug, Default, Deserialize)]
struct AnsiToml {
    black: Option<String>,
    red: Option<String>,
    green: Option<String>,
    yellow: Option<String>,
    blue: Option<String>,
    magenta: Option<String>,
    cyan: Option<String>,
    white: Option<String>,
    bright_black: Option<String>,
    bright_red: Option<String>,
    bright_green: Option<String>,
    bright_yellow: Option<String>,
    bright_blue: Option<String>,
    bright_magenta: Option<String>,
    bright_cyan: Option<String>,
    bright_white: Option<String>,
}

/// Syntax color overrides.
#[derive(Debug, Default, Deserialize)]
struct SyntaxToml {
    command: Option<String>,
    argument: Option<String>,
    flag: Option<String>,
    path: Option<String>,
    string: Option<String>,
    number: Option<String>,
    pipe: Option<String>,
    redirect: Option<String>,
    variable: Option<String>,
    comment: Option<String>,
    error: Option<String>,
}

/// Parse a hex color string (#RRGGBB or #RRGGBBAA) into a Color.
///
/// # Errors
///
/// Returns [`ThemeError::InvalidColor`] if the string is malformed.
pub fn parse_hex_color(s: &str) -> Result<Color, ThemeError> {
    let s = s.trim_start_matches('#');
    match s.len() {
        6 => {
            let r = u8::from_str_radix(&s[0..2], 16)
                .map_err(|_| ThemeError::InvalidColor(s.to_string()))?;
            let g = u8::from_str_radix(&s[2..4], 16)
                .map_err(|_| ThemeError::InvalidColor(s.to_string()))?;
            let b = u8::from_str_radix(&s[4..6], 16)
                .map_err(|_| ThemeError::InvalidColor(s.to_string()))?;
            Ok(Color::new(
                f32::from(r) / 255.0,
                f32::from(g) / 255.0,
                f32::from(b) / 255.0,
                1.0,
            ))
        }
        8 => {
            let r = u8::from_str_radix(&s[0..2], 16)
                .map_err(|_| ThemeError::InvalidColor(s.to_string()))?;
            let g = u8::from_str_radix(&s[2..4], 16)
                .map_err(|_| ThemeError::InvalidColor(s.to_string()))?;
            let b = u8::from_str_radix(&s[4..6], 16)
                .map_err(|_| ThemeError::InvalidColor(s.to_string()))?;
            let a = u8::from_str_radix(&s[6..8], 16)
                .map_err(|_| ThemeError::InvalidColor(s.to_string()))?;
            Ok(Color::new(
                f32::from(r) / 255.0,
                f32::from(g) / 255.0,
                f32::from(b) / 255.0,
                f32::from(a) / 255.0,
            ))
        }
        _ => Err(ThemeError::InvalidColor(s.to_string())),
    }
}

/// Load a theme from a TOML file, merging with defaults.
///
/// # Errors
///
/// Returns [`ThemeError`] if the file cannot be read or parsed.
pub fn load_theme(path: &Path) -> Result<Theme, ThemeError> {
    let content = std::fs::read_to_string(path)?;
    let toml_theme: ThemeToml = toml::from_str(&content)?;
    let mut theme = Theme::default();

    if let Some(name) = toml_theme.name {
        theme.name = name;
    }
    if let Some(bg) = toml_theme.background {
        theme.background = parse_hex_color(&bg)?;
    }
    if let Some(fg) = toml_theme.foreground {
        theme.foreground = parse_hex_color(&fg)?;
    }
    if let Some(c) = toml_theme.cursor {
        theme.cursor = parse_hex_color(&c)?;
    }
    if let Some(s) = toml_theme.selection {
        theme.selection = parse_hex_color(&s)?;
    }
    if let Some(o) = toml_theme.opacity {
        theme.opacity = o;
    }
    if let Some(f) = toml_theme.font_family {
        theme.font_family = f;
    }
    if let Some(s) = toml_theme.font_size {
        theme.font_size = s;
    }
    if let Some(p) = toml_theme.background_image {
        theme.background_image = Some(PathBuf::from(p));
    }
    if let Some(c) = toml_theme.tab_bar_bg {
        theme.tab_bar_bg = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.tab_active_bg {
        theme.tab_active_bg = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.tab_inactive_bg {
        theme.tab_inactive_bg = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.status_bar_bg {
        theme.status_bar_bg = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.input_bg {
        theme.input_bg = parse_hex_color(&c)?;
    }

    // Apply ANSI overrides
    if let Some(ansi) = toml_theme.ansi {
        let overrides = [
            (0, ansi.black),
            (1, ansi.red),
            (2, ansi.green),
            (3, ansi.yellow),
            (4, ansi.blue),
            (5, ansi.magenta),
            (6, ansi.cyan),
            (7, ansi.white),
            (8, ansi.bright_black),
            (9, ansi.bright_red),
            (10, ansi.bright_green),
            (11, ansi.bright_yellow),
            (12, ansi.bright_blue),
            (13, ansi.bright_magenta),
            (14, ansi.bright_cyan),
            (15, ansi.bright_white),
        ];
        for (idx, val) in overrides {
            if let Some(hex) = val {
                theme.ansi_colors[idx] = parse_hex_color(&hex)?;
            }
        }
    }

    // Apply syntax overrides
    if let Some(syn) = toml_theme.syntax {
        apply_optional_color(&mut theme.syntax.command, syn.command)?;
        apply_optional_color(&mut theme.syntax.argument, syn.argument)?;
        apply_optional_color(&mut theme.syntax.flag, syn.flag)?;
        apply_optional_color(&mut theme.syntax.path, syn.path)?;
        apply_optional_color(&mut theme.syntax.string, syn.string)?;
        apply_optional_color(&mut theme.syntax.number, syn.number)?;
        apply_optional_color(&mut theme.syntax.pipe, syn.pipe)?;
        apply_optional_color(&mut theme.syntax.redirect, syn.redirect)?;
        apply_optional_color(&mut theme.syntax.variable, syn.variable)?;
        apply_optional_color(&mut theme.syntax.comment, syn.comment)?;
        apply_optional_color(&mut theme.syntax.error, syn.error)?;
    }

    Ok(theme)
}

fn apply_optional_color(target: &mut Color, hex: Option<String>) -> Result<(), ThemeError> {
    if let Some(h) = hex {
        *target = parse_hex_color(&h)?;
    }
    Ok(())
}

/// Discover available theme files in the themes directory.
pub fn discover_themes(config_dir: &Path) -> Vec<PathBuf> {
    let themes_dir = config_dir.join("themes");
    if !themes_dir.is_dir() {
        return Vec::new();
    }

    std::fs::read_dir(&themes_dir)
        .map(|entries| {
            entries
                .filter_map(Result::ok)
                .filter(|e| e.path().extension().is_some_and(|ext| ext == "toml"))
                .map(|e| e.path())
                .collect()
        })
        .unwrap_or_default()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_hex_rgb() {
        let c = parse_hex_color("#ff0000").unwrap();
        assert!((c.r - 1.0).abs() < 0.01);
        assert!((c.g - 0.0).abs() < 0.01);
        assert!((c.b - 0.0).abs() < 0.01);
        assert!((c.a - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_parse_hex_rgba() {
        let c = parse_hex_color("#ff000080").unwrap();
        assert!((c.r - 1.0).abs() < 0.01);
        assert!((c.a - 0.502).abs() < 0.01);
    }

    #[test]
    fn test_invalid_hex() {
        assert!(parse_hex_color("#xyz").is_err());
    }

    #[test]
    fn test_parse_without_hash() {
        let c = parse_hex_color("00ff00").unwrap();
        assert!((c.g - 1.0).abs() < 0.01);
    }
}
