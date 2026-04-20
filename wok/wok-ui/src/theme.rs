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
            command: Color::rgb(0.478, 0.635, 0.969),  // #7aa2f7
            argument: Color::rgb(0.753, 0.792, 0.961), // #c0caf5
            flag: Color::rgb(0.514, 0.580, 0.961),     // #838af6
            path: Color::rgb(0.451, 0.812, 0.592),     // #73cf97
            string: Color::rgb(0.631, 0.824, 0.435),   // #a1d26f
            number: Color::rgb(1.0, 0.612, 0.529),     // #ff9c87
            pipe: Color::rgb(0.537, 0.576, 0.647),     // #899ba5
            redirect: Color::rgb(0.537, 0.576, 0.647), // #899ba5
            variable: Color::rgb(0.965, 0.643, 0.310), // #f6a44e
            comment: Color::rgb(0.337, 0.373, 0.459),  // #565f75
            error: Color::rgb(0.969, 0.467, 0.557),    // #f7778e
        }
    }
}

impl Default for Theme {
    fn default() -> Self {
        Self {
            name: "Wok Dark".to_string(),
            background: Color::rgb(0.102, 0.106, 0.149), // #1a1b26
            foreground: Color::rgb(0.753, 0.792, 0.961), // #c0caf5
            cursor: Color::rgb(0.969, 0.467, 0.557),     // #f7768e
            vi_cursor_color: Color::rgb(0.956, 0.859, 0.475), // #f4db79
            selection: Color::new(0.478, 0.635, 0.969, 0.3), // #7aa2f7 semi-transparent
            ansi_colors: default_ansi_colors(),
            tab_bar_bg: Color::rgb(0.082, 0.086, 0.125), // #151620
            tab_active_bg: Color::rgb(0.141, 0.149, 0.200), // #242633
            tab_inactive_bg: Color::rgb(0.102, 0.106, 0.149), // #1a1b26
            tab_text: Color::rgb(0.753, 0.792, 0.961),   // #c0caf5
            status_bar_bg: Color::rgb(0.082, 0.086, 0.125), // #151620
            status_bar_text: Color::rgb(0.537, 0.576, 0.647), // #899ba5
            input_bg: Color::rgb(0.122, 0.129, 0.176),   // #1f2130
            input_text: Color::rgb(0.753, 0.792, 0.961), // #c0caf5
            block_separator: Color::rgb(0.180, 0.192, 0.259), // #2e3142
            block_success_accent: Color::rgb(0.451, 0.812, 0.592), // #73cf97
            block_error_accent: Color::rgb(0.969, 0.467, 0.557), // #f7768e
            highlight_match: Color::new(0.965, 0.820, 0.310, 0.3), // yellow semi-transparent
            highlight_current_match: Color::new(1.0, 0.647, 0.0, 0.5), // orange semi-transparent
            hyperlink_color: Color::rgb(0.45, 0.74, 1.0), // #73bcff
            bracket_match: Color::new(0.478, 0.635, 0.969, 0.4), // blue semi-transparent
            syntax: SyntaxColors::default(),
            font_family: "JetBrains Mono".to_string(),
            font_size: 14.0,
            opacity: 1.0,
            background_image: None,
        }
    }
}

/// Return the default 16 ANSI colors (dark theme).
fn default_ansi_colors() -> [Color; 16] {
    [
        // Normal colors
        Color::rgb(0.082, 0.086, 0.118), // 0 Black   #15161e
        Color::rgb(0.969, 0.467, 0.557), // 1 Red     #f7768e
        Color::rgb(0.451, 0.812, 0.592), // 2 Green   #73cf97
        Color::rgb(0.878, 0.773, 0.463), // 3 Yellow  #e0c576
        Color::rgb(0.478, 0.635, 0.969), // 4 Blue    #7aa2f7
        Color::rgb(0.733, 0.506, 0.969), // 5 Magenta #bb81f7
        Color::rgb(0.478, 0.827, 0.843), // 6 Cyan    #7ad3d7
        Color::rgb(0.753, 0.792, 0.961), // 7 White   #c0caf5
        // Bright colors
        Color::rgb(0.337, 0.373, 0.459), // 8  Bright Black   #565f75
        Color::rgb(0.969, 0.467, 0.557), // 9  Bright Red     #f7768e
        Color::rgb(0.451, 0.812, 0.592), // 10 Bright Green   #73cf97
        Color::rgb(0.878, 0.773, 0.463), // 11 Bright Yellow  #e0c576
        Color::rgb(0.478, 0.635, 0.969), // 12 Bright Blue    #7aa2f7
        Color::rgb(0.733, 0.506, 0.969), // 13 Bright Magenta #bb81f7
        Color::rgb(0.478, 0.827, 0.843), // 14 Bright Cyan    #7ad3d7
        Color::rgb(0.878, 0.914, 0.992), // 15 Bright White   #e0e9fd
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
        assert!((theme.font_size - 14.0).abs() < f32::EPSILON);
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
