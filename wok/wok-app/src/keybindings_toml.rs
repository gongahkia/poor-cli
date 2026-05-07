//! TOML loader for `~/.config/wok/keybindings.toml` overrides.
//!
//! Schema:
//! ```toml
//! [[binding]]
//! keys = "cmd+t"
//! action = "new_tab"
//! when = ["any"]   # optional; defaults to ["any"]
//! ```
//!
//! Resolution: defaults are built in `KeybindingConfig::default()` (Rust);
//! this loader returns a `Vec<BindingOverride>` that the caller merges by
//! upserting `(KeyCombo, Action)` into `bindings` (last write wins).

use std::path::Path;

use serde::{Deserialize, Serialize};

use crate::input::{KeyAction, Modifiers};
use crate::keybindings::{Action, KeyCombo};

/// One TOML-loaded binding entry.
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BindingEntry {
    /// `+`-separated stroke description: `"cmd+shift+x"`.
    pub keys: String,
    /// Action id matching `action_to_palette_id` strings (e.g. `"new_tab"`).
    pub action: String,
    /// Optional context tags (currently unused; reserved for chord_keymap).
    #[serde(default)]
    pub when: Vec<String>,
}

/// Whole `keybindings.toml` document.
#[derive(Debug, Default, Clone, Deserialize, Serialize)]
pub struct KeybindingsTomlDoc {
    /// `[[binding]]` entries.
    #[serde(default)]
    pub binding: Vec<BindingEntry>,
}

/// Resolved override ready to merge into `KeybindingConfig::bindings`.
#[derive(Debug, Clone)]
pub struct BindingOverride {
    /// Resolved key combo.
    pub combo: KeyCombo,
    /// Resolved action.
    pub action: Action,
    /// Original `when` field (informational; not enforced yet).
    pub when: Vec<String>,
}

/// Errors raised when parsing user keybindings.
#[derive(Debug)]
pub enum LoadError {
    /// I/O failure reading the file.
    Io(std::io::Error),
    /// TOML parse failure.
    Parse(toml::de::Error),
}

impl std::fmt::Display for LoadError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Io(e) => write!(f, "{e}"),
            Self::Parse(e) => write!(f, "{e}"),
        }
    }
}

impl std::error::Error for LoadError {}

/// Load + parse + resolve. Returns successful overrides AND non-fatal warnings
/// for entries with unknown actions/keys (those entries are dropped, others
/// keep loading).
pub fn load(path: &Path) -> Result<(Vec<BindingOverride>, Vec<String>), LoadError> {
    let text = std::fs::read_to_string(path).map_err(LoadError::Io)?;
    let doc: KeybindingsTomlDoc = toml::from_str(&text).map_err(LoadError::Parse)?;
    let mut out = Vec::new();
    let mut warnings = Vec::new();
    for entry in doc.binding {
        let combo = match parse_keys(&entry.keys) {
            Some(c) => c,
            None => {
                warnings.push(format!(
                    "ignoring binding with unparseable keys: {:?}",
                    entry.keys
                ));
                continue;
            }
        };
        let action = match parse_action_id(&entry.action) {
            Some(a) => a,
            None => {
                warnings.push(format!(
                    "ignoring binding with unknown action '{}'",
                    entry.action
                ));
                continue;
            }
        };
        out.push(BindingOverride {
            combo,
            action,
            when: entry.when,
        });
    }
    Ok((out, warnings))
}

/// Save or replace one action binding in `keybindings.toml`.
pub fn upsert_binding(path: &Path, action: &str, combo: &KeyCombo) -> Result<(), LoadError> {
    let mut doc = load_doc_or_default(path)?;
    doc.binding.retain(|entry| entry.action != action);
    doc.binding.push(BindingEntry {
        keys: format_keys(combo),
        action: action.to_string(),
        when: Vec::new(),
    });
    write_doc(path, &doc).map_err(LoadError::Io)
}

/// Remove any user override for one action from `keybindings.toml`.
pub fn remove_binding(path: &Path, action: &str) -> Result<bool, LoadError> {
    let mut doc = load_doc_or_default(path)?;
    let before = doc.binding.len();
    doc.binding.retain(|entry| entry.action != action);
    let removed = doc.binding.len() != before;
    write_doc(path, &doc).map_err(LoadError::Io)?;
    Ok(removed)
}

fn load_doc_or_default(path: &Path) -> Result<KeybindingsTomlDoc, LoadError> {
    if !path.exists() {
        return Ok(KeybindingsTomlDoc::default());
    }
    let text = std::fs::read_to_string(path).map_err(LoadError::Io)?;
    toml::from_str(&text).map_err(LoadError::Parse)
}

fn write_doc(path: &Path, doc: &KeybindingsTomlDoc) -> std::io::Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let mut text = String::from("# Wok keybindings. Edited by Wok; comments may be rewritten.\n\n");
    text.push_str(&toml::to_string_pretty(doc).unwrap_or_else(|_| String::new()));
    std::fs::write(path, text)
}

/// Format a key combo using the same syntax accepted by [`parse_keys`].
pub fn format_keys(combo: &KeyCombo) -> String {
    let mut parts = Vec::new();
    if combo.modifiers.meta {
        parts.push("cmd".to_string());
    }
    if combo.modifiers.ctrl {
        parts.push("ctrl".to_string());
    }
    if combo.modifiers.alt {
        parts.push("alt".to_string());
    }
    if combo.modifiers.shift {
        parts.push("shift".to_string());
    }
    parts.push(format_key_action(&combo.key));
    parts.join("+")
}

fn format_key_action(action: &KeyAction) -> String {
    match action {
        KeyAction::Char(ch) => ch.to_string(),
        KeyAction::Enter => "enter".to_string(),
        KeyAction::Tab => "tab".to_string(),
        KeyAction::Backspace => "backspace".to_string(),
        KeyAction::Delete => "delete".to_string(),
        KeyAction::Escape => "escape".to_string(),
        KeyAction::ArrowUp => "up".to_string(),
        KeyAction::ArrowDown => "down".to_string(),
        KeyAction::ArrowLeft => "left".to_string(),
        KeyAction::ArrowRight => "right".to_string(),
        KeyAction::Home => "home".to_string(),
        KeyAction::End => "end".to_string(),
        KeyAction::PageUp => "pageup".to_string(),
        KeyAction::PageDown => "pagedown".to_string(),
        KeyAction::FunctionKey(index) => format!("f{index}"),
        KeyAction::Copy => "copy".to_string(),
        KeyAction::Paste => "paste".to_string(),
        KeyAction::Cut => "cut".to_string(),
        KeyAction::SelectAll => "select_all".to_string(),
        KeyAction::Undo => "undo".to_string(),
        KeyAction::Redo => "redo".to_string(),
        KeyAction::ModifierShift => "shift".to_string(),
        KeyAction::ModifierControl => "control".to_string(),
        KeyAction::ModifierAlt => "alt".to_string(),
        KeyAction::ModifierMeta => "meta".to_string(),
    }
}

/// Parse `"cmd+shift+t"` → `KeyCombo`. Tokens are case-insensitive; `+` is the
/// separator. Modifier names: `cmd|super|meta|win`, `ctrl|control`, `alt|opt|option`,
/// `shift`. Final token is the key.
pub fn parse_keys(spec: &str) -> Option<KeyCombo> {
    let mut mods = Modifiers::default();
    let mut key: Option<KeyAction> = None;
    let mut tokens = spec.split('+').peekable();
    while let Some(raw) = tokens.next() {
        let token = raw.trim();
        if token.is_empty() {
            return None;
        }
        let last = tokens.peek().is_none();
        let lower = token.to_ascii_lowercase();
        if !last {
            match lower.as_str() {
                "cmd" | "super" | "meta" | "win" => mods.meta = true,
                "ctrl" | "control" => mods.ctrl = true,
                "alt" | "opt" | "option" => mods.alt = true,
                "shift" => mods.shift = true,
                _ => return None,
            }
        } else {
            key = parse_key_action(token);
        }
    }
    let key = key?;
    Some(KeyCombo {
        key,
        modifiers: mods,
    })
}

fn parse_key_action(token: &str) -> Option<KeyAction> {
    let lower = token.to_ascii_lowercase();
    Some(match lower.as_str() {
        "enter" | "return" => KeyAction::Enter,
        "tab" => KeyAction::Tab,
        "backspace" => KeyAction::Backspace,
        "delete" | "del" => KeyAction::Delete,
        "escape" | "esc" => KeyAction::Escape,
        "up" | "arrowup" => KeyAction::ArrowUp,
        "down" | "arrowdown" => KeyAction::ArrowDown,
        "left" | "arrowleft" => KeyAction::ArrowLeft,
        "right" | "arrowright" => KeyAction::ArrowRight,
        "home" => KeyAction::Home,
        "end" => KeyAction::End,
        "pageup" | "pgup" => KeyAction::PageUp,
        "pagedown" | "pgdn" => KeyAction::PageDown,
        "copy" => KeyAction::Copy,
        "paste" => KeyAction::Paste,
        "cut" => KeyAction::Cut,
        "selectall" | "select_all" => KeyAction::SelectAll,
        "undo" => KeyAction::Undo,
        "redo" => KeyAction::Redo,
        s if s.starts_with('f') && s[1..].chars().all(|c| c.is_ascii_digit()) => {
            let n: u8 = s[1..].parse().ok()?;
            if (1..=12).contains(&n) {
                KeyAction::FunctionKey(n)
            } else {
                return None;
            }
        }
        s if s.chars().count() == 1 => {
            KeyAction::Char(s.chars().next().unwrap().to_ascii_lowercase())
        }
        _ => return None,
    })
}

/// Translate a canonical action id (matches `action_to_palette_id` outputs)
/// into the `Action` enum. Only no-arg variants supported here; parameterised
/// variants like `save_session:NAME` are handled by callers if needed.
pub fn parse_action_id(id: &str) -> Option<Action> {
    if let Some(index) = id.strip_prefix("switch_to_tab_") {
        return index
            .parse::<u8>()
            .ok()
            .filter(|value| (1..=9).contains(value))
            .map(Action::SwitchToTab);
    }
    if let Some(index) = id
        .strip_prefix("workspace_switch:")
        .or_else(|| id.strip_prefix("workspace_switch_"))
    {
        return index
            .parse::<u8>()
            .ok()
            .filter(|value| (1..=9).contains(value))
            .map(Action::WorkspaceSwitch);
    }
    Some(match id {
        "new_tab" => Action::NewTab,
        "close_tab" => Action::CloseTab,
        "next_tab" => Action::NextTab,
        "prev_tab" => Action::PrevTab,
        "workspace_new" => Action::WorkspaceNew,
        "workspace_next" => Action::WorkspaceNext,
        "workspace_prev" => Action::WorkspacePrev,
        "surface_new" => Action::SurfaceNew,
        "surface_next" => Action::SurfaceNext,
        "surface_prev" => Action::SurfacePrev,
        "surface_close" => Action::SurfaceClose,
        "split_vertical" => Action::SplitVertical,
        "split_horizontal" => Action::SplitHorizontal,
        "close_split" => Action::CloseSplit,
        "focus_left" => Action::FocusLeft,
        "focus_right" => Action::FocusRight,
        "focus_up" => Action::FocusUp,
        "focus_down" => Action::FocusDown,
        "focus_prev_pane" => Action::FocusPrevPane,
        "focus_next_pane" => Action::FocusNextPane,
        "resize_split_left" => Action::ResizeSplitLeft,
        "resize_split_right" => Action::ResizeSplitRight,
        "resize_split_up" => Action::ResizeSplitUp,
        "resize_split_down" => Action::ResizeSplitDown,
        "copy" => Action::Copy,
        "paste" => Action::Paste,
        "select_all" => Action::SelectAll,
        "scroll_up" => Action::ScrollUp,
        "scroll_down" => Action::ScrollDown,
        "scroll_page_up" => Action::ScrollPageUp,
        "scroll_page_down" => Action::ScrollPageDown,
        "scroll_to_top" => Action::ScrollToTop,
        "scroll_to_bottom" => Action::ScrollToBottom,
        "command_palette" => Action::CommandPalette,
        "command_search" => Action::CommandSearch,
        "search_global" => Action::SearchGlobal,
        "enter_vi_mode" => Action::EnterViMode,
        "quick_select" => Action::QuickSelect,
        "quick_select_block" => Action::QuickSelectBlock,
        "toggle_broadcast" => Action::ToggleBroadcast,
        "toggle_block_foot_strip" => Action::ToggleBlockFootStrip,
        "toggle_typewriter_effect" => Action::ToggleTypewriterEffect,
        "cycle_visual_effect" => Action::CycleVisualEffect,
        "close_media_preview" => Action::CloseMediaPreview,
        "toggle_media_preview_playback" => Action::ToggleMediaPreviewPlayback,
        "seek_media_preview_backward" => Action::SeekMediaPreviewBackward,
        "seek_media_preview_forward" => Action::SeekMediaPreviewForward,
        "slow_media_preview_playback" => Action::SlowMediaPreviewPlayback,
        "fast_media_preview_playback" => Action::FastMediaPreviewPlayback,
        "step_media_preview_backward" => Action::StepMediaPreviewBackward,
        "step_media_preview_forward" => Action::StepMediaPreviewForward,
        "toggle_media_preview_mute" => Action::ToggleMediaPreviewMute,
        "preview_path_under_cursor" => Action::PreviewPathUnderCursor,
        "open_path_under_cursor" => Action::OpenPathUnderCursor,
        "copy_path_under_cursor" => Action::CopyPathUnderCursor,
        "reveal_path_under_cursor" => Action::RevealPathUnderCursor,
        "tail_path_under_cursor" => Action::TailPathUnderCursor,
        "open_scratch_buffer" => Action::OpenScratchBuffer,
        "open_scratch_palette" => Action::OpenScratchPalette,
        "toggle_search_regex" => Action::ToggleSearchRegex,
        "cycle_search_scope" => Action::CycleSearchScope,
        "open_search_results" => Action::OpenSearchResults,
        "save_current_search" => Action::SaveCurrentSearch,
        "open_saved_searches" => Action::OpenSavedSearches,
        "open_block_inspector" => Action::OpenBlockInspector,
        "open_block_rerun_history" => Action::OpenBlockRerunHistory,
        "open_block_rerun_comparison" => Action::OpenBlockRerunComparison,
        "block_context_menu" => Action::BlockContextMenu,
        "block_scroll_top" => Action::BlockScrollTop,
        "block_scroll_bottom" => Action::BlockScrollBottom,
        "insert_scratch_selection_into_input" => Action::InsertScratchSelectionIntoInput,
        "send_scratch_selection_to_pane" => Action::SendScratchSelectionToPane,
        "open_workspace_browser" => Action::OpenWorkspaceBrowser,
        "new_floating_pane" => Action::NewFloatingPane,
        "toggle_floating_pane" => Action::ToggleFloatingPane,
        "close_floating_pane" => Action::CloseFloatingPane,
        "next_layout" => Action::NextLayout,
        "prev_layout" => Action::PrevLayout,
        "toggle_input_position" => Action::ToggleInputPosition,
        "zoom_in" => Action::ZoomIn,
        "zoom_out" => Action::ZoomOut,
        "zoom_reset" => Action::ZoomReset,
        "open_settings" => Action::OpenSettings,
        "reset_settings" => Action::ResetSettings,
        "clear_screen" => Action::ClearScreen,
        "send_eof" => Action::SendEof,
        "theme_picker" => Action::ThemePicker,
        "keybinding_discovery" => Action::KeybindingDiscovery,
        "keybinding_editor" => Action::KeybindingEditor,
        "settings_discovery" => Action::SettingsDiscovery,
        "notification_popover" => Action::NotificationPopover,
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_modifier_combos() {
        let c = parse_keys("cmd+shift+t").unwrap();
        assert!(c.modifiers.meta);
        assert!(c.modifiers.shift);
        assert!(!c.modifiers.ctrl);
        assert_eq!(c.key, KeyAction::Char('t'));
    }

    #[test]
    fn parses_named_keys() {
        assert_eq!(parse_keys("enter").unwrap().key, KeyAction::Enter);
        assert_eq!(parse_keys("escape").unwrap().key, KeyAction::Escape);
        assert_eq!(parse_keys("ctrl+up").unwrap().key, KeyAction::ArrowUp);
        assert_eq!(parse_keys("alt+f5").unwrap().key, KeyAction::FunctionKey(5));
    }

    #[test]
    fn case_insensitive_modifiers() {
        let a = parse_keys("CMD+T").unwrap();
        let b = parse_keys("cmd+t").unwrap();
        assert_eq!(a, b);
    }

    #[test]
    fn rejects_unknown_modifier() {
        assert!(parse_keys("foo+t").is_none());
    }

    #[test]
    fn rejects_empty_token() {
        assert!(parse_keys("cmd++t").is_none());
    }

    #[test]
    fn parse_action_id_known_and_unknown() {
        assert!(matches!(parse_action_id("new_tab"), Some(Action::NewTab)));
        assert!(matches!(
            parse_action_id("switch_to_tab_3"),
            Some(Action::SwitchToTab(3))
        ));
        assert!(matches!(
            parse_action_id("reset_settings"),
            Some(Action::ResetSettings)
        ));
        assert!(matches!(
            parse_action_id("cycle_visual_effect"),
            Some(Action::CycleVisualEffect)
        ));
        assert!(matches!(
            parse_action_id("close_media_preview"),
            Some(Action::CloseMediaPreview)
        ));
        assert!(matches!(
            parse_action_id("preview_path_under_cursor"),
            Some(Action::PreviewPathUnderCursor)
        ));
        assert!(matches!(
            parse_action_id("open_scratch_buffer"),
            Some(Action::OpenScratchBuffer)
        ));
        assert!(matches!(
            parse_action_id("toggle_search_regex"),
            Some(Action::ToggleSearchRegex)
        ));
        assert!(parse_action_id("not_a_real_action").is_none());
    }

    #[test]
    fn loads_doc_round_trip() {
        let dir = std::env::temp_dir().join(format!(
            "wok-keybindings-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("keybindings.toml");
        std::fs::write(
            &path,
            "[[binding]]\nkeys = \"cmd+shift+t\"\naction = \"new_tab\"\n\
             [[binding]]\nkeys = \"alt+f4\"\naction = \"close_tab\"\n",
        )
        .unwrap();
        let (overrides, warnings) = load(&path).unwrap();
        assert_eq!(overrides.len(), 2);
        assert!(warnings.is_empty());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn upsert_and_remove_binding_round_trip() {
        let dir = std::env::temp_dir().join(format!(
            "wok-keybindings-edit-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("keybindings.toml");
        let combo = KeyCombo {
            key: KeyAction::Char('k'),
            modifiers: Modifiers {
                meta: true,
                shift: true,
                ..Modifiers::default()
            },
        };

        upsert_binding(&path, "command_palette", &combo).unwrap();
        let (overrides, warnings) = load(&path).unwrap();
        assert!(warnings.is_empty());
        assert_eq!(overrides.len(), 1);
        assert_eq!(overrides[0].combo, combo);
        assert_eq!(format_keys(&combo), "cmd+shift+k");

        assert!(remove_binding(&path, "command_palette").unwrap());
        let (overrides, warnings) = load(&path).unwrap();
        assert!(warnings.is_empty());
        assert!(overrides.is_empty());
        std::fs::remove_dir_all(&dir).ok();
    }

    #[test]
    fn ignores_unknown_actions_with_warning() {
        let dir = std::env::temp_dir().join(format!(
            "wok-keybindings-warn-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("keybindings.toml");
        std::fs::write(
            &path,
            "[[binding]]\nkeys = \"cmd+t\"\naction = \"new_tab\"\n\
             [[binding]]\nkeys = \"cmd+x\"\naction = \"not_real\"\n",
        )
        .unwrap();
        let (overrides, warnings) = load(&path).unwrap();
        assert_eq!(overrides.len(), 1);
        assert_eq!(warnings.len(), 1);
        assert!(warnings[0].contains("not_real"));
        std::fs::remove_dir_all(&dir).ok();
    }
}
