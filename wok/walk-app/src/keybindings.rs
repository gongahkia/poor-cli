//! Keybinding system: maps key combinations to actions.

use std::collections::HashMap;

use crate::input::{KeyAction, Modifiers};

/// All bindable actions in Walk.
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
    /// Toggle collapse on selected block.
    BlockCollapse,
    /// Search within selected block.
    BlockSearch,
    /// Search within selected block (alias).
    SearchInBlock,
    /// Global terminal search.
    SearchGlobal,
    /// Toggle input position (top/bottom).
    ToggleInputPosition,
    /// Increase font size.
    ZoomIn,
    /// Decrease font size.
    ZoomOut,
    /// Reset font size.
    ZoomReset,
    /// Clear terminal screen.
    ClearScreen,
    /// Send EOF (Ctrl+D).
    SendEof,
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
}

/// Keybinding configuration.
pub struct KeybindingConfig {
    /// Global keybindings.
    pub bindings: HashMap<KeyCombo, Action>,
    /// Context-specific keybindings.
    pub context_bindings: HashMap<Context, HashMap<KeyCombo, Action>>,
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
            KeyCombo { key: KeyAction::Char('t'), modifiers: pm },
            Action::NewTab,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('w'), modifiers: pm },
            Action::CloseTab,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Tab, modifiers: pm },
            Action::NextTab,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Tab, modifiers: pms },
            Action::PrevTab,
        );

        // Tab switching 1-9
        for i in 1..=9u8 {
            let ch = char::from(b'0' + i);
            bindings.insert(
                KeyCombo { key: KeyAction::Char(ch), modifiers: pm },
                Action::SwitchToTab(i),
            );
        }

        // Split panes
        bindings.insert(
            KeyCombo { key: KeyAction::Char('d'), modifiers: pm },
            Action::SplitVertical,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('d'), modifiers: pms },
            Action::SplitHorizontal,
        );

        // Focus direction
        bindings.insert(
            KeyCombo { key: KeyAction::ArrowLeft, modifiers: pma },
            Action::FocusLeft,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::ArrowRight, modifiers: pma },
            Action::FocusRight,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::ArrowUp, modifiers: pma },
            Action::FocusUp,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::ArrowDown, modifiers: pma },
            Action::FocusDown,
        );

        // Clipboard
        bindings.insert(
            KeyCombo { key: KeyAction::Copy, modifiers: Modifiers::default() },
            Action::Copy,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Paste, modifiers: Modifiers::default() },
            Action::Paste,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::SelectAll, modifiers: Modifiers::default() },
            Action::SelectAll,
        );

        // Block navigation
        bindings.insert(
            KeyCombo { key: KeyAction::ArrowUp, modifiers: pm },
            Action::BlockPrev,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::ArrowDown, modifiers: pm },
            Action::BlockNext,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('c'), modifiers: pms },
            Action::BlockCopy,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('e'), modifiers: pms },
            Action::BlockCollapse,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('f'), modifiers: pms },
            Action::SearchInBlock,
        );

        // Search
        bindings.insert(
            KeyCombo { key: KeyAction::Char('f'), modifiers: pm },
            Action::SearchGlobal,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('i'), modifiers: pms },
            Action::ToggleInputPosition,
        );

        // Zoom
        bindings.insert(
            KeyCombo { key: KeyAction::Char('='), modifiers: pm },
            Action::ZoomIn,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('-'), modifiers: pm },
            Action::ZoomOut,
        );
        bindings.insert(
            KeyCombo { key: KeyAction::Char('0'), modifiers: pm },
            Action::ZoomReset,
        );

        // Clear screen
        bindings.insert(
            KeyCombo { key: KeyAction::Char('k'), modifiers: pm },
            Action::ClearScreen,
        );

        Self {
            bindings,
            context_bindings: HashMap::new(),
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
        assert_eq!(config.resolve(&combo, &Context::Terminal), Some(&Action::BlockCopy));
    }
}
