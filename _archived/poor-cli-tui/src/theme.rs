/// Theme-aware style helpers for the poor-cli TUI.
///
/// Supports 8 named themes: dark (one-dark), light (github-light),
/// dracula, nord, monokai, github-dark, solarized-light, quiet-light.
use crate::app::ThemeMode;
use ratatui::style::{Color, Modifier, Style};

pub fn app_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(52, 56, 60),
        ThemeMode::Light => Color::Rgb(243, 240, 232),
        ThemeMode::Dracula => Color::Rgb(40, 42, 54),
        ThemeMode::Nord => Color::Rgb(46, 52, 64),
        ThemeMode::Monokai => Color::Rgb(39, 40, 34),
        ThemeMode::GithubDark => Color::Rgb(36, 41, 47),
        ThemeMode::SolarizedLight => Color::Rgb(253, 246, 227),
        ThemeMode::QuietLight => Color::Rgb(245, 245, 245),
    }
}

pub fn surface_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(60, 64, 69),
        ThemeMode::Light => Color::Rgb(235, 231, 221),
        ThemeMode::Dracula => Color::Rgb(68, 71, 90),
        ThemeMode::Nord => Color::Rgb(59, 66, 82),
        ThemeMode::Monokai => Color::Rgb(52, 53, 46),
        ThemeMode::GithubDark => Color::Rgb(48, 54, 61),
        ThemeMode::SolarizedLight => Color::Rgb(238, 232, 213),
        ThemeMode::QuietLight => Color::Rgb(235, 235, 235),
    }
}

pub fn elevated_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(66, 71, 76),
        ThemeMode::Light => Color::Rgb(227, 223, 214),
        ThemeMode::Dracula => Color::Rgb(98, 114, 164),
        ThemeMode::Nord => Color::Rgb(67, 76, 94),
        ThemeMode::Monokai => Color::Rgb(62, 63, 55),
        ThemeMode::GithubDark => Color::Rgb(56, 62, 70),
        ThemeMode::SolarizedLight => Color::Rgb(227, 220, 200),
        ThemeMode::QuietLight => Color::Rgb(225, 225, 225),
    }
}

pub fn base_fg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(229, 218, 193),
        ThemeMode::Light => Color::Rgb(45, 43, 40),
        ThemeMode::Dracula => Color::Rgb(248, 248, 242),
        ThemeMode::Nord => Color::Rgb(216, 222, 233),
        ThemeMode::Monokai => Color::Rgb(248, 248, 240),
        ThemeMode::GithubDark => Color::Rgb(201, 209, 217),
        ThemeMode::SolarizedLight => Color::Rgb(101, 123, 131),
        ThemeMode::QuietLight => Color::Rgb(57, 58, 52),
    }
}

pub fn muted_fg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(149, 145, 137),
        ThemeMode::Light => Color::Rgb(121, 115, 105),
        ThemeMode::Dracula => Color::Rgb(98, 114, 164),
        ThemeMode::Nord => Color::Rgb(127, 140, 160),
        ThemeMode::Monokai => Color::Rgb(117, 113, 94),
        ThemeMode::GithubDark => Color::Rgb(139, 148, 158),
        ThemeMode::SolarizedLight => Color::Rgb(147, 161, 161),
        ThemeMode::QuietLight => Color::Rgb(130, 130, 130),
    }
}

pub fn accent(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(176, 187, 143),
        ThemeMode::Light => Color::Rgb(107, 118, 74),
        ThemeMode::Dracula => Color::Rgb(189, 147, 249),
        ThemeMode::Nord => Color::Rgb(136, 192, 208),
        ThemeMode::Monokai => Color::Rgb(166, 226, 46),
        ThemeMode::GithubDark => Color::Rgb(121, 192, 255),
        ThemeMode::SolarizedLight => Color::Rgb(38, 139, 210),
        ThemeMode::QuietLight => Color::Rgb(75, 105, 198),
    }
}

pub fn success(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(166, 218, 168),
        ThemeMode::Light => Color::Rgb(36, 124, 74),
        ThemeMode::Dracula => Color::Rgb(80, 250, 123),
        ThemeMode::Nord => Color::Rgb(163, 190, 140),
        ThemeMode::Monokai => Color::Rgb(166, 226, 46),
        ThemeMode::GithubDark => Color::Rgb(63, 185, 80),
        ThemeMode::SolarizedLight => Color::Rgb(133, 153, 0),
        ThemeMode::QuietLight => Color::Rgb(76, 131, 56),
    }
}

pub fn warning(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(220, 199, 149),
        ThemeMode::Light => Color::Rgb(155, 117, 24),
        ThemeMode::Dracula => Color::Rgb(241, 250, 140),
        ThemeMode::Nord => Color::Rgb(235, 203, 139),
        ThemeMode::Monokai => Color::Rgb(230, 219, 116),
        ThemeMode::GithubDark => Color::Rgb(210, 153, 34),
        ThemeMode::SolarizedLight => Color::Rgb(181, 137, 0),
        ThemeMode::QuietLight => Color::Rgb(158, 109, 19),
    }
}

pub fn error(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(235, 129, 122),
        ThemeMode::Light => Color::Rgb(176, 72, 67),
        ThemeMode::Dracula => Color::Rgb(255, 85, 85),
        ThemeMode::Nord => Color::Rgb(191, 97, 106),
        ThemeMode::Monokai => Color::Rgb(249, 38, 114),
        ThemeMode::GithubDark => Color::Rgb(248, 81, 73),
        ThemeMode::SolarizedLight => Color::Rgb(220, 50, 47),
        ThemeMode::QuietLight => Color::Rgb(195, 55, 55),
    }
}

pub fn user_color(mode: ThemeMode) -> Color {
    warning(mode)
}

pub fn assistant_color(mode: ThemeMode) -> Color {
    accent(mode)
}

pub fn system_color(mode: ThemeMode) -> Color {
    if mode.is_dark() { muted_fg(mode) } else { muted_fg(mode) }
}

pub fn status_bar_style(mode: ThemeMode) -> Style {
    Style::default().fg(base_fg(mode)).bg(surface_bg(mode))
}

pub fn app_background_style(mode: ThemeMode) -> Style {
    Style::default().bg(app_bg(mode))
}

pub fn surface_style(mode: ThemeMode) -> Style {
    Style::default().fg(base_fg(mode)).bg(surface_bg(mode))
}

pub fn footer_style(mode: ThemeMode) -> Style {
    Style::default().fg(muted_fg(mode)).bg(surface_bg(mode))
}

pub fn activity_style(mode: ThemeMode) -> Style {
    Style::default().fg(base_fg(mode)).bg(surface_bg(mode))
}

pub fn input_panel_style(mode: ThemeMode) -> Style {
    Style::default().fg(base_fg(mode)).bg(elevated_bg(mode))
}

pub fn brand_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(base_fg(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn user_label_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(user_color(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn assistant_label_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(assistant_color(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn tool_border_style(mode: ThemeMode) -> Style {
    Style::default().fg(input_border_color(mode))
}

pub fn tool_title_style(mode: ThemeMode) -> Style {
    Style::default().fg(muted_fg(mode))
}

pub fn input_style(mode: ThemeMode) -> Style {
    Style::default().fg(base_fg(mode))
}

pub fn input_cursor_style(mode: ThemeMode) -> Style {
    if mode.is_dark() {
        Style::default().fg(Color::Black).bg(accent(mode))
    } else {
        Style::default().fg(Color::White).bg(accent(mode))
    }
}

pub fn input_border_color(mode: ThemeMode) -> Color {
    if mode.is_dark() { Color::Rgb(88, 91, 96) } else { Color::Rgb(176, 168, 154) }
}

pub fn code_block_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(46, 49, 54),
        ThemeMode::Light => Color::Rgb(239, 235, 226),
        ThemeMode::Dracula => Color::Rgb(34, 36, 48),
        ThemeMode::Nord => Color::Rgb(40, 46, 56),
        ThemeMode::Monokai => Color::Rgb(33, 34, 28),
        ThemeMode::GithubDark => Color::Rgb(30, 35, 41),
        ThemeMode::SolarizedLight => Color::Rgb(246, 240, 222),
        ThemeMode::QuietLight => Color::Rgb(238, 238, 238),
    }
}

pub fn local_badge_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(system_color(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn hint_style(mode: ThemeMode) -> Style {
    footer_style(mode)
}

pub fn spinner_style(mode: ThemeMode) -> Style {
    Style::default().fg(accent(mode))
}

pub fn error_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(error(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn code_block_border_style(mode: ThemeMode) -> Style {
    Style::default().fg(input_border_color(mode))
}

pub fn code_block_line_style(mode: ThemeMode, language: &str) -> Style {
    Style::default()
        .fg(code_language_color(mode, language))
        .bg(code_block_bg(mode))
}

pub fn heading_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(base_fg(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn bold_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(base_fg(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn italic_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(base_fg(mode))
        .add_modifier(Modifier::ITALIC)
}

pub fn inline_code_style(mode: ThemeMode) -> Style {
    let fg = if mode.is_dark() {
        Color::Rgb(255, 206, 125)
    } else {
        Color::Rgb(156, 83, 0)
    };
    Style::default().fg(fg)
}

pub fn link_style(mode: ThemeMode) -> Style {
    Style::default().fg(accent(mode)).add_modifier(Modifier::UNDERLINED)
}

pub fn list_bullet_style(mode: ThemeMode) -> Style {
    Style::default().fg(muted_fg(mode))
}

pub fn code_language_color(mode: ThemeMode, language: &str) -> Color {
    let normalized = language.trim().to_lowercase();
    let group = if matches!(normalized.as_str(), "python" | "py" | "ruby" | "rb" | "lua") {
        "python"
    } else if matches!(
        normalized.as_str(),
        "javascript" | "js" | "typescript" | "ts" | "tsx" | "jsx"
    ) {
        "js"
    } else if matches!(
        normalized.as_str(),
        "rust" | "rs" | "go" | "c" | "cpp" | "cc" | "h" | "hpp" | "java"
    ) {
        "systems"
    } else if matches!(
        normalized.as_str(),
        "bash" | "sh" | "zsh" | "fish" | "powershell"
    ) {
        "shell"
    } else if matches!(
        normalized.as_str(),
        "json" | "yaml" | "yml" | "toml" | "xml" | "ini" | "markdown" | "md"
    ) {
        "config"
    } else {
        "default"
    };

    // use accent for the primary language color, muted for config
    match group {
        "python" => warning(mode),
        "js" => if mode.is_dark() { Color::Rgb(226, 176, 132) } else { Color::Rgb(138, 92, 28) },
        "systems" => accent(mode),
        "shell" => success(mode),
        "config" => muted_fg(mode),
        _ => base_fg(mode),
    }
}
