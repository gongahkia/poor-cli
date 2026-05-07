//! Theme loader: loads and parses TOML theme files.

use std::collections::HashMap;
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
    vi_cursor_color: Option<String>,
    selection: Option<String>,
    opacity: Option<f32>,
    font_family: Option<String>,
    chrome_font_family: Option<String>,
    font_size: Option<f32>,
    background_image: Option<String>,
    ansi: Option<AnsiToml>,
    syntax: Option<SyntaxToml>,
    tab_bar_bg: Option<String>,
    tab_active_bg: Option<String>,
    tab_inactive_bg: Option<String>,
    tab_text: Option<String>,
    status_bar_bg: Option<String>,
    status_bar_text: Option<String>,
    input_bg: Option<String>,
    input_text: Option<String>,
    block_separator: Option<String>,
    block_success_accent: Option<String>,
    block_error_accent: Option<String>,
    highlight_match: Option<String>,
    highlight_current_match: Option<String>,
    hyperlink_color: Option<String>,
    bracket_match: Option<String>,
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
    if let Some(c) = toml_theme.vi_cursor_color {
        theme.vi_cursor_color = parse_hex_color(&c)?;
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
    if let Some(f) = toml_theme.chrome_font_family {
        theme.chrome_font_family = f;
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
    if let Some(c) = toml_theme.tab_text {
        theme.tab_text = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.status_bar_bg {
        theme.status_bar_bg = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.status_bar_text {
        theme.status_bar_text = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.input_bg {
        theme.input_bg = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.input_text {
        theme.input_text = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.block_separator {
        theme.block_separator = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.block_success_accent {
        theme.block_success_accent = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.block_error_accent {
        theme.block_error_accent = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.highlight_match {
        theme.highlight_match = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.highlight_current_match {
        theme.highlight_current_match = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.hyperlink_color {
        theme.hyperlink_color = parse_hex_color(&c)?;
    }
    if let Some(c) = toml_theme.bracket_match {
        theme.bracket_match = parse_hex_color(&c)?;
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

/// Apply a flat map of runtime theme overrides to an existing theme.
///
/// # Errors
///
/// Returns [`ThemeError`] if a color or numeric override cannot be parsed.
pub fn apply_theme_overrides<S: std::hash::BuildHasher>(
    theme: &mut Theme,
    overrides: &HashMap<String, String, S>,
) -> Result<(), ThemeError> {
    for (key, value) in overrides {
        match key.as_str() {
            "name" => theme.name.clone_from(value),
            "background" => theme.background = parse_hex_color(value)?,
            "foreground" => theme.foreground = parse_hex_color(value)?,
            "cursor" => theme.cursor = parse_hex_color(value)?,
            "vi_cursor_color" => theme.vi_cursor_color = parse_hex_color(value)?,
            "selection" => theme.selection = parse_hex_color(value)?,
            "opacity" => {
                theme.opacity = value
                    .parse::<f32>()
                    .map_err(|_| ThemeError::InvalidColor(format!("{key}={value}")))?;
            }
            "font_family" => theme.font_family.clone_from(value),
            "chrome_font_family" => theme.chrome_font_family.clone_from(value),
            "font_size" => {
                theme.font_size = value
                    .parse::<f32>()
                    .map_err(|_| ThemeError::InvalidColor(format!("{key}={value}")))?;
            }
            "background_image" => {
                theme.background_image = (!value.trim().is_empty()).then(|| PathBuf::from(value));
            }
            "tab_bar_bg" => theme.tab_bar_bg = parse_hex_color(value)?,
            "tab_active_bg" => theme.tab_active_bg = parse_hex_color(value)?,
            "tab_inactive_bg" => theme.tab_inactive_bg = parse_hex_color(value)?,
            "status_bar_bg" => theme.status_bar_bg = parse_hex_color(value)?,
            "status_bar_text" => theme.status_bar_text = parse_hex_color(value)?,
            "input_bg" => theme.input_bg = parse_hex_color(value)?,
            "input_text" => theme.input_text = parse_hex_color(value)?,
            "block_separator" => theme.block_separator = parse_hex_color(value)?,
            "block_success_accent" => theme.block_success_accent = parse_hex_color(value)?,
            "block_error_accent" => theme.block_error_accent = parse_hex_color(value)?,
            "highlight_match" => theme.highlight_match = parse_hex_color(value)?,
            "highlight_current_match" => theme.highlight_current_match = parse_hex_color(value)?,
            "hyperlink_color" => theme.hyperlink_color = parse_hex_color(value)?,
            "bracket_match" => theme.bracket_match = parse_hex_color(value)?,
            _ => {}
        }
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

    #[test]
    fn test_apply_theme_overrides_updates_runtime_fields() {
        let mut theme = Theme::default();
        let overrides = HashMap::from([
            ("background".to_string(), "#010203".to_string()),
            ("font_family".to_string(), "Iosevka".to_string()),
            (
                "chrome_font_family".to_string(),
                "IBM Plex Mono".to_string(),
            ),
            ("font_size".to_string(), "16".to_string()),
        ]);

        apply_theme_overrides(&mut theme, &overrides).unwrap();

        assert_eq!(theme.font_family, "Iosevka");
        assert_eq!(theme.chrome_font_family, "IBM Plex Mono");
        assert!((theme.font_size - 16.0).abs() < f32::EPSILON);
        assert!((theme.background.r - (1.0 / 255.0)).abs() < 0.01);
    }

    #[test]
    fn test_load_theme_applies_full_chrome_fields() {
        let dir = std::env::temp_dir();
        let path = dir.join(format!("wok-theme-loader-{}.toml", std::process::id()));
        std::fs::write(
            &path,
            r##"
name = "Full Chrome"
chrome_font_family = "IBM Plex Mono"
tab_text = "#112233"
status_bar_text = "#223344"
input_text = "#334455"
block_separator = "#445566"
block_success_accent = "#556677"
block_error_accent = "#667788"
highlight_match = "#77889980"
highlight_current_match = "#8899aa80"
bracket_match = "#99aabb80"
"##,
        )
        .expect("theme file should be written");

        let theme = load_theme(&path).expect("theme should load");
        assert_eq!(theme.name, "Full Chrome");
        assert_eq!(theme.chrome_font_family, "IBM Plex Mono");
        assert!((theme.tab_text.r - (0x11 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.status_bar_text.r - (0x22 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.input_text.r - (0x33 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.block_separator.r - (0x44 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.block_success_accent.r - (0x55 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.block_error_accent.r - (0x66 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.highlight_match.a - (0x80 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.highlight_current_match.r - (0x88 as f32 / 255.0)).abs() < 0.01);
        assert!((theme.bracket_match.r - (0x99 as f32 / 255.0)).abs() < 0.01);

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn test_checked_in_themes_load() {
        let themes_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../themes");
        for name in [
            "ghostty-wok-dark.toml",
            "gruvbox-wok-dark.toml",
            "gruvbox-wok-day.toml",
            "gruvbox-wok-neon.toml",
            "tokyo-night.toml",
            "catppuccin.toml",
            "nord.toml",
            "gruvbox-dark.toml",
            "solarized-dark.toml",
            "paper-light.toml",
        ] {
            let path = themes_dir.join(name);
            let theme = load_theme(&path)
                .unwrap_or_else(|error| panic!("theme {} should load: {error}", path.display()));
            assert_eq!(theme.ansi_colors.len(), 16);
            assert!(!theme.name.trim().is_empty());
        }
    }
}
