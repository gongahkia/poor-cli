//! Main application struct: wires all subsystems together.

use crate::action_effects::{
    ActionEffects, ClipboardEffect, OverlayEffect, RuntimeEffect, ViewportEffect, WorkspaceEffect,
};
use crate::block_query::{BlockQueryMode, BlockQueryState};
use crate::command_search::CommandSearchState;
use wok_blocks::block::BlockManager;
use wok_blocks::block_nav::BlockNavigator;
use wok_input::editor::{EditorKey, InputEditor, InputPosition};
use wok_terminal::terminal::SemanticEvent;
use wok_ui::clipboard::ClipboardManager;
use wok_ui::command_palette::CommandPaletteState;
use wok_ui::quick_select::QuickSelectState;
use wok_ui::search::GlobalSearch;
use wok_ui::selection::SelectionManager;
use wok_ui::theme::Theme;
use wok_ui::vi_mode::ViModeState;
use wok_ui::zoom::ZoomManager;

use crate::config::WokConfig;
use crate::input::InputEvent;
use crate::keybindings::{Action, Context, KeyCombo, KeybindingConfig};

/// Active input surface for a pane.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputMode {
    /// The shell prompt inside the PTY is the primary editor.
    ShellNative,
    /// Wok's owned input editor is the primary command-entry path.
    OwnedInput,
    /// The owned command palette / scratch editor is active.
    CommandPalette,
}

/// The main Wok application state.
pub struct WokApp {
    /// Application configuration.
    pub config: WokConfig,
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
    /// Command-history search overlay.
    pub command_search: Option<CommandSearchState>,
    /// Rich command palette state.
    pub command_palette: CommandPaletteState,
    /// Quick-select overlay.
    pub quick_select: QuickSelectState,
    /// Block-local find/filter overlay state.
    pub block_query: Option<BlockQueryState>,
    /// Active vi-mode state.
    pub vi_mode: Option<ViModeState>,
    /// Draft to restore after dismissing the command palette.
    pub saved_draft: Option<String>,
    /// Font zoom manager.
    pub zoom: ZoomManager,
    /// Keybinding configuration.
    pub keybindings: KeybindingConfig,
}

impl WokApp {
    /// Create a new Wok application with the given configuration.
    pub fn new(config: WokConfig) -> Self {
        let theme = if let Some(ref path) = config.theme_path {
            wok_ui::theme_loader::load_theme(path).unwrap_or_default()
        } else {
            Theme::default()
        };

        let input_position = match config.input_position {
            crate::config::InputPosition::Top => InputPosition::Top,
            crate::config::InputPosition::Bottom => InputPosition::Bottom,
        };

        let input_mode = if matches!(
            config.command_entry_mode,
            crate::config::CommandEntryMode::OwnedPrimary
        ) {
            InputMode::OwnedInput
        } else {
            InputMode::ShellNative
        };

        let mut input_editor = InputEditor::new(config.shell.clone(), input_position);
        input_editor.is_active = matches!(
            config.command_entry_mode,
            crate::config::CommandEntryMode::OwnedPrimary
        );

        Self {
            zoom: ZoomManager::new(config.font_size),
            config,
            theme,
            block_manager: BlockManager::new(),
            block_navigator: BlockNavigator::new(),
            input_editor,
            input_mode,
            clipboard: ClipboardManager::new(),
            selection: SelectionManager::new(),
            global_search: GlobalSearch::new(),
            command_search: None,
            command_palette: CommandPaletteState::new(),
            quick_select: QuickSelectState::new(),
            block_query: None,
            vi_mode: None,
            saved_draft: None,
            keybindings: KeybindingConfig::default(),
        }
    }

    /// Return the active keybinding context.
    pub fn current_context(&self) -> Context {
        if self.global_search.is_active
            || self.block_query.is_some()
            || self.command_search.is_some()
        {
            Context::SearchActive
        } else if self.vi_mode.is_some() {
            Context::ViMode
        } else if self.quick_select.active {
            Context::QuickSelect
        } else if self.input_mode == InputMode::CommandPalette
            || (self.input_mode == InputMode::OwnedInput && self.input_editor.is_active)
        {
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
                if matches!(
                    self.input_mode,
                    InputMode::CommandPalette | InputMode::OwnedInput
                ) && self.input_editor.is_active
                {
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
            Action::OpenSettings => {
                effects.push(RuntimeEffect::Status("Opening settings".to_string()));
            }
            Action::ResetSettings => {}
            Action::BlockPrev => {
                self.block_navigator.select_prev(self.block_manager.len());
                self.sync_active_block();
            }
            Action::BlockNext => {
                self.block_navigator.select_next(self.block_manager.len());
                self.sync_active_block();
            }
            Action::BlockCollapse => {
                if let Some(block_id) = self.selected_or_latest_block_id() {
                    self.select_block(block_id);
                }
                self.block_navigator
                    .toggle_collapse(&mut self.block_manager);
            }
            Action::BlockCopy => {
                if self.selected_or_latest_block_id().is_some() {
                    effects.push(RuntimeEffect::Clipboard(ClipboardEffect::CopySelectedBlock));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::BlockCopyCommand => {
                if self.selected_or_latest_block_id().is_some() {
                    effects.push(RuntimeEffect::Clipboard(
                        ClipboardEffect::CopySelectedBlockCommand,
                    ));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::BlockCopyOutput => {
                if self.selected_or_latest_block_id().is_some() {
                    effects.push(RuntimeEffect::Clipboard(
                        ClipboardEffect::CopySelectedBlockOutput,
                    ));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::BlockToggleBookmark => {
                let target_block_id = self.selected_or_latest_block_id();
                match self.block_manager.toggle_bookmark(target_block_id) {
                    Some(_) => {
                        if let Some(block_id) = target_block_id {
                            self.select_block(block_id);
                        }
                    }
                    None => effects.push(RuntimeEffect::Status("No block available".to_string())),
                }
            }
            Action::BlockPrevBookmark => {
                if let Some(block_id) = self
                    .block_manager
                    .prev_bookmark(self.selected_or_latest_block_id())
                {
                    self.select_block(block_id);
                } else {
                    effects.push(RuntimeEffect::Status("No bookmarked blocks".to_string()));
                }
            }
            Action::BlockNextBookmark => {
                if let Some(block_id) = self
                    .block_manager
                    .next_bookmark(self.selected_or_latest_block_id())
                {
                    self.select_block(block_id);
                } else {
                    effects.push(RuntimeEffect::Status("No bookmarked blocks".to_string()));
                }
            }
            Action::BlockPrevFailed => {
                if let Some(block_id) = self
                    .block_manager
                    .prev_failed(self.selected_or_latest_block_id())
                {
                    self.select_block(block_id);
                } else {
                    effects.push(RuntimeEffect::Status("No failed blocks".to_string()));
                }
            }
            Action::BlockNextFailed => {
                if let Some(block_id) = self
                    .block_manager
                    .next_failed(self.selected_or_latest_block_id())
                {
                    self.select_block(block_id);
                } else {
                    effects.push(RuntimeEffect::Status("No failed blocks".to_string()));
                }
            }
            Action::BlockFind => {
                if let Some(block_id) = self.selected_or_latest_block_id() {
                    self.select_block(block_id);
                    effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenBlockQuery {
                        mode: BlockQueryMode::Find,
                        target_block_id: block_id,
                    }));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::BlockFilter => {
                if let Some(block_id) = self.selected_or_latest_block_id() {
                    self.select_block(block_id);
                    effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenBlockQuery {
                        mode: BlockQueryMode::Filter,
                        target_block_id: block_id,
                    }));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::BlockDiff => {
                let Some(block_id) = self.selected_or_latest_block_id() else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                    return effects;
                };
                let can_diff = self.block_manager.get_block(block_id).is_some_and(|block| {
                    block.exit_code.is_some() && !block.command_text.trim().is_empty()
                });
                if can_diff {
                    self.select_block(block_id);
                    effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenBlockQuery {
                        mode: BlockQueryMode::Diff,
                        target_block_id: block_id,
                    }));
                } else {
                    effects.push(RuntimeEffect::Status(
                        "Only completed blocks with commands can be diffed".to_string(),
                    ));
                }
            }
            Action::BlockRerun => {
                let Some(block) = self.selected_or_latest_block() else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                    return effects;
                };
                if block.exit_code.is_none() || block.command_text.trim().is_empty() {
                    effects.push(RuntimeEffect::Status(
                        "Only completed blocks with commands can be rerun".to_string(),
                    ));
                } else {
                    effects.push(RuntimeEffect::PtyWrite(
                        format!("{}\r", block.command_text).into_bytes(),
                    ));
                }
            }
            Action::BlockRerunInSplit => {
                let Some(block) = self.selected_or_latest_block() else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                    return effects;
                };
                if block.exit_code.is_none() || block.command_text.trim().is_empty() {
                    effects.push(RuntimeEffect::Status(
                        "Only completed blocks with commands can be rerun in split".to_string(),
                    ));
                } else {
                    effects.push(RuntimeEffect::Workspace(WorkspaceEffect::SplitVertical));
                    effects.push(RuntimeEffect::PtyWrite(
                        format!("{}\r", block.command_text).into_bytes(),
                    ));
                }
            }
            Action::BlockSaveWorkflow => {
                if self.selected_or_latest_block_id().is_some() {
                    effects.push(RuntimeEffect::Status(
                        "Saving selected block as workflow".to_string(),
                    ));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::BlockExportMarkdown => {
                if self.selected_or_latest_block_id().is_some() {
                    effects.push(RuntimeEffect::Status(
                        "Exporting selected block as Markdown".to_string(),
                    ));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::BlockExportJson => {
                if self.selected_or_latest_block_id().is_some() {
                    effects.push(RuntimeEffect::Status(
                        "Exporting selected block as JSON".to_string(),
                    ));
                } else {
                    effects.push(RuntimeEffect::Status("No block available".to_string()));
                }
            }
            Action::ToggleFailureTrendsPanel => {
                effects.push(RuntimeEffect::Overlay(
                    OverlayEffect::ToggleFailureTrendsPanel,
                ));
            }
            Action::ToggleWorkspaceInsightsPanel => {
                effects.push(RuntimeEffect::Overlay(
                    OverlayEffect::ToggleWorkspaceInsightsPanel,
                ));
            }
            Action::GitChanges => {}
            Action::GitWorktrees => {}
            Action::SearchGlobal => {
                effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenSearch));
            }
            Action::EnterViMode => {
                effects.push(RuntimeEffect::Status("Vi mode".to_string()));
            }
            Action::ToggleBroadcast => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::ToggleBroadcast));
            }
            Action::ToggleTypewriterEffect => {}
            Action::CycleVisualEffect => {}
            Action::NewFloatingPane => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::NewFloatingPane));
            }
            Action::ToggleFloatingPane => {
                effects.push(RuntimeEffect::Workspace(
                    WorkspaceEffect::ToggleFloatingPane,
                ));
            }
            Action::CloseFloatingPane => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::CloseFloatingPane));
            }
            Action::NextLayout => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::NextLayout));
            }
            Action::PrevLayout => {
                effects.push(RuntimeEffect::Workspace(WorkspaceEffect::PrevLayout));
            }
            Action::CommandPalette => {
                effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenCommandPalette));
            }
            Action::CommandSearch => {
                effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenCommandSearch));
            }
            Action::QuickSelect => {
                effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenQuickSelect));
            }
            Action::QuickSelectBlock => {
                effects.push(RuntimeEffect::Overlay(OverlayEffect::OpenQuickSelectBlock));
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
            // Discovery palettes — handled directly in WokHandler (no app-level
            // effect; they manipulate the global theme/keybinding registries).
            Action::ThemePicker | Action::KeybindingDiscovery | Action::SettingsDiscovery => {}
        }

        effects
    }

    /// Open the command palette input mode.
    pub fn open_command_palette(&mut self) {
        if self.input_mode == InputMode::OwnedInput {
            self.saved_draft = Some(self.input_editor.buffer.text());
            self.input_editor.buffer.clear();
        }
        self.input_mode = InputMode::CommandPalette;
        self.input_editor.is_active = true;
        self.command_palette.is_open = true;
    }

    /// Close the command palette input mode.
    pub fn close_command_palette(&mut self) {
        self.input_mode = if matches!(
            self.config.command_entry_mode,
            crate::config::CommandEntryMode::OwnedPrimary
        ) {
            InputMode::OwnedInput
        } else {
            InputMode::ShellNative
        };
        self.input_editor.is_active = self.input_mode == InputMode::OwnedInput;
        if let Some(saved_draft) = self.saved_draft.take() {
            self.input_editor.buffer.set_text(&saved_draft);
        } else {
            self.input_editor.buffer.clear();
        }
        self.command_palette.close();
    }

    /// Return the selected block when present, otherwise the latest block.
    pub fn selected_or_latest_block(&self) -> Option<&wok_blocks::block::Block> {
        self.block_navigator
            .selected_block(&self.block_manager)
            .or_else(|| self.block_manager.selected_or_latest_block())
    }

    /// Return the selected block id when present, otherwise the latest block id.
    pub fn selected_or_latest_block_id(&self) -> Option<u64> {
        self.selected_or_latest_block().map(|block| block.id)
    }

    /// Select a specific block by id.
    pub fn select_block(&mut self, block_id: u64) -> bool {
        if !self
            .block_navigator
            .select_block(&self.block_manager, block_id)
        {
            return false;
        }
        self.sync_active_block();
        true
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
    use crate::config::{CommandEntryMode, WokConfig};
    use crate::input::{InputEventType, KeyAction};

    #[test]
    fn test_resolve_action_uses_active_context() {
        let mut app = WokApp::new(WokConfig::default());
        app.global_search.activate();

        let action = app.resolve_action(&InputEvent {
            action: KeyAction::Char('f'),
            modifiers: crate::input::Modifiers {
                ctrl: !cfg!(target_os = "macos"),
                meta: cfg!(target_os = "macos"),
                ..crate::input::Modifiers::default()
            },
            is_repeat: false,
            event_type: InputEventType::Press,
        });

        assert_eq!(action, Some(Action::SearchGlobal));
    }

    #[test]
    fn test_handle_semantic_event_builds_blocks() {
        let mut app = WokApp::new(WokConfig::default());
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
        let mut app = WokApp::new(WokConfig::default());
        app.open_command_palette();
        app.input_editor.handle_key(EditorKey::Char('x'));
        let _ = app.handle_action(&Action::SelectAll);

        assert_eq!(app.input_editor.buffer.cursors()[0].anchor, Some(0));
    }

    #[test]
    fn test_command_palette_is_not_active_by_default() {
        let app = WokApp::new(WokConfig::default());
        assert_eq!(app.input_mode, InputMode::ShellNative);
        assert!(!app.input_editor.is_active);
    }

    #[test]
    fn test_owned_primary_mode_starts_in_owned_input() {
        let config = WokConfig {
            command_entry_mode: CommandEntryMode::OwnedPrimary,
            ..WokConfig::default()
        };

        let app = WokApp::new(config);

        assert_eq!(app.input_mode, InputMode::OwnedInput);
        assert!(app.input_editor.is_active);
    }

    #[test]
    fn test_search_action_emits_overlay_effect() {
        let mut app = WokApp::new(WokConfig::default());
        let effects = app.handle_action(&Action::SearchGlobal);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::Overlay(OverlayEffect::OpenSearch)]
        );
    }

    #[test]
    fn test_command_search_action_emits_overlay_effect() {
        let config = WokConfig {
            command_entry_mode: CommandEntryMode::OwnedPrimary,
            ..WokConfig::default()
        };
        let mut app = WokApp::new(config);
        let effects = app.handle_action(&Action::CommandSearch);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::Overlay(OverlayEffect::OpenCommandSearch)]
        );
    }

    #[test]
    fn test_failure_trends_action_emits_overlay_toggle() {
        let mut app = WokApp::new(WokConfig::default());
        let effects = app.handle_action(&Action::ToggleFailureTrendsPanel);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::Overlay(
                OverlayEffect::ToggleFailureTrendsPanel
            )]
        );
    }

    #[test]
    fn test_workspace_insights_action_emits_overlay_toggle() {
        let mut app = WokApp::new(WokConfig::default());
        let effects = app.handle_action(&Action::ToggleWorkspaceInsightsPanel);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::Overlay(
                OverlayEffect::ToggleWorkspaceInsightsPanel
            )]
        );
    }

    #[test]
    fn test_block_find_targets_selected_or_latest_block() {
        let mut app = WokApp::new(WokConfig::default());
        app.handle_semantic_event(&SemanticEvent::PromptStart { row: 0 });
        app.handle_semantic_event(&SemanticEvent::CommandStart { row: 1 });
        app.handle_semantic_event(&SemanticEvent::CommandText {
            row: 1,
            text: "cargo test".to_string(),
        });
        app.handle_semantic_event(&SemanticEvent::OutputStart { row: 2 });
        app.handle_semantic_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        let effects = app.handle_action(&Action::BlockFind);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::Overlay(OverlayEffect::OpenBlockQuery {
                mode: BlockQueryMode::Find,
                target_block_id: 1,
            })]
        );
    }

    #[test]
    fn test_block_rerun_emits_pty_write() {
        let mut app = WokApp::new(WokConfig::default());
        app.handle_semantic_event(&SemanticEvent::PromptStart { row: 0 });
        app.handle_semantic_event(&SemanticEvent::CommandStart { row: 1 });
        app.handle_semantic_event(&SemanticEvent::CommandText {
            row: 1,
            text: "cargo test".to_string(),
        });
        app.handle_semantic_event(&SemanticEvent::OutputStart { row: 2 });
        app.handle_semantic_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        let effects = app.handle_action(&Action::BlockRerun);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::PtyWrite(b"cargo test\r".to_vec())]
        );
    }

    #[test]
    fn test_block_rerun_in_split_emits_split_then_pty_write() {
        let mut app = WokApp::new(WokConfig::default());
        app.handle_semantic_event(&SemanticEvent::PromptStart { row: 0 });
        app.handle_semantic_event(&SemanticEvent::CommandStart { row: 1 });
        app.handle_semantic_event(&SemanticEvent::CommandText {
            row: 1,
            text: "cargo test".to_string(),
        });
        app.handle_semantic_event(&SemanticEvent::OutputStart { row: 2 });
        app.handle_semantic_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        let effects = app.handle_action(&Action::BlockRerunInSplit);

        assert_eq!(
            effects.effects,
            vec![
                RuntimeEffect::Workspace(WorkspaceEffect::SplitVertical),
                RuntimeEffect::PtyWrite(b"cargo test\r".to_vec())
            ]
        );
    }

    #[test]
    fn test_block_diff_targets_selected_or_latest_block() {
        let mut app = WokApp::new(WokConfig::default());
        app.handle_semantic_event(&SemanticEvent::PromptStart { row: 0 });
        app.handle_semantic_event(&SemanticEvent::CommandStart { row: 1 });
        app.handle_semantic_event(&SemanticEvent::CommandText {
            row: 1,
            text: "cargo test".to_string(),
        });
        app.handle_semantic_event(&SemanticEvent::OutputStart { row: 2 });
        app.handle_semantic_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        let effects = app.handle_action(&Action::BlockDiff);

        assert_eq!(
            effects.effects,
            vec![RuntimeEffect::Overlay(OverlayEffect::OpenBlockQuery {
                mode: BlockQueryMode::Diff,
                target_block_id: 1,
            })]
        );
    }

    #[test]
    fn test_failed_block_navigation_selects_failed_blocks() {
        let mut app = WokApp::new(WokConfig::default());
        for (row, code) in [(0, Some(0)), (10, Some(1)), (20, Some(2))] {
            app.handle_semantic_event(&SemanticEvent::PromptStart { row });
            app.handle_semantic_event(&SemanticEvent::CommandStart { row: row + 1 });
            app.handle_semantic_event(&SemanticEvent::OutputStart { row: row + 2 });
            app.handle_semantic_event(&SemanticEvent::CommandEnd {
                row: row + 3,
                exit_code: code,
            });
        }

        let _ = app.handle_action(&Action::BlockNextFailed);
        assert_eq!(app.selected_or_latest_block_id(), Some(2));

        let _ = app.handle_action(&Action::BlockNextFailed);
        assert_eq!(app.selected_or_latest_block_id(), Some(3));

        let _ = app.handle_action(&Action::BlockPrevFailed);
        assert_eq!(app.selected_or_latest_block_id(), Some(2));
    }
}
