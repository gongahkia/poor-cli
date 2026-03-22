//! Walk terminal emulator entry point.

use std::collections::HashMap;
use std::error::Error;
use std::sync::Arc;

use clap::Parser;
use mlua::Value;
use tracing::{info, warn};
use walk_app::app::WalkApp;
use walk_app::config::WalkConfig;
use walk_app::event_loop::run_event_loop;
use walk_app::handler::AppHandler;
use walk_app::input::{InputEvent, KeyAction};
use walk_app::keybindings::{Action, Context, KeyCombo};
use walk_app::scripting::LuaRuntime;
use walk_app::session::{
    default_session_path, load_session, save_session, split_node_from_state, split_node_to_state,
    PaneState, WorkspaceSessionState, WorkspaceTabState,
};
use walk_app::window::WindowConfig;
use walk_app::workspace::{FocusDirection, PaneId, WorkspaceState, WorkspaceTab};
use walk_blocks::block::Block;
use walk_input::editor::{EditorAction, EditorKey};
use walk_renderer::atlas::GlyphAtlas;
use walk_renderer::font::FontSystem;
use walk_renderer::gpu::GpuContext;
use walk_renderer::pipeline::QuadBatch;
use walk_renderer::render_pipeline::TerminalRenderPipeline;
use walk_terminal::shell::ShellType;
use walk_terminal::state::CellColor;
use walk_terminal::terminal::SemanticEvent;
use walk_terminal::terminal::Terminal;
use walk_ui::layout::Rect;
use walk_ui::search::SearchLine;
use walk_ui::selection::{CellPos, SelectionState};
use walk_ui::splits::SplitManager;
use walk_ui::theme::Theme;
use winit::dpi::PhysicalSize;
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
    font: FontSystem,
    render: Option<RenderState>,
    window: Option<Arc<Window>>,
    chrome_rects: ChromeRects,
    needs_redraw: bool,
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

        Self {
            config,
            workspace,
            panes: HashMap::new(),
            pending_pane_restore: HashMap::new(),
            lua,
            font,
            render: None,
            window: None,
            chrome_rects: ChromeRects::default(),
            needs_redraw: true,
        }
    }

    fn active_pane_id(&self) -> Option<PaneId> {
        self.workspace.active_pane_id()
    }

    fn active_pane(&self) -> Option<&PaneRuntime> {
        self.active_pane_id().and_then(|pane_id| self.panes.get(&pane_id))
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
        let (cols, rows) = self.font.grid_dimensions(ui_rects.viewport.w, ui_rects.viewport.h);
        let env = HashMap::new();

        match Terminal::new(&pane_config.shell, cols, rows, pane_config.scrollback_lines, env) {
            Ok(terminal) => {
                let pane_runtime = PaneRuntime {
                    app,
                    terminal,
                    ui_rects,
                    cols,
                    rows,
                };
                self.panes.insert(
                    pane_id,
                    pane_runtime,
                );
                if let Some(pane_state) = restore {
                    if let Some(pane) = self.panes.get_mut(&pane_id) {
                        pane.terminal.title = pane_state.title;
                        if !pane_state.cwd.as_os_str().is_empty() {
                            let command =
                                format!("cd -- {}\r", shell_quote_path(&pane_state.cwd.display().to_string()));
                            let _ = pane.terminal.send_input(command.as_bytes());
                        }
                    }
                }
            }
            Err(error) => warn!("failed to spawn pane terminal: {error}"),
        }
    }

    fn sync_workspace_layout(&mut self, size: PhysicalSize<u32>) {
        self.chrome_rects = compute_chrome_rects(size);
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
            let (cols, rows) = self.font.grid_dimensions(ui_rects.viewport.w, ui_rects.viewport.h);
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
        self.pending_pane_restore = session
            .panes
            .into_iter()
            .map(|pane_state| (pane_state.id, pane_state))
            .collect();
        let tabs = session
            .tabs
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
        self.workspace = WorkspaceState::from_tabs(tabs, session.active_tab);
        self.panes.clear();
        if let Some(window) = &self.window {
            self.sync_workspace_layout(window.inner_size());
        }
        if let Some(active_pane) = self.active_pane_mut() {
            if active_pane.app.global_search.is_active {
                let lines = collect_search_lines(
                    &active_pane.terminal,
                    &active_pane.app.block_manager.blocks,
                );
                active_pane
                    .app
                    .global_search
                    .search(&active_pane.app.global_search.search_input.clone(), &lines);
            }
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
            format!("{cwd}  |  {}", active_pane.app.config.shell)
        });
        let Some(render) = self.render.as_mut() else {
            return;
        };

        render.batch.clear();
        render_tab_bar(
            render,
            &mut self.font,
            self.chrome_rects.tab_bar,
            &tab_labels,
        );
        render_status_bar(
            render,
            &mut self.font,
            self.chrome_rects.status,
            status_text.as_deref(),
        );

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
            let row_positions = build_visible_row_positions(&visible_rows, &pane.app.block_manager.blocks);
            let selected_block_id = pane
                .app
                .block_navigator
                .selected_block(&pane.app.block_manager)
                .map(|block| block.id);
            let cw = self.font.metrics.cell_width;
            let ch = self.font.metrics.cell_height;

            render.batch.push_bg_quad(
                viewport.x,
                viewport.y,
                viewport.w,
                viewport.h,
                [theme.background.r, theme.background.g, theme.background.b, theme.background.a],
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

                    render.batch.push_bg_quad(x, y, cw, ch, bg);
                    if let Some(current_match) =
                        search_match_at_cell(&pane.app.global_search, absolute_row, col_idx as u16)
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
                &pane.app.global_search,
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
                [theme.block_separator.r, theme.block_separator.g, theme.block_separator.b, 0.9],
            );
            render.batch.push_bg_quad(
                viewport.x,
                viewport.y,
                1.0,
                viewport.h,
                [theme.block_separator.r, theme.block_separator.g, theme.block_separator.b, 0.9],
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
                render.batch.push_bg_quad(
                    cursor_x,
                    cursor_y,
                    cw,
                    ch,
                    [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.7],
                );
            }

            if focused {
                render_input_editor(
                    render,
                    &mut self.font,
                    theme,
                    pane.ui_rects.input,
                    &pane.app.input_editor.render_data(),
                );
                if pane.app.global_search.is_active {
                    render_search_overlay(
                        render,
                        &mut self.font,
                        theme,
                        pane.ui_rects.viewport,
                        &pane.app.global_search,
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
        for binding in bindings {
            let Some(combo) = parse_lua_key_combo(&binding.key) else {
                continue;
            };
            let Some(action) = parse_lua_action(&binding.action) else {
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

    fn run_lua_hook(&mut self, hook: &str) {
        let Some(lua) = &self.lua else {
            return;
        };
        if let Err(error) = lua.trigger_hook(hook, Value::Nil) {
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
                SemanticEvent::CommandEnd { .. } => self.run_lua_hook("block_finished"),
                SemanticEvent::CwdChanged(_) => self.run_lua_hook("cwd_changed"),
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
            Action::NewTab => {
                self.workspace.new_tab("Shell");
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.run_lua_hook("tab_opened");
            }
            Action::CloseTab => {
                if let Some(removed) = self.workspace.close_active_tab() {
                    for pane_id in removed {
                        self.panes.remove(&pane_id);
                    }
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                }
            }
            Action::NextTab => {
                self.workspace.next_tab();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::PrevTab => {
                self.workspace.prev_tab();
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::SwitchToTab(index) => {
                self.workspace.switch_tab(index.saturating_sub(1) as usize);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::SplitVertical => {
                let _ = self
                    .workspace
                    .split_active(walk_ui::splits::SplitDirection::Horizontal);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.run_lua_hook("pane_opened");
            }
            Action::SplitHorizontal => {
                let _ = self
                    .workspace
                    .split_active(walk_ui::splits::SplitDirection::Vertical);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
                self.run_lua_hook("pane_opened");
            }
            Action::CloseSplit => {
                if let Some(removed_pane) = self.workspace.close_active_pane() {
                    self.panes.remove(&removed_pane);
                    if let Some(window) = &self.window {
                        self.sync_workspace_layout(window.inner_size());
                    }
                }
            }
            Action::FocusLeft => {
                self.workspace
                    .focus_in_direction(FocusDirection::Left, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::FocusRight => {
                self.workspace
                    .focus_in_direction(FocusDirection::Right, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::FocusUp => {
                self.workspace
                    .focus_in_direction(FocusDirection::Up, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
                }
            }
            Action::FocusDown => {
                self.workspace
                    .focus_in_direction(FocusDirection::Down, self.chrome_rects.content);
                if let Some(window) = &self.window {
                    self.sync_workspace_layout(window.inner_size());
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
            if !command.is_empty() {
                self.send_to_pty(command.as_bytes());
            }
            self.send_to_pty(b"\r");
            self.run_lua_hook("command_submitted");
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
        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };
        if !active_pane.app.global_search.is_active {
            return;
        }

        if active_pane.app.global_search.search_input.is_empty() {
            active_pane.app.global_search.matches.clear();
            active_pane.app.global_search.current = 0;
            active_pane.app.global_search.query.clear();
            return;
        }

        let lines = collect_search_lines(&active_pane.terminal, &active_pane.app.block_manager.blocks);
        active_pane
            .app
            .global_search
            .search(&active_pane.app.global_search.search_input.clone(), &lines);
        self.scroll_to_current_search_match();
    }

    fn scroll_to_current_search_match(&mut self) {
        let Some(active_pane) = self.active_pane_mut() else {
            return;
        };
        let Some(target) = active_pane
            .app
            .global_search
            .matches
            .get(active_pane.app.global_search.current)
        else {
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
        self.run_lua_hook("app_start");
        info!("GPU initialized");
    }

    fn on_frame_tick(&mut self) -> bool {
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
            let clear = [
                clear_theme.background.r,
                clear_theme.background.g,
                clear_theme.background.b,
                clear_theme.background.a,
            ];
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
                let was_selecting =
                    self.active_pane().is_some_and(|pane| matches!(pane.app.selection.state, SelectionState::Selecting { .. }));
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
                if self
                    .active_pane()
                    .is_some_and(|pane| matches!(pane.app.selection.state, SelectionState::Selecting { .. }))
                {
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

    fn on_close_requested(&mut self) {
        self.run_lua_hook("app_exit");
        let session = self.snapshot_session();
        let _ = save_session(&session, &default_session_path());
        info!("walk closing");
    }
}

fn compute_chrome_rects(size: PhysicalSize<u32>) -> ChromeRects {
    let width = size.width as f32;
    let height = size.height as f32;
    let tab_bar_height = 32.0;
    let status_height = 24.0;

    ChromeRects {
        tab_bar: Rect::new(0.0, 0.0, width, tab_bar_height),
        content: Rect::new(0.0, tab_bar_height, width, (height - tab_bar_height - status_height).max(0.0)),
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
    let line_count = input_lines.max(1).min(8) as f32;
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
) {
    render.batch.push_bg_quad(rect.x, rect.y, rect.w, rect.h, [0.08, 0.09, 0.13, 1.0]);
    if tabs.is_empty() {
        return;
    }

    let tab_width = (rect.w / tabs.len() as f32).max(120.0).min(220.0);
    for (index, (is_active, label)) in tabs.iter().enumerate() {
        let x = rect.x + index as f32 * tab_width;
        let background = if *is_active {
            [0.14, 0.16, 0.22, 1.0]
        } else {
            [0.10, 0.11, 0.15, 1.0]
        };
        render.batch.push_bg_quad(x, rect.y, tab_width, rect.h, background);
        push_text(
            render,
            font,
            x + 12.0,
            rect.y + 8.0,
            label,
            [0.75, 0.79, 0.96, 1.0],
        );
    }
}

fn render_status_bar(
    render: &mut RenderState,
    font: &mut FontSystem,
    rect: Rect,
    status_text: Option<&str>,
) {
    render.batch.push_bg_quad(rect.x, rect.y, rect.w, rect.h, [0.08, 0.09, 0.13, 1.0]);
    let Some(status_text) = status_text else {
        return;
    };
    push_text(
        render,
        font,
        rect.x + 10.0,
        rect.y + 4.0,
        status_text,
        [0.54, 0.58, 0.65, 1.0],
    );
}

fn render_input_editor(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    rect: Rect,
    input: &walk_input::editor::InputRenderData,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        [
            theme.input_bg.r,
            theme.input_bg.g,
            theme.input_bg.b,
            theme.input_bg.a,
        ],
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        1.0,
        [
            theme.block_separator.r,
            theme.block_separator.g,
            theme.block_separator.b,
            0.9,
        ],
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
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                0.8,
            ],
        );
    } else {
        for (index, line) in input.lines.iter().enumerate() {
            push_text(
                render,
                font,
                base_x,
                base_y + index as f32 * font.metrics.cell_height,
                line,
                text_color,
            );
        }
    }

    if let Some((cursor_row, cursor_col)) = input.cursors.first().copied() {
        let cursor_x = base_x + cursor_col as f32 * font.metrics.cell_width;
        let cursor_y = base_y + cursor_row as f32 * font.metrics.cell_height;
        render.batch.push_bg_quad(
            cursor_x,
            cursor_y,
            2.0,
            font.metrics.cell_height,
            [
                theme.cursor.r,
                theme.cursor.g,
                theme.cursor.b,
                0.95,
            ],
        );
    }
}

fn render_search_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    search: &walk_ui::search::GlobalSearch,
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
        [
            theme.tab_bar_bg.r,
            theme.tab_bar_bg.g,
            theme.tab_bar_bg.b,
            0.96,
        ],
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        [
            theme.highlight_current_match.r,
            theme.highlight_current_match.g,
            theme.highlight_current_match.b,
            0.85,
        ],
    );

    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0,
        &format!("Search: {}", search.search_input),
        [
            theme.foreground.r,
            theme.foreground.g,
            theme.foreground.b,
            theme.foreground.a,
        ],
    );
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0 + font.metrics.cell_height,
        &search.match_count_display(),
        [
            theme.status_bar_text.r,
            theme.status_bar_text.g,
            theme.status_bar_text.b,
            theme.status_bar_text.a,
        ],
    );
}

fn search_match_at_cell(
    search: &walk_ui::search::GlobalSearch,
    absolute_row: usize,
    column: u16,
) -> Option<bool> {
    if search.matches.is_empty() {
        return None;
    }

    for (index, search_match) in search.matches.iter().enumerate() {
        if search_match.is_command || search_match.row != absolute_row {
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
    block_id: u64,
) -> Option<bool> {
    if search.matches.is_empty() {
        return None;
    }

    search
        .matches
        .iter()
        .enumerate()
        .find(|(_, search_match)| search_match.is_command && search_match.block_id == Some(block_id))
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
                render.pipeline.upload_glyph(
                    &render.gpu,
                    region.x,
                    region.y,
                    width,
                    height,
                    &data,
                );
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

fn collect_search_lines(terminal: &Terminal, blocks: &[Block]) -> Vec<SearchLine> {
    let mut lines: Vec<SearchLine> = terminal
        .state
        .text_rows()
        .into_iter()
        .map(|row| SearchLine {
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

        if let Some(current_match) = search_match_for_block_command(global_search, block.id) {
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

fn shell_quote_path(path: &str) -> String {
    format!("'{}'", path.replace('\'', "'\"'\"'"))
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
    match action {
        "new_tab" => Some(Action::NewTab),
        "close_tab" => Some(Action::CloseTab),
        "next_tab" => Some(Action::NextTab),
        "prev_tab" => Some(Action::PrevTab),
        "split_vertical" => Some(Action::SplitVertical),
        "split_horizontal" => Some(Action::SplitHorizontal),
        "close_split" => Some(Action::CloseSplit),
        "focus_left" => Some(Action::FocusLeft),
        "focus_right" => Some(Action::FocusRight),
        "focus_up" => Some(Action::FocusUp),
        "focus_down" => Some(Action::FocusDown),
        "search_global" => Some(Action::SearchGlobal),
        "block_prev" => Some(Action::BlockPrev),
        "block_next" => Some(Action::BlockNext),
        "block_copy" => Some(Action::BlockCopy),
        "block_collapse" => Some(Action::BlockCollapse),
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
        config.shell = match shell.as_str() {
            "bash" => ShellType::Bash,
            "zsh" => ShellType::Zsh,
            "fish" => ShellType::Fish,
            "powershell" => ShellType::PowerShell,
            _ => config.shell,
        };
    }

    if let Some(ref dir) = cli.working_dir {
        std::env::set_current_dir(dir)?;
    }

    let handler = WalkHandler::new(config);

    let window_config = WindowConfig {
        title: cli.title,
        ..WindowConfig::default()
    };

    run_event_loop(window_config, handler)?;
    Ok(())
}
