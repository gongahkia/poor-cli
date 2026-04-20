//! Configuration file system: loads and provides typed access to Wok settings.

use std::path::{Path, PathBuf};

use serde::Deserialize;
use tracing::warn;

use wok_terminal::shell::ShellType;
use wok_ui::layout_presets::{LayoutPreset, PresetNode};
use wok_ui::splits::SplitDirection;

/// Cursor display style.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum CursorStyle {
    /// Filled block cursor.
    Block,
    /// Thin vertical bar.
    Bar,
    /// Underline cursor.
    Underline,
}

/// Command-entry routing mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum CommandEntryMode {
    /// Send typing directly to the PTY-backed shell prompt.
    ShellNative,
    /// Use Wok's owned input editor whenever the shell is idle at a prompt.
    OwnedPrimary,
}

/// Trigger scope loaded from config.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum TriggerScopeConfig {
    /// Evaluate trigger against command output.
    #[default]
    Output,
    /// Evaluate trigger against command text.
    Command,
    /// Evaluate trigger against both command and output.
    Both,
}

/// A regex trigger loaded from configuration.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TriggerConfig {
    /// Trigger display name.
    pub name: String,
    /// Regex pattern.
    pub pattern: String,
    /// Action descriptors.
    pub actions: Vec<String>,
    /// Trigger evaluation scope.
    pub scope: TriggerScopeConfig,
}

/// Complete Wok configuration.
#[derive(Debug, Clone)]
pub struct WokConfig {
    /// Shell to use.
    pub shell: ShellType,
    /// Path to the theme file.
    pub theme_path: Option<PathBuf>,
    /// Font family name.
    pub font_family: String,
    /// Font size in points.
    pub font_size: f32,
    /// Input editor position.
    pub input_position: InputPosition,
    /// Command-entry routing mode.
    pub command_entry_mode: CommandEntryMode,
    /// Scrollback line count.
    pub scrollback_lines: usize,
    /// Cursor display style.
    pub cursor_style: CursorStyle,
    /// Whether the cursor blinks.
    pub cursor_blink: bool,
    /// Whether the tab bar is visible.
    pub tab_bar_visible: bool,
    /// Whether the status bar is visible.
    pub status_bar_visible: bool,
    /// Window opacity (0.0 to 1.0).
    pub window_opacity: f32,
    /// Background image path.
    pub background_image: Option<PathBuf>,
    /// Optional out-of-process plugin bridge command.
    pub external_plugin_command: Option<String>,
    /// Copy text to clipboard on selection.
    pub copy_on_select: bool,
    /// Ask before closing with running processes.
    pub confirm_close_with_running_process: bool,
    /// Whether to restore sessions on startup.
    pub restore_session: bool,
    /// Whether to show the internal debug overlay.
    pub debug_overlay: bool,
    /// Regex triggers loaded from config.
    pub triggers: Vec<TriggerConfig>,
    /// Custom layout presets loaded from config.
    pub layout_presets: Vec<LayoutPreset>,
}

/// Input editor position.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum InputPosition {
    /// Above the terminal viewport.
    Top,
    /// Below the terminal viewport.
    Bottom,
}

/// TOML config with optional fields.
#[derive(Debug, Default, Deserialize)]
struct ConfigToml {
    shell: Option<String>,
    theme_path: Option<String>,
    font_family: Option<String>,
    font_size: Option<f32>,
    input_position: Option<String>,
    command_entry_mode: Option<String>,
    scrollback_lines: Option<usize>,
    cursor_style: Option<String>,
    cursor_blink: Option<bool>,
    tab_bar_visible: Option<bool>,
    status_bar_visible: Option<bool>,
    window_opacity: Option<f32>,
    background_image: Option<String>,
    external_plugin_command: Option<String>,
    copy_on_select: Option<bool>,
    confirm_close_with_running_process: Option<bool>,
    restore_session: Option<bool>,
    debug_overlay: Option<bool>,
    triggers: Option<Vec<TriggerToml>>,
    layouts: Option<Vec<LayoutToml>>,
}

/// TOML trigger section.
#[derive(Debug, Default, Deserialize)]
struct TriggerToml {
    name: Option<String>,
    pattern: Option<String>,
    actions: Option<Vec<String>>,
    scope: Option<String>,
}

/// TOML layout preset section.
#[derive(Debug, Deserialize)]
struct LayoutToml {
    name: String,
    description: Option<String>,
    tree: PresetNodeToml,
}

#[derive(Debug, Deserialize)]
#[serde(untagged)]
enum PresetNodeToml {
    Leaf {
        leaf: Option<bool>,
        weight: Option<f64>,
    },
    Split {
        split: String,
        ratio: Option<f64>,
        children: Vec<PresetNodeToml>,
    },
}

impl Default for WokConfig {
    fn default() -> Self {
        Self {
            shell: wok_terminal::shell::detect_default_shell(),
            theme_path: None,
            font_family: "JetBrains Mono".to_string(),
            font_size: 24.0,
            input_position: InputPosition::Bottom,
            command_entry_mode: CommandEntryMode::ShellNative,
            scrollback_lines: 10_000,
            cursor_style: CursorStyle::Block,
            cursor_blink: true,
            tab_bar_visible: true,
            status_bar_visible: true,
            window_opacity: 1.0,
            background_image: None,
            external_plugin_command: None,
            copy_on_select: false,
            confirm_close_with_running_process: true,
            restore_session: false,
            debug_overlay: false,
            triggers: Vec::new(),
            layout_presets: Vec::new(),
        }
    }
}

impl WokConfig {
    /// Load configuration from the standard search paths.
    ///
    /// Search order: `$WOK_CONFIG`, `~/.config/wok/config.toml`, `~/.wok.toml`.
    pub fn load() -> Self {
        let paths = config_search_paths();
        for path in &paths {
            if path.exists() {
                match Self::load_from(path) {
                    Ok(config) => return config,
                    Err(e) => {
                        warn!("failed to load config from {}: {e}", path.display());
                    }
                }
            }
        }
        Self::default()
    }

    /// Load configuration from a specific file.
    fn load_from(path: &Path) -> Result<Self, Box<dyn std::error::Error>> {
        let content = std::fs::read_to_string(path)?;
        let toml_config: ConfigToml = toml::from_str(&content)?;
        let mut config = Self::default();

        if let Some(shell) = toml_config.shell {
            config.shell = parse_shell_config(&shell, &config.shell);
        }
        if let Some(p) = toml_config.theme_path {
            config.theme_path = Some(PathBuf::from(p));
        }
        if let Some(f) = toml_config.font_family {
            config.font_family = f;
        }
        if let Some(s) = toml_config.font_size {
            config.font_size = s;
        }
        if let Some(p) = toml_config.input_position {
            config.input_position = match p.as_str() {
                "top" => InputPosition::Top,
                _ => InputPosition::Bottom,
            };
        }
        if let Some(mode) = toml_config.command_entry_mode {
            config.command_entry_mode = match mode.as_str() {
                "owned_primary" => CommandEntryMode::OwnedPrimary,
                _ => CommandEntryMode::ShellNative,
            };
        }
        if let Some(s) = toml_config.scrollback_lines {
            config.scrollback_lines = s;
        }
        if let Some(s) = toml_config.cursor_style {
            config.cursor_style = match s.as_str() {
                "bar" => CursorStyle::Bar,
                "underline" => CursorStyle::Underline,
                _ => CursorStyle::Block,
            };
        }
        if let Some(b) = toml_config.cursor_blink {
            config.cursor_blink = b;
        }
        if let Some(v) = toml_config.tab_bar_visible {
            config.tab_bar_visible = v;
        }
        if let Some(v) = toml_config.status_bar_visible {
            config.status_bar_visible = v;
        }
        if let Some(o) = toml_config.window_opacity {
            config.window_opacity = o;
        }
        if let Some(p) = toml_config.background_image {
            config.background_image = Some(PathBuf::from(p));
        }
        if let Some(command) = toml_config.external_plugin_command {
            let trimmed = command.trim();
            if !trimmed.is_empty() {
                config.external_plugin_command = Some(trimmed.to_string());
            }
        }
        if let Some(c) = toml_config.copy_on_select {
            config.copy_on_select = c;
        }
        if let Some(c) = toml_config.confirm_close_with_running_process {
            config.confirm_close_with_running_process = c;
        }
        if let Some(r) = toml_config.restore_session {
            config.restore_session = r;
        }
        if let Some(debug_overlay) = toml_config.debug_overlay {
            config.debug_overlay = debug_overlay;
        }
        if let Some(triggers) = toml_config.triggers {
            config.triggers = triggers
                .into_iter()
                .filter_map(|trigger| {
                    let name = trigger.name?.trim().to_string();
                    let pattern = trigger.pattern?.trim().to_string();
                    if name.is_empty() || pattern.is_empty() {
                        return None;
                    }
                    let actions = trigger.actions.unwrap_or_default();
                    let scope = match trigger
                        .scope
                        .as_deref()
                        .map(str::trim)
                        .map(str::to_ascii_lowercase)
                        .as_deref()
                    {
                        Some("command") => TriggerScopeConfig::Command,
                        Some("both") => TriggerScopeConfig::Both,
                        _ => TriggerScopeConfig::Output,
                    };
                    Some(TriggerConfig {
                        name,
                        pattern,
                        actions,
                        scope,
                    })
                })
                .collect();
        }
        if let Some(layouts) = toml_config.layouts {
            config.layout_presets = layouts
                .into_iter()
                .filter_map(|layout| {
                    let name = layout.name.trim().to_string();
                    if name.is_empty() {
                        return None;
                    }
                    let tree = preset_node_from_toml(layout.tree)?;
                    Some(LayoutPreset {
                        name,
                        description: layout.description.unwrap_or_default(),
                        tree,
                    })
                })
                .collect();
        }

        Ok(config)
    }

    /// Return the platform-appropriate config directory.
    pub fn config_dir() -> PathBuf {
        #[cfg(unix)]
        {
            std::env::var("HOME")
                .map(|h| PathBuf::from(h).join(".config").join("wok"))
                .unwrap_or_else(|_| PathBuf::from(".config/wok"))
        }
        #[cfg(windows)]
        {
            std::env::var("APPDATA")
                .map(|a| PathBuf::from(a).join("Wok"))
                .unwrap_or_else(|_| PathBuf::from("Wok"))
        }
    }
}

fn config_search_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();

    if let Ok(p) = std::env::var("WOK_CONFIG") {
        paths.push(PathBuf::from(p));
    }

    let config_dir = WokConfig::config_dir();
    paths.push(config_dir.join("config.toml"));

    if let Ok(home) = std::env::var("HOME") {
        paths.push(PathBuf::from(home).join(".wok.toml"));
    }

    paths
}

fn parse_shell_config(value: &str, fallback: &ShellType) -> ShellType {
    if let Some(distro) = value.strip_prefix("wsl:") {
        if !distro.trim().is_empty() {
            return ShellType::Wsl(distro.trim().to_string());
        }
    }

    match value {
        "bash" => ShellType::Bash,
        "zsh" => ShellType::Zsh,
        "fish" => ShellType::Fish,
        "powershell" => ShellType::PowerShell,
        _ => fallback.clone(),
    }
}

fn preset_node_from_toml(node: PresetNodeToml) -> Option<PresetNode> {
    match node {
        PresetNodeToml::Leaf { leaf, weight } => {
            if leaf.is_some_and(|value| !value) {
                return None;
            }
            Some(PresetNode::Leaf {
                weight: weight.unwrap_or(1.0),
            })
        }
        PresetNodeToml::Split {
            split,
            ratio,
            children,
        } => {
            let direction = match split.trim().to_ascii_lowercase().as_str() {
                "vertical" => SplitDirection::Horizontal,
                "horizontal" => SplitDirection::Vertical,
                _ => return None,
            };
            let children = children
                .into_iter()
                .filter_map(preset_node_from_toml)
                .collect::<Vec<_>>();
            if children.is_empty() {
                return None;
            }
            Some(PresetNode::Split {
                direction,
                ratio: ratio.unwrap_or(0.5),
                children,
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = WokConfig::default();
        assert!((config.font_size - 24.0).abs() < f32::EPSILON);
        assert_eq!(config.scrollback_lines, 10_000);
        assert_eq!(config.cursor_style, CursorStyle::Block);
        assert_eq!(config.input_position, InputPosition::Bottom);
        assert_eq!(config.command_entry_mode, CommandEntryMode::ShellNative);
    }

    #[test]
    fn test_load_with_no_file() {
        let config = WokConfig::load();
        // Should return defaults without error
        assert!((config.font_size - 24.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_config_dir() {
        let dir = WokConfig::config_dir();
        assert!(!dir.to_str().unwrap().is_empty());
    }

    #[test]
    fn test_parse_shell_config_supports_wsl() {
        let shell = parse_shell_config("wsl:Ubuntu", &ShellType::Bash);
        assert_eq!(shell, ShellType::Wsl("Ubuntu".to_string()));
    }

    #[test]
    fn test_command_entry_mode_defaults_to_shell_native() {
        let config = WokConfig::default();
        assert_eq!(config.command_entry_mode, CommandEntryMode::ShellNative);
    }
}
