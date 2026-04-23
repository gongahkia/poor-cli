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

/// Tab bar layout direction.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum TabBarOrientation {
    /// Render tabs across the top of the window.
    Horizontal,
    /// Render tabs stacked along the left side of the window.
    Vertical,
}

/// A side of the app chrome where a bar or overlay can be placed.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum ChromeSide {
    /// Top edge.
    Top,
    /// Bottom edge.
    Bottom,
    /// Left edge.
    Left,
    /// Right edge.
    Right,
}

impl ChromeSide {
    /// Return whether this side should use a horizontal layout.
    pub fn is_horizontal(self) -> bool {
        matches!(self, Self::Top | Self::Bottom)
    }

    /// Return the tab orientation implied by this side.
    pub fn tab_orientation(self) -> TabBarOrientation {
        if self.is_horizontal() {
            TabBarOrientation::Horizontal
        } else {
            TabBarOrientation::Vertical
        }
    }

    /// Return the stable config label for this side.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Top => "top",
            Self::Bottom => "bottom",
            Self::Left => "left",
            Self::Right => "right",
        }
    }
}

/// Position for small floating overlays.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum OverlayPosition {
    /// Top-left corner of the workspace content area.
    TopLeft,
    /// Top-right corner of the workspace content area.
    TopRight,
    /// Bottom-left corner of the workspace content area.
    BottomLeft,
    /// Bottom-right corner of the workspace content area.
    BottomRight,
}

impl OverlayPosition {
    /// Return the stable config label for this position.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::TopLeft => "top_left",
            Self::TopRight => "top_right",
            Self::BottomLeft => "bottom_left",
            Self::BottomRight => "bottom_right",
        }
    }
}

/// How a background image should be sized inside the window.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum BackgroundFit {
    /// Stretch the image to fill the full background rect.
    Stretch,
    /// Preserve aspect ratio and cover the full background rect.
    Cover,
    /// Preserve aspect ratio and fit the whole image inside the background rect.
    Contain,
    /// Render the image at its intrinsic pixel size or configured size.
    Center,
}

/// Anchor point for a background image that does not fill the full rect.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum BackgroundPosition {
    /// Center of the background rect.
    Center,
    /// Top-left corner.
    TopLeft,
    /// Top-right corner.
    TopRight,
    /// Bottom-left corner.
    BottomLeft,
    /// Bottom-right corner.
    BottomRight,
}

/// Recent key visualizer configuration.
#[derive(Debug, Clone, PartialEq)]
pub struct RecentKeysConfig {
    /// Whether to render recent key presses.
    pub visible: bool,
    /// Overlay position.
    pub position: OverlayPosition,
    /// Maximum number of recent key labels to retain.
    pub max_entries: usize,
    /// How long a key label stays visible.
    pub timeout_ms: u64,
    /// Overlay opacity.
    pub opacity: f32,
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
    /// Side where the tab bar is rendered.
    pub tab_bar_side: ChromeSide,
    /// Whether tabs are rendered horizontally or vertically.
    pub tab_bar_orientation: TabBarOrientation,
    /// Optional tab bar thickness in physical pixels.
    pub tab_bar_size: Option<f32>,
    /// Whether the status bar is visible.
    pub status_bar_visible: bool,
    /// Side where the status bar is rendered.
    pub status_bar_side: ChromeSide,
    /// Optional status bar thickness in physical pixels.
    pub status_bar_size: Option<f32>,
    /// Window opacity (0.0 to 1.0).
    pub window_opacity: f32,
    /// Background image path.
    pub background_image: Option<PathBuf>,
    /// Background image opacity.
    pub background_opacity: f32,
    /// Background image sizing mode.
    pub background_fit: BackgroundFit,
    /// Background image anchor position.
    pub background_position: BackgroundPosition,
    /// Optional background image render width in physical pixels.
    pub background_width: Option<f32>,
    /// Optional background image render height in physical pixels.
    pub background_height: Option<f32>,
    /// Optional terminal pane background opacity override.
    pub terminal_background_opacity: Option<f32>,
    /// Split pane border width.
    pub pane_border_width: f32,
    /// Focused split pane border width.
    pub focused_pane_border_width: f32,
    /// Floating pane title height.
    pub floating_pane_title_height: f32,
    /// Optional out-of-process plugin bridge command.
    pub external_plugin_command: Option<String>,
    /// Copy text to clipboard on selection.
    pub copy_on_select: bool,
    /// Ask before closing with running processes.
    pub confirm_close_with_running_process: bool,
    /// Close panes, tabs, or the app when their shell process exits.
    pub close_on_shell_exit: bool,
    /// Whether to restore sessions on startup.
    pub restore_session: bool,
    /// Whether to show the internal debug overlay.
    pub debug_overlay: bool,
    /// Whether to write command lifecycle telemetry to disk.
    pub command_telemetry: bool,
    /// Recent key visualizer settings.
    pub recent_keys: RecentKeysConfig,
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
    tab_bar_side: Option<String>,
    tab_bar_orientation: Option<String>,
    tab_bar_size: Option<f32>,
    status_bar_visible: Option<bool>,
    status_bar_side: Option<String>,
    status_bar_size: Option<f32>,
    window_opacity: Option<f32>,
    background_image: Option<String>,
    background_opacity: Option<f32>,
    background_fit: Option<String>,
    background_position: Option<String>,
    background_width: Option<f32>,
    background_height: Option<f32>,
    terminal_background_opacity: Option<f32>,
    pane_border_width: Option<f32>,
    focused_pane_border_width: Option<f32>,
    floating_pane_title_height: Option<f32>,
    external_plugin_command: Option<String>,
    copy_on_select: Option<bool>,
    confirm_close_with_running_process: Option<bool>,
    close_on_shell_exit: Option<bool>,
    restore_session: Option<bool>,
    debug_overlay: Option<bool>,
    command_telemetry: Option<bool>,
    recent_keys_visible: Option<bool>,
    recent_keys_position: Option<String>,
    recent_keys_max_entries: Option<usize>,
    recent_keys_timeout_ms: Option<u64>,
    recent_keys_opacity: Option<f32>,
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
            font_family: default_font_family().to_string(),
            font_size: 24.0,
            input_position: InputPosition::Bottom,
            command_entry_mode: CommandEntryMode::ShellNative,
            scrollback_lines: 10_000,
            cursor_style: CursorStyle::Block,
            cursor_blink: true,
            tab_bar_visible: true,
            tab_bar_side: ChromeSide::Top,
            tab_bar_orientation: TabBarOrientation::Horizontal,
            tab_bar_size: None,
            status_bar_visible: true,
            status_bar_side: ChromeSide::Bottom,
            status_bar_size: None,
            window_opacity: 1.0,
            background_image: None,
            background_opacity: 1.0,
            background_fit: BackgroundFit::Stretch,
            background_position: BackgroundPosition::Center,
            background_width: None,
            background_height: None,
            terminal_background_opacity: None,
            pane_border_width: 1.0,
            focused_pane_border_width: 2.0,
            floating_pane_title_height: 18.0,
            external_plugin_command: None,
            copy_on_select: false,
            confirm_close_with_running_process: true,
            close_on_shell_exit: true,
            restore_session: false,
            debug_overlay: false,
            command_telemetry: false,
            recent_keys: RecentKeysConfig {
                visible: true,
                position: OverlayPosition::BottomRight,
                max_entries: 8,
                timeout_ms: 2_000,
                opacity: 0.86,
            },
            triggers: Vec::new(),
            layout_presets: Vec::new(),
        }
    }
}

fn default_font_family() -> &'static str {
    #[cfg(target_os = "macos")]
    {
        "Menlo"
    }
    #[cfg(not(target_os = "macos"))]
    {
        "JetBrains Mono"
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
        if let Some(orientation) = toml_config.tab_bar_orientation {
            config.tab_bar_side = match orientation.trim().to_ascii_lowercase().as_str() {
                "vertical" | "left" => ChromeSide::Left,
                "right" => ChromeSide::Right,
                "bottom" => ChromeSide::Bottom,
                _ => ChromeSide::Top,
            };
            config.tab_bar_orientation = config.tab_bar_side.tab_orientation();
        }
        if let Some(side) = toml_config.tab_bar_side {
            if let Some(side) = parse_chrome_side(&side) {
                config.tab_bar_side = side;
                config.tab_bar_orientation = side.tab_orientation();
            }
        }
        if let Some(size) = toml_config.tab_bar_size {
            if size.is_finite() && size > 0.0 {
                config.tab_bar_size = Some(size);
            }
        }
        if let Some(v) = toml_config.status_bar_visible {
            config.status_bar_visible = v;
        }
        if let Some(side) = toml_config.status_bar_side {
            if let Some(side) = parse_chrome_side(&side) {
                config.status_bar_side = side;
            }
        }
        if let Some(size) = toml_config.status_bar_size {
            if size.is_finite() && size > 0.0 {
                config.status_bar_size = Some(size);
            }
        }
        if let Some(o) = toml_config.window_opacity {
            config.window_opacity = clamp_unit(o);
        }
        if let Some(p) = toml_config.background_image {
            let trimmed = p.trim();
            config.background_image = (!trimmed.is_empty()).then(|| PathBuf::from(trimmed));
        }
        if let Some(opacity) = toml_config.background_opacity {
            config.background_opacity = clamp_unit(opacity);
        }
        if let Some(fit) = toml_config.background_fit {
            config.background_fit = parse_background_fit(&fit);
        }
        if let Some(position) = toml_config.background_position {
            config.background_position = parse_background_position(&position);
        }
        if let Some(width) = toml_config.background_width {
            config.background_width = finite_positive(width);
        }
        if let Some(height) = toml_config.background_height {
            config.background_height = finite_positive(height);
        }
        if let Some(opacity) = toml_config.terminal_background_opacity {
            config.terminal_background_opacity = Some(clamp_unit(opacity));
        }
        if let Some(width) = toml_config.pane_border_width {
            config.pane_border_width = finite_non_negative(width).unwrap_or(0.0);
        }
        if let Some(width) = toml_config.focused_pane_border_width {
            config.focused_pane_border_width = finite_non_negative(width).unwrap_or(0.0);
        }
        if let Some(height) = toml_config.floating_pane_title_height {
            config.floating_pane_title_height = finite_non_negative(height).unwrap_or(0.0);
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
        if let Some(c) = toml_config.close_on_shell_exit {
            config.close_on_shell_exit = c;
        }
        if let Some(r) = toml_config.restore_session {
            config.restore_session = r;
        }
        if let Some(debug_overlay) = toml_config.debug_overlay {
            config.debug_overlay = debug_overlay;
        }
        if let Some(command_telemetry) = toml_config.command_telemetry {
            config.command_telemetry = command_telemetry;
        }
        if let Some(visible) = toml_config.recent_keys_visible {
            config.recent_keys.visible = visible;
        }
        if let Some(position) = toml_config.recent_keys_position {
            if let Some(position) = parse_overlay_position(&position) {
                config.recent_keys.position = position;
            }
        }
        if let Some(max_entries) = toml_config.recent_keys_max_entries {
            config.recent_keys.max_entries = max_entries.min(64);
        }
        if let Some(timeout_ms) = toml_config.recent_keys_timeout_ms {
            config.recent_keys.timeout_ms = timeout_ms.clamp(250, 30_000);
        }
        if let Some(opacity) = toml_config.recent_keys_opacity {
            if opacity.is_finite() {
                config.recent_keys.opacity = opacity.clamp(0.0, 1.0);
            }
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

fn parse_chrome_side(value: &str) -> Option<ChromeSide> {
    match value.trim().to_ascii_lowercase().as_str() {
        "top" => Some(ChromeSide::Top),
        "bottom" => Some(ChromeSide::Bottom),
        "left" => Some(ChromeSide::Left),
        "right" => Some(ChromeSide::Right),
        _ => None,
    }
}

fn parse_overlay_position(value: &str) -> Option<OverlayPosition> {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "top_left" | "left_top" => Some(OverlayPosition::TopLeft),
        "top_right" | "right_top" => Some(OverlayPosition::TopRight),
        "bottom_left" | "left_bottom" => Some(OverlayPosition::BottomLeft),
        "bottom_right" | "right_bottom" => Some(OverlayPosition::BottomRight),
        _ => None,
    }
}

fn parse_background_fit(value: &str) -> BackgroundFit {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "cover" => BackgroundFit::Cover,
        "contain" | "fit" => BackgroundFit::Contain,
        "center" | "actual" | "actual_size" => BackgroundFit::Center,
        _ => BackgroundFit::Stretch,
    }
}

fn parse_background_position(value: &str) -> BackgroundPosition {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "top_left" | "left_top" => BackgroundPosition::TopLeft,
        "top_right" | "right_top" => BackgroundPosition::TopRight,
        "bottom_left" | "left_bottom" => BackgroundPosition::BottomLeft,
        "bottom_right" | "right_bottom" => BackgroundPosition::BottomRight,
        _ => BackgroundPosition::Center,
    }
}

fn clamp_unit(value: f32) -> f32 {
    if value.is_finite() {
        value.clamp(0.0, 1.0)
    } else {
        1.0
    }
}

fn finite_positive(value: f32) -> Option<f32> {
    (value.is_finite() && value > 0.0).then_some(value)
}

fn finite_non_negative(value: f32) -> Option<f32> {
    (value.is_finite() && value >= 0.0).then_some(value)
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
        assert_eq!(config.tab_bar_side, ChromeSide::Top);
        assert_eq!(config.tab_bar_orientation, TabBarOrientation::Horizontal);
        assert_eq!(config.status_bar_side, ChromeSide::Bottom);
        assert!(config.close_on_shell_exit);
        assert!(config.recent_keys.visible);
        assert_eq!(config.recent_keys.position, OverlayPosition::BottomRight);
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

    #[test]
    fn test_parse_chrome_side_supports_all_edges() {
        assert_eq!(parse_chrome_side("top"), Some(ChromeSide::Top));
        assert_eq!(parse_chrome_side("bottom"), Some(ChromeSide::Bottom));
        assert_eq!(parse_chrome_side("left"), Some(ChromeSide::Left));
        assert_eq!(parse_chrome_side("right"), Some(ChromeSide::Right));
    }

    #[test]
    fn test_parse_overlay_position_supports_corners() {
        assert_eq!(
            parse_overlay_position("bottom-right"),
            Some(OverlayPosition::BottomRight)
        );
        assert_eq!(
            parse_overlay_position("left_top"),
            Some(OverlayPosition::TopLeft)
        );
    }
}
