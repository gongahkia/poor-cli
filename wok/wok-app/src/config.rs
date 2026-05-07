//! Configuration file system: loads and provides typed access to Wok settings.

use std::path::{Path, PathBuf};
#[cfg(test)]
use std::time::{SystemTime, UNIX_EPOCH};

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

/// Frontend chrome/layout generation.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub enum FrontendLayout {
    /// Original chrome defaults.
    V1,
    /// Pane-first frontend rework.
    V2,
}

impl FrontendLayout {
    /// Stable config label.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::V1 => "v1",
            Self::V2 => "v2",
        }
    }
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

/// Region where a configured mouse binding applies.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MouseBindingArea {
    /// Terminal pane content.
    Content,
    /// A concrete tab label.
    Tab,
    /// Empty tab bar space.
    TabBar,
    /// Status bar.
    Status,
    /// Any non-content chrome surface.
    Chrome,
    /// Any app surface.
    Any,
}

/// A configurable mouse shortcut.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MouseBindingConfig {
    /// Mouse button: left, middle, right, back, forward, or other:N.
    pub button: String,
    /// Exact modifier set: ctrl, alt, shift, meta/cmd.
    pub modifiers: Vec<String>,
    /// Area where the binding applies.
    pub area: MouseBindingArea,
    /// Action id, using the same names as keybinding/Lua actions.
    pub action: String,
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

/// Decorative terminal text effect.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum VisualEffectMode {
    /// No decorative effect.
    #[default]
    None,
    /// Animated hue cycling.
    Rainbow,
    /// Static per-character rainbow gradient.
    RainbowStatic,
    /// Sinusoidal vertical glyph wobble.
    Wavy,
    /// Jitter, flicker, and chromatic ghosting.
    Glitch,
    /// Scanlines and subtle phosphor tint.
    Crt,
    /// Soft duplicate glyph glow.
    Bloom,
    /// Speckled cookie-cutter holes and crumbs.
    Cookie,
}

impl VisualEffectMode {
    /// Stable config/action label.
    pub fn as_str(self) -> &'static str {
        match self {
            Self::None => "none",
            Self::Rainbow => "rainbow",
            Self::RainbowStatic => "rainbow_static",
            Self::Wavy => "wavy",
            Self::Glitch => "glitch",
            Self::Crt => "crt",
            Self::Bloom => "bloom",
            Self::Cookie => "cookie",
        }
    }

    /// Return the next effect in the palette cycle.
    pub fn next(self) -> Self {
        match self {
            Self::None => Self::Rainbow,
            Self::Rainbow => Self::RainbowStatic,
            Self::RainbowStatic => Self::Wavy,
            Self::Wavy => Self::Glitch,
            Self::Glitch => Self::Crt,
            Self::Crt => Self::Bloom,
            Self::Bloom => Self::Cookie,
            Self::Cookie => Self::None,
        }
    }
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
    /// Font family for chrome labels and controls.
    pub chrome_font_family: String,
    /// Font size in points.
    pub font_size: f32,
    /// Input editor position.
    pub input_position: InputPosition,
    /// Command-entry routing mode.
    pub command_entry_mode: CommandEntryMode,
    /// Frontend chrome/layout generation.
    pub ui_layout: FrontendLayout,
    /// Whether to reserve a compact header line for each pane.
    pub pane_header_visible: bool,
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
    /// Whether to render the block timeline rail.
    pub timeline_rail_visible: bool,
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
    /// Whether selected blocks render the optional foot action strip.
    pub block_foot_visible: bool,
    /// Floating pane title height.
    pub floating_pane_title_height: f32,
    /// Whether command output is revealed character-by-character.
    pub typewriter_effect_enabled: bool,
    /// Reveal speed for the command-output typewriter effect.
    pub typewriter_effect_cps: f32,
    /// Maximum queued cells for the command-output typewriter effect.
    pub typewriter_effect_max_pending_cells: usize,
    /// Decorative terminal text effect.
    pub visual_effect: VisualEffectMode,
    /// Visual effect strength from 0.0 to 1.0.
    pub visual_effect_intensity: f32,
    /// Whether the visual effect animates over time.
    pub visual_effect_animated: bool,
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
    /// Configured mouse shortcuts.
    pub mouse_bindings: Vec<MouseBindingConfig>,
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
    chrome_font_family: Option<String>,
    font_size: Option<f32>,
    input_position: Option<String>,
    command_entry_mode: Option<String>,
    ui_layout: Option<String>,
    pane_header_visible: Option<bool>,
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
    timeline_rail_visible: Option<bool>,
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
    block_foot_visible: Option<bool>,
    floating_pane_title_height: Option<f32>,
    typewriter_effect_enabled: Option<bool>,
    typewriter_effect_cps: Option<f32>,
    typewriter_effect_max_pending_cells: Option<usize>,
    visual_effect: Option<String>,
    visual_effect_intensity: Option<f32>,
    visual_effect_animated: Option<bool>,
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
    mouse_bindings: Option<Vec<MouseBindingToml>>,
    triggers: Option<Vec<TriggerToml>>,
    layouts: Option<Vec<LayoutToml>>,
}

/// TOML mouse binding section.
#[derive(Debug, Default, Deserialize)]
struct MouseBindingToml {
    button: Option<String>,
    modifiers: Option<Vec<String>>,
    mods: Option<Vec<String>>,
    area: Option<String>,
    action: Option<String>,
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
            chrome_font_family: default_chrome_font_family().to_string(),
            font_size: 15.0,
            input_position: InputPosition::Bottom,
            command_entry_mode: CommandEntryMode::OwnedPrimary,
            ui_layout: FrontendLayout::V2,
            pane_header_visible: false,
            scrollback_lines: 10_000,
            cursor_style: CursorStyle::Block,
            cursor_blink: true,
            tab_bar_visible: true,
            tab_bar_side: ChromeSide::Top,
            tab_bar_orientation: TabBarOrientation::Horizontal,
            tab_bar_size: Some(24.0),
            status_bar_visible: false,
            status_bar_side: ChromeSide::Bottom,
            status_bar_size: Some(24.0),
            timeline_rail_visible: false,
            window_opacity: 1.0,
            background_image: None,
            background_opacity: 1.0,
            background_fit: BackgroundFit::Stretch,
            background_position: BackgroundPosition::Center,
            background_width: None,
            background_height: None,
            terminal_background_opacity: None,
            pane_border_width: 0.0,
            focused_pane_border_width: 1.0,
            block_foot_visible: false,
            floating_pane_title_height: 16.0,
            typewriter_effect_enabled: false,
            typewriter_effect_cps: 180.0,
            typewriter_effect_max_pending_cells: 4_096,
            visual_effect: VisualEffectMode::None,
            visual_effect_intensity: 0.5,
            visual_effect_animated: true,
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
            mouse_bindings: default_mouse_bindings(),
            triggers: Vec::new(),
            layout_presets: Vec::new(),
        }
    }
}

fn default_font_family() -> &'static str {
    "JetBrainsMono Nerd Font Mono"
}

fn default_chrome_font_family() -> &'static str {
    "IBM Plex Mono"
}

impl WokConfig {
    /// Load configuration from the standard search paths.
    ///
    /// Search order: `$WOK_CONFIG`, `~/.config/wok/config.toml`, `~/.wok.toml`.
    pub fn load() -> Self {
        let paths = config_search_paths();
        Self::load_from_search_paths(&paths)
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
        if let Some(f) = toml_config.chrome_font_family {
            config.chrome_font_family = f;
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
        if let Some(layout) = toml_config.ui_layout {
            config.ui_layout = match layout.trim().to_ascii_lowercase().as_str() {
                "v1" | "classic" | "legacy" => FrontendLayout::V1,
                _ => FrontendLayout::V2,
            };
            if matches!(config.ui_layout, FrontendLayout::V1) {
                config.pane_header_visible = false;
                config.command_entry_mode = CommandEntryMode::ShellNative;
                config.tab_bar_size = None;
                config.status_bar_size = None;
            }
        }
        if let Some(visible) = toml_config.pane_header_visible {
            config.pane_header_visible = visible;
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
        if let Some(visible) = toml_config.timeline_rail_visible {
            config.timeline_rail_visible = visible;
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
        if let Some(visible) = toml_config.block_foot_visible {
            config.block_foot_visible = visible;
        }
        if let Some(height) = toml_config.floating_pane_title_height {
            config.floating_pane_title_height = finite_non_negative(height).unwrap_or(0.0);
        }
        if let Some(enabled) = toml_config.typewriter_effect_enabled {
            config.typewriter_effect_enabled = enabled;
        }
        if let Some(cps) = toml_config.typewriter_effect_cps {
            if cps.is_finite() {
                config.typewriter_effect_cps = cps.clamp(20.0, 2_000.0);
            }
        }
        if let Some(max_pending_cells) = toml_config.typewriter_effect_max_pending_cells {
            config.typewriter_effect_max_pending_cells = max_pending_cells.min(100_000);
        }
        if let Some(effect) = toml_config.visual_effect {
            config.visual_effect = parse_visual_effect_mode(&effect);
        }
        if let Some(intensity) = toml_config.visual_effect_intensity {
            if intensity.is_finite() {
                config.visual_effect_intensity = intensity.clamp(0.0, 1.0);
            }
        }
        if let Some(animated) = toml_config.visual_effect_animated {
            config.visual_effect_animated = animated;
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
        if let Some(mouse_bindings) = toml_config.mouse_bindings {
            config.mouse_bindings = mouse_bindings
                .into_iter()
                .filter_map(parse_mouse_binding_toml)
                .collect();
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

    fn load_from_search_paths(paths: &[PathBuf]) -> Self {
        for path in paths {
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

fn parse_visual_effect_mode(value: &str) -> VisualEffectMode {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "rainbow" | "rainbow_cycle" | "rainbow_cycling" => VisualEffectMode::Rainbow,
        "rainbow_static" | "static_rainbow" | "gradient" => VisualEffectMode::RainbowStatic,
        "wavy" | "wave" | "wobble" => VisualEffectMode::Wavy,
        "glitch" | "flicker" => VisualEffectMode::Glitch,
        "crt" | "scanlines" => VisualEffectMode::Crt,
        "bloom" | "glow" => VisualEffectMode::Bloom,
        "cookie" | "cookie_cutter" | "speckle" | "speckled" => VisualEffectMode::Cookie,
        _ => VisualEffectMode::None,
    }
}

fn default_mouse_bindings() -> Vec<MouseBindingConfig> {
    vec![
        mouse_binding(
            "left",
            ["alt"],
            MouseBindingArea::Content,
            "split_horizontal",
        ),
        mouse_binding(
            "right",
            ["meta"],
            MouseBindingArea::Content,
            "split_vertical",
        ),
        mouse_binding(
            "right",
            ["alt", "meta"],
            MouseBindingArea::Content,
            "new_floating_pane",
        ),
        mouse_binding("left", ["alt"], MouseBindingArea::Tab, "close_tab"),
        mouse_binding("right", ["meta"], MouseBindingArea::Tab, "close_tab"),
        mouse_binding("right", ["meta"], MouseBindingArea::TabBar, "new_tab"),
        mouse_binding(
            "left",
            ["alt"],
            MouseBindingArea::Status,
            "new_floating_pane",
        ),
        mouse_binding(
            "right",
            ["meta"],
            MouseBindingArea::Status,
            "new_floating_pane",
        ),
    ]
}

fn mouse_binding<const N: usize>(
    button: &str,
    modifiers: [&str; N],
    area: MouseBindingArea,
    action: &str,
) -> MouseBindingConfig {
    MouseBindingConfig {
        button: button.to_string(),
        modifiers: modifiers
            .into_iter()
            .filter_map(normalize_mouse_modifier)
            .collect(),
        area,
        action: action.to_string(),
    }
}

fn parse_mouse_binding_toml(binding: MouseBindingToml) -> Option<MouseBindingConfig> {
    let button = normalize_mouse_button(&binding.button?)?;
    let action = binding.action?.trim().to_string();
    if action.is_empty() {
        return None;
    }
    let modifiers = binding
        .modifiers
        .or(binding.mods)
        .unwrap_or_default()
        .into_iter()
        .filter_map(|modifier| normalize_mouse_modifier(&modifier))
        .collect();
    let area = binding
        .area
        .as_deref()
        .and_then(parse_mouse_binding_area)
        .unwrap_or(MouseBindingArea::Any);
    Some(MouseBindingConfig {
        button,
        modifiers,
        area,
        action,
    })
}

fn parse_mouse_binding_area(value: &str) -> Option<MouseBindingArea> {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "content" | "pane" | "terminal" | "viewport" => Some(MouseBindingArea::Content),
        "tab" | "tab_label" => Some(MouseBindingArea::Tab),
        "tab_bar" | "tabs" | "empty_tab_bar" => Some(MouseBindingArea::TabBar),
        "status" | "status_bar" => Some(MouseBindingArea::Status),
        "chrome" => Some(MouseBindingArea::Chrome),
        "any" | "global" => Some(MouseBindingArea::Any),
        _ => None,
    }
}

fn normalize_mouse_button(value: &str) -> Option<String> {
    let normalized = value.trim().to_ascii_lowercase().replace('-', "_");
    match normalized.as_str() {
        "left" | "button1" | "primary" => Some("left".to_string()),
        "middle" | "button2" | "aux" | "auxiliary" => Some("middle".to_string()),
        "right" | "button3" | "secondary" => Some("right".to_string()),
        "back" | "button4" => Some("back".to_string()),
        "forward" | "button5" => Some("forward".to_string()),
        _ => normalized
            .strip_prefix("other:")
            .and_then(|number| number.parse::<u16>().ok())
            .map(|number| format!("other:{number}")),
    }
}

fn normalize_mouse_modifier(value: &str) -> Option<String> {
    match value.trim().to_ascii_lowercase().replace('-', "_").as_str() {
        "ctrl" | "control" => Some("ctrl".to_string()),
        "alt" | "option" => Some("alt".to_string()),
        "shift" => Some("shift".to_string()),
        "meta" | "cmd" | "command" | "super" => Some("meta".to_string()),
        _ => None,
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

/// Manual `wok_settings::Settings` impl. Mirrors every TOML key on
/// `WokConfig` so live-reload diffing can name changed fields without forcing
/// `Serialize`/`Deserialize` derives onto every nested enum (which would
/// require a wider-scope refactor).
impl wok_settings::Settings for WokConfig {
    fn schema() -> wok_settings::SettingsSchema {
        macro_rules! field {
            ($name:literal, $ty:literal) => {
                wok_settings::SettingsField {
                    name: $name,
                    type_name: $ty,
                }
            };
        }
        wok_settings::SettingsSchema {
            type_name: "WokConfig",
            fields: vec![
                field!("shell", "ShellType"),
                field!("theme_path", "Option<PathBuf>"),
                field!("font_family", "String"),
                field!("chrome_font_family", "String"),
                field!("font_size", "f32"),
                field!("input_position", "InputPosition"),
                field!("command_entry_mode", "CommandEntryMode"),
                field!("ui_layout", "FrontendLayout"),
                field!("pane_header_visible", "bool"),
                field!("scrollback_lines", "usize"),
                field!("cursor_style", "CursorStyle"),
                field!("cursor_blink", "bool"),
                field!("tab_bar_visible", "bool"),
                field!("tab_bar_side", "ChromeSide"),
                field!("tab_bar_orientation", "TabBarOrientation"),
                field!("tab_bar_size", "Option<f32>"),
                field!("status_bar_visible", "bool"),
                field!("status_bar_side", "ChromeSide"),
                field!("status_bar_size", "Option<f32>"),
                field!("timeline_rail_visible", "bool"),
                field!("window_opacity", "f32"),
                field!("background_image", "Option<PathBuf>"),
                field!("background_opacity", "f32"),
                field!("background_fit", "BackgroundFit"),
                field!("background_position", "BackgroundPosition"),
                field!("background_width", "Option<f32>"),
                field!("background_height", "Option<f32>"),
                field!("terminal_background_opacity", "Option<f32>"),
                field!("pane_border_width", "f32"),
                field!("focused_pane_border_width", "f32"),
                field!("block_foot_visible", "bool"),
                field!("floating_pane_title_height", "f32"),
                field!("typewriter_effect_enabled", "bool"),
                field!("typewriter_effect_cps", "f32"),
                field!("typewriter_effect_max_pending_cells", "usize"),
                field!("visual_effect", "VisualEffectMode"),
                field!("visual_effect_intensity", "f32"),
                field!("visual_effect_animated", "bool"),
                field!("external_plugin_command", "Option<String>"),
                field!("copy_on_select", "bool"),
                field!("confirm_close_with_running_process", "bool"),
                field!("close_on_shell_exit", "bool"),
                field!("restore_session", "bool"),
                field!("debug_overlay", "bool"),
                field!("command_telemetry", "bool"),
                field!("recent_keys", "RecentKeysConfig"),
                field!("mouse_bindings", "Vec<MouseBindingConfig>"),
                field!("triggers", "Vec<TriggerConfig>"),
                field!("layout_presets", "Vec<LayoutPreset>"),
            ],
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use wok_settings::Settings as _;

    #[test]
    fn schema_lists_known_fields() {
        let s = WokConfig::schema();
        assert_eq!(s.type_name, "WokConfig");
        assert!(s.fields.iter().any(|f| f.name == "shell"));
        assert!(s.fields.iter().any(|f| f.name == "scrollback_lines"));
        assert!(s.fields.iter().any(|f| f.name == "triggers"));
        assert!(s.fields.iter().any(|f| f.name == "layout_presets"));
    }

    #[test]
    fn schema_field_names_are_unique() {
        let s = WokConfig::schema();
        let mut seen: Vec<&str> = s.fields.iter().map(|f| f.name).collect();
        let original = seen.len();
        seen.sort_unstable();
        seen.dedup();
        assert_eq!(seen.len(), original);
    }

    #[test]
    fn test_default_config() {
        let config = WokConfig::default();
        assert!((config.font_size - 15.0).abs() < f32::EPSILON);
        assert_eq!(config.chrome_font_family, default_chrome_font_family());
        assert_eq!(config.scrollback_lines, 10_000);
        assert_eq!(config.cursor_style, CursorStyle::Block);
        assert_eq!(config.input_position, InputPosition::Bottom);
        assert_eq!(config.command_entry_mode, CommandEntryMode::OwnedPrimary);
        assert_eq!(config.ui_layout, FrontendLayout::V2);
        assert!(!config.pane_header_visible);
        assert_eq!(config.tab_bar_side, ChromeSide::Top);
        assert_eq!(config.tab_bar_orientation, TabBarOrientation::Horizontal);
        assert!(!config.status_bar_visible);
        assert_eq!(config.status_bar_side, ChromeSide::Bottom);
        assert!(!config.timeline_rail_visible);
        assert!((config.window_opacity - 1.0).abs() < f32::EPSILON);
        assert_eq!(config.background_image, None);
        assert!((config.background_opacity - 1.0).abs() < f32::EPSILON);
        assert_eq!(config.background_fit, BackgroundFit::Stretch);
        assert_eq!(config.background_position, BackgroundPosition::Center);
        assert_eq!(config.background_width, None);
        assert_eq!(config.background_height, None);
        assert_eq!(config.terminal_background_opacity, None);
        assert!((config.pane_border_width - 0.0).abs() < f32::EPSILON);
        assert!((config.focused_pane_border_width - 1.0).abs() < f32::EPSILON);
        assert!(!config.block_foot_visible);
        assert!((config.floating_pane_title_height - 16.0).abs() < f32::EPSILON);
        assert!(!config.typewriter_effect_enabled);
        assert!((config.typewriter_effect_cps - 180.0).abs() < f32::EPSILON);
        assert_eq!(config.typewriter_effect_max_pending_cells, 4_096);
        assert_eq!(config.visual_effect, VisualEffectMode::None);
        assert!((config.visual_effect_intensity - 0.5).abs() < f32::EPSILON);
        assert!(config.visual_effect_animated);
        assert!(config.close_on_shell_exit);
        assert!(config.recent_keys.visible);
        assert_eq!(config.recent_keys.position, OverlayPosition::BottomRight);
        assert!(config
            .mouse_bindings
            .iter()
            .any(|binding| binding.button == "left"
                && binding.modifiers == vec!["alt"]
                && binding.area == MouseBindingArea::Content
                && binding.action == "split_horizontal"));
    }

    #[test]
    fn test_load_with_no_file() {
        let missing = std::env::temp_dir().join(format!(
            "wok-missing-config-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("clock should be after epoch")
                .as_nanos()
        ));
        let config = WokConfig::load_from_search_paths(&[missing]);
        // Should return defaults without error
        assert!((config.font_size - 15.0).abs() < f32::EPSILON);
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
    fn test_load_mouse_bindings_normalizes_aliases() {
        let path = std::env::temp_dir().join(format!(
            "wok-config-mouse-bindings-{}.toml",
            std::process::id()
        ));
        std::fs::write(
            &path,
            r#"
[[mouse_bindings]]
button = "secondary"
mods = ["cmd", "option"]
area = "terminal"
action = "new_floating_pane"
"#,
        )
        .expect("test config should be written");

        let config = WokConfig::load_from(&path).expect("config should load");
        std::fs::remove_file(&path).ok();
        assert_eq!(config.mouse_bindings.len(), 1);
        let binding = &config.mouse_bindings[0];
        assert_eq!(binding.button, "right");
        assert_eq!(binding.modifiers, vec!["meta", "alt"]);
        assert_eq!(binding.area, MouseBindingArea::Content);
        assert_eq!(binding.action, "new_floating_pane");
    }

    #[test]
    fn test_empty_mouse_bindings_disable_defaults() {
        let path = std::env::temp_dir().join(format!(
            "wok-config-empty-mouse-bindings-{}.toml",
            std::process::id()
        ));
        std::fs::write(&path, "mouse_bindings = []\n").expect("test config should be written");

        let config = WokConfig::load_from(&path).expect("config should load");
        std::fs::remove_file(&path).ok();
        assert!(config.mouse_bindings.is_empty());
    }

    #[test]
    fn test_command_entry_mode_defaults_to_owned_primary_for_v2() {
        let config = WokConfig::default();
        assert_eq!(config.command_entry_mode, CommandEntryMode::OwnedPrimary);
        assert_eq!(config.ui_layout, FrontendLayout::V2);
    }

    #[test]
    fn test_v1_layout_restores_shell_native_defaults() {
        let path =
            std::env::temp_dir().join(format!("wok-config-v1-layout-{}.toml", std::process::id()));
        std::fs::write(&path, "ui_layout = \"v1\"\n").expect("config should be written");

        let config = WokConfig::load_from(&path).expect("config should load");
        std::fs::remove_file(&path).ok();
        assert_eq!(config.ui_layout, FrontendLayout::V1);
        assert_eq!(config.command_entry_mode, CommandEntryMode::ShellNative);
        assert!(!config.pane_header_visible);
    }

    #[test]
    fn test_load_chrome_font_family() {
        let path = std::env::temp_dir().join(format!(
            "wok-config-chrome-font-{}.toml",
            std::process::id()
        ));
        std::fs::write(
            &path,
            r#"
font_family = "JetBrains Mono"
chrome_font_family = "IBM Plex Mono"
"#,
        )
        .expect("config should be written");

        let config = WokConfig::load_from(&path).expect("config should load");
        assert_eq!(config.font_family, "JetBrains Mono");
        assert_eq!(config.chrome_font_family, "IBM Plex Mono");

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn test_load_timeline_rail_visible() {
        let path =
            std::env::temp_dir().join(format!("wok-config-timeline-{}.toml", std::process::id()));
        std::fs::write(&path, "timeline_rail_visible = true\n").expect("config should be written");

        let config = WokConfig::load_from(&path).expect("config should load");
        assert!(config.timeline_rail_visible);

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn test_load_command_trigger_with_system_notify_action() {
        let path =
            std::env::temp_dir().join(format!("wok-config-trigger-{}.toml", std::process::id()));
        std::fs::write(
            &path,
            r#"
[[triggers]]
name = "Homebrew task finished"
pattern = '^\s*brew\s+(update|upgrade)\b'
scope = "command"
actions = ["highlight_blue", "system_notify:Homebrew task finished"]
"#,
        )
        .expect("config should be written");

        let config = WokConfig::load_from(&path).expect("config should load");
        assert_eq!(config.triggers.len(), 1);
        assert_eq!(config.triggers[0].scope, TriggerScopeConfig::Command);
        assert_eq!(
            config.triggers[0].actions,
            vec![
                "highlight_blue".to_string(),
                "system_notify:Homebrew task finished".to_string()
            ]
        );

        let _ = std::fs::remove_file(path);
    }

    #[test]
    fn test_load_typewriter_max_pending_cells_clamps() {
        let path = std::env::temp_dir().join(format!(
            "wok-config-typewriter-cap-{}.toml",
            std::process::id()
        ));
        std::fs::write(
            &path,
            r#"
typewriter_effect_max_pending_cells = 250000
"#,
        )
        .expect("config should be written");

        let config = WokConfig::load_from(&path).expect("config should load");
        assert_eq!(config.typewriter_effect_max_pending_cells, 100_000);

        let _ = std::fs::remove_file(path);
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

    #[test]
    fn test_parse_background_fit_supports_sizing_modes() {
        assert_eq!(parse_background_fit("cover"), BackgroundFit::Cover);
        assert_eq!(parse_background_fit("contain"), BackgroundFit::Contain);
        assert_eq!(parse_background_fit("fit"), BackgroundFit::Contain);
        assert_eq!(parse_background_fit("actual-size"), BackgroundFit::Center);
        assert_eq!(parse_background_fit("unknown"), BackgroundFit::Stretch);
    }

    #[test]
    fn test_parse_visual_effect_mode_supports_effects() {
        assert_eq!(
            parse_visual_effect_mode("rainbow"),
            VisualEffectMode::Rainbow
        );
        assert_eq!(
            parse_visual_effect_mode("static-rainbow"),
            VisualEffectMode::RainbowStatic
        );
        assert_eq!(parse_visual_effect_mode("wobble"), VisualEffectMode::Wavy);
        assert_eq!(parse_visual_effect_mode("scanlines"), VisualEffectMode::Crt);
        assert_eq!(parse_visual_effect_mode("glow"), VisualEffectMode::Bloom);
        assert_eq!(
            parse_visual_effect_mode("cookie-cutter"),
            VisualEffectMode::Cookie
        );
        assert_eq!(parse_visual_effect_mode("plain"), VisualEffectMode::None);
    }

    #[test]
    fn test_parse_background_position_supports_corners() {
        assert_eq!(
            parse_background_position("top-left"),
            BackgroundPosition::TopLeft
        );
        assert_eq!(
            parse_background_position("right_top"),
            BackgroundPosition::TopRight
        );
        assert_eq!(
            parse_background_position("bottom_left"),
            BackgroundPosition::BottomLeft
        );
        assert_eq!(
            parse_background_position("bottom-right"),
            BackgroundPosition::BottomRight
        );
        assert_eq!(
            parse_background_position("unknown"),
            BackgroundPosition::Center
        );
    }
}
