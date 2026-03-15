/// Theme-aware style helpers for the poor-cli TUI.
use crate::app::ThemeMode;
use ratatui::style::{Color, Modifier, Style};

pub fn app_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(52, 56, 60),
        ThemeMode::Light => Color::Rgb(243, 240, 232),
    }
}

pub fn surface_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(60, 64, 69),
        ThemeMode::Light => Color::Rgb(235, 231, 221),
    }
}

pub fn elevated_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(66, 71, 76),
        ThemeMode::Light => Color::Rgb(227, 223, 214),
    }
}

pub fn base_fg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(229, 218, 193),
        ThemeMode::Light => Color::Rgb(45, 43, 40),
    }
}

pub fn muted_fg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(149, 145, 137),
        ThemeMode::Light => Color::Rgb(121, 115, 105),
    }
}

pub fn accent(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(137, 205, 152),
        ThemeMode::Light => Color::Rgb(45, 138, 86),
    }
}

pub fn success(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(166, 218, 168),
        ThemeMode::Light => Color::Rgb(36, 124, 74),
    }
}

pub fn warning(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(220, 199, 149),
        ThemeMode::Light => Color::Rgb(155, 117, 24),
    }
}

pub fn error(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(235, 129, 122),
        ThemeMode::Light => Color::Rgb(176, 72, 67),
    }
}

pub fn user_color(mode: ThemeMode) -> Color {
    warning(mode)
}

pub fn assistant_color(mode: ThemeMode) -> Color {
    accent(mode)
}

pub fn system_color(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(191, 181, 145),
        ThemeMode::Light => Color::Rgb(123, 111, 74),
    }
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
    match mode {
        ThemeMode::Dark => Style::default()
            .fg(Color::Black)
            .bg(Color::Rgb(100, 200, 255)),
        ThemeMode::Light => Style::default()
            .fg(Color::White)
            .bg(Color::Rgb(0, 122, 204)),
    }
}

pub fn input_border_color(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(88, 91, 96),
        ThemeMode::Light => Color::Rgb(176, 168, 154),
    }
}

pub fn code_block_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(46, 49, 54),
        ThemeMode::Light => Color::Rgb(239, 235, 226),
    }
}

pub fn local_badge_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(system_color(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn hint_style(mode: ThemeMode) -> Style {
    Style::default().fg(muted_fg(mode)).bg(app_bg(mode))
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
    let fg = match mode {
        ThemeMode::Dark => Color::Rgb(255, 206, 125),
        ThemeMode::Light => Color::Rgb(156, 83, 0),
    };
    Style::default().fg(fg)
}

pub fn link_style(mode: ThemeMode) -> Style {
    let fg = match mode {
        ThemeMode::Dark => Color::Rgb(127, 181, 255),
        ThemeMode::Light => Color::Rgb(0, 92, 173),
    };
    Style::default().fg(fg).add_modifier(Modifier::UNDERLINED)
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

    match (mode, group) {
        (ThemeMode::Dark, "python") => Color::Rgb(224, 208, 150),
        (ThemeMode::Dark, "js") => Color::Rgb(226, 176, 132),
        (ThemeMode::Dark, "systems") => Color::Rgb(145, 184, 227),
        (ThemeMode::Dark, "shell") => Color::Rgb(151, 209, 160),
        (ThemeMode::Dark, "config") => Color::Rgb(190, 185, 172),
        (ThemeMode::Dark, "default") => Color::Rgb(224, 217, 203),
        (ThemeMode::Light, "python") => Color::Rgb(121, 89, 20),
        (ThemeMode::Light, "js") => Color::Rgb(138, 92, 28),
        (ThemeMode::Light, "systems") => Color::Rgb(58, 95, 138),
        (ThemeMode::Light, "shell") => Color::Rgb(48, 119, 74),
        (ThemeMode::Light, "config") => Color::Rgb(93, 88, 80),
        (ThemeMode::Light, "default") => Color::Rgb(55, 52, 47),
        _ => base_fg(mode),
    }
}
