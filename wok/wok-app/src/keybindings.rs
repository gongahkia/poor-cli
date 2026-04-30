//! Keybinding system: maps key combinations to actions.

use std::collections::HashMap;

use crate::input::{KeyAction, Modifiers};

/// All bindable actions in Wok.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Action {
    /// Create a new tab.
    NewTab,
    /// Close the current tab.
    CloseTab,
    /// Switch to the next tab.
    NextTab,
    /// Switch to the previous tab.
    PrevTab,
    /// Switch to tab N (1-indexed).
    SwitchToTab(u8),
    /// Split the pane vertically.
    SplitVertical,
    /// Split the pane horizontally.
    SplitHorizontal,
    /// Close the current split pane.
    CloseSplit,
    /// Focus the pane to the left.
    FocusLeft,
    /// Focus the pane to the right.
    FocusRight,
    /// Focus the pane above.
    FocusUp,
    /// Focus the pane below.
    FocusDown,
    /// Resize split left.
    ResizeSplitLeft,
    /// Resize split right.
    ResizeSplitRight,
    /// Resize split up.
    ResizeSplitUp,
    /// Resize split down.
    ResizeSplitDown,
    /// Copy to clipboard.
    Copy,
    /// Paste from clipboard.
    Paste,
    /// Select all text.
    SelectAll,
    /// Scroll up.
    ScrollUp,
    /// Scroll down.
    ScrollDown,
    /// Scroll up one page.
    ScrollPageUp,
    /// Scroll down one page.
    ScrollPageDown,
    /// Scroll to top.
    ScrollToTop,
    /// Scroll to bottom.
    ScrollToBottom,
    /// Select previous block.
    BlockPrev,
    /// Select next block.
    BlockNext,
    /// Copy selected block output.
    BlockCopy,
    /// Copy the selected block command only.
    BlockCopyCommand,
    /// Copy the selected block output only.
    BlockCopyOutput,
    /// Toggle collapse on selected block.
    BlockCollapse,
    /// Bookmark or unbookmark the selected block.
    BlockToggleBookmark,
    /// Move to the previous bookmarked block.
    BlockPrevBookmark,
    /// Move to the next bookmarked block.
    BlockNextBookmark,
    /// Move to the previous failed block.
    BlockPrevFailed,
    /// Move to the next failed block.
    BlockNextFailed,
    /// Search within the selected block output.
    BlockFind,
    /// Filter the selected block output down to matching lines.
    BlockFilter,
    /// Show a diff against the previous comparable run of the selected block command.
    BlockDiff,
    /// Re-run the selected block command in the active PTY.
    BlockRerun,
    /// Re-run the selected block command in a new split pane.
    BlockRerunInSplit,
    /// Save the selected block command as a reusable workflow template.
    BlockSaveWorkflow,
    /// Export selected block metadata + output as Markdown.
    BlockExportMarkdown,
    /// Export selected block metadata + output as JSON.
    BlockExportJson,
    /// Toggle the failure-trends panel for the active pane.
    ToggleFailureTrendsPanel,
    /// Toggle the workspace insights panel for the active pane.
    ToggleWorkspaceInsightsPanel,
    /// Global terminal search.
    SearchGlobal,
    /// Enter vi navigation mode.
    EnterViMode,
    /// Toggle pane input broadcast mode.
    ToggleBroadcast,
    /// Create a new floating pane.
    NewFloatingPane,
    /// Toggle visibility for floating panes.
    ToggleFloatingPane,
    /// Close the focused floating pane.
    CloseFloatingPane,
    /// Cycle to the next layout preset.
    NextLayout,
    /// Cycle to the previous layout preset.
    PrevLayout,
    /// Open the command palette.
    CommandPalette,
    /// Open pane-local command history search.
    CommandSearch,
    /// Start quick select on the visible viewport.
    QuickSelect,
    /// Start quick select scoped to the selected block.
    QuickSelectBlock,
    /// Toggle input position (top/bottom).
    ToggleInputPosition,
    /// Increase font size.
    ZoomIn,
    /// Decrease font size.
    ZoomOut,
    /// Reset font size.
    ZoomReset,
    /// Open the Wok settings file.
    OpenSettings,
    /// Clear terminal screen.
    ClearScreen,
    /// Send EOF (Ctrl+D).
    SendEof,
    /// Save the current workspace to a named session snapshot.
    SaveSession(String),
    /// Load a named workspace session snapshot.
    LoadSession(String),
    /// Open the theme picker palette.
    ThemePicker,
    /// Open the read-only keybinding discovery palette.
    KeybindingDiscovery,
}

/// A key combination (key + modifiers).
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct KeyCombo {
    /// The key action.
    pub key: KeyAction,
    /// Active modifiers.
    pub modifiers: Modifiers,
}

/// Context in which a keybinding is resolved.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Context {
    /// Normal terminal mode.
    Terminal,
    /// Input editor is focused.
    InputEditor,
    /// A block is selected.
    BlockSelected,
    /// Search mode is active.
    SearchActive,
    /// Quick-select label mode is active.
    QuickSelect,
    /// Vi-mode navigation is active.
    ViMode,
}

/// Keybinding configuration.
pub struct KeybindingConfig {
    /// Global keybindings.
    pub bindings: HashMap<KeyCombo, Action>,
    /// Context-specific keybindings.
    pub context_bindings: HashMap<Context, HashMap<KeyCombo, Action>>,
    /// Chord-style bindings (multi-stroke sequences). Resolved separately via
    /// [`KeybindingConfig::resolve_chord`]; flat bindings above keep working.
    pub chord_keymap: wok_keymap::Keymap,
    /// Stroke buffer accumulated since the last chord resolution.
    pub chord_buffer: Vec<wok_keymap::Stroke>,
}

impl KeybindingConfig {
    /// Resolve a key combo to an action, checking context first then global.
    pub fn resolve(&self, combo: &KeyCombo, context: &Context) -> Option<&Action> {
        // Check context-specific bindings first
        if let Some(ctx_bindings) = self.context_bindings.get(context) {
            if let Some(action) = ctx_bindings.get(combo) {
                return Some(action);
            }
        }
        // Fall back to global bindings
        self.bindings.get(combo)
    }

    /// Feed one stroke into the chord resolver. Returns:
    ///   - `Match { action, .. }` — buffer cleared, caller dispatches `action`.
    ///   - `Pending` — buffer retained; caller buffers the next stroke.
    ///   - `None` — buffer cleared; caller falls back to flat-binding lookup.
    pub fn resolve_chord(
        &mut self,
        stroke: wok_keymap::Stroke,
        ctx: &wok_keymap::Context,
    ) -> wok_keymap::Resolution {
        self.chord_buffer.push(stroke);
        let resolution = self.chord_keymap.resolve(&self.chord_buffer, ctx);
        match resolution {
            wok_keymap::Resolution::Pending => {}
            _ => self.chord_buffer.clear(),
        }
        resolution
    }

    /// Drop any in-flight chord buffer (call on focus change / Esc).
    pub fn clear_chord_buffer(&mut self) {
        self.chord_buffer.clear();
    }

    /// Apply user TOML overrides on top of defaults. Each override upserts a
    /// `(KeyCombo, Action)` pair into `bindings`. Returns the warnings list
    /// from the loader so the caller can surface them in the status bar.
    pub fn apply_toml_overrides(
        &mut self,
        overrides: Vec<crate::keybindings_toml::BindingOverride>,
    ) -> usize {
        let n = overrides.len();
        for ov in overrides {
            self.bindings.insert(ov.combo, ov.action);
        }
        n
    }

    /// Convenience: load `path` (if it exists) + apply. Missing file returns
    /// `Ok(0, vec![])`. Parse errors propagate.
    pub fn load_and_apply_overrides(
        &mut self,
        path: &std::path::Path,
    ) -> Result<(usize, Vec<String>), crate::keybindings_toml::LoadError> {
        if !path.exists() {
            return Ok((0, Vec::new()));
        }
        let (overrides, warnings) = crate::keybindings_toml::load(path)?;
        let count = self.apply_toml_overrides(overrides);
        Ok((count, warnings))
    }
}

/// Get the platform modifier (Cmd on macOS, Ctrl elsewhere).
fn platform_mod() -> Modifiers {
    #[cfg(target_os = "macos")]
    {
        Modifiers {
            meta: true,
            ..Modifiers::default()
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        Modifiers {
            ctrl: true,
            ..Modifiers::default()
        }
    }
}

/// Get platform modifier + shift.
fn platform_mod_shift() -> Modifiers {
    let mut m = platform_mod();
    m.shift = true;
    m
}

/// Get platform modifier + alt.
fn platform_mod_alt() -> Modifiers {
    let mut m = platform_mod();
    m.alt = true;
    m
}

impl Default for KeybindingConfig {
    fn default() -> Self {
        let pm = platform_mod();
        let pms = platform_mod_shift();
        let pma = platform_mod_alt();

        let mut bindings = HashMap::new();

        // Tab management
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('t'),
                modifiers: pm,
            },
            Action::NewTab,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('w'),
                modifiers: pm,
            },
            Action::CloseTab,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Tab,
                modifiers: pm,
            },
            Action::NextTab,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Tab,
                modifiers: pms,
            },
            Action::PrevTab,
        );

        // Tab switching 1-9
        for i in 1..=9u8 {
            let ch = char::from(b'0' + i);
            bindings.insert(
                KeyCombo {
                    key: KeyAction::Char(ch),
                    modifiers: pm,
                },
                Action::SwitchToTab(i),
            );
        }

        // Split panes
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('d'),
                modifiers: pm,
            },
            Action::SplitVertical,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('d'),
                modifiers: pms,
            },
            Action::SplitHorizontal,
        );

        // Focus direction
        bindings.insert(
            KeyCombo {
                key: KeyAction::ArrowLeft,
                modifiers: pma,
            },
            Action::FocusLeft,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::ArrowRight,
                modifiers: pma,
            },
            Action::FocusRight,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::ArrowUp,
                modifiers: pma,
            },
            Action::FocusUp,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::ArrowDown,
                modifiers: pma,
            },
            Action::FocusDown,
        );

        // Clipboard
        bindings.insert(
            KeyCombo {
                key: KeyAction::Copy,
                modifiers: Modifiers::default(),
            },
            Action::Copy,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Paste,
                modifiers: Modifiers::default(),
            },
            Action::Paste,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::SelectAll,
                modifiers: Modifiers::default(),
            },
            Action::SelectAll,
        );

        // Block navigation
        bindings.insert(
            KeyCombo {
                key: KeyAction::ArrowUp,
                modifiers: pm,
            },
            Action::BlockPrev,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::ArrowDown,
                modifiers: pm,
            },
            Action::BlockNext,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('c'),
                modifiers: pms,
            },
            Action::BlockCopy,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('o'),
                modifiers: pms,
            },
            Action::BlockCopyOutput,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('e'),
                modifiers: pms,
            },
            Action::BlockCollapse,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('f'),
                modifiers: pms,
            },
            Action::BlockFind,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('f'),
                modifiers: pma,
            },
            Action::BlockFilter,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('b'),
                modifiers: pms,
            },
            Action::BlockToggleBookmark,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('['),
                modifiers: pma,
            },
            Action::BlockPrevFailed,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char(']'),
                modifiers: pma,
            },
            Action::BlockNextFailed,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('d'),
                modifiers: pma,
            },
            Action::BlockDiff,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('r'),
                modifiers: pma,
            },
            Action::BlockRerun,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('r'),
                modifiers: Modifiers { shift: true, ..pma },
            },
            Action::BlockRerunInSplit,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('w'),
                modifiers: Modifiers { shift: true, ..pma },
            },
            Action::BlockSaveWorkflow,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('m'),
                modifiers: Modifiers { shift: true, ..pma },
            },
            Action::BlockExportMarkdown,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('j'),
                modifiers: Modifiers { shift: true, ..pma },
            },
            Action::BlockExportJson,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('y'),
                modifiers: pma,
            },
            Action::ToggleFailureTrendsPanel,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('i'),
                modifiers: pma,
            },
            Action::ToggleWorkspaceInsightsPanel,
        );

        // Search
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('f'),
                modifiers: pm,
            },
            Action::SearchGlobal,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('p'),
                modifiers: pm,
            },
            Action::CommandPalette,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('v'),
                modifiers: pms,
            },
            Action::EnterViMode,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('q'),
                modifiers: pms,
            },
            Action::QuickSelect,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('q'),
                modifiers: pma,
            },
            Action::QuickSelectBlock,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('b'),
                modifiers: pma,
            },
            Action::ToggleBroadcast,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('n'),
                modifiers: pma,
            },
            Action::NewFloatingPane,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('t'),
                modifiers: pma,
            },
            Action::ToggleFloatingPane,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('w'),
                modifiers: pma,
            },
            Action::CloseFloatingPane,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('l'),
                modifiers: pma,
            },
            Action::NextLayout,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('l'),
                modifiers: Modifiers { shift: true, ..pma },
            },
            Action::PrevLayout,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('r'),
                modifiers: Modifiers {
                    ctrl: true,
                    ..Modifiers::default()
                },
            },
            Action::CommandSearch,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('i'),
                modifiers: pms,
            },
            Action::ToggleInputPosition,
        );

        // Zoom
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('='),
                modifiers: pm,
            },
            Action::ZoomIn,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('-'),
                modifiers: pm,
            },
            Action::ZoomOut,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('0'),
                modifiers: pm,
            },
            Action::ZoomReset,
        );

        // Clear screen
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('k'),
                modifiers: pm,
            },
            Action::ClearScreen,
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('s'),
                modifiers: pms,
            },
            Action::SaveSession("manual".to_string()),
        );
        bindings.insert(
            KeyCombo {
                key: KeyAction::Char('r'),
                modifiers: pms,
            },
            Action::LoadSession("manual".to_string()),
        );

        let mut context_bindings = HashMap::new();
        let mut block_selected = HashMap::new();
        block_selected.insert(
            KeyCombo {
                key: KeyAction::Char('i'),
                modifiers: pms,
            },
            Action::BlockCopyCommand,
        );
        block_selected.insert(
            KeyCombo {
                key: KeyAction::ArrowUp,
                modifiers: pma,
            },
            Action::BlockPrevBookmark,
        );
        block_selected.insert(
            KeyCombo {
                key: KeyAction::ArrowDown,
                modifiers: pma,
            },
            Action::BlockNextBookmark,
        );
        context_bindings.insert(Context::BlockSelected, block_selected);

        Self {
            bindings,
            context_bindings,
            chord_keymap: wok_keymap::Keymap::new(),
            chord_buffer: Vec::new(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_keybindings() {
        let config = KeybindingConfig::default();
        assert!(!config.bindings.is_empty());
    }

    #[test]
    fn test_resolve_global() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::Char('t'),
            modifiers: platform_mod(),
        };
        let action = config.resolve(&combo, &Context::Terminal);
        assert_eq!(action, Some(&Action::NewTab));
    }

    #[test]
    fn test_resolve_returns_none_for_unbound() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::Char('q'),
            modifiers: Modifiers::default(),
        };
        assert!(config.resolve(&combo, &Context::Terminal).is_none());
    }

    #[test]
    fn test_block_copy_binding_exists() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::Char('c'),
            modifiers: platform_mod_shift(),
        };
        assert_eq!(
            config.resolve(&combo, &Context::Terminal),
            Some(&Action::BlockCopy)
        );
    }

    #[test]
    fn test_block_copy_command_context_binding_overrides_toggle_input_position() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::Char('i'),
            modifiers: platform_mod_shift(),
        };

        assert_eq!(
            config.resolve(&combo, &Context::Terminal),
            Some(&Action::ToggleInputPosition)
        );
        assert_eq!(
            config.resolve(&combo, &Context::BlockSelected),
            Some(&Action::BlockCopyCommand)
        );
    }

    #[test]
    fn test_bookmark_navigation_is_block_selected_only() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::ArrowDown,
            modifiers: platform_mod_alt(),
        };

        assert_eq!(
            config.resolve(&combo, &Context::Terminal),
            Some(&Action::FocusDown)
        );
        assert_eq!(
            config.resolve(&combo, &Context::BlockSelected),
            Some(&Action::BlockNextBookmark)
        );
    }

    #[test]
    fn test_block_diff_binding_exists() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::Char('d'),
            modifiers: platform_mod_alt(),
        };

        assert_eq!(
            config.resolve(&combo, &Context::Terminal),
            Some(&Action::BlockDiff)
        );
    }

    #[test]
    fn test_failure_trends_panel_binding_exists() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::Char('y'),
            modifiers: platform_mod_alt(),
        };
        assert_eq!(
            config.resolve(&combo, &Context::Terminal),
            Some(&Action::ToggleFailureTrendsPanel)
        );
    }

    #[test]
    fn test_workspace_insights_panel_binding_exists() {
        let config = KeybindingConfig::default();
        let combo = KeyCombo {
            key: KeyAction::Char('i'),
            modifiers: platform_mod_alt(),
        };
        assert_eq!(
            config.resolve(&combo, &Context::Terminal),
            Some(&Action::ToggleWorkspaceInsightsPanel)
        );
    }

    #[test]
    fn test_failed_block_navigation_bindings_exist() {
        let config = KeybindingConfig::default();
        let prev_combo = KeyCombo {
            key: KeyAction::Char('['),
            modifiers: platform_mod_alt(),
        };
        let next_combo = KeyCombo {
            key: KeyAction::Char(']'),
            modifiers: platform_mod_alt(),
        };
        assert_eq!(
            config.resolve(&prev_combo, &Context::Terminal),
            Some(&Action::BlockPrevFailed)
        );
        assert_eq!(
            config.resolve(&next_combo, &Context::Terminal),
            Some(&Action::BlockNextFailed)
        );
    }

    #[test]
    fn test_block_workflow_bindings_exist() {
        let config = KeybindingConfig::default();
        let rerun_split_combo = KeyCombo {
            key: KeyAction::Char('r'),
            modifiers: Modifiers {
                shift: true,
                ..platform_mod_alt()
            },
        };
        let save_workflow_combo = KeyCombo {
            key: KeyAction::Char('w'),
            modifiers: Modifiers {
                shift: true,
                ..platform_mod_alt()
            },
        };
        assert_eq!(
            config.resolve(&rerun_split_combo, &Context::Terminal),
            Some(&Action::BlockRerunInSplit)
        );
        assert_eq!(
            config.resolve(&save_workflow_combo, &Context::Terminal),
            Some(&Action::BlockSaveWorkflow)
        );
    }

    #[test]
    fn test_block_export_bindings_exist() {
        let config = KeybindingConfig::default();
        let markdown_combo = KeyCombo {
            key: KeyAction::Char('m'),
            modifiers: Modifiers {
                shift: true,
                ..platform_mod_alt()
            },
        };
        let json_combo = KeyCombo {
            key: KeyAction::Char('j'),
            modifiers: Modifiers {
                shift: true,
                ..platform_mod_alt()
            },
        };
        assert_eq!(
            config.resolve(&markdown_combo, &Context::Terminal),
            Some(&Action::BlockExportMarkdown)
        );
        assert_eq!(
            config.resolve(&json_combo, &Context::Terminal),
            Some(&Action::BlockExportJson)
        );
    }

    #[test]
    fn test_manual_session_bindings_exist() {
        let config = KeybindingConfig::default();

        let save_combo = KeyCombo {
            key: KeyAction::Char('s'),
            modifiers: platform_mod_shift(),
        };
        let load_combo = KeyCombo {
            key: KeyAction::Char('r'),
            modifiers: platform_mod_shift(),
        };

        assert_eq!(
            config.resolve(&save_combo, &Context::Terminal),
            Some(&Action::SaveSession("manual".to_string()))
        );
        assert_eq!(
            config.resolve(&load_combo, &Context::Terminal),
            Some(&Action::LoadSession("manual".to_string()))
        );
    }
}
