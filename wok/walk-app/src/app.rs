//! Main application struct: wires all subsystems together.

use crate::action_effects::{
    ActionEffects, ClipboardEffect, OverlayEffect, RuntimeEffect, ViewportEffect, WorkspaceEffect,
};
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

/// Active input surface for a pane.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputMode {
    /// The shell prompt inside the PTY is the primary editor.
    ShellNative,
    /// The owned command palette / scratch editor is active.
    CommandPalette,
}

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
    /// Active input mode.
    pub input_mode: InputMode,
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

        let mut input_editor = InputEditor::new(config.shell.clone(), history, input_position);
        input_editor.is_active = false;

        Self {
            zoom: ZoomManager::new(config.font_size),
            config,
            theme,
            block_manager: BlockManager::new(),
            block_navigator: BlockNavigator::new(),
            input_editor,
            input_mode: InputMode::ShellNative,
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
        } else if self.input_mode == InputMode::CommandPalette {
            Context::InputEditor
        } else if self.block_navigator.selected_block_index.is_some() {
            Context::BlockSelected
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

    /// Dispatch a resolved action and return typed runtime effects.
    pub fn handle_action(&mut self, action: &Action) -> ActionEffects {
        let mut effects = ActionEffects::new();

        match action {
            Action::Copy => {
                effects.push(RuntimeEffect::Clipboard(ClipboardEffect::CopySelection));
            }
            Action::Paste => {
                effects.push(RuntimeEffect::Clipboard(ClipboardEffect::Paste));
            }
            Action::SelectAll => {
                if self.input_mode == InputMode::CommandPalette {
                    self.input_editor.handle_key(EditorKey::SelectAll);
                }
            }
            Action::ZoomIn => {
                self.zoom.zoom_in();
                effects.push(RuntimeEffect::Zoom(self.zoom.current_size()));
            }
            Action::ZoomOut => {
                self.zoom.zoom_out();
                effects.push(RuntimeEffect::Zoom(self.zoom.current_size()));
            }
            Action::ZoomReset => {
                self.zoom.zoom_reset();
                effects.push(RuntimeEffect::Zoom(self.zoom.current_size()));
            }
            Action::BlockPrev => {
                self.block_navigator.select_prev(self.block_manager.len());
                self.sync_active_block();
            }
            Action::BlockNext => {
                self.block_navigator.select_next(self.block_manager.len());
                self.sync_active_block();
            }
            Action::BlockCollapse => {
                self.block_navigator
                    .toggle_collapse(&mut self.block_manager);
            }
            Action::BlockCopy => {
                effects.push(RuntimeEffect::Clipboard(ClipboardEffect::CopySelectedBlock));
            }
            Action::BlockSearch | Action::SearchInBlock | Action::SearchGlobal => {
                effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenSearch));
            }
            Action::CommandPalette => {
                effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenCommandPalette));
            }
            Action::ToggleInputPosition => {
                let new_pos = match self.input_editor.render_data().position {
                    InputPosition::Top => InputPosition::Bottom,
                    InputPosition::Bottom => InputPosition::Top,
                };
                self.input_editor.set_position(new_pos);
            }
            Action::ClearScreen => {
                effects.push(RuntimeEffect::PtyWrite(b"\x1b[2J\x1b[H".to_vec()));
            }
            Action::SendEof => {
                effects.push(RuntimeEffect::PtyWrite(b"\x04".to_vec()));
            }
            Action::ScrollUp => {
                effects.push(RuntimeEffect::Viewport(ViewportEffect::ScrollLines(3)));
            }
            Action::ScrollDown => {
                effects.push(RuntimeEffect::Viewport(ViewportEffect::ScrollLines(-3)));
            }
            Action::ScrollPageUp => {
                effects.push(RuntimeEffect::Viewport(ViewportEffect::ScrollPages(1)));
            }
            Action::ScrollPageDown => {
                effects.push(RuntimeEffect::Viewport(ViewportEffect::ScrollPages(-1)));
            }
            Action::ScrollToTop => {
                effects.push(RuntimeEffect::Viewport(ViewportEffect::ScrollToTop));
            }
            Action::ScrollToBottom => {
                effects.push(RuntimeEffect::Viewport(ViewportEffect::ScrollToBottom));
            }
            Action::NewTab => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::NewTab));
            }
            Action::CloseTab => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::CloseTab));
            }
            Action::NextTab => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::NextTab));
            }
            Action::PrevTab => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::PrevTab));
            }
            Action::SwitchToTab(index) => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::SwitchToTab(
                    *index,
                )));
            }
            Action::SplitVertical => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::SplitVertical));
            }
            Action::SplitHorizontal => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::SplitHorizontal));
            }
            Action::CloseSplit => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::CloseSplit));
            }
            Action::FocusLeft => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::FocusLeft));
            }
            Action::FocusRight => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::FocusRight));
            }
            Action::FocusUp => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::FocusUp));
            }
            Action::FocusDown => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::FocusDown));
            }
            Action::ResizeSplitLeft => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::ResizeSplitLeft));
            }
            Action::ResizeSplitRight => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::ResizeSplitRight));
            }
            Action::ResizeSplitUp => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::ResizeSplitUp));
            }
            Action::ResizeSplitDown => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::ResizeSplitDown));
            }
            Action::SaveSession(name) => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::SaveSession(
                    name.clone(),
                )));
            }
            Action::LoadSession(name) => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::LoadSession(
                    name.clone(),
                )));
            }
        }

        effects
    }

    /// Open the command palette input mode.
    pub fn open_command_palette(&mut self) {
        self.input_mode = InputMode::CommandPalette;
        self.input_editor.is_active = true;
    }

    /// Close the command palette input mode.
    pub fn close_command_palette(&mut self) {
        self.input_mode = InputMode::ShellNative;
        self.input_editor.is_active = false;
        self.input_editor.buffer.clear();
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
        app.handle_semantic_event(&SemanticEvent::PromptStart { row: 0 });
        app.block_manager.set_command_text("echo hello");
        app.handle_semantic_event(&SemanticEvent::CommandStart { row: 1 });
        app.handle_semantic_event(&SemanticEvent::OutputStart { row: 2 });
        app.handle_semantic_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        assert_eq!(app.block_manager.len(), 1);
    }

    #[test]
    fn test_select_all_routes_to_editor() {
        let mut app = WalkApp::new(WalkConfig::default());
        app.open_command_palette();
        app.input_editor.handle_key(EditorKey::Char('x'));
        let _ = app.handle_action(&Action::SelectAll);

        assert_eq!(app.input_editor.buffer.cursors()[0].anchor, Some(0));
    }

    #[test]
    fn test_command_palette_is_not_active_by_default() {
        let app = WalkApp::new(WalkConfig::default());
        assert_eq!(app.input_mode, InputMode::ShellNative);
        assert!(!app.input_editor.is_active);
    }

    #[test]
    fn test_search_action_emits_overlay_effect() {
        let mut app = WalkApp::new(WalkConfig::default());
        let effects = app.handle_action(&Action::SearchGlobal);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::Overlay(OverlayEffect::OpenSearch)]
        );
    }
}
