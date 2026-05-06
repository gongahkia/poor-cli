//! Wok terminal emulator entry point.
#![allow(unexpected_cfgs)]

use std::cell::RefCell;
use std::collections::HashMap;
use std::collections::HashSet;
use std::collections::VecDeque;
use std::error::Error;
use std::fs::{File, OpenOptions};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::process::Command;
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

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
use wok_app::block_query::{BlockQueryMode, BlockQueryState, DiffLineEntry, DiffLineKind};
use wok_app::command_search::{CommandSearchScope, CommandSearchState};
use wok_app::config::{MouseBindingArea, TriggerScopeConfig, VisualEffectMode, WokConfig};
use wok_app::event_loop::{run_event_loop, RuntimeWaker};
use wok_app::handler::{AppHandler, AppMenuAction};
use wok_app::input::{InputEvent, InputEventType, KeyAction, Modifiers};
use wok_app::keybindings::Action;
use wok_app::plugin_host::PluginHost;
use wok_app::remote_control::{
    error_response, result_response, RemoteControlServer, RemoteRequest,
};
use wok_app::scripting::{
    QuickSelectPatternRequest, SetupRequest, StatusBarRequest, SystemNotificationRequest,
    ThemeRequest, TriggerRequest, WorkflowRequest,
};
use wok_app::session::{
    block_from_state, block_to_state, default_session_path, history_entry_from_state,
    history_entry_to_state, load_session, named_session_path, save_session, split_node_from_state,
    split_node_to_state, FloatingPaneState, PaneState, WorkspaceSessionState, WorkspaceTabState,
};
use wok_app::window::WindowConfig;
use wok_app::workspace::{
    FloatingPane, FloatingResizeEdges, FocusDirection, PaneId, WorkspaceState, WorkspaceTab,
};
use wok_blocks::block::{Block, OutputLineEvent};
use wok_blocks::triggers::{
    Trigger, TriggerAction, TriggerEngine, TriggerHighlight, TriggerMatch, TriggerScope,
};
use wok_input::editor::{EditorAction, EditorKey, InputEditor};
use wok_input::history::{prefix_matches, CommandHistory, HistoryEntry};
use wok_input::workflows::{Workflow, WorkflowStore};
use wok_renderer::atlas::GlyphAtlas;
use wok_renderer::damage::DirtyRegion;
use wok_renderer::font::FontSystem;
use wok_renderer::gpu::{native_instance_descriptor, GpuContext};
use wok_renderer::inline_images::{ImagePlacement, InlineImageStore};
use wok_renderer::pipeline::CursorShape;
use wok_renderer::pipeline::QuadBatch;
use wok_renderer::render_pipeline::TerminalRenderPipeline;
use wok_terminal::replay::{ReplaySnapshot, ReplayStore};
use wok_terminal::shell::ShellType;
use wok_terminal::state::{CellColor, CellRenderData};
use wok_terminal::terminal::{SemanticEvent, Terminal, TerminalDamage};
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
use wok_ui::splits::{SplitDirection, SplitManager};
use wok_ui::status_bar::{StatusBarState, StatusSegment};
use wok_ui::theme::Theme;
use wok_ui::theme_watcher::ThemeWatcher;
use wok_ui::vi_mode::{ViModeState, ViPending, ViSubMode};
use wok_ui::viewport::ViewportRenderer;

mod action_parser;
mod cli_runtime;
mod input_codec;
mod jsonrpc_params;
mod media_preview;
mod perf_metrics;
mod remote_runtime;
mod render_runtime;
mod rpc_cli;
mod setup_ops;
mod workspace_runtime;

use action_parser::parse_lua_action;
use cli_runtime::{dispatch_cli_command, parse_shell_type, CliAction};
use input_codec::{input_event_to_editor_key, input_event_to_pty_bytes};
use media_preview::{media_kind_for_path, MediaPreview, PreviewFrame};
use perf_metrics::{format_bytes, percent, SystemMetricsSampler};
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
        /// Reset scope: managed, state, or all.
        #[arg(long, value_enum, default_value_t = setup_ops::ResetScope::Managed)]
        scope: setup_ops::ResetScope,
        /// Confirm reset without interactive prompt.
        #[arg(long, default_value_t = false)]
        yes: bool,
    },
    /// Manage shell startup wiring for Wok integration scripts.
    Shell {
        #[command(subcommand)]
        command: ShellCommand,
    },
    /// Manage named workspace snapshots on a running Wok instance.
    Workspace {
        #[command(subcommand)]
        command: WorkspaceCommand,
    },
    /// Bundle local diagnostics into a directory for bug reports (no upload).
    BugReport {
        /// Optional explicit destination directory. Default: ./bug-<unix_ms>.
        #[arg(long)]
        output: Option<std::path::PathBuf>,
    },
    /// Replay a previously recorded `.wokcast` file by writing its byte
    /// chunks to stdout at original cadence (or scaled by `--speed`).
    Replay {
        /// Path to the wokcast file.
        file: std::path::PathBuf,
        /// Playback speed multiplier (1.0 = original, 2.0 = 2x, 0 = instant).
        #[arg(long, default_value_t = 1.0)]
        speed: f64,
    },
    /// Guided 4-step onboarding: detect shell → seed config → install → smoke.
    Onboard {
        /// Target shell: auto, bash, zsh, or fish.
        #[arg(long)]
        shell: Option<String>,
        /// Skip writing to the user's shell startup file.
        #[arg(long, default_value_t = false)]
        no_install: bool,
        /// Overwrite existing managed config files.
        #[arg(long, default_value_t = false)]
        overwrite: bool,
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
        /// Optional remote-control auth token. Defaults to $WOK_RPC_TOKEN.
        #[arg(long)]
        token: Option<String>,
        /// Optional JSON-RPC id value. Parsed as JSON, fallback to string.
        #[arg(long)]
        id: Option<String>,
        /// Send as notification (no id, no response expected).
        #[arg(long, default_value_t = false)]
        notify: bool,
    },
    /// Print Git status for the active pane through remote control.
    GitStatus {
        /// Optional pane id. Defaults to the active pane.
        #[arg(long)]
        pane_id: Option<u64>,
        /// Explicit remote-control socket path. Defaults to $WOK_SOCKET.
        #[arg(long)]
        socket: Option<String>,
        /// Optional remote-control auth token. Defaults to $WOK_RPC_TOKEN.
        #[arg(long)]
        token: Option<String>,
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
        /// Target shell to roll back: bash, zsh, or fish.
        #[arg(long)]
        shell: Option<String>,
        /// Confirm rollback without interactive prompt.
        #[arg(long, default_value_t = false)]
        yes: bool,
    },
}

#[derive(Subcommand, Debug, Clone)]
enum WorkspaceCommand {
    /// Save the current workspace to a named snapshot.
    Save {
        /// Snapshot name.
        name: String,
        /// Explicit remote-control socket path. Defaults to $WOK_SOCKET.
        #[arg(long)]
        socket: Option<String>,
        /// Optional remote-control auth token. Defaults to $WOK_RPC_TOKEN.
        #[arg(long)]
        token: Option<String>,
    },
    /// Load a named workspace snapshot.
    Load {
        /// Snapshot name.
        name: String,
        /// Explicit remote-control socket path. Defaults to $WOK_SOCKET.
        #[arg(long)]
        socket: Option<String>,
        /// Optional remote-control auth token. Defaults to $WOK_RPC_TOKEN.
        #[arg(long)]
        token: Option<String>,
    },
    /// List saved workspace snapshots.
    List,
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
    baseline_block_id: Option<u64>,
    query: String,
    current_match: usize,
    overlay_scroll_offset: usize,
    matches: Vec<(usize, usize, usize)>,
    diff_entries: Vec<(DiffLineKind, String)>,
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

#[derive(Clone, Copy)]
struct TypewriterReveal {
    reveal_at: Instant,
}

#[derive(Default)]
struct TypewriterState {
    pending: HashMap<(usize, usize), TypewriterReveal>,
    next_reveal_at: Option<Instant>,
}

impl TypewriterState {
    fn clear(&mut self) {
        self.pending.clear();
        self.next_reveal_at = None;
    }

    fn has_pending(&self) -> bool {
        !self.pending.is_empty()
    }

    fn pending_cell_count(&self) -> usize {
        self.pending.len()
    }

    fn pending_row_count(&self) -> usize {
        self.pending
            .keys()
            .map(|(row, _)| *row)
            .collect::<HashSet<_>>()
            .len()
    }

    fn pending_rows(&self) -> impl Iterator<Item = usize> + '_ {
        self.pending.keys().map(|(row, _)| *row)
    }

    fn is_cell_hidden(&self, absolute_row: usize, col: usize, now: Instant) -> bool {
        self.pending
            .get(&(absolute_row, col))
            .is_some_and(|cell| cell.reveal_at > now)
    }

    fn prune_revealed(&mut self, now: Instant) {
        self.pending.retain(|_, cell| cell.reveal_at > now);
        if self.pending.is_empty() {
            self.next_reveal_at = None;
        }
    }

    fn enqueue_changed_cells(
        &mut self,
        absolute_row: usize,
        previous: Option<&PaneRowSignature>,
        next_cells: &[CellRenderData],
        now: Instant,
        cps: f32,
        max_pending_cells: usize,
    ) {
        let Some(previous) = previous else {
            self.enqueue_new_cells(absolute_row, next_cells, now, cps, max_pending_cells);
            return;
        };
        if previous.absolute_row != absolute_row {
            self.enqueue_new_cells(absolute_row, next_cells, now, cps, max_pending_cells);
            return;
        }

        let interval = Duration::from_secs_f64(1.0 / f64::from(cps.clamp(20.0, 2_000.0)));
        let mut reveal_at = self.next_reveal_at.unwrap_or(now).max(now);
        let mut budget = max_pending_cells.saturating_sub(self.pending.len());

        for (col, next_cell) in next_cells.iter().enumerate() {
            let Some(previous_cell) = previous.cells.get(col) else {
                continue;
            };
            if previous_cell == next_cell {
                continue;
            }

            let key = (absolute_row, col);
            if next_cell.character == ' ' || next_cell.character == '\0' {
                self.pending.remove(&key);
                budget = max_pending_cells.saturating_sub(self.pending.len());
                continue;
            }

            if !self.pending.contains_key(&key) {
                if budget == 0 {
                    continue;
                }
                budget -= 1;
            }
            self.pending.insert(key, TypewriterReveal { reveal_at });
            reveal_at += interval;
        }

        self.next_reveal_at = Some(reveal_at);
    }

    fn enqueue_new_cells(
        &mut self,
        absolute_row: usize,
        next_cells: &[CellRenderData],
        now: Instant,
        cps: f32,
        max_pending_cells: usize,
    ) {
        let interval = Duration::from_secs_f64(1.0 / f64::from(cps.clamp(20.0, 2_000.0)));
        let mut reveal_at = self.next_reveal_at.unwrap_or(now).max(now);
        let mut queued = false;
        let mut budget = max_pending_cells.saturating_sub(self.pending.len());

        for (col, next_cell) in next_cells.iter().enumerate() {
            if next_cell.character == ' ' || next_cell.character == '\0' {
                continue;
            }
            let key = (absolute_row, col);
            if !self.pending.contains_key(&key) {
                if budget == 0 {
                    continue;
                }
                budget -= 1;
            }
            self.pending.insert(key, TypewriterReveal { reveal_at });
            reveal_at += interval;
            queued = true;
        }

        if queued {
            self.next_reveal_at = Some(reveal_at);
        }
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

#[derive(Clone)]
struct PendingRerunDiff {
    baseline_block_id: u64,
    command_text: String,
    baseline_output: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct FailureSummaryEntry {
    command: String,
    count: usize,
    last_exit_code: i32,
    last_completed_at_ms: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct FailureTrendEntry {
    command: String,
    cwd: String,
    branch: String,
    bucket_start_ms: u64,
    count: usize,
    last_exit_code: i32,
    last_completed_at_ms: u64,
}

struct SettingsEditorState {
    path: PathBuf,
    editor: InputEditor,
}

struct FilePreviewState {
    path: PathBuf,
    title: String,
    help: String,
    editor: InputEditor,
    search_active: bool,
    search_query: String,
    truncated: bool,
}

struct ScratchBufferState {
    path: PathBuf,
    editor: InputEditor,
}

#[derive(Clone)]
struct ContextMenuState {
    x: f32,
    y: f32,
    entries: Vec<ContextMenuEntry>,
    selected: usize,
    pane_id: PaneId,
    target_block_id: Option<u64>,
}

#[derive(Clone)]
struct ContextMenuEntry {
    label: String,
    description: String,
    action: ContextMenuAction,
}

#[derive(Clone)]
enum ContextMenuAction {
    Clipboard(ClipboardEffect),
    Palette(PaletteAction),
    BuiltIn(Action),
    Window(WindowContextAction),
    OpenUrl(String),
    CopyText(String, String),
}

#[derive(Clone)]
enum WindowContextAction {
    ToggleFullscreen,
    ToggleMaximized,
    Minimize,
}

#[derive(Clone, Copy)]
struct MouseBindingTarget {
    area: MouseBindingArea,
    tab_index: Option<usize>,
    pane_id: Option<PaneId>,
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
    pending_rerun_diff: Option<PendingRerunDiff>,
    typewriter: TypewriterState,
    pending_typewriter_block_id: Option<u64>,
}

#[derive(Clone, Copy)]
struct SessionEstimateCache {
    bytes: usize,
    refreshed_at: Instant,
}

const ATTACHED_DAEMON_PANE_ID: u64 = 0;
const DEFAULT_FAILURE_TREND_BUCKET_MS: u64 = 60 * 60 * 1000;
const REMOTE_RPC_SCHEMA_VERSION: &str = "1.0.0";
const MAX_GLOBAL_SEARCH_LINES: usize = 50_000;
const MAX_DIFF_INPUT_LINES: usize = 1_200;
const MAX_DIFF_ENTRIES: usize = 8_000;
const STATUS_BAR_GIT_CACHE_TTL: Duration = Duration::from_secs(2);
const SESSION_ESTIMATE_CACHE_TTL: Duration = Duration::from_secs(1);

fn typewriter_applies_to_row(
    blocks: &[Block],
    active_output_block_id: Option<u64>,
    absolute_row: usize,
) -> bool {
    let Some(active_output_block_id) = active_output_block_id else {
        return false;
    };
    blocks.iter().rev().any(|block| {
        if block.id != active_output_block_id {
            return false;
        }
        if block.exit_code.is_none() {
            absolute_row >= block.output_start_row
        } else {
            absolute_row >= block.output_start_row && absolute_row <= block.output_end_row
        }
    })
}

fn typewriter_is_active(enabled: bool, is_alt_screen: bool) -> bool {
    enabled && !is_alt_screen
}

fn mark_typewriter_pending_rows_dirty(pane: &mut PaneRuntime) {
    if !pane.typewriter.has_pending() {
        return;
    }
    let pending_rows = pane.typewriter.pending_rows().collect::<HashSet<_>>();
    if pending_rows.is_empty() {
        return;
    }
    for (row_idx, absolute_row) in pane.terminal.state.visible_rows().into_iter().enumerate() {
        if pending_rows.contains(&absolute_row) {
            pane.row_cache.dirty.mark_row_dirty(row_idx);
        }
    }
}

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

#[derive(Clone)]
struct GitStatusBarCacheEntry {
    fetched_at: Instant,
    text: Option<String>,
}

#[derive(Clone, Copy)]
enum FloatingDragMode {
    Move,
    Resize(FloatingResizeEdges),
}

#[derive(Clone, Copy)]
struct FloatingDragState {
    pane_id: PaneId,
    mode: FloatingDragMode,
    last_x: f64,
    last_y: f64,
}

#[derive(Clone)]
struct SplitDividerDragState {
    path: Vec<u8>,
    direction: SplitDirection,
    split_rect: Rect,
    last_x: f64,
    last_y: f64,
}

#[derive(Clone, Copy)]
enum TerminalMouseEvent {
    Press(MouseButton),
    Release,
    Motion(Option<MouseButton>),
    Wheel { horizontal: bool, positive: bool },
}

enum PathCursorAction {
    Preview,
    Open,
    Copy,
    Reveal,
    Tail,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct ParsedPathTarget {
    path: PathBuf,
    line: Option<usize>,
    column: Option<usize>,
}

struct RecentKeyEntry {
    label: String,
    at: Instant,
}

#[derive(Default)]
struct PhaseMetric {
    last_us: u64,
    avg_us: u64,
    max_us: u64,
    samples: VecDeque<u64>,
}

impl PhaseMetric {
    const SAMPLE_LIMIT: usize = 120;

    fn record(&mut self, duration: Duration) {
        let duration_us = duration.as_micros() as u64;
        self.last_us = duration_us;
        self.samples.push_back(duration_us);
        while self.samples.len() > Self::SAMPLE_LIMIT {
            self.samples.pop_front();
        }
        let total = self.samples.iter().copied().sum::<u64>();
        self.avg_us = total / self.samples.len().max(1) as u64;
        self.max_us = self.samples.iter().copied().max().unwrap_or(0);
    }

    fn last_ms(&self) -> f32 {
        self.last_us as f32 / 1000.0
    }

    fn avg_ms(&self) -> f32 {
        self.avg_us as f32 / 1000.0
    }

    fn max_ms(&self) -> f32 {
        self.max_us as f32 / 1000.0
    }
}

#[derive(Default)]
#[allow(dead_code)]
struct RuntimeMetrics {
    frame_count: u64,
    last_frame_duration_us: u64,
    pane_count: usize,
    replay_snapshot_count: usize,
    daemon_sync_lag_ms: Option<u64>,
    last_quad_count: usize,
    frame_tick: PhaseMetric,
    pty_drain: PhaseMetric,
    semantic_events: PhaseMetric,
    replay_capture: PhaseMetric,
    input_sync: PhaseMetric,
    output_hooks: PhaseMetric,
    block_query: PhaseMetric,
    quad_build: PhaseMetric,
    gpu_render: PhaseMetric,
    mark_clean: PhaseMetric,
}

impl RuntimeMetrics {
    fn summary_line(&self) -> String {
        let mut parts = vec![
            format!("frames:{}", self.frame_count),
            format!(
                "last_frame:{:.2}ms",
                self.last_frame_duration_us as f32 / 1000.0
            ),
            format!("panes:{}", self.pane_count),
            format!("replays:{}", self.replay_snapshot_count),
        ];
        if let Some(lag) = self.daemon_sync_lag_ms {
            parts.push(format!("sync_lag:{}ms", lag));
        }
        parts.join(" ")
    }

    fn phase_lines(&self) -> Vec<String> {
        vec![
            format!(
                "phase tick last {:.2} avg {:.2} max {:.2} ms",
                self.frame_tick.last_ms(),
                self.frame_tick.avg_ms(),
                self.frame_tick.max_ms()
            ),
            format!(
                "phase pty last {:.2} avg {:.2} max {:.2} ms",
                self.pty_drain.last_ms(),
                self.pty_drain.avg_ms(),
                self.pty_drain.max_ms()
            ),
            format!(
                "phase semantic last {:.2} avg {:.2} max {:.2} ms",
                self.semantic_events.last_ms(),
                self.semantic_events.avg_ms(),
                self.semantic_events.max_ms()
            ),
            format!(
                "phase replay last {:.2} avg {:.2} max {:.2} ms",
                self.replay_capture.last_ms(),
                self.replay_capture.avg_ms(),
                self.replay_capture.max_ms()
            ),
            format!(
                "phase input last {:.2} avg {:.2} max {:.2} ms",
                self.input_sync.last_ms(),
                self.input_sync.avg_ms(),
                self.input_sync.max_ms()
            ),
            format!(
                "phase hooks last {:.2} avg {:.2} max {:.2} ms",
                self.output_hooks.last_ms(),
                self.output_hooks.avg_ms(),
                self.output_hooks.max_ms()
            ),
            format!(
                "phase blockq last {:.2} avg {:.2} max {:.2} ms",
                self.block_query.last_ms(),
                self.block_query.avg_ms(),
                self.block_query.max_ms()
            ),
            format!(
                "phase quads last {:.2} avg {:.2} max {:.2} ms count {}",
                self.quad_build.last_ms(),
                self.quad_build.avg_ms(),
                self.quad_build.max_ms(),
                self.last_quad_count
            ),
            format!(
                "phase gpu last {:.2} avg {:.2} max {:.2} ms",
                self.gpu_render.last_ms(),
                self.gpu_render.avg_ms(),
                self.gpu_render.max_ms()
            ),
            format!(
                "phase clean last {:.2} avg {:.2} max {:.2} ms",
                self.mark_clean.last_ms(),
                self.mark_clean.avg_ms(),
                self.mark_clean.max_ms()
            ),
        ]
    }
}

fn measure_phase<T>(enabled: bool, total: &mut Duration, f: impl FnOnce() -> T) -> T {
    if enabled {
        let started = Instant::now();
        let result = f();
        *total += started.elapsed();
        result
    } else {
        f()
    }
}

#[derive(Clone)]
struct CommandTelemetryBlockSnapshot {
    block_id: u64,
    output_start_row: usize,
    output_end_row: usize,
    duration_ms: Option<u64>,
}

struct CommandTelemetryLogger {
    file: File,
}

impl CommandTelemetryLogger {
    fn new() -> Result<Self, std::io::Error> {
        let config_dir = WokConfig::config_dir();
        std::fs::create_dir_all(&config_dir)?;
        let path = config_dir.join("command-telemetry.jsonl");
        let file = OpenOptions::new().create(true).append(true).open(path)?;
        Ok(Self { file })
    }

    fn log_submitted(&mut self, pane_id: PaneId, command: &str, cwd: Option<&PathBuf>) {
        let command = command.trim();
        if command.is_empty() {
            return;
        }
        let cwd = cwd.map(|path| path.display().to_string());
        let payload = json!({
            "event": "command_submitted",
            "timestamp_ms": current_unix_ms(),
            "pane_id": pane_id,
            "command": command,
            "cwd": cwd,
        });
        self.write_payload(payload);
        info!(
            target: "wok::commands",
            pane_id,
            command,
            cwd = cwd.as_deref().unwrap_or(""),
            "command submitted"
        );
    }

    fn log_completed(
        &mut self,
        entry: &HistoryEntry,
        block: Option<&CommandTelemetryBlockSnapshot>,
    ) {
        let command = entry.command.trim();
        if command.is_empty() {
            return;
        }
        let cwd = entry.cwd.as_ref().map(|path| path.display().to_string());
        let block_id = block.map(|block| block.block_id);
        let output_start_row = block.map(|block| block.output_start_row);
        let output_end_row = block.map(|block| block.output_end_row);
        let duration_ms = entry
            .duration_ms
            .or_else(|| block.and_then(|block| block.duration_ms));
        let payload = json!({
            "event": "command_completed",
            "timestamp_ms": current_unix_ms(),
            "pane_id": entry.source_pane_id,
            "block_id": block_id,
            "command": command,
            "cwd": cwd,
            "exit_code": entry.exit_code,
            "duration_ms": duration_ms,
            "output_start_row": output_start_row,
            "output_end_row": output_end_row,
        });
        self.write_payload(payload);
        info!(
            target: "wok::commands",
            pane_id = ?entry.source_pane_id,
            block_id = ?block_id,
            command,
            cwd = cwd.as_deref().unwrap_or(""),
            exit_code = ?entry.exit_code,
            duration_ms = ?duration_ms,
            "command completed"
        );
    }

    fn write_payload(&mut self, payload: Value) {
        if let Err(error) = writeln!(self.file, "{payload}") {
            warn!("failed to write command telemetry: {error}");
        }
    }
}

fn current_unix_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_millis() as u64)
}

fn send_system_notification(
    notification: &SystemNotificationRequest,
) -> Result<(), Box<dyn Error>> {
    let n = wok_process::Notification {
        title: &notification.title,
        message: &notification.message,
        subtitle: notification.subtitle.as_deref(),
    };
    wok_process::notify(&n).map_err(|e| Box::new(e) as Box<dyn Error>)
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
    command_telemetry: Option<CommandTelemetryLogger>,
    remote_control: Option<RemoteControlServer>,
    remote_socket_path: Option<PathBuf>,
    remote_rpc_token: Option<String>,
    attached_session: Option<String>,
    daemon_pane_by_local: HashMap<PaneId, u64>,
    status_message: Option<String>,
    show_failure_trends_panel: bool,
    show_workspace_insights_panel: bool,
    settings_editor: Option<SettingsEditorState>,
    file_preview: Option<FilePreviewState>,
    scratch_buffer: Option<ScratchBufferState>,
    context_menu: Option<ContextMenuState>,
    failure_trend_bucket_ms: u64,
    status_bar_state: StatusBarState,
    git_status_bar_cache: RefCell<HashMap<PathBuf, GitStatusBarCacheEntry>>,
    status_bar_refresh_interval: Duration,
    last_status_bar_refresh: Instant,
    hovered_link: Option<String>,
    theme_watcher: Option<ThemeWatcher>,
    config_watcher: Option<wok_watcher::PathWatcher>,
    /// User keybinding overrides loaded from `~/.config/wok/keybindings.toml`.
    /// Applied to every pane's `KeybindingConfig` after construction.
    user_keybinding_overrides: Vec<wok_app::keybindings_toml::BindingOverride>,
    /// Watcher for `keybindings.toml` so saves apply live.
    keybindings_watcher: Option<wok_watcher::PathWatcher>,
    /// Action id currently waiting for the next key press in the keybinding editor.
    pending_keybinding_capture: Option<String>,
    /// Future-home of the entity-handle runtime. Currently empty; existing
    /// `WokHandler` substates are *not* migrated. This field gives downstream
    /// PRs a place to lift state into `Handle<T>` entities incrementally.
    #[allow(dead_code)]
    ui_core: wok_ui_core::App,
    background: BackgroundRenderer,
    media_preview: Option<MediaPreview>,
    font: FontSystem,
    render: Option<RenderState>,
    runtime_waker: Option<RuntimeWaker>,
    window: Option<Arc<Window>>,
    chrome_rects: ChromeRects,
    tab_scroll_offset: f32,
    needs_redraw: bool,
    exit_requested: bool,
    started_at: Instant,
    last_cursor_visible: bool,
    pending_close_confirmation: Option<Instant>,
    redraw_history_ms: VecDeque<f32>,
    frame_timestamps: VecDeque<Instant>,
    system_metrics: SystemMetricsSampler,
    theme_overrides: HashMap<String, String>,
    floating_drag: Option<FloatingDragState>,
    split_drag: Option<SplitDividerDragState>,
    pressed_mouse_button: Option<MouseButton>,
    recent_keys: VecDeque<RecentKeyEntry>,
    metrics: RuntimeMetrics,
    session_estimate_cache: Option<SessionEstimateCache>,
}

impl WokHandler {
    fn new(config: WokConfig) -> Self {
        let font = FontSystem::new(&config.font_family, config.font_size);
        let (workspace, _) = WorkspaceState::new("Wok");
        let plugins = PluginHost::new(
            &WokConfig::config_dir(),
            config.external_plugin_command.as_deref(),
        );
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
        let remote_rpc_token = std::env::var("WOK_RPC_TOKEN")
            .ok()
            .map(|token| token.trim().to_string())
            .filter(|token| !token.is_empty());
        let command_telemetry = if config.command_telemetry {
            match CommandTelemetryLogger::new() {
                Ok(logger) => Some(logger),
                Err(error) => {
                    warn!("failed to initialize command telemetry log: {error}");
                    None
                }
            }
        } else {
            None
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
            command_telemetry,
            remote_control,
            remote_socket_path,
            remote_rpc_token,
            attached_session: None,
            daemon_pane_by_local: HashMap::new(),
            status_message: None,
            show_failure_trends_panel: false,
            show_workspace_insights_panel: false,
            settings_editor: None,
            file_preview: None,
            scratch_buffer: None,
            context_menu: None,
            failure_trend_bucket_ms: DEFAULT_FAILURE_TREND_BUCKET_MS,
            status_bar_state: StatusBarState::default(),
            git_status_bar_cache: RefCell::new(HashMap::new()),
            status_bar_refresh_interval: Duration::from_secs(5),
            last_status_bar_refresh: Instant::now(),
            hovered_link: None,
            theme_watcher,
            config_watcher: wok_watcher::PathWatcher::new(
                &WokConfig::config_dir().join("config.toml"),
            )
            .ok(),
            user_keybinding_overrides: load_user_keybinding_overrides(),
            keybindings_watcher: wok_watcher::PathWatcher::new(
                &WokConfig::config_dir().join("keybindings.toml"),
            )
            .ok(),
            pending_keybinding_capture: None,
            ui_core: wok_ui_core::App::new(),
            background,
            media_preview: None,
            font,
            render: None,
            runtime_waker: None,
            window: None,
            chrome_rects: ChromeRects::default(),
            tab_scroll_offset: 0.0,
            needs_redraw: true,
            exit_requested: false,
            started_at: Instant::now(),
            last_cursor_visible: true,
            pending_close_confirmation: None,
            redraw_history_ms: VecDeque::with_capacity(60),
            frame_timestamps: VecDeque::with_capacity(120),
            system_metrics: SystemMetricsSampler::new(Duration::from_secs(2)),
            theme_overrides: HashMap::new(),
            floating_drag: None,
            split_drag: None,
            pressed_mouse_button: None,
            recent_keys: VecDeque::new(),
            metrics: RuntimeMetrics::default(),
            session_estimate_cache: None,
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

    fn log_command_submitted(&mut self, pane_id: PaneId, command: &str, cwd: Option<PathBuf>) {
        if let Some(logger) = self.command_telemetry.as_mut() {
            logger.log_submitted(pane_id, command, cwd.as_ref());
        }
    }

    fn log_command_completed(
        &mut self,
        entry: &HistoryEntry,
        block: Option<&CommandTelemetryBlockSnapshot>,
    ) {
        if let Some(logger) = self.command_telemetry.as_mut() {
            logger.log_completed(entry, block);
        }
    }

    fn compose_status_bar_segments(&self, pane: &PaneRuntime) -> StatusBarSegments {
        let mut state = self.status_bar_state.clone();
        state.shell = pane.app.config.shell.to_string();
        state.cwd = if !pane.current_cwd.as_os_str().is_empty() {
            pane.current_cwd.clone()
        } else {
            pane.app
                .block_manager
                .blocks
                .last()
                .map(|block| block.cwd.clone())
                .filter(|cwd| !cwd.as_os_str().is_empty())
                .unwrap_or_else(|| PathBuf::from("~"))
        };
        state.git_branch = pane
            .app
            .block_manager
            .blocks
            .last()
            .and_then(|block| block.git_branch.clone())
            .or_else(|| wok_ui::status_bar::detect_git_branch(&state.cwd));

        let mut left = vec![
            StatusSegment::plain(state.cwd.display().to_string()),
            StatusSegment::plain(state.shell.clone()),
        ];
        if let Some(git_text) = self.status_bar_git_text(&state.cwd, state.git_branch.as_deref()) {
            left.push(StatusSegment::plain(git_text));
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

    fn status_bar_git_text(&self, cwd: &PathBuf, fallback_branch: Option<&str>) -> Option<String> {
        if let Some(entry) = self.git_status_bar_cache.borrow().get(cwd) {
            if entry.fetched_at.elapsed() < STATUS_BAR_GIT_CACHE_TTL {
                return entry.text.clone();
            }
        }

        let text = match wok_git::service::load_status(cwd) {
            Ok(snapshot) => snapshot
                .branch
                .as_deref()
                .or(fallback_branch)
                .map(|branch| git_status_bar_text(branch, snapshot.files.len())),
            Err(wok_git::service::GitServiceError::NotGitRepository(_)) => {
                fallback_branch.map(|branch| git_status_bar_text(branch, 0))
            }
            Err(error) => {
                warn!("failed to load Git status for status bar: {error}");
                fallback_branch.map(|branch| git_status_bar_text(branch, 0))
            }
        };
        self.git_status_bar_cache.borrow_mut().insert(
            cwd.clone(),
            GitStatusBarCacheEntry {
                fetched_at: Instant::now(),
                text: text.clone(),
            },
        );
        text
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
        // user TOML overrides win over both defaults and plugin bindings.
        app.keybindings
            .apply_toml_overrides(self.user_keybinding_overrides.clone());
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

        match Terminal::new_with_wake_callback(
            &pane_config.shell,
            cols,
            rows,
            pane_config.scrollback_lines,
            env,
            initial_cwd,
            self.runtime_waker.as_ref().map(RuntimeWaker::wake_callback),
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
                    pending_rerun_diff: None,
                    typewriter: TypewriterState::default(),
                    pending_typewriter_block_id: None,
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
            self.config.tab_bar_side,
            self.config.status_bar_visible,
            self.config.status_bar_side,
            self.font.metrics.cell_height,
            self.config.tab_bar_size,
            self.config.status_bar_size,
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
        self.ensure_active_tab_visible();
        self.sync_media_preview_frame();
    }

    fn clamp_tab_scroll(&mut self) {
        let tab_labels = self.tab_labels_for_render();
        let max_scroll = tab_bar_max_scroll(
            self.chrome_rects.tab_bar,
            &tab_labels,
            self.font.metrics.cell_width,
            self.config.tab_bar_side.tab_orientation(),
        );
        self.tab_scroll_offset = self.tab_scroll_offset.clamp(0.0, max_scroll);
    }

    fn ensure_active_tab_visible(&mut self) {
        if !self.config.tab_bar_visible || self.workspace.tabs.is_empty() {
            self.tab_scroll_offset = 0.0;
            return;
        }

        let tab_labels = self.tab_labels_for_render();
        let Some((active_start, active_end)) = tab_bar_tab_range(
            &tab_labels,
            self.workspace.active_tab,
            self.font.metrics.cell_width,
            self.config.tab_bar_side.tab_orientation(),
        ) else {
            self.tab_scroll_offset = 0.0;
            return;
        };
        let visible_extent = match self.config.tab_bar_side.tab_orientation() {
            wok_app::config::TabBarOrientation::Horizontal => self.chrome_rects.tab_bar.w,
            wok_app::config::TabBarOrientation::Vertical => self.chrome_rects.tab_bar.h,
        };
        if active_start < self.tab_scroll_offset {
            self.tab_scroll_offset = active_start;
        } else if active_end > self.tab_scroll_offset + visible_extent {
            self.tab_scroll_offset = active_end - visible_extent;
        }
        self.clamp_tab_scroll();
    }

    fn tab_at_point(&self, x: f64, y: f64) -> Option<usize> {
        if !self.config.tab_bar_visible || self.workspace.tabs.is_empty() {
            return None;
        }
        let rect = self.chrome_rects.tab_bar;
        if x < f64::from(rect.x)
            || y < f64::from(rect.y)
            || x > f64::from(rect.x + rect.w)
            || y > f64::from(rect.y + rect.h)
        {
            return None;
        }

        let tab_labels = self.tab_labels_for_render();
        tab_bar_index_at_point(
            rect,
            &tab_labels,
            self.tab_scroll_offset,
            x as f32,
            y as f32,
            self.font.metrics.cell_width,
            self.config.tab_bar_side.tab_orientation(),
        )
    }

    fn scroll_tab_bar(&mut self, delta_x: f64, delta_y: f64) -> bool {
        if !self.config.tab_bar_visible || self.workspace.tabs.is_empty() {
            return false;
        }
        let delta = if delta_x.abs() > f64::EPSILON {
            delta_x
        } else {
            delta_y
        };
        if delta.abs() <= f64::EPSILON {
            return false;
        }

        let unit = if delta.abs() < 8.0 { 48.0 } else { 1.0 };
        self.tab_scroll_offset -= delta as f32 * unit;
        self.clamp_tab_scroll();
        self.needs_redraw = true;
        true
    }

    fn switch_to_tab_index(&mut self, index: usize) {
        if index >= self.workspace.tabs.len() || index == self.workspace.active_tab {
            return;
        }
        let search = self.active_search_state();
        self.workspace.switch_tab(index);
        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
        if let Some(search) = search {
            self.install_search_state_on_active_pane(search);
            self.refresh_global_search();
        }
        self.ensure_active_tab_visible();
        self.needs_redraw = true;
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
            schema_version: 1,
            saved_at_unix_ms: current_time_ms(),
            wok_version: env!("CARGO_PKG_VERSION").to_string(),
            workspace_description: String::new(),
            workspace_tags: Vec::new(),
            tabs,
            panes,
            active_tab: self.workspace.active_tab,
            window_size,
            window_position,
            show_failure_trends_panel: self.show_failure_trends_panel,
            show_workspace_insights_panel: self.show_workspace_insights_panel,
            failure_trend_bucket_ms: self.failure_trend_bucket_ms,
        }
    }

    fn restore_session(&mut self, session: WorkspaceSessionState) {
        let WorkspaceSessionState {
            schema_version: _,
            saved_at_unix_ms: _,
            wok_version: _,
            workspace_description: _,
            workspace_tags: _,
            tabs,
            panes,
            active_tab,
            window_size,
            window_position,
            show_failure_trends_panel,
            show_workspace_insights_panel,
            failure_trend_bucket_ms,
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
        self.show_failure_trends_panel = show_failure_trends_panel;
        self.show_workspace_insights_panel = show_workspace_insights_panel;
        self.failure_trend_bucket_ms = failure_trend_bucket_ms.max(60_000);
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
        let tab_labels = self.tab_labels_for_render();
        let status_segments = self
            .active_pane()
            .map(|active_pane| self.compose_status_bar_segments(active_pane));
        let workspace_search = self.active_search_state();
        self.ensure_active_tab_visible();
        self.clamp_tab_scroll();
        let cursor_shape = self.cursor_shape();
        let cursor_visible = self.cursor_visible();
        let window_opacity = self.config.window_opacity.clamp(0.0, 1.0);
        let background_image = self.background.image.clone();
        let background_loaded = background_image.is_some();
        let background_image_size = background_image
            .as_ref()
            .map(|image| (image.width, image.height));
        let show_failure_trends_panel = self.show_failure_trends_panel;
        let show_workspace_insights_panel = self.show_workspace_insights_panel;
        let failure_trend_bucket_ms = self.failure_trend_bucket_ms;
        let debug_overlay_lines = if self.config.debug_overlay {
            Some(self.debug_overlay_lines())
        } else {
            None
        };
        let command_palette_overlay = self.active_pane().and_then(|pane| {
            (pane.app.input_mode == InputMode::CommandPalette).then(|| {
                (
                    pane.app.theme.clone(),
                    pane.app.input_editor.render_data(),
                    pane.app.command_palette.clone(),
                )
            })
        });
        let settings_editor_overlay = self.settings_editor.as_ref().map(|settings| {
            (
                self.active_pane()
                    .map_or_else(Theme::default, |pane| pane.app.theme.clone()),
                settings.path.clone(),
                settings.editor.render_data(),
            )
        });
        let file_preview_overlay = self.file_preview.as_ref().map(|preview| {
            (
                self.active_pane()
                    .map_or_else(Theme::default, |pane| pane.app.theme.clone()),
                preview.title.clone(),
                preview.path.clone(),
                if preview.search_active {
                    format!(
                        "Search: {}  Enter next  Esc exit search",
                        if preview.search_query.is_empty() {
                            "(type query)"
                        } else {
                            preview.search_query.as_str()
                        }
                    )
                } else if preview.truncated {
                    format!("{}  truncated", preview.help)
                } else {
                    preview.help.clone()
                },
                preview.editor.render_data(),
            )
        });
        let scratch_overlay = self.scratch_buffer.as_ref().map(|scratch| {
            (
                self.active_pane()
                    .map_or_else(Theme::default, |pane| pane.app.theme.clone()),
                scratch.path.clone(),
                scratch.editor.render_data(),
            )
        });
        let context_menu_overlay = self.context_menu.as_ref().map(|menu| {
            (
                self.active_pane()
                    .map_or_else(Theme::default, |pane| pane.app.theme.clone()),
                menu.clone(),
            )
        });
        let recent_keys_overlay = if self.config.recent_keys.visible {
            let labels = self.recent_key_labels();
            (!labels.is_empty()).then(|| {
                (
                    self.active_pane()
                        .map_or_else(Theme::default, |pane| pane.app.theme.clone()),
                    labels,
                    self.config.recent_keys.position,
                    self.config.recent_keys.opacity,
                )
            })
        } else {
            None
        };
        let full_width = self.chrome_rects.content.x + self.chrome_rects.content.w;
        let full_height =
            self.chrome_rects.content.y + self.chrome_rects.content.h + self.chrome_rects.status.h;
        let full_rect = Rect::new(0.0, 0.0, full_width, full_height);
        let render_time = Instant::now();
        let typewriter_enabled = self.config.typewriter_effect_enabled;
        let typewriter_cps = self.config.typewriter_effect_cps;
        let typewriter_max_pending_cells = self.config.typewriter_effect_max_pending_cells;
        let visual_effect = VisualEffectState::from_config(&self.config, self.started_at.elapsed());
        let Some(render) = self.render.as_mut() else {
            return;
        };

        render.batch.clear();
        if let Some(image_size) = background_image_size {
            push_background_image(
                &mut render.batch,
                full_rect,
                image_size,
                &self.config,
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
            let mut visible_rows = pane.terminal.state.visible_rows();
            let total_cols = pane.terminal.state.columns();
            let smooth_scroll_y =
                pane.viewport.render_translation_rows() * self.font.metrics.cell_height;
            if smooth_scroll_y < -f32::EPSILON {
                if let Some(next_row) = visible_rows.last().copied().and_then(|row| {
                    let next = row + 1;
                    (next < pane.terminal.state.total_rows()).then_some(next)
                }) {
                    visible_rows.push(next_row);
                }
            }
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
            let terminal_surface_alpha =
                if let Some(opacity) = self.config.terminal_background_opacity {
                    (window_opacity * theme.opacity * opacity).clamp(0.0, 1.0)
                } else if background_loaded {
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
                        let title_height = self.config.floating_pane_title_height;
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
            let active_output_block_id = pane.app.block_manager.active_output_block_id();
            let typewriter_block_id = active_output_block_id.or(pane.pending_typewriter_block_id);
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

            let terminal_damage = if pane.terminal.is_dirty() {
                Some(pane.terminal.take_damage())
            } else {
                None
            };
            let terminal_had_damage = terminal_damage.is_some();
            let terminal_full_damage =
                matches!(terminal_damage.as_ref(), Some(TerminalDamage::Full));
            let typewriter_active =
                typewriter_is_active(typewriter_enabled, pane.terminal.state.is_alt_screen());
            if typewriter_enabled && !typewriter_active && pane.typewriter.has_pending() {
                pane.typewriter.clear();
                pane.row_cache.dirty.mark_fully_damaged();
            }
            if pane.viewport.needs_render() || terminal_full_damage {
                for (row_idx, absolute_row) in visible_rows.iter().copied().enumerate() {
                    let previous_signature = pane.row_cache.row_signatures[row_idx].clone();
                    let signature = PaneRowSignature {
                        absolute_row,
                        render_row: row_positions.get(row_idx).copied().flatten(),
                        cells: collect_row_cells(&pane.terminal, absolute_row, total_cols),
                    };
                    if pane.row_cache.row_signatures[row_idx].as_ref() != Some(&signature) {
                        if typewriter_active
                            && terminal_had_damage
                            && typewriter_applies_to_row(
                                &pane.app.block_manager.blocks,
                                typewriter_block_id,
                                absolute_row,
                            )
                        {
                            pane.typewriter.enqueue_changed_cells(
                                absolute_row,
                                previous_signature.as_ref(),
                                &signature.cells,
                                render_time,
                                typewriter_cps,
                                typewriter_max_pending_cells,
                            );
                        }
                        pane.row_cache.row_signatures[row_idx] = Some(signature);
                        pane.row_cache.dirty.mark_row_dirty(row_idx);
                    }
                }
            } else if let Some(TerminalDamage::Rows(rows)) = terminal_damage {
                for row_idx in rows {
                    let Some(absolute_row) = visible_rows.get(row_idx).copied() else {
                        continue;
                    };
                    let previous_signature = pane.row_cache.row_signatures[row_idx].clone();
                    let signature = PaneRowSignature {
                        absolute_row,
                        render_row: row_positions.get(row_idx).copied().flatten(),
                        cells: collect_row_cells(&pane.terminal, absolute_row, total_cols),
                    };
                    if pane.row_cache.row_signatures[row_idx].as_ref() != Some(&signature) {
                        if typewriter_active
                            && typewriter_applies_to_row(
                                &pane.app.block_manager.blocks,
                                typewriter_block_id,
                                absolute_row,
                            )
                        {
                            pane.typewriter.enqueue_changed_cells(
                                absolute_row,
                                previous_signature.as_ref(),
                                &signature.cells,
                                render_time,
                                typewriter_cps,
                                typewriter_max_pending_cells,
                            );
                        }
                        pane.row_cache.row_signatures[row_idx] = Some(signature);
                        pane.row_cache.dirty.mark_row_dirty(row_idx);
                    }
                }
            }
            if pane.pending_typewriter_block_id.is_some()
                && pane.pending_typewriter_block_id != active_output_block_id
            {
                pane.pending_typewriter_block_id = None;
            }

            if pane.row_cache.dirty.has_damage() {
                let blocks = &pane.app.block_manager.blocks;
                let terminal = &pane.terminal;
                let row_cache = &mut pane.row_cache;
                let typewriter = typewriter_active.then_some(&pane.typewriter);
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
                        visual_effect,
                        typewriter,
                        render_time,
                    );
                }
                row_cache.dirty.clear();
            }

            if typewriter_enabled {
                pane.typewriter.prune_revealed(render_time);
            }

            for row_batch in pane.row_cache.row_batches.iter().take(visible_rows.len()) {
                render
                    .batch
                    .append_translated(row_batch, 0.0, smooth_scroll_y);
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
            let border_width = self.config.pane_border_width;
            if border_width > 0.0 {
                render.batch.push_bg_quad(
                    viewport.x,
                    viewport.y,
                    viewport.w,
                    border_width,
                    border_color,
                );
                render.batch.push_bg_quad(
                    viewport.x,
                    viewport.y,
                    border_width,
                    viewport.h,
                    border_color,
                );
            }
            if focused {
                let focused_border_width = self.config.focused_pane_border_width;
                if focused_border_width > 0.0 {
                    render.batch.push_bg_quad(
                        viewport.x,
                        viewport.y,
                        viewport.w,
                        focused_border_width,
                        [
                            theme.highlight_current_match.r,
                            theme.highlight_current_match.g,
                            theme.highlight_current_match.b,
                            0.8,
                        ],
                    );
                }
            }
            if let Some(floating) = floating.as_ref() {
                let title_height = self.config.floating_pane_title_height;
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
                let border_width = self.config.pane_border_width;
                if border_width > 0.0 {
                    render.batch.push_bg_quad(
                        viewport.x + viewport.w - border_width,
                        viewport.y,
                        border_width,
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
                        viewport.y + viewport.h - border_width,
                        viewport.w,
                        border_width,
                        [
                            theme.block_separator.r,
                            theme.block_separator.g,
                            theme.block_separator.b,
                            0.9,
                        ],
                    );
                }
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
                                    viewport.y + render_row as f32 * ch + smooth_scroll_y,
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
                                viewport.y + render_row as f32 * ch + smooth_scroll_y,
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
                    let cursor_y = viewport.y + cursor_row as f32 * ch + smooth_scroll_y;
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
                    let target_block = pane
                        .app
                        .block_manager
                        .get_block(block_query_state.target_block_id)
                        .cloned();
                    if target_block.is_none() && !block_query_state.is_external_diff() {
                        pane.app.block_query = None;
                        continue;
                    }
                    let filtered_lines = if matches!(
                        block_query_state.mode,
                        BlockQueryMode::Filter | BlockQueryMode::Diff
                    ) {
                        let max_visible_lines = filter_overlay_visible_lines(
                            pane.ui_rects.viewport,
                            self.font.metrics.cell_height,
                        );
                        block_query_state.ensure_current_line_visible(max_visible_lines);
                        if matches!(block_query_state.mode, BlockQueryMode::Diff) {
                            Vec::new()
                        } else {
                            target_block
                                .as_ref()
                                .map(|target_block| {
                                    block_query_state
                                        .filtered_line_indices()
                                        .into_iter()
                                        .filter_map(|line_idx| {
                                            let absolute_row =
                                                target_block.output_start_row + line_idx;
                                            (absolute_row <= target_block.output_end_row).then(
                                                || {
                                                    (
                                                        line_idx,
                                                        pane.terminal.state.row_text(absolute_row),
                                                    )
                                                },
                                            )
                                        })
                                        .collect::<Vec<_>>()
                                })
                                .unwrap_or_default()
                        }
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

            if focused && show_failure_trends_panel {
                let rows = failure_trend_panel_lines(
                    &pane.pane_history,
                    &pane.app.block_manager.blocks,
                    failure_trend_bucket_ms,
                    10,
                );
                render_failure_trends_overlay(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.viewport,
                    &rows,
                    failure_trend_bucket_ms,
                    window_opacity,
                );
            }

            if focused && show_workspace_insights_panel {
                let rows = workspace_insight_panel_lines(
                    &pane.pane_history,
                    &pane.app.block_manager.blocks,
                    10,
                );
                render_workspace_insights_overlay(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.viewport,
                    &rows,
                    window_opacity,
                );
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

        if self.config.tab_bar_visible {
            render_tab_bar(
                render,
                &mut self.font,
                self.chrome_rects.tab_bar,
                &tab_labels,
                self.tab_scroll_offset,
                self.config.tab_bar_side.tab_orientation(),
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

        if let Some((theme, input, palette)) = command_palette_overlay.as_ref() {
            render_command_palette(
                render,
                &mut self.font,
                theme,
                self.chrome_rects.content,
                input,
                palette,
                cursor_shape,
                cursor_visible,
                window_opacity,
            );
        }
        if let Some((theme, path, input)) = settings_editor_overlay.as_ref() {
            render_settings_editor(
                render,
                &mut self.font,
                theme,
                self.chrome_rects.content,
                "Settings",
                path,
                "Esc close  Mod+S save  Enter newline",
                input,
                cursor_shape,
                cursor_visible,
                window_opacity,
            );
        }
        if let Some((theme, title, path, help, input)) = file_preview_overlay.as_ref() {
            render_settings_editor(
                render,
                &mut self.font,
                theme,
                self.chrome_rects.content,
                title,
                path,
                help,
                input,
                cursor_shape,
                false,
                window_opacity,
            );
        }
        if let Some((theme, path, input)) = scratch_overlay.as_ref() {
            render_settings_editor(
                render,
                &mut self.font,
                theme,
                self.chrome_rects.content,
                "Scratch",
                path,
                "Esc close  Mod+S save  Enter newline",
                input,
                cursor_shape,
                cursor_visible,
                window_opacity,
            );
        }
        if let Some((theme, menu)) = context_menu_overlay.as_ref() {
            render_context_menu(
                render,
                &mut self.font,
                theme,
                self.chrome_rects.content,
                menu,
                window_opacity,
            );
        }
        if let Some((theme, labels, position, opacity)) = recent_keys_overlay.as_ref() {
            render_recent_keys_overlay(
                render,
                &mut self.font,
                theme,
                self.chrome_rects.content,
                labels,
                *position,
                *opacity,
                window_opacity,
            );
        }
    }

    fn tab_labels_for_render(&self) -> Vec<(bool, String)> {
        let active_pane_id = self.active_pane_id();
        self.workspace
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
            .collect()
    }

    fn recent_key_labels(&self) -> Vec<String> {
        if !self.config.recent_keys.visible {
            return Vec::new();
        }
        self.recent_keys
            .iter()
            .map(|entry| entry.label.clone())
            .collect()
    }

    fn record_recent_key(&mut self, event: &InputEvent) {
        if !self.config.recent_keys.visible || event.event_type == InputEventType::Release {
            return;
        }
        let max_entries = self.config.recent_keys.max_entries.min(64);
        if max_entries == 0 {
            self.recent_keys.clear();
            return;
        }
        let combo = wok_app::keybindings::KeyCombo {
            key: event.action.clone(),
            modifiers: event.modifiers,
        };
        self.recent_keys.push_back(RecentKeyEntry {
            label: key_combo_label(&combo),
            at: Instant::now(),
        });
        while self.recent_keys.len() > max_entries {
            self.recent_keys.pop_front();
        }
        self.needs_redraw = true;
    }

    fn prune_recent_keys(&mut self) {
        if self.recent_keys.is_empty() {
            return;
        }
        if !self.config.recent_keys.visible || self.config.recent_keys.max_entries == 0 {
            self.recent_keys.clear();
            self.needs_redraw = true;
            return;
        }
        let timeout = Duration::from_millis(self.config.recent_keys.timeout_ms);
        let before = self.recent_keys.len();
        while self
            .recent_keys
            .front()
            .is_some_and(|entry| entry.at.elapsed() >= timeout)
        {
            self.recent_keys.pop_front();
        }
        if self.recent_keys.len() != before {
            self.needs_redraw = true;
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

    fn pane_exit_hook_payload(&self, pane_id: PaneId) -> serde_json::Value {
        let mut payload = self.pane_hook_payload(pane_id);
        if let Some(object) = payload.as_object_mut() {
            let exit_code = self
                .panes
                .get(&pane_id)
                .and_then(|pane| pane.terminal.exit_code);
            object.insert("exit_code".to_string(), json!(exit_code));
        }
        payload
    }

    fn tab_done_hook_payload(&self, tab_index: usize) -> serde_json::Value {
        let tab = self.workspace.tabs.get(tab_index);
        let pane_ids = self.workspace.pane_ids_for_tab_index(tab_index);
        let pane_count = pane_ids.len();
        json!({
            "tab_index": tab_index,
            "tab_id": tab.map(|tab| tab.id),
            "tab_title": tab.map(|tab| tab.title.clone()),
            "pane_ids": pane_ids,
            "pane_count": pane_count,
            "is_active_tab": self.workspace.active_tab == tab_index,
        })
    }

    fn dispatch_shell_completion_hooks(&mut self, exited_pane_ids: &[PaneId]) {
        if exited_pane_ids.is_empty() {
            return;
        }

        let mut events = Vec::new();
        let mut seen_panes = HashSet::new();
        let mut candidate_tabs = HashSet::new();
        for pane_id in exited_pane_ids.iter().copied() {
            if !seen_panes.insert(pane_id)
                || !self
                    .panes
                    .get(&pane_id)
                    .is_some_and(|pane| pane.terminal.exited)
            {
                continue;
            }

            events.push(("pane_exited", self.pane_exit_hook_payload(pane_id)));
            if let Some(tab_index) = self.workspace.find_tab_index_for_pane(pane_id) {
                candidate_tabs.insert(tab_index);
            }
        }

        for tab_index in candidate_tabs {
            let pane_ids = self.workspace.pane_ids_for_tab_index(tab_index);
            let tab_done = !pane_ids.is_empty()
                && pane_ids.iter().all(|pane_id| {
                    self.panes
                        .get(pane_id)
                        .is_some_and(|pane| pane.terminal.exited)
                });
            if tab_done {
                events.push(("tab_done", self.tab_done_hook_payload(tab_index)));
            }
        }

        for (hook, payload) in events {
            self.run_plugin_hook(hook, &payload);
        }
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
        let Some((target_block_id, mode, query)) = self.panes.get(&pane_id).and_then(|pane| {
            pane.app
                .block_query
                .as_ref()
                .map(|state| (state.target_block_id, state.mode, state.query.clone()))
        }) else {
            return;
        };

        if self
            .panes
            .get(&pane_id)
            .and_then(|pane| pane.app.block_query.as_ref())
            .is_some_and(BlockQueryState::is_external_diff)
        {
            return;
        }

        if matches!(mode, BlockQueryMode::Diff) {
            let Some((baseline_block_id, entries)) = self
                .panes
                .get(&pane_id)
                .and_then(|pane| build_block_diff_for_target(pane, target_block_id))
            else {
                if let Some(pane) = self.panes.get_mut(&pane_id) {
                    pane.app.block_query = None;
                }
                return;
            };

            if let Some(pane) = self.panes.get_mut(&pane_id) {
                if let Some(state) = pane.app.block_query.as_mut() {
                    if state.target_block_id == target_block_id
                        && matches!(state.mode, BlockQueryMode::Diff)
                    {
                        state.set_diff_entries(baseline_block_id, entries);
                    }
                }
            }
            self.scroll_to_current_block_query_match();
            return;
        }

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
            if lines.len() >= MAX_GLOBAL_SEARCH_LINES {
                lines.truncate(MAX_GLOBAL_SEARCH_LINES);
                break;
            }
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

    fn debug_overlay_lines(&mut self) -> Vec<String> {
        let active_scrollback = self
            .active_pane()
            .map_or(0, |pane| pane.terminal.state.scrollback_len());
        let typewriter_line = self.active_pane().map_or_else(
            || {
                format!(
                    "typewriter enabled={} active_block=n/a active_output=n/a pending_block=n/a queue=0 cells 0 rows cap={}",
                    self.config.typewriter_effect_enabled,
                    self.config.typewriter_effect_max_pending_cells
                )
            },
            |pane| {
                let active_block = pane
                    .app
                    .block_manager
                    .active_block
                    .map_or_else(|| "n/a".to_string(), |id| id.to_string());
                let active_output = pane
                    .app
                    .block_manager
                    .active_output_block_id()
                    .map_or_else(|| "n/a".to_string(), |id| id.to_string());
                let pending_block = pane
                    .pending_typewriter_block_id
                    .map_or_else(|| "n/a".to_string(), |id| id.to_string());
                format!(
                    "typewriter enabled={} active_block={} active_output={} pending_block={} queue={} cells {} rows cap={}",
                    self.config.typewriter_effect_enabled,
                    active_block,
                    active_output,
                    pending_block,
                    pane.typewriter.pending_cell_count(),
                    pane.typewriter.pending_row_count(),
                    self.config.typewriter_effect_max_pending_cells
                )
            },
        );
        let total_session_bytes = self.cached_estimated_session_bytes(Instant::now());
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
        let fps = self.current_fps();
        let system = self.system_metrics.snapshot();
        let memory_percent = percent(system.memory_used_bytes, system.memory_total_bytes);
        let disk_used = system
            .disk_total_bytes
            .saturating_sub(system.disk_available_bytes);
        let disk_percent = percent(disk_used, system.disk_total_bytes);
        let app_memory = system
            .app_memory_bytes
            .map(format_bytes)
            .unwrap_or_else(|| "n/a".to_string());
        let app_cpu = system
            .app_cpu_usage_percent
            .map(|cpu| format!("{cpu:.1}%"))
            .unwrap_or_else(|| "n/a".to_string());
        let app_disk = match (system.app_disk_read_bytes, system.app_disk_written_bytes) {
            (Some(read), Some(written)) => {
                format!("r {} w {}", format_bytes(read), format_bytes(written))
            }
            _ => "n/a".to_string(),
        };
        let battery = system
            .battery
            .as_ref()
            .map(|battery| {
                let percent = battery
                    .percent
                    .map(|percent| format!("{percent:.0}%"))
                    .unwrap_or_else(|| "n/a".to_string());
                let state = battery.state.as_deref().unwrap_or("unknown");
                let remaining = battery.time_remaining.as_deref().unwrap_or("n/a");
                format!("{percent} {state} {remaining}")
            })
            .unwrap_or_else(|| "n/a".to_string());
        let gpu_line = self.render.as_ref().map_or_else(
            || "gpu n/a".to_string(),
            |render| {
                let info = render.gpu.adapter_info();
                format!(
                    "gpu {} {:?} {:?}",
                    truncate_metric_text(&info.name, 28),
                    info.backend,
                    info.device_type
                )
            },
        );

        let mut lines = vec![
            format!("fps {:.1} redraw {:.2} ms", fps, avg_redraw_ms),
            format!("atlas {} glyphs {:.1}% full", atlas_entries, atlas_usage),
            format!("cpu sys {:.1}% app {app_cpu}", system.cpu_usage_percent),
            format!(
                "mem sys {} / {} ({memory_percent:.1}%) app {app_memory}",
                format_bytes(system.memory_used_bytes),
                format_bytes(system.memory_total_bytes)
            ),
            format!(
                "disk sys {} / {} ({disk_percent:.1}%) app {app_disk}",
                format_bytes(disk_used),
                format_bytes(system.disk_total_bytes)
            ),
            gpu_line,
            "gpu util n/a (wgpu does not expose cross-platform utilization)".to_string(),
            format!("battery {battery}"),
            format!("scrollback {} rows", active_scrollback),
            format!("session ~{} KiB", total_session_bytes / 1024),
            typewriter_line,
            self.metrics.summary_line(),
        ];
        lines.extend(self.metrics.phase_lines());
        for warning in &system.warnings {
            lines.push(format!("warn {warning}"));
        }
        lines
    }

    fn current_fps(&self) -> f32 {
        let Some(first) = self.frame_timestamps.front() else {
            return 0.0;
        };
        let Some(last) = self.frame_timestamps.back() else {
            return 0.0;
        };
        let elapsed = last.duration_since(*first).as_secs_f32();
        if elapsed <= f32::EPSILON || self.frame_timestamps.len() < 2 {
            0.0
        } else {
            (self.frame_timestamps.len() - 1) as f32 / elapsed
        }
    }

    fn cached_estimated_session_bytes(&mut self, now: Instant) -> usize {
        if let Some(cache) = self.session_estimate_cache {
            if now.duration_since(cache.refreshed_at) < SESSION_ESTIMATE_CACHE_TTL {
                return cache.bytes;
            }
        }

        let bytes = self.estimated_session_bytes();
        self.session_estimate_cache = Some(SessionEstimateCache {
            bytes,
            refreshed_at: now,
        });
        bytes
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

    fn running_process_count(&self) -> usize {
        self.panes
            .values()
            .filter(|pane| !pane.terminal.exited)
            .count()
    }

    /// Toggle the active pane's "show only failed" block filter using
    /// `wok_blocks::filter::failed_only`. Reports the resulting count.
    fn toggle_failed_only_filter(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let blocks_snapshot: Vec<_> = self
            .panes
            .get(&pane_id)
            .map(|p| p.app.block_manager.blocks.clone())
            .unwrap_or_default();
        let filter = wok_blocks::filter::failed_only();
        let matched = wok_blocks::filter::apply(&blocks_snapshot, &filter);
        if matched.is_empty() {
            self.status_message = Some("no failed blocks in this pane".to_string());
        } else {
            self.status_message = Some(format!("{} failed block(s) in this pane", matched.len()));
        }
    }

    fn handle_shell_exit_transitions(&mut self, exited_pane_ids: &[PaneId]) -> bool {
        if exited_pane_ids.is_empty()
            || !self.config.close_on_shell_exit
            || self.attached_session.is_some()
        {
            return false;
        }

        if !self.panes.is_empty() && self.panes.values().all(|pane| pane.terminal.exited) {
            self.exit_requested = true;
            return false;
        }

        let mut relayout = false;
        let mut seen = HashSet::new();
        for pane_id in exited_pane_ids.iter().copied() {
            if !seen.insert(pane_id)
                || !self
                    .panes
                    .get(&pane_id)
                    .is_some_and(|pane| pane.terminal.exited)
            {
                continue;
            }

            if let Some(removed_pane) = self.workspace.close_pane(pane_id) {
                self.panes.remove(&removed_pane);
                relayout = true;
                continue;
            }

            let Some(tab_index) = self.workspace.find_tab_index_for_pane(pane_id) else {
                continue;
            };
            let tab_pane_ids = self.workspace.pane_ids_for_tab_index(tab_index);
            let tab_has_only_exited_panes = !tab_pane_ids.is_empty()
                && tab_pane_ids.iter().all(|tab_pane_id| {
                    self.panes
                        .get(tab_pane_id)
                        .is_some_and(|pane| pane.terminal.exited)
                });
            if !tab_has_only_exited_panes {
                continue;
            }

            if let Some(removed_panes) = self.workspace.close_tab(tab_index) {
                for removed_pane in removed_panes {
                    self.panes.remove(&removed_pane);
                }
                relayout = true;
            }
        }

        if self.panes.is_empty() || self.panes.values().all(|pane| pane.terminal.exited) {
            self.exit_requested = true;
        } else if relayout {
            self.status_message = Some("Closed exited shell".to_string());
            self.needs_redraw = true;
        }

        relayout
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
        plugins.update_snapshot(&self.plugin_snapshot());
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
            "tab_bar_orientation": match self.config.tab_bar_side.tab_orientation() {
                wok_app::config::TabBarOrientation::Horizontal => "horizontal",
                wok_app::config::TabBarOrientation::Vertical => "vertical",
            },
            "tab_bar_side": self.config.tab_bar_side.as_str(),
            "status_bar_side": self.config.status_bar_side.as_str(),
            "recent_keys_visible": self.config.recent_keys.visible,
            "recent_keys_position": self.config.recent_keys.position.as_str(),
            "typewriter_effect_enabled": self.config.typewriter_effect_enabled,
            "typewriter_effect_cps": self.config.typewriter_effect_cps,
            "typewriter_effect_max_pending_cells": self.config.typewriter_effect_max_pending_cells,
            "close_on_shell_exit": self.config.close_on_shell_exit,
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
                // Last 200 global history entries, for wok.history.entries().
                "history": self
                    .global_history
                    .entries()
                    .iter()
                    .rev()
                    .take(200)
                    .rev()
                    .map(|e| json!({
                        "command": e.command,
                        "cwd": e.cwd.as_ref().map(|p| p.display().to_string()),
                        "started_at_ms": e.started_at_ms,
                        "completed_at_ms": e.completed_at_ms,
                        "exit_code": e.exit_code,
                        "duration_ms": e.duration_ms,
                    }))
                    .collect::<Vec<_>>(),
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
                // Last 100 blocks of the active pane, for wok.blocks.list().
                "blocks": pane
                    .map(|pane| {
                        pane.app
                            .block_manager
                            .blocks
                            .iter()
                            .rev()
                            .take(100)
                            .rev()
                            .map(|b| json!({
                                "id": b.id,
                                "command": b.command_text,
                                "cwd": b.cwd.display().to_string(),
                                "exit_code": b.exit_code,
                                "duration_ms": b.duration.map(|d| d.as_millis() as u64),
                                "is_bookmarked": b.is_bookmarked,
                                "git_branch": b.git_branch.clone(),
                            }))
                            .collect::<Vec<_>>()
                    })
                    .unwrap_or_default(),
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
        for notification in effects.system_notifications {
            if let Err(error) = send_system_notification(&notification) {
                warn!("failed to send system notification: {error}");
                self.status_message = Some(format!("System notification failed: {error}"));
            }
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
        for request in effects.setup_requests {
            self.apply_setup_request(request);
        }
        for text in effects.clipboard_copy_requests {
            if let Some(active_pane) = self.active_pane_mut() {
                if let Err(error) = active_pane.app.clipboard.copy(&text) {
                    warn!("lua clipboard.copy failed: {error}");
                }
            }
        }
        for bytes in effects.pty_input_requests {
            self.send_to_pty(&bytes);
        }
        for request in effects.window_requests {
            self.apply_window_request(request);
        }
        self.refresh_plugin_config();
        self.refresh_plugin_snapshot();
    }

    fn apply_window_request(&mut self, request: wok_app::scripting::WindowRequest) {
        let Some(window) = self.window.as_ref() else {
            return;
        };
        match request {
            wok_app::scripting::WindowRequest::SetTitle(title) => {
                window.set_title(&title);
            }
            wok_app::scripting::WindowRequest::ToggleFullscreen => {
                use winit::window::Fullscreen;
                let new = if window.fullscreen().is_some() {
                    None
                } else {
                    Some(Fullscreen::Borderless(None))
                };
                window.set_fullscreen(new);
            }
            wok_app::scripting::WindowRequest::SetOpacity(value) => {
                self.config.window_opacity = value.clamp(0.0, 1.0);
                self.needs_redraw = true;
            }
        }
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

    fn apply_setup_request(&mut self, request: SetupRequest) {
        let result: Result<String, Box<dyn Error>> = match request {
            SetupRequest::Init { overwrite } => {
                setup_ops::run_init(overwrite).map(|_| "Setup: init completed".to_string())
            }
            SetupRequest::Doctor { json } => {
                setup_ops::run_doctor(json).map(|_| "Setup: doctor completed".to_string())
            }
            SetupRequest::Reset { scope, yes } => parse_reset_scope_value(&scope)
                .ok_or_else(|| -> Box<dyn Error> {
                    format!("unsupported reset scope '{scope}'").into()
                })
                .and_then(|scope| setup_ops::run_reset(scope, yes))
                .map(|_| "Setup: reset completed".to_string()),
            SetupRequest::ShellInstall { shell, overwrite } => {
                setup_ops::run_shell_install(shell.as_deref(), overwrite)
                    .map(|_| "Setup: shell install completed".to_string())
            }
            SetupRequest::ShellRollback { shell, yes } => {
                setup_ops::run_shell_rollback(shell.as_deref(), yes)
                    .map(|_| "Setup: shell rollback completed".to_string())
            }
        };

        match result {
            Ok(message) => self.status_message = Some(message),
            Err(error) => {
                warn!("failed to apply setup request: {error}");
                self.status_message = Some(format!("Setup request failed: {error}"));
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
        self.prewarm_glyph_atlas();
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

    fn prewarm_glyph_atlas(&mut self) {
        if let Some(render) = self.render.as_mut() {
            let _ = prewarm_common_glyphs(render, &mut self.font);
        }
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

    fn open_media_preview(&mut self, path: PathBuf) {
        let path = self.resolve_preview_path(&path);
        let Some(kind) = media_kind_for_path(&path) else {
            self.status_message = Some(format!("Unsupported preview type: {}", path.display()));
            self.needs_redraw = true;
            return;
        };
        if !path.is_file() {
            self.status_message = Some(format!("Preview file not found: {}", path.display()));
            self.needs_redraw = true;
            return;
        }

        let Some(window) = self.window.clone() else {
            self.status_message = Some("Window is not ready for media preview".to_string());
            self.needs_redraw = true;
            return;
        };
        let Some(frame) = self.media_preview_frame_for_window(&window) else {
            self.status_message = Some("Window is too small for media preview".to_string());
            self.needs_redraw = true;
            return;
        };

        self.media_preview = None;
        match MediaPreview::open(&window, path.clone(), kind, frame) {
            Ok(preview) => {
                self.status_message =
                    Some(format!("Previewing {}: {}", kind.label(), path.display()));
                self.media_preview = Some(preview);
            }
            Err(error) => {
                self.status_message = Some(format!("Failed to open preview: {error}"));
            }
        }
        self.needs_redraw = true;
    }

    fn preview_file_path(&mut self, path: PathBuf) {
        self.preview_file_target(ParsedPathTarget {
            path,
            line: None,
            column: None,
        });
    }

    fn preview_file_target(&mut self, target: ParsedPathTarget) {
        let path = self.resolve_preview_path(&target.path);
        if media_kind_for_path(&path).is_some() {
            self.open_media_preview(path);
            return;
        }
        if is_text_preview_path(&path) {
            self.open_text_file_preview_at(path, target.line, target.column);
        } else {
            self.quick_look_or_open_path(&path);
        }
    }

    fn open_text_file_preview_at(
        &mut self,
        path: PathBuf,
        line: Option<usize>,
        column: Option<usize>,
    ) {
        let path = self.resolve_preview_path(&path);
        if !path.is_file() {
            self.status_message = Some(format!("Preview file not found: {}", path.display()));
            self.needs_redraw = true;
            return;
        }
        match read_text_preview_file(&path) {
            Ok((content, truncated)) => {
                self.open_text_preview_state(
                    "Preview",
                    path.clone(),
                    content,
                    truncated,
                    line,
                    column,
                    "Esc close  / search  Enter next  arrows scroll  Mod+C copy",
                );
                self.status_message = Some(if truncated {
                    format!("Previewing first 2 MiB of text: {}", path.display())
                } else {
                    format!("Previewing text: {}", path.display())
                });
            }
            Err(error) => {
                self.status_message = Some(format!("Failed to preview text: {error}"));
            }
        }
        self.needs_redraw = true;
    }

    fn open_text_preview_state(
        &mut self,
        title: &str,
        path: PathBuf,
        content: String,
        truncated: bool,
        line: Option<usize>,
        column: Option<usize>,
        help: &str,
    ) {
        let mut editor = InputEditor::new(
            self.config.shell.clone(),
            wok_input::editor::InputPosition::Bottom,
        );
        editor.buffer.set_text(&content);
        if let Some(line) = line {
            let offset = text_offset_for_line_col(
                &content,
                line.saturating_sub(1),
                column.unwrap_or(1).saturating_sub(1),
            );
            if let Some(cursor) = editor.buffer.cursors_mut().first_mut() {
                cursor.position = offset;
                cursor.anchor = None;
            }
        }
        editor.is_active = true;
        self.file_preview = Some(FilePreviewState {
            path,
            title: title.to_string(),
            help: help.to_string(),
            editor,
            search_active: false,
            search_query: String::new(),
            truncated,
        });
    }

    fn open_scratch_buffer(&mut self) {
        self.open_scratch_buffer_named("default");
    }

    fn open_scratch_buffer_named(&mut self, name: &str) {
        let path = scratch_path_for_name(name);
        if let Some(parent) = path.parent() {
            if let Err(error) = std::fs::create_dir_all(parent) {
                self.status_message = Some(format!("Scratch unavailable: {error}"));
                self.needs_redraw = true;
                return;
            }
        }
        let content = std::fs::read_to_string(&path).unwrap_or_default();
        let mut editor = InputEditor::new(
            self.config.shell.clone(),
            wok_input::editor::InputPosition::Bottom,
        );
        editor.buffer.set_text(&content);
        editor.is_active = true;
        self.scratch_buffer = Some(ScratchBufferState {
            path: path.clone(),
            editor,
        });
        self.status_message = Some(format!("Scratch buffer opened: {}", path.display()));
        self.needs_redraw = true;
    }

    fn save_scratch_buffer(&mut self) {
        let Some(scratch) = self.scratch_buffer.as_ref() else {
            return;
        };
        match std::fs::write(&scratch.path, scratch.editor.buffer.text()) {
            Ok(()) => {
                self.status_message = Some(format!("Saved scratch ({})", scratch.path.display()));
            }
            Err(error) => {
                self.status_message = Some(format!("Failed to save scratch: {error}"));
            }
        }
        self.needs_redraw = true;
    }

    fn insert_scratch_selection_into_input(&mut self) {
        let Some(text) = self.scratch_buffer.as_ref().map(|scratch| {
            selected_editor_text(&scratch.editor).unwrap_or_else(|| scratch.editor.buffer.text())
        }) else {
            self.status_message = Some("Scratch buffer is not open".to_string());
            self.needs_redraw = true;
            return;
        };
        let text = text.trim_end_matches('\n').to_string();
        if text.is_empty() {
            self.status_message = Some("Scratch buffer is empty".to_string());
            self.needs_redraw = true;
            return;
        }
        if let Some(active_pane) = self.active_pane_mut() {
            active_pane.app.input_mode = InputMode::OwnedInput;
            active_pane.app.input_editor.is_active = true;
            let _ = active_pane.app.input_editor.buffer.insert_at(0, &text);
            self.status_message = Some("Inserted scratch text into command input".to_string());
        }
        self.needs_redraw = true;
    }

    fn send_scratch_selection_to_pane(&mut self) {
        let Some(text) = self.scratch_buffer.as_ref().map(|scratch| {
            selected_editor_text(&scratch.editor).unwrap_or_else(|| scratch.editor.buffer.text())
        }) else {
            self.status_message = Some("Scratch buffer is not open".to_string());
            self.needs_redraw = true;
            return;
        };
        if text.trim().is_empty() {
            self.status_message = Some("Scratch buffer is empty".to_string());
            self.needs_redraw = true;
            return;
        }
        let mut payload = text;
        if !payload.ends_with('\n') {
            payload.push('\n');
        }
        self.send_raw_input_to_pty(payload.as_bytes());
        self.status_message = Some("Sent scratch text to pane".to_string());
        self.needs_redraw = true;
    }

    fn open_scratch_palette(&mut self) {
        let mut entries = Vec::new();
        for (name, path) in scratch_files() {
            entries.push(PaletteEntry {
                label: format!("Open Scratch {name}"),
                description: path.display().to_string(),
                category: PaletteCategory::ScratchSnippet,
                score: 0.0,
                action: PaletteAction::OpenScratch(name),
            });
        }
        if entries.is_empty() {
            self.status_message = Some("No scratch buffers found".to_string());
            self.needs_redraw = true;
        } else {
            self.open_transient_palette(entries, "scratch buffers");
        }
    }

    fn toggle_media_preview_playback(&mut self) {
        let Some(preview) = self.media_preview.as_mut() else {
            self.status_message = Some("No media preview is open".to_string());
            self.needs_redraw = true;
            return;
        };
        let path = preview.path().display().to_string();
        match preview.toggle_playback() {
            Some(true) => self.status_message = Some(format!("Playing preview: {path}")),
            Some(false) => self.status_message = Some(format!("Paused preview: {path}")),
            None => self.status_message = Some("Static image preview has no playback".to_string()),
        }
        self.needs_redraw = true;
    }

    fn control_media_preview(&mut self, action: Action) {
        let Some(preview) = self.media_preview.as_mut() else {
            self.status_message = Some("No media preview is open".to_string());
            self.needs_redraw = true;
            return;
        };
        let message = match action {
            Action::SeekMediaPreviewBackward => preview
                .seek_by_seconds(-5.0)
                .map(|()| "Rewound preview 5s".to_string()),
            Action::SeekMediaPreviewForward => preview
                .seek_by_seconds(5.0)
                .map(|()| "Skipped preview 5s".to_string()),
            Action::SlowMediaPreviewPlayback => preview
                .adjust_rate(-0.25)
                .map(|rate| format!("Preview speed: {rate:.2}x")),
            Action::FastMediaPreviewPlayback => preview
                .adjust_rate(0.25)
                .map(|rate| format!("Preview speed: {rate:.2}x")),
            Action::StepMediaPreviewBackward => preview
                .step_frame(-1)
                .map(|()| "Stepped preview back one frame".to_string()),
            Action::StepMediaPreviewForward => preview
                .step_frame(1)
                .map(|()| "Stepped preview forward one frame".to_string()),
            Action::ToggleMediaPreviewMute => preview.toggle_mute().map(|muted| {
                if muted {
                    "Muted preview".to_string()
                } else {
                    "Unmuted preview".to_string()
                }
            }),
            _ => None,
        };
        self.status_message = Some(
            message
                .unwrap_or_else(|| "Media control is only available for MP4 previews".to_string()),
        );
        self.needs_redraw = true;
    }

    fn open_block_inspector(&mut self) {
        let Some((path, content)) = self.active_pane().and_then(|pane| {
            let block = pane.app.selected_or_latest_block()?;
            let output = extract_block_output_text(&pane.terminal, block);
            let duration = block
                .duration
                .map(|duration| format!("{}ms", duration.as_millis()))
                .unwrap_or_else(|| "running".to_string());
            let exit = block
                .exit_code
                .map_or_else(|| "running".to_string(), |code| code.to_string());
            let branch = block.git_branch.as_deref().unwrap_or("unknown");
            let dirty = block
                .git_dirty
                .map_or_else(|| "unknown".to_string(), |dirty| dirty.to_string());
            let content = format!(
                "# Command Block {}\n\ncommand: {}\ncwd: {}\nexit: {}\nduration: {}\nrows: {}..{}\nbranch: {}\ngit_dirty: {}\nbookmarked: {}\ncollapsed: {}\n\n## Output\n\n{}",
                block.id,
                block.command_text,
                block.cwd.display(),
                exit,
                duration,
                block.output_start_row,
                block.output_end_row,
                branch,
                dirty,
                block.is_bookmarked,
                block.is_collapsed,
                output
            );
            Some((PathBuf::from(format!("block-{}-inspector.md", block.id)), content))
        }) else {
            self.status_message = Some("No command block to inspect".to_string());
            self.needs_redraw = true;
            return;
        };
        self.open_text_preview_state(
            "Block Inspector",
            path,
            content,
            false,
            None,
            None,
            "Esc close  / search  Enter next  Mod+C copy",
        );
        self.needs_redraw = true;
    }

    fn open_block_rerun_history(&mut self) {
        let Some(command) = self
            .active_pane()
            .and_then(|pane| pane.app.selected_or_latest_block())
            .map(|block| block.command_text.clone())
        else {
            self.status_message = Some("No command block for rerun history".to_string());
            self.needs_redraw = true;
            return;
        };
        let mut entries = self
            .active_pane()
            .map(|pane| pane.pane_history.clone())
            .unwrap_or_default();
        entries.extend(self.global_history.entries().iter().cloned());
        entries.retain(|entry| entry.command.trim() == command.trim());
        entries.sort_by(|left, right| right.started_at_ms.cmp(&left.started_at_ms));
        entries.dedup_by(|left, right| {
            left.started_at_ms == right.started_at_ms && left.source_pane_id == right.source_pane_id
        });
        let mut content = format!("# Rerun History\n\ncommand: {}\n\n", command);
        if entries.is_empty() {
            content.push_str("No previous runs recorded.");
        } else {
            for entry in entries.iter().take(100) {
                let cwd = entry
                    .cwd
                    .as_ref()
                    .map_or_else(|| "~".to_string(), |path| path.display().to_string());
                let exit = entry
                    .exit_code
                    .map_or_else(|| "exit ?".to_string(), |code| format!("exit {code}"));
                let duration = entry
                    .duration_ms
                    .map_or_else(String::new, |ms| format!(" in {ms}ms"));
                content.push_str(&format!(
                    "- {}{} | {} | started {}\n",
                    exit, duration, cwd, entry.started_at_ms
                ));
            }
        }
        self.open_text_preview_state(
            "Rerun History",
            PathBuf::from("block-rerun-history.md"),
            content,
            false,
            None,
            None,
            "Esc close  / search  Mod+C copy",
        );
        self.needs_redraw = true;
    }

    fn open_block_rerun_comparison(&mut self) {
        let Some(command) = self
            .active_pane()
            .and_then(|pane| pane.app.selected_or_latest_block())
            .map(|block| block.command_text.clone())
        else {
            self.status_message = Some("No command block for rerun comparison".to_string());
            self.needs_redraw = true;
            return;
        };
        let mut entries = self
            .active_pane()
            .map(|pane| pane.pane_history.clone())
            .unwrap_or_default();
        entries.extend(self.global_history.entries().iter().cloned());
        entries.retain(|entry| entry.command.trim() == command.trim());
        entries.sort_by(|left, right| left.started_at_ms.cmp(&right.started_at_ms));
        entries.dedup_by(|left, right| {
            left.started_at_ms == right.started_at_ms && left.source_pane_id == right.source_pane_id
        });

        let mut content = format!("# Rerun Comparison\n\ncommand: {}\n\n", command);
        if entries.is_empty() {
            content.push_str("No comparable runs recorded.");
        } else {
            let durations = entries
                .iter()
                .filter_map(|entry| entry.duration_ms)
                .collect::<Vec<_>>();
            if let (Some(min), Some(max)) = (durations.iter().min(), durations.iter().max()) {
                content.push_str(&format!(
                    "runs: {}\nfastest: {}ms\nslowest: {}ms\n\n",
                    entries.len(),
                    min,
                    max
                ));
            }
            content.push_str("| run | exit | duration | cwd |\n| --- | --- | --- | --- |\n");
            for (index, entry) in entries.iter().enumerate() {
                let exit = entry
                    .exit_code
                    .map_or_else(|| "?".to_string(), |code| code.to_string());
                let duration = entry
                    .duration_ms
                    .map_or_else(|| "?".to_string(), |ms| format!("{ms}ms"));
                let cwd = entry
                    .cwd
                    .as_ref()
                    .map_or_else(|| "~".to_string(), |path| path.display().to_string());
                content.push_str(&format!(
                    "| {} | {} | {} | {} |\n",
                    index + 1,
                    exit,
                    duration,
                    cwd.replace('|', "\\|")
                ));
            }
        }
        self.open_text_preview_state(
            "Rerun Comparison",
            PathBuf::from("block-rerun-comparison.md"),
            content,
            false,
            None,
            None,
            "Esc close  / search  Mod+C copy",
        );
        self.needs_redraw = true;
    }

    fn close_media_preview(&mut self) {
        if let Some(preview) = self.media_preview.take() {
            self.status_message = Some(format!(
                "Closed {} preview: {}",
                preview.kind().label(),
                preview.path().display()
            ));
            self.needs_redraw = true;
        }
    }

    fn sync_media_preview_frame(&mut self) {
        let Some(window) = self.window.clone() else {
            return;
        };
        let Some(frame) = self.media_preview_frame_for_window(&window) else {
            return;
        };
        if let Some(preview) = self.media_preview.as_mut() {
            preview.set_frame(frame);
        }
    }

    fn media_preview_frame_for_window(&self, window: &Window) -> Option<PreviewFrame> {
        let content = self.chrome_rects.content;
        if content.w <= 1.0 || content.h <= 1.0 {
            return None;
        }

        let scale = window.scale_factor().max(1.0) as f32;
        let inner_size = window.inner_size();
        let window_height_points = inner_size.height as f32 / scale;
        let margin = 24.0;
        let x = (content.x + margin) / scale;
        let y_from_top = (content.y + margin) / scale;
        let width = (content.w - margin * 2.0).max(120.0) / scale;
        let height = (content.h - margin * 2.0).max(90.0) / scale;
        let y = (window_height_points - y_from_top - height).max(0.0);

        Some(PreviewFrame {
            x: f64::from(x),
            y: f64::from(y),
            width: f64::from(width),
            height: f64::from(height),
        })
    }

    fn resolve_preview_path(&self, path: &Path) -> PathBuf {
        if path.is_absolute() {
            return path.to_path_buf();
        }
        self.active_pane()
            .map(|pane| pane.current_cwd.join(path))
            .unwrap_or_else(|| path.to_path_buf())
    }

    fn path_under_cursor(&self) -> Option<ParsedPathTarget> {
        let pane = self.active_pane()?;
        let (row, col) = if let Some(vi) = pane.app.vi_mode.as_ref() {
            (vi.cursor_row, vi.cursor_col)
        } else {
            let (col, _) = pane.terminal.state.cursor_position();
            (pane.terminal.state.absolute_cursor_row(), col)
        };
        let line = self.path_detection_line_for_row(pane, row);
        extract_path_near_column(&line, col)
    }

    fn path_at_cell(&self, pane_id: PaneId, cell: CellPos) -> Option<ParsedPathTarget> {
        let pane = self.panes.get(&pane_id)?;
        let absolute_row = pane
            .terminal
            .state
            .viewport_row_to_absolute(usize::from(cell.row));
        let line = self.path_detection_line_for_row(pane, absolute_row);
        extract_path_near_column(&line, usize::from(cell.col))
    }

    fn path_detection_line_for_row(&self, pane: &PaneRuntime, row: usize) -> String {
        let mut line = pane.terminal.state.row_text(row);
        if line.ends_with('\\') || line.ends_with('/') {
            let next = pane.terminal.state.row_text(row.saturating_add(1));
            line.push_str(next.trim_start());
        }
        line
    }

    fn apply_path_action_under_cursor(&mut self, action: PathCursorAction) {
        let Some(target) = self.path_under_cursor() else {
            self.status_message = Some("No file path under cursor".to_string());
            self.needs_redraw = true;
            return;
        };
        let path = self.resolve_preview_path(&target.path);
        match action {
            PathCursorAction::Preview => self.preview_file_target(ParsedPathTarget {
                path,
                line: target.line,
                column: target.column,
            }),
            PathCursorAction::Open => self.open_path_externally(&path),
            PathCursorAction::Copy => self.copy_path_to_clipboard(&path),
            PathCursorAction::Reveal => self.reveal_path_in_finder(&path),
            PathCursorAction::Tail => self.tail_path_in_split(&path),
        }
    }

    fn open_path_externally(&mut self, path: &Path) {
        match Command::new("open").arg(path).status() {
            Ok(status) if status.success() => {
                self.status_message = Some(format!("Opened externally: {}", path.display()));
            }
            Ok(status) => {
                self.status_message = Some(format!("open exited with status {status}"));
            }
            Err(error) => {
                self.status_message = Some(format!("Failed to open externally: {error}"));
            }
        }
        self.needs_redraw = true;
    }

    fn quick_look_or_open_path(&mut self, path: &Path) {
        match Command::new("qlmanage").arg("-p").arg(path).spawn() {
            Ok(_) => {
                self.status_message = Some(format!("Opened Quick Look: {}", path.display()));
            }
            Err(error) => {
                warn!(
                    "failed to launch Quick Look for '{}': {error}",
                    path.display()
                );
                self.open_path_externally(path);
                return;
            }
        }
        self.needs_redraw = true;
    }

    fn reveal_path_in_finder(&mut self, path: &Path) {
        match Command::new("open").arg("-R").arg(path).status() {
            Ok(status) if status.success() => {
                self.status_message = Some(format!("Revealed in Finder: {}", path.display()));
            }
            Ok(status) => {
                self.status_message = Some(format!("open -R exited with status {status}"))
            }
            Err(error) => self.status_message = Some(format!("Failed to reveal path: {error}")),
        }
        self.needs_redraw = true;
    }

    fn copy_path_to_clipboard(&mut self, path: &Path) {
        let text = path.display().to_string();
        if let Some(active_pane) = self.active_pane_mut() {
            if let Err(error) = active_pane.app.clipboard.copy(&text) {
                self.status_message = Some(format!("Failed to copy path: {error}"));
            } else {
                self.status_message = Some(format!("Copied path: {text}"));
            }
        }
        self.needs_redraw = true;
    }

    fn tail_path_in_split(&mut self, path: &Path) {
        if !path.is_file() {
            self.status_message = Some(format!("Cannot tail missing file: {}", path.display()));
            self.needs_redraw = true;
            return;
        }
        let command = format!(
            "tail -f {}\n",
            shell_quote_path(&path.display().to_string())
        );
        self.handle_action(Action::SplitHorizontal);
        self.send_to_pty(command.as_bytes());
        self.status_message = Some(format!("Tailing: {}", path.display()));
        self.needs_redraw = true;
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
        let mut system_notifications = Vec::new();
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
                    TriggerAction::SystemNotify { title, message } => {
                        let title = if title.trim().is_empty() {
                            trigger_match.trigger_name.clone()
                        } else {
                            title.trim().to_string()
                        };
                        let matched_source = if matches!(trigger_match.scope, TriggerScope::Command)
                            && !command_text.trim().is_empty()
                        {
                            command_text.trim()
                        } else {
                            &trigger_match.matched_text
                        };
                        let message = if message.trim().is_empty() {
                            format!("matched '{matched_source}'")
                        } else {
                            format!("{message}: {matched_source}")
                        };
                        system_notifications.push(SystemNotificationRequest {
                            title,
                            message,
                            subtitle: Some(format!("pane {pane_id}")),
                        });
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
        for notification in system_notifications {
            if let Err(error) = send_system_notification(&notification) {
                warn!("failed to send trigger notification: {error}");
            }
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
                        pane.pending_typewriter_block_id =
                            pane.app.block_manager.active_output_block_id();
                    }
                    relayout = true;
                }
                SemanticEvent::CommandText { text, .. } => {
                    let mut telemetry_submission = None;
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        let trimmed = text.trim().to_string();
                        if let Some(pending) = pane.pending_history.as_mut() {
                            pending.command.clone_from(&trimmed);
                        } else if !trimmed.is_empty() {
                            pane.pending_history = Some(HistoryEntry::pending(
                                &text,
                                (!pane.current_cwd.as_os_str().is_empty())
                                    .then(|| pane.current_cwd.clone()),
                                Some(pane_id),
                            ));
                        }
                        if !trimmed.is_empty() {
                            telemetry_submission = Some((
                                trimmed,
                                (!pane.current_cwd.as_os_str().is_empty())
                                    .then(|| pane.current_cwd.clone()),
                            ));
                        }
                    }
                    if let Some((command, cwd)) = telemetry_submission {
                        self.log_command_submitted(pane_id, &command, cwd);
                    }
                }
                SemanticEvent::CommandEnd { exit_code, .. } => {
                    let mut telemetry_completion = None;
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
                        let block_snapshot = block.map(|candidate| CommandTelemetryBlockSnapshot {
                            block_id: candidate.id,
                            output_start_row: candidate.output_start_row,
                            output_end_row: candidate.output_end_row,
                            duration_ms: candidate
                                .duration
                                .map(|duration| duration.as_millis() as u64),
                        });

                        entry.mark_completed(exit_code, duration, cwd);
                        if !entry.command.is_empty() {
                            pane.pane_history.push(entry.clone());
                            pane.last_output_line_row = None;
                            telemetry_completion = Some((entry.clone(), block_snapshot));
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
                    if let Some((entry, block_snapshot)) = telemetry_completion.as_ref() {
                        self.log_command_completed(entry, block_snapshot.as_ref());
                    }
                    self.report_pending_rerun_diff(pane_id);
                    self.update_failure_status_for_pane(pane_id, exit_code);
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
                                z_index,
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
                                        z_index,
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
                                z_index,
                            } => {
                                pane.inline_images.place_existing(
                                    image_id,
                                    ImagePlacement {
                                        row,
                                        col,
                                        display_cols,
                                        display_rows,
                                        placement_id,
                                        z_index,
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

    fn prepare_rerun_diff_tracking(&mut self) {
        let Some(pane) = self.active_pane_mut() else {
            return;
        };
        let Some(block) = pane.app.selected_or_latest_block() else {
            pane.pending_rerun_diff = None;
            return;
        };
        if block.exit_code.is_none() || block.command_text.trim().is_empty() {
            pane.pending_rerun_diff = None;
            return;
        }
        pane.pending_rerun_diff = Some(PendingRerunDiff {
            baseline_block_id: block.id,
            command_text: block.command_text.trim().to_string(),
            baseline_output: collect_block_output_lines(&pane.terminal, block),
        });
    }

    fn report_pending_rerun_diff(&mut self, pane_id: PaneId) {
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return;
        };
        let Some(pending) = pane.pending_rerun_diff.take() else {
            return;
        };
        let Some(new_block) = pane.app.block_manager.blocks.last() else {
            return;
        };
        if new_block.id == pending.baseline_block_id {
            return;
        }
        if new_block.command_text.trim() != pending.command_text {
            return;
        }

        let latest_output = collect_block_output_lines(&pane.terminal, new_block);
        let (added, removed) = diff_line_counts(&pending.baseline_output, &latest_output);
        self.status_message = Some(format!(
            "Rerun diff for '{}': +{} -{} lines",
            pending.command_text, added, removed
        ));
    }

    fn failure_summary_for_pane(&self, pane_id: PaneId, limit: usize) -> Vec<FailureSummaryEntry> {
        let Some(pane) = self.panes.get(&pane_id) else {
            return Vec::new();
        };
        summarize_failures(&pane.pane_history, limit)
    }

    fn failure_trends_for_pane(
        &self,
        pane_id: PaneId,
        bucket_ms: u64,
        limit: usize,
    ) -> Vec<FailureTrendEntry> {
        let Some(pane) = self.panes.get(&pane_id) else {
            return Vec::new();
        };
        summarize_failure_trends(
            &pane.pane_history,
            &pane.app.block_manager.blocks,
            bucket_ms,
            limit,
        )
    }

    fn update_failure_status_for_pane(&mut self, pane_id: PaneId, exit_code: Option<i32>) {
        if exit_code.unwrap_or(0) == 0 {
            return;
        }
        let top = self.failure_summary_for_pane(pane_id, 3);
        if top.is_empty() {
            return;
        }
        let summary = top
            .iter()
            .map(|item| format!("{} ({})", item.command, item.count))
            .collect::<Vec<_>>()
            .join(", ");
        self.status_message = Some(format!("Recent failures: {summary}"));
    }

    fn save_selected_block_as_workflow(&mut self) {
        let Some((command, cwd_display)) = self.active_pane().and_then(|pane| {
            let block = pane.app.selected_or_latest_block()?;
            if block.exit_code.is_none() || block.command_text.trim().is_empty() {
                return None;
            }
            let cwd = (!block.cwd.as_os_str().is_empty()).then(|| block.cwd.display().to_string());
            Some((block.command_text.trim().to_string(), cwd))
        }) else {
            self.status_message =
                Some("Select a completed block with command text to save as workflow".to_string());
            return;
        };

        let workflow_name = workflow_name_from_command(&command);
        let description = cwd_display.map_or_else(
            || "Captured from selected Wok command block".to_string(),
            |cwd| format!("Captured from selected Wok command block in {cwd}"),
        );
        let workflow = Workflow {
            name: workflow_name.clone(),
            description,
            template: command,
            params: Vec::new(),
        };
        self.workflow_store.add(workflow.clone());

        match persist_workflow_template(&workflow) {
            Ok(path) => {
                self.status_message = Some(format!(
                    "Saved workflow '{}' ({})",
                    workflow.name,
                    path.display()
                ));
            }
            Err(error) => {
                warn!("failed to persist workflow '{}': {error}", workflow.name);
                self.status_message =
                    Some(format!("Saved workflow '{}' in memory only", workflow.name));
            }
        }
    }

    fn export_selected_block_bundle(&mut self, format: BlockExportFormat) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("No active pane for block export".to_string());
            return;
        };
        let Some((bundle, serialized)) = self.active_pane().and_then(|pane| {
            let block = pane.app.selected_or_latest_block()?;
            let output = collect_block_output_lines(&pane.terminal, block);
            let duration_ms = block.duration.map(|duration| duration.as_millis() as u64);
            let cwd = (!block.cwd.as_os_str().is_empty()).then(|| block.cwd.display().to_string());
            let generated_at_unix_ms = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_or(0, |duration| duration.as_millis() as u64);

            let bundle = BlockExportBundle {
                generated_at_unix_ms,
                pane_id,
                block_id: block.id,
                command: block.command_text.clone(),
                cwd,
                git_branch: block.git_branch.clone(),
                exit_code: block.exit_code,
                duration_ms,
                output_start_row: block.output_start_row,
                output_end_row: block.output_end_row,
                output_lines: output,
            };
            let serialized = match format {
                BlockExportFormat::Markdown => bundle.to_markdown(),
                BlockExportFormat::Json => match serde_json::to_string_pretty(&bundle) {
                    Ok(payload) => payload,
                    Err(error) => {
                        warn!("failed to serialize block export JSON: {error}");
                        return None;
                    }
                },
            };
            Some((bundle, serialized))
        }) else {
            self.status_message = Some("No block available for export".to_string());
            return;
        };

        if let Some(active_pane) = self.active_pane_mut() {
            if let Err(error) = active_pane.app.clipboard.copy(&serialized) {
                warn!("failed to copy block export to clipboard: {error}");
            }
        }

        match persist_block_export(&bundle, &serialized, format) {
            Ok(path) => {
                self.status_message = Some(format!(
                    "Exported block {} as {} ({})",
                    bundle.block_id,
                    format.label(),
                    path.display()
                ));
            }
            Err(error) => {
                warn!("failed to persist block export: {error}");
                self.status_message = Some(format!(
                    "Exported block {} as {} to clipboard only",
                    bundle.block_id,
                    format.label()
                ));
            }
        }
    }

    fn open_settings(&mut self) {
        match ensure_settings_file() {
            Ok(path) => match std::fs::read_to_string(&path) {
                Ok(content) => {
                    let mut editor = InputEditor::new(
                        self.config.shell.clone(),
                        wok_input::editor::InputPosition::Bottom,
                    );
                    editor.buffer.set_text(&content);
                    editor.is_active = true;
                    self.settings_editor = Some(SettingsEditorState {
                        path: path.clone(),
                        editor,
                    });
                    self.status_message = Some(format!(
                        "Settings buffer opened: {} (save with Mod+S, close with Esc)",
                        path.display()
                    ));
                }
                Err(error) => {
                    warn!("failed to read settings '{}': {error}", path.display());
                    self.status_message = Some(format!("Settings unavailable: {error}"));
                }
            },
            Err(error) => {
                warn!("failed to prepare settings file: {error}");
                self.status_message = Some(format!("Settings unavailable: {error}"));
            }
        }
    }

    fn reset_settings_to_defaults(&mut self) {
        match setup_ops::reset_config_file() {
            Ok(path) => {
                let content = std::fs::read_to_string(&path).ok();
                self.reload_configuration();
                if let Some(settings) = self.settings_editor.as_mut() {
                    if settings.path == path {
                        if let Some(content) = content {
                            settings.editor.buffer.set_text(&content);
                        }
                    } else {
                        self.settings_editor = None;
                    }
                }
                self.status_message =
                    Some(format!("Reset settings to defaults ({})", path.display()));
                self.needs_redraw = true;
            }
            Err(error) => {
                warn!("failed to reset settings: {error}");
                self.status_message = Some(format!("Failed to reset settings: {error}"));
                self.needs_redraw = true;
            }
        }
    }

    fn save_settings_editor(&mut self) {
        let Some(settings) = self.settings_editor.as_ref() else {
            return;
        };
        let path = settings.path.clone();
        let content = settings.editor.buffer.text();

        match std::fs::write(&path, content) {
            Ok(()) => {
                self.reload_configuration();
                self.status_message = Some(format!("Saved settings ({})", path.display()));
            }
            Err(error) => {
                warn!("failed to save settings '{}': {error}", path.display());
                self.status_message = Some(format!("Failed to save settings: {error}"));
            }
        }
    }

    fn copy_settings_selection_to_clipboard(&mut self) {
        let selected_text = self
            .settings_editor
            .as_ref()
            .and_then(|settings| selected_editor_text(&settings.editor));
        if let (Some(text), Some(active_pane)) = (selected_text, self.active_pane_mut()) {
            let _ = active_pane.app.clipboard.copy(&text);
        }
    }

    fn cut_settings_selection_to_clipboard(&mut self) {
        self.copy_settings_selection_to_clipboard();
        if let Some(settings) = self.settings_editor.as_mut() {
            delete_editor_selection(&mut settings.editor);
        }
        self.needs_redraw = true;
    }

    fn paste_into_settings_editor(&mut self) {
        let pasted = self
            .active_pane_mut()
            .and_then(|pane| pane.app.clipboard.paste().ok());
        if let (Some(text), Some(settings)) = (pasted, self.settings_editor.as_mut()) {
            replace_editor_selection(&mut settings.editor, &text);
        }
        self.needs_redraw = true;
    }

    fn select_all_settings_editor(&mut self) {
        if let Some(settings) = self.settings_editor.as_mut() {
            settings.editor.handle_key(EditorKey::SelectAll);
        }
        self.needs_redraw = true;
    }

    fn copy_file_preview_to_clipboard(&mut self) {
        let text = self
            .file_preview
            .as_ref()
            .map(|preview| preview.editor.buffer.text());
        if let (Some(text), Some(active_pane)) = (text, self.active_pane_mut()) {
            let _ = active_pane.app.clipboard.copy(&text);
            self.status_message = Some("Copied preview contents".to_string());
        }
        self.needs_redraw = true;
    }

    fn find_next_in_file_preview(&mut self) {
        let Some(preview) = self.file_preview.as_mut() else {
            return;
        };
        let query = preview.search_query.trim();
        if query.is_empty() {
            self.status_message = Some("Preview search is empty".to_string());
            return;
        }
        let text = preview.editor.buffer.text();
        let lines = text.lines().collect::<Vec<_>>();
        let current_row = preview
            .editor
            .buffer
            .cursor_positions()
            .first()
            .map(|(row, _)| *row)
            .unwrap_or_default();
        let query_lower = query.to_ascii_lowercase();
        let total = lines.len().max(1);
        for step in 1..=total {
            let row = (current_row + step) % total;
            let Some(line) = lines.get(row) else {
                continue;
            };
            let found = line.to_ascii_lowercase().find(&query_lower);
            if let Some(col) = found {
                let offset = text_offset_for_line_col(&text, row, col);
                if let Some(cursor) = preview.editor.buffer.cursors_mut().first_mut() {
                    cursor.position = offset;
                    cursor.anchor = None;
                }
                self.status_message = Some(format!("Preview search: match on line {}", row + 1));
                return;
            }
        }
        self.status_message = Some(format!("Preview search: no match for '{query}'"));
    }

    fn handle_file_preview_input(&mut self, event: &InputEvent) -> bool {
        if self.file_preview.is_none() {
            return false;
        }
        if self
            .file_preview
            .as_ref()
            .is_some_and(|preview| preview.search_active)
        {
            match event.action {
                KeyAction::Escape => {
                    if let Some(preview) = self.file_preview.as_mut() {
                        preview.search_active = false;
                    }
                    self.needs_redraw = true;
                    return true;
                }
                KeyAction::Enter | KeyAction::ArrowDown => {
                    self.find_next_in_file_preview();
                    self.needs_redraw = true;
                    return true;
                }
                KeyAction::Backspace
                    if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
                {
                    if let Some(preview) = self.file_preview.as_mut() {
                        preview.search_query.pop();
                    }
                    self.needs_redraw = true;
                    return true;
                }
                KeyAction::Char(ch)
                    if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
                {
                    if let Some(preview) = self.file_preview.as_mut() {
                        preview.search_query.push(ch);
                    }
                    self.find_next_in_file_preview();
                    self.needs_redraw = true;
                    return true;
                }
                _ => return true,
            }
        }
        match event.action {
            KeyAction::Escape => {
                self.file_preview = None;
                self.status_message = Some("Closed file preview".to_string());
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Char('/')
                if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                if let Some(preview) = self.file_preview.as_mut() {
                    preview.search_active = true;
                    preview.search_query.clear();
                }
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Enter => {
                self.find_next_in_file_preview();
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Copy => {
                self.copy_file_preview_to_clipboard();
                return true;
            }
            _ => {}
        }
        if let Some(editor_key) = input_event_to_editor_key(event) {
            if let Some(preview) = self.file_preview.as_mut() {
                let _ = preview.editor.handle_key(editor_key);
            }
        }
        self.needs_redraw = true;
        true
    }

    fn handle_scratch_buffer_input(&mut self, event: &InputEvent) -> bool {
        if self.scratch_buffer.is_none() {
            return false;
        }

        match event.action {
            KeyAction::Escape => {
                self.scratch_buffer = None;
                self.status_message = Some("Closed scratch buffer".to_string());
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Char('s') | KeyAction::Char('S')
                if platform_modifier_active(event.modifiers) =>
            {
                self.save_scratch_buffer();
                return true;
            }
            KeyAction::Copy => {
                if let Some(text) = self
                    .scratch_buffer
                    .as_ref()
                    .and_then(|scratch| selected_editor_text(&scratch.editor))
                {
                    if let Some(active_pane) = self.active_pane_mut() {
                        let _ = active_pane.app.clipboard.copy(&text);
                    }
                }
                return true;
            }
            KeyAction::Paste => {
                let pasted = self
                    .active_pane_mut()
                    .and_then(|pane| pane.app.clipboard.paste().ok());
                if let (Some(text), Some(scratch)) = (pasted, self.scratch_buffer.as_mut()) {
                    replace_editor_selection(&mut scratch.editor, &text);
                }
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Enter => {
                if let Some(scratch) = self.scratch_buffer.as_mut() {
                    replace_editor_selection(&mut scratch.editor, "\n");
                }
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Char(ch)
                if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                if let Some(scratch) = self.scratch_buffer.as_mut() {
                    replace_editor_selection(&mut scratch.editor, &ch.to_string());
                }
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Backspace | KeyAction::Delete => {
                let deleted_selection = self
                    .scratch_buffer
                    .as_mut()
                    .is_some_and(|scratch| delete_editor_selection(&mut scratch.editor));
                if deleted_selection {
                    self.needs_redraw = true;
                    return true;
                }
            }
            _ => {}
        }

        if let Some(editor_key) = input_event_to_editor_key(event) {
            let editor_key = match editor_key {
                EditorKey::Enter => EditorKey::ShiftEnter,
                other => other,
            };
            if let Some(scratch) = self.scratch_buffer.as_mut() {
                let _ = scratch.editor.handle_key(editor_key);
            }
        }
        self.needs_redraw = true;
        true
    }

    fn handle_settings_editor_input(&mut self, event: &InputEvent) -> bool {
        if self.settings_editor.is_none() {
            return false;
        }

        match event.action {
            KeyAction::Escape => {
                self.settings_editor = None;
                self.status_message = Some("Closed settings buffer".to_string());
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Char('s') | KeyAction::Char('S')
                if platform_modifier_active(event.modifiers) =>
            {
                self.save_settings_editor();
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Char('w') | KeyAction::Char('W')
                if platform_modifier_active(event.modifiers) =>
            {
                self.settings_editor = None;
                self.status_message = Some("Closed settings buffer".to_string());
                self.needs_redraw = true;
                return true;
            }
            KeyAction::SelectAll => {
                self.select_all_settings_editor();
                return true;
            }
            KeyAction::Copy => {
                self.copy_settings_selection_to_clipboard();
                return true;
            }
            KeyAction::Cut => {
                self.cut_settings_selection_to_clipboard();
                return true;
            }
            KeyAction::Paste => {
                self.paste_into_settings_editor();
                return true;
            }
            KeyAction::Tab => {
                if let Some(settings) = self.settings_editor.as_mut() {
                    replace_editor_selection(&mut settings.editor, "\t");
                }
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Enter => {
                if let Some(settings) = self.settings_editor.as_mut() {
                    replace_editor_selection(&mut settings.editor, "\n");
                }
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Char(ch)
                if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                if let Some(settings) = self.settings_editor.as_mut() {
                    replace_editor_selection(&mut settings.editor, &ch.to_string());
                }
                self.needs_redraw = true;
                return true;
            }
            KeyAction::Backspace | KeyAction::Delete => {
                let deleted_selection = if let Some(settings) = self.settings_editor.as_mut() {
                    delete_editor_selection(&mut settings.editor)
                } else {
                    false
                };
                if deleted_selection {
                    self.needs_redraw = true;
                    return true;
                }
            }
            _ => {}
        }

        let Some(editor_key) = input_event_to_editor_key(event) else {
            self.needs_redraw = true;
            return true;
        };
        let editor_key = match editor_key {
            EditorKey::Enter => EditorKey::ShiftEnter,
            other => other,
        };
        if let Some(settings) = self.settings_editor.as_mut() {
            let _ = settings.editor.handle_key(editor_key);
        }
        self.needs_redraw = true;
        true
    }

    fn reload_configuration(&mut self) {
        let config = WokConfig::load();
        self.config = config.clone();
        self.trigger_engine = trigger_engine_from_config(&config);
        self.layout_presets = default_layout_presets();
        self.layout_presets.extend(config.layout_presets.clone());
        self.layout_index = self
            .layout_index
            .min(self.layout_presets.len().saturating_sub(1));

        let theme = config.theme_path.as_ref().and_then(|path| {
            match wok_ui::theme_loader::load_theme(path) {
                Ok(mut theme) => {
                    if let Err(error) = wok_ui::theme_loader::apply_theme_overrides(
                        &mut theme,
                        &self.theme_overrides,
                    ) {
                        warn!("failed to apply live theme overrides after config reload: {error}");
                    }
                    Some(theme)
                }
                Err(error) => {
                    warn!("failed to reload configured theme: {error}");
                    None
                }
            }
        });
        self.theme_watcher = config
            .theme_path
            .as_ref()
            .and_then(|path| ThemeWatcher::new(path).ok());

        if let Some(theme) = theme {
            self.apply_theme_to_runtime(theme);
        } else {
            self.font = FontSystem::new(&config.font_family, config.font_size);
            if let Some(render) = self.render.as_mut() {
                render.atlas.clear();
            }
            self.prewarm_glyph_atlas();
            for pane in self.panes.values_mut() {
                pane.app.config = config.clone();
                pane.app
                    .input_editor
                    .set_position(match config.input_position {
                        wok_app::config::InputPosition::Top => {
                            wok_input::editor::InputPosition::Top
                        }
                        wok_app::config::InputPosition::Bottom => {
                            wok_input::editor::InputPosition::Bottom
                        }
                    });
                pane.app.zoom = wok_ui::zoom::ZoomManager::new(config.font_size);
            }
            self.invalidate_all_row_caches();
            self.sync_background_renderer(None);
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            self.needs_redraw = true;
        }

        for pane in self.panes.values_mut() {
            pane.app.config.typewriter_effect_enabled = self.config.typewriter_effect_enabled;
            pane.app.config.typewriter_effect_cps = self.config.typewriter_effect_cps;
            pane.app.config.typewriter_effect_max_pending_cells =
                self.config.typewriter_effect_max_pending_cells;
            if !self.config.typewriter_effect_enabled {
                pane.typewriter.clear();
            }
            pane.row_cache.invalidate();
        }

        self.refresh_plugin_config();
        self.refresh_plugin_snapshot();
        self.status_message = Some("Reloaded configuration".to_string());
    }

    fn handle_action(&mut self, action: Action) {
        if matches!(action, Action::EnterViMode) {
            self.enter_vi_mode();
            self.needs_redraw = true;
            return;
        }
        if matches!(action, Action::BlockSaveWorkflow) {
            self.save_selected_block_as_workflow();
            self.needs_redraw = true;
            return;
        }
        if matches!(action, Action::BlockExportMarkdown) {
            self.export_selected_block_bundle(BlockExportFormat::Markdown);
            self.needs_redraw = true;
            return;
        }
        if matches!(action, Action::BlockFilter) {
            self.toggle_failed_only_filter();
            self.needs_redraw = true;
            return;
        }
        if matches!(action, Action::ThemePicker) {
            self.open_theme_picker();
            return;
        }
        if matches!(action, Action::KeybindingDiscovery) {
            self.open_keybinding_discovery();
            return;
        }
        if matches!(action, Action::KeybindingEditor) {
            self.open_keybinding_editor();
            return;
        }
        if matches!(action, Action::SettingsDiscovery) {
            self.open_settings_discovery();
            return;
        }
        if matches!(action, Action::GitChanges) {
            self.open_git_changes_palette();
            return;
        }
        if matches!(action, Action::GitWorktrees) {
            self.open_git_worktrees_palette();
            return;
        }
        if matches!(action, Action::BlockExportJson) {
            self.export_selected_block_bundle(BlockExportFormat::Json);
            self.needs_redraw = true;
            return;
        }
        if matches!(action, Action::OpenSettings) {
            self.open_settings();
            self.needs_redraw = true;
            return;
        }
        if matches!(action, Action::ResetSettings) {
            self.reset_settings_to_defaults();
            return;
        }
        if matches!(action, Action::CloseMediaPreview) {
            self.close_media_preview();
            return;
        }
        if matches!(action, Action::ToggleMediaPreviewPlayback) {
            self.toggle_media_preview_playback();
            return;
        }
        if matches!(
            action,
            Action::SeekMediaPreviewBackward
                | Action::SeekMediaPreviewForward
                | Action::SlowMediaPreviewPlayback
                | Action::FastMediaPreviewPlayback
                | Action::StepMediaPreviewBackward
                | Action::StepMediaPreviewForward
                | Action::ToggleMediaPreviewMute
        ) {
            self.control_media_preview(action);
            return;
        }
        match action {
            Action::PreviewPathUnderCursor => {
                self.apply_path_action_under_cursor(PathCursorAction::Preview);
                return;
            }
            Action::OpenPathUnderCursor => {
                self.apply_path_action_under_cursor(PathCursorAction::Open);
                return;
            }
            Action::CopyPathUnderCursor => {
                self.apply_path_action_under_cursor(PathCursorAction::Copy);
                return;
            }
            Action::RevealPathUnderCursor => {
                self.apply_path_action_under_cursor(PathCursorAction::Reveal);
                return;
            }
            Action::TailPathUnderCursor => {
                self.apply_path_action_under_cursor(PathCursorAction::Tail);
                return;
            }
            Action::OpenScratchBuffer => {
                self.open_scratch_buffer();
                return;
            }
            Action::OpenScratchPalette => {
                self.open_scratch_palette();
                return;
            }
            Action::InsertScratchSelectionIntoInput => {
                self.insert_scratch_selection_into_input();
                return;
            }
            Action::SendScratchSelectionToPane => {
                self.send_scratch_selection_to_pane();
                return;
            }
            Action::OpenBlockInspector => {
                self.open_block_inspector();
                return;
            }
            Action::OpenBlockRerunHistory => {
                self.open_block_rerun_history();
                return;
            }
            Action::OpenBlockRerunComparison => {
                self.open_block_rerun_comparison();
                return;
            }
            Action::ToggleSearchRegex => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.global_search.mode =
                        active_pane.app.global_search.mode.toggled();
                    self.status_message = Some(format!(
                        "Search mode: {}",
                        active_pane.app.global_search.mode.label()
                    ));
                }
                self.refresh_global_search();
                self.needs_redraw = true;
                return;
            }
            Action::CycleSearchScope => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.global_search.scope =
                        active_pane.app.global_search.scope.next();
                    self.status_message = Some(format!(
                        "Search scope: {}",
                        active_pane.app.global_search.scope.label()
                    ));
                }
                self.refresh_global_search();
                self.needs_redraw = true;
                return;
            }
            Action::OpenSearchResults => {
                self.open_search_results_palette();
                return;
            }
            Action::SaveCurrentSearch => {
                self.save_current_search();
                return;
            }
            Action::OpenSavedSearches => {
                self.open_saved_searches_palette();
                return;
            }
            Action::OpenWorkspaceBrowser => {
                self.open_workspace_browser_palette();
                return;
            }
            _ => {}
        }
        if matches!(action, Action::ToggleTypewriterEffect) {
            self.config.typewriter_effect_enabled = !self.config.typewriter_effect_enabled;
            for pane in self.panes.values_mut() {
                pane.app.config.typewriter_effect_enabled = self.config.typewriter_effect_enabled;
                if !self.config.typewriter_effect_enabled {
                    pane.typewriter.clear();
                }
                pane.row_cache.invalidate();
            }
            self.status_message = Some(format!(
                "Typewriter output {}",
                if self.config.typewriter_effect_enabled {
                    "on"
                } else {
                    "off"
                }
            ));
            self.needs_redraw = true;
            return;
        }
        if matches!(action, Action::CycleVisualEffect) {
            self.config.visual_effect = self.config.visual_effect.next();
            for pane in self.panes.values_mut() {
                pane.app.config.visual_effect = self.config.visual_effect;
                pane.row_cache.invalidate();
            }
            self.status_message = Some(format!(
                "Visual effect: {}",
                self.config.visual_effect.as_str()
            ));
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
                        | Action::BlockPrevFailed
                        | Action::BlockNextFailed
                        | Action::BlockFind
                        | Action::BlockFilter
                        | Action::BlockDiff
                        | Action::BlockRerun
                        | Action::BlockRerunInSplit
                        | Action::BlockSaveWorkflow
                        | Action::BlockExportMarkdown
                        | Action::BlockExportJson
                        | Action::ToggleFailureTrendsPanel
                        | Action::ToggleWorkspaceInsightsPanel
                        | Action::GitChanges
                        | Action::GitWorktrees
                        | Action::SearchGlobal
                        | Action::CommandPalette
                        | Action::CommandSearch
                )
        }) {
            return;
        }

        if matches!(action, Action::BlockRerun) {
            self.prepare_rerun_diff_tracking();
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
                self.copy_selection_to_clipboard();
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

    fn scroll_active_viewport_rows(&mut self, rows: f32) {
        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };
        let max_scroll = pane_max_scroll(active_pane);
        active_pane.viewport.handle_scroll(rows, max_scroll);
        active_pane
            .terminal
            .state
            .set_display_offset(active_pane.viewport.display_offset());
    }

    fn complete_active_typewriter(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            return;
        };
        let Some(pane) = self.panes.get_mut(&pane_id) else {
            return;
        };
        if !pane.typewriter.has_pending() {
            return;
        }

        mark_typewriter_pending_rows_dirty(pane);
        pane.typewriter.clear();
        self.needs_redraw = true;
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
                let Some(mut state) = self.active_pane().and_then(|pane| match mode {
                    BlockQueryMode::Find | BlockQueryMode::Filter => {
                        let output_lines = pane
                            .app
                            .block_manager
                            .get_block(target_block_id)
                            .map(|block| collect_block_output_lines(&pane.terminal, block))?;
                        let mut state = BlockQueryState::new(mode, target_block_id);
                        state.search("", &output_lines);
                        Some(state)
                    }
                    BlockQueryMode::Diff => {
                        let (baseline_block_id, entries) =
                            build_block_diff_for_target(pane, target_block_id)?;
                        let mut state = BlockQueryState::new(mode, target_block_id);
                        state.set_diff_entries(baseline_block_id, entries);
                        Some(state)
                    }
                }) else {
                    let reason = if matches!(mode, BlockQueryMode::Diff) {
                        "No previous comparable block found for diff".to_string()
                    } else {
                        "No block available".to_string()
                    };
                    self.status_message = Some(reason);
                    return;
                };
                if matches!(mode, BlockQueryMode::Diff) {
                    let max_visible_lines = self.active_pane().map_or(0, |pane| {
                        filter_overlay_visible_lines(
                            pane.ui_rects.viewport,
                            self.font.metrics.cell_height,
                        )
                    });
                    state.ensure_current_line_visible(max_visible_lines);
                }
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.close_command_palette();
                    active_pane.app.global_search.deactivate();
                    active_pane.app.command_search = None;
                    active_pane.app.quick_select.dismiss();
                    active_pane.app.block_query = Some(state);
                }
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            OverlayEffect::ToggleFailureTrendsPanel => {
                self.show_failure_trends_panel = !self.show_failure_trends_panel;
                if self.show_failure_trends_panel {
                    self.show_workspace_insights_panel = false;
                }
                self.status_message = Some(if self.show_failure_trends_panel {
                    "Opened failure trends panel".to_string()
                } else {
                    "Closed failure trends panel".to_string()
                });
                self.needs_redraw = true;
            }
            OverlayEffect::ToggleWorkspaceInsightsPanel => {
                self.show_workspace_insights_panel = !self.show_workspace_insights_panel;
                if self.show_workspace_insights_panel {
                    self.show_failure_trends_panel = false;
                }
                self.status_message = Some(if self.show_workspace_insights_panel {
                    "Opened workspace insights panel".to_string()
                } else {
                    "Closed workspace insights panel".to_string()
                });
                self.needs_redraw = true;
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
            let can_edit_query = !matches!(block_query.mode, BlockQueryMode::Diff);

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
                    if can_edit_query
                        && !event.modifiers.ctrl
                        && !event.modifiers.alt
                        && !event.modifiers.meta =>
                {
                    block_query.query.pop();
                    query_changed = true;
                }
                KeyAction::Char(ch)
                    if can_edit_query
                        && !event.modifiers.ctrl
                        && !event.modifiers.alt
                        && !event.modifiers.meta =>
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
                KeyAction::ArrowDown | KeyAction::Char('n' | 'j')
                    if matches!(&event.action, KeyAction::ArrowDown)
                        || event.modifiers.ctrl
                            && !event.modifiers.alt
                            && !event.modifiers.meta =>
                {
                    command_search.next_match();
                }
                KeyAction::ArrowUp | KeyAction::Char('p' | 'k')
                    if matches!(&event.action, KeyAction::ArrowUp)
                        || event.modifiers.ctrl
                            && !event.modifiers.alt
                            && !event.modifiers.meta =>
                {
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

        if let Some(step_up) = owned_input_history_navigation(event) {
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
            KeyAction::ArrowDown | KeyAction::Char('n' | 'j')
                if matches!(&event.action, KeyAction::ArrowDown)
                    || event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.command_palette.select_next();
                }
                self.needs_redraw = true;
                true
            }
            KeyAction::ArrowUp | KeyAction::Char('p' | 'k')
                if matches!(&event.action, KeyAction::ArrowUp)
                    || event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
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
                        PaletteAction::PreviewMedia(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.open_media_preview(PathBuf::from(path));
                        }
                        PaletteAction::PreviewPath(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.preview_file_path(PathBuf::from(path));
                        }
                        PaletteAction::OpenPathExternal(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.open_path_externally(&PathBuf::from(path));
                        }
                        PaletteAction::CopyPath(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.copy_path_to_clipboard(&PathBuf::from(path));
                        }
                        PaletteAction::RevealPath(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.reveal_path_in_finder(&PathBuf::from(path));
                        }
                        PaletteAction::TailPath(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.tail_path_in_split(&PathBuf::from(path));
                        }
                        PaletteAction::SearchMatch { pane_id, row } => {
                            self.jump_to_search_match(pane_id, row);
                        }
                        PaletteAction::SavedSearch(query) => {
                            self.load_saved_search(query);
                        }
                        PaletteAction::DeleteSavedSearch(query) => {
                            self.delete_saved_search(query);
                        }
                        PaletteAction::ScratchSnippet(text) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                                active_pane.app.input_editor.is_active = true;
                                let _ = active_pane.app.input_editor.buffer.insert_at(0, &text);
                            }
                        }
                        PaletteAction::OpenScratch(name) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.open_scratch_buffer_named(&name);
                        }
                        PaletteAction::LoadWorkspace(name) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.handle_action(Action::LoadSession(name));
                        }
                        PaletteAction::RebindKeybinding(action_id) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.begin_keybinding_capture(action_id);
                        }
                        PaletteAction::ResetKeybinding(action_id) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.reset_user_keybinding(&action_id);
                        }
                        PaletteAction::ApplyTheme(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.apply_theme_selection(&path);
                        }
                        PaletteAction::GitFileDiff(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.open_git_file_diff(&path);
                        }
                        PaletteAction::GitStageFile(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.apply_git_file_action(&path, GitPaletteFileAction::Stage);
                        }
                        PaletteAction::GitUnstageFile(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.apply_git_file_action(&path, GitPaletteFileAction::Unstage);
                        }
                        PaletteAction::GitDiscardFile(path) => {
                            self.open_git_discard_confirmation(&path);
                        }
                        PaletteAction::GitConfirmDiscardFile(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.apply_git_file_action(&path, GitPaletteFileAction::Discard);
                        }
                        PaletteAction::Dismiss => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                        }
                        PaletteAction::ChangeDirectory(path) => {
                            if let Some(active_pane) = self.active_pane_mut() {
                                active_pane.app.close_command_palette();
                                active_pane.app.input_mode = InputMode::OwnedInput;
                            }
                            self.change_active_pane_directory(&path);
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
        if let Some(render) = self.render.as_mut() {
            render.atlas.clear();
        }
        self.prewarm_glyph_atlas();
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
        // surface a hint in the status bar when the input looks like a paste
        // or heredoc — gives users a chance to bail before sending big runs.
        let classification = wok_input_classifier::classify(&command);
        match classification.kind {
            wok_input_classifier::InputKind::Paste => {
                self.status_message = Some(format!(
                    "submitting {} bytes pasted across {} lines",
                    classification.hints.bytes,
                    classification.hints.lines + 1
                ));
            }
            wok_input_classifier::InputKind::Heredoc => {
                self.status_message =
                    Some("submitting heredoc — terminator must close on its own line".to_string());
            }
            _ => {}
        }
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

        let active_pane_id = self.active_pane_id().map(u64::from);
        let lines = self.collect_workspace_search_lines();
        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };
        active_pane
            .app
            .global_search
            .search_for_pane(&query, &lines, active_pane_id);
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

    /// Open a palette pre-populated with available themes (built-in +
    /// `~/.config/wok/themes/*.toml`). Selecting a theme writes its path
    /// to `theme_path` in config.toml and triggers a reload.
    fn open_theme_picker(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let entries = self.build_theme_palette_entries();
        if entries.is_empty() {
            self.status_message = Some("no themes found in ~/.config/wok/themes".to_string());
            return;
        }
        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.input_mode = InputMode::CommandPalette;
            active_pane.app.command_palette.open(entries);
        }
        self.needs_redraw = true;
    }

    fn build_theme_palette_entries(&self) -> Vec<PaletteEntry> {
        let mut entries = Vec::new();
        let theme_dir = WokConfig::config_dir().join("themes");
        let active_path = self
            .config
            .theme_path
            .as_ref()
            .and_then(|p| p.canonicalize().ok());
        if let Ok(rd) = std::fs::read_dir(&theme_dir) {
            let mut names: Vec<_> = rd
                .filter_map(|e| e.ok())
                .filter(|e| {
                    e.path()
                        .extension()
                        .and_then(|ext| ext.to_str())
                        .is_some_and(|ext| ext == "toml")
                })
                .collect();
            names.sort_by_key(|e| e.file_name());
            for entry in names {
                let path = entry.path();
                let label = path
                    .file_stem()
                    .and_then(|s| s.to_str())
                    .unwrap_or("theme")
                    .to_string();
                let description = if active_path == path.canonicalize().ok() {
                    "active".to_string()
                } else {
                    path.display().to_string()
                };
                entries.push(PaletteEntry {
                    label,
                    description,
                    category: PaletteCategory::Theme,
                    score: 0.0,
                    action: PaletteAction::ApplyTheme(path.display().to_string()),
                });
            }
        }
        entries
    }

    /// Open a structured palette listing every settings field with its
    /// current value, declared type, and a "→ open in TOML editor" hint.
    /// Selecting any entry opens config.toml in the existing settings buffer
    /// editor. This is the structured *view*; in-place form controls land in
    /// a future commit.
    fn open_settings_discovery(&mut self) {
        use wok_settings::Settings as _;
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let schema = wok_app::config::WokConfig::schema();
        let snapshot = self.settings_field_snapshot();
        let mut entries: Vec<PaletteEntry> = Vec::new();
        for field in &schema.fields {
            let current = snapshot
                .get(field.name)
                .cloned()
                .unwrap_or_else(|| "—".to_string());
            entries.push(PaletteEntry {
                label: format!("{}  =  {current}", field.name),
                description: format!("{}  →  open settings", field.type_name),
                category: PaletteCategory::SettingsField,
                score: 0.0,
                action: PaletteAction::BuiltInAction("open_settings".to_string()),
            });
        }
        if entries.is_empty() {
            self.status_message = Some("no settings fields registered".to_string());
            return;
        }
        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.input_mode = InputMode::CommandPalette;
            active_pane.app.command_palette.open(entries);
        }
        self.needs_redraw = true;
    }

    /// Open a palette listing changed files in the active pane's Git repo.
    fn open_git_changes_palette(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let Some(cwd) = self
            .panes
            .get(&pane_id)
            .map(|pane| pane.current_cwd.clone())
        else {
            self.status_message = Some("no active pane".to_string());
            return;
        };

        let entries = match wok_git::service::load_status(&cwd) {
            Ok(snapshot) => self.build_git_changes_palette_entries(snapshot),
            Err(wok_git::service::GitServiceError::NotGitRepository(_)) => {
                self.status_message = Some("not in a Git repository".to_string());
                return;
            }
            Err(error) => {
                self.status_message = Some(format!("failed to load Git changes: {error}"));
                return;
            }
        };

        if entries.is_empty() {
            self.status_message = Some("Git working tree is clean".to_string());
            return;
        }

        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.global_search.deactivate();
            active_pane.app.command_search = None;
            active_pane.app.block_query = None;
            active_pane.app.quick_select.dismiss();
            active_pane.app.input_mode = InputMode::CommandPalette;
            active_pane.app.command_palette.open(entries);
        }
        self.needs_redraw = true;
    }

    fn build_git_changes_palette_entries(
        &self,
        snapshot: wok_git::service::GitStatusSnapshot,
    ) -> Vec<PaletteEntry> {
        git_changes_palette_entries_from_snapshot(snapshot)
    }

    fn open_git_discard_confirmation(&mut self, path: &str) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let entries = git_discard_confirmation_entries(path);
        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.global_search.deactivate();
            active_pane.app.command_search = None;
            active_pane.app.block_query = None;
            active_pane.app.quick_select.dismiss();
            active_pane.app.input_mode = InputMode::CommandPalette;
            active_pane.app.command_palette.open(entries);
        }
        self.status_message = Some(format!("Confirm discard for {path}"));
        self.needs_redraw = true;
    }

    fn apply_git_file_action(&mut self, path: &str, action: GitPaletteFileAction) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let Some(cwd) = self
            .panes
            .get(&pane_id)
            .map(|pane| pane.current_cwd.clone())
        else {
            self.status_message = Some("no active pane".to_string());
            return;
        };

        let result = match action {
            GitPaletteFileAction::Stage => wok_git::service::stage_path(&cwd, path),
            GitPaletteFileAction::Unstage => wok_git::service::unstage_path(&cwd, path),
            GitPaletteFileAction::Discard => wok_git::service::discard_path(&cwd, path),
        };

        if let Err(error) = result {
            self.status_message = Some(match error {
                wok_git::service::GitServiceError::NotGitRepository(_) => {
                    "not in a Git repository".to_string()
                }
                error => format!("failed to {} {path}: {error}", action.verb()),
            });
            return;
        }

        let refresh = match wok_git::service::load_status(&cwd) {
            Ok(snapshot) => git_changes_refresh_after_action(snapshot),
            Err(error) => {
                self.status_message = Some(format!(
                    "{} {path}; failed to refresh Git changes: {error}",
                    action.past_tense()
                ));
                self.needs_redraw = true;
                return;
            }
        };

        match refresh {
            GitChangesRefresh::Clean => {
                self.status_message = Some("Git working tree is clean".to_string());
            }
            GitChangesRefresh::Entries(entries) => {
                if let Some(active_pane) = self.panes.get_mut(&pane_id) {
                    active_pane.app.global_search.deactivate();
                    active_pane.app.command_search = None;
                    active_pane.app.block_query = None;
                    active_pane.app.quick_select.dismiss();
                    active_pane.app.input_mode = InputMode::CommandPalette;
                    active_pane.app.command_palette.open(entries);
                }
                self.status_message = Some(format!("{} {path}", action.past_tense()));
            }
        }
        self.git_status_bar_cache.borrow_mut().remove(&cwd);
        self.needs_redraw = true;
    }

    /// Open an in-app unified diff overlay for one repository-relative path.
    fn open_git_file_diff(&mut self, path: &str) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let Some(cwd) = self
            .panes
            .get(&pane_id)
            .map(|pane| pane.current_cwd.clone())
        else {
            self.status_message = Some("no active pane".to_string());
            return;
        };

        let diff = match wok_git::service::load_file_diff(&cwd, path) {
            Ok(diff) => diff,
            Err(wok_git::service::GitServiceError::NotGitRepository(_)) => {
                self.status_message = Some("not in a Git repository".to_string());
                return;
            }
            Err(error) => {
                self.status_message = Some(format!("failed to load Git diff: {error}"));
                return;
            }
        };

        let title = format!("Git Diff {}", diff.path);
        let entries = git_diff_line_entries(diff.rows);
        if entries.is_empty() {
            self.status_message = Some(format!("no diff hunks for {}", diff.path));
            return;
        }

        let mut state = BlockQueryState::new(BlockQueryMode::Diff, 0);
        state.set_external_diff_entries(title, entries);
        let max_visible_lines = self.active_pane().map_or(0, |pane| {
            filter_overlay_visible_lines(pane.ui_rects.viewport, self.font.metrics.cell_height)
        });
        state.ensure_current_line_visible(max_visible_lines);

        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.global_search.deactivate();
            active_pane.app.command_search = None;
            active_pane.app.quick_select.dismiss();
            active_pane.app.block_query = Some(state);
        }
        self.status_message = Some(format!("Opened diff for {path}"));
        self.needs_redraw = true;
    }

    /// Open a palette listing worktrees for the active pane's Git repository.
    fn open_git_worktrees_palette(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let Some(cwd) = self
            .panes
            .get(&pane_id)
            .map(|pane| pane.current_cwd.clone())
        else {
            self.status_message = Some("no active pane".to_string());
            return;
        };

        let entries = match wok_git::service::load_worktrees(&cwd) {
            Ok(worktrees) => build_git_worktree_palette_entries(worktrees, &cwd),
            Err(wok_git::service::GitServiceError::NotGitRepository(_)) => {
                self.status_message = Some("not in a Git repository".to_string());
                return;
            }
            Err(error) => {
                self.status_message = Some(format!("failed to load Git worktrees: {error}"));
                return;
            }
        };

        if entries.is_empty() {
            self.status_message = Some("no Git worktrees found".to_string());
            return;
        }

        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.global_search.deactivate();
            active_pane.app.command_search = None;
            active_pane.app.block_query = None;
            active_pane.app.quick_select.dismiss();
            active_pane.app.input_mode = InputMode::CommandPalette;
            active_pane.app.command_palette.open(entries);
        }
        self.needs_redraw = true;
    }

    fn change_active_pane_directory(&mut self, path: &str) {
        let command = cd_command_for_path(path);
        self.send_raw_input_to_pty(command.as_bytes());
        if let Some(active_pane) = self.active_pane_mut() {
            active_pane.current_cwd = std::path::PathBuf::from(path);
        }
        self.status_message = Some(format!("Switching to {path}"));
        self.needs_redraw = true;
    }

    /// Render every WokConfig field as a string so the discovery palette can
    /// show current values. Optional fields render as `none` when unset.
    fn settings_field_snapshot(&self) -> std::collections::HashMap<&'static str, String> {
        use std::collections::HashMap;
        let c = &self.config;
        let mut m: HashMap<&'static str, String> = HashMap::new();
        m.insert("shell", c.shell.to_string());
        m.insert(
            "theme_path",
            c.theme_path
                .as_ref()
                .map(|p| p.display().to_string())
                .unwrap_or_else(|| "none".to_string()),
        );
        m.insert("font_family", c.font_family.clone());
        m.insert("font_size", format!("{}", c.font_size));
        m.insert("input_position", format!("{:?}", c.input_position));
        m.insert("command_entry_mode", format!("{:?}", c.command_entry_mode));
        m.insert("scrollback_lines", c.scrollback_lines.to_string());
        m.insert("cursor_style", format!("{:?}", c.cursor_style));
        m.insert("cursor_blink", c.cursor_blink.to_string());
        m.insert("tab_bar_visible", c.tab_bar_visible.to_string());
        m.insert("tab_bar_side", format!("{:?}", c.tab_bar_side));
        m.insert(
            "tab_bar_orientation",
            format!("{:?}", c.tab_bar_orientation),
        );
        m.insert(
            "tab_bar_size",
            c.tab_bar_size
                .map(|v| v.to_string())
                .unwrap_or_else(|| "auto".to_string()),
        );
        m.insert("status_bar_visible", c.status_bar_visible.to_string());
        m.insert("status_bar_side", format!("{:?}", c.status_bar_side));
        m.insert(
            "status_bar_size",
            c.status_bar_size
                .map(|v| v.to_string())
                .unwrap_or_else(|| "auto".to_string()),
        );
        m.insert("window_opacity", format!("{}", c.window_opacity));
        m.insert(
            "background_image",
            c.background_image
                .as_ref()
                .map(|p| p.display().to_string())
                .unwrap_or_else(|| "none".to_string()),
        );
        m.insert("background_opacity", format!("{}", c.background_opacity));
        m.insert("background_fit", format!("{:?}", c.background_fit));
        m.insert(
            "background_position",
            format!("{:?}", c.background_position),
        );
        m.insert(
            "background_width",
            c.background_width
                .map(|v| v.to_string())
                .unwrap_or_else(|| "auto".to_string()),
        );
        m.insert(
            "background_height",
            c.background_height
                .map(|v| v.to_string())
                .unwrap_or_else(|| "auto".to_string()),
        );
        m.insert(
            "terminal_background_opacity",
            c.terminal_background_opacity
                .map(|v| v.to_string())
                .unwrap_or_else(|| "auto".to_string()),
        );
        m.insert("pane_border_width", format!("{}", c.pane_border_width));
        m.insert(
            "focused_pane_border_width",
            format!("{}", c.focused_pane_border_width),
        );
        m.insert(
            "floating_pane_title_height",
            format!("{}", c.floating_pane_title_height),
        );
        m.insert(
            "typewriter_effect_enabled",
            c.typewriter_effect_enabled.to_string(),
        );
        m.insert(
            "typewriter_effect_cps",
            format!("{}", c.typewriter_effect_cps),
        );
        m.insert(
            "typewriter_effect_max_pending_cells",
            c.typewriter_effect_max_pending_cells.to_string(),
        );
        m.insert(
            "external_plugin_command",
            c.external_plugin_command
                .clone()
                .unwrap_or_else(|| "none".to_string()),
        );
        m.insert("copy_on_select", c.copy_on_select.to_string());
        m.insert(
            "confirm_close_with_running_process",
            c.confirm_close_with_running_process.to_string(),
        );
        m.insert("close_on_shell_exit", c.close_on_shell_exit.to_string());
        m.insert("restore_session", c.restore_session.to_string());
        m.insert("debug_overlay", c.debug_overlay.to_string());
        m.insert("command_telemetry", c.command_telemetry.to_string());
        m.insert("recent_keys", format!("{:?}", c.recent_keys));
        m.insert(
            "mouse_bindings",
            format!("{} entries", c.mouse_bindings.len()),
        );
        m.insert("triggers", format!("{} entries", c.triggers.len()));
        m.insert(
            "layout_presets",
            format!("{} entries", c.layout_presets.len()),
        );
        m
    }

    /// Open a read-only palette listing every active keybinding. Selecting
    /// an entry triggers its action immediately. This is the discovery UI;
    /// editing bindings still requires editing config + recompiling until
    /// the TOML keybind override layer ships.
    fn open_keybinding_discovery(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };
        let mut entries: Vec<PaletteEntry> = Vec::new();
        if let Some(pane) = self.panes.get(&pane_id) {
            let mut bindings: Vec<(String, &Action)> = pane
                .app
                .keybindings
                .bindings
                .iter()
                .map(|(combo, action)| (key_combo_label(combo), action))
                .collect();
            bindings.sort_by(|a, b| a.0.cmp(&b.0));
            for (label, action) in bindings {
                let Some(action_id) = action_to_palette_id(action) else {
                    continue;
                };
                let display = action_display_label(action);
                entries.push(PaletteEntry {
                    label: format!("{label}  →  {display}"),
                    description: action_id.clone(),
                    category: PaletteCategory::Keybinding,
                    score: 0.0,
                    action: PaletteAction::BuiltInAction(action_id),
                });
            }
        }
        if entries.is_empty() {
            self.status_message = Some("no keybindings registered".to_string());
            return;
        }
        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.input_mode = InputMode::CommandPalette;
            active_pane.app.command_palette.open(entries);
        }
        self.needs_redraw = true;
    }

    /// Open the editable keybinding palette. Selecting "Bind" closes the
    /// palette and captures the next key press into keybindings.toml.
    fn open_keybinding_editor(&mut self) {
        let Some(pane_id) = self.active_pane_id() else {
            self.status_message = Some("no active pane".to_string());
            return;
        };

        let current = self
            .panes
            .get(&pane_id)
            .map(|pane| action_binding_labels(&pane.app.keybindings))
            .unwrap_or_default();
        let defaults = action_binding_labels(&wok_app::keybindings::KeybindingConfig::default());

        let mut entries = Vec::new();
        for action in palette_actions_catalog() {
            let Some(action_id) = action_to_palette_id(&action) else {
                continue;
            };
            let label = action_display_label(&action);
            let current_label =
                binding_list_label(current.get(&action).cloned().unwrap_or_default());
            let default_label =
                binding_list_label(defaults.get(&action).cloned().unwrap_or_default());
            let user_override = self
                .user_keybinding_overrides
                .iter()
                .any(|binding| binding.action == action);

            entries.push(PaletteEntry {
                label: format!("Bind {label}"),
                description: format!("current: {current_label} | default: {default_label}"),
                category: PaletteCategory::Keybinding,
                score: 0.0,
                action: PaletteAction::RebindKeybinding(action_id.clone()),
            });

            if user_override {
                entries.push(PaletteEntry {
                    label: format!("Reset {label}"),
                    description: format!("remove user override | default: {default_label}"),
                    category: PaletteCategory::Keybinding,
                    score: 0.0,
                    action: PaletteAction::ResetKeybinding(action_id),
                });
            }
        }

        if let Some(active_pane) = self.panes.get_mut(&pane_id) {
            active_pane.app.input_mode = InputMode::CommandPalette;
            active_pane.app.command_palette.open(entries);
        }
        self.needs_redraw = true;
    }

    fn begin_keybinding_capture(&mut self, action_id: String) {
        let label = parse_palette_action(&action_id)
            .map(|action| action_display_label(&action))
            .unwrap_or_else(|| action_id.clone());
        self.pending_keybinding_capture = Some(action_id);
        self.status_message = Some(format!("Press a new shortcut for {label}. Esc cancels."));
        self.needs_redraw = true;
    }

    fn handle_keybinding_capture(&mut self, event: &InputEvent) -> bool {
        let Some(action_id) = self.pending_keybinding_capture.clone() else {
            return false;
        };
        if event.event_type == InputEventType::Release {
            return true;
        }
        if matches!(event.action, KeyAction::Escape) {
            self.pending_keybinding_capture = None;
            self.status_message = Some("Keybinding capture cancelled".to_string());
            self.needs_redraw = true;
            return true;
        }
        if is_modifier_only_key(&event.action) {
            return true;
        }

        let combo = wok_app::keybindings::KeyCombo {
            key: event.action.clone(),
            modifiers: event.modifiers,
        };
        let path = keybindings_toml_path();
        match wok_app::keybindings_toml::upsert_binding(&path, &action_id, &combo) {
            Ok(()) => {
                self.pending_keybinding_capture = None;
                self.reload_user_keybindings();
                self.status_message = Some(format!(
                    "Bound {action_id} to {}",
                    wok_app::keybindings_toml::format_keys(&combo)
                ));
            }
            Err(error) => {
                self.pending_keybinding_capture = None;
                self.status_message = Some(format!("Failed to save keybinding: {error}"));
            }
        }
        self.needs_redraw = true;
        true
    }

    fn reset_user_keybinding(&mut self, action_id: &str) {
        let path = keybindings_toml_path();
        match wok_app::keybindings_toml::remove_binding(&path, action_id) {
            Ok(true) => {
                self.reload_user_keybindings();
                self.status_message = Some(format!("Reset keybinding for {action_id}"));
            }
            Ok(false) => {
                self.status_message = Some(format!("No user keybinding for {action_id}"));
            }
            Err(error) => {
                self.status_message = Some(format!("Failed to reset keybinding: {error}"));
            }
        }
        self.needs_redraw = true;
    }

    fn reload_user_keybindings(&mut self) {
        let overrides = load_user_keybinding_overrides();
        self.user_keybinding_overrides = overrides;
        self.rebuild_runtime_keybindings();
    }

    fn rebuild_runtime_keybindings(&mut self) {
        let plugins = self.plugins.as_ref();
        let overrides = self.user_keybinding_overrides.clone();
        for pane in self.panes.values_mut() {
            pane.app.keybindings = wok_app::keybindings::KeybindingConfig::default();
            if let Some(plugins) = plugins {
                plugins.apply_keybindings(&mut pane.app, parse_lua_action);
            }
            pane.app.keybindings.apply_toml_overrides(overrides.clone());
        }
    }

    /// Persist `theme_path` to config.toml + reload configuration.
    fn apply_theme_selection(&mut self, theme_path: &str) {
        let config_path = WokConfig::config_dir().join("config.toml");
        let existing = std::fs::read_to_string(&config_path).unwrap_or_default();
        let new = upsert_toml_string_key(&existing, "theme_path", theme_path);
        match std::fs::write(&config_path, new) {
            Ok(()) => {
                self.reload_configuration();
                self.status_message = Some(format!(
                    "Applied theme '{}'",
                    std::path::Path::new(theme_path)
                        .file_stem()
                        .and_then(|s| s.to_str())
                        .unwrap_or(theme_path)
                ));
            }
            Err(error) => {
                warn!("failed to persist theme selection: {error}");
                self.status_message = Some(format!("Failed to save theme: {error}"));
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

    fn open_search_results_palette(&mut self) {
        self.refresh_global_search();
        let Some(search) = self.active_search_state() else {
            self.status_message = Some("Search is not active".to_string());
            self.needs_redraw = true;
            return;
        };
        if search.matches.is_empty() {
            self.status_message = Some("No search results to list".to_string());
            self.needs_redraw = true;
            return;
        }
        let mut entries = Vec::new();
        for (index, found) in search.matches.iter().take(200).enumerate() {
            let line = self
                .panes
                .get(&found.pane_id)
                .map(|pane| pane.terminal.state.row_text(found.row))
                .unwrap_or_default();
            let block_label = self
                .panes
                .get(&found.pane_id)
                .and_then(|pane| {
                    found.block_id.and_then(|block_id| {
                        pane.app
                            .block_manager
                            .get_block(block_id)
                            .map(|block| truncate_metric_text(&block.command_text, 48))
                    })
                })
                .map_or_else(
                    || "output".to_string(),
                    |command| format!("block: {command}"),
                );
            entries.push(PaletteEntry {
                label: format!(
                    "Pane {} line {} col {}",
                    found.pane_id,
                    found.row + 1,
                    usize::from(found.col_start) + 1
                ),
                description: format!("{block_label} | {}", truncate_metric_text(&line, 100)),
                category: PaletteCategory::SearchResult,
                score: 0.0,
                action: PaletteAction::SearchMatch {
                    pane_id: found.pane_id,
                    row: found.row,
                },
            });
            if index >= 199 {
                break;
            }
        }
        self.open_transient_palette(entries, "Search results");
    }

    fn open_saved_searches_palette(&mut self) {
        let queries = read_saved_searches();
        if queries.is_empty() {
            self.status_message = Some("No saved searches yet".to_string());
            self.needs_redraw = true;
            return;
        }
        let mut entries = Vec::new();
        for query in queries {
            entries.push(PaletteEntry {
                label: query.clone(),
                description: "Run saved search".to_string(),
                category: PaletteCategory::SavedSearch,
                score: 0.0,
                action: PaletteAction::SavedSearch(query.clone()),
            });
            entries.push(PaletteEntry {
                label: format!("Delete Saved Search {query}"),
                description: "Remove saved search query".to_string(),
                category: PaletteCategory::SavedSearch,
                score: 0.0,
                action: PaletteAction::DeleteSavedSearch(query),
            });
        }
        self.open_transient_palette(entries, "Saved searches");
    }

    fn open_workspace_browser_palette(&mut self) {
        let entries = workspace_session_entries()
            .into_iter()
            .map(|(name, description)| PaletteEntry {
                label: format!("Load Workspace {name}"),
                description,
                category: PaletteCategory::Workspace,
                score: 0.0,
                action: PaletteAction::LoadWorkspace(name),
            })
            .collect::<Vec<_>>();
        if entries.is_empty() {
            self.status_message = Some("No named workspaces saved yet".to_string());
            self.needs_redraw = true;
            return;
        }
        self.open_transient_palette(entries, "workspace browser");
    }

    fn save_current_search(&mut self) {
        let query = self
            .active_search_state()
            .map(|search| {
                if search.search_input.trim().is_empty() {
                    search.query
                } else {
                    search.search_input
                }
            })
            .unwrap_or_default();
        let query = query.trim();
        if query.is_empty() {
            self.status_message = Some("No active search query to save".to_string());
            self.needs_redraw = true;
            return;
        }
        let mut queries = read_saved_searches();
        queries.retain(|existing| existing != query);
        queries.insert(0, query.to_string());
        queries.truncate(100);
        match write_saved_searches(&queries) {
            Ok(()) => self.status_message = Some(format!("Saved search: {query}")),
            Err(error) => self.status_message = Some(format!("Failed to save search: {error}")),
        }
        self.needs_redraw = true;
    }

    fn load_saved_search(&mut self, query: String) {
        if let Some(active_pane) = self.active_pane_mut() {
            active_pane.app.close_command_palette();
            active_pane.app.global_search.activate();
            active_pane.app.global_search.search_input = query.clone();
        }
        self.refresh_global_search();
        self.scroll_to_current_search_match();
        self.status_message = Some(format!("Loaded saved search: {query}"));
        self.needs_redraw = true;
    }

    fn delete_saved_search(&mut self, query: String) {
        let mut queries = read_saved_searches();
        let before = queries.len();
        queries.retain(|existing| existing != &query);
        match write_saved_searches(&queries) {
            Ok(()) if queries.len() < before => {
                self.status_message = Some(format!("Deleted saved search: {query}"));
            }
            Ok(()) => self.status_message = Some(format!("Saved search not found: {query}")),
            Err(error) => {
                self.status_message = Some(format!("Failed to delete saved search: {error}"))
            }
        }
        self.needs_redraw = true;
    }

    fn jump_to_search_match(&mut self, pane_id: PaneId, row: usize) {
        if self.workspace.focus_pane(pane_id) {
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
        }
        if let Some(active_pane) = self.active_pane_mut() {
            active_pane.app.close_command_palette();
            if let Some(index) = active_pane
                .app
                .global_search
                .matches
                .iter()
                .position(|found| found.pane_id == pane_id && found.row == row)
            {
                active_pane.app.global_search.current = index;
            }
            let screen_lines = active_pane.terminal.state.screen_lines().max(1);
            let desired_start = row.saturating_sub(screen_lines / 2);
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
        }
        self.needs_redraw = true;
    }

    fn open_transient_palette(&mut self, entries: Vec<PaletteEntry>, label: &str) {
        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };
        active_pane.app.global_search.deactivate();
        active_pane.app.command_search = None;
        active_pane.app.block_query = None;
        active_pane.app.quick_select.dismiss();
        active_pane.app.command_palette.open(entries);
        active_pane.app.input_mode = InputMode::CommandPalette;
        active_pane.app.input_editor.buffer.set_text("");
        self.status_message = Some(format!("Opened {label}"));
        self.needs_redraw = true;
    }

    fn build_palette_entries(&self, pane_id: PaneId) -> Vec<PaletteEntry> {
        let mut entries = Vec::new();
        let Some(pane) = self.panes.get(&pane_id) else {
            return entries;
        };

        let mut action_bindings = HashMap::<Action, Vec<String>>::new();
        for (combo, action) in &pane.app.keybindings.bindings {
            action_bindings
                .entry(action.clone())
                .or_default()
                .push(key_combo_label(combo));
        }
        for bindings in action_bindings.values_mut() {
            bindings.sort();
            bindings.dedup();
        }

        let mut inserted_action_ids = HashSet::new();
        for action in palette_actions_catalog() {
            let Some(action_id) = action_to_palette_id(&action) else {
                continue;
            };
            inserted_action_ids.insert(action_id.clone());
            let keybinding = action_bindings
                .remove(&action)
                .and_then(|bindings| bindings.first().cloned())
                .unwrap_or_default();
            entries.push(PaletteEntry {
                label: action_display_label(&action),
                description: action_palette_description(&action, &keybinding),
                category: PaletteCategory::Action,
                score: 0.0,
                action: PaletteAction::BuiltInAction(action_id),
            });
        }

        for (action, keybindings) in action_bindings {
            if let Some(action_id) = action_to_palette_id(&action) {
                if inserted_action_ids.contains(&action_id) {
                    continue;
                }
                let keybinding = keybindings.first().cloned().unwrap_or_default();
                entries.push(PaletteEntry {
                    label: action_display_label(&action),
                    description: action_palette_description(&action, &keybinding),
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

        for query in read_saved_searches().into_iter().take(25) {
            entries.push(PaletteEntry {
                label: query.clone(),
                description: "Run saved search".to_string(),
                category: PaletteCategory::SavedSearch,
                score: 0.0,
                action: PaletteAction::SavedSearch(query),
            });
        }

        for (name, path) in scratch_files().into_iter().take(20) {
            entries.push(PaletteEntry {
                label: format!("Open Scratch {name}"),
                description: path.display().to_string(),
                category: PaletteCategory::ScratchSnippet,
                score: 0.0,
                action: PaletteAction::OpenScratch(name),
            });
        }

        for snippet in scratch_snippet_entries().into_iter().take(40) {
            entries.push(PaletteEntry {
                label: truncate_metric_text(&snippet, 80),
                description: "Insert scratch snippet".to_string(),
                category: PaletteCategory::ScratchSnippet,
                score: 0.0,
                action: PaletteAction::ScratchSnippet(snippet),
            });
        }

        for (name, description) in workspace_session_entries().into_iter().take(20) {
            entries.push(PaletteEntry {
                label: format!("Load Workspace {name}"),
                description,
                category: PaletteCategory::Workspace,
                score: 0.0,
                action: PaletteAction::LoadWorkspace(name),
            });
        }

        if pane.current_cwd.is_dir() {
            if let Ok(read_dir) = std::fs::read_dir(&pane.current_cwd) {
                for path in read_dir.flatten().take(50).map(|entry| entry.path()) {
                    entries.extend(file_action_palette_entries(&path));
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

        let mut seen_visible_paths = HashSet::new();
        for path in visible_file_paths_for_pane(pane).into_iter().take(40) {
            let path = self.resolve_preview_path(&path);
            if seen_visible_paths.insert(path.clone()) {
                entries.extend(file_action_palette_entries(&path));
            }
        }

        entries
    }

    fn scroll_to_current_block_query_match(&mut self) {
        let Some(block_query) = self.active_block_query_state() else {
            return;
        };
        if matches!(block_query.mode, BlockQueryMode::Diff) {
            let max_visible_lines = self.active_pane().map_or(0, |pane| {
                filter_overlay_visible_lines(pane.ui_rects.viewport, self.font.metrics.cell_height)
            });
            if let Some(active_pane) = self.active_pane_mut() {
                if let Some(state) = active_pane.app.block_query.as_mut() {
                    state.ensure_current_line_visible(max_visible_lines);
                }
            }
            return;
        }
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

    fn send_terminal_mouse_event(
        &mut self,
        event: TerminalMouseEvent,
        x: f64,
        y: f64,
        modifiers: wok_app::input::Modifiers,
    ) -> bool {
        if modifiers.shift {
            return false;
        }
        let Some(pane_id) = self.active_pane_id() else {
            return false;
        };
        let Some(cell) = self.pixel_to_cell_in_pane(pane_id, x, y) else {
            return false;
        };
        let Some(pane) = self.panes.get(&pane_id) else {
            return false;
        };
        let state = &pane.terminal.state;
        let report = match event {
            TerminalMouseEvent::Press(_) | TerminalMouseEvent::Release => {
                state.reports_mouse_clicks()
                    || state.reports_mouse_drag()
                    || state.reports_mouse_motion()
            }
            TerminalMouseEvent::Motion(button) => {
                state.reports_mouse_motion() || (button.is_some() && state.reports_mouse_drag())
            }
            TerminalMouseEvent::Wheel { .. } => state.reports_mouse(),
        };
        if !report {
            return false;
        }

        let sgr = state.uses_sgr_mouse();
        let Some(bytes) = encode_terminal_mouse_event(event, cell, modifiers, sgr) else {
            return false;
        };
        self.send_raw_input_to_pty(&bytes);
        true
    }

    fn send_alternate_scroll(&mut self, delta_x: f64, delta_y: f64) -> bool {
        let Some(active_pane) = self.active_pane() else {
            return false;
        };
        if !active_pane.terminal.state.is_alt_screen()
            || !active_pane.terminal.state.uses_alternate_scroll()
        {
            return false;
        }

        let (sequence, amount) = if delta_x.abs() > delta_y.abs() && delta_x.abs() > f64::EPSILON {
            if delta_x > 0.0 {
                (b"\x1b[C".as_slice(), delta_x)
            } else {
                (b"\x1b[D".as_slice(), -delta_x)
            }
        } else if delta_y.abs() > f64::EPSILON {
            if delta_y > 0.0 {
                (b"\x1b[A".as_slice(), delta_y)
            } else {
                (b"\x1b[B".as_slice(), -delta_y)
            }
        } else {
            return false;
        };

        let repetitions = amount.abs().round().clamp(1.0, 8.0) as usize;
        for _ in 0..repetitions {
            self.send_raw_input_to_pty(sequence);
        }
        true
    }

    fn selection_text(&self) -> Option<String> {
        let active_pane = self.active_pane()?;
        let (start, end) = active_pane.app.selection.selection_range()?;
        Some(extract_selection_text(&active_pane.terminal, start, end))
    }

    fn copy_selection_to_clipboard(&mut self) -> bool {
        let Some(text) = self.selection_text() else {
            return false;
        };
        let Some(active_pane) = self.active_pane_mut() else {
            return false;
        };
        active_pane.app.clipboard.copy(&text).is_ok()
    }

    fn copy_text_to_clipboard(&mut self, text: &str, label: &str) -> bool {
        let Some(active_pane) = self.active_pane_mut() else {
            return false;
        };
        match active_pane.app.clipboard.copy(text) {
            Ok(()) => {
                self.status_message = Some(format!("Copied {label}"));
                self.needs_redraw = true;
                true
            }
            Err(error) => {
                self.status_message = Some(format!("Failed to copy {label}: {error}"));
                self.needs_redraw = true;
                false
            }
        }
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

    fn open_context_menu_at(&mut self, pane_id: PaneId, x: f64, y: f64) -> bool {
        let Some(cell) = self.pixel_to_cell_in_pane(pane_id, x, y) else {
            return false;
        };
        let entries = self.context_menu_entries_for_cell(pane_id, cell);
        let target_block_id = self.block_id_at_cell(pane_id, cell);
        self.open_context_menu_with_entries(pane_id, x, y, entries, target_block_id)
    }

    fn open_context_menu_with_entries(
        &mut self,
        pane_id: PaneId,
        x: f64,
        y: f64,
        entries: Vec<ContextMenuEntry>,
        target_block_id: Option<u64>,
    ) -> bool {
        if entries.is_empty() {
            self.context_menu = None;
            return false;
        }
        self.context_menu = Some(ContextMenuState {
            x: x as f32,
            y: y as f32,
            entries,
            selected: 0,
            pane_id,
            target_block_id,
        });
        self.needs_redraw = true;
        true
    }

    fn open_tab_context_menu_at(&mut self, tab_index: usize, x: f64, y: f64) -> bool {
        self.switch_to_tab_index(tab_index);
        let Some(pane_id) = self.active_pane_id() else {
            return false;
        };
        self.open_context_menu_with_entries(
            pane_id,
            x,
            y,
            context_menu_tab_entries(tab_index),
            None,
        )
    }

    fn open_workspace_context_menu_at(&mut self, x: f64, y: f64) -> bool {
        let Some(pane_id) = self.active_pane_id() else {
            return false;
        };
        self.open_context_menu_with_entries(pane_id, x, y, context_menu_workspace_entries(), None)
    }

    fn context_menu_entries_for_cell(
        &self,
        pane_id: PaneId,
        cell: CellPos,
    ) -> Vec<ContextMenuEntry> {
        let mut entries = Vec::new();
        let has_selection = self
            .panes
            .get(&pane_id)
            .is_some_and(|pane| pane.app.selection.has_selection());
        if has_selection {
            entries.push(ContextMenuEntry {
                label: "Copy Selection".to_string(),
                description: "selection".to_string(),
                action: ContextMenuAction::Clipboard(ClipboardEffect::CopySelection),
            });
        }
        entries.push(ContextMenuEntry {
            label: "Paste".to_string(),
            description: "clipboard".to_string(),
            action: ContextMenuAction::Clipboard(ClipboardEffect::Paste),
        });

        if let Some(uri) = self.link_at_pane_cell(pane_id, cell) {
            entries.push(ContextMenuEntry {
                label: "Open Link".to_string(),
                description: truncate_menu_description(&uri),
                action: ContextMenuAction::OpenUrl(uri.clone()),
            });
            entries.push(ContextMenuEntry {
                label: "Copy Link".to_string(),
                description: truncate_menu_description(&uri),
                action: ContextMenuAction::CopyText(uri, "link".to_string()),
            });
        }

        if let Some(target) = self.path_at_cell(pane_id, cell) {
            let path = self.resolve_preview_path(&target.path);
            entries.extend(
                file_action_palette_entries(&path)
                    .into_iter()
                    .map(context_menu_entry_from_palette),
            );
        }

        if self.block_id_at_cell(pane_id, cell).is_some() {
            entries.extend([
                context_menu_builtin("Copy Block", "command + output", Action::BlockCopy),
                context_menu_builtin("Copy Command", "selected block", Action::BlockCopyCommand),
                context_menu_builtin("Copy Output", "selected block", Action::BlockCopyOutput),
                context_menu_builtin("Rerun Command", "selected block", Action::BlockRerun),
                context_menu_builtin(
                    "Rerun In Split",
                    "selected block",
                    Action::BlockRerunInSplit,
                ),
                context_menu_builtin("Collapse Output", "selected block", Action::BlockCollapse),
                context_menu_builtin(
                    "Inspect Block",
                    "metadata + output",
                    Action::OpenBlockInspector,
                ),
                context_menu_builtin("Diff Block", "compare output", Action::BlockDiff),
                context_menu_builtin(
                    "Bookmark Block",
                    "toggle bookmark",
                    Action::BlockToggleBookmark,
                ),
            ]);
        }

        entries.extend(context_menu_workspace_entries());
        entries
    }

    fn link_at_pane_cell(&self, pane_id: PaneId, cell: CellPos) -> Option<String> {
        let pane = self.panes.get(&pane_id)?;
        let absolute_row = pane
            .terminal
            .state
            .viewport_row_to_absolute(usize::from(cell.row));
        link_at_cell(&pane.terminal, absolute_row, usize::from(cell.col))
    }

    fn block_id_at_cell(&self, pane_id: PaneId, cell: CellPos) -> Option<u64> {
        let pane = self.panes.get(&pane_id)?;
        let absolute_row = pane
            .terminal
            .state
            .viewport_row_to_absolute(usize::from(cell.row));
        pane.app
            .block_manager
            .blocks
            .iter()
            .rev()
            .find_map(|block| {
                (absolute_row >= block.output_start_row && absolute_row <= block.output_end_row)
                    .then_some(block.id)
            })
    }

    fn close_context_menu(&mut self) {
        if self.context_menu.take().is_some() {
            self.needs_redraw = true;
        }
    }

    fn select_context_menu_entry(&mut self, index: usize) {
        if let Some(menu) = self.context_menu.as_mut() {
            if index < menu.entries.len() {
                menu.selected = index;
                self.needs_redraw = true;
            }
        }
    }

    fn run_context_menu_selected(&mut self) {
        let Some(menu) = self.context_menu.take() else {
            return;
        };
        let Some(entry) = menu.entries.get(menu.selected).cloned() else {
            return;
        };
        if let Some(pane) = self.panes.get_mut(&menu.pane_id) {
            if let Some(block_id) = menu.target_block_id {
                pane.app.select_block(block_id);
            }
        }
        self.execute_context_menu_action(entry.action);
        self.needs_redraw = true;
    }

    fn execute_context_menu_action(&mut self, action: ContextMenuAction) {
        match action {
            ContextMenuAction::Clipboard(effect) => self.apply_clipboard_effect(effect),
            ContextMenuAction::Palette(action) => self.execute_palette_action(action),
            ContextMenuAction::BuiltIn(action) => self.handle_action(action),
            ContextMenuAction::Window(action) => self.execute_window_context_action(action),
            ContextMenuAction::OpenUrl(uri) => {
                wok_ui::links::open_url(&uri);
                self.status_message = Some(format!("Opened {uri}"));
                self.needs_redraw = true;
            }
            ContextMenuAction::CopyText(text, label) => {
                self.copy_text_to_clipboard(&text, &label);
            }
        }
    }

    fn execute_window_context_action(&mut self, action: WindowContextAction) {
        let Some(window) = self.window.as_ref() else {
            self.status_message = Some("No active window".to_string());
            self.needs_redraw = true;
            return;
        };
        match action {
            WindowContextAction::ToggleFullscreen => {
                use winit::window::Fullscreen;
                let fullscreen = if window.fullscreen().is_some() {
                    None
                } else {
                    Some(Fullscreen::Borderless(None))
                };
                window.set_fullscreen(fullscreen);
                self.status_message = Some("Toggled full screen".to_string());
            }
            WindowContextAction::ToggleMaximized => {
                window.set_maximized(!window.is_maximized());
                self.status_message = Some("Toggled window zoom".to_string());
            }
            WindowContextAction::Minimize => {
                window.set_minimized(true);
                self.status_message = Some("Minimized window".to_string());
            }
        }
        self.needs_redraw = true;
    }

    fn execute_palette_action(&mut self, action: PaletteAction) {
        match action {
            PaletteAction::BuiltInAction(action_name) => {
                if let Some(action) = parse_palette_action(&action_name) {
                    self.handle_action(action);
                }
            }
            PaletteAction::PreviewMedia(path) => self.open_media_preview(PathBuf::from(path)),
            PaletteAction::PreviewPath(path) => self.preview_file_path(PathBuf::from(path)),
            PaletteAction::OpenPathExternal(path) => {
                self.open_path_externally(&PathBuf::from(path))
            }
            PaletteAction::CopyPath(path) => self.copy_path_to_clipboard(&PathBuf::from(path)),
            PaletteAction::RevealPath(path) => self.reveal_path_in_finder(&PathBuf::from(path)),
            PaletteAction::TailPath(path) => self.tail_path_in_split(&PathBuf::from(path)),
            PaletteAction::Dismiss => {}
            other => {
                self.status_message = Some(format!("Unsupported context action: {other:?}"));
                self.needs_redraw = true;
            }
        }
    }

    fn handle_context_menu_input(&mut self, event: &InputEvent) -> bool {
        let Some(menu) = self.context_menu.as_mut() else {
            return false;
        };
        match event.action {
            KeyAction::Escape => {
                self.close_context_menu();
                true
            }
            KeyAction::ArrowDown | KeyAction::Char('j') => {
                if !menu.entries.is_empty() {
                    menu.selected = (menu.selected + 1) % menu.entries.len();
                    self.needs_redraw = true;
                }
                true
            }
            KeyAction::ArrowUp | KeyAction::Char('k') => {
                if !menu.entries.is_empty() {
                    menu.selected = if menu.selected == 0 {
                        menu.entries.len() - 1
                    } else {
                        menu.selected - 1
                    };
                    self.needs_redraw = true;
                }
                true
            }
            KeyAction::Enter => {
                self.run_context_menu_selected();
                true
            }
            _ => {
                self.close_context_menu();
                false
            }
        }
    }

    fn handle_context_menu_mouse_event(&mut self, event: &wok_app::input::MouseEvent) -> bool {
        let Some(menu) = self.context_menu.clone() else {
            return false;
        };
        match event {
            wok_app::input::MouseEvent::Move { x, y, .. } => {
                if let Some(index) = context_menu_index_at(
                    &menu,
                    self.chrome_rects.content,
                    self.font.metrics.cell_width,
                    self.font.metrics.cell_height,
                    *x,
                    *y,
                ) {
                    self.select_context_menu_entry(index);
                }
                true
            }
            wok_app::input::MouseEvent::Press { button, x, y, .. } => {
                if *button == MouseButton::Right {
                    self.close_context_menu();
                    return false;
                }
                if *button != MouseButton::Left {
                    self.close_context_menu();
                    return true;
                }
                if let Some(index) = context_menu_index_at(
                    &menu,
                    self.chrome_rects.content,
                    self.font.metrics.cell_width,
                    self.font.metrics.cell_height,
                    *x,
                    *y,
                ) {
                    self.select_context_menu_entry(index);
                    self.run_context_menu_selected();
                } else {
                    self.close_context_menu();
                }
                true
            }
            wok_app::input::MouseEvent::Release { .. } => true,
            wok_app::input::MouseEvent::Scroll { .. } => {
                self.close_context_menu();
                true
            }
        }
    }

    fn handle_configured_mouse_binding(
        &mut self,
        button: MouseButton,
        x: f64,
        y: f64,
        modifiers: Modifiers,
    ) -> bool {
        let target = self.mouse_binding_target_at(x, y);
        let action = self.config.mouse_bindings.iter().find_map(|binding| {
            (mouse_button_matches(&binding.button, button)
                && mouse_modifiers_match(&binding.modifiers, modifiers)
                && mouse_binding_area_matches(binding.area, target.area))
            .then(|| binding.action.clone())
        });
        let Some(action) = action else {
            return false;
        };

        self.execute_mouse_binding_action(&action, target, x, y);
        true
    }

    fn mouse_binding_target_at(&self, x: f64, y: f64) -> MouseBindingTarget {
        let tab_index = self.tab_at_point(x, y);
        if let Some(tab_index) = tab_index {
            return MouseBindingTarget {
                area: MouseBindingArea::Tab,
                tab_index: Some(tab_index),
                pane_id: self.active_pane_id(),
            };
        }
        if point_in_rect(self.chrome_rects.tab_bar, x, y) {
            return MouseBindingTarget {
                area: MouseBindingArea::TabBar,
                tab_index: None,
                pane_id: self.active_pane_id(),
            };
        }
        if point_in_rect(self.chrome_rects.status, x, y) {
            return MouseBindingTarget {
                area: MouseBindingArea::Status,
                tab_index: None,
                pane_id: self.active_pane_id(),
            };
        }
        if point_in_rect(self.chrome_rects.content, x, y) {
            let pane_id = self
                .workspace
                .pane_at_point(self.chrome_rects.content, x as f32, y as f32)
                .or_else(|| self.active_pane_id());
            return MouseBindingTarget {
                area: MouseBindingArea::Content,
                tab_index: None,
                pane_id,
            };
        }
        MouseBindingTarget {
            area: MouseBindingArea::Any,
            tab_index: None,
            pane_id: self.active_pane_id(),
        }
    }

    fn execute_mouse_binding_action(
        &mut self,
        action: &str,
        target: MouseBindingTarget,
        x: f64,
        y: f64,
    ) {
        if let Some(tab_index) = target.tab_index {
            self.switch_to_tab_index(tab_index);
        } else if let Some(pane_id) = target.pane_id {
            if self.workspace.focus_pane(pane_id) {
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.needs_redraw = true;
            }
        }

        match action.trim() {
            "context_menu" => {
                if target.area == MouseBindingArea::Tab {
                    if let Some(tab_index) = target.tab_index {
                        self.open_tab_context_menu_at(tab_index, x, y);
                    }
                } else if target.area == MouseBindingArea::Content {
                    if let Some(pane_id) = target.pane_id {
                        self.open_context_menu_at(pane_id, x, y);
                    }
                } else {
                    self.open_workspace_context_menu_at(x, y);
                }
            }
            "workspace_context_menu" => {
                self.open_workspace_context_menu_at(x, y);
            }
            "tab_context_menu" => {
                if let Some(tab_index) = target.tab_index {
                    self.open_tab_context_menu_at(tab_index, x, y);
                }
            }
            "paste" => {
                self.apply_clipboard_effect(ClipboardEffect::Paste);
                self.needs_redraw = true;
            }
            action => {
                if let Some(action) = parse_lua_action(action) {
                    self.handle_action(action);
                } else {
                    self.status_message = Some(format!("Unknown mouse action: {action}"));
                    self.needs_redraw = true;
                }
            }
        }
    }

    fn handle_chrome_mouse_press(
        &mut self,
        button: MouseButton,
        x: f64,
        y: f64,
        _modifiers: Modifiers,
    ) -> bool {
        if let Some(tab_index) = self.tab_at_point(x, y) {
            match button {
                MouseButton::Left => {
                    self.switch_to_tab_index(tab_index);
                }
                MouseButton::Middle => {
                    self.close_tab_at_index(tab_index);
                }
                MouseButton::Right => {
                    self.open_tab_context_menu_at(tab_index, x, y);
                }
                _ => {}
            }
            return true;
        }

        if point_in_rect(self.chrome_rects.tab_bar, x, y) {
            match button {
                MouseButton::Left | MouseButton::Middle => {
                    self.handle_action(Action::NewTab);
                }
                MouseButton::Right => {
                    self.open_workspace_context_menu_at(x, y);
                }
                _ => {}
            }
            return true;
        }

        if point_in_rect(self.chrome_rects.status, x, y) {
            match button {
                MouseButton::Left => {
                    self.handle_action(Action::CommandPalette);
                }
                MouseButton::Middle => {
                    self.handle_action(Action::NewFloatingPane);
                }
                MouseButton::Right => {
                    self.open_workspace_context_menu_at(x, y);
                }
                _ => {}
            }
            return true;
        }

        false
    }

    fn close_tab_at_index(&mut self, tab_index: usize) {
        self.switch_to_tab_index(tab_index);
        self.handle_action(Action::CloseTab);
    }

    fn start_split_divider_drag_at(&mut self, x: f64, y: f64) -> bool {
        if !point_in_rect(self.chrome_rects.content, x, y) {
            return false;
        }
        let topmost_pane =
            self.workspace
                .pane_at_point(self.chrome_rects.content, x as f32, y as f32);
        if topmost_pane.is_some_and(|pane_id| self.workspace.is_active_floating_pane(pane_id)) {
            return false;
        }

        let tolerance = self.config.focused_pane_border_width.max(8.0);
        let Some(hit) = self.workspace.hit_test_split_divider(
            self.chrome_rects.content,
            x as f32,
            y as f32,
            tolerance,
        ) else {
            return false;
        };

        self.split_drag = Some(SplitDividerDragState {
            path: hit.path,
            direction: hit.direction,
            split_rect: hit.split_rect,
            last_x: x,
            last_y: y,
        });
        self.needs_redraw = true;
        true
    }

    fn start_floating_drag_at(&mut self, x: f64, y: f64) -> bool {
        let Some(pane_id) = self.active_pane_id() else {
            return false;
        };
        let Some(mode) = self.floating_drag_mode_at(pane_id, x, y) else {
            return false;
        };
        self.floating_drag = Some(FloatingDragState {
            pane_id,
            mode,
            last_x: x,
            last_y: y,
        });
        self.needs_redraw = true;
        true
    }

    fn floating_drag_mode_at(&self, pane_id: PaneId, x: f64, y: f64) -> Option<FloatingDragMode> {
        let floating = self.workspace.active_floating_pane(pane_id)?;
        let rect = floating.rect;
        if !point_in_rect(rect, x, y) {
            return None;
        }

        let tolerance = self.config.focused_pane_border_width.max(8.0);
        let xf = x as f32;
        let yf = y as f32;
        let edges = FloatingResizeEdges {
            left: xf <= rect.x + tolerance,
            right: xf >= rect.x + rect.w - tolerance,
            top: yf <= rect.y + tolerance,
            bottom: yf >= rect.y + rect.h - tolerance,
        };
        if edges.left || edges.right || edges.top || edges.bottom {
            return Some(FloatingDragMode::Resize(edges));
        }

        let title_height = self.config.floating_pane_title_height.max(18.0);
        if yf <= rect.y + title_height {
            return Some(FloatingDragMode::Move);
        }
        None
    }

    fn update_split_divider_drag(&mut self, x: f64, y: f64) -> bool {
        let Some(drag) = self.split_drag.as_mut() else {
            return false;
        };
        let delta = match drag.direction {
            SplitDirection::Horizontal => {
                let width = drag.split_rect.w.max(1.0);
                ((x - drag.last_x) as f32) / width
            }
            SplitDirection::Vertical => {
                let height = drag.split_rect.h.max(1.0);
                ((y - drag.last_y) as f32) / height
            }
        };
        drag.last_x = x;
        drag.last_y = y;
        if delta.abs() <= f32::EPSILON {
            return true;
        }
        if self.workspace.resize_split_divider(&drag.path, delta) {
            if let Some(window) = &self.window {
                self.sync_workspace_layout(window.inner_size());
            }
            self.needs_redraw = true;
        }
        true
    }
}

impl AppHandler for WokHandler {
    fn on_runtime_waker(&mut self, waker: RuntimeWaker) {
        self.runtime_waker = Some(waker);
    }

    fn on_init(&mut self, window: Arc<Window>) {
        let size = window.inner_size();
        self.window = Some(window.clone());

        // Initialize wgpu
        let instance = wgpu::Instance::new(&native_instance_descriptor());
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
        self.prewarm_glyph_atlas();

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
        let collect_phase_metrics = self.config.debug_overlay;
        let tick_started = collect_phase_metrics.then(Instant::now);
        let mut pty_drain_duration = Duration::ZERO;
        let mut semantic_events_duration = Duration::ZERO;
        let mut replay_capture_duration = Duration::ZERO;
        let mut input_sync_duration = Duration::ZERO;
        let mut output_hooks_duration = Duration::ZERO;
        let mut block_query_duration = Duration::ZERO;

        if self.config.debug_overlay {
            self.system_metrics.maybe_refresh();
            self.needs_redraw = true;
        }
        if let Some(plugins) = &self.plugins {
            plugins.pump_timers(64);
        }
        self.drain_plugin_side_effects();
        self.sync_attached_session_snapshot();
        self.pump_remote_control();
        self.prune_recent_keys();

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

        if let Some(watcher) = self.config_watcher.as_mut() {
            if watcher.poll() {
                self.reload_configuration();
                info!("config.toml reloaded from disk");
                self.status_message = Some("config.toml reloaded".to_string());
                self.needs_redraw = true;
            }
        }

        let keybindings_changed = self.keybindings_watcher.as_mut().is_some_and(|w| w.poll());
        if keybindings_changed {
            self.reload_user_keybindings();
            let count = self.user_keybinding_overrides.len();
            info!("keybindings.toml reloaded ({count} overrides)");
            self.status_message = Some(format!("keybindings.toml reloaded ({count} overrides)"));
            self.needs_redraw = true;
        }

        if let Some(theme) = self.theme_watcher.as_mut().and_then(ThemeWatcher::poll) {
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
        let mut exited_pane_ids = Vec::new();
        for pane_id in pane_ids {
            let mut semantic_events = Vec::new();
            let mut is_dirty = false;
            let mut command_ended = false;
            let previously_exited = self
                .panes
                .get(&pane_id)
                .is_some_and(|pane| pane.terminal.exited);
            let previous_input_active = self
                .panes
                .get(&pane_id)
                .map(|pane| pane.app.input_editor.is_active)
                .unwrap_or(false);
            if let Some(pane) = self.panes.get_mut(&pane_id) {
                measure_phase(collect_phase_metrics, &mut pty_drain_duration, || {
                    pane.terminal.process_pty_output();
                });

                semantic_events =
                    measure_phase(collect_phase_metrics, &mut semantic_events_duration, || {
                        pane.terminal.drain_semantic_events()
                    });

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
            let now_exited = self
                .panes
                .get(&pane_id)
                .is_some_and(|pane| pane.terminal.exited);
            if now_exited && !previously_exited {
                exited_pane_ids.push(pane_id);
            }
            if !semantic_events.is_empty() {
                command_ended = semantic_events
                    .iter()
                    .any(|event| matches!(event, SemanticEvent::CommandEnd { .. }));
                measure_phase(collect_phase_metrics, &mut semantic_events_duration, || {
                    self.handle_semantic_events(pane_id, semantic_events);
                });
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
            measure_phase(collect_phase_metrics, &mut replay_capture_duration, || {
                self.capture_replay_snapshot_for_pane(pane_id, force_marker);
            });

            if force_marker {
                if let Some(pane) = self.panes.get_mut(&pane_id) {
                    pane.pending_replay_block_marker = false;
                }
            }
            measure_phase(collect_phase_metrics, &mut input_sync_duration, || {
                self.sync_owned_input_state_for_pane(pane_id);
            });

            if output_line_hooks_enabled {
                measure_phase(collect_phase_metrics, &mut output_hooks_duration, || {
                    output_line_events
                        .extend(self.collect_output_line_events_for_pane(pane_id, command_ended));
                });
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
                measure_phase(collect_phase_metrics, &mut block_query_duration, || {
                    self.refresh_block_query_for_pane(pane_id);
                });
            }
            self.needs_redraw |= is_dirty;
        }

        if !matches!(self.config.visual_effect, VisualEffectMode::None)
            && self.config.visual_effect_animated
        {
            for pane in self.panes.values_mut() {
                pane.row_cache.dirty.mark_fully_damaged();
            }
            self.needs_redraw = true;
        }

        if self.config.typewriter_effect_enabled {
            for pane in self.panes.values_mut() {
                if pane.typewriter.has_pending() {
                    mark_typewriter_pending_rows_dirty(pane);
                    self.needs_redraw = true;
                }
            }
        } else {
            for pane in self.panes.values_mut() {
                if pane.typewriter.has_pending() {
                    pane.typewriter.clear();
                    pane.row_cache.invalidate();
                    self.needs_redraw = true;
                }
            }
        }

        if output_line_hooks_enabled {
            measure_phase(collect_phase_metrics, &mut output_hooks_duration, || {
                self.dispatch_output_line_hooks(output_line_events);
            });
        }
        self.dispatch_shell_completion_hooks(&exited_pane_ids);
        relayout |= self.handle_shell_exit_transitions(&exited_pane_ids);
        if !self.panes.is_empty() && self.panes.values().all(|pane| pane.terminal.exited) {
            self.exit_requested = true;
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
        if let Some(tick_started) = tick_started {
            self.metrics.pty_drain.record(pty_drain_duration);
            self.metrics
                .semantic_events
                .record(semantic_events_duration);
            self.metrics.replay_capture.record(replay_capture_duration);
            self.metrics.input_sync.record(input_sync_duration);
            self.metrics.output_hooks.record(output_hooks_duration);
            self.metrics.block_query.record(block_query_duration);
            self.metrics.frame_tick.record(tick_started.elapsed());
        }

        self.needs_redraw
    }

    fn on_redraw(&mut self) {
        if !self.needs_redraw {
            return;
        }
        let redraw_started = Instant::now();
        let collect_phase_metrics = self.config.debug_overlay;

        // Build vertex data from terminal grid
        let mut quad_build_duration = Duration::ZERO;
        measure_phase(collect_phase_metrics, &mut quad_build_duration, || {
            self.build_quads();
        });
        if collect_phase_metrics {
            self.metrics.quad_build.record(quad_build_duration);
            self.metrics.last_quad_count = self
                .render
                .as_ref()
                .map_or(0, |render| render.batch.quad_count());
        }

        // Render
        let clear_theme = self
            .active_pane()
            .map(|pane| pane.app.theme.clone())
            .unwrap_or_default();
        let mut gpu_render_duration = Duration::ZERO;
        measure_phase(collect_phase_metrics, &mut gpu_render_duration, || {
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
                            warn!("GPU surface became invalid ({e:?}); resizing surface");
                            let (w, h) = render.gpu.dimensions();
                            render.gpu.resize(&render.surface, w, h);
                        }
                        wgpu::SurfaceError::OutOfMemory => {
                            warn!("GPU out of memory");
                            self.exit_requested = true;
                        }
                        wgpu::SurfaceError::Timeout => {
                            warn!("GPU frame presentation timed out");
                        }
                        wgpu::SurfaceError::Other => {
                            warn!("GPU surface error: {e:?}");
                        }
                    }
                }
            }
        });
        if collect_phase_metrics {
            self.metrics.gpu_render.record(gpu_render_duration);
        }

        let mut mark_clean_duration = Duration::ZERO;
        measure_phase(collect_phase_metrics, &mut mark_clean_duration, || {
            for pane in self.panes.values_mut() {
                pane.terminal.mark_clean();
                pane.viewport.mark_rendered();
            }
        });
        if collect_phase_metrics {
            self.metrics.mark_clean.record(mark_clean_duration);
        }
        if self.redraw_history_ms.len() >= 60 {
            self.redraw_history_ms.pop_front();
        }
        let redraw_duration = redraw_started.elapsed();
        self.metrics.last_frame_duration_us = redraw_duration.as_micros() as u64;
        self.redraw_history_ms
            .push_back(redraw_duration.as_secs_f32() * 1000.0);
        self.frame_timestamps.push_back(Instant::now());
        while self.frame_timestamps.len() > 120 {
            self.frame_timestamps.pop_front();
        }
        self.needs_redraw = false;
    }

    fn should_exit(&mut self) -> bool {
        if !self.exit_requested {
            return false;
        }
        self.exit_requested = false;
        self.on_close_requested()
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
            if self.handle_context_menu_input(&event) {
                return;
            }

            self.complete_active_typewriter();

            if self.handle_keybinding_capture(&event) {
                return;
            }

            if matches!(event.action, KeyAction::Escape) && self.media_preview.is_some() {
                self.close_media_preview();
                return;
            }

            self.record_recent_key(&event);

            if self.handle_file_preview_input(&event) {
                return;
            }

            if self.handle_scratch_buffer_input(&event) {
                return;
            }

            if self.handle_settings_editor_input(&event) {
                return;
            }

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
        if self.context_menu.is_some() && self.handle_context_menu_mouse_event(&event) {
            return;
        }

        match event {
            wok_app::input::MouseEvent::Press {
                button,
                x,
                y,
                modifiers,
            } => {
                self.pressed_mouse_button = Some(button);
                if !point_in_rect(self.chrome_rects.content, x, y)
                    && self.handle_configured_mouse_binding(button, x, y, modifiers)
                {
                    return;
                }
                if self.handle_chrome_mouse_press(button, x, y, modifiers) {
                    return;
                }
                if button == MouseButton::Left && self.start_split_divider_drag_at(x, y) {
                    return;
                }
                self.focus_pane_at_point(x, y);
                if button == MouseButton::Left && self.start_floating_drag_at(x, y) {
                    return;
                }
                if self.send_terminal_mouse_event(
                    TerminalMouseEvent::Press(button),
                    x,
                    y,
                    modifiers,
                ) {
                    self.needs_redraw = true;
                    return;
                }
                if self.handle_configured_mouse_binding(button, x, y, modifiers) {
                    return;
                }
                if button == MouseButton::Middle {
                    if modifiers.alt && platform_modifier_active(modifiers) {
                        self.handle_action(Action::NewFloatingPane);
                        self.needs_redraw = true;
                        return;
                    }
                    if modifiers.alt {
                        self.handle_action(Action::SplitHorizontal);
                        self.needs_redraw = true;
                        return;
                    }
                    if platform_modifier_active(modifiers) {
                        self.handle_action(Action::SplitVertical);
                        self.needs_redraw = true;
                        return;
                    }
                    self.apply_clipboard_effect(ClipboardEffect::Paste);
                    self.needs_redraw = true;
                    return;
                }
                if button == MouseButton::Right {
                    if let Some(pane_id) = self.active_pane_id() {
                        self.open_context_menu_at(pane_id, x, y);
                        self.needs_redraw = true;
                    }
                    return;
                }
                if button != MouseButton::Left {
                    return;
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
                    let click_count = self
                        .active_pane()
                        .map_or(0, |pane| pane.app.selection.click_count());
                    if click_count == 2 {
                        let selection = self
                            .active_pane()
                            .and_then(|pane| word_selection_at_cell(&pane.terminal, cell));
                        if let (Some((start, end)), Some(active_pane)) =
                            (selection, self.active_pane_mut())
                        {
                            active_pane.app.selection.state =
                                SelectionState::Selected { start, end };
                        }
                    } else if click_count >= 3 {
                        if let Some(active_pane) = self.active_pane_mut() {
                            active_pane.app.selection.state = SelectionState::Selected {
                                start: CellPos {
                                    row: cell.row,
                                    col: 0,
                                },
                                end: CellPos {
                                    row: cell.row,
                                    col: u16::MAX,
                                },
                            };
                        }
                    }
                    self.needs_redraw = true;
                }
            }
            wok_app::input::MouseEvent::Release {
                button,
                x,
                y,
                modifiers,
            } => {
                self.pressed_mouse_button = None;
                let was_internal_drag = self.floating_drag.is_some() || self.split_drag.is_some();
                self.floating_drag = None;
                self.split_drag = None;
                if was_internal_drag {
                    self.needs_redraw = true;
                    return;
                }
                if self.send_terminal_mouse_event(TerminalMouseEvent::Release, x, y, modifiers) {
                    self.needs_redraw = true;
                    return;
                }
                if button != MouseButton::Left {
                    return;
                }
                let was_selecting = self.active_pane().is_some_and(|pane| {
                    matches!(pane.app.selection.state, SelectionState::Selecting { .. })
                });
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.selection.handle_mouse_up();
                }
                let has_selection = self
                    .active_pane()
                    .is_some_and(|pane| pane.app.selection.has_selection());
                if (was_selecting || has_selection) && self.config.copy_on_select {
                    self.copy_selection_to_clipboard();
                }
                self.needs_redraw = true;
            }
            wok_app::input::MouseEvent::Move { x, y, modifiers } => {
                if self.split_drag.is_some() {
                    self.update_split_divider_drag(x, y);
                    return;
                }
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
                        FloatingDragMode::Resize(edges) => {
                            self.workspace.resize_floating_pane_edges(
                                drag.pane_id,
                                edges,
                                dx,
                                dy,
                                self.chrome_rects.content,
                            )
                        }
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
                if self.send_terminal_mouse_event(
                    TerminalMouseEvent::Motion(self.pressed_mouse_button),
                    x,
                    y,
                    modifiers,
                ) {
                    self.needs_redraw = true;
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
            wok_app::input::MouseEvent::Scroll {
                x,
                y,
                delta_x,
                delta_y,
                is_pixel_delta,
                modifiers,
            } => {
                if delta_y.abs() < f64::EPSILON && delta_x.abs() < f64::EPSILON {
                    return;
                }
                if y >= f64::from(self.chrome_rects.tab_bar.y)
                    && y <= f64::from(self.chrome_rects.tab_bar.y + self.chrome_rects.tab_bar.h)
                    && x >= f64::from(self.chrome_rects.tab_bar.x)
                    && x <= f64::from(self.chrome_rects.tab_bar.x + self.chrome_rects.tab_bar.w)
                    && self.scroll_tab_bar(delta_x, delta_y)
                {
                    return;
                }

                if modifiers.shift || delta_x.abs() > delta_y.abs() {
                    let horizontal_delta = if delta_x.abs() > f64::EPSILON {
                        delta_x
                    } else {
                        delta_y
                    };
                    if self.send_terminal_mouse_event(
                        TerminalMouseEvent::Wheel {
                            horizontal: true,
                            positive: horizontal_delta > 0.0,
                        },
                        x,
                        y,
                        modifiers,
                    ) {
                        self.needs_redraw = true;
                        return;
                    }
                }

                if self.send_terminal_mouse_event(
                    TerminalMouseEvent::Wheel {
                        horizontal: false,
                        positive: delta_y > 0.0,
                    },
                    x,
                    y,
                    modifiers,
                ) {
                    self.needs_redraw = true;
                    return;
                }

                if self.send_alternate_scroll(delta_x, delta_y) {
                    self.needs_redraw = true;
                    return;
                }

                let scroll_rows = if is_pixel_delta {
                    (delta_y as f32 / self.font.metrics.cell_height.max(1.0)).clamp(-24.0, 24.0)
                } else {
                    delta_y as f32
                };
                self.scroll_active_viewport_rows(scroll_rows);
                self.needs_redraw = true;
            }
        }
    }

    fn on_file_drop(&mut self, path: PathBuf) {
        let text = shell_quote_path(&path.display().to_string());
        if let Some(active_pane) = self.active_pane_mut() {
            if active_pane.app.input_mode == InputMode::OwnedInput
                || active_pane.app.input_editor.is_active
            {
                let _ = active_pane.app.input_editor.buffer.insert_at(0, &text);
                self.status_message = Some(format!("Inserted dropped path: {}", path.display()));
                self.needs_redraw = true;
                return;
            }
        }
        self.send_raw_input_to_pty(text.as_bytes());
        self.status_message = Some(format!("Sent dropped path: {}", path.display()));
        self.needs_redraw = true;
    }

    fn on_menu_action(&mut self, action: AppMenuAction) -> bool {
        if self.settings_editor.is_some() {
            match action {
                AppMenuAction::Copy => {
                    self.copy_settings_selection_to_clipboard();
                    return false;
                }
                AppMenuAction::Paste => {
                    self.paste_into_settings_editor();
                    return false;
                }
                AppMenuAction::SelectAll => {
                    self.select_all_settings_editor();
                    return false;
                }
                AppMenuAction::OpenSettings => {
                    self.handle_action(Action::OpenSettings);
                    return false;
                }
                _ => {}
            }
        }

        match action {
            AppMenuAction::OpenSettings => self.handle_action(Action::OpenSettings),
            AppMenuAction::ReloadConfiguration => {
                self.reload_configuration();
                self.needs_redraw = true;
            }
            AppMenuAction::OpenCommandPalette => self.handle_action(Action::CommandPalette),
            AppMenuAction::NewTab => self.handle_action(Action::NewTab),
            AppMenuAction::CloseTab => self.handle_action(Action::CloseTab),
            AppMenuAction::Copy => self.handle_action(Action::Copy),
            AppMenuAction::Paste => self.handle_action(Action::Paste),
            AppMenuAction::SelectAll => self.handle_action(Action::SelectAll),
            AppMenuAction::ZoomIn => self.handle_action(Action::ZoomIn),
            AppMenuAction::ZoomOut => self.handle_action(Action::ZoomOut),
            AppMenuAction::ZoomReset => self.handle_action(Action::ZoomReset),
            AppMenuAction::ToggleInputPosition => self.handle_action(Action::ToggleInputPosition),
            AppMenuAction::NextTab => self.handle_action(Action::NextTab),
            AppMenuAction::PrevTab => self.handle_action(Action::PrevTab),
            AppMenuAction::Quit => return self.on_close_requested(),
        }
        false
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
            // drive the wok_ui::quit_warning state machine; preserve
            // tap-twice cancellation via the existing pending instant.
            let mut warning = wok_ui::quit_warning::QuitWarning::new();
            let _ = warning.on_running_children(self.running_process_count());
            let effect = warning.on_quit_request();
            let confirmed = self
                .pending_close_confirmation
                .is_some_and(|instant| instant.elapsed().as_secs_f32() <= 2.0);
            if matches!(effect, wok_ui::quit_warning::Effect::Show) && !confirmed {
                self.pending_close_confirmation = Some(Instant::now());
                self.status_message = Some(format!(
                    "{} running process(es). Close again within 2s to exit.",
                    warning.running_children()
                ));
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

fn encode_terminal_mouse_event(
    event: TerminalMouseEvent,
    cell: CellPos,
    modifiers: wok_app::input::Modifiers,
    sgr: bool,
) -> Option<Vec<u8>> {
    let mut code = match event {
        TerminalMouseEvent::Press(button) | TerminalMouseEvent::Motion(Some(button)) => {
            mouse_button_code(button)?
        }
        TerminalMouseEvent::Release => 3,
        TerminalMouseEvent::Motion(None) => 3,
        TerminalMouseEvent::Wheel {
            horizontal: false,
            positive: true,
        } => 64,
        TerminalMouseEvent::Wheel {
            horizontal: false,
            positive: false,
        } => 65,
        TerminalMouseEvent::Wheel {
            horizontal: true,
            positive: true,
        } => 66,
        TerminalMouseEvent::Wheel {
            horizontal: true,
            positive: false,
        } => 67,
    };
    if matches!(event, TerminalMouseEvent::Motion(_)) {
        code += 32;
    }
    if modifiers.shift {
        code += 4;
    }
    if modifiers.alt {
        code += 8;
    }
    if modifiers.ctrl {
        code += 16;
    }

    let x = cell.col + 1;
    let y = cell.row + 1;
    if sgr {
        let suffix = if matches!(event, TerminalMouseEvent::Release) {
            'm'
        } else {
            'M'
        };
        return Some(format!("\x1b[<{code};{x};{y}{suffix}").into_bytes());
    }

    let encoded_x = u8::try_from(x + 32).ok()?;
    let encoded_y = u8::try_from(y + 32).ok()?;
    let encoded_code = u8::try_from(code + 32).ok()?;
    Some(vec![0x1b, b'[', b'M', encoded_code, encoded_x, encoded_y])
}

fn mouse_button_code(button: MouseButton) -> Option<u16> {
    match button {
        MouseButton::Left => Some(0),
        MouseButton::Middle => Some(1),
        MouseButton::Right => Some(2),
        _ => None,
    }
}

fn word_selection_at_cell(terminal: &Terminal, cell: CellPos) -> Option<(CellPos, CellPos)> {
    let absolute_row = terminal
        .state
        .viewport_row_to_absolute(usize::from(cell.row));
    let row = terminal
        .state
        .row_slice(absolute_row, 0, terminal.state.columns());
    let (start, end) = word_selection_range(&row, usize::from(cell.col))?;

    Some((
        CellPos {
            row: cell.row,
            col: start.min(usize::from(u16::MAX)) as u16,
        },
        CellPos {
            row: cell.row,
            col: end.min(usize::from(u16::MAX)) as u16,
        },
    ))
}

fn word_selection_range(row: &str, col: usize) -> Option<(usize, usize)> {
    let chars = row.chars().collect::<Vec<_>>();
    if col >= chars.len() || chars[col].is_whitespace() {
        return None;
    }

    let mut start = col;
    while start > 0 && !chars[start - 1].is_whitespace() {
        start -= 1;
    }
    let mut end = col;
    while end + 1 < chars.len() && !chars[end + 1].is_whitespace() {
        end += 1;
    }
    Some((start, end))
}

/// Load `~/.config/wok/keybindings.toml` if present. Logs warnings; returns
/// empty Vec on missing file or parse error.
fn load_user_keybinding_overrides() -> Vec<wok_app::keybindings_toml::BindingOverride> {
    let path = keybindings_toml_path();
    if !path.exists() {
        return Vec::new();
    }
    match wok_app::keybindings_toml::load(&path) {
        Ok((overrides, warnings)) => {
            for w in warnings {
                warn!("keybindings.toml: {w}");
            }
            overrides
        }
        Err(error) => {
            warn!("failed to load keybindings.toml: {error}");
            Vec::new()
        }
    }
}

/// Insert or replace a top-level `key = "value"` line in a TOML document.
/// Preserves comments + other lines. Strings are double-quoted; embedded
/// double-quotes are escaped.
fn upsert_toml_string_key(existing: &str, key: &str, value: &str) -> String {
    let escaped = value.replace('\\', "\\\\").replace('"', "\\\"");
    let new_line = format!("{key} = \"{escaped}\"");
    let mut out = String::with_capacity(existing.len() + new_line.len() + 1);
    let mut replaced = false;
    let key_eq_prefix = format!("{key} =");
    let key_eq_compact = format!("{key}=");
    for line in existing.lines() {
        let trimmed = line.trim_start();
        if !replaced
            && (trimmed.starts_with(&key_eq_prefix) || trimmed.starts_with(&key_eq_compact))
        {
            out.push_str(&new_line);
            replaced = true;
        } else {
            out.push_str(line);
        }
        out.push('\n');
    }
    if !replaced {
        if !out.is_empty() && !out.ends_with('\n') {
            out.push('\n');
        }
        out.push_str(&new_line);
        out.push('\n');
    }
    out
}

fn ensure_settings_file() -> std::io::Result<PathBuf> {
    let config_dir = WokConfig::config_dir();
    std::fs::create_dir_all(&config_dir)?;
    let path = config_dir.join("config.toml");
    if !path.exists() {
        return setup_ops::reset_config_file();
    }
    Ok(path)
}

fn editor_selection_range(editor: &InputEditor) -> Option<(usize, usize)> {
    let cursor = editor.buffer.cursors().first()?;
    let anchor = cursor.anchor?;
    if anchor == cursor.position {
        return None;
    }
    Some((anchor.min(cursor.position), anchor.max(cursor.position)))
}

fn selected_editor_text(editor: &InputEditor) -> Option<String> {
    let (start, end) = editor_selection_range(editor)?;
    Some(
        editor
            .buffer
            .text()
            .chars()
            .skip(start)
            .take(end - start)
            .collect(),
    )
}

fn delete_editor_selection(editor: &mut InputEditor) -> bool {
    let Some((start, end)) = editor_selection_range(editor) else {
        return false;
    };
    if editor.buffer.delete_range(start, end).is_err() {
        return false;
    }
    if let Some(cursor) = editor.buffer.cursors_mut().first_mut() {
        cursor.position = start;
        cursor.anchor = None;
    }
    true
}

fn replace_editor_selection(editor: &mut InputEditor, replacement: &str) {
    let _ = delete_editor_selection(editor);
    let _ = editor.buffer.insert_at(0, replacement);
}

fn text_offset_for_line_col(text: &str, target_row: usize, target_col: usize) -> usize {
    let mut offset = 0usize;
    for (row, line) in text.lines().enumerate() {
        if row == target_row {
            return offset + target_col.min(line.chars().count());
        }
        offset += line.chars().count() + 1;
    }
    text.chars().count()
}

fn current_time_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
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
            if let Some(message) = trimmed.strip_prefix("system_notify:") {
                return Some(TriggerAction::SystemNotify {
                    title: String::new(),
                    message: message.trim().to_string(),
                });
            }
            if let Some(message) = trimmed.strip_prefix("desktop_notify:") {
                return Some(TriggerAction::SystemNotify {
                    title: String::new(),
                    message: message.trim().to_string(),
                });
            }
            if lower == "system_notify" || lower == "desktop_notify" {
                return Some(TriggerAction::SystemNotify {
                    title: String::new(),
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

fn build_block_diff_for_target(
    pane: &PaneRuntime,
    target_block_id: u64,
) -> Option<(u64, Vec<DiffLineEntry>)> {
    let blocks = &pane.app.block_manager.blocks;
    let target_index = blocks
        .iter()
        .position(|block| block.id == target_block_id)?;
    let target = blocks.get(target_index)?;
    target.exit_code?;
    let command = target.command_text.trim();
    if command.is_empty() {
        return None;
    }

    let baseline = blocks[..target_index]
        .iter()
        .rev()
        .find(|block| block.exit_code.is_some() && block.command_text.trim() == command)?;

    let baseline_output = collect_block_output_lines(&pane.terminal, baseline);
    let target_output = collect_block_output_lines(&pane.terminal, target);
    Some((
        baseline.id,
        diff_line_entries(&baseline_output, &target_output, 2),
    ))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum DiffOpKind {
    Equal,
    Add,
    Remove,
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct DiffOp {
    kind: DiffOpKind,
    text: String,
    old_line: usize,
    new_line: usize,
}

fn diff_line_entries(
    previous: &[String],
    current: &[String],
    context_lines: usize,
) -> Vec<DiffLineEntry> {
    let (previous, previous_skipped) = trim_diff_input(previous);
    let (current, current_skipped) = trim_diff_input(current);
    let mut entries = if previous_skipped > 0 || current_skipped > 0 {
        vec![DiffLineEntry {
            kind: DiffLineKind::HunkHeader,
            text: format!(
                "@@ ... trimmed {previous_skipped} earlier baseline lines and {current_skipped} earlier target lines ... @@"
            ),
        }]
    } else {
        Vec::new()
    };

    entries.extend(diff_line_entries_with_offsets(
        previous,
        current,
        context_lines,
        previous_skipped,
        current_skipped,
    ));
    if entries.len() > MAX_DIFF_ENTRIES {
        entries.truncate(MAX_DIFF_ENTRIES);
        entries.push(DiffLineEntry {
            kind: DiffLineKind::HunkHeader,
            text: format!("@@ ... diff output truncated to {MAX_DIFF_ENTRIES} lines ... @@"),
        });
    }
    entries
}

fn diff_line_entries_with_offsets(
    previous: &[String],
    current: &[String],
    context_lines: usize,
    old_line_offset: usize,
    new_line_offset: usize,
) -> Vec<DiffLineEntry> {
    let operations = diff_line_operations(previous, current, old_line_offset, new_line_offset);
    let changed_indices = operations
        .iter()
        .enumerate()
        .filter(|(_, operation)| !matches!(operation.kind, DiffOpKind::Equal))
        .map(|(index, _)| index)
        .collect::<Vec<_>>();
    if changed_indices.is_empty() {
        return Vec::new();
    }

    let mut changed_ranges = Vec::<(usize, usize)>::new();
    let mut range_start = changed_indices[0];
    let mut range_end = changed_indices[0];
    for index in changed_indices.into_iter().skip(1) {
        if index == range_end + 1 {
            range_end = index;
            continue;
        }
        changed_ranges.push((range_start, range_end));
        range_start = index;
        range_end = index;
    }
    changed_ranges.push((range_start, range_end));

    let max_index = operations.len().saturating_sub(1);
    let mut expanded = changed_ranges
        .into_iter()
        .map(|(start, end)| {
            (
                start.saturating_sub(context_lines),
                end.saturating_add(context_lines).min(max_index),
            )
        })
        .collect::<Vec<_>>();

    let mut merged = Vec::<(usize, usize)>::new();
    for range in expanded.drain(..) {
        if let Some(last) = merged.last_mut() {
            if range.0 <= last.1 + 1 {
                last.1 = last.1.max(range.1);
                continue;
            }
        }
        merged.push(range);
    }

    let mut entries = Vec::new();
    for (start, end) in merged {
        let old_start = first_old_line_in_range(&operations, start, end)
            .unwrap_or_else(|| previous.len().saturating_add(1));
        let new_start = first_new_line_in_range(&operations, start, end)
            .unwrap_or_else(|| current.len().saturating_add(1));
        let old_count = operations[start..=end]
            .iter()
            .filter(|operation| !matches!(operation.kind, DiffOpKind::Add))
            .count();
        let new_count = operations[start..=end]
            .iter()
            .filter(|operation| !matches!(operation.kind, DiffOpKind::Remove))
            .count();

        entries.push(DiffLineEntry {
            kind: DiffLineKind::HunkHeader,
            text: format!("@@ -{old_start},{old_count} +{new_start},{new_count} @@"),
        });

        for operation in &operations[start..=end] {
            let kind = match operation.kind {
                DiffOpKind::Equal => DiffLineKind::Context,
                DiffOpKind::Add => DiffLineKind::Added,
                DiffOpKind::Remove => DiffLineKind::Removed,
            };
            entries.push(DiffLineEntry {
                kind,
                text: operation.text.clone(),
            });
        }
    }

    entries
}

fn diff_line_counts(previous: &[String], current: &[String]) -> (usize, usize) {
    let (previous, previous_skipped) = trim_diff_input(previous);
    let (current, current_skipped) = trim_diff_input(current);
    diff_line_entries_with_offsets(previous, current, 0, previous_skipped, current_skipped)
        .into_iter()
        .fold((0usize, 0usize), |(added, removed), entry| {
            match entry.kind {
                DiffLineKind::Added => (added + 1, removed),
                DiffLineKind::Removed => (added, removed + 1),
                DiffLineKind::Context | DiffLineKind::HunkHeader => (added, removed),
            }
        })
}

fn trim_diff_input(lines: &[String]) -> (&[String], usize) {
    if lines.len() > MAX_DIFF_INPUT_LINES {
        let skipped = lines.len().saturating_sub(MAX_DIFF_INPUT_LINES);
        (&lines[skipped..], skipped)
    } else {
        (lines, 0)
    }
}

fn diff_line_operations(
    previous: &[String],
    current: &[String],
    old_line_offset: usize,
    new_line_offset: usize,
) -> Vec<DiffOp> {
    let previous_len = previous.len();
    let current_len = current.len();
    let mut lcs = vec![0usize; (previous_len + 1) * (current_len + 1)];
    let index = |i: usize, j: usize| i * (current_len + 1) + j;

    for i in (0..previous_len).rev() {
        for j in (0..current_len).rev() {
            lcs[index(i, j)] = if previous[i] == current[j] {
                lcs[index(i + 1, j + 1)] + 1
            } else {
                lcs[index(i + 1, j)].max(lcs[index(i, j + 1)])
            };
        }
    }

    let mut operations = Vec::new();
    let mut i = 0usize;
    let mut j = 0usize;
    let mut old_line = old_line_offset.saturating_add(1);
    let mut new_line = new_line_offset.saturating_add(1);

    while i < previous_len && j < current_len {
        if previous[i] == current[j] {
            operations.push(DiffOp {
                kind: DiffOpKind::Equal,
                text: previous[i].clone(),
                old_line,
                new_line,
            });
            i += 1;
            j += 1;
            old_line += 1;
            new_line += 1;
            continue;
        }

        if lcs[index(i + 1, j)] >= lcs[index(i, j + 1)] {
            operations.push(DiffOp {
                kind: DiffOpKind::Remove,
                text: previous[i].clone(),
                old_line,
                new_line: 0,
            });
            i += 1;
            old_line += 1;
        } else {
            operations.push(DiffOp {
                kind: DiffOpKind::Add,
                text: current[j].clone(),
                old_line: 0,
                new_line,
            });
            j += 1;
            new_line += 1;
        }
    }

    while i < previous_len {
        operations.push(DiffOp {
            kind: DiffOpKind::Remove,
            text: previous[i].clone(),
            old_line,
            new_line: 0,
        });
        i += 1;
        old_line += 1;
    }

    while j < current_len {
        operations.push(DiffOp {
            kind: DiffOpKind::Add,
            text: current[j].clone(),
            old_line: 0,
            new_line,
        });
        j += 1;
        new_line += 1;
    }

    operations
}

fn first_old_line_in_range(operations: &[DiffOp], start: usize, end: usize) -> Option<usize> {
    operations[start..=end]
        .iter()
        .find_map(|operation| (operation.old_line > 0).then_some(operation.old_line))
}

fn first_new_line_in_range(operations: &[DiffOp], start: usize, end: usize) -> Option<usize> {
    operations[start..=end]
        .iter()
        .find_map(|operation| (operation.new_line > 0).then_some(operation.new_line))
}

fn summarize_failures(entries: &[HistoryEntry], limit: usize) -> Vec<FailureSummaryEntry> {
    let mut grouped = HashMap::<String, FailureSummaryEntry>::new();
    for entry in entries {
        let exit_code = entry.exit_code.unwrap_or(0);
        if exit_code == 0 {
            continue;
        }
        let command = entry.command.trim();
        if command.is_empty() {
            continue;
        }
        let timestamp = entry.completed_at_ms.unwrap_or(entry.started_at_ms);
        grouped
            .entry(command.to_string())
            .and_modify(|summary| {
                summary.count += 1;
                if timestamp >= summary.last_completed_at_ms {
                    summary.last_completed_at_ms = timestamp;
                    summary.last_exit_code = exit_code;
                }
            })
            .or_insert(FailureSummaryEntry {
                command: command.to_string(),
                count: 1,
                last_exit_code: exit_code,
                last_completed_at_ms: timestamp,
            });
    }

    let mut summaries = grouped.into_values().collect::<Vec<_>>();
    summaries.sort_by(|left, right| {
        right
            .count
            .cmp(&left.count)
            .then(right.last_completed_at_ms.cmp(&left.last_completed_at_ms))
    });
    summaries.truncate(limit);
    summaries
}

fn summarize_failure_trends(
    entries: &[HistoryEntry],
    blocks: &[Block],
    bucket_ms: u64,
    limit: usize,
) -> Vec<FailureTrendEntry> {
    let bucket_ms = bucket_ms.max(60_000);
    let mut branch_by_command_cwd = HashMap::<(String, String), String>::new();
    for block in blocks.iter().rev() {
        if block.exit_code.is_none() {
            continue;
        }
        let command = block.command_text.trim();
        if command.is_empty() {
            continue;
        }
        let cwd = if block.cwd.as_os_str().is_empty() {
            String::new()
        } else {
            block.cwd.display().to_string()
        };
        let branch = block
            .git_branch
            .as_ref()
            .filter(|value| !value.trim().is_empty())
            .cloned()
            .unwrap_or_else(|| "unknown".to_string());
        branch_by_command_cwd
            .entry((command.to_string(), cwd))
            .or_insert(branch);
    }

    let mut grouped = HashMap::<(String, String, String, u64), FailureTrendEntry>::new();
    for entry in entries {
        let exit_code = entry.exit_code.unwrap_or(0);
        if exit_code == 0 {
            continue;
        }
        let command = entry.command.trim();
        if command.is_empty() {
            continue;
        }
        let cwd = entry
            .cwd
            .as_ref()
            .map(|path| path.display().to_string())
            .unwrap_or_default();
        let branch = branch_by_command_cwd
            .get(&(command.to_string(), cwd.clone()))
            .cloned()
            .unwrap_or_else(|| "unknown".to_string());
        let timestamp = entry.completed_at_ms.unwrap_or(entry.started_at_ms);
        let bucket_start_ms = timestamp.saturating_sub(timestamp % bucket_ms);

        grouped
            .entry((
                command.to_string(),
                cwd.clone(),
                branch.clone(),
                bucket_start_ms,
            ))
            .and_modify(|trend| {
                trend.count += 1;
                if timestamp >= trend.last_completed_at_ms {
                    trend.last_completed_at_ms = timestamp;
                    trend.last_exit_code = exit_code;
                }
            })
            .or_insert(FailureTrendEntry {
                command: command.to_string(),
                cwd,
                branch,
                bucket_start_ms,
                count: 1,
                last_exit_code: exit_code,
                last_completed_at_ms: timestamp,
            });
    }

    let mut trends = grouped.into_values().collect::<Vec<_>>();
    trends.sort_by(|left, right| {
        right
            .bucket_start_ms
            .cmp(&left.bucket_start_ms)
            .then(right.count.cmp(&left.count))
            .then(right.last_completed_at_ms.cmp(&left.last_completed_at_ms))
            .then(left.command.cmp(&right.command))
            .then(left.cwd.cmp(&right.cwd))
            .then(left.branch.cmp(&right.branch))
    });
    trends.truncate(limit);
    trends
}

fn format_bucket_label(bucket_start_ms: u64) -> String {
    let total_minutes = (bucket_start_ms / 1000) / 60;
    let minute = total_minutes % 60;
    let hour = (total_minutes / 60) % 24;
    format!("{hour:02}:{minute:02}")
}

fn failure_trend_panel_lines(
    entries: &[HistoryEntry],
    blocks: &[Block],
    bucket_ms: u64,
    limit: usize,
) -> Vec<String> {
    summarize_failure_trends(entries, blocks, bucket_ms, limit)
        .into_iter()
        .map(|entry| {
            let bucket = format_bucket_label(entry.bucket_start_ms);
            let branch = if entry.branch.trim().is_empty() {
                "unknown".to_string()
            } else {
                entry.branch
            };
            let cwd = if entry.cwd.trim().is_empty() {
                "unknown".to_string()
            } else {
                entry.cwd
            };
            format!(
                "{}x [{}] {} · {} · {}",
                entry.count, bucket, entry.command, cwd, branch
            )
        })
        .collect()
}

fn workspace_insight_panel_lines(
    entries: &[HistoryEntry],
    blocks: &[Block],
    limit: usize,
) -> Vec<String> {
    let commands = entries
        .iter()
        .filter(|entry| !entry.command.trim().is_empty())
        .collect::<Vec<_>>();
    if commands.is_empty() {
        return vec!["No command history for this pane yet".to_string()];
    }

    let total = commands.len();
    let failures = commands
        .iter()
        .filter(|entry| entry.exit_code.unwrap_or(0) != 0)
        .count();
    let failure_rate = (failures as f64 / total as f64) * 100.0;

    let durations = commands
        .iter()
        .filter_map(|entry| entry.duration_ms)
        .collect::<Vec<_>>();
    let avg_duration = if durations.is_empty() {
        "unknown".to_string()
    } else {
        format!(
            "{}ms",
            durations.iter().sum::<u64>() / durations.len() as u64
        )
    };

    let mut by_command_count = HashMap::<String, usize>::new();
    let mut by_command_duration = HashMap::<String, (u64, usize)>::new();
    for entry in &commands {
        let command = entry.command.trim();
        if command.is_empty() {
            continue;
        }
        *by_command_count.entry(command.to_string()).or_insert(0) += 1;
        if let Some(duration_ms) = entry.duration_ms {
            let bucket = by_command_duration
                .entry(command.to_string())
                .or_insert((0, 0));
            bucket.0 += duration_ms;
            bucket.1 += 1;
        }
    }

    let mut repeated = by_command_count.into_iter().collect::<Vec<_>>();
    repeated.sort_by(|left, right| right.1.cmp(&left.1).then(left.0.cmp(&right.0)));
    let repeated = repeated
        .into_iter()
        .take(3)
        .map(|(command, count)| format!("{command} ({count})"))
        .collect::<Vec<_>>()
        .join(", ");

    let mut slowest = by_command_duration
        .into_iter()
        .filter_map(|(command, (sum, count))| (count > 0).then(|| (command, sum / count as u64)))
        .collect::<Vec<_>>();
    slowest.sort_by(|left, right| right.1.cmp(&left.1).then(left.0.cmp(&right.0)));
    let slowest = slowest
        .into_iter()
        .take(3)
        .map(|(command, avg)| format!("{command} ({avg}ms)"))
        .collect::<Vec<_>>()
        .join(", ");

    let block_count = blocks.len();
    let bookmarked = blocks.iter().filter(|block| block.is_bookmarked).count();
    let open_blocks = blocks
        .iter()
        .filter(|block| block.exit_code.is_none())
        .count();
    let failure_summary = summarize_failures(entries, limit)
        .into_iter()
        .take(3)
        .map(|entry| format!("{} ({})", entry.command, entry.count))
        .collect::<Vec<_>>()
        .join(", ");

    vec![
        format!(
            "Commands: {total} | Failures: {failures} ({failure_rate:.1}%) | Avg duration: {avg_duration}"
        ),
        format!("Blocks: {block_count} | Running: {open_blocks} | Bookmarked: {bookmarked}"),
        if repeated.is_empty() {
            "Most repeated: n/a".to_string()
        } else {
            format!("Most repeated: {repeated}")
        },
        if slowest.is_empty() {
            "Slowest avg commands: n/a".to_string()
        } else {
            format!("Slowest avg commands: {slowest}")
        },
        if failure_summary.is_empty() {
            "Failure hot spots: n/a".to_string()
        } else {
            format!("Failure hot spots: {failure_summary}")
        },
    ]
}

fn workflow_name_from_command(command: &str) -> String {
    let slug = command
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() {
                ch.to_ascii_lowercase()
            } else {
                '_'
            }
        })
        .collect::<String>();
    let slug = slug
        .trim_matches('_')
        .split('_')
        .filter(|segment| !segment.is_empty())
        .take(4)
        .collect::<Vec<_>>()
        .join("_");
    let slug = if slug.is_empty() {
        "workflow".to_string()
    } else {
        slug
    };
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_or(0, |duration| duration.as_secs());
    format!("{slug}_{stamp}")
}

fn persist_workflow_template(workflow: &Workflow) -> Result<PathBuf, Box<dyn Error>> {
    let workflows_dir = WokConfig::config_dir().join("workflows");
    std::fs::create_dir_all(&workflows_dir)?;
    let path = workflows_dir.join(format!("{}.toml", workflow.name));
    let payload = toml::to_string_pretty(workflow)?;
    std::fs::write(&path, payload)?;
    Ok(path)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BlockExportFormat {
    Markdown,
    Json,
}

impl BlockExportFormat {
    fn label(self) -> &'static str {
        match self {
            Self::Markdown => "markdown",
            Self::Json => "json",
        }
    }

    fn extension(self) -> &'static str {
        match self {
            Self::Markdown => "md",
            Self::Json => "json",
        }
    }
}

#[derive(Debug, Clone, Serialize)]
struct BlockExportBundle {
    generated_at_unix_ms: u64,
    pane_id: PaneId,
    block_id: u64,
    command: String,
    cwd: Option<String>,
    git_branch: Option<String>,
    exit_code: Option<i32>,
    duration_ms: Option<u64>,
    output_start_row: usize,
    output_end_row: usize,
    output_lines: Vec<String>,
}

impl BlockExportBundle {
    fn to_markdown(&self) -> String {
        let cwd = self.cwd.as_deref().unwrap_or("unknown");
        let branch = self.git_branch.as_deref().unwrap_or("unknown");
        let exit = self
            .exit_code
            .map_or_else(|| "unknown".to_string(), |code| code.to_string());
        let duration = self
            .duration_ms
            .map_or_else(|| "unknown".to_string(), |ms| format!("{ms}ms"));
        // strip ANSI escapes so the fenced ```text block stays readable.
        let output = self
            .output_lines
            .iter()
            .map(|line| wok_blocks::share::strip_csi(line))
            .collect::<Vec<_>>()
            .join("\n");
        format!(
            "# Wok Block Export\n\n\
             - Generated At (unix ms): `{}`\n\
             - Pane ID: `{}`\n\
             - Block ID: `{}`\n\
             - CWD: `{}`\n\
             - Branch: `{}`\n\
             - Exit Code: `{}`\n\
             - Duration: `{}`\n\
             - Output Rows: `{}..={}`\n\n\
             ## Command\n\n\
             ```bash\n{}\n```\n\n\
             ## Output\n\n\
             ```text\n{}\n```\n",
            self.generated_at_unix_ms,
            self.pane_id,
            self.block_id,
            cwd,
            branch,
            exit,
            duration,
            self.output_start_row,
            self.output_end_row,
            self.command,
            output,
        )
    }
}

fn persist_block_export(
    bundle: &BlockExportBundle,
    payload: &str,
    format: BlockExportFormat,
) -> Result<PathBuf, Box<dyn Error>> {
    let exports_dir = WokConfig::config_dir().join("exports");
    std::fs::create_dir_all(&exports_dir)?;
    let path = exports_dir.join(format!(
        "block-{}-{}.{}",
        bundle.block_id,
        bundle.generated_at_unix_ms,
        format.extension()
    ));
    std::fs::write(&path, payload)?;
    Ok(path)
}

fn remote_rpc_methods() -> &'static [&'static str] {
    &[
        "wok.get_rpc_info",
        "wok.get_panes",
        "wok.send_text",
        "wok.run_action",
        "wok.get_blocks",
        "wok.get_text",
        "wok.get_git_status",
        "wok.get_git_diff",
        "wok.git.stage",
        "wok.git.unstage",
        "wok.git.discard",
        "wok.create_pane",
        "wok.close_pane",
        "wok.set_theme",
        "wok.notify",
        "wok.get_failure_summary",
        "wok.get_failure_trends",
        "wok.setup.init",
        "wok.setup.doctor",
        "wok.setup.reset",
        "wok.setup.shell_install",
        "wok.setup.shell_rollback",
    ]
}

fn parse_reset_scope_value(value: &str) -> Option<setup_ops::ResetScope> {
    match value.trim().to_ascii_lowercase().as_str() {
        "managed" => Some(setup_ops::ResetScope::Managed),
        "state" => Some(setup_ops::ResetScope::State),
        "all" => Some(setup_ops::ResetScope::All),
        _ => None,
    }
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
        Action::BlockPrevFailed => "block_prev_failed".to_string(),
        Action::BlockNextFailed => "block_next_failed".to_string(),
        Action::BlockFind => "block_find".to_string(),
        Action::BlockFilter => "block_filter".to_string(),
        Action::BlockDiff => "block_diff".to_string(),
        Action::BlockRerun => "block_rerun".to_string(),
        Action::BlockRerunInSplit => "block_rerun_in_split".to_string(),
        Action::BlockSaveWorkflow => "block_save_workflow".to_string(),
        Action::BlockExportMarkdown => "block_export_markdown".to_string(),
        Action::BlockExportJson => "block_export_json".to_string(),
        Action::ToggleFailureTrendsPanel => "toggle_failure_trends_panel".to_string(),
        Action::ToggleWorkspaceInsightsPanel => "toggle_workspace_insights_panel".to_string(),
        Action::SearchGlobal => "search_global".to_string(),
        Action::EnterViMode => "enter_vi_mode".to_string(),
        Action::CommandPalette => "command_palette".to_string(),
        Action::CommandSearch => "command_search".to_string(),
        Action::QuickSelect => "quick_select".to_string(),
        Action::QuickSelectBlock => "quick_select_block".to_string(),
        Action::ToggleBroadcast => "toggle_broadcast".to_string(),
        Action::ToggleTypewriterEffect => "toggle_typewriter_effect".to_string(),
        Action::CycleVisualEffect => "cycle_visual_effect".to_string(),
        Action::CloseMediaPreview => "close_media_preview".to_string(),
        Action::ToggleMediaPreviewPlayback => "toggle_media_preview_playback".to_string(),
        Action::SeekMediaPreviewBackward => "seek_media_preview_backward".to_string(),
        Action::SeekMediaPreviewForward => "seek_media_preview_forward".to_string(),
        Action::SlowMediaPreviewPlayback => "slow_media_preview_playback".to_string(),
        Action::FastMediaPreviewPlayback => "fast_media_preview_playback".to_string(),
        Action::StepMediaPreviewBackward => "step_media_preview_backward".to_string(),
        Action::StepMediaPreviewForward => "step_media_preview_forward".to_string(),
        Action::ToggleMediaPreviewMute => "toggle_media_preview_mute".to_string(),
        Action::PreviewPathUnderCursor => "preview_path_under_cursor".to_string(),
        Action::OpenPathUnderCursor => "open_path_under_cursor".to_string(),
        Action::CopyPathUnderCursor => "copy_path_under_cursor".to_string(),
        Action::RevealPathUnderCursor => "reveal_path_under_cursor".to_string(),
        Action::TailPathUnderCursor => "tail_path_under_cursor".to_string(),
        Action::OpenScratchBuffer => "open_scratch_buffer".to_string(),
        Action::OpenScratchPalette => "open_scratch_palette".to_string(),
        Action::ToggleSearchRegex => "toggle_search_regex".to_string(),
        Action::CycleSearchScope => "cycle_search_scope".to_string(),
        Action::OpenSearchResults => "open_search_results".to_string(),
        Action::SaveCurrentSearch => "save_current_search".to_string(),
        Action::OpenSavedSearches => "open_saved_searches".to_string(),
        Action::OpenBlockInspector => "open_block_inspector".to_string(),
        Action::OpenBlockRerunHistory => "open_block_rerun_history".to_string(),
        Action::OpenBlockRerunComparison => "open_block_rerun_comparison".to_string(),
        Action::InsertScratchSelectionIntoInput => {
            "insert_scratch_selection_into_input".to_string()
        }
        Action::SendScratchSelectionToPane => "send_scratch_selection_to_pane".to_string(),
        Action::OpenWorkspaceBrowser => "open_workspace_browser".to_string(),
        Action::NewFloatingPane => "new_floating_pane".to_string(),
        Action::ToggleFloatingPane => "toggle_floating_pane".to_string(),
        Action::CloseFloatingPane => "close_floating_pane".to_string(),
        Action::NextLayout => "next_layout".to_string(),
        Action::PrevLayout => "prev_layout".to_string(),
        Action::ToggleInputPosition => "toggle_input_position".to_string(),
        Action::ZoomIn => "zoom_in".to_string(),
        Action::ZoomOut => "zoom_out".to_string(),
        Action::ZoomReset => "zoom_reset".to_string(),
        Action::OpenSettings => "open_settings".to_string(),
        Action::ResetSettings => "reset_settings".to_string(),
        Action::ClearScreen => "clear_screen".to_string(),
        Action::SendEof => "send_eof".to_string(),
        Action::SaveSession(name) => format!("save_session:{name}"),
        Action::LoadSession(name) => format!("load_session:{name}"),
        Action::ThemePicker => "theme_picker".to_string(),
        Action::KeybindingDiscovery => "keybinding_discovery".to_string(),
        Action::KeybindingEditor => "keybinding_editor".to_string(),
        Action::SettingsDiscovery => "settings_discovery".to_string(),
        Action::GitChanges => "git_changes".to_string(),
        Action::GitWorktrees => "git_worktrees".to_string(),
    };
    Some(id)
}

fn action_display_label(action: &Action) -> String {
    match action {
        Action::SwitchToTab(index) => format!("Switch To Tab {index}"),
        Action::SaveSession(name) => format!("Save Session ({name})"),
        Action::LoadSession(name) => format!("Load Session ({name})"),
        Action::GitChanges => "Git Changes".to_string(),
        Action::GitWorktrees => "Git Worktrees".to_string(),
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

fn palette_actions_catalog() -> Vec<Action> {
    let mut actions = vec![
        Action::CommandPalette,
        Action::CommandSearch,
        Action::SearchGlobal,
        Action::QuickSelect,
        Action::QuickSelectBlock,
        Action::EnterViMode,
        Action::BlockFind,
        Action::BlockFilter,
        Action::BlockDiff,
        Action::BlockRerun,
        Action::BlockRerunInSplit,
        Action::BlockSaveWorkflow,
        Action::BlockExportMarkdown,
        Action::BlockExportJson,
        Action::ToggleFailureTrendsPanel,
        Action::ToggleWorkspaceInsightsPanel,
        Action::GitChanges,
        Action::GitWorktrees,
        Action::BlockPrevFailed,
        Action::BlockNextFailed,
        Action::BlockPrev,
        Action::BlockNext,
        Action::BlockToggleBookmark,
        Action::BlockPrevBookmark,
        Action::BlockNextBookmark,
        Action::BlockCopy,
        Action::BlockCopyCommand,
        Action::BlockCopyOutput,
        Action::BlockCollapse,
        Action::ToggleBroadcast,
        Action::ToggleTypewriterEffect,
        Action::CycleVisualEffect,
        Action::CloseMediaPreview,
        Action::ToggleMediaPreviewPlayback,
        Action::SeekMediaPreviewBackward,
        Action::SeekMediaPreviewForward,
        Action::SlowMediaPreviewPlayback,
        Action::FastMediaPreviewPlayback,
        Action::StepMediaPreviewBackward,
        Action::StepMediaPreviewForward,
        Action::ToggleMediaPreviewMute,
        Action::PreviewPathUnderCursor,
        Action::OpenPathUnderCursor,
        Action::CopyPathUnderCursor,
        Action::RevealPathUnderCursor,
        Action::TailPathUnderCursor,
        Action::OpenScratchBuffer,
        Action::OpenScratchPalette,
        Action::InsertScratchSelectionIntoInput,
        Action::SendScratchSelectionToPane,
        Action::ToggleSearchRegex,
        Action::CycleSearchScope,
        Action::OpenSearchResults,
        Action::SaveCurrentSearch,
        Action::OpenSavedSearches,
        Action::OpenBlockInspector,
        Action::OpenBlockRerunHistory,
        Action::OpenBlockRerunComparison,
        Action::OpenWorkspaceBrowser,
        Action::SplitVertical,
        Action::SplitHorizontal,
        Action::CloseSplit,
        Action::FocusLeft,
        Action::FocusRight,
        Action::FocusUp,
        Action::FocusDown,
        Action::ResizeSplitLeft,
        Action::ResizeSplitRight,
        Action::ResizeSplitUp,
        Action::ResizeSplitDown,
        Action::NewFloatingPane,
        Action::ToggleFloatingPane,
        Action::CloseFloatingPane,
        Action::NewTab,
        Action::CloseTab,
        Action::NextTab,
        Action::PrevTab,
        Action::NextLayout,
        Action::PrevLayout,
        Action::ToggleInputPosition,
        Action::ScrollUp,
        Action::ScrollDown,
        Action::ScrollPageUp,
        Action::ScrollPageDown,
        Action::ScrollToTop,
        Action::ScrollToBottom,
        Action::ZoomIn,
        Action::ZoomOut,
        Action::ZoomReset,
        Action::OpenSettings,
        Action::ResetSettings,
        Action::ThemePicker,
        Action::KeybindingDiscovery,
        Action::KeybindingEditor,
        Action::SettingsDiscovery,
        Action::ClearScreen,
        Action::SendEof,
        Action::Copy,
        Action::Paste,
        Action::SelectAll,
    ];
    actions.extend((1..=9).map(Action::SwitchToTab));
    actions
}

fn action_palette_description(action: &Action, keybinding: &str) -> String {
    let summary = match action {
        Action::NewTab => "Create a new tab",
        Action::CloseTab => "Close the active tab",
        Action::NextTab => "Move focus to the next tab",
        Action::PrevTab => "Move focus to the previous tab",
        Action::SwitchToTab(_) => "Jump directly to a numbered tab",
        Action::SplitVertical => "Split the active pane vertically",
        Action::SplitHorizontal => "Split the active pane horizontally",
        Action::CloseSplit => "Close the active split pane",
        Action::FocusLeft => "Move focus to the pane on the left",
        Action::FocusRight => "Move focus to the pane on the right",
        Action::FocusUp => "Move focus to the pane above",
        Action::FocusDown => "Move focus to the pane below",
        Action::ResizeSplitLeft => "Grow the active pane to the left",
        Action::ResizeSplitRight => "Grow the active pane to the right",
        Action::ResizeSplitUp => "Grow the active pane upward",
        Action::ResizeSplitDown => "Grow the active pane downward",
        Action::Copy => "Copy selection to the clipboard",
        Action::Paste => "Paste clipboard contents",
        Action::SelectAll => "Select all visible terminal text",
        Action::ScrollUp => "Scroll terminal view up",
        Action::ScrollDown => "Scroll terminal view down",
        Action::ScrollPageUp => "Scroll up by one page",
        Action::ScrollPageDown => "Scroll down by one page",
        Action::ScrollToTop => "Jump to the top of scrollback",
        Action::ScrollToBottom => "Jump to the live prompt",
        Action::BlockPrev => "Select the previous command block",
        Action::BlockNext => "Select the next command block",
        Action::BlockCopy => "Copy command and output for the selected block",
        Action::BlockCopyCommand => "Copy only the command text of the selected block",
        Action::BlockCopyOutput => "Copy only output text of the selected block",
        Action::BlockCollapse => "Collapse or expand selected block output",
        Action::BlockToggleBookmark => "Toggle a bookmark on the selected block",
        Action::BlockPrevBookmark => "Jump to the previous bookmarked block",
        Action::BlockNextBookmark => "Jump to the next bookmarked block",
        Action::BlockPrevFailed => "Jump to the previous failed command block",
        Action::BlockNextFailed => "Jump to the next failed command block",
        Action::BlockFind => "Search within selected block output",
        Action::BlockFilter => "Filter selected block output by query",
        Action::BlockDiff => "Compare selected block output with prior runs",
        Action::BlockRerun => "Re-run the selected block command",
        Action::BlockRerunInSplit => "Re-run the selected block command in a new split pane",
        Action::BlockSaveWorkflow => "Save selected block command as a reusable workflow",
        Action::BlockExportMarkdown => "Export selected block metadata and output as Markdown",
        Action::BlockExportJson => "Export selected block metadata and output as JSON",
        Action::ToggleFailureTrendsPanel => "Open failure trends analytics panel",
        Action::ToggleWorkspaceInsightsPanel => "Open workspace command insights panel",
        Action::SearchGlobal => "Search text across the workspace",
        Action::EnterViMode => "Enable vi-style navigation mode",
        Action::CommandPalette => "Open action/workflow palette (`>` filters actions)",
        Action::CommandSearch => "Search pane and global command history",
        Action::QuickSelect => "Start quick-select labels for visible output",
        Action::QuickSelectBlock => "Start quick-select labels for selected block",
        Action::ToggleBroadcast => "Toggle input broadcast across panes",
        Action::ToggleTypewriterEffect => "Toggle character-by-character output reveal",
        Action::CycleVisualEffect => "Cycle rainbow, wavy, glitch, CRT, bloom, and cookie effects",
        Action::CloseMediaPreview => "Close the built-in image, GIF, or MP4 preview",
        Action::ToggleMediaPreviewPlayback => "Play or pause the built-in GIF or MP4 preview",
        Action::SeekMediaPreviewBackward => "Seek the MP4 preview backward by five seconds",
        Action::SeekMediaPreviewForward => "Seek the MP4 preview forward by five seconds",
        Action::SlowMediaPreviewPlayback => "Slow down MP4 preview playback",
        Action::FastMediaPreviewPlayback => "Speed up MP4 preview playback",
        Action::StepMediaPreviewBackward => "Step MP4 preview backward by one frame",
        Action::StepMediaPreviewForward => "Step MP4 preview forward by one frame",
        Action::ToggleMediaPreviewMute => "Mute or unmute the MP4 preview",
        Action::PreviewPathUnderCursor => "Preview the file path under the cursor",
        Action::OpenPathUnderCursor => "Open the file path under the cursor externally",
        Action::CopyPathUnderCursor => "Copy the file path under the cursor",
        Action::RevealPathUnderCursor => "Reveal the file path under the cursor in Finder",
        Action::TailPathUnderCursor => "Tail the file path under the cursor in a new split",
        Action::OpenScratchBuffer => "Open a persistent scratch buffer",
        Action::OpenScratchPalette => "Open named scratch buffers",
        Action::InsertScratchSelectionIntoInput => {
            "Insert selected scratch text into command input"
        }
        Action::SendScratchSelectionToPane => "Send selected scratch text directly to the pane",
        Action::ToggleSearchRegex => "Toggle global search regex mode",
        Action::CycleSearchScope => "Cycle search scope across all, pane, commands, and output",
        Action::OpenSearchResults => "Open current search matches as a result list",
        Action::SaveCurrentSearch => "Save the current search query",
        Action::OpenSavedSearches => "Open saved search queries",
        Action::OpenBlockInspector => "Inspect selected command block metadata and output",
        Action::OpenBlockRerunHistory => "Show recorded rerun history for selected command block",
        Action::OpenBlockRerunComparison => "Compare every recorded rerun of the selected command",
        Action::OpenWorkspaceBrowser => "Browse and load named workspace snapshots",
        Action::NewFloatingPane => "Create a floating pane",
        Action::ToggleFloatingPane => "Show or hide floating panes",
        Action::CloseFloatingPane => "Close focused floating pane",
        Action::NextLayout => "Cycle to the next layout preset",
        Action::PrevLayout => "Cycle to the previous layout preset",
        Action::ToggleInputPosition => "Toggle input bar position",
        Action::ZoomIn => "Increase terminal font size",
        Action::ZoomOut => "Decrease terminal font size",
        Action::ZoomReset => "Reset terminal font size",
        Action::OpenSettings => "Open the Wok settings buffer",
        Action::ResetSettings => "Reset the Wok settings file to defaults",
        Action::ClearScreen => "Clear terminal viewport and scrollback",
        Action::SendEof => "Send EOF (Ctrl+D) to the active shell",
        Action::SaveSession(_) => "Persist the current workspace as a named session",
        Action::LoadSession(_) => "Load a previously saved named session",
        Action::ThemePicker => "Pick a theme from ~/.config/wok/themes",
        Action::KeybindingDiscovery => "List all keybindings (read-only)",
        Action::KeybindingEditor => "Edit keybindings and capture new shortcuts",
        Action::SettingsDiscovery => "List every settings field with current value",
        Action::GitChanges => "List changed files in the active Git repository",
        Action::GitWorktrees => "Switch between Git worktrees for the active repository",
    };

    if keybinding.trim().is_empty() {
        format!("{summary}. Shortcut: unbound")
    } else {
        format!("{summary}. Shortcut: {keybinding}")
    }
}

fn build_git_worktree_palette_entries(
    worktrees: Vec<wok_git::service::GitWorktree>,
    current_cwd: &std::path::Path,
) -> Vec<PaletteEntry> {
    let mut entries = worktrees
        .into_iter()
        .map(|worktree| {
            let path = worktree.path.display().to_string();
            PaletteEntry {
                label: git_worktree_label(&worktree),
                description: git_worktree_description(&worktree, current_cwd),
                category: PaletteCategory::GitWorktree,
                score: 0.0,
                action: PaletteAction::ChangeDirectory(path),
            }
        })
        .collect::<Vec<_>>();
    entries.sort_by(|left, right| left.label.cmp(&right.label));
    entries
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum GitPaletteFileAction {
    Stage,
    Unstage,
    Discard,
}

impl GitPaletteFileAction {
    fn verb(self) -> &'static str {
        match self {
            GitPaletteFileAction::Stage => "stage",
            GitPaletteFileAction::Unstage => "unstage",
            GitPaletteFileAction::Discard => "discard",
        }
    }

    fn past_tense(self) -> &'static str {
        match self {
            GitPaletteFileAction::Stage => "Staged",
            GitPaletteFileAction::Unstage => "Unstaged",
            GitPaletteFileAction::Discard => "Discarded",
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
enum GitChangesRefresh {
    Clean,
    Entries(Vec<PaletteEntry>),
}

fn git_changes_palette_entries_from_snapshot(
    snapshot: wok_git::service::GitStatusSnapshot,
) -> Vec<PaletteEntry> {
    snapshot
        .files
        .into_iter()
        .flat_map(git_change_palette_entries_for_file)
        .collect()
}

fn git_changes_refresh_after_action(
    snapshot: wok_git::service::GitStatusSnapshot,
) -> GitChangesRefresh {
    let entries = git_changes_palette_entries_from_snapshot(snapshot);
    if entries.is_empty() {
        GitChangesRefresh::Clean
    } else {
        GitChangesRefresh::Entries(entries)
    }
}

fn git_change_palette_entries_for_file(file: wok_git::status::GitStatusFile) -> Vec<PaletteEntry> {
    let status = file.status_text();
    let description = git_status_file_description(&file);
    let path = file.path.clone();
    let mut entries = vec![PaletteEntry {
        label: format!("Preview {status}  {path}"),
        description: description.clone(),
        category: PaletteCategory::GitFile,
        score: 0.0,
        action: PaletteAction::GitFileDiff(path.clone()),
    }];

    if file.is_unstaged() {
        entries.push(PaletteEntry {
            label: format!("Stage {path}"),
            description: description.clone(),
            category: PaletteCategory::GitFile,
            score: 0.0,
            action: PaletteAction::GitStageFile(path.clone()),
        });
    }
    if file.is_staged() {
        entries.push(PaletteEntry {
            label: format!("Unstage {path}"),
            description: description.clone(),
            category: PaletteCategory::GitFile,
            score: 0.0,
            action: PaletteAction::GitUnstageFile(path.clone()),
        });
    }
    if file.is_staged() || file.is_unstaged() {
        entries.push(PaletteEntry {
            label: format!("Discard {path}"),
            description,
            category: PaletteCategory::GitFile,
            score: 0.0,
            action: PaletteAction::GitDiscardFile(path),
        });
    }

    entries
}

fn git_discard_confirmation_entries(path: &str) -> Vec<PaletteEntry> {
    vec![
        PaletteEntry {
            label: format!("Confirm discard {path}"),
            description: "Deletes unstaged edits or removes an untracked file".to_string(),
            category: PaletteCategory::GitFile,
            score: 0.0,
            action: PaletteAction::GitConfirmDiscardFile(path.to_string()),
        },
        PaletteEntry {
            label: "Cancel".to_string(),
            description: "Return to the terminal without discarding changes".to_string(),
            category: PaletteCategory::GitFile,
            score: 0.0,
            action: PaletteAction::Dismiss,
        },
    ]
}

fn git_worktree_label(worktree: &wok_git::service::GitWorktree) -> String {
    worktree
        .branch
        .clone()
        .or_else(|| {
            worktree
                .head
                .as_ref()
                .map(|head| format!("detached {}", head.chars().take(8).collect::<String>()))
        })
        .unwrap_or_else(|| {
            worktree
                .path
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or("worktree")
                .to_string()
        })
}

fn git_worktree_description(
    worktree: &wok_git::service::GitWorktree,
    current_cwd: &std::path::Path,
) -> String {
    let mut parts = Vec::new();
    if current_cwd.starts_with(&worktree.path) {
        parts.push("current".to_string());
    }
    if worktree.is_bare {
        parts.push("bare".to_string());
    }
    if worktree.is_detached {
        parts.push("detached".to_string());
    }
    parts.push(worktree.path.display().to_string());
    parts.join(" | ")
}

fn visible_file_paths_for_pane(pane: &PaneRuntime) -> Vec<PathBuf> {
    let mut paths = Vec::new();
    let visible = pane.terminal.state.visible_rows();
    for (index, row) in visible.iter().copied().enumerate() {
        let mut line = pane.terminal.state.row_text(row);
        if line.ends_with('\\') || line.ends_with('/') {
            if let Some(next_row) = visible.get(index + 1) {
                line.push_str(pane.terminal.state.row_text(*next_row).trim_start());
            }
        }
        for span in path_like_spans(&line) {
            paths.push(span.target.path);
        }
    }
    paths
}

fn file_action_palette_entries(path: &Path) -> Vec<PaletteEntry> {
    let display = path.display().to_string();
    let name = path
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or(display.as_str());
    let preview_action = if media_kind_for_path(path).is_some() {
        PaletteAction::PreviewMedia(display.clone())
    } else {
        PaletteAction::PreviewPath(display.clone())
    };
    let mut entries = vec![
        PaletteEntry {
            label: format!("Preview {name}"),
            description: format!("Open in built-in preview: {display}"),
            category: PaletteCategory::FilePath,
            score: 0.0,
            action: preview_action,
        },
        PaletteEntry {
            label: format!("Open {name} Externally"),
            description: display.clone(),
            category: PaletteCategory::FilePath,
            score: 0.0,
            action: PaletteAction::OpenPathExternal(display.clone()),
        },
        PaletteEntry {
            label: format!("Copy Path {name}"),
            description: display.clone(),
            category: PaletteCategory::FilePath,
            score: 0.0,
            action: PaletteAction::CopyPath(display.clone()),
        },
        PaletteEntry {
            label: format!("Reveal {name}"),
            description: display.clone(),
            category: PaletteCategory::FilePath,
            score: 0.0,
            action: PaletteAction::RevealPath(display.clone()),
        },
    ];
    if path.is_file() {
        entries.push(PaletteEntry {
            label: format!("Tail {name}"),
            description: display.clone(),
            category: PaletteCategory::FilePath,
            score: 0.0,
            action: PaletteAction::TailPath(display),
        });
    }
    entries
}

fn context_menu_entry_from_palette(entry: PaletteEntry) -> ContextMenuEntry {
    ContextMenuEntry {
        label: entry.label,
        description: truncate_menu_description(&entry.description),
        action: ContextMenuAction::Palette(entry.action),
    }
}

fn context_menu_tab_entries(tab_index: usize) -> Vec<ContextMenuEntry> {
    let display_index = tab_index + 1;
    let mut entries = vec![
        context_menu_builtin(
            &format!("Switch To Tab {display_index}"),
            "focus tab",
            Action::SwitchToTab(display_index.min(u8::MAX as usize) as u8),
        ),
        context_menu_builtin("New Tab", "tab bar", Action::NewTab),
        context_menu_builtin("Close Tab", "focused tab", Action::CloseTab),
        context_menu_builtin("Next Tab", "tab bar", Action::NextTab),
        context_menu_builtin("Previous Tab", "tab bar", Action::PrevTab),
    ];
    entries.extend(context_menu_workspace_entries());
    entries
}

fn context_menu_workspace_entries() -> Vec<ContextMenuEntry> {
    vec![
        context_menu_builtin("Split Right", "new pane", Action::SplitVertical),
        context_menu_builtin("Split Down", "new pane", Action::SplitHorizontal),
        context_menu_builtin("Close Pane", "focused pane", Action::CloseSplit),
        context_menu_builtin("New Floating Pane", "overlay pane", Action::NewFloatingPane),
        context_menu_builtin(
            "Toggle Floating Panes",
            "show / hide",
            Action::ToggleFloatingPane,
        ),
        context_menu_builtin(
            "Close Floating Pane",
            "focused floating",
            Action::CloseFloatingPane,
        ),
        context_menu_builtin("Next Layout", "cycle preset", Action::NextLayout),
        context_menu_builtin("Previous Layout", "cycle preset", Action::PrevLayout),
        context_menu_builtin("Focus Left", "neighbor pane", Action::FocusLeft),
        context_menu_builtin("Focus Right", "neighbor pane", Action::FocusRight),
        context_menu_builtin("Focus Up", "neighbor pane", Action::FocusUp),
        context_menu_builtin("Focus Down", "neighbor pane", Action::FocusDown),
        context_menu_window(
            "Toggle Full Screen",
            "macOS window",
            WindowContextAction::ToggleFullscreen,
        ),
        context_menu_window(
            "Zoom Window",
            "macOS window",
            WindowContextAction::ToggleMaximized,
        ),
        context_menu_window(
            "Minimize Window",
            "macOS window",
            WindowContextAction::Minimize,
        ),
        context_menu_builtin("Command Palette", "all actions", Action::CommandPalette),
        context_menu_builtin("Search Scrollback", "workspace", Action::SearchGlobal),
    ]
}

fn context_menu_builtin(label: &str, description: &str, action: Action) -> ContextMenuEntry {
    ContextMenuEntry {
        label: label.to_string(),
        description: description.to_string(),
        action: ContextMenuAction::BuiltIn(action),
    }
}

fn context_menu_window(
    label: &str,
    description: &str,
    action: WindowContextAction,
) -> ContextMenuEntry {
    ContextMenuEntry {
        label: label.to_string(),
        description: description.to_string(),
        action: ContextMenuAction::Window(action),
    }
}

fn truncate_menu_description(value: &str) -> String {
    const MAX_CHARS: usize = 42;
    let mut chars = value.chars();
    let truncated = chars.by_ref().take(MAX_CHARS).collect::<String>();
    if chars.next().is_some() {
        format!("{truncated}...")
    } else {
        truncated
    }
}

fn point_in_rect(rect: Rect, x: f64, y: f64) -> bool {
    rect.w > 0.0
        && rect.h > 0.0
        && x >= f64::from(rect.x)
        && x <= f64::from(rect.x + rect.w)
        && y >= f64::from(rect.y)
        && y <= f64::from(rect.y + rect.h)
}

fn mouse_button_matches(expected: &str, actual: MouseButton) -> bool {
    match actual {
        MouseButton::Left => expected == "left",
        MouseButton::Middle => expected == "middle",
        MouseButton::Right => expected == "right",
        MouseButton::Back => expected == "back",
        MouseButton::Forward => expected == "forward",
        MouseButton::Other(number) => expected == format!("other:{number}"),
    }
}

fn mouse_modifiers_match(expected: &[String], actual: Modifiers) -> bool {
    let ctrl = expected.iter().any(|modifier| modifier == "ctrl");
    let alt = expected.iter().any(|modifier| modifier == "alt");
    let shift = expected.iter().any(|modifier| modifier == "shift");
    let meta = expected.iter().any(|modifier| modifier == "meta");
    actual.ctrl == ctrl && actual.alt == alt && actual.shift == shift && actual.meta == meta
}

fn mouse_binding_area_matches(expected: MouseBindingArea, actual: MouseBindingArea) -> bool {
    match expected {
        MouseBindingArea::Any => true,
        MouseBindingArea::Chrome => !matches!(actual, MouseBindingArea::Content),
        _ => expected == actual,
    }
}

fn shell_quote_path(path: &str) -> String {
    format!("'{}'", path.replace('\'', "'\"'\"'"))
}

fn is_text_preview_path(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }
    let Some(extension) = path.extension().and_then(|value| value.to_str()) else {
        return true;
    };
    matches!(
        extension.to_ascii_lowercase().as_str(),
        "txt"
            | "md"
            | "markdown"
            | "rs"
            | "toml"
            | "json"
            | "yaml"
            | "yml"
            | "lua"
            | "sh"
            | "zsh"
            | "fish"
            | "py"
            | "js"
            | "ts"
            | "tsx"
            | "jsx"
            | "css"
            | "html"
            | "xml"
            | "csv"
            | "log"
            | "env"
            | "gitignore"
    )
}

fn read_text_preview_file(path: &Path) -> std::io::Result<(String, bool)> {
    const MAX_PREVIEW_BYTES: u64 = 2 * 1024 * 1024;
    let mut file = File::open(path)?;
    let mut bytes = Vec::new();
    let read = std::io::Read::by_ref(&mut file)
        .take(MAX_PREVIEW_BYTES + 1)
        .read_to_end(&mut bytes)?;
    let truncated = read as u64 > MAX_PREVIEW_BYTES;
    if truncated {
        bytes.truncate(MAX_PREVIEW_BYTES as usize);
    }
    if bytes.iter().take(8192).any(|byte| *byte == 0) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "binary-looking file contains NUL bytes",
        ));
    }
    let mut content = String::from_utf8_lossy(&bytes).into_owned();
    if truncated {
        content.push_str("\n\n[preview truncated at 2 MiB]");
    }
    Ok((content, truncated))
}

fn saved_searches_path() -> PathBuf {
    WokConfig::config_dir().join("searches.txt")
}

fn read_saved_searches() -> Vec<String> {
    std::fs::read_to_string(saved_searches_path())
        .unwrap_or_default()
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .map(ToString::to_string)
        .collect()
}

fn write_saved_searches(queries: &[String]) -> std::io::Result<()> {
    let path = saved_searches_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, queries.join("\n"))
}

fn workspace_session_entries() -> Vec<(String, String)> {
    let dir = WokConfig::config_dir().join("sessions");
    let mut entries = Vec::new();
    if let Ok(read_dir) = std::fs::read_dir(dir) {
        for entry in read_dir.flatten() {
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("json") {
                continue;
            }
            let Some(name) = path.file_stem().and_then(|value| value.to_str()) else {
                continue;
            };
            let description = load_session(&path).map_or_else(
                |_| path.display().to_string(),
                |session| {
                    let saved = if session.saved_at_unix_ms == 0 {
                        "unknown time".to_string()
                    } else {
                        format!("saved {}", session.saved_at_unix_ms)
                    };
                    let mut label = format!(
                        "{} | {} tabs | {} panes | Wok {}",
                        saved,
                        session.tabs.len(),
                        session.panes.len(),
                        if session.wok_version.is_empty() {
                            "unknown"
                        } else {
                            session.wok_version.as_str()
                        }
                    );
                    if !session.workspace_description.trim().is_empty() {
                        label.push_str(&format!(" | {}", session.workspace_description.trim()));
                    }
                    if !session.workspace_tags.is_empty() {
                        label.push_str(&format!(" | tags: {}", session.workspace_tags.join(",")));
                    }
                    label
                },
            );
            entries.push((name.to_string(), description));
        }
    }
    entries.sort_by(|left, right| left.0.cmp(&right.0));
    entries
}

fn scratch_snippet_entries() -> Vec<String> {
    scratch_files()
        .into_iter()
        .flat_map(|(_, path)| {
            std::fs::read_to_string(path)
                .unwrap_or_default()
                .lines()
                .map(ToString::to_string)
                .collect::<Vec<_>>()
        })
        .map(|line| line.trim().to_string())
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .collect()
}

fn scratch_dir() -> PathBuf {
    WokConfig::config_dir().join("scratch")
}

fn scratch_path_for_name(name: &str) -> PathBuf {
    let safe = sanitize_workspace_name(name);
    if safe == "default" {
        return WokConfig::config_dir().join("scratch.md");
    }
    scratch_dir().join(format!("{safe}.md"))
}

fn scratch_files() -> Vec<(String, PathBuf)> {
    let mut files = vec![("default".to_string(), scratch_path_for_name("default"))];
    if let Ok(read_dir) = std::fs::read_dir(scratch_dir()) {
        for entry in read_dir.flatten() {
            let path = entry.path();
            if path.extension().and_then(|value| value.to_str()) != Some("md") {
                continue;
            }
            let Some(name) = path.file_stem().and_then(|value| value.to_str()) else {
                continue;
            };
            if name != "default" {
                files.push((name.to_string(), path));
            }
        }
    }
    files.sort_by(|left, right| left.0.cmp(&right.0));
    files.dedup_by(|left, right| left.0 == right.0);
    files
}

fn sanitize_workspace_name(name: &str) -> String {
    let sanitized = name
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || matches!(ch, '-' | '_' | '.') {
                ch
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .to_string();
    if sanitized.is_empty() {
        "default".to_string()
    } else {
        sanitized
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
struct PathLikeSpan {
    start_col: usize,
    end_col: usize,
    target: ParsedPathTarget,
}

fn extract_path_near_column(line: &str, col: usize) -> Option<ParsedPathTarget> {
    let mut candidates = Vec::new();
    for span in path_like_spans(line) {
        let start = span.start_col;
        let end = span.end_col;
        if (start..=end).contains(&col) {
            candidates.push(span);
        }
    }
    candidates
        .into_iter()
        .max_by_key(|candidate| candidate.end_col.saturating_sub(candidate.start_col))
        .map(|candidate| candidate.target)
}

fn path_like_spans(line: &str) -> Vec<PathLikeSpan> {
    let mut spans = Vec::new();
    let mut start_byte = None;
    let mut start_col = 0usize;
    let mut quote = None;
    let mut escaped = false;

    for (byte_idx, ch) in line.char_indices() {
        if let Some(active_quote) = quote {
            if escaped {
                escaped = false;
                continue;
            }
            if ch == '\\' {
                escaped = true;
                continue;
            }
            if ch == active_quote {
                if let Some(start) = start_byte {
                    let end = extend_line_column_suffix_end(line, byte_idx + ch.len_utf8());
                    push_path_span_candidate(line, start, end, start_col, &mut spans);
                }
                start_byte = None;
                quote = None;
            }
            continue;
        }

        if matches!(ch, '"' | '\'' | '`') {
            start_byte = Some(byte_idx);
            start_col = line[..byte_idx].chars().count();
            quote = Some(ch);
            continue;
        }

        if escaped {
            escaped = false;
            continue;
        }
        if ch == '\\' && start_byte.is_some() {
            escaped = true;
            continue;
        }
        let path_char = is_path_token_char(ch);
        match (start_byte, path_char) {
            (None, true) => {
                start_byte = Some(byte_idx);
                start_col = line[..byte_idx].chars().count();
            }
            (Some(start), false) => {
                push_path_span_candidate(line, start, byte_idx, start_col, &mut spans);
                start_byte = None;
            }
            _ => {}
        }
    }
    if let Some(start) = start_byte {
        push_path_span_candidate(line, start, line.len(), start_col, &mut spans);
    }
    spans
}

fn is_path_token_char(ch: char) -> bool {
    ch.is_ascii_alphanumeric()
        || matches!(
            ch,
            '/' | '~' | '.' | '_' | '-' | '+' | '@' | ':' | '[' | ']'
        )
}

fn looks_like_path_token(token: &str) -> bool {
    token.starts_with('/')
        || token.starts_with("~/")
        || token.starts_with("./")
        || token.starts_with("../")
        || token.contains('/')
}

fn clean_path_token(token: &str) -> String {
    token
        .trim_matches(|ch: char| matches!(ch, '"' | '\'' | '`' | '<' | '>' | '[' | ']' | '(' | ')'))
        .trim_end_matches(|ch: char| matches!(ch, ',' | ';' | ':' | '.'))
        .replace("\\ ", " ")
        .replace("\\(", "(")
        .replace("\\)", ")")
        .to_string()
}

fn push_path_span_candidate(
    line: &str,
    start_byte: usize,
    end_byte: usize,
    start_col: usize,
    spans: &mut Vec<PathLikeSpan>,
) {
    let raw = &line[start_byte..end_byte];
    let Some(target) = parse_path_target(raw) else {
        return;
    };
    let end_col = start_col + raw.chars().count();
    spans.push(PathLikeSpan {
        start_col,
        end_col,
        target,
    });
}

fn extend_line_column_suffix_end(line: &str, mut end_byte: usize) -> usize {
    let bytes = line.as_bytes();
    let mut cursor = end_byte;
    for _ in 0..2 {
        if bytes.get(cursor) != Some(&b':') {
            break;
        }
        let digits_start = cursor + 1;
        let mut digits_end = digits_start;
        while bytes
            .get(digits_end)
            .is_some_and(|byte| byte.is_ascii_digit())
        {
            digits_end += 1;
        }
        if digits_end == digits_start {
            break;
        }
        end_byte = digits_end;
        cursor = digits_end;
    }
    end_byte
}

fn parse_path_target(raw: &str) -> Option<ParsedPathTarget> {
    let mut token = clean_path_token(raw);
    if token.is_empty() {
        return None;
    }
    let (line, column) = parse_line_column_suffix(&mut token);
    token = clean_path_token(&token);
    if !looks_like_path_token(&token) {
        return None;
    }
    Some(ParsedPathTarget {
        path: PathBuf::from(token),
        line,
        column,
    })
}

fn parse_line_column_suffix(token: &mut String) -> (Option<usize>, Option<usize>) {
    let parts = token.rsplitn(3, ':').collect::<Vec<_>>();
    if parts.len() < 2 {
        return (None, None);
    }
    let first = parts[0].parse::<usize>().ok();
    let second = parts.get(1).and_then(|value| value.parse::<usize>().ok());
    match (first, second) {
        (Some(column), Some(line)) if parts.len() == 3 => {
            let keep = token
                .len()
                .saturating_sub(parts[0].len() + parts[1].len() + 2);
            token.truncate(keep);
            (Some(line), Some(column))
        }
        (Some(line), _) => {
            let keep = token.len().saturating_sub(parts[0].len() + 1);
            token.truncate(keep);
            (Some(line), None)
        }
        _ => (None, None),
    }
}

fn cd_command_for_path(path: &str) -> String {
    format!("cd {}\r", shell_quote_path(path))
}

fn git_status_bar_text(branch: &str, dirty_count: usize) -> String {
    if dirty_count == 0 {
        format!("git:{branch}")
    } else {
        format!("git:{branch} +{dirty_count}")
    }
}

fn git_status_file_description(file: &wok_git::status::GitStatusFile) -> String {
    let mut parts = Vec::new();
    if file.is_staged() {
        parts.push(format!("staged {}", file.staged_status_text()));
    }
    if file.is_unstaged() {
        parts.push(format!("unstaged {}", file.unstaged_status_text()));
    }
    if let Some(old_path) = &file.old_path {
        parts.push(format!("from {old_path}"));
    }
    match (file.additions, file.deletions, file.is_binary) {
        (_, _, true) => parts.push("binary".to_string()),
        (Some(additions), Some(deletions), false) => {
            parts.push(format!("+{additions} -{deletions}"))
        }
        (Some(additions), None, false) => parts.push(format!("+{additions}")),
        (None, Some(deletions), false) => parts.push(format!("-{deletions}")),
        (None, None, false) => {}
    }
    if parts.is_empty() {
        "Git change".to_string()
    } else {
        parts.join(" | ")
    }
}

fn git_diff_line_entries(rows: Vec<wok_git::diff::DiffDisplayRow>) -> Vec<DiffLineEntry> {
    rows.into_iter()
        .map(|row| {
            let kind = match row.kind {
                wok_git::diff::DiffRowKind::Hunk => DiffLineKind::HunkHeader,
                wok_git::diff::DiffRowKind::Context => DiffLineKind::Context,
                wok_git::diff::DiffRowKind::Addition => DiffLineKind::Added,
                wok_git::diff::DiffRowKind::Deletion => DiffLineKind::Removed,
                wok_git::diff::DiffRowKind::Collapsed => DiffLineKind::HunkHeader,
            };
            DiffLineEntry {
                kind,
                text: row.text,
            }
        })
        .collect()
}

fn action_binding_labels(
    config: &wok_app::keybindings::KeybindingConfig,
) -> HashMap<Action, Vec<String>> {
    let mut labels: HashMap<Action, Vec<String>> = HashMap::new();
    for (combo, action) in &config.bindings {
        labels
            .entry(action.clone())
            .or_default()
            .push(key_combo_label(combo));
    }
    for bindings in config.context_bindings.values() {
        for (combo, action) in bindings {
            labels
                .entry(action.clone())
                .or_default()
                .push(key_combo_label(combo));
        }
    }
    for values in labels.values_mut() {
        values.sort();
        values.dedup();
    }
    labels
}

fn binding_list_label(labels: Vec<String>) -> String {
    if labels.is_empty() {
        "unbound".to_string()
    } else {
        labels.join(", ")
    }
}

fn key_combo_label(combo: &wok_app::keybindings::KeyCombo) -> String {
    let mut parts = Vec::new();
    if combo.modifiers.ctrl {
        parts.push("C".to_string());
    }
    if combo.modifiers.alt {
        parts.push("M".to_string());
    }
    if combo.modifiers.shift {
        parts.push("^".to_string());
    }
    if combo.modifiers.meta {
        parts.push("Cmd".to_string());
    }
    let key = key_action_label(&combo.key);
    if parts.is_empty() {
        key
    } else {
        format!("{}-{key}", parts.join("-"))
    }
}

fn is_modifier_only_key(action: &KeyAction) -> bool {
    matches!(
        action,
        KeyAction::ModifierShift
            | KeyAction::ModifierControl
            | KeyAction::ModifierAlt
            | KeyAction::ModifierMeta
    )
}

fn keybindings_toml_path() -> PathBuf {
    WokConfig::config_dir().join("keybindings.toml")
}

fn key_action_label(action: &KeyAction) -> String {
    match action {
        KeyAction::Char(ch) => ch.to_string(),
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

fn truncate_metric_text(text: &str, max_chars: usize) -> String {
    if text.chars().count() <= max_chars {
        return text.to_string();
    }
    let keep = max_chars.saturating_sub(3);
    let mut truncated = text.chars().take(keep).collect::<String>();
    truncated.push_str("...");
    truncated
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

fn owned_input_history_navigation(event: &InputEvent) -> Option<bool> {
    match &event.action {
        KeyAction::ArrowUp
            if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
        {
            Some(true)
        }
        KeyAction::ArrowDown
            if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
        {
            Some(false)
        }
        KeyAction::Char('p')
            if event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
        {
            Some(true)
        }
        KeyAction::Char('n')
            if event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
        {
            Some(false)
        }
        _ => None,
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

    const TEST_TYPEWRITER_CAP: usize = 4_096;

    fn test_cell(character: char) -> CellRenderData {
        CellRenderData {
            character,
            fg: CellColor::Named(256),
            bg: CellColor::Named(257),
            is_inverse: false,
            is_bold: false,
            is_italic: false,
            is_underline: false,
        }
    }

    #[test]
    fn typewriter_enqueues_nonempty_cells_for_new_output_rows() {
        let now = Instant::now();
        let mut typewriter = TypewriterState::default();
        let cells = vec![
            test_cell('l'),
            test_cell('s'),
            test_cell(' '),
            test_cell('\0'),
        ];

        typewriter.enqueue_changed_cells(42, None, &cells, now, 100.0, TEST_TYPEWRITER_CAP);

        assert!(!typewriter.is_cell_hidden(42, 0, now));
        assert!(typewriter.is_cell_hidden(42, 1, now));
        assert!(!typewriter.is_cell_hidden(42, 2, now));
        assert!(!typewriter.is_cell_hidden(42, 3, now));
    }

    #[test]
    fn typewriter_caps_large_output_bursts() {
        let now = Instant::now();
        let mut typewriter = TypewriterState::default();
        let cells = vec![test_cell('x'); TEST_TYPEWRITER_CAP + 128];

        typewriter.enqueue_changed_cells(42, None, &cells, now, 100.0, TEST_TYPEWRITER_CAP);

        assert_eq!(typewriter.pending_cell_count(), TEST_TYPEWRITER_CAP);
        assert!(!typewriter.is_cell_hidden(42, TEST_TYPEWRITER_CAP + 1, now));
    }

    #[test]
    fn typewriter_reveals_until_completion_without_time_cap() {
        let now = Instant::now();
        let mut typewriter = TypewriterState::default();
        let cells = vec![test_cell('x'); 512];

        typewriter.enqueue_changed_cells(42, None, &cells, now, 100.0, TEST_TYPEWRITER_CAP);

        assert!(typewriter.is_cell_hidden(42, 400, now + Duration::from_secs(3)));
        assert!(!typewriter.is_cell_hidden(42, 400, now + Duration::from_secs(5)));
    }

    #[test]
    fn typewriter_zero_cap_reveals_large_output_immediately() {
        let now = Instant::now();
        let mut typewriter = TypewriterState::default();
        let cells = vec![test_cell('x'); 512];

        typewriter.enqueue_changed_cells(42, None, &cells, now, 100.0, 0);

        assert_eq!(typewriter.pending_cell_count(), 0);
        assert!(!typewriter.is_cell_hidden(42, 100, now));
    }

    #[test]
    fn typewriter_large_scrollback_profile_stays_capped() {
        let now = Instant::now();
        let mut typewriter = TypewriterState::default();
        let cells = vec![test_cell('x'); 80];
        let start = Instant::now();

        for row in 0..15_000 {
            typewriter.enqueue_changed_cells(row, None, &cells, now, 2_000.0, TEST_TYPEWRITER_CAP);
        }

        let elapsed = start.elapsed();
        eprintln!(
            "typewriter large scrollback profile: queued={} rows={} elapsed_ms={:.3}",
            typewriter.pending_cell_count(),
            typewriter.pending_row_count(),
            elapsed.as_secs_f64() * 1_000.0
        );
        assert_eq!(typewriter.pending_cell_count(), TEST_TYPEWRITER_CAP);
        assert!(typewriter.pending_row_count() <= 15_000);
    }

    #[test]
    fn typewriter_fast_finished_output_uses_pending_block_fixture() {
        let mut blocks = wok_blocks::block::BlockManager::new();
        blocks.handle_event(&SemanticEvent::PromptStart { row: 0 });
        blocks.handle_event(&SemanticEvent::CommandStart { row: 0 });
        blocks.handle_event(&SemanticEvent::CommandText {
            row: 0,
            text: "ls".to_string(),
        });
        blocks.handle_event(&SemanticEvent::OutputStart { row: 1 });
        let pending_typewriter_block_id = blocks.active_output_block_id();

        blocks.handle_event(&SemanticEvent::CommandEnd {
            row: 2,
            exit_code: Some(0),
        });

        assert_eq!(blocks.active_output_block_id(), None);
        assert!(typewriter_applies_to_row(
            &blocks.blocks,
            pending_typewriter_block_id,
            1
        ));
        assert!(typewriter_applies_to_row(
            &blocks.blocks,
            pending_typewriter_block_id,
            2
        ));
        assert!(!typewriter_applies_to_row(
            &blocks.blocks,
            pending_typewriter_block_id,
            3
        ));
    }

    #[test]
    fn typewriter_alt_screen_replay_fixture_disables_queueing() {
        let mut terminal = wok_terminal::state::TerminalState::new(80, 24, 1_000);
        assert!(typewriter_is_active(true, terminal.is_alt_screen()));

        terminal.process_bytes(b"\x1b[?1049h");
        assert!(terminal.is_alt_screen());
        assert!(!typewriter_is_active(true, terminal.is_alt_screen()));

        terminal.process_bytes(b"\x1b[?1049l");
        assert!(!terminal.is_alt_screen());
        assert!(typewriter_is_active(true, terminal.is_alt_screen()));
        assert!(!typewriter_is_active(false, terminal.is_alt_screen()));
    }

    #[test]
    fn debug_overlay_reports_typewriter_runtime_state() {
        let config = WokConfig {
            typewriter_effect_enabled: true,
            ..Default::default()
        };
        let mut handler = WokHandler::new(config);

        assert!(handler.debug_overlay_lines().iter().any(|line| {
            line.contains("typewriter enabled=true")
                && line.contains("active_block=n/a")
                && line.contains("queue=0 cells 0 rows")
        }));
    }

    #[test]
    fn debug_overlay_session_estimate_reuses_cache_until_ttl() {
        let mut handler = WokHandler::new(WokConfig::default());
        let now = Instant::now();
        handler.session_estimate_cache = Some(SessionEstimateCache {
            bytes: 42,
            refreshed_at: now,
        });

        assert_eq!(
            handler.cached_estimated_session_bytes(now + Duration::from_millis(250)),
            42
        );
        assert_eq!(
            handler.cached_estimated_session_bytes(now + SESSION_ESTIMATE_CACHE_TTL),
            0
        );
    }

    fn test_block(id: u64, start: usize, end: usize, exit_code: Option<i32>) -> Block {
        Block {
            id,
            prompt_text: String::new(),
            command_text: format!("command {id}"),
            output_start_row: start,
            output_end_row: end,
            exit_code,
            start_time: Instant::now(),
            end_time: exit_code.map(|_| Instant::now()),
            duration: None,
            is_collapsed: false,
            scroll_offset: 0,
            cwd: PathBuf::from("/tmp"),
            git_branch: None,
            git_dirty: None,
            is_bookmarked: false,
            trigger_highlights: Vec::new(),
        }
    }

    #[test]
    fn typewriter_only_applies_to_active_output_block() {
        let blocks = vec![test_block(1, 10, 12, Some(0)), test_block(2, 20, 20, None)];

        assert!(!typewriter_applies_to_row(&blocks, Some(2), 11));
        assert!(typewriter_applies_to_row(&blocks, Some(2), 20));
        assert!(typewriter_applies_to_row(&blocks, Some(2), 21));
        assert!(!typewriter_applies_to_row(&blocks, None, 20));
    }

    #[test]
    fn typewriter_allows_pending_completed_block_once() {
        let blocks = vec![
            test_block(1, 10, 12, Some(0)),
            test_block(2, 20, 22, Some(0)),
        ];

        assert!(!typewriter_applies_to_row(&blocks, Some(2), 12));
        assert!(typewriter_applies_to_row(&blocks, Some(2), 20));
        assert!(typewriter_applies_to_row(&blocks, Some(2), 22));
        assert!(!typewriter_applies_to_row(&blocks, Some(2), 23));
    }

    #[test]
    fn test_parse_lua_action_supports_aliases() {
        assert_eq!(parse_lua_action("close_pane"), Some(Action::CloseSplit));
        assert_eq!(
            parse_lua_action("toggle_search"),
            Some(Action::SearchGlobal)
        );
        assert_eq!(parse_lua_action("copy_block"), Some(Action::BlockCopy));
        assert_eq!(
            parse_lua_action("reset_config"),
            Some(Action::ResetSettings)
        );
        assert_eq!(
            parse_lua_action("next_visual_effect"),
            Some(Action::CycleVisualEffect)
        );
        assert_eq!(
            parse_lua_action("close_preview"),
            Some(Action::CloseMediaPreview)
        );
        assert_eq!(
            parse_lua_action("preview_path"),
            Some(Action::PreviewPathUnderCursor)
        );
        assert_eq!(parse_lua_action("scratch"), Some(Action::OpenScratchBuffer));
        assert_eq!(
            parse_lua_action("regex_search"),
            Some(Action::ToggleSearchRegex)
        );
        assert_eq!(
            parse_lua_action("media_play_pause"),
            Some(Action::ToggleMediaPreviewPlayback)
        );
        assert_eq!(
            parse_lua_action("media_faster"),
            Some(Action::FastMediaPreviewPlayback)
        );
        assert_eq!(
            parse_lua_action("search_results"),
            Some(Action::OpenSearchResults)
        );
        assert_eq!(
            parse_lua_action("block_inspector"),
            Some(Action::OpenBlockInspector)
        );
        assert_eq!(
            parse_lua_action("insert_scratch"),
            Some(Action::InsertScratchSelectionIntoInput)
        );
        assert_eq!(
            parse_lua_action("run_scratch"),
            Some(Action::SendScratchSelectionToPane)
        );
        assert_eq!(
            parse_lua_action("workspace_browser"),
            Some(Action::OpenWorkspaceBrowser)
        );
        assert_eq!(
            parse_lua_action("compare_reruns"),
            Some(Action::OpenBlockRerunComparison)
        );
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
    fn test_parse_trigger_action_supports_system_notify() {
        assert_eq!(
            parse_trigger_action_descriptor("system_notify:Homebrew finished"),
            Some(TriggerAction::SystemNotify {
                title: String::new(),
                message: "Homebrew finished".to_string(),
            })
        );
        assert_eq!(
            parse_trigger_action_descriptor("desktop_notify"),
            Some(TriggerAction::SystemNotify {
                title: String::new(),
                message: String::new(),
            })
        );
    }

    #[test]
    fn test_build_quads_renders_chrome_after_smooth_scrolled_rows() {
        let source = include_str!("main.rs");
        let build_quads = source
            .split("fn build_quads(&mut self)")
            .nth(1)
            .expect("build_quads should exist");
        let smooth_rows = build_quads
            .find(".append_translated(row_batch, 0.0, smooth_scroll_y)")
            .expect("smooth-scrolled row append should exist");
        let tab_bar = build_quads
            .find("render_tab_bar(")
            .expect("tab bar rendering should exist");
        let status_bar = build_quads
            .find("render_status_bar(")
            .expect("status bar rendering should exist");

        assert!(
            smooth_rows < tab_bar,
            "chrome must render after smooth-scrolled rows so translated terminal content cannot cover the tab bar"
        );
        assert!(
            smooth_rows < status_bar,
            "chrome must render after smooth-scrolled rows so translated terminal content cannot cover the status bar"
        );
    }

    #[test]
    fn test_palette_actions_catalog_prioritizes_discoverability() {
        let catalog = palette_actions_catalog();
        assert_eq!(catalog[0], Action::CommandPalette);
        assert_eq!(catalog[1], Action::CommandSearch);
        assert_eq!(catalog[2], Action::SearchGlobal);
        assert_eq!(catalog[3], Action::QuickSelect);
        assert!(catalog.contains(&Action::ResetSettings));
        assert!(catalog.contains(&Action::CycleVisualEffect));
        assert!(catalog.contains(&Action::CloseMediaPreview));
        assert!(catalog.contains(&Action::ToggleMediaPreviewPlayback));
        assert!(catalog.contains(&Action::FastMediaPreviewPlayback));
        assert!(catalog.contains(&Action::PreviewPathUnderCursor));
        assert!(catalog.contains(&Action::OpenScratchBuffer));
        assert!(catalog.contains(&Action::OpenScratchPalette));
        assert!(catalog.contains(&Action::InsertScratchSelectionIntoInput));
        assert!(catalog.contains(&Action::SendScratchSelectionToPane));
        assert!(catalog.contains(&Action::ToggleSearchRegex));
        assert!(catalog.contains(&Action::OpenSearchResults));
        assert!(catalog.contains(&Action::OpenBlockInspector));
        assert!(catalog.contains(&Action::OpenBlockRerunComparison));
        assert!(catalog.contains(&Action::OpenWorkspaceBrowser));
    }

    #[test]
    fn test_extract_path_near_column_finds_visible_paths() {
        let line = "open ./src/main.rs or /tmp/out.log";
        assert_eq!(
            extract_path_near_column(line, 8).map(|target| target.path),
            Some(PathBuf::from("./src/main.rs"))
        );
        assert_eq!(
            extract_path_near_column(line, 26).map(|target| target.path),
            Some(PathBuf::from("/tmp/out.log"))
        );
        let compiler = r#"error: "src/my file.rs":42:7: nope"#;
        let target = extract_path_near_column(compiler, 10).expect("path target");
        assert_eq!(target.path, PathBuf::from("src/my file.rs"));
        assert_eq!(target.line, Some(42));
        assert_eq!(target.column, Some(7));
    }

    #[test]
    fn test_action_palette_description_marks_unbound_shortcut() {
        let description = action_palette_description(&Action::CommandPalette, "");
        assert!(description.contains("Shortcut: unbound"));
    }

    #[test]
    fn test_git_status_file_description_includes_staging_and_counts() {
        let file = wok_git::status::GitStatusFile {
            path: "src/lib.rs".to_string(),
            old_path: None,
            index_status: 'M',
            worktree_status: 'M',
            additions: Some(3),
            deletions: Some(1),
            is_binary: false,
        };

        assert_eq!(
            git_status_file_description(&file),
            "staged M | unstaged M | +3 -1"
        );
    }

    #[test]
    fn test_git_diff_line_entries_map_to_overlay_kinds() {
        let entries = git_diff_line_entries(vec![
            wok_git::diff::DiffDisplayRow {
                kind: wok_git::diff::DiffRowKind::Hunk,
                old_line_number: None,
                new_line_number: None,
                old_text: None,
                new_text: None,
                text: "@@ -1 +1 @@".to_string(),
            },
            wok_git::diff::DiffDisplayRow {
                kind: wok_git::diff::DiffRowKind::Addition,
                old_line_number: None,
                new_line_number: Some(1),
                old_text: None,
                new_text: Some("new".to_string()),
                text: "+new".to_string(),
            },
        ]);

        assert_eq!(entries[0].kind, DiffLineKind::HunkHeader);
        assert_eq!(entries[1].kind, DiffLineKind::Added);
    }

    #[test]
    fn test_git_change_palette_entries_include_file_actions() {
        let file = wok_git::status::GitStatusFile {
            path: "src/main.rs".to_string(),
            old_path: None,
            index_status: 'M',
            worktree_status: 'M',
            additions: Some(3),
            deletions: Some(1),
            is_binary: false,
        };

        let entries = git_change_palette_entries_for_file(file);
        let actions = entries
            .iter()
            .map(|entry| entry.action.clone())
            .collect::<Vec<_>>();

        assert_eq!(
            actions,
            vec![
                PaletteAction::GitFileDiff("src/main.rs".to_string()),
                PaletteAction::GitStageFile("src/main.rs".to_string()),
                PaletteAction::GitUnstageFile("src/main.rs".to_string()),
                PaletteAction::GitDiscardFile("src/main.rs".to_string()),
            ]
        );
        assert_eq!(entries[0].label, "Preview M  src/main.rs");
        assert!(entries[0].description.contains("+3 -1"));
    }

    #[test]
    fn test_git_discard_confirmation_entries_require_confirm_action() {
        let entries = git_discard_confirmation_entries("src/main.rs");

        assert_eq!(entries[0].label, "Confirm discard src/main.rs");
        assert_eq!(
            entries[0].action,
            PaletteAction::GitConfirmDiscardFile("src/main.rs".to_string())
        );
        assert_eq!(entries[1].label, "Cancel");
        assert_eq!(entries[1].action, PaletteAction::Dismiss);
    }

    #[test]
    fn test_git_changes_refresh_reports_clean_or_entries() {
        let clean = wok_git::service::GitStatusSnapshot {
            worktree_root: std::path::PathBuf::from("/repo"),
            branch: Some("main".to_string()),
            files: Vec::new(),
        };
        assert_eq!(
            git_changes_refresh_after_action(clean),
            GitChangesRefresh::Clean
        );

        let dirty = wok_git::service::GitStatusSnapshot {
            worktree_root: std::path::PathBuf::from("/repo"),
            branch: Some("main".to_string()),
            files: vec![wok_git::status::GitStatusFile {
                path: "src/main.rs".to_string(),
                old_path: None,
                index_status: ' ',
                worktree_status: 'M',
                additions: None,
                deletions: None,
                is_binary: false,
            }],
        };
        let GitChangesRefresh::Entries(entries) = git_changes_refresh_after_action(dirty) else {
            panic!("dirty snapshot should reopen palette entries");
        };
        assert!(entries.iter().any(|entry| {
            entry.action == PaletteAction::GitStageFile("src/main.rs".to_string())
        }));
    }

    #[test]
    fn test_git_worktree_entries_mark_current_worktree() {
        let worktree = wok_git::service::GitWorktree {
            path: std::path::PathBuf::from("/repo/main"),
            branch: Some("main".to_string()),
            head: Some("abcdef".to_string()),
            is_bare: false,
            is_detached: false,
        };

        let entries = build_git_worktree_palette_entries(
            vec![worktree],
            std::path::Path::new("/repo/main/src"),
        );

        assert_eq!(entries[0].label, "main");
        assert!(entries[0].description.contains("current"));
        assert_eq!(
            entries[0].action,
            PaletteAction::ChangeDirectory("/repo/main".to_string())
        );
    }

    #[test]
    fn test_shell_quote_path_escapes_single_quotes() {
        assert_eq!(shell_quote_path("/tmp/it's-here"), "'/tmp/it'\"'\"'s-here'");
    }

    #[test]
    fn test_cd_command_for_path_quotes_path() {
        assert_eq!(
            cd_command_for_path("/tmp/work tree"),
            "cd '/tmp/work tree'\r"
        );
    }

    #[test]
    fn test_git_status_bar_text_includes_dirty_count() {
        assert_eq!(git_status_bar_text("main", 0), "git:main");
        assert_eq!(git_status_bar_text("feature/x", 3), "git:feature/x +3");
    }

    #[test]
    fn test_recent_key_label_preserves_character_case() {
        let lower = wok_app::keybindings::KeyCombo {
            key: KeyAction::Char('a'),
            modifiers: wok_app::input::Modifiers::default(),
        };
        let upper = wok_app::keybindings::KeyCombo {
            key: KeyAction::Char('A'),
            modifiers: wok_app::input::Modifiers {
                shift: true,
                ..Default::default()
            },
        };

        assert_eq!(key_combo_label(&lower), "a");
        assert_eq!(key_combo_label(&upper), "^-A");
    }

    #[test]
    fn test_sgr_mouse_press_encoding() {
        let bytes = encode_terminal_mouse_event(
            TerminalMouseEvent::Press(MouseButton::Left),
            CellPos { row: 4, col: 2 },
            wok_app::input::Modifiers::default(),
            true,
        )
        .expect("left press should encode");

        assert_eq!(bytes, b"\x1b[<0;3;5M");
    }

    #[test]
    fn test_legacy_mouse_release_encoding() {
        let bytes = encode_terminal_mouse_event(
            TerminalMouseEvent::Release,
            CellPos { row: 0, col: 0 },
            wok_app::input::Modifiers::default(),
            false,
        )
        .expect("release should encode");

        assert_eq!(bytes, vec![0x1b, b'[', b'M', 35, 33, 33]);
    }

    #[test]
    fn test_sgr_mouse_drag_and_horizontal_wheel_encoding() {
        let drag = encode_terminal_mouse_event(
            TerminalMouseEvent::Motion(Some(MouseButton::Left)),
            CellPos { row: 1, col: 1 },
            wok_app::input::Modifiers {
                ctrl: true,
                ..Default::default()
            },
            true,
        )
        .expect("left drag should encode");
        assert_eq!(drag, b"\x1b[<48;2;2M");

        let wheel = encode_terminal_mouse_event(
            TerminalMouseEvent::Wheel {
                horizontal: true,
                positive: false,
            },
            CellPos { row: 0, col: 0 },
            wok_app::input::Modifiers::default(),
            true,
        )
        .expect("horizontal wheel should encode");
        assert_eq!(wheel, b"\x1b[<67;1;1M");
    }

    #[test]
    fn test_word_selection_range_selects_cli_tokens() {
        let row = "open /tmp/wok file.txt";

        assert_eq!(word_selection_range(row, 7), Some((5, 12)));
        assert_eq!(word_selection_range(row, 13), None);
        assert_eq!(word_selection_range(row, 15), Some((14, 21)));
    }

    #[test]
    fn test_remote_rpc_schema_file_matches_runtime_method_catalog() {
        let schema_path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .join("..")
            .join("docs")
            .join("REMOTE_RPC_SCHEMA_V1.json");
        let schema_text =
            std::fs::read_to_string(schema_path).expect("rpc schema file should be readable");
        let schema: serde_json::Value =
            serde_json::from_str(&schema_text).expect("rpc schema json should parse");

        assert_eq!(schema["schema_version"], json!(REMOTE_RPC_SCHEMA_VERSION));
        let schema_methods = schema["methods"]
            .as_object()
            .expect("schema methods should be an object")
            .keys()
            .cloned()
            .collect::<std::collections::BTreeSet<_>>();
        let runtime_methods = remote_rpc_methods()
            .iter()
            .map(|method| (*method).to_string())
            .collect::<std::collections::BTreeSet<_>>();
        assert_eq!(
            schema_methods, runtime_methods,
            "schema methods should stay in lock-step with runtime handlers"
        );
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
            "\u{1b}[80:112;6:2u"
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
    fn test_kitty_keyboard_release_requires_event_type_flag() {
        let event = InputEvent {
            action: KeyAction::Char('q'),
            modifiers: Default::default(),
            is_repeat: false,
            event_type: InputEventType::Release,
        };

        assert!(input_event_to_pty_bytes(&event, 0x1).is_none());
        let encoded =
            input_event_to_pty_bytes(&event, 0x2).expect("release should encode with event flag");
        assert_eq!(String::from_utf8(encoded).expect("utf8"), "\u{1b}[113;1:3u");
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
        assert_eq!(String::from_utf8(encoded).expect("utf8"), "\u{1b}[97;1:3u");
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
            "\u{1b}[57442;5:1u"
        );
    }

    #[test]
    fn test_kitty_keyboard_combined_modifiers_encode_single_modifier_field() {
        let event = InputEvent {
            action: KeyAction::ArrowUp,
            modifiers: wok_app::input::Modifiers {
                ctrl: true,
                alt: true,
                shift: true,
                meta: true,
            },
            is_repeat: false,
            event_type: InputEventType::Press,
        };
        let encoded = input_event_to_pty_bytes(&event, 0x1).expect("kitty arrow should encode");
        assert_eq!(
            String::from_utf8(encoded).expect("utf8"),
            "\u{1b}[57362;16u"
        );
    }

    #[test]
    fn test_kitty_keyboard_repeat_omits_event_type_unless_requested() {
        let event = InputEvent {
            action: KeyAction::Char('j'),
            modifiers: Default::default(),
            is_repeat: true,
            event_type: InputEventType::Repeat,
        };

        let base =
            input_event_to_pty_bytes(&event, 0x1).expect("kitty repeat should encode without type");
        assert_eq!(String::from_utf8(base).expect("utf8"), "\u{1b}[106;1u");

        let typed =
            input_event_to_pty_bytes(&event, 0x2).expect("kitty repeat should encode with type");
        assert_eq!(String::from_utf8(typed).expect("utf8"), "\u{1b}[106;1:2u");
    }

    #[test]
    fn test_kitty_keyboard_modifier_release_requires_event_type_flag() {
        let event = InputEvent {
            action: KeyAction::ModifierAlt,
            modifiers: wok_app::input::Modifiers {
                alt: true,
                ..Default::default()
            },
            is_repeat: false,
            event_type: InputEventType::Release,
        };

        assert!(input_event_to_pty_bytes(&event, 0x1 | 0x4).is_none());
        let encoded =
            input_event_to_pty_bytes(&event, 0x2).expect("modifier release should encode");
        assert_eq!(
            String::from_utf8(encoded).expect("utf8"),
            "\u{1b}[57443;3:3u"
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
            ..Default::default()
        };
        assert_eq!(
            m.summary_line(),
            "frames:42 last_frame:0.50ms panes:2 replays:10"
        );
    }

    #[test]
    fn runtime_metrics_summary_line_with_daemon_lag() {
        let m = RuntimeMetrics {
            frame_count: 1,
            last_frame_duration_us: 0,
            pane_count: 1,
            replay_snapshot_count: 0,
            daemon_sync_lag_ms: Some(15),
            ..Default::default()
        };
        assert_eq!(
            m.summary_line(),
            "frames:1 last_frame:0.00ms panes:1 replays:0 sync_lag:15ms"
        );
    }

    #[test]
    fn phase_metric_records_rolling_summary() {
        let mut metric = PhaseMetric::default();
        metric.record(Duration::from_micros(1_000));
        metric.record(Duration::from_micros(3_000));
        assert_eq!(metric.last_us, 3_000);
        assert_eq!(metric.avg_us, 2_000);
        assert_eq!(metric.max_us, 3_000);
    }

    #[test]
    fn diff_line_counts_reports_added_and_removed_rows() {
        let previous = vec!["alpha".to_string(), "beta".to_string(), "beta".to_string()];
        let current = vec!["beta".to_string(), "gamma".to_string(), "gamma".to_string()];
        let (added, removed) = diff_line_counts(&previous, &current);
        assert_eq!((added, removed), (2, 2));
    }

    #[test]
    fn diff_line_entries_groups_hunks_with_context() {
        let previous = vec!["same".to_string(), "drop".to_string()];
        let current = vec!["same".to_string(), "add".to_string(), "add".to_string()];
        let entries = diff_line_entries(&previous, &current, 1);

        assert_eq!(entries[0].kind, DiffLineKind::HunkHeader);
        assert!(entries[0].text.starts_with("@@ -1,2 +1,3 @@"));
        assert_eq!(entries[1].kind, DiffLineKind::Context);
        assert_eq!(entries[1].text, "same");
        assert_eq!(entries[2].kind, DiffLineKind::Removed);
        assert_eq!(entries[2].text, "drop");
        assert_eq!(entries[3].kind, DiffLineKind::Added);
        assert_eq!(entries[3].text, "add");
        assert_eq!(entries[4].kind, DiffLineKind::Added);
        assert_eq!(entries[4].text, "add");
    }

    #[test]
    fn diff_line_entries_prefixes_trim_notice_for_large_inputs() {
        let previous = (0..(MAX_DIFF_INPUT_LINES + 5))
            .map(|index| format!("base-{index}"))
            .collect::<Vec<_>>();
        let mut current = previous.clone();
        current[MAX_DIFF_INPUT_LINES + 4] = "changed".to_string();

        let entries = diff_line_entries(&previous, &current, 1);
        assert_eq!(entries[0].kind, DiffLineKind::HunkHeader);
        assert!(entries[0].text.contains("trimmed 5 earlier baseline lines"));
    }

    #[test]
    fn diff_line_counts_use_trimmed_view_for_large_inputs() {
        let previous = (0..(MAX_DIFF_INPUT_LINES + 2))
            .map(|index| format!("base-{index}"))
            .collect::<Vec<_>>();
        let mut current = previous.clone();
        let last_index = current.len().saturating_sub(1);
        current[last_index] = "different-last-line".to_string();

        let (added, removed) = diff_line_counts(&previous, &current);
        assert_eq!((added, removed), (1, 1));
    }

    #[test]
    fn summarize_failures_groups_by_command() {
        let mut ok = HistoryEntry::pending("cargo test", None, Some(1));
        ok.mark_completed(Some(0), None, None);

        let mut fail_one = HistoryEntry::pending("cargo test", None, Some(1));
        fail_one.mark_completed(Some(101), None, None);

        let mut fail_two = HistoryEntry::pending("npm run lint", None, Some(1));
        fail_two.mark_completed(Some(2), None, None);

        let mut fail_three = HistoryEntry::pending("cargo test", None, Some(1));
        fail_three.mark_completed(Some(101), None, None);

        let summary = summarize_failures(&[ok, fail_one, fail_two, fail_three], 5);
        assert_eq!(summary.len(), 2);
        assert_eq!(summary[0].command, "cargo test");
        assert_eq!(summary[0].count, 2);
        assert_eq!(summary[1].command, "npm run lint");
        assert_eq!(summary[1].count, 1);
    }

    #[test]
    fn summarize_failure_trends_groups_by_bucket_cwd_and_branch() {
        let entries = vec![
            HistoryEntry {
                command: "cargo test".to_string(),
                cwd: Some(PathBuf::from("/repo/a")),
                source_pane_id: Some(1),
                started_at_ms: 3_661_000,
                completed_at_ms: Some(3_662_000),
                exit_code: Some(101),
                duration_ms: Some(1000),
            },
            HistoryEntry {
                command: "cargo test".to_string(),
                cwd: Some(PathBuf::from("/repo/a")),
                source_pane_id: Some(1),
                started_at_ms: 3_671_000,
                completed_at_ms: Some(3_672_000),
                exit_code: Some(101),
                duration_ms: Some(1000),
            },
            HistoryEntry {
                command: "npm run lint".to_string(),
                cwd: Some(PathBuf::from("/repo/b")),
                source_pane_id: Some(1),
                started_at_ms: 7_201_000,
                completed_at_ms: Some(7_202_000),
                exit_code: Some(2),
                duration_ms: Some(1000),
            },
        ];
        let blocks = vec![
            Block {
                id: 1,
                prompt_text: String::new(),
                command_text: "cargo test".to_string(),
                output_start_row: 0,
                output_end_row: 0,
                exit_code: Some(101),
                start_time: Instant::now(),
                end_time: Some(Instant::now()),
                duration: None,
                is_collapsed: false,
                scroll_offset: 0,
                cwd: PathBuf::from("/repo/a"),
                git_branch: Some("main".to_string()),
                git_dirty: None,
                is_bookmarked: false,
                trigger_highlights: Vec::new(),
            },
            Block {
                id: 2,
                prompt_text: String::new(),
                command_text: "npm run lint".to_string(),
                output_start_row: 0,
                output_end_row: 0,
                exit_code: Some(2),
                start_time: Instant::now(),
                end_time: Some(Instant::now()),
                duration: None,
                is_collapsed: false,
                scroll_offset: 0,
                cwd: PathBuf::from("/repo/b"),
                git_branch: Some("feature/x".to_string()),
                git_dirty: None,
                is_bookmarked: false,
                trigger_highlights: Vec::new(),
            },
        ];

        let trends = summarize_failure_trends(&entries, &blocks, 3_600_000, 10);
        assert_eq!(trends.len(), 2);
        assert_eq!(trends[0].command, "npm run lint");
        assert_eq!(trends[0].branch, "feature/x");
        assert_eq!(trends[0].count, 1);
        assert_eq!(trends[1].command, "cargo test");
        assert_eq!(trends[1].branch, "main");
        assert_eq!(trends[1].count, 2);
    }
}
