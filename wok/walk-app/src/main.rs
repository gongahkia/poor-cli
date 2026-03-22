//! Walk terminal emulator entry point.

use std::collections::HashMap;
use std::error::Error;
use std::sync::Arc;
use std::time::Instant;

use clap::Parser;
use serde::Serialize;
use serde_json::json;
use tracing::{info, warn};
use walk_app::app::WalkApp;
use walk_app::config::WalkConfig;
use walk_app::event_loop::run_event_loop;
use walk_app::handler::AppHandler;
use walk_app::input::{InputEvent, KeyAction};
use walk_app::keybindings::{Action, Context, KeyCombo};
use walk_app::scripting::LuaRuntime;
use walk_app::session::{
    block_from_state, block_to_state, default_session_path, load_session, named_session_path,
    save_session, split_node_from_state, split_node_to_state, PaneState, WorkspaceSessionState,
    WorkspaceTabState,
};
use walk_app::window::WindowConfig;
use walk_app::workspace::{FocusDirection, PaneId, WorkspaceState, WorkspaceTab};
use walk_blocks::block::Block;
use walk_input::editor::{EditorAction, EditorKey};
use walk_renderer::atlas::GlyphAtlas;
use walk_renderer::font::FontSystem;
use walk_renderer::gpu::GpuContext;
use walk_renderer::pipeline::CursorShape;
use walk_renderer::pipeline::QuadBatch;
use walk_renderer::render_pipeline::TerminalRenderPipeline;
use walk_terminal::shell::ShellType;
use walk_terminal::state::CellColor;
use walk_terminal::terminal::SemanticEvent;
use walk_terminal::terminal::Terminal;
use walk_ui::background::{BackgroundImage, BackgroundRenderer};
use walk_ui::layout::Rect;
use walk_ui::search::SearchLine;
use walk_ui::selection::{CellPos, SelectionState};
use walk_ui::splits::SplitManager;
use walk_ui::theme::Theme;
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
#[derive(Clone, Copy)]
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
#[derive(Clone, Copy)]
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

/// Runtime state for a pane.
struct PaneRuntime {
    app: WalkApp,
    terminal: Terminal,
    ui_rects: UiRects,
    cols: u16,
    rows: u16,
}

/// Walk application handler.
struct WalkHandler {
    config: WalkConfig,
    workspace: WorkspaceState,
    panes: HashMap<PaneId, PaneRuntime>,
    pending_pane_restore: HashMap<PaneId, PaneState>,
    lua: Option<LuaRuntime>,
    status_message: Option<String>,
    background: BackgroundRenderer,
    font: FontSystem,
    render: Option<RenderState>,
    window: Option<Arc<Window>>,
    chrome_rects: ChromeRects,
    needs_redraw: bool,
    started_at: Instant,
    last_cursor_visible: bool,
    pending_close_confirmation: Option<Instant>,
}

impl WalkHandler {
    fn new(config: WalkConfig) -> Self {
        let font = FontSystem::new(&config.font_family, config.font_size);
        let (workspace, _) = WorkspaceState::new("Walk");
        let mut lua = LuaRuntime::new().ok();
        if let Some(runtime) = lua.as_mut() {
            if let Err(error) = runtime.init(&WalkConfig::config_dir()) {
                warn!("failed to initialize Lua runtime: {error}");
            }
        }
        let background = {
            let mut background = BackgroundRenderer::new();
            if let Some(path) = resolve_background_image_path(&config) {
                if let Err(error) = background.load_image(&path) {
                    warn!("failed to load background image: {error}");
                }
            }
            background
        };

        Self {
            config,
            workspace,
            panes: HashMap::new(),
            pending_pane_restore: HashMap::new(),
            lua,
            status_message: None,
            background,
            font,
            render: None,
            window: None,
            chrome_rects: ChromeRects::default(),
            needs_redraw: true,
            started_at: Instant::now(),
            last_cursor_visible: true,
            pending_close_confirmation: None,
        }
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

    fn spawn_pane(&mut self, pane_id: PaneId, rect: Rect, focused: bool) {
        let restore = self.pending_pane_restore.remove(&pane_id);
        let mut pane_config = self.config.clone();
        if let Some(shell) = restore
            .as_ref()
            .map(|pane_state| parse_shell_type(&pane_state.shell))
        {
            pane_config.shell = shell;
        }
        let mut app = WalkApp::new(pane_config.clone());
        self.apply_lua_keybindings(&mut app);
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
            app.input_editor.buffer.line_count(),
            self.font.metrics.cell_height,
            focused,
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
                    ui_rects,
                    cols,
                    rows,
                };
                self.panes.insert(pane_id, pane_runtime);
                if let Some(pane_state) = restore {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.terminal.title = pane_state.title;
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
                pane.app.input_editor.buffer.line_count(),
                self.font.metrics.cell_height,
                focused,
            );
            let (cols, rows) = self
                .font
                .grid_dimensions(ui_rects.viewport.w, ui_rects.viewport.h);
            pane.ui_rects = ui_rects;
            if pane.cols != cols || pane.rows != rows {
                if let Err(error) = pane.terminal.resize(cols, rows) {
                    warn!("failed to resize pane terminal: {error}");
                }
                pane.cols = cols;
                pane.rows = rows;
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
                cwd: pane
                    .app
                    .block_manager
                    .blocks
                    .last()
                    .map(|block| block.cwd.clone())
                    .unwrap_or_default(),
                shell: pane.app.config.shell.to_string(),
                title: pane.terminal.title.clone(),
                input_draft: pane.app.input_editor.buffer.text(),
                search_query: pane.app.global_search.search_input.clone(),
                buffer_lines: pane
                    .terminal
                    .state
                    .text_rows()
                    .into_iter()
                    .map(|row| row.text)
                    .collect(),
                display_offset: pane.terminal.state.display_offset(),
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
            match &self.status_message {
                Some(message) => {
                    format!("{cwd}  |  {}  |  {message}", active_pane.app.config.shell)
                }
                None => format!("{cwd}  |  {}", active_pane.app.config.shell),
            }
        });
        let workspace_search = self.active_search_state();
        let cursor_shape = self.cursor_shape();
        let cursor_visible = self.cursor_visible();
        let window_opacity = self.config.window_opacity.clamp(0.0, 1.0);
        let background_image = self.background.image.clone();
        let background_loaded = background_image.is_some();
        let full_height =
            self.chrome_rects.content.y + self.chrome_rects.content.h + self.chrome_rects.status.h;
        let full_rect = Rect::new(0.0, 0.0, self.chrome_rects.content.w, full_height);
        let Some(render) = self.render.as_mut() else {
            return;
        };

        render.batch.clear();
        if let Some(image) = background_image.as_ref() {
            push_background_image(&mut render.batch, image, full_rect, window_opacity);
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

            for (row_idx, absolute_row) in visible_rows.iter().copied().enumerate() {
                let Some(render_row) = row_positions.get(row_idx).and_then(|row| *row) else {
                    continue;
                };
                for col_idx in 0..total_cols {
                    let cell = pane.terminal.state.cell_at_absolute(absolute_row, col_idx);
                    let x = viewport.x + col_idx as f32 * cw;
                    let y = viewport.y + render_row as f32 * ch;
                    let mut bg = resolve_cell_color(&cell.bg, theme, true);
                    let mut fg = resolve_cell_color(&cell.fg, theme, false);

                    if cell.is_inverse {
                        std::mem::swap(&mut bg, &mut fg);
                    }
                    if matches!(cell.bg, CellColor::Named(idx) if idx >= 16) {
                        bg[3] *= terminal_surface_alpha;
                    }

                    render.batch.push_bg_quad(x, y, cw, ch, bg);
                    let search = workspace_search.as_ref().unwrap_or(&pane.app.global_search);
                    if let Some(current_match) =
                        search_match_at_cell(search, pane_id, absolute_row, col_idx as u16)
                    {
                        let highlight = if current_match {
                            theme.highlight_current_match
                        } else {
                            theme.highlight_match
                        };
                        render.batch.push_bg_quad(
                            x,
                            y,
                            cw,
                            ch,
                            [highlight.r, highlight.g, highlight.b, highlight.a],
                        );
                    }

                    if cell.character != ' ' && cell.character != '\0' {
                        push_glyph(render, &mut self.font, x, y, cell.character, fg);
                    }
                }
            }

            push_block_decorations(
                &mut render.batch,
                theme,
                &pane.app.block_manager.blocks,
                selected_block_id,
                workspace_search.as_ref().unwrap_or(&pane.app.global_search),
                pane_id,
                &visible_rows,
                &row_positions,
                total_cols,
                viewport.x,
                viewport.y,
                cw,
                ch,
            );

            render.batch.push_bg_quad(
                viewport.x,
                viewport.y,
                viewport.w,
                1.0,
                [
                    theme.block_separator.r,
                    theme.block_separator.g,
                    theme.block_separator.b,
                    0.9,
                ],
            );
            render.batch.push_bg_quad(
                viewport.x,
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

            if focused && !pane.app.input_editor.is_active {
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

            if focused {
                render_input_editor(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.input,
                    &pane.app.input_editor.render_data(),
                    cursor_shape,
                    cursor_visible,
                    window_opacity,
                );
                let search = workspace_search.as_ref().unwrap_or(&pane.app.global_search);
                if search.is_active {
                    render_search_overlay(
                        render,
                        &mut self.font,
                        theme,
                        pane.ui_rects.viewport,
                        search,
                        window_opacity,
                    );
                }
            }
        }
    }

    fn apply_lua_keybindings(&self, app: &mut WalkApp) {
        let Some(lua) = &self.lua else {
            return;
        };
        let bindings = lua.state.keybindings.lock().unwrap().clone();
        let commands = lua.state.commands.lock().unwrap().clone();
        for binding in bindings {
            let Some(combo) = parse_lua_key_combo(&binding.key) else {
                continue;
            };
            let action_name = commands
                .get(&binding.action)
                .map(String::as_str)
                .unwrap_or(&binding.action);
            let Some(action) = parse_lua_action(action_name) else {
                continue;
            };
            let Some(context) = parse_lua_context(&binding.mode) else {
                continue;
            };
            app.keybindings
                .context_bindings
                .entry(context)
                .or_default()
                .insert(combo, action);
        }
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
            .and_then(|pane| {
                pane.app
                    .block_manager
                    .blocks
                    .last()
                    .map(|block| block.cwd.display().to_string())
            })
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

    fn has_running_processes(&self) -> bool {
        self.panes.values().any(|pane| !pane.terminal.exited)
    }

    fn run_lua_hook<T>(&mut self, hook: &str, payload: &T)
    where
        T: Serialize + ?Sized,
    {
        let Some(lua) = &self.lua else {
            return;
        };
        if let Err(error) = lua.trigger_hook(hook, payload) {
            warn!("lua hook '{hook}' failed: {error}");
        }
        self.drain_lua_side_effects();
    }

    fn drain_lua_side_effects(&mut self) {
        let Some(lua) = &self.lua else {
            return;
        };
        for notification in lua.take_notifications() {
            info!("lua: {notification}");
            self.status_message = Some(notification);
        }
        for command in lua.take_exec_requests() {
            let payload = format!("{command}\r");
            self.send_to_pty(payload.as_bytes());
        }
    }

    fn send_to_pty(&mut self, data: &[u8]) {
        if let Some(active_pane) = self.active_pane() {
            if let Err(error) = active_pane.terminal.send_input(data) {
                warn!("failed to send to PTY: {error}");
            }
        }
    }

    fn handle_semantic_events(&mut self, pane_id: PaneId, events: Vec<SemanticEvent>) {
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
                SemanticEvent::CommandEnd { exit_code, .. } => {
                    let payload = self.block_hook_payload(pane_id, exit_code);
                    self.run_lua_hook("block_finished", &payload);
                }
                SemanticEvent::CwdChanged(path) => {
                    let mut payload = self.pane_hook_payload(pane_id);
                    if let Some(object) = payload.as_object_mut() {
                        object.insert("path".to_string(), json!(path.display().to_string()));
                    }
                    self.run_lua_hook("cwd_changed", &payload);
                }
                _ => {}
            }
        }
    }

    fn handle_action(&mut self, action: Action) {
        match action {
            Action::Copy => {
                if let Some(text) = self.selection_text() {
                    if let Some(active_pane) = self.active_pane_mut() {
                        let _ = active_pane.app.clipboard.copy(&text);
                    }
                }
            }
            Action::BlockCopy => {
                if let Some(text) = self.selected_block_text() {
                    if let Some(active_pane) = self.active_pane_mut() {
                        let _ = active_pane.app.clipboard.copy(&text);
                    }
                }
            }
            Action::SearchGlobal | Action::BlockSearch | Action::SearchInBlock => {
                if let Some(active_pane) = self.active_pane_mut() {
                    active_pane.app.global_search.activate();
                }
                self.refresh_global_search();
            }
            Action::SaveSession(name) => {
                let session = self.snapshot_session();
                let path = named_session_path(&name);
                match save_session(&session, &path) {
                    Ok(()) => {
                        self.status_message = Some(format!("saved session snapshot '{}'", name));
                    }
                    Err(error) => warn!("failed to save session snapshot '{}': {error}", name),
                }
            }
            Action::LoadSession(name) => {
                let path = named_session_path(&name);
                match load_session(&path) {
                    Ok(session) => {
                        self.restore_session(session);
                        self.status_message = Some(format!("loaded session snapshot '{}'", name));
                    }
                    Err(error) => warn!("failed to load session snapshot '{}': {error}", name),
                }
            }
            Action::NewTab => {
                let pane_id = self.workspace.new_tab("Shell");
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                let payload = self.pane_hook_payload(pane_id);
                self.run_lua_hook("tab_opened", &payload);
            }
            Action::CloseTab => {
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
            Action::NextTab => {
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
            Action::PrevTab => {
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
            Action::SwitchToTab(index) => {
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
            Action::SplitVertical => {
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
                    self.run_lua_hook("pane_opened", &payload);
                }
            }
            Action::SplitHorizontal => {
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
                    self.run_lua_hook("pane_opened", &payload);
                }
            }
            Action::CloseSplit => {
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
            Action::FocusLeft => {
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
            Action::FocusRight => {
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
            Action::FocusUp => {
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
            Action::FocusDown => {
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
            Action::ResizeSplitLeft => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Horizontal, -0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::ResizeSplitRight => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Horizontal, 0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::ResizeSplitUp => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Vertical, -0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::ResizeSplitDown => {
                self.workspace
                    .resize_active_split(walk_ui::splits::SplitDirection::Vertical, 0.05);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            other => {
                let mut pty_data = None;
                let mut target_zoom = None;
                if let Some(active_pane) = self.active_pane_mut() {
                    let previous_zoom = active_pane.app.zoom.current_size();
                    pty_data = active_pane.app.handle_action(&other);
                    if (active_pane.app.zoom.current_size() - previous_zoom).abs() > f32::EPSILON {
                        target_zoom = Some(active_pane.app.zoom.current_size());
                    }
                }
                if let Some(data) = pty_data {
                    self.send_to_pty(&data);
                }
                if let Some(target_zoom) = target_zoom {
                    self.apply_zoom(target_zoom);
                }
            }
        }

        self.needs_redraw = true;
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

        self.scroll_to_current_search_match();
        self.needs_redraw = true;
        true
    }

    fn handle_editor_input(&mut self, event: &InputEvent) -> bool {
        let Some(editor_key) = input_event_to_editor_key(event) else {
            return false;
        };

        let mut submitted = None;
        let mut send_eof = false;
        if let Some(active_pane) = self.active_pane_mut() {
            match active_pane.app.input_editor.handle_key(editor_key) {
                EditorAction::Submit(command) => {
                    active_pane.app.block_manager.set_command_text(&command);
                    submitted = Some(command);
                }
                EditorAction::SendEof => {
                    send_eof = true;
                }
                EditorAction::None => {}
            }
        }

        if let Some(command) = submitted {
            let active_pane_id = self.active_pane_id();
            if !command.is_empty() {
                self.send_to_pty(command.as_bytes());
            }
            self.send_to_pty(b"\r");
            if let Some(pane_id) = active_pane_id {
                let mut payload = self.pane_hook_payload(pane_id);
                if let Some(object) = payload.as_object_mut() {
                    object.insert("command".to_string(), json!(command));
                }
                self.run_lua_hook("command_submitted", &payload);
            }
        }
        if send_eof {
            self.send_to_pty(b"\x04");
        }

        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
        self.needs_redraw = true;
        true
    }

    fn apply_zoom(&mut self, target_size: f32) {
        if (self.font.font_size - target_size).abs() <= f32::EPSILON {
            return;
        }

        self.font.set_font_size(target_size);
        for pane in self.panes.values_mut() {
            pane.app.zoom.set_current_size(target_size);
        }
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
        active_pane.terminal.state.set_display_offset(new_offset);
        self.needs_redraw = true;
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
        let selected = active_pane
            .app
            .block_navigator
            .selected_block(&active_pane.app.block_manager)?;
        Some(extract_block_text(&active_pane.terminal, selected))
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
        self.run_lua_hook("app_start", &payload);
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

        let pane_ids: Vec<PaneId> = self.panes.keys().copied().collect();
        for pane_id in pane_ids {
            let mut semantic_events = Vec::new();
            let mut is_dirty = false;
            if let Some(pane) = self.panes.get_mut(&pane_id) {
                pane.terminal.process_pty_output();
                semantic_events = pane.terminal.drain_semantic_events();
                is_dirty = pane.terminal.is_dirty();
            }
            if !semantic_events.is_empty() {
                self.handle_semantic_events(pane_id, semantic_events);
            }
            self.needs_redraw |= is_dirty;
        }

        self.needs_redraw
    }

    fn on_redraw(&mut self) {
        if !self.needs_redraw {
            return;
        }

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
        }
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

        if self.handle_editor_input(&event) {
            return;
        }

        if let Some(data) = input_event_to_pty_bytes(&event) {
            self.send_to_pty(&data);
            self.needs_redraw = true;
        }
    }

    fn on_mouse_event(&mut self, event: walk_app::input::MouseEvent) {
        match event {
            walk_app::input::MouseEvent::Press {
                button: MouseButton::Left,
                x,
                y,
                ..
            } => {
                if let Some(cell) = self.pixel_to_cell(x, y) {
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
                }
            }
            walk_app::input::MouseEvent::Scroll { .. } => {}
            walk_app::input::MouseEvent::Press { .. }
            | walk_app::input::MouseEvent::Release { .. } => {}
        }
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
        self.run_lua_hook("app_exit", &payload);
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

#[allow(clippy::too_many_arguments)]
fn render_input_editor(
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
            [
                theme.input_bg.r,
                theme.input_bg.g,
                theme.input_bg.b,
                theme.input_bg.a,
            ],
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
                theme.block_separator.r,
                theme.block_separator.g,
                theme.block_separator.b,
                0.9,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 12.0;
    let padding_y = 10.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;
    let text_color = [
        theme.input_text.r,
        theme.input_text.g,
        theme.input_text.b,
        theme.input_text.a,
    ];

    if input.lines.iter().all(String::is_empty) {
        push_text(
            render,
            font,
            base_x,
            base_y,
            "Type a command and press Enter",
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.8,
                ],
                surface_opacity,
            ),
        );
    } else {
        for (index, line) in input.lines.iter().enumerate() {
            push_text(
                render,
                font,
                base_x,
                base_y + index as f32 * font.metrics.cell_height,
                line,
                with_opacity(text_color, surface_opacity),
            );
        }
    }

    if cursor_visible {
        if let Some((cursor_row, cursor_col)) = input.cursors.first().copied() {
            let cursor_x = base_x + cursor_col as f32 * font.metrics.cell_width;
            let cursor_y = base_y + cursor_row as f32 * font.metrics.cell_height;
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

fn with_opacity(mut color: [f32; 4], opacity: f32) -> [f32; 4] {
    color[3] *= opacity.clamp(0.0, 1.0);
    color
}

fn push_background_image(batch: &mut QuadBatch, image: &BackgroundImage, rect: Rect, opacity: f32) {
    if image.width == 0 || image.height == 0 || rect.w <= 0.0 || rect.h <= 0.0 {
        return;
    }

    let grid_cols = 48usize;
    let aspect_ratio = if rect.w > 0.0 { rect.h / rect.w } else { 1.0 };
    let grid_rows = ((grid_cols as f32 * aspect_ratio).round() as usize).clamp(18, 64);
    let tile_w = rect.w / grid_cols as f32;
    let tile_h = rect.h / grid_rows as f32;

    for row in 0..grid_rows {
        for col in 0..grid_cols {
            let sample_x = ((col as f32 + 0.5) / grid_cols as f32 * image.width as f32)
                .floor()
                .clamp(0.0, image.width.saturating_sub(1) as f32)
                as usize;
            let sample_y = ((row as f32 + 0.5) / grid_rows as f32 * image.height as f32)
                .floor()
                .clamp(0.0, image.height.saturating_sub(1) as f32)
                as usize;
            let pixel_index = (sample_y * image.width as usize + sample_x) * 4;
            let Some(pixel) = image.pixels.get(pixel_index..pixel_index + 4) else {
                continue;
            };

            batch.push_bg_quad(
                rect.x + col as f32 * tile_w,
                rect.y + row as f32 * tile_h,
                tile_w + 0.5,
                tile_h + 0.5,
                [
                    f32::from(pixel[0]) / 255.0,
                    f32::from(pixel[1]) / 255.0,
                    f32::from(pixel[2]) / 255.0,
                    (f32::from(pixel[3]) / 255.0) * opacity.clamp(0.0, 1.0),
                ],
            );
        }
    }
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
        if let Some(region) = render.atlas.get_or_insert(glyph_key, width, height) {
            if width > 0 && height > 0 {
                render
                    .pipeline
                    .upload_glyph(&render.gpu, region.x, region.y, width, height, &data);
            }
            render.batch.push_glyph_quad(
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

fn extract_block_text(terminal: &Terminal, block: &Block) -> String {
    let total_rows = terminal.state.total_rows();
    if total_rows == 0 {
        return block.command_text.clone();
    }

    let max_row = total_rows.saturating_sub(1);
    let start_row = block.output_start_row.min(max_row);
    let end_row = block.output_end_row.min(max_row);
    let mut lines = Vec::new();

    if !block.command_text.is_empty() {
        lines.push(block.command_text.clone());
    }

    for row in start_row..=end_row {
        lines.push(terminal.state.row_text(row));
    }

    lines.join("\n")
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

#[allow(clippy::too_many_arguments)]
fn push_block_decorations(
    batch: &mut QuadBatch,
    theme: &Theme,
    blocks: &[Block],
    selected_block_id: Option<u64>,
    global_search: &walk_ui::search::GlobalSearch,
    pane_id: PaneId,
    visible_rows: &[usize],
    row_positions: &[Option<usize>],
    total_cols: usize,
    x_offset: f32,
    y_offset: f32,
    cell_width: f32,
    cell_height: f32,
) {
    let viewport_width = total_cols as f32 * cell_width;

    for block in blocks {
        let Some(start_idx) = visible_rows
            .iter()
            .position(|absolute_row| *absolute_row == block.output_start_row)
        else {
            continue;
        };
        let Some(start_row) = row_positions.get(start_idx).and_then(|row| *row) else {
            continue;
        };

        let end_row = visible_rows
            .iter()
            .enumerate()
            .filter(|(_, absolute_row)| {
                **absolute_row >= block.output_start_row && **absolute_row <= block.output_end_row
            })
            .filter_map(|(index, _)| row_positions.get(index).and_then(|mapped| *mapped))
            .next_back()
            .unwrap_or(start_row);

        let y = y_offset + start_row as f32 * cell_height;
        let height = (end_row.saturating_sub(start_row) + 1) as f32 * cell_height;
        let accent = if block.exit_code.unwrap_or(0) == 0 {
            theme.block_success_accent
        } else {
            theme.block_error_accent
        };

        batch.push_bg_quad(
            x_offset,
            y,
            viewport_width,
            1.0,
            [
                theme.block_separator.r,
                theme.block_separator.g,
                theme.block_separator.b,
                0.65,
            ],
        );
        batch.push_bg_quad(
            x_offset,
            y,
            4.0,
            height,
            [accent.r, accent.g, accent.b, 0.9],
        );

        if selected_block_id == Some(block.id) {
            batch.push_bg_quad(
                x_offset,
                y,
                viewport_width,
                height,
                [
                    theme.selection.r,
                    theme.selection.g,
                    theme.selection.b,
                    0.12,
                ],
            );
        }

        if let Some(current_match) =
            search_match_for_block_command(global_search, pane_id, block.id)
        {
            let highlight = if current_match {
                theme.highlight_current_match
            } else {
                theme.highlight_match
            };
            batch.push_bg_quad(
                x_offset + 4.0,
                y,
                viewport_width - 4.0,
                cell_height,
                [highlight.r, highlight.g, highlight.b, highlight.a],
            );
        }

        if block.is_collapsed {
            batch.push_bg_quad(
                x_offset + 4.0,
                y,
                viewport_width - 4.0,
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

fn parse_lua_context(mode: &str) -> Option<Context> {
    match mode {
        "normal" | "terminal" => Some(Context::Terminal),
        "input" => Some(Context::InputEditor),
        "block" => Some(Context::BlockSelected),
        "search" => Some(Context::SearchActive),
        _ => None,
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
        "block_prev" => Some(Action::BlockPrev),
        "block_next" => Some(Action::BlockNext),
        "block_copy" | "copy_block" => Some(Action::BlockCopy),
        "block_collapse" | "collapse_block" => Some(Action::BlockCollapse),
        "zoom_in" => Some(Action::ZoomIn),
        "zoom_out" => Some(Action::ZoomOut),
        "zoom_reset" => Some(Action::ZoomReset),
        "clear_screen" => Some(Action::ClearScreen),
        "send_eof" => Some(Action::SendEof),
        _ => None,
    }
}

fn parse_lua_key_combo(key: &str) -> Option<KeyCombo> {
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

    key_action.map(|key| KeyCombo { key, modifiers })
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
