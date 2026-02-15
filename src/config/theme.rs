use std::collections::HashMap;
use serde::Deserialize;
use ratatui::style::Color;

/// TUI color theme (Task 11)
#[derive(Debug, Clone)]
pub struct TuiTheme {
    pub name: String,
    pub entity_colors: HashMap<String, Color>,
    pub rel_colors: HashMap<String, Color>,
    pub timeline_bg: Color,
    pub selection: Color,
    pub text: Color,
    pub status_bg: Color,
    pub status_fg: Color,
}

impl TuiTheme {
    pub fn dark() -> Self {
        let mut entity_colors = HashMap::new();
        entity_colors.insert("character".into(), Color::Blue);
        entity_colors.insert("event".into(), Color::Red);
        entity_colors.insert("location".into(), Color::Green);
        entity_colors.insert("artifact".into(), Color::Magenta);
        entity_colors.insert("faction".into(), Color::Cyan);
        entity_colors.insert("org".into(), Color::Cyan);

        Self {
            name: "dark".into(),
            entity_colors,
            rel_colors: HashMap::new(),
            timeline_bg: Color::Reset,
            selection: Color::Yellow,
            text: Color::White,
            status_bg: Color::DarkGray,
            status_fg: Color::White,
        }
    }

    pub fn light() -> Self {
        let mut entity_colors = HashMap::new();
        entity_colors.insert("character".into(), Color::Blue);
        entity_colors.insert("event".into(), Color::Red);
        entity_colors.insert("location".into(), Color::Green);
        entity_colors.insert("artifact".into(), Color::Magenta);
        entity_colors.insert("faction".into(), Color::Cyan);
        entity_colors.insert("org".into(), Color::Cyan);

        Self {
            name: "light".into(),
            entity_colors,
            rel_colors: HashMap::new(),
            timeline_bg: Color::White,
            selection: Color::LightYellow,
            text: Color::Black,
            status_bg: Color::Gray,
            status_fg: Color::Black,
        }
    }

    pub fn entity_color(&self, entity_type: &str, connected: bool) -> Color {
        if !connected { return Color::DarkGray; }
        self.entity_colors.get(entity_type).copied().unwrap_or(self.text)
    }

    pub fn rel_color(&self, label: &str) -> Color {
        self.rel_colors.get(label).copied().unwrap_or(Color::Magenta)
    }
}

/// TOML-deserializable theme config
#[derive(Debug, Deserialize)]
pub struct ThemeConfig {
    pub name: Option<String>,
    pub entity_colors: Option<HashMap<String, String>>,
    pub rel_colors: Option<HashMap<String, String>>,
    pub selection: Option<String>,
    pub text: Option<String>,
}

impl ThemeConfig {
    pub fn to_tui_theme(&self) -> TuiTheme {
        let base = TuiTheme::dark();
        let mut theme = base;

        if let Some(ref name) = self.name {
            theme.name = name.clone();
        }
        if let Some(ref ec) = self.entity_colors {
            for (k, v) in ec {
                if let Some(c) = parse_color(v) {
                    theme.entity_colors.insert(k.clone(), c);
                }
            }
        }
        if let Some(ref rc) = self.rel_colors {
            for (k, v) in rc {
                if let Some(c) = parse_color(v) {
                    theme.rel_colors.insert(k.clone(), c);
                }
            }
        }
        if let Some(ref s) = self.selection {
            if let Some(c) = parse_color(s) { theme.selection = c; }
        }
        if let Some(ref t) = self.text {
            if let Some(c) = parse_color(t) { theme.text = c; }
        }
        theme
    }
}

fn parse_color(s: &str) -> Option<Color> {
    if s.starts_with('#') {
        let hex = &s[1..];
        match hex.len() {
            // #RGB shorthand → expand to #RRGGBB
            3 => {
                let r = u8::from_str_radix(&hex[0..1].repeat(2), 16).ok()?;
                let g = u8::from_str_radix(&hex[1..2].repeat(2), 16).ok()?;
                let b = u8::from_str_radix(&hex[2..3].repeat(2), 16).ok()?;
                return Some(Color::Rgb(r, g, b));
            }
            // #RRGGBB standard
            6 => {
                let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
                let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
                let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
                return Some(Color::Rgb(r, g, b));
            }
            // #RRGGBBAA with alpha (alpha ignored for terminal)
            8 => {
                let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
                let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
                let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
                // alpha byte hex[6..8] ignored
                return Some(Color::Rgb(r, g, b));
            }
            _ => return None,
        }
    }
    match s.to_lowercase().as_str() {
        "black" => Some(Color::Black),
        "red" => Some(Color::Red),
        "green" => Some(Color::Green),
        "yellow" => Some(Color::Yellow),
        "blue" => Some(Color::Blue),
        "magenta" => Some(Color::Magenta),
        "cyan" => Some(Color::Cyan),
        "white" => Some(Color::White),
        "gray" | "grey" => Some(Color::Gray),
        "darkgray" | "darkgrey" => Some(Color::DarkGray),
        _ => None,
    }
}
