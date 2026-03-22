//! Main application struct: wires all subsystems together.

use walk_blocks::block::BlockManager;
use walk_blocks::block_nav::BlockNavigator;
use walk_input::editor::{EditorKey, InputEditor, InputPosition};
use walk_input::history::CommandHistory;
use walk_ui::clipboard::ClipboardManager;
use walk_ui::search::GlobalSearch;
use walk_ui::selection::SelectionManager;
use walk_ui::theme::Theme;
use walk_ui::zoom::ZoomManager;

use crate::config::WalkConfig;
use crate::keybindings::{Action, KeybindingConfig};

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
                None
            }
            Action::BlockNext => {
                self.block_navigator.select_next(self.block_manager.len());
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
}
