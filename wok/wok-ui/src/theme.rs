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
            command: Color::rgb(0.478, 0.655, 1.0),    // #7aa7ff
            argument: Color::rgb(0.843, 0.882, 0.875), // #d7e1df
            flag: Color::rgb(0.780, 0.573, 0.918),     // #c792ea
            path: Color::rgb(0.486, 0.969, 0.757),     // #7cf7c1
            string: Color::rgb(0.627, 0.839, 0.420),   // #a0d66b
            number: Color::rgb(1.0, 0.722, 0.424),     // #ffb86c
            pipe: Color::rgb(0.498, 0.584, 0.580),     // #7f9594
            redirect: Color::rgb(0.498, 0.584, 0.580), // #7f9594
            variable: Color::rgb(0.941, 0.776, 0.455), // #f0c674
            comment: Color::rgb(0.255, 0.314, 0.353),  // #41505a
            error: Color::rgb(1.0, 0.420, 0.478),      // #ff6b7a
        }
    }
}

impl Default for Theme {
    fn default() -> Self {
        Self {
            name: "Graph Box Dark".to_string(),
            background: Color::rgb(0.043, 0.059, 0.071), // #0b0f12
            foreground: Color::rgb(0.843, 0.882, 0.875), // #d7e1df
            cursor: Color::rgb(0.486, 0.969, 0.757),     // #7cf7c1
            vi_cursor_color: Color::rgb(0.941, 0.776, 0.455), // #f0c674
            selection: Color::new(0.184, 0.435, 0.522, 0.36), // #2f6f855c
            ansi_colors: default_ansi_colors(),
            tab_bar_bg: Color::rgb(0.031, 0.047, 0.059), // #080c0f
            tab_active_bg: Color::rgb(0.075, 0.125, 0.153), // #132027
            tab_inactive_bg: Color::rgb(0.051, 0.078, 0.094), // #0d1418
            tab_text: Color::rgb(0.843, 0.882, 0.875),   // #d7e1df
            status_bar_bg: Color::rgb(0.031, 0.047, 0.059), // #080c0f
            status_bar_text: Color::rgb(0.498, 0.584, 0.580), // #7f9594
            input_bg: Color::rgb(0.063, 0.094, 0.125),   // #101820
            input_text: Color::rgb(0.843, 0.882, 0.875), // #d7e1df
            block_separator: Color::rgb(0.133, 0.192, 0.227), // #22313a
            block_success_accent: Color::rgb(0.486, 0.969, 0.757), // #7cf7c1
            block_error_accent: Color::rgb(1.0, 0.420, 0.478), // #ff6b7a
            highlight_match: Color::new(0.941, 0.776, 0.455, 0.33), // #f0c67455
            highlight_current_match: Color::new(1.0, 0.722, 0.424, 0.50), // #ffb86c80
            hyperlink_color: Color::rgb(0.478, 0.655, 1.0), // #7aa7ff
            bracket_match: Color::new(0.486, 0.969, 0.757, 0.33), // #7cf7c155
            syntax: SyntaxColors::default(),
            font_family: "Monaspace Neon".to_string(),
            chrome_font_family: "IBM Plex Mono".to_string(),
            font_size: 24.0,
            opacity: 1.0,
            background_image: None,
        }
    }
}

/// Return the default 16 ANSI colors (dark theme).
fn default_ansi_colors() -> [Color; 16] {
    [
        // Normal colors
        Color::rgb(0.043, 0.059, 0.071), // 0 Black   #0b0f12
        Color::rgb(1.0, 0.420, 0.478),   // 1 Red     #ff6b7a
        Color::rgb(0.486, 0.969, 0.757), // 2 Green   #7cf7c1
        Color::rgb(0.941, 0.776, 0.455), // 3 Yellow  #f0c674
        Color::rgb(0.478, 0.655, 1.0),   // 4 Blue    #7aa7ff
        Color::rgb(0.780, 0.573, 0.918), // 5 Magenta #c792ea
        Color::rgb(0.388, 0.847, 0.847), // 6 Cyan    #63d8d8
        Color::rgb(0.843, 0.882, 0.875), // 7 White   #d7e1df
        // Bright colors
        Color::rgb(0.255, 0.314, 0.353), // 8  Bright Black   #41505a
        Color::rgb(1.0, 0.514, 0.569),   // 9  Bright Red     #ff8391
        Color::rgb(0.604, 1.0, 0.827),   // 10 Bright Green   #9affd3
        Color::rgb(1.0, 0.859, 0.541),   // 11 Bright Yellow  #ffdb8a
        Color::rgb(0.612, 0.753, 1.0),   // 12 Bright Blue    #9cc0ff
        Color::rgb(0.875, 0.686, 1.0),   // 13 Bright Magenta #dfafff
        Color::rgb(0.533, 0.965, 0.965), // 14 Bright Cyan    #88f6f6
        Color::rgb(0.949, 0.973, 0.969), // 15 Bright White   #f2f8f7
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
        assert!((theme.font_size - 24.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_default_theme_is_graph_box_dark() {
        let theme = Theme::default();
        assert_eq!(theme.name, "Graph Box Dark");
        assert!((theme.background.r - (11.0 / 255.0)).abs() < 0.01);
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
