/// Theme-aware style helpers for the poor-cli TUI.
use crate::app::ThemeMode;
use ratatui::style::{Color, Modifier, Style};

pub fn base_fg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(232, 235, 242),
        ThemeMode::Light => Color::Rgb(26, 33, 41),
    }
}

pub fn muted_fg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(122, 129, 141),
        ThemeMode::Light => Color::Rgb(110, 118, 133),
    }
}

pub fn accent(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(94, 194, 255),
        ThemeMode::Light => Color::Rgb(0, 106, 184),
    }
}

pub fn success(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(114, 219, 139),
        ThemeMode::Light => Color::Rgb(23, 128, 74),
    }
}

pub fn warning(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(244, 209, 96),
        ThemeMode::Light => Color::Rgb(156, 116, 11),
    }
}

pub fn error(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(255, 112, 112),
        ThemeMode::Light => Color::Rgb(184, 42, 42),
    }
}

pub fn user_color(mode: ThemeMode) -> Color {
    accent(mode)
}

pub fn assistant_color(mode: ThemeMode) -> Color {
    success(mode)
}

pub fn system_color(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(209, 141, 255),
        ThemeMode::Light => Color::Rgb(123, 74, 191),
    }
}

pub fn status_bar_style(mode: ThemeMode) -> Style {
    let bg = match mode {
        ThemeMode::Dark => Color::Rgb(23, 26, 36),
        ThemeMode::Light => Color::Rgb(232, 239, 248),
    };
    Style::default().fg(base_fg(mode)).bg(bg)
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
    Style::default().fg(muted_fg(mode))
}

pub fn tool_title_style(mode: ThemeMode) -> Style {
    let fg = match mode {
        ThemeMode::Dark => Color::Rgb(167, 175, 188),
        ThemeMode::Light => Color::Rgb(92, 100, 114),
    };
    Style::default().fg(fg)
}

pub fn input_style(mode: ThemeMode) -> Style {
    Style::default().fg(base_fg(mode))
}

pub fn input_cursor_style(mode: ThemeMode) -> Style {
    match mode {
        ThemeMode::Dark => Style::default().fg(Color::Black).bg(Color::Rgb(100, 200, 255)),
        ThemeMode::Light => Style::default().fg(Color::White).bg(Color::Rgb(0, 122, 204)),
    }
}

pub fn input_border_color(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(50, 50, 70),
        ThemeMode::Light => Color::Rgb(171, 184, 199),
    }
}

pub fn code_block_bg(mode: ThemeMode) -> Color {
    match mode {
        ThemeMode::Dark => Color::Rgb(27, 31, 42),
        ThemeMode::Light => Color::Rgb(243, 247, 252),
    }
}

pub fn local_badge_style(mode: ThemeMode) -> Style {
    Style::default()
        .fg(system_color(mode))
        .add_modifier(Modifier::BOLD)
}

pub fn hint_style(mode: ThemeMode) -> Style {
    Style::default().fg(muted_fg(mode))
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
    let fg = match mode {
        ThemeMode::Dark => Color::Rgb(84, 92, 112),
        ThemeMode::Light => Color::Rgb(156, 168, 184),
    };
    Style::default().fg(fg)
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
    let group = if matches!(
        normalized.as_str(),
        "python" | "py" | "ruby" | "rb" | "lua"
    ) {
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
        (ThemeMode::Dark, "python") => Color::Rgb(247, 228, 147),
        (ThemeMode::Dark, "js") => Color::Rgb(247, 188, 120),
        (ThemeMode::Dark, "systems") => Color::Rgb(133, 192, 255),
        (ThemeMode::Dark, "shell") => Color::Rgb(137, 229, 160),
        (ThemeMode::Dark, "config") => Color::Rgb(179, 194, 213),
        (ThemeMode::Dark, "default") => Color::Rgb(219, 224, 233),
        (ThemeMode::Light, "python") => Color::Rgb(121, 82, 0),
        (ThemeMode::Light, "js") => Color::Rgb(143, 76, 11),
        (ThemeMode::Light, "systems") => Color::Rgb(10, 89, 161),
        (ThemeMode::Light, "shell") => Color::Rgb(25, 117, 66),
        (ThemeMode::Light, "config") => Color::Rgb(75, 89, 105),
        (ThemeMode::Light, "default") => Color::Rgb(39, 46, 57),
        _ => base_fg(mode),
    }
}
