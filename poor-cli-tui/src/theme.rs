/// Color theme constants matching Claude Code / Codex aesthetic.
///
/// Dark backgrounds, cyan/green accents for roles, dim borders for panels.
use ratatui::style::{Color, Modifier, Style};

// ── Base palette ──────────────────────────────────────────────────────
pub const BG: Color = Color::Reset; // use terminal default
pub const FG: Color = Color::White;
pub const DIM: Color = Color::DarkGray;
pub const ACCENT: Color = Color::Cyan;
pub const SUCCESS: Color = Color::Green;
pub const WARNING: Color = Color::Yellow;
pub const ERROR: Color = Color::Red;
pub const MAGENTA: Color = Color::Magenta;

// ── Role colors ───────────────────────────────────────────────────────
pub const USER_COLOR: Color = Color::Cyan;
pub const ASSISTANT_COLOR: Color = Color::Rgb(80, 200, 120);
pub const SYSTEM_COLOR: Color = Color::Magenta;
pub const TOOL_COLOR: Color = Color::DarkGray;

// ── Pre-built styles ─────────────────────────────────────────────────
pub fn status_bar_style() -> Style {
    Style::default().fg(Color::White).bg(Color::Rgb(30, 30, 50))
}

pub fn user_label_style() -> Style {
    Style::default().fg(USER_COLOR).add_modifier(Modifier::BOLD)
}

pub fn assistant_label_style() -> Style {
    Style::default()
        .fg(ASSISTANT_COLOR)
        .add_modifier(Modifier::BOLD)
}

pub fn tool_border_style() -> Style {
    Style::default().fg(DIM)
}

pub fn tool_title_style() -> Style {
    Style::default().fg(Color::DarkGray)
}

pub fn input_style() -> Style {
    Style::default().fg(FG)
}

pub fn input_cursor_style() -> Style {
    Style::default().fg(Color::Black).bg(Color::Rgb(100, 200, 255))
}

pub fn code_block_bg() -> Color {
    Color::Rgb(30, 32, 40)
}

pub fn local_badge_style() -> Style {
    Style::default().fg(Color::Magenta).add_modifier(Modifier::BOLD)
}

pub fn hint_style() -> Style {
    Style::default().fg(DIM)
}

pub fn spinner_style() -> Style {
    Style::default().fg(ACCENT)
}

pub fn error_style() -> Style {
    Style::default().fg(ERROR).add_modifier(Modifier::BOLD)
}

pub fn code_block_border_style() -> Style {
    Style::default().fg(Color::Rgb(80, 80, 100))
}

pub fn heading_style() -> Style {
    Style::default()
        .fg(Color::White)
        .add_modifier(Modifier::BOLD)
}

pub fn bold_style() -> Style {
    Style::default().add_modifier(Modifier::BOLD)
}

pub fn italic_style() -> Style {
    Style::default().add_modifier(Modifier::ITALIC)
}

pub fn inline_code_style() -> Style {
    Style::default().fg(Color::Rgb(230, 180, 100))
}

pub fn link_style() -> Style {
    Style::default()
        .fg(Color::Rgb(100, 160, 255))
        .add_modifier(Modifier::UNDERLINED)
}

pub fn list_bullet_style() -> Style {
    Style::default().fg(DIM)
}
