//! Wok terminal emulator entry point.

use std::collections::HashMap;
use std::collections::HashSet;
use std::collections::VecDeque;
use std::error::Error;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

use clap::{Parser, Subcommand};
use regex::Regex;
use serde::Serialize;
use serde_json::{json, Value};
use tracing::{info, warn};
use winit::dpi::{PhysicalPosition, PhysicalSize};
use winit::event::MouseButton;
use winit::window::Window;
use wok_app::action_effects::{
    ActionEffects, ClipboardEffect, OverlayEffect, RuntimeEffect, ViewportEffect, WorkspaceEffect,
};
use wok_app::app::{InputMode, WokApp};
use wok_app::block_query::{BlockQueryMode, BlockQueryState};
use wok_app::command_search::{CommandSearchScope, CommandSearchState};
use wok_app::config::{TriggerScopeConfig, WokConfig};
use wok_app::event_loop::run_event_loop;
use wok_app::handler::AppHandler;
use wok_app::input::{InputEvent, InputEventType, KeyAction};
use wok_app::keybindings::Action;
use wok_app::plugin_host::PluginHost;
use wok_app::remote_control::{
    error_response, result_response, RemoteControlServer, RemoteRequest,
};
use wok_app::scripting::{
    QuickSelectPatternRequest, StatusBarRequest, ThemeRequest, TriggerRequest, WorkflowRequest,
};
use wok_app::session::{
    block_from_state, block_to_state, default_session_path, history_entry_from_state,
    history_entry_to_state, load_session, named_session_path, save_session, split_node_from_state,
    split_node_to_state, FloatingPaneState, PaneState, WorkspaceSessionState, WorkspaceTabState,
};
use wok_app::window::WindowConfig;
use wok_app::workspace::{FloatingPane, FocusDirection, PaneId, WorkspaceState, WorkspaceTab};
use wok_blocks::block::{Block, OutputLineEvent};
use wok_blocks::triggers::{
    Trigger, TriggerAction, TriggerEngine, TriggerHighlight, TriggerMatch, TriggerScope,
};
use wok_input::editor::EditorAction;
use wok_input::history::{prefix_matches, CommandHistory, HistoryEntry};
use wok_input::workflows::WorkflowStore;
use wok_renderer::atlas::GlyphAtlas;
use wok_renderer::damage::DirtyRegion;
use wok_renderer::font::FontSystem;
use wok_renderer::gpu::GpuContext;
use wok_renderer::inline_images::{ImagePlacement, InlineImageStore};
use wok_renderer::pipeline::CursorShape;
use wok_renderer::pipeline::QuadBatch;
use wok_renderer::render_pipeline::TerminalRenderPipeline;
use wok_terminal::replay::{ReplaySnapshot, ReplayStore};
use wok_terminal::shell::ShellType;
use wok_terminal::state::{CellColor, CellRenderData};
use wok_terminal::terminal::SemanticEvent;
use wok_terminal::terminal::Terminal;
use wok_ui::background::BackgroundRenderer;
use wok_ui::command_palette::{CommandPaletteState, PaletteAction, PaletteCategory, PaletteEntry};
use wok_ui::layout::Rect;
use wok_ui::layout_presets::{
    append_panes_to_last_leaf, build_tree_for_panes, default_layout_presets, leaf_count,
    LayoutPreset,
};
use wok_ui::links::detect_links;
use wok_ui::quick_select::{PatternRegistry, QuickSelectScope};
use wok_ui::replay_overlay::ReplayTimeline;
use wok_ui::search::SearchLine;
use wok_ui::selection::{CellPos, SelectionState};
use wok_ui::splits::SplitManager;
use wok_ui::status_bar::{StatusBarState, StatusSegment};
use wok_ui::theme::Theme;
use wok_ui::theme_watcher::ThemeWatcher;
use wok_ui::vi_mode::{ViModeState, ViPending, ViSubMode};
use wok_ui::viewport::ViewportRenderer;

mod action_parser;
mod cli_runtime;
mod input_codec;
mod jsonrpc_params;
mod remote_runtime;
mod render_runtime;
mod rpc_cli;
mod setup_ops;
mod workspace_runtime;

use action_parser::parse_lua_action;
use cli_runtime::{dispatch_cli_command, parse_shell_type, CliAction};
use input_codec::{input_event_to_editor_key, input_event_to_pty_bytes};
use render_runtime::*;

/// Wok — a GPU-accelerated terminal emulator with Blocks.
#[derive(Parser, Debug)]
#[command(name = "wok", version, about)]
struct Cli {
    /// Start a headless daemon session.
    #[arg(long)]
    daemon: Option<String>,

    /// Session command.
    #[command(subcommand)]
    command: Option<CliCommand>,

    /// Override the default shell.
    #[arg(long)]
    shell: Option<String>,

    /// Window title.
    #[arg(long, default_value = "Wok")]
    title: String,

    /// Initial working directory.
    #[arg(long)]
    working_dir: Option<String>,
}

#[derive(Subcommand, Debug, Clone)]
enum CliCommand {
    /// Initialize managed local Wok files in the config directory.
    Init {
        /// Overwrite existing managed files.
        #[arg(long, default_value_t = false)]
        overwrite: bool,
    },
    /// Run local diagnostics for config and shell integration state.
    Doctor {
        /// Emit machine-readable JSON.
        #[arg(long, default_value_t = false)]
        json: bool,
    },
    /// Reset managed local Wok files in the config directory.
    Reset {
        /// Also remove session/workflow/theme state directories.
        #[arg(long, default_value_t = false)]
        all: bool,
        /// Confirm reset without interactive prompt.
        #[arg(long, default_value_t = false)]
        yes: bool,
    },
    /// Manage shell startup wiring for Wok integration scripts.
    Shell {
        #[command(subcommand)]
        command: ShellCommand,
    },
    /// Attach to a running named session.
    Attach {
        /// Session name.
        name: String,
    },
    /// Detach from a running named session.
    Detach {
        /// Session name.
        name: String,
    },
    /// List running daemon sessions.
    List,
    /// Terminate a running named session daemon.
    Kill {
        /// Session name.
        name: String,
    },
    /// Send one JSON-RPC request to a running Wok instance.
    Rpc {
        /// JSON-RPC method name (for example: wok.get_panes).
        method: String,
        /// JSON value for request params (object or array).
        #[arg(long, default_value = "null")]
        params: String,
        /// Explicit remote-control socket path. Defaults to $WOK_SOCKET.
        #[arg(long)]
        socket: Option<String>,
        /// Optional JSON-RPC id value. Parsed as JSON, fallback to string.
        #[arg(long)]
        id: Option<String>,
        /// Send as notification (no id, no response expected).
        #[arg(long, default_value_t = false)]
        notify: bool,
    },
}

#[derive(Subcommand, Debug, Clone)]
enum ShellCommand {
    /// Install shell startup wiring with backup support.
    Install {
        /// Target shell: auto, bash, zsh, or fish.
        #[arg(long)]
        shell: Option<String>,
        /// Overwrite managed Wok integration scripts before wiring startup files.
        #[arg(long, default_value_t = false)]
        overwrite: bool,
    },
    /// Roll back the most recent `wok shell install`.
    Rollback {
        /// Confirm rollback without interactive prompt.
        #[arg(long, default_value_t = false)]
        yes: bool,
    },
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

#[derive(Debug, Clone)]
struct ReplayModeState {
    snapshot_index: usize,
}

struct PaneRuntime {
    app: WokApp,
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
    replay_store: ReplayStore,
    replay_mode: Option<ReplayModeState>,
    pending_replay_block_marker: bool,
    daemon_last_synced_row: Option<usize>,
    inline_images: InlineImageStore,
    last_output_line_row: Option<usize>,
}

const ATTACHED_DAEMON_PANE_ID: u64 = 0;

fn attached_mode_blocks_workspace_effect(effect: &WorkspaceEffect) -> bool {
    matches!(
        effect,
        WorkspaceEffect::SaveSession(_) | WorkspaceEffect::LoadSession(_)
    )
}

#[derive(Clone, Default)]
struct StatusBarSegments {
    left: Vec<StatusSegment>,
    center: Vec<StatusSegment>,
    right: Vec<StatusSegment>,
}

#[derive(Clone, Copy)]
enum FloatingDragMode {
    Move,
    Resize,
}

#[derive(Clone, Copy)]
struct FloatingDragState {
    pane_id: PaneId,
    mode: FloatingDragMode,
    last_x: f64,
    last_y: f64,
}

#[derive(Default)]
#[allow(dead_code)]
struct RuntimeMetrics {
    frame_count: u64,
    last_frame_duration_us: u64,
    pane_count: usize,
    replay_snapshot_count: usize,
    daemon_sync_lag_ms: Option<u64>,
}

impl RuntimeMetrics {
    fn summary_line(&self) -> String {
        let mut parts = vec![
            format!("frames:{}", self.frame_count),
            format!("panes:{}", self.pane_count),
            format!("replays:{}", self.replay_snapshot_count),
        ];
        if let Some(lag) = self.daemon_sync_lag_ms {
            parts.push(format!("sync_lag:{}ms", lag));
        }
        parts.join(" ")
    }
}

/// Wok application handler.
struct WokHandler {
    config: WokConfig,
    trigger_engine: TriggerEngine,
    pattern_registry: PatternRegistry,
    workflow_store: WorkflowStore,
    layout_presets: Vec<LayoutPreset>,
    layout_index: usize,
    workspace: WorkspaceState,
    panes: HashMap<PaneId, PaneRuntime>,
    pending_pane_restore: HashMap<PaneId, PaneState>,
    global_history: CommandHistory,
    plugins: Option<PluginHost>,
    remote_control: Option<RemoteControlServer>,
    remote_socket_path: Option<PathBuf>,
    attached_session: Option<String>,
    daemon_pane_by_local: HashMap<PaneId, u64>,
    status_message: Option<String>,
    status_bar_state: StatusBarState,
    status_bar_refresh_interval: Duration,
    last_status_bar_refresh: Instant,
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
    floating_drag: Option<FloatingDragState>,
    metrics: RuntimeMetrics,
}

impl WokHandler {
    fn new(config: WokConfig) -> Self {
        let font = FontSystem::new(&config.font_family, config.font_size);
        let (workspace, _) = WorkspaceState::new("Wok");
        let plugins = PluginHost::new(&WokConfig::config_dir());
        let trigger_engine = trigger_engine_from_config(&config);
        let pattern_registry = PatternRegistry::new();
        let mut workflow_store = WorkflowStore::new();
        workflow_store.load_from_dir(&WokConfig::config_dir().join("workflows"));
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
        let mut layout_presets = default_layout_presets();
        layout_presets.extend(config.layout_presets.clone());
        let (remote_control, remote_socket_path) = match RemoteControlServer::bind_default() {
            Ok(server) => {
                let path = server.socket_path().to_path_buf();
                std::env::set_var("WOK_SOCKET", &path);
                (Some(server), Some(path))
            }
            Err(error) => {
                warn!("failed to initialize remote control socket: {error}");
                (None, None)
            }
        };

        let handler = Self {
            config,
            trigger_engine,
            pattern_registry,
            workflow_store,
            layout_presets,
            layout_index: 0,
            workspace,
            panes: HashMap::new(),
            pending_pane_restore: HashMap::new(),
            global_history,
            plugins,
            remote_control,
            remote_socket_path,
            attached_session: None,
            daemon_pane_by_local: HashMap::new(),
            status_message: None,
            status_bar_state: StatusBarState::default(),
            status_bar_refresh_interval: Duration::from_secs(5),
            last_status_bar_refresh: Instant::now(),
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
            floating_drag: None,
            metrics: RuntimeMetrics::default(),
        };
        handler.refresh_plugin_config();
        handler.refresh_plugin_snapshot();
        handler
    }

    fn active_pane_id(&self) -> Option<PaneId> {
        self.workspace.active_pane_id()
    }

    fn attached_daemon_pane_id(&self, local_pane_id: PaneId) -> u64 {
        self.daemon_pane_by_local
            .get(&local_pane_id)
            .copied()
            .unwrap_or(ATTACHED_DAEMON_PANE_ID)
    }

    fn active_pane(&self) -> Option<&PaneRuntime> {
        self.active_pane_id()
            .and_then(|pane_id| self.panes.get(&pane_id))
    }

    fn active_pane_mut(&mut self) -> Option<&mut PaneRuntime> {
        let pane_id = self.active_pane_id()?;
        self.panes.get_mut(&pane_id)
    }

    fn compose_status_bar_segments(&self, pane: &PaneRuntime) -> StatusBarSegments {
        let mut state = self.status_bar_state.clone();
        state.shell = pane.app.config.shell.to_string();
        state.cwd = pane
            .app
            .block_manager
            .blocks
            .last()
            .map(|block| block.cwd.clone())
            .filter(|cwd| !cwd.as_os_str().is_empty())
            .unwrap_or_else(|| PathBuf::from("~"));
        state.git_branch = pane.app.block_manager.blocks.last().and_then(|block| {
            block
                .git_branch
                .clone()
                .or_else(|| wok_ui::status_bar::detect_git_branch(&state.cwd))
        });

        let mut left = vec![
            StatusSegment::plain(state.cwd.display().to_string()),
            StatusSegment::plain(state.shell.clone()),
        ];
        if let Some(branch) = state.git_branch.as_ref() {
            left.push(StatusSegment::plain(format!("git:{branch}")));
        }
        left.extend(state.custom_left.clone());

        let mut center = Vec::new();
        if self.workspace.broadcast_input {
            center.push(StatusSegment {
                text: "BROADCAST".to_string(),
                fg: Some("#ffd166".to_string()),
                bg: None,
                bold: true,
            });
        }
        if let Some(replay) = pane.replay_mode.as_ref().and_then(|replay| {
            pane.replay_store
                .snapshot(replay.snapshot_index)
                .map(|snapshot| format_replay_age(snapshot.timestamp.elapsed()))
        }) {
            center.push(StatusSegment {
                text: format!("REPLAY {replay}"),
                fg: Some("#f3c969".to_string()),
                bg: None,
                bold: true,
            });
        }
        if let Some(mode) = pane.app.vi_mode.as_ref().map(ViModeState::mode_label) {
            center.push(StatusSegment::plain(mode));
        }
        if let Some(message) = self.hovered_link.as_ref().or(self.status_message.as_ref()) {
            center.push(StatusSegment::plain(message.clone()));
        }
        center.extend(state.custom_center.clone());

        let mut right = state.custom_right.clone();
        let zoom_percent = (pane.app.zoom.current_size() / self.config.font_size * 100.0).round();
        right.push(StatusSegment::plain(format!(
            "Zoom {}%",
            zoom_percent as i32
        )));

        StatusBarSegments {
            left,
            center,
            right,
        }
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
        let mut app = WokApp::new(pane_config.clone());
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
        let mut env = HashMap::new();
        if let Some(socket_path) = self.remote_socket_path.as_ref() {
            env.insert("WOK_SOCKET".to_string(), socket_path.display().to_string());
        }
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
                    replay_store: ReplayStore::default(),
                    replay_mode: None,
                    pending_replay_block_marker: false,
                    daemon_last_synced_row: None,
                    inline_images: InlineImageStore::new(),
                    last_output_line_row: None,
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

            let daemon_pane_id = self.attached_daemon_pane_id(pane_id);
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
                if let Some(session) = self.attached_session.as_deref() {
                    if let Err(error) =
                        wok_app::daemon::resize_pane(session, daemon_pane_id, cols, rows)
                    {
                        warn!("failed to resize daemon pane for session '{session}': {error}");
                    }
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
                focused_floating: tab.focused_floating,
                split_tree: split_node_to_state(&tab.split_manager.root),
                floating_panes: tab
                    .floating_panes
                    .iter()
                    .map(|pane| FloatingPaneState {
                        pane_id: pane.pane_id,
                        rect: (pane.rect.x, pane.rect.y, pane.rect.w, pane.rect.h),
                        z_order: pane.z_order,
                        is_visible: pane.is_visible,
                        title: pane.title.clone(),
                    })
                    .collect(),
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
                floating_panes: tab
                    .floating_panes
                    .into_iter()
                    .map(|pane| FloatingPane {
                        pane_id: pane.pane_id,
                        rect: Rect::new(pane.rect.0, pane.rect.1, pane.rect.2, pane.rect.3),
                        z_order: pane.z_order,
                        is_visible: pane.is_visible,
                        title: pane.title,
                    })
                    .collect(),
                focused_floating: tab.focused_floating,
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
        let status_segments = self
            .active_pane()
            .map(|active_pane| self.compose_status_bar_segments(active_pane));
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
                status_segments.as_ref(),
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
            let floating = self.workspace.active_floating_pane(pane_id).cloned();
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

            if let Some(replay_mode) = pane.replay_mode.as_ref() {
                if let Some(snapshot) = pane.replay_store.snapshot(replay_mode.snapshot_index) {
                    pane.row_cache.invalidate();
                    render_replay_snapshot(
                        render,
                        &mut self.font,
                        theme,
                        viewport,
                        snapshot,
                        &pane.replay_store,
                        replay_mode.snapshot_index,
                        cursor_shape,
                        cursor_visible,
                        focused,
                        self.workspace.broadcast_input,
                        window_opacity,
                        terminal_surface_alpha,
                    );
                    if let Some(floating) = floating.as_ref() {
                        let title_height = 18.0;
                        render.batch.push_bg_quad(
                            viewport.x,
                            viewport.y,
                            viewport.w,
                            title_height,
                            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.92],
                        );
                        push_text(
                            render,
                            &mut self.font,
                            viewport.x + 8.0,
                            viewport.y + 2.0,
                            &floating.title,
                            [
                                theme.status_bar_text.r,
                                theme.status_bar_text.g,
                                theme.status_bar_text.b,
                                0.95,
                            ],
                        );
                    }
                    continue;
                }
            }

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
                        &pane.inline_images,
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
            render
                .batch
                .push_bg_quad(viewport.x, viewport.y, viewport.w, 1.0, border_color);
            render
                .batch
                .push_bg_quad(viewport.x, viewport.y, 1.0, viewport.h, border_color);
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
            if let Some(floating) = floating.as_ref() {
                let title_height = 18.0;
                render.batch.push_bg_quad(
                    viewport.x,
                    viewport.y,
                    viewport.w,
                    title_height,
                    [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.92],
                );
                push_text(
                    render,
                    &mut self.font,
                    viewport.x + 8.0,
                    viewport.y + 2.0,
                    &floating.title,
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.95,
                    ],
                );
                render.batch.push_bg_quad(
                    viewport.x + viewport.w - 1.0,
                    viewport.y,
                    1.0,
                    viewport.h,
                    [
                        theme.block_separator.r,
                        theme.block_separator.g,
                        theme.block_separator.b,
                        0.9,
                    ],
                );
                render.batch.push_bg_quad(
                    viewport.x,
                    viewport.y + viewport.h - 1.0,
                    viewport.w,
                    1.0,
                    [
                        theme.block_separator.r,
                        theme.block_separator.g,
                        theme.block_separator.b,
                        0.9,
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

    fn apply_plugin_keybindings(&self, app: &mut WokApp) {
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

    fn active_search_state(&self) -> Option<wok_ui::search::GlobalSearch> {
        self.active_pane().and_then(|pane| {
            pane.app
                .global_search
                .is_active
                .then(|| pane.app.global_search.clone())
        })
    }

    fn install_search_state_on_active_pane(&mut self, search: wok_ui::search::GlobalSearch) {
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
            wok_app::config::CursorStyle::Block => CursorShape::Block,
            wok_app::config::CursorStyle::Bar => CursorShape::Bar,
            wok_app::config::CursorStyle::Underline => CursorShape::Underline,
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
            self.metrics.summary_line(),
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
                wok_app::config::InputPosition::Top => "top",
                wok_app::config::InputPosition::Bottom => "bottom",
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

    fn output_line_hooks_enabled(&self) -> bool {
        self.plugins
            .as_ref()
            .is_some_and(|plugins| plugins.has_hook_listener("output_line"))
    }

    fn collect_output_line_events_for_pane(
        &mut self,
        pane_id: PaneId,
        include_current_row: bool,
    ) -> Vec<OutputLineEvent> {
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return Vec::new();
        };
        let Some(block_id) = pane.app.block_manager.active_output_block_id().or_else(|| {
            include_current_row
                .then(|| pane.app.block_manager.blocks.last().map(|block| block.id))
                .flatten()
        }) else {
            return Vec::new();
        };
        let Some(block) = pane
            .app
            .block_manager
            .blocks
            .iter()
            .find(|block| block.id == block_id)
        else {
            return Vec::new();
        };

        let start_row = pane
            .last_output_line_row
            .map_or(block.output_start_row, |row| row.saturating_add(1));
        let end_row = if include_current_row {
            block.output_end_row
        } else {
            pane.terminal.state.absolute_cursor_row().saturating_sub(1)
        };
        if end_row < start_row {
            return Vec::new();
        }

        pane.last_output_line_row = Some(end_row);
        pane.app.block_manager.output_line_events_for_range(
            &pane.terminal,
            pane_id,
            block_id,
            start_row,
            end_row,
        )
    }

    fn dispatch_output_line_hooks(&mut self, events: Vec<OutputLineEvent>) {
        if events.is_empty() {
            return;
        }
        let Some(plugins) = &self.plugins else {
            return;
        };

        self.refresh_plugin_snapshot();
        for chunk in events.chunks(100) {
            if chunk.len() == 1 {
                let event = &chunk[0];
                plugins.trigger_hook(
                    "output_line",
                    &json!({
                        "pane_id": event.pane_id,
                        "block_id": event.block_id,
                        "line_number": event.line_number,
                        "text": event.text,
                    }),
                );
            } else {
                let payload: Vec<_> = chunk
                    .iter()
                    .map(|event| {
                        json!({
                            "pane_id": event.pane_id,
                            "block_id": event.block_id,
                            "line_number": event.line_number,
                            "text": event.text,
                        })
                    })
                    .collect();
                plugins.trigger_hook("output_line", &payload);
            }
        }
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
        for request in effects.status_bar_requests {
            self.apply_status_bar_request(request);
        }
        self.refresh_plugin_config();
        self.refresh_plugin_snapshot();
    }

    fn apply_status_bar_request(&mut self, request: StatusBarRequest) {
        match request {
            StatusBarRequest::SetLeft(segments) => self.status_bar_state.set_left(segments),
            StatusBarRequest::SetCenter(segments) => self.status_bar_state.set_center(segments),
            StatusBarRequest::SetRight(segments) => self.status_bar_state.set_right(segments),
            StatusBarRequest::Clear => self.status_bar_state.clear_custom(),
            StatusBarRequest::SetRefreshInterval(ms) => {
                let clamped = ms.clamp(250, 60_000);
                self.status_bar_refresh_interval = Duration::from_millis(clamped);
            }
        }
        self.needs_redraw = true;
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
                match wok_ui::theme_loader::load_theme(&path) {
                    Ok(mut theme) => {
                        if let Err(error) = wok_ui::theme_loader::apply_theme_overrides(
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
                            .and_then(|path| wok_ui::theme_loader::load_theme(path).ok())
                            .unwrap_or_default()
                    });
                match wok_ui::theme_loader::apply_theme_overrides(&mut theme, &self.theme_overrides)
                {
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
            pane.app.zoom = wok_ui::zoom::ZoomManager::new(theme.font_size);
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
        if let Some(session) = self.attached_session.as_deref() {
            if let Some(pane_id) = self.active_pane_id() {
                let daemon_pane_id = self.attached_daemon_pane_id(pane_id);
                if let Err(error) = wok_app::daemon::send_input(session, daemon_pane_id, data) {
                    warn!("failed to send daemon input for session '{session}': {error}");
                }
            }
            return;
        }

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

    fn capture_replay_snapshot_for_pane(&mut self, pane_id: PaneId, force_marker: bool) {
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return;
        };
        let capture = pane.replay_store.capture_snapshot(
            &pane.terminal.state,
            pane.app.block_manager.blocks.len(),
            50,
            force_marker,
            force_marker,
        );
        if !capture.captured {
            return;
        }

        if let Some(mode) = pane.replay_mode.as_mut() {
            if capture.dropped_oldest && mode.snapshot_index > 0 {
                mode.snapshot_index = mode.snapshot_index.saturating_sub(1);
            }
            if let Some(newest) = pane.replay_store.newest_index() {
                mode.snapshot_index = mode.snapshot_index.min(newest);
            }
        }
    }

    fn toggle_replay_mode(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            return;
        };
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return;
        };

        if pane.replay_mode.is_some() {
            pane.replay_mode = None;
            pane.row_cache.invalidate();
            self.status_message = Some("Exited replay mode".to_string());
            self.needs_redraw = true;
            return;
        }

        if pane.replay_store.is_empty() {
            let _ = pane.replay_store.capture_snapshot(
                &pane.terminal.state,
                pane.app.block_manager.blocks.len(),
                50,
                false,
                true,
            );
        }

        let Some(newest) = pane.replay_store.newest_index() else {
            self.status_message = Some("Replay history is empty".to_string());
            return;
        };

        pane.replay_mode = Some(ReplayModeState {
            snapshot_index: newest,
        });
        pane.row_cache.invalidate();
        self.status_message = Some("Replay mode active".to_string());
        self.needs_redraw = true;
    }

    fn handle_replay_input(&mut self, event: &InputEvent) -> bool {
        let is_toggle = matches!(event.action, KeyAction::Char('r') | KeyAction::Char('R'))
            && platform_modifier_active(event.modifiers)
            && event.modifiers.alt
            && event.modifiers.shift;
        if is_toggle {
            self.toggle_replay_mode();
            return true;
        }

        let Some(pane_id) = self.active_pane_id() else {
            return false;
        };
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return false;
        };
        let Some(mode) = pane.replay_mode.as_mut() else {
            return false;
        };

        let Some(newest) = pane.replay_store.newest_index() else {
            pane.replay_mode = None;
            return true;
        };
        let oldest = 0usize;

        match event.action {
            KeyAction::Escape => {
                pane.replay_mode = None;
                pane.row_cache.invalidate();
                self.status_message = Some("Exited replay mode".to_string());
            }
            KeyAction::ArrowLeft => {
                mode.snapshot_index = mode.snapshot_index.saturating_sub(1);
            }
            KeyAction::ArrowRight => {
                mode.snapshot_index = (mode.snapshot_index + 1).min(newest);
            }
            KeyAction::Home => {
                mode.snapshot_index = oldest;
            }
            KeyAction::End => {
                mode.snapshot_index = newest;
            }
            KeyAction::Char('[') => {
                if let Some(previous) = pane.replay_store.previous_marker(mode.snapshot_index) {
                    mode.snapshot_index = previous;
                }
            }
            KeyAction::Char(']') => {
                if let Some(next) = pane.replay_store.next_marker(mode.snapshot_index) {
                    mode.snapshot_index = next;
                }
            }
            _ => {}
        }

        self.needs_redraw = true;
        true
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
            wok_ui::links::open_url(&url);
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
                SemanticEvent::CommandStart { .. } => {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.prompt_ready = false;
                    }
                    relayout = true;
                }
                SemanticEvent::OutputStart { row } => {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.prompt_ready = false;
                        pane.last_output_line_row = row.checked_sub(1);
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
                            pane.last_output_line_row = None;
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
                SemanticEvent::InlineImage(image_event) => {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        match image_event {
                            wok_terminal::terminal::InlineImageEvent::Put {
                                image_id,
                                width,
                                height,
                                pixels,
                                row,
                                col,
                                display_cols,
                                display_rows,
                                placement_id,
                            } => {
                                pane.inline_images.upsert_image(
                                    image_id,
                                    width,
                                    height,
                                    pixels,
                                    ImagePlacement {
                                        row,
                                        col,
                                        display_cols,
                                        display_rows,
                                        placement_id,
                                    },
                                );
                            }
                            wok_terminal::terminal::InlineImageEvent::Place {
                                image_id,
                                row,
                                col,
                                display_cols,
                                display_rows,
                                placement_id,
                            } => {
                                pane.inline_images.place_existing(
                                    image_id,
                                    ImagePlacement {
                                        row,
                                        col,
                                        display_cols,
                                        display_rows,
                                        placement_id,
                                    },
                                );
                            }
                            wok_terminal::terminal::InlineImageEvent::Delete {
                                image_id,
                                placement_id,
                            } => {
                                pane.inline_images.delete(image_id, placement_id);
                            }
                        }
                    }
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
                            if let Some(workflow) =
                                self.workflow_store.by_name(&workflow_name).cloned()
                            {
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
                                active_pane.app.input_editor.buffer.insert_at(0, &path).ok();
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
                    if let EditorAction::SendEof =
                        active_pane.app.input_editor.handle_key(editor_key)
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
                                let prev_line = pane
                                    .terminal
                                    .state
                                    .row_text(vi.cursor_row.saturating_sub(1));
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
                    let prev_line = pane
                        .terminal
                        .state
                        .row_text(vi.cursor_row.saturating_sub(1));
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
        self.status_message = self.panes.get(&pane_id).and_then(|pane| {
            pane.app
                .vi_mode
                .as_ref()
                .map(|vi| vi.mode_label().to_string())
        });
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
                    .filter(|entry| seen.insert(entry.command.clone()))
                    .map(|entry| entry.command.clone())
                    .collect::<Vec<_>>()
            })
            .unwrap_or_default();

        candidates.extend(
            prefix_matches(self.global_history.entries(), &base_query)
                .into_iter()
                .filter(|entry| seen.insert(entry.command.clone()))
                .map(|entry| entry.command.clone()),
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
            .filter(|entry| {
                !entry.command.trim().is_empty() && seen_recent.insert(entry.command.clone())
            })
            .map(|entry| entry.command.clone())
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

    fn focus_pane_at_point(&mut self, x: f64, y: f64) -> bool {
        let Some(pane_id) =
            self.workspace
                .pane_at_point(self.chrome_rects.content, x as f32, y as f32)
        else {
            return false;
        };
        let changed = self.active_pane_id() != Some(pane_id) && self.workspace.focus_pane(pane_id);
        if changed {
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            self.needs_redraw = true;
        }
        changed
    }

    fn pixel_to_cell(&self, x: f64, y: f64) -> Option<CellPos> {
        let pane_id = self.active_pane_id()?;
        self.pixel_to_cell_in_pane(pane_id, x, y)
    }

    fn pixel_to_cell_in_pane(&self, pane_id: PaneId, x: f64, y: f64) -> Option<CellPos> {
        let active_pane = self.panes.get(&pane_id)?;
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

impl AppHandler for WokHandler {
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
        if let Some(plugins) = &self.plugins {
            plugins.pump_timers(64);
        }
        self.drain_plugin_side_effects();
        self.sync_attached_session_snapshot();
        self.pump_remote_control();

        if self.last_status_bar_refresh.elapsed() >= self.status_bar_refresh_interval {
            self.last_status_bar_refresh = Instant::now();
            if let Some(pane_id) = self.active_pane_id() {
                let payload = self.pane_hook_payload(pane_id);
                self.run_plugin_hook("status_bar_refresh", &payload);
            }
        }

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
                wok_ui::theme_loader::apply_theme_overrides(&mut theme, &self.theme_overrides)
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
        let output_line_hooks_enabled = self.output_line_hooks_enabled();
        let mut output_line_events = Vec::new();
        for pane_id in pane_ids {
            let mut semantic_events = Vec::new();
            let mut is_dirty = false;
            let mut command_ended = false;
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
                command_ended = semantic_events
                    .iter()
                    .any(|event| matches!(event, SemanticEvent::CommandEnd { .. }));
                self.handle_semantic_events(pane_id, semantic_events);
            }
            if command_ended {
                if let Some(pane) = self.panes.get_mut(&pane_id) {
                    pane.pending_replay_block_marker = true;
                }
            }
            let force_marker = self
                .panes
                .get(&pane_id)
                .is_some_and(|pane| pane.pending_replay_block_marker);
            self.capture_replay_snapshot_for_pane(pane_id, force_marker);
            if force_marker {
                if let Some(pane) = self.panes.get_mut(&pane_id) {
                    pane.pending_replay_block_marker = false;
                }
            }
            self.sync_owned_input_state_for_pane(pane_id);
            if output_line_hooks_enabled {
                output_line_events
                    .extend(self.collect_output_line_events_for_pane(pane_id, command_ended));
            }
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

        if output_line_hooks_enabled {
            self.dispatch_output_line_hooks(output_line_events);
        }

        if relayout {
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
        }

        self.metrics.pane_count = self.panes.len();
        self.metrics.replay_snapshot_count =
            self.panes.values().map(|p| p.replay_store.len()).sum();
        self.metrics.frame_count += 1;

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

    fn on_scale_factor_changed(&mut self, _new_scale_factor: f64, new_size: PhysicalSize<u32>) {
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
        if self.handle_replay_input(&event) {
            return;
        }

        let kitty_flags = self
            .active_pane()
            .map_or(0, |pane| pane.terminal.state.kitty_keyboard_flags());
        if event.event_type == InputEventType::Release && kitty_flags == 0 {
            return;
        }

        if event.event_type != InputEventType::Release {
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
        }
        if let Some(data) = input_event_to_pty_bytes(&event, kitty_flags) {
            self.send_raw_input_to_pty(&data);
            self.needs_redraw = true;
        }
    }

    fn on_mouse_event(&mut self, event: wok_app::input::MouseEvent) {
        match event {
            wok_app::input::MouseEvent::Press {
                button: MouseButton::Left,
                x,
                y,
                modifiers,
            } => {
                self.focus_pane_at_point(x, y);
                if modifiers.alt && platform_modifier_active(modifiers) {
                    if let Some(pane_id) = self.active_pane_id() {
                        if let Some(floating) = self.workspace.active_floating_pane(pane_id) {
                            let rect = floating.rect;
                            let near_right = x >= f64::from(rect.x + rect.w - 10.0)
                                && x <= f64::from(rect.x + rect.w);
                            let near_bottom = y >= f64::from(rect.y + rect.h - 10.0)
                                && y <= f64::from(rect.y + rect.h);
                            let in_title = y >= f64::from(rect.y)
                                && y <= f64::from(rect.y + 18.0)
                                && x >= f64::from(rect.x)
                                && x <= f64::from(rect.x + rect.w);
                            let mode = if near_right || near_bottom {
                                Some(FloatingDragMode::Resize)
                            } else if in_title {
                                Some(FloatingDragMode::Move)
                            } else {
                                None
                            };
                            if let Some(mode) = mode {
                                self.floating_drag = Some(FloatingDragState {
                                    pane_id,
                                    mode,
                                    last_x: x,
                                    last_y: y,
                                });
                                self.needs_redraw = true;
                                return;
                            }
                        }
                    }
                }
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
                            wok_ui::links::open_url(&uri);
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
            wok_app::input::MouseEvent::Release {
                button: MouseButton::Left,
                ..
            } => {
                self.floating_drag = None;
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
            wok_app::input::MouseEvent::Move { x, y } => {
                if let Some(drag) = self.floating_drag.as_mut() {
                    let dx = (x - drag.last_x) as f32;
                    let dy = (y - drag.last_y) as f32;
                    let moved = match drag.mode {
                        FloatingDragMode::Move => self.workspace.move_floating_pane(
                            drag.pane_id,
                            dx,
                            dy,
                            self.chrome_rects.content,
                        ),
                        FloatingDragMode::Resize => self.workspace.resize_floating_pane(
                            drag.pane_id,
                            dx,
                            dy,
                            self.chrome_rects.content,
                        ),
                    };
                    drag.last_x = x;
                    drag.last_y = y;
                    if moved {
                        if let Some(window) = &self.window {
                            self.sync_workspace_layout(window.inner_size());
                        }
                        self.needs_redraw = true;
                    }
                    return;
                }
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
            wok_app::input::MouseEvent::Scroll { delta_y, .. } => {
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
            wok_app::input::MouseEvent::Press { .. }
            | wok_app::input::MouseEvent::Release { .. } => {}
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
        info!("wok closing");
        true
    }
}

fn trigger_engine_from_config(config: &WokConfig) -> TriggerEngine {
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
                let parsed = wok_ui::theme_loader::parse_hex_color(&highlight.color).ok()?;
                return Some([parsed.r, parsed.g, parsed.b, parsed.a]);
            }
        }
    }
    None
}

fn format_replay_age(elapsed: Duration) -> String {
    let total_seconds = elapsed.as_secs();
    let minutes = total_seconds / 60;
    let seconds = total_seconds % 60;
    if minutes == 0 {
        format!("{seconds}s ago")
    } else {
        format!("{minutes}m{seconds:02}s ago")
    }
}

#[cfg(test)]
fn parse_lua_key_combo(key: &str) -> Option<wok_app::keybindings::KeyCombo> {
    let mut modifiers = wok_app::input::Modifiers::default();
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

    key_action.map(|key| wok_app::keybindings::KeyCombo { key, modifiers })
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
        Action::NewFloatingPane => "new_floating_pane".to_string(),
        Action::ToggleFloatingPane => "toggle_floating_pane".to_string(),
        Action::CloseFloatingPane => "close_floating_pane".to_string(),
        Action::NextLayout => "next_layout".to_string(),
        Action::PrevLayout => "prev_layout".to_string(),
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

fn key_combo_label(combo: &wok_app::keybindings::KeyCombo) -> String {
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
        KeyAction::ModifierShift => "Shift".to_string(),
        KeyAction::ModifierControl => "Control".to_string(),
        KeyAction::ModifierAlt => "Alt".to_string(),
        KeyAction::ModifierMeta => "Meta".to_string(),
        KeyAction::Copy => "Copy".to_string(),
        KeyAction::Paste => "Paste".to_string(),
        KeyAction::Cut => "Cut".to_string(),
        KeyAction::SelectAll => "SelectAll".to_string(),
        KeyAction::Undo => "Undo".to_string(),
        KeyAction::Redo => "Redo".to_string(),
    }
}

fn platform_modifier_active(modifiers: wok_app::input::Modifiers) -> bool {
    #[cfg(target_os = "macos")]
    {
        modifiers.meta
    }
    #[cfg(not(target_os = "macos"))]
    {
        modifiers.ctrl
    }
}

fn main() -> Result<(), Box<dyn Error>> {
    let default_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        eprintln!("Wok panicked: {info}");
        default_hook(info);
    }));
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| "warn".into()),
        )
        .init();
    let cli = Cli::parse();
    info!("starting Wok terminal");

    let attached_session = match dispatch_cli_command(&cli)? {
        CliAction::ExitOk => return Ok(()),
        CliAction::ContinueToWindow { attached_session } => attached_session,
    };

    let onboarding_message = match setup_ops::ensure_first_run_bootstrap() {
        Ok(message) => message,
        Err(error) => {
            warn!("failed to run first-run bootstrap: {error}");
            None
        }
    };

    let mut config = WokConfig::load();
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
    let mut handler = WokHandler::new(config);
    if let Some(message) = onboarding_message {
        handler.status_message = Some(message);
    }
    if let Some(session) = attached_session {
        handler.attached_session = Some(session.clone());
        let attach_message = format!("Attached session '{session}'");
        handler.status_message = match handler.status_message.take() {
            Some(existing) => Some(format!("{existing} | {attach_message}")),
            None => Some(attach_message),
        };
    }

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
    fn test_attached_daemon_pane_id_defaults_to_zero() {
        let handler = WokHandler::new(WokConfig::default());
        assert_eq!(handler.attached_daemon_pane_id(1), ATTACHED_DAEMON_PANE_ID);
        assert_eq!(handler.attached_daemon_pane_id(99), ATTACHED_DAEMON_PANE_ID);
    }

    #[test]
    fn test_attached_daemon_pane_id_uses_mapping() {
        let mut handler = WokHandler::new(WokConfig::default());
        handler.daemon_pane_by_local.insert(5, 42);
        assert_eq!(handler.attached_daemon_pane_id(5), 42);
        assert_eq!(handler.attached_daemon_pane_id(6), ATTACHED_DAEMON_PANE_ID);
    }

    #[test]
    fn test_attached_mode_blocks_session_save_load() {
        assert!(attached_mode_blocks_workspace_effect(
            &WorkspaceEffect::SaveSession("x".to_string())
        ));
        assert!(attached_mode_blocks_workspace_effect(
            &WorkspaceEffect::LoadSession("x".to_string())
        ));
    }

    #[test]
    fn test_attached_mode_allows_splits_and_tabs() {
        assert!(!attached_mode_blocks_workspace_effect(
            &WorkspaceEffect::SplitVertical
        ));
        assert!(!attached_mode_blocks_workspace_effect(
            &WorkspaceEffect::NewTab
        ));
    }

    #[test]
    fn test_parse_remote_action_with_params_supports_named_forms() {
        assert_eq!(
            action_parser::parse_remote_action_with_params("save_session", Some(&json!("demo"))),
            Some(Action::SaveSession("demo".to_string()))
        );
        assert_eq!(
            action_parser::parse_remote_action_with_params(
                "load_session",
                Some(&json!({"name": "nightly"})),
            ),
            Some(Action::LoadSession("nightly".to_string()))
        );
        assert_eq!(
            action_parser::parse_remote_action_with_params(
                "switch_to_tab",
                Some(&json!({"index": 3})),
            ),
            Some(Action::SwitchToTab(3))
        );
    }

    #[test]
    fn test_parse_lua_key_combo_supports_modifiers_and_named_keys() {
        let combo = parse_lua_key_combo("ctrl+shift+up").expect("combo should parse");
        assert_eq!(combo.key, KeyAction::ArrowUp);
        assert!(combo.modifiers.ctrl);
        assert!(combo.modifiers.shift);
        assert!(!combo.modifiers.alt);
    }

    #[test]
    fn test_kitty_keyboard_encoding_uses_event_type_when_enabled() {
        let event = InputEvent {
            action: KeyAction::Char('P'),
            modifiers: wok_app::input::Modifiers {
                ctrl: true,
                shift: true,
                ..Default::default()
            },
            is_repeat: true,
            event_type: InputEventType::Repeat,
        };
        let encoded =
            input_event_to_pty_bytes(&event, 0x2 | 0x4).expect("kitty-encoded bytes should exist");
        assert_eq!(
            String::from_utf8(encoded).expect("utf8"),
            "\u{1b}[80:112;6;2u"
        );
    }

    #[test]
    fn test_kitty_keyboard_encoding_uses_base_modifier_value() {
        let event = InputEvent {
            action: KeyAction::Tab,
            modifiers: Default::default(),
            is_repeat: false,
            event_type: InputEventType::Press,
        };
        let encoded = input_event_to_pty_bytes(&event, 0x1).expect("kitty-encoded bytes");
        assert_eq!(String::from_utf8(encoded).expect("utf8"), "\u{1b}[9;1u");
    }

    #[test]
    fn test_legacy_encoding_unchanged_without_kitty_flags() {
        let event = InputEvent {
            action: KeyAction::Enter,
            modifiers: Default::default(),
            is_repeat: false,
            event_type: InputEventType::Press,
        };
        let encoded = input_event_to_pty_bytes(&event, 0).expect("legacy bytes should exist");
        assert_eq!(encoded, b"\r".to_vec());
    }

    #[test]
    fn test_kitty_keyboard_release_event_encodes_type_three() {
        let event = InputEvent {
            action: KeyAction::Char('a'),
            modifiers: Default::default(),
            is_repeat: false,
            event_type: InputEventType::Release,
        };
        let encoded =
            input_event_to_pty_bytes(&event, 0x2).expect("kitty-encoded release should exist");
        assert_eq!(String::from_utf8(encoded).expect("utf8"), "\u{1b}[97;1;3u");
    }

    #[test]
    fn test_kitty_keyboard_modifier_only_events_are_encoded() {
        let event = InputEvent {
            action: KeyAction::ModifierControl,
            modifiers: wok_app::input::Modifiers {
                ctrl: true,
                ..Default::default()
            },
            is_repeat: false,
            event_type: InputEventType::Press,
        };
        let encoded =
            input_event_to_pty_bytes(&event, 0x2).expect("kitty modifier event should encode");
        assert_eq!(
            String::from_utf8(encoded).expect("utf8"),
            "\u{1b}[57442;5;1u"
        );
    }

    #[test]
    fn runtime_metrics_summary_line_without_daemon_lag() {
        let m = RuntimeMetrics {
            frame_count: 42,
            last_frame_duration_us: 500,
            pane_count: 2,
            replay_snapshot_count: 10,
            daemon_sync_lag_ms: None,
        };
        assert_eq!(m.summary_line(), "frames:42 panes:2 replays:10");
    }

    #[test]
    fn runtime_metrics_summary_line_with_daemon_lag() {
        let m = RuntimeMetrics {
            frame_count: 1,
            last_frame_duration_us: 0,
            pane_count: 1,
            replay_snapshot_count: 0,
            daemon_sync_lag_ms: Some(15),
        };
        assert_eq!(m.summary_line(), "frames:1 panes:1 replays:0 sync_lag:15ms");
    }
}
