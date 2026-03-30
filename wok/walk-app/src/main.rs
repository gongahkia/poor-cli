//! Walk terminal emulator entry point.

use std::collections::HashMap;
use std::collections::HashSet;
use std::collections::VecDeque;
use std::error::Error;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;

use clap::Parser;
use regex::Regex;
use serde::Serialize;
use serde_json::json;
use tracing::{info, warn};
use walk_app::action_effects::{
    ActionEffects, ClipboardEffect, OverlayEffect, RuntimeEffect, ViewportEffect, WorkspaceEffect,
};
use walk_app::app::{InputMode, WalkApp};
use walk_app::block_query::{BlockQueryMode, BlockQueryState};
use walk_app::command_search::{CommandSearchScope, CommandSearchState};
use walk_app::config::{TriggerScopeConfig, WalkConfig};
use walk_app::event_loop::run_event_loop;
use walk_app::handler::AppHandler;
use walk_app::input::{InputEvent, KeyAction};
use walk_app::keybindings::Action;
use walk_app::plugin_host::PluginHost;
use walk_app::scripting::{
    QuickSelectPatternRequest, ThemeRequest, TriggerRequest, WorkflowRequest,
};
use walk_app::session::{
    block_from_state, block_to_state, default_session_path, history_entry_from_state,
    history_entry_to_state, load_session, named_session_path, save_session, split_node_from_state,
    split_node_to_state, PaneState, WorkspaceSessionState, WorkspaceTabState,
};
use walk_app::window::WindowConfig;
use walk_app::workspace::{FocusDirection, PaneId, WorkspaceState, WorkspaceTab};
use walk_blocks::block::Block;
use walk_blocks::triggers::{
    Trigger, TriggerAction, TriggerEngine, TriggerHighlight, TriggerMatch, TriggerScope,
};
use walk_input::editor::{EditorAction, EditorKey};
use walk_input::history::{prefix_matches, CommandHistory, HistoryEntry};
use walk_input::workflows::WorkflowStore;
use walk_renderer::atlas::GlyphAtlas;
use walk_renderer::damage::DirtyRegion;
use walk_renderer::font::FontSystem;
use walk_renderer::gpu::GpuContext;
use walk_renderer::pipeline::CursorShape;
use walk_renderer::pipeline::QuadBatch;
use walk_renderer::render_pipeline::TerminalRenderPipeline;
use walk_terminal::shell::ShellType;
use walk_terminal::state::{CellColor, CellRenderData};
use walk_terminal::terminal::SemanticEvent;
use walk_terminal::terminal::Terminal;
use walk_ui::background::BackgroundRenderer;
use walk_ui::command_palette::{
    CommandPaletteState, PaletteAction, PaletteCategory, PaletteEntry,
};
use walk_ui::layout::Rect;
use walk_ui::links::detect_links;
use walk_ui::quick_select::{PatternRegistry, QuickSelectScope};
use walk_ui::search::SearchLine;
use walk_ui::selection::{CellPos, SelectionState};
use walk_ui::splits::SplitManager;
use walk_ui::theme::Theme;
use walk_ui::theme_watcher::ThemeWatcher;
use walk_ui::vi_mode::{ViModeState, ViPending, ViSubMode};
use walk_ui::viewport::ViewportRenderer;
use winit::dpi::{PhysicalPosition, PhysicalSize};
use winit::event::MouseButton;
use winit::window::Window;

/// Walk — a GPU-accelerated terminal emulator with Blocks.
#[derive(Parser, Debug)]
#[command(name = "walk", version, about)]
struct Cli {
    /// Override the default shell.
    #[arg(long)]
    shell: Option<String>,

    /// Window title.
    #[arg(long, default_value = "Walk")]
    title: String,

    /// Initial working directory.
    #[arg(long)]
    working_dir: Option<String>,
}

/// GPU render state, initialized after window creation.
struct RenderState {
    #[allow(dead_code)]
    instance: wgpu::Instance,
    surface: wgpu::Surface<'static>,
    gpu: GpuContext,
    pipeline: TerminalRenderPipeline,
    batch: QuadBatch,
    atlas: GlyphAtlas,
}

/// Window sub-rectangles used by the single-pane runtime.
#[derive(Clone, Copy, PartialEq)]
struct UiRects {
    viewport: Rect,
    input: Rect,
}

impl Default for UiRects {
    fn default() -> Self {
        Self {
            viewport: Rect::new(0.0, 0.0, 0.0, 0.0),
            input: Rect::new(0.0, 0.0, 0.0, 0.0),
        }
    }
}

/// Global window chrome rectangles shared by the workspace.
#[derive(Clone, Copy, PartialEq)]
struct ChromeRects {
    tab_bar: Rect,
    content: Rect,
    status: Rect,
}

impl Default for ChromeRects {
    fn default() -> Self {
        Self {
            tab_bar: Rect::new(0.0, 0.0, 0.0, 0.0),
            content: Rect::new(0.0, 0.0, 0.0, 0.0),
            status: Rect::new(0.0, 0.0, 0.0, 0.0),
        }
    }
}

#[derive(Clone, PartialEq, Eq)]
struct PaneOverlaySignature {
    selected_block_id: Option<u64>,
    blocks: Vec<(u64, usize, usize, Option<i32>, bool, bool)>,
    search_query: String,
    search_current: usize,
    search_matches: Vec<(usize, u16, u16, Option<u64>, bool)>,
    block_query: Option<BlockQueryOverlaySignature>,
}

#[derive(Clone, PartialEq, Eq)]
struct BlockQueryOverlaySignature {
    mode: BlockQueryMode,
    target_block_id: u64,
    query: String,
    current_match: usize,
    overlay_scroll_offset: usize,
    matches: Vec<(usize, usize, usize)>,
}

#[derive(Clone, PartialEq, Eq)]
struct PaneRowSignature {
    absolute_row: usize,
    render_row: Option<usize>,
    cells: Vec<CellRenderData>,
}

struct PaneRowCache {
    dirty: DirtyRegion,
    row_batches: Vec<QuadBatch>,
    row_signatures: Vec<Option<PaneRowSignature>>,
    overlay_signature: Option<PaneOverlaySignature>,
    cols: usize,
}

impl PaneRowCache {
    fn new(rows: usize, cols: usize) -> Self {
        Self {
            dirty: DirtyRegion::new(rows),
            row_batches: (0..rows).map(|_| Self::row_batch(cols)).collect(),
            row_signatures: vec![None; rows],
            overlay_signature: None,
            cols,
        }
    }

    fn resize(&mut self, rows: usize, cols: usize) {
        if self.row_batches.len() == rows && self.cols == cols {
            return;
        }

        self.dirty = DirtyRegion::new(rows);
        self.row_batches = (0..rows).map(|_| Self::row_batch(cols)).collect();
        self.row_signatures = vec![None; rows];
        self.overlay_signature = None;
        self.cols = cols;
    }

    fn invalidate(&mut self) {
        self.overlay_signature = None;
        for signature in &mut self.row_signatures {
            *signature = None;
        }
        self.dirty.mark_fully_damaged();
    }

    fn row_batch(cols: usize) -> QuadBatch {
        QuadBatch::with_capacity(
            cols.saturating_mul(8).max(64),
            cols.saturating_mul(12).max(96),
        )
    }
}

/// Runtime state for a pane.
#[derive(Debug, Clone, Default)]
struct HistoryNavigationState {
    base_query: String,
    candidates: Vec<String>,
    current: Option<usize>,
}

struct PaneRuntime {
    app: WalkApp,
    terminal: Terminal,
    viewport: ViewportRenderer,
    ui_rects: UiRects,
    cols: u16,
    rows: u16,
    row_cache: PaneRowCache,
    current_cwd: PathBuf,
    prompt_ready: bool,
    pane_history: Vec<HistoryEntry>,
    pending_history: Option<HistoryEntry>,
    history_nav: HistoryNavigationState,
}

/// Walk application handler.
struct WalkHandler {
    config: WalkConfig,
    trigger_engine: TriggerEngine,
    pattern_registry: PatternRegistry,
    workflow_store: WorkflowStore,
    workspace: WorkspaceState,
    panes: HashMap<PaneId, PaneRuntime>,
    pending_pane_restore: HashMap<PaneId, PaneState>,
    global_history: CommandHistory,
    plugins: Option<PluginHost>,
    status_message: Option<String>,
    hovered_link: Option<String>,
    theme_watcher: Option<ThemeWatcher>,
    background: BackgroundRenderer,
    font: FontSystem,
    render: Option<RenderState>,
    window: Option<Arc<Window>>,
    chrome_rects: ChromeRects,
    needs_redraw: bool,
    started_at: Instant,
    last_cursor_visible: bool,
    pending_close_confirmation: Option<Instant>,
    redraw_history_ms: VecDeque<f32>,
    theme_overrides: HashMap<String, String>,
}

impl WalkHandler {
    fn new(config: WalkConfig) -> Self {
        let font = FontSystem::new(&config.font_family, config.font_size);
        let (workspace, _) = WorkspaceState::new("Walk");
        let plugins = PluginHost::new(&WalkConfig::config_dir());
        let trigger_engine = trigger_engine_from_config(&config);
        let pattern_registry = PatternRegistry::new();
        let mut workflow_store = WorkflowStore::new();
        workflow_store.load_from_dir(&WalkConfig::config_dir().join("workflows"));
        let background = {
            let mut background = BackgroundRenderer::new();
            if let Some(path) = resolve_background_image_path(&config) {
                if let Err(error) = background.load_image(&path) {
                    warn!("failed to load background image: {error}");
                }
            }
            background
        };
        let theme_watcher = config
            .theme_path
            .as_ref()
            .and_then(|path| ThemeWatcher::new(path).ok());
        let global_history = CommandHistory::load(&CommandHistory::default_path(), 10_000);

        let handler = Self {
            config,
            trigger_engine,
            pattern_registry,
            workflow_store,
            workspace,
            panes: HashMap::new(),
            pending_pane_restore: HashMap::new(),
            global_history,
            plugins,
            status_message: None,
            hovered_link: None,
            theme_watcher,
            background,
            font,
            render: None,
            window: None,
            chrome_rects: ChromeRects::default(),
            needs_redraw: true,
            started_at: Instant::now(),
            last_cursor_visible: true,
            pending_close_confirmation: None,
            redraw_history_ms: VecDeque::with_capacity(60),
            theme_overrides: HashMap::new(),
        };
        handler.refresh_plugin_config();
        handler.refresh_plugin_snapshot();
        handler
    }

    fn active_pane_id(&self) -> Option<PaneId> {
        self.workspace.active_pane_id()
    }

    fn active_pane(&self) -> Option<&PaneRuntime> {
        self.active_pane_id()
            .and_then(|pane_id| self.panes.get(&pane_id))
    }

    fn active_pane_mut(&mut self) -> Option<&mut PaneRuntime> {
        let pane_id = self.active_pane_id()?;
        self.panes.get_mut(&pane_id)
    }

    fn should_activate_owned_input(pane: &PaneRuntime) -> bool {
        pane.app.input_mode == InputMode::OwnedInput
            && pane.prompt_ready
            && !pane.terminal.state.is_alt_screen()
            && !pane.app.global_search.is_active
            && pane.app.block_query.is_none()
            && pane.app.command_search.is_none()
    }

    fn sync_owned_input_state_for_pane(&mut self, pane_id: PaneId) {
        if let Some(pane) = self.panes.get_mut(&pane_id) {
            pane.app.input_editor.is_active = Self::should_activate_owned_input(pane);
            if !pane.app.input_editor.is_active {
                pane.history_nav = HistoryNavigationState::default();
            }
        }
    }

    fn show_input_surface(pane: &PaneRuntime, focused: bool) -> bool {
        focused
            && (pane.app.input_mode == InputMode::CommandPalette
                || pane.app.command_search.is_some()
                || pane.app.input_editor.is_active)
    }

    fn pane_input_lines(pane: &PaneRuntime) -> usize {
        if pane.app.input_mode == InputMode::CommandPalette {
            pane.app.input_editor.buffer.line_count().max(1) + 6
        } else if pane.app.command_search.is_some() {
            9
        } else {
            pane.app.input_editor.buffer.line_count().max(1)
        }
    }

    fn spawn_pane(&mut self, pane_id: PaneId, rect: Rect, _focused: bool) {
        let restore = self.pending_pane_restore.remove(&pane_id);
        let mut pane_config = self.config.clone();
        if let Some(shell) = restore
            .as_ref()
            .map(|pane_state| parse_shell_type(&pane_state.shell))
        {
            pane_config.shell = shell;
        }
        let mut app = WalkApp::new(pane_config.clone());
        self.apply_plugin_keybindings(&mut app);
        if let Some(pane_state) = &restore {
            app.input_editor.buffer.set_text(&pane_state.input_draft);
            if !pane_state.search_query.is_empty() {
                app.global_search.activate();
                app.global_search.search_input = pane_state.search_query.clone();
            }
        }
        let ui_rects = compute_pane_ui_rects(
            rect,
            app.input_editor.render_data().position,
            1,
            self.font.metrics.cell_height,
            false,
        );
        let (cols, rows) = self
            .font
            .grid_dimensions(ui_rects.viewport.w, ui_rects.viewport.h);
        let env = HashMap::new();
        let initial_cwd = restore.as_ref().and_then(|pane_state| {
            (!pane_state.cwd.as_os_str().is_empty()).then_some(pane_state.cwd.as_path())
        });

        match Terminal::new(
            &pane_config.shell,
            cols,
            rows,
            pane_config.scrollback_lines,
            env,
            initial_cwd,
        ) {
            Ok(mut terminal) => {
                if let Some(pane_state) = &restore {
                    terminal.restore_scrollback(&pane_state.buffer_lines);
                    terminal.restore_display_offset(pane_state.display_offset);
                }
                let pane_runtime = PaneRuntime {
                    app,
                    terminal,
                    viewport: ViewportRenderer::new(),
                    ui_rects,
                    cols,
                    rows,
                    row_cache: PaneRowCache::new(rows as usize, cols as usize),
                    current_cwd: restore
                        .as_ref()
                        .map_or_else(PathBuf::new, |pane_state| pane_state.cwd.clone()),
                    prompt_ready: false,
                    pane_history: restore
                        .as_ref()
                        .map(|pane_state| {
                            pane_state
                                .command_history
                                .iter()
                                .map(history_entry_from_state)
                                .collect()
                        })
                        .unwrap_or_default(),
                    pending_history: None,
                    history_nav: HistoryNavigationState::default(),
                };
                self.panes.insert(pane_id, pane_runtime);
                self.sync_owned_input_state_for_pane(pane_id);
                if let Some(pane_state) = restore {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.terminal.title = pane_state.title;
                        pane.viewport
                            .set_display_offset(pane_state.display_offset, pane_max_scroll(pane));
                        pane.viewport
                            .set_follow_output(pane_state.follow_output, pane_max_scroll(pane));
                        let blocks = pane_state
                            .blocks
                            .iter()
                            .map(block_from_state)
                            .collect::<Vec<_>>();
                        pane.app
                            .block_manager
                            .restore_blocks(blocks, pane_state.selected_block);
                        pane.app.block_navigator.selected_block_index =
                            pane_state.selected_block.and_then(|selected_id| {
                                pane.app
                                    .block_manager
                                    .blocks
                                    .iter()
                                    .position(|block| block.id == selected_id)
                            });
                    }
                }
            }
            Err(error) => warn!("failed to spawn pane terminal: {error}"),
        }
    }

    fn sync_workspace_layout(&mut self, size: PhysicalSize<u32>) {
        self.chrome_rects = compute_chrome_rects(
            size,
            self.config.tab_bar_visible,
            self.config.status_bar_visible,
        );
        let active_pane_id = self.active_pane_id();
        let pane_rects = self.workspace.active_pane_rects(self.chrome_rects.content);

        for (pane_id, rect) in pane_rects {
            let focused = active_pane_id == Some(pane_id);
            if !self.panes.contains_key(&pane_id) {
                self.spawn_pane(pane_id, rect, focused);
                continue;
            }

            let Some(pane) = self.panes.get_mut(&pane_id) else {
                continue;
            };
            let ui_rects = compute_pane_ui_rects(
                rect,
                pane.app.input_editor.render_data().position,
                Self::pane_input_lines(pane),
                self.font.metrics.cell_height,
                Self::show_input_surface(pane, focused),
            );
            let (cols, rows) = self
                .font
                .grid_dimensions(ui_rects.viewport.w, ui_rects.viewport.h);
            if pane.ui_rects != ui_rects {
                pane.row_cache.invalidate();
                pane.ui_rects = ui_rects;
            }
            if pane.cols != cols || pane.rows != rows {
                if let Err(error) = pane.terminal.resize(cols, rows) {
                    warn!("failed to resize pane terminal: {error}");
                }
                pane.cols = cols;
                pane.rows = rows;
                pane.row_cache.resize(rows as usize, cols as usize);
            }
        }
    }

    fn snapshot_session(&self) -> WorkspaceSessionState {
        let window_size = self
            .window
            .as_ref()
            .map(|window| {
                let size = window.inner_size();
                (size.width, size.height)
            })
            .unwrap_or((1280, 800));
        let window_position = self
            .window
            .as_ref()
            .and_then(|window| window.outer_position().ok())
            .map(|position| (position.x, position.y))
            .unwrap_or((0, 0));

        let panes = self
            .panes
            .iter()
            .map(|(pane_id, pane)| PaneState {
                id: *pane_id,
                cwd: pane.current_cwd.clone(),
                shell: pane.app.config.shell.to_string(),
                title: pane.terminal.title.clone(),
                input_draft: pane.app.input_editor.buffer.text(),
                search_query: pane.app.global_search.search_input.clone(),
                command_history: pane
                    .pane_history
                    .iter()
                    .map(history_entry_to_state)
                    .collect(),
                buffer_lines: pane
                    .terminal
                    .state
                    .text_rows()
                    .into_iter()
                    .map(|row| row.text)
                    .collect(),
                display_offset: pane.terminal.state.display_offset(),
                follow_output: pane.viewport.follow_output(),
                blocks: pane
                    .app
                    .block_manager
                    .blocks
                    .iter()
                    .map(block_to_state)
                    .collect(),
                selected_block: pane
                    .app
                    .block_navigator
                    .selected_block(&pane.app.block_manager)
                    .map(|block| block.id),
            })
            .collect();

        let tabs = self
            .workspace
            .tabs
            .iter()
            .map(|tab| WorkspaceTabState {
                id: tab.id,
                title: tab.title.clone(),
                focused_pane: tab.split_manager.focused_leaf,
                split_tree: split_node_to_state(&tab.split_manager.root),
            })
            .collect();

        WorkspaceSessionState {
            tabs,
            panes,
            active_tab: self.workspace.active_tab,
            window_size,
            window_position,
        }
    }

    fn restore_session(&mut self, session: WorkspaceSessionState) {
        let WorkspaceSessionState {
            tabs,
            panes,
            active_tab,
            window_size,
            window_position,
        } = session;

        self.pending_pane_restore = panes
            .into_iter()
            .map(|pane_state| (pane_state.id, pane_state))
            .collect();
        let tabs = tabs
            .into_iter()
            .map(|tab| WorkspaceTab {
                id: tab.id,
                title: tab.title,
                split_manager: SplitManager {
                    root: split_node_from_state(&tab.split_tree),
                    focused_leaf: tab.focused_pane,
                },
            })
            .collect();
        self.workspace = WorkspaceState::from_tabs(tabs, active_tab);
        self.panes.clear();
        if let Some(window) = &self.window {
            window.set_outer_position(PhysicalPosition::new(window_position.0, window_position.1));
            let _ = window.request_inner_size(PhysicalSize::new(window_size.0, window_size.1));
            self.sync_workspace_layout(window.inner_size());
        }
        if self.active_search_state().is_some() {
            self.refresh_global_search();
        }
    }

    fn build_quads(&mut self) {
        let active_pane_id = self.active_pane_id();
        let tab_labels: Vec<(bool, String)> = self
            .workspace
            .tabs
            .iter()
            .enumerate()
            .map(|(index, tab)| {
                let label = if index == self.workspace.active_tab {
                    active_pane_id
                        .and_then(|pane_id| self.panes.get(&pane_id))
                        .map(|pane| format!("{}  [{}x{}]", tab.title, pane.cols, pane.rows))
                        .unwrap_or_else(|| tab.title.clone())
                } else {
                    tab.title.clone()
                };
                (index == self.workspace.active_tab, label)
            })
            .collect();
        let status_text = self.active_pane().map(|active_pane| {
            let cwd = active_pane
                .app
                .block_manager
                .blocks
                .last()
                .map(|block| block.cwd.display().to_string())
                .filter(|cwd| !cwd.is_empty())
                .unwrap_or_else(|| "~".to_string());
            let vi_mode = active_pane.app.vi_mode.as_ref().map(ViModeState::mode_label);
            let broadcast = self
                .workspace
                .broadcast_input
                .then_some("BROADCAST");
            let ephemeral = self.hovered_link.as_ref().or(self.status_message.as_ref());
            match (broadcast, vi_mode, ephemeral) {
                (Some(broadcast), Some(mode), Some(message)) => format!(
                    "{cwd}  |  {}  |  {broadcast}  |  {mode}  |  {message}",
                    active_pane.app.config.shell
                ),
                (Some(broadcast), Some(mode), None) => {
                    format!(
                        "{cwd}  |  {}  |  {broadcast}  |  {mode}",
                        active_pane.app.config.shell
                    )
                }
                (Some(broadcast), None, Some(message)) => format!(
                    "{cwd}  |  {}  |  {broadcast}  |  {message}",
                    active_pane.app.config.shell
                ),
                (Some(broadcast), None, None) => {
                    format!("{cwd}  |  {}  |  {broadcast}", active_pane.app.config.shell)
                }
                (None, Some(mode), Some(message)) => {
                    format!("{cwd}  |  {}  |  {mode}  |  {message}", active_pane.app.config.shell)
                }
                (None, Some(mode), None) => {
                    format!("{cwd}  |  {}  |  {mode}", active_pane.app.config.shell)
                }
                (None, None, Some(message)) => {
                    format!("{cwd}  |  {}  |  {message}", active_pane.app.config.shell)
                }
                (None, None, None) => format!("{cwd}  |  {}", active_pane.app.config.shell),
            }
        });
        let workspace_search = self.active_search_state();
        let cursor_shape = self.cursor_shape();
        let cursor_visible = self.cursor_visible();
        let window_opacity = self.config.window_opacity.clamp(0.0, 1.0);
        let background_image = self.background.image.clone();
        let background_loaded = background_image.is_some();
        let debug_overlay_lines = if self.config.debug_overlay {
            Some(self.debug_overlay_lines())
        } else {
            None
        };
        let full_height =
            self.chrome_rects.content.y + self.chrome_rects.content.h + self.chrome_rects.status.h;
        let full_rect = Rect::new(0.0, 0.0, self.chrome_rects.content.w, full_height);
        let Some(render) = self.render.as_mut() else {
            return;
        };

        render.batch.clear();
        if background_image.is_some() {
            push_background_image(&mut render.batch, full_rect, window_opacity);
        }
        if self.config.tab_bar_visible {
            render_tab_bar(
                render,
                &mut self.font,
                self.chrome_rects.tab_bar,
                &tab_labels,
                window_opacity,
            );
        }
        if self.config.status_bar_visible {
            render_status_bar(
                render,
                &mut self.font,
                self.chrome_rects.status,
                status_text.as_deref(),
                window_opacity,
            );
        }
        if let Some(lines) = debug_overlay_lines.as_ref() {
            render_debug_overlay(
                render,
                &mut self.font,
                self.chrome_rects.content,
                lines,
                window_opacity,
            );
        }

        let pane_ids = self.workspace.active_pane_ids();
        for pane_id in pane_ids {
            let focused = active_pane_id == Some(pane_id);
            let Some(pane) = self.panes.get_mut(&pane_id) else {
                continue;
            };

            let theme = &pane.app.theme;
            let viewport = pane.ui_rects.viewport;
            let visible_rows = pane.terminal.state.visible_rows();
            let total_cols = pane.terminal.state.columns();
            let (cursor_col, _) = pane.terminal.state.cursor_position();
            let cursor_row = pane.terminal.state.absolute_cursor_row();
            let row_positions =
                build_visible_row_positions(&visible_rows, &pane.app.block_manager.blocks);
            let selected_block_id = pane
                .app
                .block_navigator
                .selected_block(&pane.app.block_manager)
                .map(|block| block.id);
            let cw = self.font.metrics.cell_width;
            let ch = self.font.metrics.cell_height;
            let terminal_surface_alpha = if background_loaded {
                (window_opacity * theme.opacity * 0.72).clamp(0.18, 1.0)
            } else {
                (window_opacity * theme.opacity).clamp(0.0, 1.0)
            };

            render.batch.push_bg_quad(
                viewport.x,
                viewport.y,
                viewport.w,
                viewport.h,
                with_opacity(
                    [
                        theme.background.r,
                        theme.background.g,
                        theme.background.b,
                        theme.background.a,
                    ],
                    terminal_surface_alpha,
                ),
            );

            let search = workspace_search.as_ref().unwrap_or(&pane.app.global_search);
            let block_query = pane.app.block_query.as_ref();
            let overlay_signature = pane_overlay_signature(
                &pane.app.block_manager.blocks,
                selected_block_id,
                search,
                block_query,
                pane_id,
            );
            pane.row_cache.resize(visible_rows.len(), total_cols);
            if pane.row_cache.overlay_signature.as_ref() != Some(&overlay_signature) {
                pane.row_cache.overlay_signature = Some(overlay_signature);
                pane.row_cache.dirty.mark_fully_damaged();
            }

            if pane.terminal.is_dirty() || pane.viewport.needs_render() {
                for (row_idx, absolute_row) in visible_rows.iter().copied().enumerate() {
                    let signature = PaneRowSignature {
                        absolute_row,
                        render_row: row_positions.get(row_idx).copied().flatten(),
                        cells: collect_row_cells(&pane.terminal, absolute_row, total_cols),
                    };
                    if pane.row_cache.row_signatures[row_idx].as_ref() != Some(&signature) {
                        pane.row_cache.row_signatures[row_idx] = Some(signature);
                        pane.row_cache.dirty.mark_row_dirty(row_idx);
                    }
                }
            }

            if pane.row_cache.dirty.has_damage() {
                let blocks = &pane.app.block_manager.blocks;
                let terminal = &pane.terminal;
                let row_cache = &mut pane.row_cache;
                for (row_idx, absolute_row) in visible_rows.iter().copied().enumerate() {
                    if !row_cache.dirty.is_row_dirty(row_idx) {
                        continue;
                    }
                    rebuild_visible_row_batch(
                        &mut row_cache.row_batches[row_idx],
                        render,
                        &mut self.font,
                        theme,
                        blocks,
                        selected_block_id,
                        search,
                        pane.app.block_query.as_ref(),
                        pane_id,
                        terminal,
                        absolute_row,
                        row_positions.get(row_idx).copied().flatten(),
                        total_cols,
                        viewport,
                        cw,
                        ch,
                        terminal_surface_alpha,
                    );
                }
                row_cache.dirty.clear();
            }

            for row_batch in pane.row_cache.row_batches.iter().take(visible_rows.len()) {
                render.batch.append(row_batch);
            }

            let border_color = if self.workspace.broadcast_input {
                [
                    theme.block_error_accent.r,
                    theme.block_error_accent.g,
                    theme.block_error_accent.b,
                    0.95,
                ]
            } else {
                [
                    theme.block_separator.r,
                    theme.block_separator.g,
                    theme.block_separator.b,
                    0.9,
                ]
            };
            render.batch.push_bg_quad(
                viewport.x,
                viewport.y,
                viewport.w,
                1.0,
                border_color,
            );
            render.batch.push_bg_quad(
                viewport.x,
                viewport.y,
                1.0,
                viewport.h,
                border_color,
            );
            if focused {
                render.batch.push_bg_quad(
                    viewport.x,
                    viewport.y,
                    viewport.w,
                    2.0,
                    [
                        theme.highlight_current_match.r,
                        theme.highlight_current_match.g,
                        theme.highlight_current_match.b,
                        0.8,
                    ],
                );
            }

            if focused && !pane.app.input_editor.is_active && pane.app.command_search.is_none() {
                let viewport_row_for_abs = |absolute_row: usize| {
                    visible_rows
                        .iter()
                        .position(|row| *row == absolute_row)
                        .and_then(|idx| row_positions.get(idx))
                        .and_then(|row| *row)
                };

                if let Some(vi_mode) = pane.app.vi_mode.as_ref() {
                    if let Some((start, end)) = vi_mode.visual_range() {
                        let row_start = start.0.min(end.0);
                        let row_end = start.0.max(end.0);
                        let col_start = start.1.min(end.1);
                        let col_end = start.1.max(end.1).saturating_add(1);
                        for absolute_row in row_start..=row_end {
                            let Some(render_row) = viewport_row_for_abs(absolute_row) else {
                                continue;
                            };
                            let (range_start, range_end) = match vi_mode.mode {
                                ViSubMode::VisualLine => (0usize, total_cols),
                                ViSubMode::VisualBlock => {
                                    (col_start.min(total_cols), col_end.min(total_cols))
                                }
                                _ => {
                                    if absolute_row == row_start && absolute_row == row_end {
                                        (col_start.min(total_cols), col_end.min(total_cols))
                                    } else if absolute_row == row_start {
                                        (col_start.min(total_cols), total_cols)
                                    } else if absolute_row == row_end {
                                        (0, col_end.min(total_cols))
                                    } else {
                                        (0, total_cols)
                                    }
                                }
                            };
                            if range_end > range_start {
                                render.batch.push_bg_quad(
                                    viewport.x + range_start as f32 * cw,
                                    viewport.y + render_row as f32 * ch,
                                    (range_end - range_start) as f32 * cw,
                                    ch,
                                    [
                                        theme.selection.r,
                                        theme.selection.g,
                                        theme.selection.b,
                                        0.25 * window_opacity,
                                    ],
                                );
                            }
                        }
                    }

                    if cursor_visible {
                        let vi_col = vi_mode.cursor_col.min(total_cols.saturating_sub(1));
                        if let Some(render_row) = viewport_row_for_abs(vi_mode.cursor_row) {
                            render.batch.push_cursor(
                                viewport.x + vi_col as f32 * cw,
                                viewport.y + render_row as f32 * ch,
                                cw,
                                ch,
                                CursorShape::Block,
                                [
                                    theme.vi_cursor_color.r,
                                    theme.vi_cursor_color.g,
                                    theme.vi_cursor_color.b,
                                    0.9 * window_opacity,
                                ],
                            );
                        }
                    }
                } else {
                    let cursor_x = viewport.x + cursor_col as f32 * cw;
                    let cursor_row = visible_rows
                        .iter()
                        .position(|row| *row == cursor_row)
                        .and_then(|idx| row_positions.get(idx))
                        .and_then(|row| *row)
                        .unwrap_or_else(|| visible_rows.len().saturating_sub(1));
                    let cursor_y = viewport.y + cursor_row as f32 * ch;
                    if cursor_visible {
                        render.batch.push_cursor(
                            cursor_x,
                            cursor_y,
                            cw,
                            ch,
                            cursor_shape,
                            [
                                theme.cursor.r,
                                theme.cursor.g,
                                theme.cursor.b,
                                0.7 * window_opacity,
                            ],
                        );
                    }
                }
            }

            if focused
                && pane.app.input_mode == InputMode::OwnedInput
                && pane.app.input_editor.is_active
            {
                render_owned_input(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.input,
                    &pane.app.input_editor.render_data(),
                    cursor_shape,
                    cursor_visible,
                    window_opacity,
                );
            }

            if focused && pane.app.input_mode == InputMode::CommandPalette {
                render_command_palette(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.viewport,
                    &pane.app.input_editor.render_data(),
                    &pane.app.command_palette,
                    cursor_shape,
                    cursor_visible,
                    window_opacity,
                );
            }

            if focused {
                if let Some(command_search) = pane.app.command_search.as_ref() {
                    render_command_search(
                        render,
                        &mut self.font,
                        theme,
                        pane.ui_rects.input,
                        command_search,
                        cursor_shape,
                        cursor_visible,
                        window_opacity,
                    );
                }
            }

            if focused && search.is_active {
                render_search_overlay(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.viewport,
                    search,
                    window_opacity,
                );
            }

            if focused {
                if let Some(mut block_query_state) = pane.app.block_query.clone() {
                    let Some(target_block) = pane
                        .app
                        .block_manager
                        .get_block(block_query_state.target_block_id)
                        .cloned()
                    else {
                        pane.app.block_query = None;
                        continue;
                    };
                    let filtered_lines = if matches!(block_query_state.mode, BlockQueryMode::Filter)
                    {
                        let max_visible_lines = filter_overlay_visible_lines(
                            pane.ui_rects.viewport,
                            self.font.metrics.cell_height,
                        );
                        block_query_state.ensure_current_line_visible(max_visible_lines);
                        block_query_state
                            .filtered_line_indices()
                            .into_iter()
                            .filter_map(|line_idx| {
                                let absolute_row = target_block.output_start_row + line_idx;
                                (absolute_row <= target_block.output_end_row)
                                    .then(|| (line_idx, pane.terminal.state.row_text(absolute_row)))
                            })
                            .collect::<Vec<_>>()
                    } else {
                        Vec::new()
                    };
                    pane.app.block_query = Some(block_query_state.clone());
                    render_block_query_overlay(
                        render,
                        &mut self.font,
                        theme,
                        pane.ui_rects.viewport,
                        &block_query_state,
                        &filtered_lines,
                        window_opacity,
                    );
                }
            }

            if focused && pane.app.quick_select.active {
                render_quick_select_overlay(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.viewport,
                    pane.terminal.state.visible_start_row(),
                    pane.terminal.state.screen_lines(),
                    &pane.app.quick_select.matches,
                    pane.app.quick_select.typed_label.as_str(),
                    window_opacity,
                );
            }
        }
    }

    fn apply_plugin_keybindings(&self, app: &mut WalkApp) {
        let Some(plugins) = &self.plugins else {
            return;
        };
        plugins.apply_keybindings(app, parse_lua_action);
    }

    fn workspace_hook_payload(&self) -> serde_json::Value {
        json!({
            "active_tab_index": self.workspace.active_tab,
            "active_tab_id": self.workspace.active_tab().map(|tab| tab.id),
            "tab_count": self.workspace.tabs.len(),
            "pane_count": self.workspace.pane_count(),
            "active_pane_id": self.active_pane_id(),
        })
    }

    fn pane_hook_payload(&self, pane_id: PaneId) -> serde_json::Value {
        let tab_index = self.workspace.find_tab_index_for_pane(pane_id);
        let tab = tab_index.and_then(|index| self.workspace.tabs.get(index));
        let pane = self.panes.get(&pane_id);
        let cwd = pane
            .map(|pane| pane.current_cwd.display().to_string())
            .unwrap_or_default();

        json!({
            "pane_id": pane_id,
            "tab_index": tab_index,
            "tab_id": tab.map(|tab| tab.id),
            "tab_title": tab.map(|tab| tab.title.clone()),
            "shell": pane.map(|pane| pane.app.config.shell.to_string()),
            "title": pane.map(|pane| pane.terminal.title.clone()),
            "cwd": cwd,
            "is_active_pane": self.active_pane_id() == Some(pane_id),
        })
    }

    fn block_hook_payload(&self, pane_id: PaneId, exit_code: Option<i32>) -> serde_json::Value {
        let mut payload = self.pane_hook_payload(pane_id);
        if let Some(object) = payload.as_object_mut() {
            if let Some(block) = self
                .panes
                .get(&pane_id)
                .and_then(|pane| pane.app.block_manager.blocks.last())
            {
                object.insert("block_id".to_string(), json!(block.id));
                object.insert("command".to_string(), json!(block.command_text));
                object.insert(
                    "exit_code".to_string(),
                    json!(block.exit_code.or(exit_code)),
                );
                object.insert(
                    "duration_ms".to_string(),
                    json!(block.duration.map(|duration| duration.as_millis() as u64)),
                );
                object.insert(
                    "output_start_row".to_string(),
                    json!(block.output_start_row),
                );
                object.insert("output_end_row".to_string(), json!(block.output_end_row));
            } else {
                object.insert("exit_code".to_string(), json!(exit_code));
            }
        }
        payload
    }

    fn active_search_state(&self) -> Option<walk_ui::search::GlobalSearch> {
        self.active_pane().and_then(|pane| {
            pane.app
                .global_search
                .is_active
                .then(|| pane.app.global_search.clone())
        })
    }

    fn install_search_state_on_active_pane(&mut self, search: walk_ui::search::GlobalSearch) {
        for pane in self.panes.values_mut() {
            if pane.app.global_search.is_active {
                pane.app.global_search.deactivate();
            }
        }
        if let Some(active_pane) = self.active_pane_mut() {
            active_pane.app.global_search = search;
        }
    }

    fn active_block_query_state(&self) -> Option<BlockQueryState> {
        self.active_pane()
            .and_then(|pane| pane.app.block_query.as_ref().cloned())
    }

    fn refresh_block_query(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            return;
        };
        self.refresh_block_query_for_pane(pane_id);
    }

    fn refresh_block_query_for_pane(&mut self, pane_id: PaneId) {
        let Some((target_block_id, query)) = self.panes.get(&pane_id).and_then(|pane| {
            pane.app
                .block_query
                .as_ref()
                .map(|state| (state.target_block_id, state.query.clone()))
        }) else {
            return;
        };

        let Some(output_lines) = self.panes.get(&pane_id).and_then(|pane| {
            pane.app
                .block_manager
                .get_block(target_block_id)
                .map(|block| collect_block_output_lines(&pane.terminal, block))
        }) else {
            if let Some(pane) = self.panes.get_mut(&pane_id) {
                pane.app.block_query = None;
            }
            return;
        };

        if let Some(pane) = self.panes.get_mut(&pane_id) {
            if let Some(state) = pane.app.block_query.as_mut() {
                if state.target_block_id == target_block_id {
                    state.search(&query, &output_lines);
                }
            }
        }
        self.scroll_to_current_block_query_match();
    }

    fn collect_workspace_search_lines(&self) -> Vec<SearchLine> {
        let mut lines = Vec::new();
        for (pane_id, pane) in &self.panes {
            let tab_index = self.workspace.find_tab_index_for_pane(*pane_id);
            let tab_id = tab_index
                .and_then(|index| self.workspace.tabs.get(index))
                .map(|tab| tab.id)
                .unwrap_or_default();
            lines.extend(collect_search_lines(
                &pane.terminal,
                &pane.app.block_manager.blocks,
                *pane_id,
                tab_id,
            ));
        }
        lines
    }

    fn cursor_shape(&self) -> CursorShape {
        match self.config.cursor_style {
            walk_app::config::CursorStyle::Block => CursorShape::Block,
            walk_app::config::CursorStyle::Bar => CursorShape::Bar,
            walk_app::config::CursorStyle::Underline => CursorShape::Underline,
        }
    }

    fn cursor_visible(&self) -> bool {
        !self.config.cursor_blink || ((self.started_at.elapsed().as_millis() / 600) % 2 == 0)
    }

    fn debug_overlay_lines(&self) -> Vec<String> {
        let active_scrollback = self
            .active_pane()
            .map_or(0, |pane| pane.terminal.state.scrollback_len());
        let total_session_bytes = self.estimated_session_bytes();
        let avg_redraw_ms = if self.redraw_history_ms.is_empty() {
            0.0
        } else {
            self.redraw_history_ms.iter().sum::<f32>() / self.redraw_history_ms.len() as f32
        };
        let (atlas_entries, atlas_usage) = self
            .render
            .as_ref()
            .map(|render| (render.atlas.len(), render.atlas.usage_ratio() * 100.0))
            .unwrap_or((0, 0.0));

        vec![
            format!("redraw {:.2} ms", avg_redraw_ms),
            format!("atlas {} glyphs {:.1}% full", atlas_entries, atlas_usage),
            format!("scrollback {} rows", active_scrollback),
            format!("session ~{} KiB", total_session_bytes / 1024),
        ]
    }

    fn estimated_session_bytes(&self) -> usize {
        self.panes
            .values()
            .map(|pane| {
                let rows = pane
                    .terminal
                    .state
                    .text_rows()
                    .into_iter()
                    .map(|row| row.text.len())
                    .sum::<usize>();
                let blocks = pane
                    .app
                    .block_manager
                    .blocks
                    .iter()
                    .map(|block| {
                        block.command_text.len()
                            + block.prompt_text.len()
                            + block.cwd.as_os_str().len()
                    })
                    .sum::<usize>();
                rows + blocks + pane.app.input_editor.buffer.text().len()
            })
            .sum()
    }

    fn has_running_processes(&self) -> bool {
        self.panes.values().any(|pane| !pane.terminal.exited)
    }

    fn invalidate_all_row_caches(&mut self) {
        for pane in self.panes.values_mut() {
            pane.row_cache.invalidate();
        }
    }

    fn refresh_plugin_snapshot(&self) {
        let Some(plugins) = &self.plugins else {
            return;
        };
        plugins.update_snapshot(self.plugin_snapshot());
    }

    fn refresh_plugin_config(&self) {
        let Some(plugins) = &self.plugins else {
            return;
        };
        plugins.set_config_values(&self.plugin_config_snapshot());
    }

    fn plugin_config_snapshot(&self) -> serde_json::Value {
        json!({
            "shell": self.config.shell.to_string(),
            "font_family": self.config.font_family.clone(),
            "font_size": self.font.font_size,
            "scrollback_lines": self.config.scrollback_lines,
            "input_position": match self.config.input_position {
                walk_app::config::InputPosition::Top => "top",
                walk_app::config::InputPosition::Bottom => "bottom",
            },
            "theme_path": self.config.theme_path.as_ref().map(|path| path.display().to_string()),
            "window_opacity": self.config.window_opacity,
            "restore_session": self.config.restore_session,
            "debug_overlay": self.config.debug_overlay,
            "trigger_count": self.trigger_engine.len(),
            "workflow_count": self.workflow_store.workflows().len(),
        })
    }

    fn plugin_snapshot(&self) -> serde_json::Value {
        let active_pane_id = self.active_pane_id();
        let pane = self.active_pane();
        let pane_cwd = pane
            .and_then(|pane| {
                pane.app
                    .block_manager
                    .blocks
                    .last()
                    .map(|block| block.cwd.display().to_string())
            })
            .unwrap_or_default();
        let (window_size, window_position) = self
            .window
            .as_ref()
            .map(|window| {
                let size = window.inner_size();
                let position = window
                    .outer_position()
                    .map(|position| (position.x, position.y))
                    .unwrap_or((0, 0));
                ((size.width, size.height), position)
            })
            .unwrap_or(((1280, 800), (0, 0)));

        json!({
            "app": {
                "status_message": self.status_message,
                "cursor_visible": self.cursor_visible(),
                "uptime_ms": self.started_at.elapsed().as_millis() as u64,
            },
            "workspace": {
                "active_tab_index": self.workspace.active_tab,
                "active_pane_id": active_pane_id,
                "tab_count": self.workspace.tabs.len(),
                "pane_count": self.workspace.pane_count(),
            },
            "pane": {
                "pane_id": active_pane_id,
                "title": pane.map(|pane| pane.terminal.title.clone()),
                "shell": pane.map(|pane| pane.app.config.shell.to_string()),
                "cwd": pane_cwd,
                "cols": pane.map(|pane| pane.cols),
                "rows": pane.map(|pane| pane.rows),
                "follow_output": pane.map(|pane| pane.viewport.follow_output()),
                "display_offset": pane.map(|pane| pane.viewport.display_offset()),
                "search_query": pane.map(|pane| pane.app.global_search.search_input.clone()),
                "selected_block_id": pane
                    .and_then(|pane| pane.app.block_navigator.selected_block(&pane.app.block_manager))
                    .map(|block| block.id),
            },
            "session": {
                "restore_enabled": self.config.restore_session,
                "autosave_path": default_session_path(),
                "window_size": window_size,
                "window_position": window_position,
            },
            "theme": {
                "name": pane.map(|pane| pane.app.theme.name.clone()),
                "font_family": pane.map(|pane| pane.app.theme.font_family.clone()),
                "font_size": pane.map(|pane| pane.app.theme.font_size),
                "background_image": pane
                    .and_then(|pane| pane.app.theme.background_image.as_ref().map(|path| path.display().to_string())),
            }
        })
    }

    fn run_plugin_hook<T>(&mut self, hook: &str, payload: &T)
    where
        T: Serialize + ?Sized,
    {
        self.refresh_plugin_snapshot();
        let Some(plugins) = &self.plugins else {
            return;
        };
        plugins.trigger_hook(hook, payload);
        self.drain_plugin_side_effects();
    }

    fn drain_plugin_side_effects(&mut self) {
        let Some(plugins) = &self.plugins else {
            return;
        };
        let effects = plugins.drain_effects();
        for notification in effects.notifications {
            info!("lua: {notification}");
            self.status_message = Some(notification);
        }
        for command in effects.exec_requests {
            let payload = format!("{command}\r");
            self.send_to_pty(payload.as_bytes());
        }
        for action_name in effects.action_requests {
            let Some(action) = parse_lua_action(&action_name) else {
                warn!("plugin requested unknown action '{action_name}'");
                continue;
            };
            self.handle_action(action);
        }
        for request in effects.theme_requests {
            self.apply_theme_request(request);
        }
        for request in effects.trigger_requests {
            self.apply_trigger_request(request);
        }
        for request in effects.quick_select_pattern_requests {
            self.apply_quick_select_pattern_request(request);
        }
        for request in effects.workflow_requests {
            self.apply_workflow_request(request);
        }
        self.refresh_plugin_config();
        self.refresh_plugin_snapshot();
    }

    fn apply_trigger_request(&mut self, request: TriggerRequest) {
        match request {
            TriggerRequest::Add {
                name,
                pattern,
                actions,
            } => match trigger_from_descriptor(name.clone(), pattern.clone(), actions) {
                Ok(trigger) => {
                    self.trigger_engine.add_trigger(trigger);
                    self.status_message = Some(format!("registered trigger '{name}'"));
                }
                Err(error) => {
                    warn!("failed to register trigger '{name}': {error}");
                    self.status_message = Some(format!("failed to add trigger '{name}'"));
                }
            },
            TriggerRequest::Remove { name } => {
                if self.trigger_engine.remove_trigger(&name) {
                    self.status_message = Some(format!("removed trigger '{name}'"));
                }
            }
        }
    }

    fn apply_quick_select_pattern_request(&mut self, request: QuickSelectPatternRequest) {
        match request {
            QuickSelectPatternRequest::Add { name, regex } => {
                if let Err(error) = self.pattern_registry.add_pattern(&name, &regex) {
                    warn!("failed to register quick-select pattern '{name}': {error}");
                } else {
                    self.status_message = Some(format!("registered quick-select pattern '{name}'"));
                }
            }
            QuickSelectPatternRequest::Remove { name } => {
                self.pattern_registry.remove_pattern(&name);
                self.status_message = Some(format!("removed quick-select pattern '{name}'"));
            }
        }
    }

    fn apply_workflow_request(&mut self, request: WorkflowRequest) {
        match request {
            WorkflowRequest::Register(workflow) => {
                let name = workflow.name.clone();
                self.workflow_store.add(workflow);
                self.status_message = Some(format!("registered workflow '{name}'"));
            }
        }
    }

    fn apply_theme_request(&mut self, request: ThemeRequest) {
        match request {
            ThemeRequest::Load(name) => {
                let path = resolve_plugin_theme_path(&name);
                match walk_ui::theme_loader::load_theme(&path) {
                    Ok(mut theme) => {
                        if let Err(error) = walk_ui::theme_loader::apply_theme_overrides(
                            &mut theme,
                            &self.theme_overrides,
                        ) {
                            warn!("failed to apply live theme overrides after theme load: {error}");
                        }
                        self.config.theme_path = Some(path.clone());
                        self.theme_watcher = ThemeWatcher::new(&path).ok();
                        self.apply_theme_to_runtime(theme);
                        self.status_message = Some(format!("loaded theme '{}'", name));
                    }
                    Err(error) => warn!("failed to load theme '{}': {error}", name),
                }
            }
            ThemeRequest::Override(overrides) => {
                self.theme_overrides.extend(overrides);
                let mut theme = self
                    .active_pane()
                    .map(|pane| pane.app.theme.clone())
                    .unwrap_or_else(|| {
                        self.config
                            .theme_path
                            .as_ref()
                            .and_then(|path| walk_ui::theme_loader::load_theme(path).ok())
                            .unwrap_or_default()
                    });
                match walk_ui::theme_loader::apply_theme_overrides(
                    &mut theme,
                    &self.theme_overrides,
                ) {
                    Ok(()) => {
                        self.apply_theme_to_runtime(theme);
                        self.status_message = Some("applied live theme overrides".to_string());
                    }
                    Err(error) => warn!("failed to apply live theme overrides: {error}"),
                }
            }
        }
    }

    fn apply_theme_to_runtime(&mut self, theme: Theme) {
        self.config.font_family = theme.font_family.clone();
        self.config.font_size = theme.font_size;
        self.font = FontSystem::new(&theme.font_family, theme.font_size);
        if let Some(render) = self.render.as_mut() {
            render.atlas.clear();
        }
        for pane in self.panes.values_mut() {
            pane.app.theme = theme.clone();
            pane.app.config.font_family = theme.font_family.clone();
            pane.app.config.font_size = theme.font_size;
            pane.app.config.theme_path = self.config.theme_path.clone();
            pane.app.zoom = walk_ui::zoom::ZoomManager::new(theme.font_size);
        }
        self.invalidate_all_row_caches();
        self.sync_background_renderer(Some(&theme));
        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
        self.needs_redraw = true;
    }

    fn sync_background_renderer(&mut self, theme: Option<&Theme>) {
        let background_path = self
            .config
            .background_image
            .clone()
            .or_else(|| theme.and_then(|theme| theme.background_image.clone()));
        if let Some(path) = background_path {
            if let Err(error) = self.background.load_image(&path) {
                warn!("failed to load background image: {error}");
                self.background.clear();
            }
        } else {
            self.background.clear();
        }
        if let Some(render) = self.render.as_mut() {
            render.pipeline.upload_background_image(
                &render.gpu,
                self.background.image.as_ref().map(|image| image.width),
                self.background.image.as_ref().map(|image| image.height),
                self.background
                    .image
                    .as_ref()
                    .map(|image| image.pixels.as_ref()),
            );
        }
    }

    fn send_to_pty(&mut self, data: &[u8]) {
        if let Some(active_pane) = self.active_pane() {
            if let Err(error) = active_pane.terminal.send_input(data) {
                warn!("failed to send to PTY: {error}");
            }
        }
    }

    fn send_raw_input_to_pty(&mut self, data: &[u8]) {
        if !self.workspace.broadcast_input {
            self.send_to_pty(data);
            return;
        }

        for pane_id in self.workspace.all_pane_ids() {
            if let Some(pane) = self.panes.get(&pane_id) {
                if let Err(error) = pane.terminal.send_input(data) {
                    warn!("failed to broadcast PTY input to pane {pane_id}: {error}");
                }
            }
        }
    }

    fn evaluate_triggers_for_latest_block(&mut self, pane_id: PaneId) {
        if self.trigger_engine.is_empty() {
            return;
        }

        let Some((block_id, output_start_row, command_text, output_lines, matches)) =
            self.panes.get(&pane_id).and_then(|pane| {
                let block = pane.app.block_manager.blocks.last()?;
                let output_lines = collect_block_output_lines(&pane.terminal, block);
                let output_text = output_lines.join("\n");
                let mut matches =
                    self.trigger_engine
                        .evaluate(block, &output_text, TriggerScope::Output);
                if !block.command_text.trim().is_empty() {
                    matches.extend(self.trigger_engine.evaluate(
                        block,
                        &block.command_text,
                        TriggerScope::Command,
                    ));
                }

                Some((
                    block.id,
                    block.output_start_row,
                    block.command_text.clone(),
                    output_lines,
                    matches,
                ))
            })
        else {
            return;
        };

        if matches.is_empty() {
            return;
        }

        self.apply_trigger_matches(
            pane_id,
            block_id,
            output_start_row,
            &command_text,
            &output_lines,
            matches,
        );
    }

    #[allow(clippy::too_many_arguments)]
    fn apply_trigger_matches(
        &mut self,
        pane_id: PaneId,
        block_id: u64,
        output_start_row: usize,
        command_text: &str,
        output_lines: &[String],
        matches: Vec<TriggerMatch>,
    ) {
        let mut urls_to_open = Vec::new();
        let mut hook_invocations = Vec::new();
        let mut latest_notification = None;

        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return;
        };
        let Some(block) = pane.app.block_manager.get_block_mut(block_id) else {
            return;
        };

        for trigger_match in matches {
            for action in &trigger_match.actions {
                match action {
                    TriggerAction::Highlight { color } => match trigger_match.scope {
                        TriggerScope::Output => {
                            let highlights = trigger_highlights_for_output_range(
                                output_lines,
                                output_start_row,
                                trigger_match.byte_range,
                                color,
                            );
                            block.trigger_highlights.extend(highlights);
                        }
                        TriggerScope::Command => {
                            if let Some((col_start, col_end)) =
                                char_span_for_single_line(command_text, trigger_match.byte_range)
                            {
                                block.trigger_highlights.push(TriggerHighlight {
                                    absolute_row: output_start_row,
                                    col_start,
                                    col_end,
                                    color: normalize_trigger_color(color),
                                });
                            }
                        }
                        TriggerScope::Both => {}
                    },
                    TriggerAction::Notify { message } => {
                        let notification = if message.trim().is_empty() {
                            format!(
                                "trigger '{}' matched '{}'",
                                trigger_match.trigger_name, trigger_match.matched_text
                            )
                        } else {
                            format!("{message}: {}", trigger_match.matched_text)
                        };
                        latest_notification = Some(notification);
                    }
                    TriggerAction::BookmarkBlock => {
                        block.is_bookmarked = true;
                    }
                    TriggerAction::OpenUrl => {
                        urls_to_open.push(trigger_match.matched_text.clone());
                    }
                    TriggerAction::CopyMatch => {
                        if let Err(error) = pane.app.clipboard.copy(&trigger_match.matched_text) {
                            warn!("failed to copy trigger match to clipboard: {error}");
                        }
                    }
                    TriggerAction::LuaHook { hook_name } => {
                        hook_invocations.push((
                            hook_name.clone(),
                            json!({
                                "pane_id": pane_id,
                                "block_id": block_id,
                                "trigger_name": trigger_match.trigger_name,
                                "scope": match trigger_match.scope {
                                    TriggerScope::Output => "output",
                                    TriggerScope::Command => "command",
                                    TriggerScope::Both => "both",
                                },
                                "matched_text": trigger_match.matched_text,
                                "byte_range": [trigger_match.byte_range.0, trigger_match.byte_range.1],
                            }),
                        ));
                    }
                }
            }
        }

        if let Some(notification) = latest_notification {
            self.status_message = Some(notification);
        }
        for url in urls_to_open {
            walk_ui::links::open_url(&url);
        }
        for (hook, payload) in hook_invocations {
            self.run_plugin_hook(&hook, &payload);
        }
    }

    fn handle_semantic_events(&mut self, pane_id: PaneId, events: Vec<SemanticEvent>) {
        let mut relayout = false;

        for event in events {
            if let SemanticEvent::TitleChanged(title) = &event {
                if self.active_pane_id() == Some(pane_id) {
                    if let Some(window) = &self.window {
                        window.set_title(title);
                    }
                    if let Some(active_tab) = self.workspace.active_tab_mut() {
                        active_tab.title = title.clone();
                    }
                }
            }
            if let Some(pane) = self.panes.get_mut(&pane_id) {
                pane.app.handle_semantic_event(&event);
            }
            match event {
                SemanticEvent::PromptStart { .. } => {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.prompt_ready = true;
                    }
                    relayout = true;
                }
                SemanticEvent::CommandStart { .. } | SemanticEvent::OutputStart { .. } => {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.prompt_ready = false;
                    }
                    relayout = true;
                }
                SemanticEvent::CommandText { text, .. } => {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        if let Some(pending) = pane.pending_history.as_mut() {
                            pending.command = text.trim().to_string();
                        } else if !text.trim().is_empty() {
                            pane.pending_history = Some(HistoryEntry::pending(
                                &text,
                                (!pane.current_cwd.as_os_str().is_empty())
                                    .then(|| pane.current_cwd.clone()),
                                Some(pane_id),
                            ));
                        }
                    }
                }
                SemanticEvent::CommandEnd { exit_code, .. } => {
                    let completed_entry = if let Some(pane) = self.panes.get_mut(&pane_id) {
                        let mut entry = pane.pending_history.take().unwrap_or_else(|| {
                            let command = pane
                                .app
                                .block_manager
                                .blocks
                                .last()
                                .map(|block| block.command_text.clone())
                                .unwrap_or_default();
                            HistoryEntry::pending(
                                &command,
                                (!pane.current_cwd.as_os_str().is_empty())
                                    .then(|| pane.current_cwd.clone()),
                                Some(pane_id),
                            )
                        });

                        let block = pane.app.block_manager.blocks.last();
                        let cwd = block
                            .and_then(|candidate| {
                                (!candidate.cwd.as_os_str().is_empty())
                                    .then(|| candidate.cwd.clone())
                            })
                            .or_else(|| {
                                (!pane.current_cwd.as_os_str().is_empty())
                                    .then(|| pane.current_cwd.clone())
                            });
                        let duration = block.and_then(|candidate| candidate.duration);

                        entry.mark_completed(exit_code, duration, cwd);
                        if !entry.command.is_empty() {
                            pane.pane_history.push(entry.clone());
                            Some(entry)
                        } else {
                            None
                        }
                    } else {
                        None
                    };

                    if let Some(entry) = completed_entry {
                        self.global_history.record_completed(entry);
                    }
                    self.evaluate_triggers_for_latest_block(pane_id);
                    let payload = self.block_hook_payload(pane_id, exit_code);
                    self.run_plugin_hook("block_finished", &payload);
                    relayout = true;
                }
                SemanticEvent::CwdChanged(path) => {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.current_cwd = path.clone();
                    }
                    let mut payload = self.pane_hook_payload(pane_id);
                    if let Some(object) = payload.as_object_mut() {
                        object.insert("path".to_string(), json!(path.display().to_string()));
                    }
                    self.run_plugin_hook("cwd_changed", &payload);
                }
                _ => {}
            }

            self.sync_owned_input_state_for_pane(pane_id);
        }

        if relayout {
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
        }
    }

    fn handle_action(&mut self, action: Action) {
        if matches!(action, Action::EnterViMode) {
            self.enter_vi_mode();
            self.needs_redraw = true;
            return;
        }

        if self.active_pane().is_some_and(|pane| {
            pane.terminal.state.is_alt_screen()
                && matches!(
                    action,
                    Action::BlockPrev
                        | Action::BlockNext
                        | Action::BlockCopy
                        | Action::BlockCopyCommand
                        | Action::BlockCopyOutput
                        | Action::BlockCollapse
                        | Action::BlockToggleBookmark
                        | Action::BlockPrevBookmark
                        | Action::BlockNextBookmark
                        | Action::BlockFind
                        | Action::BlockFilter
                        | Action::BlockRerun
                        | Action::SearchGlobal
                        | Action::CommandPalette
                        | Action::CommandSearch
                )
        }) {
            return;
        }

        let effects = self
            .active_pane_mut()
            .map_or_else(ActionEffects::new, |pane| pane.app.handle_action(&action));
        self.apply_action_effects(effects);
        self.needs_redraw = true;
    }

    fn apply_action_effects(&mut self, effects: ActionEffects) {
        for effect in effects.effects {
            match effect {
                RuntimeEffect::PtyWrite(data) => self.send_to_pty(&data),
                RuntimeEffect::Clipboard(clipboard) => self.apply_clipboard_effect(clipboard),
                RuntimeEffect::Viewport(viewport) => self.apply_viewport_effect(viewport),
                RuntimeEffect::Workspace(workspace) => self.apply_workspace_effect(workspace),
                RuntimeEffect::Overlay(overlay) => self.apply_overlay_effect(overlay),
                RuntimeEffect::Zoom(size) => self.apply_zoom(size),
                RuntimeEffect::Status(message) => self.status_message = Some(message),
            }
        }
    }

    fn apply_clipboard_effect(&mut self, effect: ClipboardEffect) {
        match effect {
            ClipboardEffect::CopySelection => {
                if let Some(text) = self.selection_text() {
                    if let Some(active_pane) = self.active_pane_mut() {
                        let _ = active_pane.app.clipboard.copy(&text);
                    }
                }
            }
            ClipboardEffect::CopySelectedBlock => {
                if let Some(text) = self.selected_block_text() {
                    if let Some(active_pane) = self.active_pane_mut() {
                        let _ = active_pane.app.clipboard.copy(&text);
                    }
                }
            }
            ClipboardEffect::CopySelectedBlockCommand => {
                if let Some(text) = self.selected_block_command_text() {
                    if let Some(active_pane) = self.active_pane_mut() {
                        let _ = active_pane.app.clipboard.copy(&text);
                    }
                }
            }
            ClipboardEffect::CopySelectedBlockOutput => {
                if let Some(text) = self.selected_block_output_text() {
                    if let Some(active_pane) = self.active_pane_mut() {
                        let _ = active_pane.app.clipboard.copy(&text);
                    }
                }
            }
            ClipboardEffect::Paste => {
                let Some(text) = self
                    .active_pane_mut()
                    .and_then(|pane| pane.app.clipboard.paste().ok())
                else {
                    return;
                };

                let mut refresh_command_search = false;
                if let Some(active_pane) = self.active_pane_mut() {
                    if let Some(command_search) = active_pane.app.command_search.as_mut() {
                        command_search.query.push_str(&text);
                        refresh_command_search = true;
                    } else if active_pane.app.input_mode == InputMode::CommandPalette
                        || active_pane.app.input_editor.is_active
                    {
                        let _ = active_pane.app.input_editor.buffer.insert_at(0, &text);
                        active_pane.history_nav = HistoryNavigationState::default();
                    } else {
                        self.send_raw_input_to_pty(text.as_bytes());
                    }
                }
                if refresh_command_search {
                    self.refresh_command_search();
                }
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
        }
    }

    fn apply_viewport_effect(&mut self, effect: ViewportEffect) {
        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };
        let max_scroll = pane_max_scroll(active_pane);
        let page_size = active_pane.rows as usize;

        match effect {
            ViewportEffect::ScrollLines(lines) => {
                active_pane.viewport.scroll_lines(lines, max_scroll);
            }
            ViewportEffect::ScrollPages(pages) => {
                active_pane
                    .viewport
                    .scroll_pages(pages, page_size, max_scroll);
            }
            ViewportEffect::ScrollToTop => {
                active_pane.viewport.scroll_to_top(max_scroll);
            }
            ViewportEffect::ScrollToBottom => {
                active_pane.viewport.scroll_to_bottom();
            }
            ViewportEffect::FollowOutput(follow) => {
                active_pane.viewport.set_follow_output(follow, max_scroll);
            }
        }
        active_pane
            .terminal
            .state
            .set_display_offset(active_pane.viewport.display_offset());
    }

    fn apply_workspace_effect(&mut self, effect: WorkspaceEffect) {
        match effect {
            WorkspaceEffect::SaveSession(name) => {
                let session = self.snapshot_session();
                let path = named_session_path(&name);
                match save_session(&session, &path) {
                    Ok(()) => {
                        self.status_message = Some(format!("saved session snapshot '{}'", name));
                    }
                    Err(error) => warn!("failed to save session snapshot '{}': {error}", name),
                }
            }
            WorkspaceEffect::LoadSession(name) => {
                let path = named_session_path(&name);
                match load_session(&path) {
                    Ok(session) => {
                        self.restore_session(session);
                        self.status_message = Some(format!("loaded session snapshot '{}'", name));
                    }
                    Err(error) => warn!("failed to load session snapshot '{}': {error}", name),
                }
            }
            WorkspaceEffect::NewTab => {
                let pane_id = self.workspace.new_tab("Shell");
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                let payload = self.pane_hook_payload(pane_id);
                self.run_plugin_hook("tab_opened", &payload);
            }
            WorkspaceEffect::CloseTab => {
                let search = self.active_search_state();
                if let Some(removed) = self.workspace.close_active_tab() {
                    for pane_id in removed {
                        self.panes.remove(&pane_id);
                    }
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                    if let Some(search) = search {
                        self.install_search_state_on_active_pane(search);
                        self.refresh_global_search();
                    }
                }
            }
            WorkspaceEffect::NextTab => {
                let search = self.active_search_state();
                self.workspace.next_tab();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::PrevTab => {
                let search = self.active_search_state();
                self.workspace.prev_tab();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::SwitchToTab(index) => {
                let search = self.active_search_state();
                self.workspace.switch_tab(index.saturating_sub(1) as usize);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::SplitVertical => {
                let new_pane = self
                    .workspace
                    .split_active(walk_ui::splits::SplitDirection::Horizontal);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(new_pane) = new_pane {
                    let mut payload = self.pane_hook_payload(new_pane);
                    if let Some(object) = payload.as_object_mut() {
                        object.insert("direction".to_string(), json!("vertical"));
                    }
                    self.run_plugin_hook("pane_opened", &payload);
                }
            }
            WorkspaceEffect::SplitHorizontal => {
                let new_pane = self
                    .workspace
                    .split_active(walk_ui::splits::SplitDirection::Vertical);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(new_pane) = new_pane {
                    let mut payload = self.pane_hook_payload(new_pane);
                    if let Some(object) = payload.as_object_mut() {
                        object.insert("direction".to_string(), json!("horizontal"));
                    }
                    self.run_plugin_hook("pane_opened", &payload);
                }
            }
            WorkspaceEffect::CloseSplit => {
                let search = self.active_search_state();
                if let Some(removed_pane) = self.workspace.close_active_pane() {
                    self.panes.remove(&removed_pane);
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                    if let Some(search) = search {
                        self.install_search_state_on_active_pane(search);
                        self.refresh_global_search();
                    }
                }
            }
            WorkspaceEffect::FocusLeft => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Left, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::FocusRight => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Right, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::FocusUp => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Up, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::FocusDown => {
                let search = self.active_search_state();
                self.workspace
                    .focus_in_direction(FocusDirection::Down, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(search) = search {
                    self.install_search_state_on_active_pane(search);
                    self.refresh_global_search();
                }
            }
            WorkspaceEffect::ResizeSplitLeft => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Horizontal, -0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ResizeSplitRight => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Horizontal, 0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ResizeSplitUp => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Vertical, -0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ResizeSplitDown => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Vertical, 0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            WorkspaceEffect::ToggleBroadcast => {
                self.workspace.broadcast_input = !self.workspace.broadcast_input;
                self.status_message = Some(if self.workspace.broadcast_input {
                    "BROADCAST enabled".to_string()
                } else {
                    "BROADCAST disabled".to_string()
                });
            }
        }
    }

    fn apply_overlay_effect(&mut self, effect: OverlayEffect) {
        match effect {
            OverlayEffect::OpenSearch => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.close_command_palette();
                    active_pane.app.command_search = None;
                    active_pane.app.block_query = None;
                    active_pane.app.quick_select.dismiss();
                    active_pane.app.global_search.activate();
                }
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.refresh_global_search();
            }
            OverlayEffect::CloseSearch => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.global_search.deactivate();
                }
                self.refresh_global_search();
                if let Some(active_pane_id) = self.active_pane_id() {
                    self.sync_owned_input_state_for_pane(active_pane_id);
                }
            }
            OverlayEffect::OpenCommandPalette => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.global_search.deactivate();
                    active_pane.app.command_search = None;
                    active_pane.app.block_query = None;
                    active_pane.app.quick_select.dismiss();
                    active_pane.app.open_command_palette();
                }
                self.refresh_command_palette();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            OverlayEffect::CloseCommandPalette => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.close_command_palette();
                }
                if let Some(active_pane_id) = self.active_pane_id() {
                    self.sync_owned_input_state_for_pane(active_pane_id);
                }
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            OverlayEffect::OpenCommandSearch => {
                if !self
                    .active_pane()
                    .is_some_and(Self::should_activate_owned_input)
                {
                    self.status_message = Some(
                        "Command search is only available when owned input is active".to_string(),
                    );
                    return;
                }
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.global_search.deactivate();
                    active_pane.app.block_query = None;
                    active_pane.app.quick_select.dismiss();
                    if active_pane.app.input_mode == InputMode::CommandPalette {
                        active_pane.app.close_command_palette();
                    }
                    let mut command_search = CommandSearchState::new();
                    command_search.query = active_pane.app.input_editor.buffer.text();
                    active_pane.app.command_search = Some(command_search);
                }
                self.refresh_command_search();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(active_pane_id) = self.active_pane_id() {
                    self.sync_owned_input_state_for_pane(active_pane_id);
                }
            }
            OverlayEffect::CloseCommandSearch => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.command_search = None;
                }
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                if let Some(active_pane_id) = self.active_pane_id() {
                    self.sync_owned_input_state_for_pane(active_pane_id);
                }
            }
            OverlayEffect::OpenQuickSelect => {
                self.open_quick_select(QuickSelectScope::Viewport);
            }
            OverlayEffect::OpenQuickSelectBlock => {
                self.open_quick_select(QuickSelectScope::SelectedBlock);
            }
            OverlayEffect::CloseQuickSelect => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.quick_select.dismiss();
                }
            }
            OverlayEffect::OpenBlockQuery {
                mode,
                target_block_id,
            } => {
                let Some(output_lines) = self.active_pane().and_then(|pane| {
                    pane.app
                        .block_manager
                        .get_block(target_block_id)
                        .map(|block| collect_block_output_lines(&pane.terminal, block))
                }) else {
                    self.status_message = Some("No block available".to_string());
                    return;
                };
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.close_command_palette();
                    active_pane.app.global_search.deactivate();
                    active_pane.app.command_search = None;
                    active_pane.app.quick_select.dismiss();
                    active_pane.app.block_query = Some(BlockQueryState::new(mode, target_block_id));
                    if let Some(block_query) = active_pane.app.block_query.as_mut() {
                        block_query.search("", &output_lines);
                    }
                }
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            OverlayEffect::CloseBlockQuery => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.block_query = None;
                }
                if let Some(active_pane_id) = self.active_pane_id() {
                    self.sync_owned_input_state_for_pane(active_pane_id);
                }
            }
        }
    }

    fn handle_search_input(&mut self, event: &InputEvent) -> bool {
        let Some(active_pane) = self.active_pane_mut() else {
            return false;
        };
        if !active_pane.app.global_search.is_active {
            return false;
        }

        match &event.action {
            KeyAction::Escape => active_pane.app.global_search.deactivate(),
            KeyAction::Enter | KeyAction::ArrowDown => {
                active_pane.app.global_search.next_match();
            }
            KeyAction::ArrowUp => {
                active_pane.app.global_search.prev_match();
            }
            KeyAction::Backspace
                if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                active_pane.app.global_search.search_input.pop();
                self.refresh_global_search();
            }
            KeyAction::Char(ch)
                if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                active_pane.app.global_search.search_input.push(*ch);
                self.refresh_global_search();
            }
            _ => {}
        }

        if let Some(active_pane_id) = self.active_pane_id() {
            self.sync_owned_input_state_for_pane(active_pane_id);
        }
        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
        self.scroll_to_current_search_match();
        self.needs_redraw = true;
        true
    }

    fn handle_block_query_input(&mut self, event: &InputEvent) -> bool {
        if !matches!(self.active_pane(), Some(pane) if pane.app.block_query.is_some()) {
            return false;
        }

        let mut close_overlay = false;
        let mut query_changed = false;
        let mut navigated = false;

        if let Some(active_pane) = self.active_pane_mut() {
            let Some(block_query) = active_pane.app.block_query.as_mut() else {
                return false;
            };

            match &event.action {
                KeyAction::Escape => close_overlay = true,
                KeyAction::Enter | KeyAction::ArrowDown => {
                    block_query.next_match();
                    navigated = true;
                }
                KeyAction::ArrowUp => {
                    block_query.prev_match();
                    navigated = true;
                }
                KeyAction::Backspace
                    if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
                {
                    block_query.query.pop();
                    query_changed = true;
                }
                KeyAction::Char(ch)
                    if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
                {
                    block_query.query.push(*ch);
                    query_changed = true;
                }
                _ => {}
            }
        }

        if close_overlay {
            if let Some(active_pane) = self.active_pane_mut() {
                active_pane.app.block_query = None;
            }
            if let Some(active_pane_id) = self.active_pane_id() {
                self.sync_owned_input_state_for_pane(active_pane_id);
            }
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            self.needs_redraw = true;
            return true;
        }

        if query_changed {
            self.refresh_block_query();
        } else if navigated {
            self.scroll_to_current_block_query_match();
        }

        self.needs_redraw = true;
        true
    }

    fn open_quick_select(&mut self, scope: QuickSelectScope) {
        let Some(active_pane_id) = self.active_pane_id() else {
            return;
        };
        let Some(rows) = self
            .panes
            .get(&active_pane_id)
            .map(|pane| quick_select_rows_for_scope(pane, scope))
        else {
            return;
        };

        if let Some(active_pane) = self.panes.get_mut(&active_pane_id) {
            active_pane
                .app
                .quick_select
                .activate(scope, &rows, &self.pattern_registry);
            if active_pane.app.quick_select.matches.is_empty() {
                active_pane.app.quick_select.dismiss();
                self.status_message = Some("No quick-select matches in scope".to_string());
            }
        }
        self.needs_redraw = true;
    }

    fn handle_quick_select_input(&mut self, event: &InputEvent) -> bool {
        if !matches!(self.active_pane(), Some(pane) if pane.app.quick_select.active) {
            return false;
        }

        match event.action {
            KeyAction::Escape => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.quick_select.dismiss();
                }
                self.needs_redraw = true;
                true
            }
            KeyAction::Enter => {
                let copied = self
                    .active_pane()
                    .and_then(|pane| pane.app.quick_select.selected())
                    .map(|selected| selected.text.clone());
                if let Some(text) = copied {
                    if let Some(active_pane) = self.active_pane_mut() {
                        if let Err(error) = active_pane.app.clipboard.copy(&text) {
                            warn!("failed to copy quick-select match: {error}");
                        }
                        active_pane.app.quick_select.dismiss();
                    }
                    self.status_message = Some("Copied quick-select match".to_string());
                }
                self.needs_redraw = true;
                true
            }
            KeyAction::Char(ch)
                if !event.modifiers.ctrl
                    && !event.modifiers.alt
                    && !event.modifiers.meta
                    && !event.modifiers.shift =>
            {
                let copied = if let Some(active_pane) = self.active_pane_mut() {
                    active_pane
                        .app
                        .quick_select
                        .handle_label_char(ch)
                        .map(|selected| selected.text)
                } else {
                    None
                };
                if let Some(text) = copied {
                    if let Some(active_pane) = self.active_pane_mut() {
                        if let Err(error) = active_pane.app.clipboard.copy(&text) {
                            warn!("failed to copy quick-select match: {error}");
                        }
                    }
                    self.status_message = Some("Copied quick-select match".to_string());
                }
                self.needs_redraw = true;
                true
            }
            _ => true,
        }
    }

    fn handle_command_search_input(&mut self, event: &InputEvent) -> bool {
        if !matches!(self.active_pane(), Some(pane) if pane.app.command_search.is_some()) {
            return false;
        }

        let mut close_overlay = false;
        let mut query_changed = false;
        let mut accepted_command = None;

        if let Some(active_pane) = self.active_pane_mut() {
            let Some(command_search) = active_pane.app.command_search.as_mut() else {
                return false;
            };

            match &event.action {
                KeyAction::Escape => close_overlay = true,
                KeyAction::Enter => {
                    accepted_command = command_search
                        .current_match()
                        .map(|candidate| candidate.entry.command.clone());
                }
                KeyAction::ArrowDown => {
                    command_search.next_match();
                }
                KeyAction::ArrowUp => {
                    command_search.prev_match();
                }
                KeyAction::Backspace
                    if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
                {
                    command_search.query.pop();
                    query_changed = true;
                }
                KeyAction::Char(ch)
                    if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
                {
                    command_search.query.push(*ch);
                    query_changed = true;
                }
                _ => {}
            }
        }

        if close_overlay {
            if let Some(active_pane) = self.active_pane_mut() {
                active_pane.app.command_search = None;
            }
            if let Some(active_pane_id) = self.active_pane_id() {
                self.sync_owned_input_state_for_pane(active_pane_id);
            }
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            self.needs_redraw = true;
            return true;
        }

        if query_changed {
            self.refresh_command_search();
        }

        if let Some(command) = accepted_command {
            if let Some(active_pane) = self.active_pane_mut() {
                active_pane.app.input_editor.buffer.set_text(&command);
                active_pane.app.command_search = None;
                active_pane.history_nav = HistoryNavigationState::default();
            }
            if let Some(active_pane_id) = self.active_pane_id() {
                self.sync_owned_input_state_for_pane(active_pane_id);
            }
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
        }

        self.needs_redraw = true;
        true
    }

    fn handle_owned_input(&mut self, event: &InputEvent) -> bool {
        let Some(pane_id) = self.active_pane_id() else {
            return false;
        };
        if !self
            .panes
            .get(&pane_id)
            .is_some_and(Self::should_activate_owned_input)
        {
            return false;
        }

        if matches!(event.action, KeyAction::ArrowUp | KeyAction::ArrowDown)
            && !event.modifiers.ctrl
            && !event.modifiers.alt
            && !event.modifiers.meta
        {
            let step_up = matches!(event.action, KeyAction::ArrowUp);
            self.navigate_owned_history(pane_id, step_up);
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            self.needs_redraw = true;
            return true;
        }

        if let Some(pane) = self.panes.get_mut(&pane_id) {
            pane.history_nav = HistoryNavigationState::default();
        }

        let Some(editor_key) = input_event_to_editor_key(event) else {
            return false;
        };

        let mut submitted = None;
        let mut send_eof = false;
        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            match active_pane.app.input_editor.handle_key(editor_key) {
                EditorAction::Submit(command) => submitted = Some(command),
                EditorAction::SendEof => send_eof = true,
                EditorAction::None => {}
            }
        }

        if let Some(command) = submitted {
            self.submit_owned_input(pane_id, command);
        }
        if send_eof {
            self.send_raw_input_to_pty(b"\x04");
        }

        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
        self.needs_redraw = true;
        true
    }

    fn handle_editor_input(&mut self, event: &InputEvent) -> bool {
        if !matches!(
            self.active_pane(),
            Some(pane) if pane.app.input_mode == InputMode::CommandPalette
        ) {
            return false;
        }

        match event.action {
            KeyAction::Escape => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.close_command_palette();
                }
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.needs_redraw = true;
                true
            }
            KeyAction::ArrowDown => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.command_palette.select_next();
                }
                self.needs_redraw = true;
                true
            }
            KeyAction::ArrowUp => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.command_palette.select_prev();
                }
                self.needs_redraw = true;
                true
            }
            KeyAction::Enter => {
                let selected = self.active_pane().and_then(|pane| {
                    pane.app
                        .command_palette
                        .selected()
                        .map(|entry| entry.action.clone())
                });

                if let Some(selected) = selected {
                    match selected {
                        PaletteAction::BuiltInAction(action_name) => {
                            if let Some(action) = parse_palette_action(&action_name) {
                                if let Some(active_pane) = self.active_pane_mut() {
                                    active_pane.app.close_command_palette();
                                }
                                self.handle_action(action);
                            }
                        }
                        PaletteAction::LuaCommand(command) => {
                            if let Some(action_name) = self
                                .plugins
                                .as_ref()
                                .and_then(|plugins| plugins.resolve_command_action(&command))
                            {
                                if let Some(action) = parse_palette_action(&action_name) {
                                    if let Some(active_pane) = self.active_pane_mut() {
                                        active_pane.app.close_command_palette();
                                    }
                                    self.handle_action(action);
                                }
                            }
                        }
                        PaletteAction::Workflow(workflow_name) => {
                            if let Some(workflow) = self.workflow_store.by_name(&workflow_name).cloned() {
                                if let Some(active_pane) = self.active_pane_mut() {
                                    active_pane.app.close_command_palette();
                                    active_pane.app.input_mode = InputMode::OwnedInput;
                                    active_pane.app.input_editor.is_active = true;
                                    active_pane.app.input_editor.load_workflow(&workflow);
                                }
                                self.status_message =
                                    Some(format!("Loaded workflow '{}'", workflow.name));
                            }
                        }
                        PaletteAction::RecentCommand(command) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                                active_pane.app.input_editor.is_active = true;
                                active_pane.app.input_editor.buffer.set_text(&command);
                            }
                        }
                        PaletteAction::FilePath(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane
                                    .app
                                    .input_editor
                                    .buffer
                                    .insert_at(0, &path)
                                    .ok();
                                active_pane
                                    .app
                                    .command_palette
                                    .set_query(&active_pane.app.input_editor.buffer.text());
                            }
                        }
                    }
                } else {
                    let query = self
                        .active_pane()
                        .map(|pane| pane.app.input_editor.buffer.text())
                        .unwrap_or_default();
                    self.handle_command_palette_submit(query);
                }

                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.needs_redraw = true;
                true
            }
            _ => {
                let Some(editor_key) = input_event_to_editor_key(event) else {
                    return false;
                };
                let mut send_eof = false;
                if let Some(active_pane) = self.active_pane_mut() {
                    if let EditorAction::SendEof = active_pane.app.input_editor.handle_key(editor_key)
                    {
                        send_eof = true;
                    }
                    let query = active_pane.app.input_editor.buffer.text();
                    active_pane.app.command_palette.set_query(&query);
                }
                if send_eof {
                    self.send_raw_input_to_pty(b"\x04");
                }
                self.refresh_command_palette();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.needs_redraw = true;
                true
            }
        }
    }

    fn enter_vi_mode(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            return;
        };
        if let Some(pane) = self.panes.get_mut(&pane_id) {
            let (cursor_col, _) = pane.terminal.state.cursor_position();
            let cursor_row = pane.terminal.state.absolute_cursor_row();
            pane.app.vi_mode = Some(ViModeState::new(cursor_row, cursor_col));
            pane.app.input_editor.is_active = false;
            self.status_message = Some("-- VI --".to_string());
        }
        self.needs_redraw = true;
    }

    fn exit_vi_mode(&mut self, status_message: Option<String>) {
        if let Some(pane_id) = self.active_pane_id() {
            if let Some(pane) = self.panes.get_mut(&pane_id) {
                pane.app.vi_mode = None;
            }
        }
        if let Some(message) = status_message {
            self.status_message = Some(message);
        }
        self.needs_redraw = true;
    }

    fn handle_vi_mode_input(&mut self, event: &InputEvent) -> bool {
        let Some(pane_id) = self.active_pane_id() else {
            return false;
        };
        if !self
            .panes
            .get(&pane_id)
            .is_some_and(|pane| pane.app.vi_mode.is_some())
        {
            return false;
        }

        let mut copy_range: Option<((usize, usize), (usize, usize))> = None;
        let mut should_exit = false;

        if let Some(pane) = self.panes.get_mut(&pane_id) {
            let mut vi = match pane.app.vi_mode.take() {
                Some(vi) => vi,
                None => return false,
            };

            let min_row = 0usize;
            let max_row = pane.terminal.state.total_rows().saturating_sub(1);
            let page_rows = pane.terminal.rows() as usize;
            let total_cols = pane.terminal.state.columns().max(1);
            let block_starts = pane
                .app
                .block_manager
                .blocks
                .iter()
                .map(|block| block.output_start_row)
                .collect::<Vec<_>>();
            let block_ends = pane
                .app
                .block_manager
                .blocks
                .iter()
                .map(|block| block.output_end_row)
                .collect::<Vec<_>>();
            let search_matches = pane
                .app
                .global_search
                .matches
                .iter()
                .filter(|item| item.pane_id == pane_id && !item.is_command)
                .map(|item| (item.row, item.col_start as usize))
                .collect::<Vec<_>>();

            match &event.action {
                KeyAction::Escape => {
                    should_exit = true;
                }
                KeyAction::Char('q') | KeyAction::Char('i') => {
                    should_exit = true;
                }
                KeyAction::Char(ch) => {
                    if let Some(pending) = vi.pending.take() {
                        let line = pane.terminal.state.row_text(vi.cursor_row);
                        match pending {
                            ViPending::G => {
                                if *ch == 'g' {
                                    vi.top(min_row, line.chars().count().max(1));
                                }
                            }
                            ViPending::BlockBackward => {
                                if *ch == 'b' {
                                    vi.prev_boundary(&block_starts);
                                } else if *ch == 'e' {
                                    vi.prev_boundary(&block_ends);
                                }
                            }
                            ViPending::BlockForward => {
                                if *ch == 'b' {
                                    vi.next_boundary(&block_starts);
                                } else if *ch == 'e' {
                                    vi.next_boundary(&block_ends);
                                }
                            }
                            ViPending::FindForward => vi.find_forward(&line, *ch),
                            ViPending::FindBackward => vi.find_backward(&line, *ch),
                        }
                    } else {
                        let line = pane.terminal.state.row_text(vi.cursor_row);
                        let line_len = line.chars().count().max(1);
                        match *ch {
                            'h' => vi.left(),
                            'l' => vi.right(line_len),
                            'j' => {
                                let next_line = pane
                                    .terminal
                                    .state
                                    .row_text((vi.cursor_row + 1).min(max_row));
                                vi.down(max_row, next_line.chars().count().max(1));
                            }
                            'k' => {
                                let prev_line =
                                    pane.terminal.state.row_text(vi.cursor_row.saturating_sub(1));
                                vi.up(min_row, prev_line.chars().count().max(1));
                            }
                            'w' => vi.word_forward(&line),
                            'b' => vi.word_backward(&line),
                            'e' => vi.word_end(&line),
                            '0' => vi.line_start(),
                            '$' => vi.line_end(line_len),
                            'G' => {
                                let last_line = pane.terminal.state.row_text(max_row);
                                vi.bottom(max_row, last_line.chars().count().max(1));
                            }
                            'g' => vi.pending = Some(ViPending::G),
                            '[' => vi.pending = Some(ViPending::BlockBackward),
                            ']' => vi.pending = Some(ViPending::BlockForward),
                            'f' => vi.pending = Some(ViPending::FindForward),
                            'F' => vi.pending = Some(ViPending::FindBackward),
                            'v' => vi.enter_visual(ViSubMode::Visual),
                            'V' => vi.enter_visual(ViSubMode::VisualLine),
                            'y' => {
                                if let Some(range) = vi.visual_range() {
                                    copy_range = Some(range);
                                    should_exit = true;
                                }
                            }
                            'n' => vi.next_search_match(&search_matches),
                            'N' => vi.prev_search_match(&search_matches),
                            '/' => {
                                pane.app.global_search.activate();
                                pane.app.global_search.search_input.clear();
                            }
                            _ => {}
                        }
                    }
                }
                KeyAction::ArrowLeft => vi.left(),
                KeyAction::ArrowRight => {
                    let line = pane.terminal.state.row_text(vi.cursor_row);
                    vi.right(line.chars().count().max(1));
                }
                KeyAction::ArrowUp => {
                    let prev_line = pane.terminal.state.row_text(vi.cursor_row.saturating_sub(1));
                    vi.up(min_row, prev_line.chars().count().max(1));
                }
                KeyAction::ArrowDown => {
                    let next_line = pane
                        .terminal
                        .state
                        .row_text((vi.cursor_row + 1).min(max_row));
                    vi.down(max_row, next_line.chars().count().max(1));
                }
                _ => {}
            }

            if event.modifiers.ctrl && matches!(event.action, KeyAction::Char('d')) {
                let line = pane.terminal.state.row_text(vi.cursor_row);
                vi.half_page_down(max_row, page_rows, line.chars().count().max(1));
            } else if event.modifiers.ctrl && matches!(event.action, KeyAction::Char('u')) {
                let line = pane.terminal.state.row_text(vi.cursor_row);
                vi.half_page_up(min_row, page_rows, line.chars().count().max(1));
            } else if event.modifiers.ctrl && matches!(event.action, KeyAction::Char('v')) {
                vi.enter_visual(ViSubMode::VisualBlock);
            }

            vi.cursor_col = vi.cursor_col.min(total_cols.saturating_sub(1));
            pane.app.vi_mode = Some(vi);
        }

        if let Some((start, end)) = copy_range {
            if let Some(text) = self
                .panes
                .get(&pane_id)
                .map(|pane| extract_absolute_selection_text(&pane.terminal, start, end))
            {
                if let Some(pane) = self.panes.get_mut(&pane_id) {
                    let _ = pane.app.clipboard.copy(&text);
                }
            }
        }

        if should_exit {
            self.exit_vi_mode(Some("Exited vi mode".to_string()));
            return true;
        }

        self.ensure_vi_cursor_visible(pane_id);
        self.status_message = self
            .panes
            .get(&pane_id)
            .and_then(|pane| pane.app.vi_mode.as_ref().map(|vi| vi.mode_label().to_string()));
        self.needs_redraw = true;
        true
    }

    fn ensure_vi_cursor_visible(&mut self, pane_id: PaneId) {
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return;
        };
        let Some(vi) = pane.app.vi_mode.as_ref() else {
            return;
        };

        let screen_rows = pane.terminal.state.screen_lines().max(1);
        let visible_start = pane.terminal.state.visible_start_row();
        let visible_end = visible_start + screen_rows.saturating_sub(1);
        if (visible_start..=visible_end).contains(&vi.cursor_row) {
            return;
        }

        let top_row = if vi.cursor_row < visible_start {
            vi.cursor_row
        } else {
            vi.cursor_row.saturating_sub(screen_rows.saturating_sub(1))
        };
        let scrollback = pane.terminal.state.scrollback_len();
        let desired_offset = scrollback.saturating_sub(top_row);
        let max_scroll = pane_max_scroll(pane);
        pane.viewport.set_display_offset(desired_offset, max_scroll);
        pane.terminal
            .state
            .set_display_offset(pane.viewport.display_offset());
    }

    fn apply_zoom(&mut self, target_size: f32) {
        if (self.font.font_size - target_size).abs() <= f32::EPSILON {
            return;
        }

        self.font.set_font_size(target_size);
        self.config.font_size = target_size;
        for pane in self.panes.values_mut() {
            pane.app.zoom.set_current_size(target_size);
            pane.app.config.font_size = target_size;
        }
        self.invalidate_all_row_caches();
        self.refresh_plugin_config();
        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
        self.needs_redraw = true;
    }

    fn update_grid(&mut self, size: PhysicalSize<u32>) {
        if size.width == 0 || size.height == 0 {
            return;
        }
        self.sync_workspace_layout(size);
    }

    fn submit_owned_input(&mut self, pane_id: PaneId, command: String) {
        let trimmed = command.trim().to_string();
        if let Some(pane) = self.panes.get_mut(&pane_id) {
            pane.history_nav = HistoryNavigationState::default();
            pane.prompt_ready = false;
            pane.app.input_editor.is_active = false;
            pane.pending_history = if trimmed.is_empty() {
                None
            } else {
                Some(HistoryEntry::pending(
                    &command,
                    (!pane.current_cwd.as_os_str().is_empty()).then(|| pane.current_cwd.clone()),
                    Some(pane_id),
                ))
            };
        }

        if !command.is_empty() {
            self.send_raw_input_to_pty(command.as_bytes());
        }
        self.send_raw_input_to_pty(b"\r");
    }

    fn navigate_owned_history(&mut self, pane_id: PaneId, step_up: bool) {
        let base_query = self
            .panes
            .get(&pane_id)
            .map(|pane| {
                if pane.history_nav.candidates.is_empty() && pane.history_nav.current.is_none() {
                    pane.app.input_editor.buffer.text()
                } else {
                    pane.history_nav.base_query.clone()
                }
            })
            .unwrap_or_default();

        let mut seen = HashSet::new();
        let mut candidates = self
            .panes
            .get(&pane_id)
            .map(|pane| {
                prefix_matches(&pane.pane_history, &base_query)
                    .into_iter()
                    .filter_map(|entry| {
                        seen.insert(entry.command.clone())
                            .then(|| entry.command.clone())
                    })
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();

        candidates.extend(
            prefix_matches(self.global_history.entries(), &base_query)
                .into_iter()
                .filter_map(|entry| {
                    seen.insert(entry.command.clone())
                        .then(|| entry.command.clone())
                }),
        );

        if let Some(pane) = self.panes.get_mut(&pane_id) {
            pane.history_nav.base_query = base_query.clone();
            pane.history_nav.candidates = candidates;

            if pane.history_nav.candidates.is_empty() {
                pane.history_nav.current = None;
                return;
            }

            pane.history_nav.current = if step_up {
                Some(pane.history_nav.current.map_or(0, |index| {
                    (index + 1).min(pane.history_nav.candidates.len() - 1)
                }))
            } else {
                match pane.history_nav.current {
                    Some(index) if index > 0 => Some(index - 1),
                    _ => None,
                }
            };

            if let Some(index) = pane.history_nav.current {
                if let Some(candidate) = pane.history_nav.candidates.get(index) {
                    pane.app.input_editor.buffer.set_text(candidate);
                }
            } else {
                pane.app.input_editor.buffer.set_text(&base_query);
            }
        }
    }

    fn refresh_global_search(&mut self) {
        let query = self.active_pane().and_then(|pane| {
            pane.app
                .global_search
                .is_active
                .then(|| pane.app.global_search.search_input.clone())
        });
        let Some(query) = query else {
            return;
        };
        if query.is_empty() {
            let Some(active_pane) = self.active_pane_mut() else {
                return;
            };
            active_pane.app.global_search.matches.clear();
            active_pane.app.global_search.current = 0;
            active_pane.app.global_search.query.clear();
            return;
        }

        let lines = self.collect_workspace_search_lines();
        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };
        active_pane.app.global_search.search(&query, &lines);
        self.scroll_to_current_search_match();
    }

    fn refresh_command_search(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            return;
        };
        let Some(query) = self.panes.get(&pane_id).and_then(|pane| {
            pane.app
                .command_search
                .as_ref()
                .map(|command_search| command_search.query.clone())
        }) else {
            return;
        };

        let pane_entries = self
            .panes
            .get(&pane_id)
            .map(|pane| pane.pane_history.clone())
            .unwrap_or_default();
        let global_entries = self.global_history.entries().to_vec();

        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            if let Some(command_search) = active_pane.app.command_search.as_mut() {
                command_search.search(&query, &pane_entries, &global_entries);
            }
        }
    }

    fn refresh_command_palette(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            return;
        };
        let entries = self.build_palette_entries(pane_id);
        let query = self
            .panes
            .get(&pane_id)
            .map(|pane| pane.app.input_editor.buffer.text())
            .unwrap_or_default();

        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            if !active_pane.app.command_palette.is_open {
                active_pane.app.command_palette.open(entries);
            } else {
                active_pane.app.command_palette.entries = entries;
                active_pane.app.command_palette.set_query(&query);
            }
        }
    }

    fn build_palette_entries(&self, pane_id: PaneId) -> Vec<PaletteEntry> {
        let mut entries = Vec::new();
        let Some(pane) = self.panes.get(&pane_id) else {
            return entries;
        };

        let mut action_bindings = HashMap::new();
        for (combo, action) in &pane.app.keybindings.bindings {
            action_bindings
                .entry(action.clone())
                .or_insert_with(|| key_combo_label(combo));
        }

        for (action, keybinding) in action_bindings {
            if let Some(action_id) = action_to_palette_id(&action) {
                entries.push(PaletteEntry {
                    label: action_display_label(&action),
                    description: if keybinding.is_empty() {
                        "Action".to_string()
                    } else {
                        format!("Keybinding: {keybinding}")
                    },
                    category: PaletteCategory::Action,
                    score: 0.0,
                    action: PaletteAction::BuiltInAction(action_id),
                });
            }
        }

        if let Some(plugins) = &self.plugins {
            for (name, action) in plugins.command_aliases() {
                entries.push(PaletteEntry {
                    label: name.clone(),
                    description: format!("Lua command -> {action}"),
                    category: PaletteCategory::LuaCommand,
                    score: 0.0,
                    action: PaletteAction::LuaCommand(name),
                });
            }
        }

        for workflow in self.workflow_store.workflows() {
            entries.push(PaletteEntry {
                label: workflow.name.clone(),
                description: if workflow.description.is_empty() {
                    workflow.template.clone()
                } else {
                    workflow.description.clone()
                },
                category: PaletteCategory::Workflow,
                score: 0.0,
                action: PaletteAction::Workflow(workflow.name.clone()),
            });
        }

        let mut seen_recent = HashSet::new();
        for command in pane
            .pane_history
            .iter()
            .rev()
            .chain(self.global_history.entries().iter().rev())
            .filter_map(|entry| {
                (!entry.command.trim().is_empty() && seen_recent.insert(entry.command.clone()))
                    .then(|| entry.command.clone())
            })
            .take(50)
        {
            entries.push(PaletteEntry {
                label: command.clone(),
                description: "Recent command".to_string(),
                category: PaletteCategory::RecentCommand,
                score: 0.0,
                action: PaletteAction::RecentCommand(command),
            });
        }

        if pane.current_cwd.is_dir() {
            if let Ok(read_dir) = std::fs::read_dir(&pane.current_cwd) {
                for path in read_dir.flatten().take(50).map(|entry| entry.path()) {
                    entries.push(PaletteEntry {
                        label: path
                            .file_name()
                            .and_then(|name| name.to_str())
                            .unwrap_or_default()
                            .to_string(),
                        description: path.display().to_string(),
                        category: PaletteCategory::FilePath,
                        score: 0.0,
                        action: PaletteAction::FilePath(path.display().to_string()),
                    });
                }
            }
        }

        entries
    }

    fn scroll_to_current_block_query_match(&mut self) {
        let Some(block_query) = self.active_block_query_state() else {
            return;
        };
        let Some(current_match) = block_query.current_match().cloned() else {
            return;
        };
        let Some(target_block) = self.active_pane().and_then(|pane| {
            pane.app
                .block_manager
                .get_block(block_query.target_block_id)
                .cloned()
        }) else {
            return;
        };
        let target_row = target_block.output_start_row + current_match.line;

        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };

        let screen_lines = active_pane.terminal.state.screen_lines();
        if screen_lines == 0 {
            return;
        }

        let visible_start = active_pane.terminal.state.visible_start_row();
        let visible_end = visible_start + screen_lines.saturating_sub(1);
        if (visible_start..=visible_end).contains(&target_row) {
            return;
        }

        let desired_start = if target_row < visible_start {
            target_row
        } else {
            target_row.saturating_sub(screen_lines.saturating_sub(1))
        };
        let new_offset = active_pane
            .terminal
            .state
            .scrollback_len()
            .saturating_sub(desired_start);
        active_pane
            .viewport
            .reveal_offset(new_offset, pane_max_scroll(active_pane));
        active_pane
            .terminal
            .state
            .set_display_offset(active_pane.viewport.display_offset());
        self.needs_redraw = true;
    }

    fn scroll_to_current_search_match(&mut self) {
        let Some(search) = self.active_search_state() else {
            return;
        };
        let Some(target) = search.matches.get(search.current).cloned() else {
            return;
        };

        if self.active_pane_id() != Some(target.pane_id)
            && self.workspace.focus_pane(target.pane_id)
        {
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            self.install_search_state_on_active_pane(search);
        }

        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };

        let screen_lines = active_pane.terminal.state.screen_lines();
        if screen_lines == 0 {
            return;
        }

        let visible_start = active_pane.terminal.state.visible_start_row();
        let visible_end = visible_start + screen_lines.saturating_sub(1);
        if (visible_start..=visible_end).contains(&target.row) {
            return;
        }

        let desired_start = if target.row < visible_start {
            target.row
        } else {
            target.row.saturating_sub(screen_lines.saturating_sub(1))
        };
        let new_offset = active_pane
            .terminal
            .state
            .scrollback_len()
            .saturating_sub(desired_start);
        active_pane
            .viewport
            .reveal_offset(new_offset, pane_max_scroll(active_pane));
        active_pane
            .terminal
            .state
            .set_display_offset(active_pane.viewport.display_offset());
        self.needs_redraw = true;
    }

    fn handle_command_palette_submit(&mut self, command: String) {
        let trimmed = command.trim();
        let active_pane_id = self.active_pane_id();

        if trimmed.is_empty() {
            if let Some(active_pane) = self.active_pane_mut() {
                active_pane.app.close_command_palette();
            }
            return;
        }

        let workflow_name = trimmed.strip_prefix('@').unwrap_or(trimmed).trim();
        if let Some(workflow) = self.workflow_store.by_name(workflow_name).cloned() {
            if let Some(active_pane) = self.active_pane_mut() {
                active_pane.app.close_command_palette();
                active_pane.app.input_mode = InputMode::OwnedInput;
                active_pane.app.input_editor.is_active = true;
                active_pane.app.input_editor.load_workflow(&workflow);
            }
            self.status_message = Some(format!("Loaded workflow '{}'", workflow.name));
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            return;
        }

        let mapped_action = self
            .plugins
            .as_ref()
            .and_then(|plugins| plugins.resolve_command_action(trimmed))
            .and_then(|action| parse_palette_action(&action))
            .or_else(|| parse_palette_action(trimmed));

        if let Some(action) = mapped_action {
            if let Some(active_pane) = self.active_pane_mut() {
                active_pane.app.close_command_palette();
            }
            self.handle_action(action);
        } else {
            self.send_raw_input_to_pty(command.as_bytes());
            self.send_raw_input_to_pty(b"\r");
            if let Some(active_pane) = self.active_pane_mut() {
                active_pane.app.close_command_palette();
            }
            if let Some(pane_id) = active_pane_id {
                let mut payload = self.pane_hook_payload(pane_id);
                if let Some(object) = payload.as_object_mut() {
                    object.insert("command".to_string(), json!(command));
                }
                self.run_plugin_hook("command_submitted", &payload);
            }
        }
    }

    fn pixel_to_cell(&self, x: f64, y: f64) -> Option<CellPos> {
        let active_pane = self.active_pane()?;
        if active_pane.cols == 0 || active_pane.rows == 0 {
            return None;
        }

        let viewport = active_pane.ui_rects.viewport;
        if x < f64::from(viewport.x)
            || y < f64::from(viewport.y)
            || x > f64::from(viewport.x + viewport.w)
            || y > f64::from(viewport.y + viewport.h)
        {
            return None;
        }

        let local_x = x - f64::from(viewport.x);
        let local_y = y - f64::from(viewport.y);
        let col = ((local_x / f64::from(self.font.metrics.cell_width)).floor() as i64)
            .clamp(0, i64::from(active_pane.cols.saturating_sub(1))) as u16;
        let row = ((local_y / f64::from(self.font.metrics.cell_height)).floor() as i64)
            .clamp(0, i64::from(active_pane.rows.saturating_sub(1))) as u16;

        Some(CellPos { row, col })
    }

    fn selection_text(&self) -> Option<String> {
        let active_pane = self.active_pane()?;
        let (start, end) = active_pane.app.selection.selection_range()?;
        Some(extract_selection_text(&active_pane.terminal, start, end))
    }

    fn selected_block_text(&self) -> Option<String> {
        let active_pane = self.active_pane()?;
        let selected = active_pane.app.selected_or_latest_block()?;
        Some(extract_block_text(&active_pane.terminal, selected))
    }

    fn selected_block_command_text(&self) -> Option<String> {
        let active_pane = self.active_pane()?;
        active_pane
            .app
            .selected_or_latest_block()
            .map(extract_block_command_text)
    }

    fn selected_block_output_text(&self) -> Option<String> {
        let active_pane = self.active_pane()?;
        let selected = active_pane.app.selected_or_latest_block()?;
        Some(extract_block_output_text(&active_pane.terminal, selected))
    }
}

impl AppHandler for WalkHandler {
    fn on_init(&mut self, window: Arc<Window>) {
        let size = window.inner_size();
        self.window = Some(window.clone());

        // Initialize wgpu
        let instance = wgpu::Instance::new(&wgpu::InstanceDescriptor::default());
        let surface = instance.create_surface(window).expect("create surface");

        let gpu = pollster::block_on(GpuContext::new_async(
            &instance,
            &surface,
            size.width,
            size.height,
        ))
        .expect("create GPU context");

        let pipeline = TerminalRenderPipeline::new(&gpu);
        let batch = QuadBatch::new();

        let atlas = GlyphAtlas::new(2_048, 2_048);

        self.render = Some(RenderState {
            instance,
            surface,
            gpu,
            pipeline,
            batch,
            atlas,
        });
        if let Some(render) = self.render.as_mut() {
            render.pipeline.upload_background_image(
                &render.gpu,
                self.background.image.as_ref().map(|image| image.width),
                self.background.image.as_ref().map(|image| image.height),
                self.background
                    .image
                    .as_ref()
                    .map(|image| image.pixels.as_ref()),
            );
        }

        // Compute grid dimensions
        self.update_grid(size);
        if self.config.restore_session {
            let path = default_session_path();
            if let Ok(session) = load_session(&path) {
                self.restore_session(session);
            }
        }
        self.needs_redraw = true;
        let payload = self.workspace_hook_payload();
        self.refresh_plugin_snapshot();
        self.run_plugin_hook("app_start", &payload);
        info!("GPU initialized");
    }

    fn on_frame_tick(&mut self) -> bool {
        let cursor_visible = self.cursor_visible();
        if cursor_visible != self.last_cursor_visible {
            self.last_cursor_visible = cursor_visible;
            self.needs_redraw = true;
        }

        if self
            .pending_close_confirmation
            .is_some_and(|instant| instant.elapsed().as_secs_f32() > 2.0)
        {
            self.pending_close_confirmation = None;
            if self.status_message.as_deref()
                == Some("Running processes detected. Close again within 2s to exit.")
            {
                self.status_message = None;
            }
            self.needs_redraw = true;
        }

        if let Some(theme) = self.theme_watcher.as_ref().and_then(ThemeWatcher::poll) {
            let mut theme = theme;
            if let Err(error) =
                walk_ui::theme_loader::apply_theme_overrides(&mut theme, &self.theme_overrides)
            {
                warn!("failed to reapply live theme overrides after file reload: {error}");
            }
            let theme_name = theme.name.clone();
            self.apply_theme_to_runtime(theme);
            self.refresh_plugin_config();
            self.status_message = Some(format!("reloaded theme '{theme_name}'"));
            self.needs_redraw = true;
        }

        let pane_ids: Vec<PaneId> = self.panes.keys().copied().collect();
        let mut relayout = false;
        for pane_id in pane_ids {
            let mut semantic_events = Vec::new();
            let mut is_dirty = false;
            let previous_input_active = self
                .panes
                .get(&pane_id)
                .map(|pane| pane.app.input_editor.is_active)
                .unwrap_or(false);
            if let Some(pane) = self.panes.get_mut(&pane_id) {
                pane.terminal.process_pty_output();
                semantic_events = pane.terminal.drain_semantic_events();
                if pane.terminal.is_dirty() {
                    pane.viewport.on_output(pane_max_scroll(pane));
                }
                if pane.viewport.tick(pane_max_scroll(pane)) {
                    pane.terminal
                        .state
                        .set_display_offset(pane.viewport.display_offset());
                }
                is_dirty = pane.terminal.is_dirty();
                is_dirty |= pane.viewport.needs_render();
            }
            if !semantic_events.is_empty() {
                self.handle_semantic_events(pane_id, semantic_events);
            }
            self.sync_owned_input_state_for_pane(pane_id);
            let input_active = self
                .panes
                .get(&pane_id)
                .map(|pane| pane.app.input_editor.is_active)
                .unwrap_or(false);
            relayout |= input_active != previous_input_active;
            if self
                .panes
                .get(&pane_id)
                .is_some_and(|pane| pane.app.block_query.is_some())
                && is_dirty
            {
                self.refresh_block_query_for_pane(pane_id);
            }
            self.needs_redraw |= is_dirty;
        }

        if relayout {
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
        }

        self.needs_redraw
    }

    fn on_redraw(&mut self) {
        if !self.needs_redraw {
            return;
        }
        let redraw_started = Instant::now();

        // Build vertex data from terminal grid
        self.build_quads();

        // Render
        let clear_theme = self
            .active_pane()
            .map(|pane| pane.app.theme.clone())
            .unwrap_or_default();
        if let Some(ref mut render) = self.render {
            let clear = with_opacity(
                [
                    clear_theme.background.r,
                    clear_theme.background.g,
                    clear_theme.background.b,
                    clear_theme.background.a,
                ],
                self.config.window_opacity.clamp(0.0, 1.0),
            );
            if let Err(e) =
                render
                    .pipeline
                    .render_frame(&render.gpu, &render.surface, &render.batch, clear)
            {
                match e {
                    wgpu::SurfaceError::Lost | wgpu::SurfaceError::Outdated => {
                        let (w, h) = render.gpu.dimensions();
                        render.gpu.resize(&render.surface, w, h);
                    }
                    wgpu::SurfaceError::OutOfMemory => {
                        warn!("GPU out of memory");
                    }
                    _ => {}
                }
            }
        }

        for pane in self.panes.values_mut() {
            pane.terminal.mark_clean();
            pane.viewport.mark_rendered();
        }
        if self.redraw_history_ms.len() >= 60 {
            self.redraw_history_ms.pop_front();
        }
        self.redraw_history_ms
            .push_back(redraw_started.elapsed().as_secs_f32() * 1000.0);
        self.needs_redraw = false;
    }

    fn on_resize(&mut self, new_size: PhysicalSize<u32>) {
        if new_size.width == 0 || new_size.height == 0 {
            return;
        }

        if let Some(ref mut render) = self.render {
            render
                .gpu
                .resize(&render.surface, new_size.width, new_size.height);
        }

        self.update_grid(new_size);
        self.needs_redraw = true;
    }

    fn on_key_event(&mut self, event: InputEvent) {
        if self.handle_vi_mode_input(&event) {
            return;
        }

        if let Some(action) = self
            .active_pane()
            .and_then(|pane| pane.app.resolve_action(&event))
        {
            self.handle_action(action);
            return;
        }

        if self.handle_search_input(&event) {
            return;
        }

        if self.handle_block_query_input(&event) {
            return;
        }

        if self.handle_quick_select_input(&event) {
            return;
        }

        if self.handle_command_search_input(&event) {
            return;
        }

        if self.handle_owned_input(&event) {
            return;
        }

        if self.handle_editor_input(&event) {
            return;
        }

        if let Some(data) = input_event_to_pty_bytes(&event) {
            self.send_raw_input_to_pty(&data);
            self.needs_redraw = true;
        }
    }

    fn on_mouse_event(&mut self, event: walk_app::input::MouseEvent) {
        match event {
            walk_app::input::MouseEvent::Press {
                button: MouseButton::Left,
                x,
                y,
                modifiers,
            } => {
                if let Some(cell) = self.pixel_to_cell(x, y) {
                    let should_open_link = self.active_pane().is_some_and(|pane| {
                        let absolute_row = pane
                            .terminal
                            .state
                            .viewport_row_to_absolute(cell.row as usize);
                        let has_explicit = pane
                            .terminal
                            .state
                            .explicit_link_at(absolute_row, cell.col as usize)
                            .is_some();
                        has_explicit || modifiers.ctrl || modifiers.meta
                    });
                    if should_open_link {
                        if let Some(uri) = self.active_pane().and_then(|pane| {
                            let absolute_row = pane
                                .terminal
                                .state
                                .viewport_row_to_absolute(cell.row as usize);
                            link_at_cell(&pane.terminal, absolute_row, cell.col as usize)
                        }) {
                            walk_ui::links::open_url(&uri);
                            self.status_message = Some(format!("Opened {uri}"));
                            self.needs_redraw = true;
                            return;
                        }
                    }
                    if let Some(active_pane) = self.active_pane_mut() {
                        active_pane.app.selection.handle_mouse_down(cell);
                    }
                    self.needs_redraw = true;
                }
            }
            walk_app::input::MouseEvent::Release {
                button: MouseButton::Left,
                ..
            } => {
                let was_selecting = self.active_pane().is_some_and(|pane| {
                    matches!(pane.app.selection.state, SelectionState::Selecting { .. })
                });
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.selection.handle_mouse_up();
                }
                if was_selecting && self.config.copy_on_select {
                    if let Some(text) = self.selection_text() {
                        if let Some(active_pane) = self.active_pane_mut() {
                            let _ = active_pane.app.clipboard.copy(&text);
                        }
                    }
                }
                self.needs_redraw = true;
            }
            walk_app::input::MouseEvent::Move { x, y } => {
                if self.active_pane().is_some_and(|pane| {
                    matches!(pane.app.selection.state, SelectionState::Selecting { .. })
                }) {
                    if let Some(cell) = self.pixel_to_cell(x, y) {
                        if let Some(active_pane) = self.active_pane_mut() {
                            active_pane.app.selection.handle_mouse_drag(cell);
                        }
                        self.needs_redraw = true;
                    }
                } else if let Some(cell) = self.pixel_to_cell(x, y) {
                    let hovered = self.active_pane().and_then(|pane| {
                        let absolute_row = pane
                            .terminal
                            .state
                            .viewport_row_to_absolute(cell.row as usize);
                        link_at_cell(&pane.terminal, absolute_row, cell.col as usize)
                    });
                    if self.hovered_link != hovered {
                        self.hovered_link = hovered;
                        self.needs_redraw = true;
                    }
                } else if self.hovered_link.take().is_some() {
                    self.needs_redraw = true;
                }
            }
            walk_app::input::MouseEvent::Scroll { delta_y, .. } => {
                if self
                    .active_pane()
                    .is_some_and(|pane| pane.terminal.state.is_alt_screen())
                {
                    return;
                }

                if delta_y.abs() < f64::EPSILON {
                    return;
                }

                let lines = if delta_y.abs() < 1.0 {
                    delta_y.signum() as i32
                } else {
                    delta_y.round() as i32
                };
                self.apply_viewport_effect(ViewportEffect::ScrollLines(lines));
                self.needs_redraw = true;
            }
            walk_app::input::MouseEvent::Press { .. }
            | walk_app::input::MouseEvent::Release { .. } => {}
        }
    }

    fn on_focus_change(&mut self, focused: bool) {
        if focused {
            return;
        }

        if let Some(active_pane) = self.active_pane_mut() {
            if active_pane.app.input_mode == InputMode::CommandPalette {
                active_pane.app.close_command_palette();
            }
        }
        self.needs_redraw = true;
    }

    fn on_close_requested(&mut self) -> bool {
        if self.config.confirm_close_with_running_process && self.has_running_processes() {
            let confirmed = self
                .pending_close_confirmation
                .is_some_and(|instant| instant.elapsed().as_secs_f32() <= 2.0);
            if !confirmed {
                self.pending_close_confirmation = Some(Instant::now());
                self.status_message =
                    Some("Running processes detected. Close again within 2s to exit.".to_string());
                self.needs_redraw = true;
                return false;
            }
        }

        self.pending_close_confirmation = None;
        let payload = self.workspace_hook_payload();
        self.run_plugin_hook("app_exit", &payload);
        let session = self.snapshot_session();
        let _ = save_session(&session, &default_session_path());
        info!("walk closing");
        true
    }
}

fn compute_chrome_rects(
    size: PhysicalSize<u32>,
    tab_bar_visible: bool,
    status_bar_visible: bool,
) -> ChromeRects {
    let width = size.width as f32;
    let height = size.height as f32;
    let tab_bar_height = if tab_bar_visible { 32.0 } else { 0.0 };
    let status_height = if status_bar_visible { 24.0 } else { 0.0 };

    ChromeRects {
        tab_bar: Rect::new(0.0, 0.0, width, tab_bar_height),
        content: Rect::new(
            0.0,
            tab_bar_height,
            width,
            (height - tab_bar_height - status_height).max(0.0),
        ),
        status: Rect::new(0.0, (height - status_height).max(0.0), width, status_height),
    }
}

fn compute_pane_ui_rects(
    container: Rect,
    input_position: walk_input::editor::InputPosition,
    input_lines: usize,
    cell_height: f32,
    show_input: bool,
) -> UiRects {
    let line_count = input_lines.clamp(1, 8) as f32;
    let input_height = if show_input {
        (line_count * cell_height + 20.0).min((container.h * 0.45).max(cell_height))
    } else {
        0.0
    };

    match input_position {
        walk_input::editor::InputPosition::Top => UiRects {
            viewport: Rect::new(
                container.x,
                container.y + input_height,
                container.w,
                (container.h - input_height).max(cell_height),
            ),
            input: Rect::new(container.x, container.y, container.w, input_height),
        },
        walk_input::editor::InputPosition::Bottom => UiRects {
            viewport: Rect::new(
                container.x,
                container.y,
                container.w,
                (container.h - input_height).max(cell_height),
            ),
            input: Rect::new(
                container.x,
                container.y + container.h - input_height,
                container.w,
                input_height,
            ),
        },
    }
}

fn pane_max_scroll(pane: &PaneRuntime) -> f32 {
    pane.terminal.state.scrollback_len() as f32
}

fn render_tab_bar(
    render: &mut RenderState,
    font: &mut FontSystem,
    rect: Rect,
    tabs: &[(bool, String)],
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity([0.08, 0.09, 0.13, 1.0], surface_opacity),
    );
    if tabs.is_empty() {
        return;
    }

    let tab_width = (rect.w / tabs.len() as f32).clamp(120.0, 220.0);
    for (index, (is_active, label)) in tabs.iter().enumerate() {
        let x = rect.x + index as f32 * tab_width;
        let background = if *is_active {
            [0.14, 0.16, 0.22, 1.0]
        } else {
            [0.10, 0.11, 0.15, 1.0]
        };
        render.batch.push_bg_quad(
            x,
            rect.y,
            tab_width,
            rect.h,
            with_opacity(background, surface_opacity),
        );
        push_text(
            render,
            font,
            x + 12.0,
            rect.y + 8.0,
            label,
            with_opacity([0.75, 0.79, 0.96, 1.0], surface_opacity),
        );
    }
}

fn render_status_bar(
    render: &mut RenderState,
    font: &mut FontSystem,
    rect: Rect,
    status_text: Option<&str>,
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity([0.08, 0.09, 0.13, 1.0], surface_opacity),
    );
    let Some(status_text) = status_text else {
        return;
    };
    push_text(
        render,
        font,
        rect.x + 10.0,
        rect.y + 4.0,
        status_text,
        with_opacity([0.54, 0.58, 0.65, 1.0], surface_opacity),
    );
}

fn render_debug_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    content_rect: Rect,
    lines: &[String],
    surface_opacity: f32,
) {
    if lines.is_empty() {
        return;
    }

    let width = 260.0;
    let height = (lines.len() as f32 * font.metrics.cell_height) + 14.0;
    let x = content_rect.x + 12.0;
    let y = content_rect.y + 12.0;

    render.batch.push_bg_quad(
        x,
        y,
        width,
        height,
        with_opacity([0.06, 0.07, 0.10, 0.92], surface_opacity),
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        with_opacity([0.65, 0.77, 0.95, 0.95], surface_opacity),
    );

    for (index, line) in lines.iter().enumerate() {
        push_text(
            render,
            font,
            x + 10.0,
            y + 6.0 + index as f32 * font.metrics.cell_height,
            line,
            with_opacity([0.84, 0.88, 0.95, 1.0], surface_opacity),
        );
    }
}

fn render_owned_input(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    rect: Rect,
    input: &walk_input::editor::InputRenderData,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity(
            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.9,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 12.0;
    let padding_y = 8.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;

    if let Some((row, col_start, col_end)) = input.parameter_placeholder {
        let width = (col_end.saturating_sub(col_start).max(1) as f32) * font.metrics.cell_width;
        render.batch.push_bg_quad(
            base_x + col_start as f32 * font.metrics.cell_width,
            base_y + row as f32 * font.metrics.cell_height,
            width,
            font.metrics.cell_height,
            with_opacity(
                [
                    theme.highlight_current_match.r,
                    theme.highlight_current_match.g,
                    theme.highlight_current_match.b,
                    0.3,
                ],
                surface_opacity,
            ),
        );
    }

    for (row, line) in input.lines.iter().enumerate() {
        push_text(
            render,
            font,
            base_x,
            base_y + row as f32 * font.metrics.cell_height,
            line,
            with_opacity(
                [
                    theme.foreground.r,
                    theme.foreground.g,
                    theme.foreground.b,
                    theme.foreground.a,
                ],
                surface_opacity,
            ),
        );
    }

    if let Some(popup) = input.completion_popup.as_ref() {
        let max_visible = 10usize;
        let mut start = popup.selected.saturating_sub(max_visible / 2);
        if start + max_visible > popup.items.len() {
            start = popup.items.len().saturating_sub(max_visible);
        }
        let end = (start + max_visible).min(popup.items.len());
        let visible = popup.items[start..end].len();
        let popup_height = (visible as f32 + 1.0) * (font.metrics.cell_height + 2.0) + 8.0;
        let popup_width = (rect.w * 0.72).clamp(260.0, 680.0);
        let anchor_x = base_x + popup.anchor_col as f32 * font.metrics.cell_width;
        let popup_x = anchor_x.clamp(rect.x + 8.0, rect.x + rect.w - popup_width - 8.0);
        let popup_y = if matches!(input.position, walk_input::editor::InputPosition::Bottom) {
            (rect.y - popup_height - 6.0).max(0.0)
        } else {
            rect.y + rect.h + 6.0
        };

        render.batch.push_bg_quad(
            popup_x,
            popup_y,
            popup_width,
            popup_height,
            with_opacity([theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98], surface_opacity),
        );
        render.batch.push_bg_quad(
            popup_x,
            popup_y,
            popup_width,
            1.0,
            with_opacity(
                [
                    theme.highlight_current_match.r,
                    theme.highlight_current_match.g,
                    theme.highlight_current_match.b,
                    0.95,
                ],
                surface_opacity,
            ),
        );

        let mut row_y = popup_y + 5.0;
        push_text(
            render,
            font,
            popup_x + 8.0,
            row_y,
            "Completions",
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.92,
                ],
                surface_opacity,
            ),
        );
        row_y += font.metrics.cell_height + 2.0;

        for (visible_offset, item) in popup.items[start..end].iter().enumerate() {
            let absolute = start + visible_offset;
            if absolute == popup.selected {
                render.batch.push_bg_quad(
                    popup_x + 4.0,
                    row_y - 1.0,
                    popup_width - 8.0,
                    font.metrics.cell_height + 2.0,
                    with_opacity([theme.selection.r, theme.selection.g, theme.selection.b, 0.24], surface_opacity),
                );
            }
            let label = format!(
                "{} {}",
                completion_kind_token(&item.kind),
                item.text
            );
            push_text(
                render,
                font,
                popup_x + 8.0,
                row_y,
                &label,
                with_opacity(
                    [
                        theme.foreground.r,
                        theme.foreground.g,
                        theme.foreground.b,
                        theme.foreground.a,
                    ],
                    surface_opacity,
                ),
            );
            push_text(
                render,
                font,
                popup_x + popup_width * 0.45,
                row_y,
                &item.description,
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.9,
                    ],
                    surface_opacity,
                ),
            );
            row_y += font.metrics.cell_height + 2.0;
        }
    }

    if cursor_visible {
        if let Some((cursor_row, cursor_col)) = input.cursors.first().copied() {
            render.batch.push_cursor(
                base_x + cursor_col as f32 * font.metrics.cell_width,
                base_y + cursor_row as f32 * font.metrics.cell_height,
                font.metrics.cell_width,
                font.metrics.cell_height,
                cursor_shape,
                with_opacity(
                    [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.95],
                    surface_opacity,
                ),
            );
        }
    }
}

fn completion_kind_token(kind: &walk_input::completion::CompletionKind) -> &'static str {
    match kind {
        walk_input::completion::CompletionKind::Command => "[cmd]",
        walk_input::completion::CompletionKind::FilePath => "[path]",
        walk_input::completion::CompletionKind::EnvVar => "[env]",
        walk_input::completion::CompletionKind::Argument => "[arg]",
    }
}

#[allow(clippy::too_many_arguments)]
fn render_command_palette(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    input: &walk_input::editor::InputRenderData,
    palette: &CommandPaletteState,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    let panel_width = (viewport.w * 0.78).clamp(520.0, 980.0);
    let panel_height = (viewport.h * 0.72).clamp(220.0, 560.0);
    let rect = Rect::new(
        viewport.x + (viewport.w - panel_width) * 0.5,
        viewport.y + (viewport.h - panel_height) * 0.5,
        panel_width,
        panel_height,
    );

    render.batch.push_bg_quad(
        viewport.x,
        viewport.y,
        viewport.w,
        viewport.h,
        with_opacity([0.0, 0.0, 0.0, 0.32], surface_opacity),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity(
            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.9,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 14.0;
    let padding_y = 10.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;
    let input_line = input.lines.first().cloned().unwrap_or_default();
    let prefix = "Command Palette: ";
    push_text(
        render,
        font,
        base_x,
        base_y,
        "Run an action, workflow, alias, or recent command",
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                0.9,
            ],
            surface_opacity,
        ),
    );
    push_text(
        render,
        font,
        base_x,
        base_y + font.metrics.cell_height + 2.0,
        &format!("{prefix}{input_line}"),
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );

    let entries_max = 15usize;
    let available_entries = &palette.filtered;
    let mut start_idx = 0usize;
    if !available_entries.is_empty() {
        start_idx = palette.selected_index.saturating_sub(entries_max / 2);
        if start_idx + entries_max > available_entries.len() {
            start_idx = available_entries.len().saturating_sub(entries_max);
        }
    }
    let end_idx = (start_idx + entries_max).min(available_entries.len());
    let query = palette_query_content(&palette.query);
    let mut row_y = base_y + font.metrics.cell_height * 2.0 + 8.0;

    if available_entries.is_empty() {
        push_text(
            render,
            font,
            base_x,
            row_y,
            "No matching entries. Press Enter to run raw command input.",
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.85,
                ],
                surface_opacity,
            ),
        );
    } else {
        let mut last_category = None;
        for (visible_offset, filtered_idx) in
            available_entries[start_idx..end_idx].iter().enumerate()
        {
            let absolute_idx = start_idx + visible_offset;
            let Some(entry) = palette.entries.get(*filtered_idx) else {
                continue;
            };
            if last_category != Some(entry.category) {
                push_text(
                    render,
                    font,
                    base_x,
                    row_y,
                    palette_category_label(entry.category),
                    with_opacity(
                        [
                            theme.status_bar_text.r,
                            theme.status_bar_text.g,
                            theme.status_bar_text.b,
                            0.95,
                        ],
                        surface_opacity,
                    ),
                );
                row_y += font.metrics.cell_height + 2.0;
                last_category = Some(entry.category);
            }
            if absolute_idx == palette.selected_index {
                render.batch.push_bg_quad(
                    rect.x + 8.0,
                    row_y - 2.0,
                    rect.w - 16.0,
                    font.metrics.cell_height + 4.0,
                    with_opacity(
                        [theme.selection.r, theme.selection.g, theme.selection.b, 0.2],
                        surface_opacity,
                    ),
                );
            }
            for column in palette_highlight_columns(&entry.label, query) {
                render.batch.push_bg_quad(
                    base_x + column as f32 * font.metrics.cell_width,
                    row_y - 1.0,
                    font.metrics.cell_width,
                    font.metrics.cell_height + 2.0,
                    with_opacity(
                        [
                            theme.highlight_current_match.r,
                            theme.highlight_current_match.g,
                            theme.highlight_current_match.b,
                            0.22,
                        ],
                        surface_opacity,
                    ),
                );
            }
            push_text(
                render,
                font,
                base_x,
                row_y,
                &entry.label,
                with_opacity(
                    [
                        theme.foreground.r,
                        theme.foreground.g,
                        theme.foreground.b,
                        theme.foreground.a,
                    ],
                    surface_opacity,
                ),
            );
            push_text(
                render,
                font,
                base_x + 220.0,
                row_y,
                &entry.description,
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.9,
                    ],
                    surface_opacity,
                ),
            );
            row_y += font.metrics.cell_height + 4.0;
        }
        if available_entries.len() > entries_max {
            let indicator = format!(
                "{}-{} of {}",
                start_idx + 1,
                end_idx,
                available_entries.len()
            );
            push_text(
                render,
                font,
                rect.x + rect.w - 130.0,
                rect.y + rect.h - font.metrics.cell_height - 8.0,
                &indicator,
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.85,
                    ],
                    surface_opacity,
                ),
            );
        }
    }

    if cursor_visible {
        if let Some((cursor_row, cursor_col)) = input.cursors.first().copied() {
            let cursor_x = base_x
                + prefix.chars().count() as f32 * font.metrics.cell_width
                + cursor_col as f32 * font.metrics.cell_width;
            let cursor_y = base_y
                + font.metrics.cell_height
                + 2.0
                + cursor_row as f32 * font.metrics.cell_height;
            render.batch.push_cursor(
                cursor_x,
                cursor_y,
                font.metrics.cell_width,
                font.metrics.cell_height,
                cursor_shape,
                with_opacity(
                    [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.95],
                    surface_opacity,
                ),
            );
        }
    }
}

fn palette_category_label(category: PaletteCategory) -> &'static str {
    match category {
        PaletteCategory::Action => "Actions",
        PaletteCategory::LuaCommand => "Lua Commands",
        PaletteCategory::Workflow => "Workflows",
        PaletteCategory::RecentCommand => "Recent Commands",
        PaletteCategory::FilePath => "File Paths",
    }
}

fn palette_query_content(query: &str) -> &str {
    let trimmed = query.trim();
    if let Some(stripped) = trimmed.strip_prefix('>') {
        return stripped.trim_start();
    }
    if let Some(stripped) = trimmed.strip_prefix('@') {
        return stripped.trim_start();
    }
    trimmed
}

fn palette_highlight_columns(label: &str, query: &str) -> Vec<usize> {
    if query.is_empty() {
        return Vec::new();
    }

    let label_chars = label.chars().collect::<Vec<_>>();
    let query_chars = query.to_ascii_lowercase().chars().collect::<Vec<_>>();
    let mut columns = Vec::new();
    let mut cursor = 0usize;

    for query_char in query_chars {
        let mut matched = None;
        for (idx, label_char) in label_chars.iter().enumerate().skip(cursor) {
            if label_char.to_ascii_lowercase() == query_char {
                matched = Some(idx);
                break;
            }
        }
        let Some(idx) = matched else {
            return Vec::new();
        };
        columns.push(idx);
        cursor = idx + 1;
    }

    columns
}

#[allow(clippy::too_many_arguments)]
fn render_command_search(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    rect: Rect,
    command_search: &CommandSearchState,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity(
            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.9,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 12.0;
    let padding_y = 8.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;
    let prefix = "History: ";
    push_text(
        render,
        font,
        base_x,
        base_y,
        &format!("{prefix}{}", command_search.query),
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );

    let counter = command_search.match_count_display();
    push_text(
        render,
        font,
        rect.x + rect.w - 100.0,
        base_y,
        &counter,
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                0.85,
            ],
            surface_opacity,
        ),
    );

    let mut row_y = base_y + font.metrics.cell_height + 6.0;
    if command_search.results.is_empty() {
        push_text(
            render,
            font,
            base_x,
            row_y,
            "No matching commands",
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.85,
                ],
                surface_opacity,
            ),
        );
    } else {
        let mut last_scope = None;
        for (index, result) in command_search.results.iter().take(6).enumerate() {
            if last_scope != Some(result.scope) {
                let section_title = match result.scope {
                    CommandSearchScope::Pane => "Current Pane",
                    CommandSearchScope::Global => "Global History",
                };
                push_text(
                    render,
                    font,
                    base_x,
                    row_y,
                    section_title,
                    with_opacity(
                        [
                            theme.highlight_current_match.r,
                            theme.highlight_current_match.g,
                            theme.highlight_current_match.b,
                            0.95,
                        ],
                        surface_opacity,
                    ),
                );
                row_y += font.metrics.cell_height;
                last_scope = Some(result.scope);
            }

            if index == command_search.current {
                render.batch.push_bg_quad(
                    rect.x + 8.0,
                    row_y - 2.0,
                    rect.w - 16.0,
                    font.metrics.cell_height + 4.0,
                    with_opacity(
                        [theme.selection.r, theme.selection.g, theme.selection.b, 0.2],
                        surface_opacity,
                    ),
                );
            }

            push_text(
                render,
                font,
                base_x,
                row_y,
                &result.entry.command,
                with_opacity(
                    [
                        theme.foreground.r,
                        theme.foreground.g,
                        theme.foreground.b,
                        theme.foreground.a,
                    ],
                    surface_opacity,
                ),
            );
            push_text(
                render,
                font,
                base_x + 260.0,
                row_y,
                &history_metadata_label(&result.entry),
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.9,
                    ],
                    surface_opacity,
                ),
            );
            row_y += font.metrics.cell_height + 4.0;
        }
    }

    if cursor_visible {
        render.batch.push_cursor(
            base_x
                + prefix.chars().count() as f32 * font.metrics.cell_width
                + command_search.query.chars().count() as f32 * font.metrics.cell_width,
            base_y,
            font.metrics.cell_width,
            font.metrics.cell_height,
            cursor_shape,
            with_opacity(
                [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.95],
                surface_opacity,
            ),
        );
    }
}

fn history_metadata_label(entry: &HistoryEntry) -> String {
    let cwd = entry
        .cwd
        .as_ref()
        .map_or_else(|| "~".to_string(), |path| path.display().to_string());
    let exit = entry
        .exit_code
        .map_or_else(|| "exit ?".to_string(), |code| format!("exit {code}"));
    let duration = entry
        .duration_ms
        .map_or_else(String::new, |ms| format!(" | {}ms", ms));
    format!("{cwd} | {exit}{duration}")
}

fn render_search_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    search: &walk_ui::search::GlobalSearch,
    surface_opacity: f32,
) {
    let width = (viewport.w * 0.38).clamp(220.0, 420.0);
    let height = font.metrics.cell_height * 2.0 + 16.0;
    let x = viewport.x + viewport.w - width - 12.0;
    let y = viewport.y + 12.0;

    render.batch.push_bg_quad(
        x,
        y,
        width,
        height,
        with_opacity(
            [
                theme.tab_bar_bg.r,
                theme.tab_bar_bg.g,
                theme.tab_bar_bg.b,
                0.96,
            ],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.85,
            ],
            surface_opacity,
        ),
    );

    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0,
        &format!("Search: {}", search.search_input),
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0 + font.metrics.cell_height,
        &search.match_count_display(),
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                theme.status_bar_text.a,
            ],
            surface_opacity,
        ),
    );
}

#[allow(clippy::too_many_arguments)]
fn render_quick_select_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    visible_start_row: usize,
    visible_screen_lines: usize,
    matches: &[walk_ui::quick_select::QuickSelectMatch],
    typed_label: &str,
    surface_opacity: f32,
) {
    if visible_screen_lines == 0 {
        return;
    }

    for candidate in matches {
        if candidate.row < visible_start_row {
            continue;
        }
        let viewport_row = candidate.row - visible_start_row;
        if viewport_row >= visible_screen_lines {
            continue;
        }

        let row_y = viewport.y + viewport_row as f32 * font.metrics.cell_height;
        let x = viewport.x + candidate.col_start as f32 * font.metrics.cell_width;
        let width = (candidate.col_end.saturating_sub(candidate.col_start) as f32).max(1.0)
            * font.metrics.cell_width;
        let active = !typed_label.is_empty() && candidate.label.starts_with(typed_label);
        let fill = if active {
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.55,
            ]
        } else {
            [
                theme.highlight_match.r,
                theme.highlight_match.g,
                theme.highlight_match.b,
                0.35,
            ]
        };
        render.batch.push_bg_quad(
            x,
            row_y,
            width,
            font.metrics.cell_height,
            with_opacity(fill, surface_opacity),
        );

        let label_x = x;
        let label_y = row_y;
        render.batch.push_bg_quad(
            label_x,
            label_y,
            candidate.label.chars().count() as f32 * font.metrics.cell_width + 4.0,
            font.metrics.cell_height,
            with_opacity(
                [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.85],
                surface_opacity,
            ),
        );
        push_text(
            render,
            font,
            label_x + 2.0,
            label_y,
            &candidate.label,
            with_opacity(
                [
                    theme.background.r,
                    theme.background.g,
                    theme.background.b,
                    0.95,
                ],
                surface_opacity,
            ),
        );
    }
}

fn render_block_query_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    block_query: &BlockQueryState,
    filtered_lines: &[(usize, String)],
    surface_opacity: f32,
) {
    let is_filter = matches!(block_query.mode, BlockQueryMode::Filter);
    let width = if is_filter {
        (viewport.w * 0.48).clamp(280.0, 520.0)
    } else {
        (viewport.w * 0.4).clamp(240.0, 420.0)
    };
    let list_height = if is_filter {
        (viewport.h * 0.42).clamp(
            font.metrics.cell_height * 4.0,
            font.metrics.cell_height * 12.0,
        )
    } else {
        0.0
    };
    let height = font.metrics.cell_height * 2.0 + 16.0 + list_height;
    let x = viewport.x + viewport.w - width - 12.0;
    let y = viewport.y + 12.0;

    render.batch.push_bg_quad(
        x,
        y,
        width,
        height,
        with_opacity(
            [
                theme.tab_bar_bg.r,
                theme.tab_bar_bg.g,
                theme.tab_bar_bg.b,
                0.96,
            ],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.85,
            ],
            surface_opacity,
        ),
    );

    let title = match block_query.mode {
        BlockQueryMode::Find => "Find Block",
        BlockQueryMode::Filter => "Filter Block",
    };
    let header_text = if block_query.query.is_empty() {
        title.to_string()
    } else {
        format!("{title}: {}", block_query.query)
    };
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0,
        &header_text,
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0 + font.metrics.cell_height,
        &block_query.match_count_display(),
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                theme.status_bar_text.a,
            ],
            surface_opacity,
        ),
    );

    if !is_filter {
        return;
    }

    let lines_y = y + 12.0 + font.metrics.cell_height * 2.0;
    let max_chars = ((width - 24.0) / font.metrics.cell_width).floor().max(8.0) as usize;
    let max_visible_lines = filter_overlay_visible_lines(viewport, font.metrics.cell_height);
    let current_filtered_line = block_query.current_filtered_line();

    if filtered_lines.is_empty() {
        let empty_text = if block_query.query.is_empty() {
            "Type to filter block output"
        } else {
            "No lines matched"
        };
        push_text(
            render,
            font,
            x + 10.0,
            lines_y,
            empty_text,
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    theme.status_bar_text.a,
                ],
                surface_opacity,
            ),
        );
        return;
    }

    for (visible_idx, (line_idx, text)) in filtered_lines
        .iter()
        .skip(block_query.overlay_scroll_offset)
        .take(max_visible_lines)
        .enumerate()
    {
        let row_y = lines_y + visible_idx as f32 * font.metrics.cell_height;
        if current_filtered_line == Some(*line_idx) {
            render.batch.push_bg_quad(
                x + 8.0,
                row_y,
                width - 16.0,
                font.metrics.cell_height,
                with_opacity(
                    [
                        theme.highlight_current_match.r,
                        theme.highlight_current_match.g,
                        theme.highlight_current_match.b,
                        0.28,
                    ],
                    surface_opacity,
                ),
            );
        }

        let line_label = format!(
            "{:>4} {}",
            line_idx + 1,
            truncate_overlay_text(text, max_chars)
        );
        push_text(
            render,
            font,
            x + 10.0,
            row_y,
            &line_label,
            with_opacity(
                [
                    theme.foreground.r,
                    theme.foreground.g,
                    theme.foreground.b,
                    theme.foreground.a,
                ],
                surface_opacity,
            ),
        );
    }
}

fn filter_overlay_visible_lines(viewport: Rect, cell_height: f32) -> usize {
    (((viewport.h * 0.42).clamp(cell_height * 4.0, cell_height * 12.0)) / cell_height)
        .floor()
        .max(1.0) as usize
}

fn truncate_overlay_text(text: &str, max_chars: usize) -> String {
    let mut truncated = text.chars().take(max_chars).collect::<String>();
    if text.chars().count() > max_chars && max_chars > 3 {
        truncated.truncate(max_chars.saturating_sub(3));
        truncated.push_str("...");
    }
    truncated
}

fn with_opacity(mut color: [f32; 4], opacity: f32) -> [f32; 4] {
    color[3] *= opacity.clamp(0.0, 1.0);
    color
}

fn push_background_image(batch: &mut QuadBatch, rect: Rect, opacity: f32) {
    if rect.w <= 0.0 || rect.h <= 0.0 {
        return;
    }
    batch.push_image_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        [1.0, 1.0, 1.0, opacity.clamp(0.0, 1.0)],
    );
}

fn resolve_background_image_path(config: &WalkConfig) -> Option<std::path::PathBuf> {
    config.background_image.clone().or_else(|| {
        config.theme_path.as_ref().and_then(|path| {
            walk_ui::theme_loader::load_theme(path)
                .ok()
                .and_then(|theme| theme.background_image)
        })
    })
}

fn resolve_plugin_theme_path(name: &str) -> std::path::PathBuf {
    let candidate = std::path::PathBuf::from(name);
    if candidate.is_absolute()
        || candidate.extension().is_some()
        || candidate.components().count() > 1
    {
        return candidate;
    }

    WalkConfig::config_dir()
        .join("themes")
        .join(format!("{name}.toml"))
}

fn search_match_at_cell(
    search: &walk_ui::search::GlobalSearch,
    pane_id: PaneId,
    absolute_row: usize,
    column: u16,
) -> Option<bool> {
    if search.matches.is_empty() {
        return None;
    }

    for (index, search_match) in search.matches.iter().enumerate() {
        if search_match.is_command
            || search_match.pane_id != pane_id
            || search_match.row != absolute_row
        {
            continue;
        }
        if (search_match.col_start..search_match.col_end).contains(&column) {
            return Some(index == search.current);
        }
    }

    None
}

fn search_match_for_block_command(
    search: &walk_ui::search::GlobalSearch,
    pane_id: PaneId,
    block_id: u64,
) -> Option<bool> {
    if search.matches.is_empty() {
        return None;
    }

    search
        .matches
        .iter()
        .enumerate()
        .find(|(_, search_match)| {
            search_match.is_command
                && search_match.pane_id == pane_id
                && search_match.block_id == Some(block_id)
        })
        .map(|(index, _)| index == search.current)
}

fn block_query_match_at_cell(
    block_query: Option<&BlockQueryState>,
    blocks: &[Block],
    absolute_row: usize,
    column: u16,
) -> Option<bool> {
    let query = block_query?;
    let block = blocks
        .iter()
        .find(|block| block.id == query.target_block_id)?;
    if absolute_row < block.output_start_row || absolute_row > block.output_end_row {
        return None;
    }

    let line_index = absolute_row.saturating_sub(block.output_start_row);
    query
        .matches
        .iter()
        .enumerate()
        .find(|(_, search_match)| {
            search_match.line == line_index
                && (search_match.col_start as u16..search_match.col_end as u16).contains(&column)
        })
        .map(|(index, _)| index == query.current_match)
}

fn push_text(
    render: &mut RenderState,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    text: &str,
    color: [f32; 4],
) {
    let cell_width = font.metrics.cell_width;
    for (index, ch) in text.chars().enumerate() {
        push_glyph(render, font, x + index as f32 * cell_width, y, ch, color);
    }
}

fn push_glyph(
    render: &mut RenderState,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    character: char,
    color: [f32; 4],
) {
    let (pipeline, gpu, atlas, batch) = (
        &mut render.pipeline,
        &render.gpu,
        &mut render.atlas,
        &mut render.batch,
    );
    push_glyph_impl(pipeline, gpu, atlas, batch, font, x, y, character, color);
}

fn push_glyph_to_batch(
    render: &mut RenderState,
    batch: &mut QuadBatch,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    character: char,
    color: [f32; 4],
) {
    let (pipeline, gpu, atlas) = (&mut render.pipeline, &render.gpu, &mut render.atlas);
    push_glyph_impl(pipeline, gpu, atlas, batch, font, x, y, character, color);
}

#[allow(clippy::too_many_arguments)]
fn push_glyph_impl(
    pipeline: &mut TerminalRenderPipeline,
    gpu: &GpuContext,
    atlas: &mut GlyphAtlas,
    batch: &mut QuadBatch,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    character: char,
    color: [f32; 4],
) {
    if character == ' ' || character == '\0' {
        return;
    }

    let glyph_key = walk_renderer::atlas::GlyphKey {
        font_id: 0,
        glyph_id: character as u32,
        font_size_tenths: (font.font_size * 10.0) as u32,
    };

    if let Some(glyph) = font.rasterize(character) {
        let width = glyph.width;
        let height = glyph.height;
        let data = glyph.data.clone();
        let offset_x = glyph.offset_x;
        let offset_y = glyph.offset_y;
        if let Some(region) = atlas.get_or_insert(glyph_key, width, height) {
            if width > 0 && height > 0 {
                pipeline.upload_glyph(gpu, region.x, region.y, width, height, &data);
            }
            batch.push_glyph_quad(
                x + offset_x as f32,
                y + (font.metrics.baseline - offset_y as f32),
                width as f32,
                height as f32,
                &region,
                color,
            );
        }
    }
}

fn input_event_to_editor_key(event: &InputEvent) -> Option<EditorKey> {
    match &event.action {
        KeyAction::Char(ch)
            if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
        {
            Some(EditorKey::Char(*ch))
        }
        KeyAction::Char('d') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlD)
        }
        KeyAction::Char('u') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlU)
        }
        KeyAction::Enter if event.modifiers.shift => Some(EditorKey::ShiftEnter),
        KeyAction::Enter => Some(EditorKey::Enter),
        KeyAction::Backspace => Some(EditorKey::Backspace),
        KeyAction::Delete => Some(EditorKey::Delete),
        KeyAction::Escape => Some(EditorKey::Escape),
        KeyAction::Tab if event.modifiers.shift => Some(EditorKey::ShiftTab),
        KeyAction::Tab => Some(EditorKey::Tab),
        KeyAction::ArrowLeft if event.modifiers.ctrl => Some(EditorKey::WordLeft),
        KeyAction::ArrowLeft => Some(EditorKey::Left),
        KeyAction::ArrowRight if event.modifiers.ctrl => Some(EditorKey::WordRight),
        KeyAction::ArrowRight => Some(EditorKey::Right),
        KeyAction::ArrowUp => Some(EditorKey::Up),
        KeyAction::ArrowDown => Some(EditorKey::Down),
        KeyAction::Home => Some(EditorKey::Home),
        KeyAction::End => Some(EditorKey::End),
        _ => None,
    }
}

fn input_event_to_pty_bytes(event: &InputEvent) -> Option<Vec<u8>> {
    match &event.action {
        KeyAction::Char(c) => {
            if event.modifiers.ctrl && !event.modifiers.alt {
                let b = c.to_ascii_lowercase() as u8;
                if b.is_ascii_lowercase() {
                    Some(vec![b - b'a' + 1])
                } else {
                    Some(c.to_string().into_bytes())
                }
            } else if event.modifiers.alt && !event.modifiers.ctrl {
                let mut v = vec![0x1b];
                v.extend_from_slice(c.to_string().as_bytes());
                Some(v)
            } else if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta {
                Some(c.to_string().into_bytes())
            } else {
                None
            }
        }
        KeyAction::Enter => Some(b"\r".to_vec()),
        KeyAction::Backspace => Some(b"\x7f".to_vec()),
        KeyAction::Tab => Some(b"\t".to_vec()),
        KeyAction::Escape => Some(b"\x1b".to_vec()),
        KeyAction::ArrowUp => Some(b"\x1b[A".to_vec()),
        KeyAction::ArrowDown => Some(b"\x1b[B".to_vec()),
        KeyAction::ArrowRight => Some(b"\x1b[C".to_vec()),
        KeyAction::ArrowLeft => Some(b"\x1b[D".to_vec()),
        KeyAction::Home => Some(b"\x1b[H".to_vec()),
        KeyAction::End => Some(b"\x1b[F".to_vec()),
        KeyAction::Delete => Some(b"\x1b[3~".to_vec()),
        KeyAction::PageUp => Some(b"\x1b[5~".to_vec()),
        KeyAction::PageDown => Some(b"\x1b[6~".to_vec()),
        _ => None,
    }
}

fn collect_search_lines(
    terminal: &Terminal,
    blocks: &[Block],
    pane_id: PaneId,
    tab_id: u64,
) -> Vec<SearchLine> {
    let mut lines: Vec<SearchLine> = terminal
        .state
        .text_rows()
        .into_iter()
        .map(|row| SearchLine {
            pane_id,
            tab_id,
            row: row.absolute_row,
            block_id: None,
            is_command: false,
            text: row.text,
        })
        .collect();

    for block in blocks {
        if block.command_text.is_empty() {
            continue;
        }
        lines.push(SearchLine {
            pane_id,
            tab_id,
            row: block.output_start_row,
            block_id: Some(block.id),
            is_command: true,
            text: block.command_text.clone(),
        });
    }

    lines
}

fn quick_select_rows_for_scope(
    pane: &PaneRuntime,
    scope: QuickSelectScope,
) -> Vec<(usize, String)> {
    match scope {
        QuickSelectScope::Viewport => pane
            .terminal
            .state
            .visible_rows()
            .into_iter()
            .map(|absolute_row| (absolute_row, pane.terminal.state.row_text(absolute_row)))
            .collect(),
        QuickSelectScope::SelectedBlock => pane
            .app
            .selected_or_latest_block()
            .map(|block| {
                (block.output_start_row..=block.output_end_row)
                    .map(|absolute_row| (absolute_row, pane.terminal.state.row_text(absolute_row)))
                    .collect()
            })
            .unwrap_or_default(),
    }
}

fn extract_selection_text(terminal: &Terminal, start: CellPos, end: CellPos) -> String {
    let total_rows = terminal.state.screen_lines();
    if total_rows == 0 {
        return String::new();
    }

    let max_row = total_rows.saturating_sub(1);
    let start_row = usize::from(start.row).min(max_row);
    let end_row = usize::from(end.row).min(max_row);
    let mut lines = Vec::new();

    for row in start_row..=end_row {
        let absolute_row = terminal.state.viewport_row_to_absolute(row);
        let row_start = if row == start_row {
            usize::from(start.col)
        } else {
            0
        };
        let row_end = if row == end_row {
            selection_end_col(terminal, end.col)
        } else {
            terminal.state.columns()
        };
        lines.push(terminal.state.row_slice(absolute_row, row_start, row_end));
    }

    lines.join("\n")
}

fn extract_absolute_selection_text(
    terminal: &Terminal,
    start: (usize, usize),
    end: (usize, usize),
) -> String {
    let total_rows = terminal.state.total_rows();
    if total_rows == 0 {
        return String::new();
    }

    let (start, end) = if start <= end { (start, end) } else { (end, start) };
    let start_row = start.0.min(total_rows.saturating_sub(1));
    let end_row = end.0.min(total_rows.saturating_sub(1));
    let mut lines = Vec::new();

    for row in start_row..=end_row {
        let row_text = terminal.state.row_text(row);
        let row_chars = row_text.chars().collect::<Vec<_>>();
        let row_start = if row == start_row {
            start.1.min(row_chars.len())
        } else {
            0
        };
        let row_end = if row == end_row {
            (end.1 + 1).min(row_chars.len())
        } else {
            row_chars.len()
        };
        lines.push(
            row_chars[row_start..row_end]
                .iter()
                .collect::<String>()
                .trim_end()
                .to_string(),
        );
    }

    lines.join("\n")
}

fn extract_block_text(terminal: &Terminal, block: &Block) -> String {
    let mut lines = Vec::new();

    if !block.command_text.is_empty() {
        lines.push(block.command_text.clone());
    }
    lines.extend(collect_block_output_lines(terminal, block));

    lines.join("\n")
}

fn extract_block_command_text(block: &Block) -> String {
    block.command_text.clone()
}

fn extract_block_output_text(terminal: &Terminal, block: &Block) -> String {
    collect_block_output_lines(terminal, block).join("\n")
}

fn collect_block_output_lines(terminal: &Terminal, block: &Block) -> Vec<String> {
    let total_rows = terminal.state.total_rows();
    if total_rows == 0 {
        return Vec::new();
    }

    let max_row = total_rows.saturating_sub(1);
    let start_row = block.output_start_row.min(max_row);
    let end_row = block.output_end_row.min(max_row);
    let mut lines = Vec::new();

    for row in start_row..=end_row {
        lines.push(terminal.state.row_text(row));
    }

    lines
}

fn build_visible_row_positions(visible_rows: &[usize], blocks: &[Block]) -> Vec<Option<usize>> {
    let mut hidden_rows = vec![false; visible_rows.len()];

    for block in blocks {
        if !block.is_collapsed {
            continue;
        }

        for (index, absolute_row) in visible_rows.iter().copied().enumerate() {
            if absolute_row > block.output_start_row && absolute_row <= block.output_end_row {
                hidden_rows[index] = true;
            }
        }
    }

    let mut next_visible_row = 0;
    hidden_rows
        .into_iter()
        .map(|hidden| {
            if hidden {
                None
            } else {
                let visible_row = Some(next_visible_row);
                next_visible_row += 1;
                visible_row
            }
        })
        .collect()
}

fn pane_overlay_signature(
    blocks: &[Block],
    selected_block_id: Option<u64>,
    global_search: &walk_ui::search::GlobalSearch,
    block_query: Option<&BlockQueryState>,
    pane_id: PaneId,
) -> PaneOverlaySignature {
    PaneOverlaySignature {
        selected_block_id,
        blocks: blocks
            .iter()
            .map(|block| {
                (
                    block.id,
                    block.output_start_row,
                    block.output_end_row,
                    block.exit_code,
                    block.is_collapsed,
                    block.is_bookmarked,
                )
            })
            .collect(),
        search_query: global_search.query.clone(),
        search_current: global_search.current,
        search_matches: global_search
            .matches
            .iter()
            .filter(|search_match| search_match.pane_id == pane_id)
            .map(|search_match| {
                (
                    search_match.row,
                    search_match.col_start,
                    search_match.col_end,
                    search_match.block_id,
                    search_match.is_command,
                )
            })
            .collect(),
        block_query: block_query.map(|query| BlockQueryOverlaySignature {
            mode: query.mode,
            target_block_id: query.target_block_id,
            query: query.query.clone(),
            current_match: query.current_match,
            overlay_scroll_offset: query.overlay_scroll_offset,
            matches: query
                .matches
                .iter()
                .map(|search_match| {
                    (
                        search_match.line,
                        search_match.col_start,
                        search_match.col_end,
                    )
                })
                .collect(),
        }),
    }
}

#[derive(Debug, Clone)]
struct RowLinkSpan {
    col_start: usize,
    col_end: usize,
    uri: String,
}

fn collect_row_links(terminal: &Terminal, absolute_row: usize) -> Vec<RowLinkSpan> {
    let mut links = terminal
        .state
        .explicit_links_on_row(absolute_row)
        .into_iter()
        .map(|span| RowLinkSpan {
            col_start: span.col_start,
            col_end: span.col_end,
            uri: span.link.uri.clone(),
        })
        .collect::<Vec<_>>();

    let text = terminal.state.row_text(absolute_row);
    for detected in detect_links(absolute_row, &text) {
        let overlaps_explicit = links.iter().any(|span| {
            spans_overlap(
                span.col_start,
                span.col_end,
                detected.range.col_start,
                detected.range.col_end,
            )
        });
        if overlaps_explicit {
            continue;
        }
        links.push(RowLinkSpan {
            col_start: detected.range.col_start,
            col_end: detected.range.col_end,
            uri: detected.uri,
        });
    }

    links.sort_by_key(|span| span.col_start);
    links
}

fn link_at_cell(terminal: &Terminal, absolute_row: usize, col: usize) -> Option<String> {
    if let Some(explicit) = terminal.state.explicit_link_at(absolute_row, col) {
        return Some(explicit.uri.clone());
    }

    collect_row_links(terminal, absolute_row)
        .into_iter()
        .find(|span| (span.col_start..span.col_end).contains(&col))
        .map(|span| span.uri)
}

fn spans_overlap(start_a: usize, end_a: usize, start_b: usize, end_b: usize) -> bool {
    start_a < end_b && start_b < end_a
}

fn collect_row_cells(
    terminal: &Terminal,
    absolute_row: usize,
    total_cols: usize,
) -> Vec<CellRenderData> {
    (0..total_cols)
        .map(|col_idx| terminal.state.cell_at_absolute(absolute_row, col_idx))
        .collect()
}

#[allow(clippy::too_many_arguments)]
fn rebuild_visible_row_batch(
    batch: &mut QuadBatch,
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    blocks: &[Block],
    selected_block_id: Option<u64>,
    global_search: &walk_ui::search::GlobalSearch,
    block_query: Option<&BlockQueryState>,
    pane_id: PaneId,
    terminal: &Terminal,
    absolute_row: usize,
    render_row: Option<usize>,
    total_cols: usize,
    viewport: Rect,
    cell_width: f32,
    cell_height: f32,
    terminal_surface_alpha: f32,
) {
    batch.clear();
    let Some(render_row) = render_row else {
        return;
    };

    let row_y = viewport.y + render_row as f32 * cell_height;
    let row_links = collect_row_links(terminal, absolute_row);
    for col_idx in 0..total_cols {
        let cell = terminal.state.cell_at_absolute(absolute_row, col_idx);
        let x = viewport.x + col_idx as f32 * cell_width;
        let mut bg = resolve_cell_color(&cell.bg, theme, true);
        let mut fg = resolve_cell_color(&cell.fg, theme, false);
        let is_hyperlink_cell = row_links
            .iter()
            .any(|link| (link.col_start..link.col_end).contains(&col_idx));

        if cell.is_inverse {
            std::mem::swap(&mut bg, &mut fg);
        }
        if matches!(cell.bg, CellColor::Named(idx) if idx >= 16) {
            bg[3] *= terminal_surface_alpha;
        }
        if is_hyperlink_cell {
            fg = [
                theme.hyperlink_color.r,
                theme.hyperlink_color.g,
                theme.hyperlink_color.b,
                theme.hyperlink_color.a,
            ];
        }

        batch.push_bg_quad(x, row_y, cell_width, cell_height, bg);
        if let Some(current_match) =
            search_match_at_cell(global_search, pane_id, absolute_row, col_idx as u16)
        {
            let highlight = if current_match {
                theme.highlight_current_match
            } else {
                theme.highlight_match
            };
            batch.push_bg_quad(
                x,
                row_y,
                cell_width,
                cell_height,
                [highlight.r, highlight.g, highlight.b, highlight.a],
            );
        }
        if let Some(current_match) =
            block_query_match_at_cell(block_query, blocks, absolute_row, col_idx as u16)
        {
            let highlight = if current_match {
                theme.highlight_current_match
            } else {
                theme.highlight_match
            };
            batch.push_bg_quad(
                x,
                row_y,
                cell_width,
                cell_height,
                [highlight.r, highlight.g, highlight.b, highlight.a * 0.9],
            );
        }
        if let Some(trigger_color) = trigger_highlight_color_at_cell(blocks, absolute_row, col_idx)
        {
            batch.push_bg_quad(
                x,
                row_y,
                cell_width,
                cell_height,
                [trigger_color[0], trigger_color[1], trigger_color[2], 0.36],
            );
        }

        if cell.character != ' ' && cell.character != '\0' {
            push_glyph_to_batch(render, batch, font, x, row_y, cell.character, fg);
        }
        if is_hyperlink_cell {
            batch.push_bg_quad(
                x,
                row_y + cell_height - 1.5,
                cell_width,
                1.0,
                [
                    theme.hyperlink_color.r,
                    theme.hyperlink_color.g,
                    theme.hyperlink_color.b,
                    0.9,
                ],
            );
        }
    }

    if let Some(block) = blocks.iter().find(|block| {
        absolute_row >= block.output_start_row && absolute_row <= block.output_end_row
    }) {
        let accent = if block.exit_code.unwrap_or(0) == 0 {
            theme.block_success_accent
        } else {
            theme.block_error_accent
        };

        if absolute_row == block.output_start_row {
            batch.push_bg_quad(
                viewport.x,
                row_y,
                viewport.w,
                1.0,
                [
                    theme.block_separator.r,
                    theme.block_separator.g,
                    theme.block_separator.b,
                    0.65,
                ],
            );
        }

        batch.push_bg_quad(
            viewport.x,
            row_y,
            4.0,
            cell_height,
            [accent.r, accent.g, accent.b, 0.9],
        );

        if block.is_bookmarked {
            batch.push_bg_quad(
                viewport.x + 4.0,
                row_y,
                3.0,
                cell_height,
                [
                    theme.highlight_current_match.r,
                    theme.highlight_current_match.g,
                    theme.highlight_current_match.b,
                    0.9,
                ],
            );
        }

        if selected_block_id == Some(block.id) {
            batch.push_bg_quad(
                viewport.x,
                row_y,
                viewport.w,
                cell_height,
                [
                    theme.selection.r,
                    theme.selection.g,
                    theme.selection.b,
                    0.12,
                ],
            );
        }

        if absolute_row == block.output_start_row {
            if let Some(current_match) =
                search_match_for_block_command(global_search, pane_id, block.id)
            {
                let highlight = if current_match {
                    theme.highlight_current_match
                } else {
                    theme.highlight_match
                };
                batch.push_bg_quad(
                    viewport.x + 4.0,
                    row_y,
                    viewport.w - 4.0,
                    cell_height,
                    [highlight.r, highlight.g, highlight.b, highlight.a],
                );
            }

            if block.is_collapsed {
                batch.push_bg_quad(
                    viewport.x + 4.0,
                    row_y,
                    viewport.w - 4.0,
                    cell_height,
                    [
                        theme.block_separator.r,
                        theme.block_separator.g,
                        theme.block_separator.b,
                        0.25,
                    ],
                );
            }
        }
    }
}

fn selection_end_col(terminal: &Terminal, end_col: u16) -> usize {
    if end_col == u16::MAX {
        terminal.state.columns()
    } else {
        (usize::from(end_col) + 1).min(terminal.state.columns())
    }
}

/// Resolve a CellColor to [r, g, b, a] using the Walk theme.
fn resolve_cell_color(color: &CellColor, theme: &Theme, is_bg: bool) -> [f32; 4] {
    match color {
        CellColor::Named(idx) => {
            let i = *idx as usize;
            if i < 16 {
                let c = &theme.ansi_colors[i];
                [c.r, c.g, c.b, c.a]
            } else if is_bg {
                [
                    theme.background.r,
                    theme.background.g,
                    theme.background.b,
                    theme.background.a,
                ]
            } else {
                [
                    theme.foreground.r,
                    theme.foreground.g,
                    theme.foreground.b,
                    theme.foreground.a,
                ]
            }
        }
        CellColor::Rgb(r, g, b) => [
            f32::from(*r) / 255.0,
            f32::from(*g) / 255.0,
            f32::from(*b) / 255.0,
            1.0,
        ],
        CellColor::Indexed(idx) => {
            let i = *idx as usize;
            if i < 16 {
                let c = &theme.ansi_colors[i];
                [c.r, c.g, c.b, c.a]
            } else if i < 232 {
                let i = i - 16;
                let r = (i / 36) as f32 / 5.0;
                let g = ((i / 6) % 6) as f32 / 5.0;
                let b = (i % 6) as f32 / 5.0;
                [r, g, b, 1.0]
            } else {
                let gray = (i - 232) as f32 / 23.0;
                [gray, gray, gray, 1.0]
            }
        }
    }
}

fn trigger_engine_from_config(config: &WalkConfig) -> TriggerEngine {
    let mut engine = TriggerEngine::new();
    for trigger in &config.triggers {
        match trigger_from_descriptor(
            trigger.name.clone(),
            trigger.pattern.clone(),
            trigger.actions.clone(),
        ) {
            Ok(mut parsed) => {
                parsed.scope = trigger_scope_from_config(trigger.scope);
                engine.add_trigger(parsed);
            }
            Err(error) => {
                warn!("failed to load trigger '{}': {error}", trigger.name);
            }
        }
    }
    engine
}

fn trigger_scope_from_config(scope: TriggerScopeConfig) -> TriggerScope {
    match scope {
        TriggerScopeConfig::Output => TriggerScope::Output,
        TriggerScopeConfig::Command => TriggerScope::Command,
        TriggerScopeConfig::Both => TriggerScope::Both,
    }
}

fn trigger_from_descriptor(
    name: String,
    pattern: String,
    actions: Vec<String>,
) -> Result<Trigger, regex::Error> {
    let pattern = Regex::new(&pattern)?;
    let actions = actions
        .iter()
        .filter_map(|descriptor| parse_trigger_action_descriptor(descriptor))
        .collect::<Vec<_>>();
    Ok(Trigger {
        name,
        pattern,
        actions,
        scope: TriggerScope::Output,
    })
}

fn parse_trigger_action_descriptor(descriptor: &str) -> Option<TriggerAction> {
    let trimmed = descriptor.trim();
    if trimmed.is_empty() {
        return None;
    }

    let lower = trimmed.to_ascii_lowercase();
    match lower.as_str() {
        "bookmark" | "bookmark_block" => Some(TriggerAction::BookmarkBlock),
        "open_url" | "open" => Some(TriggerAction::OpenUrl),
        "copy_match" | "copy" => Some(TriggerAction::CopyMatch),
        "highlight_red" => Some(TriggerAction::Highlight {
            color: "#ff4d4f".to_string(),
        }),
        "highlight_green" => Some(TriggerAction::Highlight {
            color: "#4caf50".to_string(),
        }),
        "highlight_yellow" => Some(TriggerAction::Highlight {
            color: "#ffcc00".to_string(),
        }),
        _ => {
            if let Some(color) = lower.strip_prefix("highlight_") {
                return Some(TriggerAction::Highlight {
                    color: normalize_trigger_color(color),
                });
            }
            if lower == "highlight" {
                return Some(TriggerAction::Highlight {
                    color: "#ff4d4f".to_string(),
                });
            }
            if let Some(message) = trimmed.strip_prefix("notify:") {
                return Some(TriggerAction::Notify {
                    message: message.trim().to_string(),
                });
            }
            if lower == "notify" {
                return Some(TriggerAction::Notify {
                    message: String::new(),
                });
            }
            if let Some(hook) = trimmed
                .strip_prefix("lua_hook:")
                .or_else(|| trimmed.strip_prefix("lua:"))
            {
                return Some(TriggerAction::LuaHook {
                    hook_name: hook.trim().to_string(),
                });
            }
            None
        }
    }
}

fn normalize_trigger_color(color: &str) -> String {
    let normalized = color.trim();
    if normalized.is_empty() {
        return "#ff4d4f".to_string();
    }
    if normalized.starts_with('#') {
        return normalized.to_string();
    }

    match normalized.to_ascii_lowercase().as_str() {
        "red" => "#ff4d4f".to_string(),
        "green" => "#4caf50".to_string(),
        "blue" => "#4f83ff".to_string(),
        "yellow" => "#ffcc00".to_string(),
        "magenta" => "#d85bd8".to_string(),
        "cyan" => "#33c9dc".to_string(),
        _ => "#ff4d4f".to_string(),
    }
}

fn char_span_for_single_line(text: &str, byte_range: (usize, usize)) -> Option<(usize, usize)> {
    let len = text.len();
    let start = byte_range.0.min(len);
    let end = byte_range.1.min(len);
    if end <= start {
        return None;
    }
    Some((text[..start].chars().count(), text[..end].chars().count()))
}

fn trigger_highlights_for_output_range(
    lines: &[String],
    output_start_row: usize,
    byte_range: (usize, usize),
    color: &str,
) -> Vec<TriggerHighlight> {
    let mut highlights = Vec::new();
    let mut cursor = 0usize;
    let normalized_color = normalize_trigger_color(color);

    for (line_idx, line) in lines.iter().enumerate() {
        let line_start = cursor;
        let line_end = line_start + line.len();
        let overlap_start = byte_range.0.max(line_start);
        let overlap_end = byte_range.1.min(line_end);

        if overlap_start < overlap_end {
            let local_start = overlap_start - line_start;
            let local_end = overlap_end - line_start;
            let col_start = line[..local_start].chars().count();
            let col_end = line[..local_end].chars().count();
            highlights.push(TriggerHighlight {
                absolute_row: output_start_row + line_idx,
                col_start,
                col_end,
                color: normalized_color.clone(),
            });
        }

        cursor = line_end.saturating_add(1);
    }

    highlights
}

fn trigger_highlight_color_at_cell(
    blocks: &[Block],
    absolute_row: usize,
    col: usize,
) -> Option<[f32; 4]> {
    for block in blocks {
        for highlight in &block.trigger_highlights {
            if highlight.absolute_row == absolute_row
                && (highlight.col_start..highlight.col_end).contains(&col)
            {
                let parsed = walk_ui::theme_loader::parse_hex_color(&highlight.color).ok()?;
                return Some([parsed.r, parsed.g, parsed.b, parsed.a]);
            }
        }
    }
    None
}

fn parse_shell_type(value: &str) -> ShellType {
    if let Some(distro) = value.strip_prefix("wsl:") {
        return ShellType::Wsl(distro.to_string());
    }

    match value {
        "zsh" => ShellType::Zsh,
        "fish" => ShellType::Fish,
        "powershell" => ShellType::PowerShell,
        _ => ShellType::Bash,
    }
}

fn parse_lua_action(action: &str) -> Option<Action> {
    if let Some(name) = action.strip_prefix("save_session:") {
        return (!name.trim().is_empty()).then(|| Action::SaveSession(name.trim().to_string()));
    }
    if let Some(name) = action.strip_prefix("load_session:") {
        return (!name.trim().is_empty()).then(|| Action::LoadSession(name.trim().to_string()));
    }

    match action {
        "new_tab" => Some(Action::NewTab),
        "close_tab" => Some(Action::CloseTab),
        "next_tab" => Some(Action::NextTab),
        "prev_tab" => Some(Action::PrevTab),
        "split_vertical" => Some(Action::SplitVertical),
        "split_horizontal" => Some(Action::SplitHorizontal),
        "close_split" | "close_pane" => Some(Action::CloseSplit),
        "focus_left" => Some(Action::FocusLeft),
        "focus_right" => Some(Action::FocusRight),
        "focus_up" => Some(Action::FocusUp),
        "focus_down" => Some(Action::FocusDown),
        "search_global" | "toggle_search" | "search" => Some(Action::SearchGlobal),
        "enter_vi_mode" | "vi_mode" => Some(Action::EnterViMode),
        "command_palette" | "palette" => Some(Action::CommandPalette),
        "command_search" | "history_search" => Some(Action::CommandSearch),
        "quick_select" => Some(Action::QuickSelect),
        "quick_select_block" => Some(Action::QuickSelectBlock),
        "toggle_broadcast" | "broadcast_toggle" => Some(Action::ToggleBroadcast),
        "block_prev" => Some(Action::BlockPrev),
        "block_next" => Some(Action::BlockNext),
        "block_copy" | "copy_block" => Some(Action::BlockCopy),
        "block_copy_command" | "copy_block_command" => Some(Action::BlockCopyCommand),
        "block_copy_output" | "copy_block_output" => Some(Action::BlockCopyOutput),
        "block_collapse" | "collapse_block" => Some(Action::BlockCollapse),
        "block_toggle_bookmark" | "toggle_block_bookmark" => Some(Action::BlockToggleBookmark),
        "block_prev_bookmark" => Some(Action::BlockPrevBookmark),
        "block_next_bookmark" => Some(Action::BlockNextBookmark),
        "block_find" | "block_search" | "search_in_block" | "find_in_block" => {
            Some(Action::BlockFind)
        }
        "block_filter" | "filter_block" => Some(Action::BlockFilter),
        "block_rerun" | "rerun_block" => Some(Action::BlockRerun),
        "zoom_in" => Some(Action::ZoomIn),
        "zoom_out" => Some(Action::ZoomOut),
        "zoom_reset" => Some(Action::ZoomReset),
        "clear_screen" => Some(Action::ClearScreen),
        "send_eof" => Some(Action::SendEof),
        _ => None,
    }
}

#[cfg(test)]
fn parse_lua_key_combo(key: &str) -> Option<walk_app::keybindings::KeyCombo> {
    let mut modifiers = walk_app::input::Modifiers::default();
    let mut key_action = None;

    for part in key.split('+') {
        match part.trim().to_ascii_lowercase().as_str() {
            "ctrl" => modifiers.ctrl = true,
            "alt" => modifiers.alt = true,
            "shift" => modifiers.shift = true,
            "cmd" | "meta" => modifiers.meta = true,
            "left" => key_action = Some(KeyAction::ArrowLeft),
            "right" => key_action = Some(KeyAction::ArrowRight),
            "up" => key_action = Some(KeyAction::ArrowUp),
            "down" => key_action = Some(KeyAction::ArrowDown),
            "enter" => key_action = Some(KeyAction::Enter),
            "tab" => key_action = Some(KeyAction::Tab),
            "escape" | "esc" => key_action = Some(KeyAction::Escape),
            "backspace" => key_action = Some(KeyAction::Backspace),
            "delete" => key_action = Some(KeyAction::Delete),
            "home" => key_action = Some(KeyAction::Home),
            "end" => key_action = Some(KeyAction::End),
            value if value.len() == 1 => {
                key_action = value.chars().next().map(KeyAction::Char);
            }
            _ => {}
        }
    }

    key_action.map(|key| walk_app::keybindings::KeyCombo { key, modifiers })
}

fn parse_palette_action(action: &str) -> Option<Action> {
    let normalized = action.trim().replace(' ', "_").to_ascii_lowercase();
    if let Some(index) = normalized.strip_prefix("switch_to_tab_") {
        return index
            .parse::<u8>()
            .ok()
            .filter(|value| *value > 0)
            .map(Action::SwitchToTab);
    }
    parse_lua_action(&normalized)
}

fn action_to_palette_id(action: &Action) -> Option<String> {
    let id = match action {
        Action::NewTab => "new_tab".to_string(),
        Action::CloseTab => "close_tab".to_string(),
        Action::NextTab => "next_tab".to_string(),
        Action::PrevTab => "prev_tab".to_string(),
        Action::SwitchToTab(index) => format!("switch_to_tab_{index}"),
        Action::SplitVertical => "split_vertical".to_string(),
        Action::SplitHorizontal => "split_horizontal".to_string(),
        Action::CloseSplit => "close_split".to_string(),
        Action::FocusLeft => "focus_left".to_string(),
        Action::FocusRight => "focus_right".to_string(),
        Action::FocusUp => "focus_up".to_string(),
        Action::FocusDown => "focus_down".to_string(),
        Action::ResizeSplitLeft => "resize_split_left".to_string(),
        Action::ResizeSplitRight => "resize_split_right".to_string(),
        Action::ResizeSplitUp => "resize_split_up".to_string(),
        Action::ResizeSplitDown => "resize_split_down".to_string(),
        Action::Copy => "copy".to_string(),
        Action::Paste => "paste".to_string(),
        Action::SelectAll => "select_all".to_string(),
        Action::ScrollUp => "scroll_up".to_string(),
        Action::ScrollDown => "scroll_down".to_string(),
        Action::ScrollPageUp => "scroll_page_up".to_string(),
        Action::ScrollPageDown => "scroll_page_down".to_string(),
        Action::ScrollToTop => "scroll_to_top".to_string(),
        Action::ScrollToBottom => "scroll_to_bottom".to_string(),
        Action::BlockPrev => "block_prev".to_string(),
        Action::BlockNext => "block_next".to_string(),
        Action::BlockCopy => "block_copy".to_string(),
        Action::BlockCopyCommand => "block_copy_command".to_string(),
        Action::BlockCopyOutput => "block_copy_output".to_string(),
        Action::BlockCollapse => "block_collapse".to_string(),
        Action::BlockToggleBookmark => "block_toggle_bookmark".to_string(),
        Action::BlockPrevBookmark => "block_prev_bookmark".to_string(),
        Action::BlockNextBookmark => "block_next_bookmark".to_string(),
        Action::BlockFind => "block_find".to_string(),
        Action::BlockFilter => "block_filter".to_string(),
        Action::BlockRerun => "block_rerun".to_string(),
        Action::SearchGlobal => "search_global".to_string(),
        Action::EnterViMode => "enter_vi_mode".to_string(),
        Action::CommandPalette => "command_palette".to_string(),
        Action::CommandSearch => "command_search".to_string(),
        Action::QuickSelect => "quick_select".to_string(),
        Action::QuickSelectBlock => "quick_select_block".to_string(),
        Action::ToggleBroadcast => "toggle_broadcast".to_string(),
        Action::ToggleInputPosition => "toggle_input_position".to_string(),
        Action::ZoomIn => "zoom_in".to_string(),
        Action::ZoomOut => "zoom_out".to_string(),
        Action::ZoomReset => "zoom_reset".to_string(),
        Action::ClearScreen => "clear_screen".to_string(),
        Action::SendEof => "send_eof".to_string(),
        Action::SaveSession(name) => format!("save_session:{name}"),
        Action::LoadSession(name) => format!("load_session:{name}"),
    };
    Some(id)
}

fn action_display_label(action: &Action) -> String {
    match action {
        Action::SwitchToTab(index) => format!("Switch To Tab {index}"),
        Action::SaveSession(name) => format!("Save Session ({name})"),
        Action::LoadSession(name) => format!("Load Session ({name})"),
        _ => action_to_palette_id(action)
            .unwrap_or_default()
            .replace('_', " ")
            .split_whitespace()
            .map(|token| {
                let mut chars = token.chars();
                match chars.next() {
                    Some(first) => first.to_ascii_uppercase().to_string() + chars.as_str(),
                    None => String::new(),
                }
            })
            .collect::<Vec<_>>()
            .join(" "),
    }
}

fn key_combo_label(combo: &walk_app::keybindings::KeyCombo) -> String {
    let mut parts = Vec::new();
    if combo.modifiers.ctrl {
        parts.push("Ctrl".to_string());
    }
    if combo.modifiers.alt {
        parts.push("Alt".to_string());
    }
    if combo.modifiers.shift {
        parts.push("Shift".to_string());
    }
    if combo.modifiers.meta {
        parts.push("Cmd".to_string());
    }
    parts.push(key_action_label(&combo.key));
    parts.join("+")
}

fn key_action_label(action: &KeyAction) -> String {
    match action {
        KeyAction::Char(ch) => ch.to_ascii_uppercase().to_string(),
        KeyAction::Enter => "Enter".to_string(),
        KeyAction::Tab => "Tab".to_string(),
        KeyAction::Backspace => "Backspace".to_string(),
        KeyAction::Delete => "Delete".to_string(),
        KeyAction::Escape => "Escape".to_string(),
        KeyAction::ArrowUp => "Up".to_string(),
        KeyAction::ArrowDown => "Down".to_string(),
        KeyAction::ArrowLeft => "Left".to_string(),
        KeyAction::ArrowRight => "Right".to_string(),
        KeyAction::Home => "Home".to_string(),
        KeyAction::End => "End".to_string(),
        KeyAction::PageUp => "PageUp".to_string(),
        KeyAction::PageDown => "PageDown".to_string(),
        KeyAction::FunctionKey(index) => format!("F{index}"),
        KeyAction::Copy => "Copy".to_string(),
        KeyAction::Paste => "Paste".to_string(),
        KeyAction::Cut => "Cut".to_string(),
        KeyAction::SelectAll => "SelectAll".to_string(),
        KeyAction::Undo => "Undo".to_string(),
        KeyAction::Redo => "Redo".to_string(),
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    // Set up panic handler
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        eprintln!("Walk panicked: {info}");
        default_hook(info);
    }));

    // Initialize logging
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "warn".into()),
        )
        .init();

    let cli = Cli::parse();

    info!("starting Walk terminal");

    let mut config = WalkConfig::load();

    // Apply CLI overrides
    if let Some(shell) = cli.shell {
        config.shell = parse_shell_type(&shell);
    }

    if let Some(ref dir) = cli.working_dir {
        std::env::set_current_dir(dir)?;
    }

    let window_config = WindowConfig {
        title: cli.title,
        opacity: config.window_opacity,
        transparent: config.window_opacity < 1.0,
        ..WindowConfig::default()
    };
    let handler = WalkHandler::new(config);

    run_event_loop(window_config, handler)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_lua_action_supports_aliases() {
        assert_eq!(parse_lua_action("close_pane"), Some(Action::CloseSplit));
        assert_eq!(
            parse_lua_action("toggle_search"),
            Some(Action::SearchGlobal)
        );
        assert_eq!(parse_lua_action("copy_block"), Some(Action::BlockCopy));
    }

    #[test]
    fn test_parse_lua_action_supports_named_sessions() {
        assert_eq!(
            parse_lua_action("save_session:demo"),
            Some(Action::SaveSession("demo".to_string()))
        );
        assert_eq!(
            parse_lua_action("load_session:demo"),
            Some(Action::LoadSession("demo".to_string()))
        );
        assert_eq!(parse_lua_action("save_session:"), None);
    }

    #[test]
    fn test_parse_lua_key_combo_supports_modifiers_and_named_keys() {
        let combo = parse_lua_key_combo("ctrl+shift+up").expect("combo should parse");
        assert_eq!(combo.key, KeyAction::ArrowUp);
        assert!(combo.modifiers.ctrl);
        assert!(combo.modifiers.shift);
        assert!(!combo.modifiers.alt);
    }
}
