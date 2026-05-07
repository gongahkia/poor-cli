//! Theme data model: defines the complete color and style specification for Wok.

use std::path::PathBuf;

use serde::{Deserialize, Serialize};

/// An RGBA color with floating-point components in [0.0, 1.0].
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct Color {
    /// Red component.
    pub r: f32,
    /// Green component.
    pub g: f32,
    /// Blue component.
    pub b: f32,
    /// Alpha component.
    pub a: f32,
}

impl Color {
    /// Create a new color from RGBA components.
    pub const fn new(r: f32, g: f32, b: f32, a: f32) -> Self {
        Self { r, g, b, a }
    }

    /// Create an opaque color from RGB components.
    pub const fn rgb(r: f32, g: f32, b: f32) -> Self {
        Self { r, g, b, a: 1.0 }
    }

    /// White.
    pub const WHITE: Self = Self::rgb(1.0, 1.0, 1.0);
    /// Black.
    pub const BLACK: Self = Self::rgb(0.0, 0.0, 0.0);
    /// Transparent.
    pub const TRANSPARENT: Self = Self::new(0.0, 0.0, 0.0, 0.0);
}

/// Syntax highlighting colors for the input editor.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyntaxColors {
    /// Command name color.
    pub command: Color,
    /// Argument color.
    pub argument: Color,
    /// Flag color (e.g., -v, --verbose).
    pub flag: Color,
    /// File path color.
    pub path: Color,
    /// String literal color.
    pub string: Color,
    /// Number literal color.
    pub number: Color,
    /// Pipe operator color.
    pub pipe: Color,
    /// Redirect operator color.
    pub redirect: Color,
    /// Variable color (e.g., $HOME).
    pub variable: Color,
    /// Comment color.
    pub comment: Color,
    /// Error color (invalid command).
    pub error: Color,
}

/// Complete theme specification for the terminal.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Theme {
    /// Theme name.
    pub name: String,
    /// Terminal background color.
    pub background: Color,
    /// Terminal foreground (default text) color.
    pub foreground: Color,
    /// Cursor color.
    pub cursor: Color,
    /// Vi-mode cursor color.
    pub vi_cursor_color: Color,
    /// Selection highlight color.
    pub selection: Color,
    /// Standard 16 ANSI colors (8 normal + 8 bright).
    pub ansi_colors: [Color; 16],
    /// Tab bar background color.
    pub tab_bar_bg: Color,
    /// Active tab background color.
    pub tab_active_bg: Color,
    /// Inactive tab background color.
    pub tab_inactive_bg: Color,
    /// Tab text color.
    pub tab_text: Color,
    /// Workspace sidebar background color.
    pub sidebar_background: Color,
    /// Workspace sidebar foreground color.
    pub sidebar_foreground: Color,
    /// Active workspace row background color.
    pub sidebar_active_background: Color,
    /// Workspace sidebar badge color.
    pub sidebar_badge: Color,
    /// Status bar background color.
    pub status_bar_bg: Color,
    /// Status bar text color.
    pub status_bar_text: Color,
    /// Input editor background color.
    pub input_bg: Color,
    /// Input editor text color.
    pub input_text: Color,
    /// Block separator line color.
    pub block_separator: Color,
    /// Block success accent color (exit code 0).
    pub block_success_accent: Color,
    /// Block error accent color (nonzero exit code).
    pub block_error_accent: Color,
    /// Command block background color.
    pub block_background: Color,
    /// Selected command block background color.
    pub block_selected_background: Color,
    /// Failed command block accent color.
    pub block_failed_accent: Color,
    /// Running command block accent color.
    pub block_running_accent: Color,
    /// Command center background color.
    pub command_center_background: Color,
    /// Command center border/accent color.
    pub command_center_border: Color,
    /// Suggestion list background color.
    pub suggestion_background: Color,
    /// Search match highlight color.
    pub highlight_match: Color,
    /// Current search match highlight color.
    pub highlight_current_match: Color,
    /// Hyperlink text color.
    pub hyperlink_color: Color,
    /// Bracket match highlight color.
    pub bracket_match: Color,
    /// Syntax highlighting colors.
    pub syntax: SyntaxColors,
    /// Font family name.
    pub font_family: String,
    /// Font family for chrome labels and controls.
    pub chrome_font_family: String,
    /// Font size in points.
    pub font_size: f32,
    /// Window opacity (0.0 = fully transparent, 1.0 = fully opaque).
    pub opacity: f32,
    /// Optional background image path.
    pub background_image: Option<PathBuf>,
}

impl Default for SyntaxColors {
    fn default() -> Self {
        Self {
            command: Color::rgb(0.541, 0.678, 0.957),  // #8aadf4
            argument: Color::rgb(0.847, 0.871, 0.914), // #d8dee9
            flag: Color::rgb(0.776, 0.627, 0.965),     // #c6a0f6
            path: Color::rgb(0.545, 0.835, 0.792),     // #8bd5ca
            string: Color::rgb(0.651, 0.855, 0.584),   // #a6da95
            number: Color::rgb(0.933, 0.831, 0.624),   // #eed49f
            pipe: Color::rgb(0.561, 0.608, 0.678),     // #8f9bad
            redirect: Color::rgb(0.561, 0.608, 0.678), // #8f9bad
            variable: Color::rgb(0.961, 0.741, 0.902), // #f5bde6
            comment: Color::rgb(0.357, 0.400, 0.463),  // #5b6676
            error: Color::rgb(0.929, 0.529, 0.588),    // #ed8796
        }
    }
}

impl Default for Theme {
    fn default() -> Self {
        Self {
            name: "Wok Clean Dark".to_string(),
            background: Color::rgb(0.059, 0.078, 0.106), // #0f141b
            foreground: Color::rgb(0.847, 0.871, 0.914), // #d8dee9
            cursor: Color::rgb(0.541, 0.678, 0.957),     // #8aadf4
            vi_cursor_color: Color::rgb(0.961, 0.741, 0.902), // #f5bde6
            selection: Color::new(0.184, 0.231, 0.322, 0.67), // #2f3b52aa
            ansi_colors: default_ansi_colors(),
            tab_bar_bg: Color::rgb(0.043, 0.063, 0.090), // #0b1017
            tab_active_bg: Color::rgb(0.090, 0.118, 0.165), // #171e2a
            tab_inactive_bg: Color::rgb(0.063, 0.090, 0.125), // #101720
            tab_text: Color::rgb(0.847, 0.871, 0.914),   // #d8dee9
            sidebar_background: Color::rgb(0.043, 0.063, 0.090), // #0b1017
            sidebar_foreground: Color::rgb(0.792, 0.827, 0.875), // #cad3df
            sidebar_active_background: Color::rgb(0.090, 0.118, 0.165), // #171e2a
            sidebar_badge: Color::rgb(0.929, 0.529, 0.588), // #ed8796
            status_bar_bg: Color::rgb(0.043, 0.063, 0.090), // #0b1017
            status_bar_text: Color::rgb(0.561, 0.608, 0.678), // #8f9bad
            input_bg: Color::rgb(0.067, 0.094, 0.129),   // #111821
            input_text: Color::rgb(0.898, 0.914, 0.941), // #e5e9f0
            block_separator: Color::rgb(0.133, 0.188, 0.267), // #223044
            block_success_accent: Color::rgb(0.545, 0.835, 0.792), // #8bd5ca
            block_error_accent: Color::rgb(0.929, 0.529, 0.588), // #ed8796
            block_background: Color::new(0.067, 0.094, 0.129, 0.08), // #11182114
            block_selected_background: Color::new(0.184, 0.231, 0.322, 0.16), // #2f3b5229
            block_failed_accent: Color::rgb(0.929, 0.529, 0.588), // #ed8796
            block_running_accent: Color::rgb(0.933, 0.831, 0.624), // #eed49f
            command_center_background: Color::rgb(0.067, 0.094, 0.129), // #111821
            command_center_border: Color::rgb(0.541, 0.678, 0.957), // #8aadf4
            suggestion_background: Color::rgb(0.090, 0.118, 0.165), // #171e2a
            highlight_match: Color::new(0.541, 0.678, 0.957, 0.33), // #8aadf455
            highlight_current_match: Color::new(0.933, 0.831, 0.624, 0.45), // #eed49f73
            hyperlink_color: Color::rgb(0.541, 0.678, 0.957), // #8aadf4
            bracket_match: Color::new(0.545, 0.835, 0.792, 0.40), // #8bd5ca66
            syntax: SyntaxColors::default(),
            font_family: "JetBrainsMono Nerd Font Mono".to_string(),
            chrome_font_family: "JetBrainsMono Nerd Font Mono".to_string(),
            font_size: 15.0,
            opacity: 1.0,
            background_image: None,
        }
    }
}

/// Return the default 16 ANSI colors (dark theme).
fn default_ansi_colors() -> [Color; 16] {
    [
        // Normal colors
        Color::rgb(0.082, 0.106, 0.137), // 0 Black   #151b23
        Color::rgb(0.929, 0.529, 0.588), // 1 Red     #ed8796
        Color::rgb(0.651, 0.855, 0.584), // 2 Green   #a6da95
        Color::rgb(0.933, 0.831, 0.624), // 3 Yellow  #eed49f
        Color::rgb(0.541, 0.678, 0.957), // 4 Blue    #8aadf4
        Color::rgb(0.776, 0.627, 0.965), // 5 Magenta #c6a0f6
        Color::rgb(0.545, 0.835, 0.792), // 6 Cyan    #8bd5ca
        Color::rgb(0.792, 0.827, 0.875), // 7 White   #cad3df
        // Bright colors
        Color::rgb(0.357, 0.400, 0.463), // 8  Bright Black   #5b6676
        Color::rgb(0.961, 0.639, 0.678), // 9  Bright Red     #f5a3ad
        Color::rgb(0.722, 0.906, 0.659), // 10 Bright Green   #b8e7a8
        Color::rgb(0.953, 0.867, 0.690), // 11 Bright Yellow  #f3ddb0
        Color::rgb(0.608, 0.737, 0.969), // 12 Bright Blue    #9bbcf7
        Color::rgb(0.824, 0.702, 0.980), // 13 Bright Magenta #d2b3fa
        Color::rgb(0.608, 0.882, 0.839), // 14 Bright Cyan    #9be1d6
        Color::rgb(0.941, 0.957, 0.980), // 15 Bright White   #f0f4fa
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_theme_has_all_ansi_colors() {
        let theme = Theme::default();
        assert_eq!(theme.ansi_colors.len(), 16);
    }

    #[test]
    fn test_default_theme_opacity() {
        let theme = Theme::default();
        assert!((theme.opacity - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_default_theme_font_size() {
        let theme = Theme::default();
        assert!((theme.font_size - 15.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_default_theme_is_wok_clean_dark() {
        let theme = Theme::default();
        assert_eq!(theme.name, "Wok Clean Dark");
        assert!((theme.background.r - (15.0 / 255.0)).abs() < 0.01);
    }

    #[test]
    fn test_color_alpha_in_range() {
        let theme = Theme::default();
        assert!(theme.background.a >= 0.0 && theme.background.a <= 1.0);
        assert!(theme.selection.a >= 0.0 && theme.selection.a <= 1.0);
        for c in &theme.ansi_colors {
            assert!(c.a >= 0.0 && c.a <= 1.0);
        }
    }
}
