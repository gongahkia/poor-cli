//! Main application struct: wires all subsystems together.

use walk_blocks::block::BlockManager;
use walk_blocks::block_nav::BlockNavigator;
use walk_input::editor::{EditorKey, InputEditor, InputPosition};
use walk_input::history::CommandHistory;
use walk_terminal::terminal::SemanticEvent;
use walk_ui::clipboard::ClipboardManager;
use walk_ui::search::GlobalSearch;
use walk_ui::selection::SelectionManager;
use walk_ui::theme::Theme;
use walk_ui::zoom::ZoomManager;

use crate::config::WalkConfig;
use crate::input::InputEvent;
use crate::keybindings::{Action, Context, KeyCombo, KeybindingConfig};

/// The main Walk application state.
pub struct WalkApp {
    /// Application configuration.
    pub config: WalkConfig,
    /// Active theme.
    pub theme: Theme,
    /// Block manager for tracking command blocks.
    pub block_manager: BlockManager,
    /// Block navigator for keyboard navigation.
    pub block_navigator: BlockNavigator,
    /// Input editor.
    pub input_editor: InputEditor,
    /// Clipboard manager.
    pub clipboard: ClipboardManager,
    /// Mouse selection manager.
    pub selection: SelectionManager,
    /// Global search.
    pub global_search: GlobalSearch,
    /// Font zoom manager.
    pub zoom: ZoomManager,
    /// Keybinding configuration.
    pub keybindings: KeybindingConfig,
}

impl WalkApp {
    /// Create a new Walk application with the given configuration.
    pub fn new(config: WalkConfig) -> Self {
        let theme = if let Some(ref path) = config.theme_path {
            walk_ui::theme_loader::load_theme(path).unwrap_or_default()
        } else {
            Theme::default()
        };

        let history_path = CommandHistory::default_path();
        let history = CommandHistory::load(&history_path, 10_000);

        let input_position = match config.input_position {
            crate::config::InputPosition::Top => InputPosition::Top,
            crate::config::InputPosition::Bottom => InputPosition::Bottom,
        };

        let input_editor = InputEditor::new(
            config.shell.clone(),
            history,
            input_position,
        );

        Self {
            zoom: ZoomManager::new(config.font_size),
            config,
            theme,
            block_manager: BlockManager::new(),
            block_navigator: BlockNavigator::new(),
            input_editor,
            clipboard: ClipboardManager::new(),
            selection: SelectionManager::new(),
            global_search: GlobalSearch::new(),
            keybindings: KeybindingConfig::default(),
        }
    }

    /// Return the active keybinding context.
    pub fn current_context(&self) -> Context {
        if self.global_search.is_active {
            Context::SearchActive
        } else if self.block_navigator.selected_block_index.is_some() {
            Context::BlockSelected
        } else if self.input_editor.is_active {
            Context::InputEditor
        } else {
            Context::Terminal
        }
    }

    /// Resolve an input event through the active keybinding table.
    pub fn resolve_action(&self, event: &InputEvent) -> Option<Action> {
        let combo = KeyCombo {
            key: event.action.clone(),
            modifiers: event.modifiers,
        };
        self.keybindings
            .resolve(&combo, &self.current_context())
            .cloned()
    }

    /// Feed semantic events from the terminal into block state.
    pub fn handle_semantic_event(&mut self, event: &SemanticEvent) {
        self.block_manager.handle_event(event);
    }

    /// Dispatch a resolved action. Returns optional bytes to send to PTY.
    pub fn handle_action(&mut self, action: &Action) -> Option<Vec<u8>> {
        match action {
            Action::Copy => {
                if let Some((_, _)) = self.selection.selection_range() {
                    // Selection copy handled by caller with grid access
                }
                None
            }
            Action::Paste => {
                if let Ok(text) = self.clipboard.paste() {
                    self.input_editor.buffer.insert_at(0, &text).ok();
                    return Some(text.into_bytes());
                }
                None
            }
            Action::SelectAll => {
                self.input_editor.handle_key(EditorKey::SelectAll);
                None
            }
            Action::ZoomIn => { self.zoom.zoom_in(); None }
            Action::ZoomOut => { self.zoom.zoom_out(); None }
            Action::ZoomReset => { self.zoom.zoom_reset(); None }
            Action::BlockPrev => {
                self.block_navigator.select_prev(self.block_manager.len());
                self.sync_active_block();
                None
            }
            Action::BlockNext => {
                self.block_navigator.select_next(self.block_manager.len());
                self.sync_active_block();
                None
            }
            Action::BlockCollapse => {
                self.block_navigator.toggle_collapse(&mut self.block_manager);
                None
            }
            Action::BlockCopy | Action::BlockSearch | Action::SearchInBlock => None,
            Action::SearchGlobal => {
                self.global_search.activate();
                None
            }
            Action::ToggleInputPosition => {
                let new_pos = match self.input_editor.render_data().position {
                    InputPosition::Top => InputPosition::Bottom,
                    InputPosition::Bottom => InputPosition::Top,
                };
                self.input_editor.set_position(new_pos);
                None
            }
            Action::ClearScreen => Some(b"\x1b[2J\x1b[H".to_vec()),
            Action::SendEof => Some(b"\x04".to_vec()),
            Action::ScrollUp | Action::ScrollDown
            | Action::ScrollPageUp | Action::ScrollPageDown
            | Action::ScrollToTop | Action::ScrollToBottom => None,
            Action::NewTab | Action::CloseTab | Action::NextTab
            | Action::PrevTab | Action::SwitchToTab(_) => None,
            Action::SplitVertical | Action::SplitHorizontal | Action::CloseSplit => None,
            Action::FocusLeft | Action::FocusRight
            | Action::FocusUp | Action::FocusDown => None,
            Action::ResizeSplitLeft | Action::ResizeSplitRight
            | Action::ResizeSplitUp | Action::ResizeSplitDown => None,
        }
    }

    fn sync_active_block(&mut self) {
        self.block_manager.active_block = self
            .block_navigator
            .selected_block(&self.block_manager)
            .map(|block| block.id);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::WalkConfig;
    use crate::input::KeyAction;

    #[test]
    fn test_resolve_action_uses_active_context() {
        let mut app = WalkApp::new(WalkConfig::default());
        app.global_search.activate();

        let action = app.resolve_action(&InputEvent {
            action: KeyAction::Char('f'),
            modifiers: crate::input::Modifiers {
                ctrl: !cfg!(target_os = "macos"),
                meta: cfg!(target_os = "macos"),
                ..crate::input::Modifiers::default()
            },
            is_repeat: false,
        });

        assert_eq!(action, Some(Action::SearchGlobal));
    }

    #[test]
    fn test_handle_semantic_event_builds_blocks() {
        let mut app = WalkApp::new(WalkConfig::default());
        app.handle_semantic_event(&SemanticEvent::PromptStart { line: 0 });
        app.block_manager.set_command_text("echo hello");
        app.handle_semantic_event(&SemanticEvent::CommandStart { line: 1 });
        app.handle_semantic_event(&SemanticEvent::OutputStart { line: 2 });
        app.handle_semantic_event(&SemanticEvent::CommandEnd {
            line: 3,
            exit_code: Some(0),
        });

        assert_eq!(app.block_manager.len(), 1);
    }

    #[test]
    fn test_select_all_routes_to_editor() {
        let mut app = WalkApp::new(WalkConfig::default());
        app.input_editor.handle_key(EditorKey::Char('x'));
        let _ = app.handle_action(&Action::SelectAll);

        assert_eq!(app.input_editor.buffer.cursors()[0].anchor, Some(0));
    }
}
