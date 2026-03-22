//! Walk terminal emulator entry point.

use std::collections::HashMap;
use std::error::Error;
use std::sync::Arc;

use clap::Parser;
use tracing::{info, warn};
use walk_app::app::WalkApp;
use walk_app::config::WalkConfig;
use walk_app::event_loop::run_event_loop;
use walk_app::handler::AppHandler;
use walk_app::input::{InputEvent, KeyAction};
use walk_app::keybindings::Action;
use walk_app::window::WindowConfig;
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
use walk_ui::selection::{CellPos, SelectionState};
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

/// Walk application handler.
struct WalkHandler {
    app: WalkApp,
    font: FontSystem,
    terminal: Option<Terminal>,
    render: Option<RenderState>,
    window: Option<Arc<Window>>,
    ui_rects: UiRects,
    cols: u16,
    rows: u16,
    needs_redraw: bool,
}

impl WalkHandler {
    fn new(config: WalkConfig) -> Self {
        let app = WalkApp::new(config);
        let font = FontSystem::new(&app.config.font_family, app.zoom.current_size());

        Self {
            app,
            font,
            terminal: None,
            render: None,
            window: None,
            ui_rects: UiRects::default(),
            cols: 80,
            rows: 24,
            needs_redraw: true,
        }
    }

    fn spawn_terminal(&mut self) {
        let env = HashMap::new();
        match Terminal::new(
            &self.app.config.shell,
            self.cols,
            self.rows,
            self.app.config.scrollback_lines,
            env,
        ) {
            Ok(term) => {
                info!(
                    "terminal spawned: {} ({}x{})",
                    self.app.config.shell, self.cols, self.rows
                );
                self.terminal = Some(term);
            }
            Err(e) => {
                warn!("failed to spawn terminal: {e}");
            }
        }
    }

    fn build_quads(&mut self) {
        let render = match self.render.as_mut() {
            Some(r) => r,
            None => return,
        };
        let terminal = match self.terminal.as_ref() {
            Some(t) => t,
            None => return,
        };

        render.batch.clear();

        let cw = self.font.metrics.cell_width;
        let ch = self.font.metrics.cell_height;
        let visible_rows = terminal.state.visible_rows();
        let total_cols = terminal.state.columns();
        let (cursor_col, _) = terminal.state.cursor_position();
        let cursor_row = terminal.state.absolute_cursor_row();
        let row_positions = build_visible_row_positions(&visible_rows, &self.app.block_manager.blocks);
        let viewport = self.ui_rects.viewport;
        let selected_block_id = self
            .app
            .block_navigator
            .selected_block(&self.app.block_manager)
            .map(|block| block.id);

        for (row_idx, absolute_row) in visible_rows.iter().copied().enumerate() {
            let Some(render_row) = row_positions.get(row_idx).and_then(|row| *row) else {
                continue;
            };
            for col_idx in 0..total_cols {
                let cell = terminal.state.cell_at_absolute(absolute_row, col_idx);

                let x = viewport.x + col_idx as f32 * cw;
                let y = viewport.y + render_row as f32 * ch;

                let mut bg = resolve_cell_color(&cell.bg, &self.app.theme, true);
                let mut fg = resolve_cell_color(&cell.fg, &self.app.theme, false);

                if cell.is_inverse {
                    std::mem::swap(&mut bg, &mut fg);
                }

                // Push background quad
                render.batch.push_bg_quad(x, y, cw, ch, bg);

                // Push character glyph
                let c = cell.character;
                if c != ' ' && c != '\0' {
                    let glyph_key = walk_renderer::atlas::GlyphKey {
                        font_id: 0,
                        glyph_id: c as u32,
                        font_size_tenths: (self.font.font_size * 10.0) as u32,
                    };
                    // Try to get cached atlas region, or rasterize and upload
                    if let Some(glyph) = self.font.rasterize(c) {
                        let gw = glyph.width;
                        let gh = glyph.height;
                        let data = glyph.data.clone();
                        let ox = glyph.offset_x;
                        let oy = glyph.offset_y;
                        if let Some(region) = render.atlas.get_or_insert(glyph_key, gw, gh) {
                            // Upload glyph bitmap to atlas texture (only on first insert)
                            if gw > 0 && gh > 0 {
                                render.pipeline.upload_glyph(
                                    &render.gpu,
                                    region.x,
                                    region.y,
                                    gw,
                                    gh,
                                    &data,
                                );
                            }
                            // Draw textured glyph quad
                            let glyph_x = x + ox as f32;
                            let glyph_y = y + (self.font.metrics.baseline - oy as f32);
                            render.batch.push_glyph_quad(
                                glyph_x, glyph_y, gw as f32, gh as f32, &region, fg,
                            );
                        }
                    }
                }
            }
        }

        push_block_decorations(
            &mut render.batch,
            &self.app.theme,
            &self.app.block_manager.blocks,
            selected_block_id,
            &visible_rows,
            &row_positions,
            total_cols,
            viewport.x,
            viewport.y,
            cw,
            ch,
        );

        if !self.app.input_editor.is_active {
            let cursor_x = viewport.x + cursor_col as f32 * cw;
            let cursor_row = visible_rows
                .iter()
                .position(|row| *row == cursor_row)
                .and_then(|idx| row_positions.get(idx))
                .and_then(|row| *row)
                .unwrap_or_else(|| visible_rows.len().saturating_sub(1));
            let cursor_y = viewport.y + cursor_row as f32 * ch;
            let cursor_color = [
                self.app.theme.cursor.r,
                self.app.theme.cursor.g,
                self.app.theme.cursor.b,
                0.7,
            ];
            render
                .batch
                .push_bg_quad(cursor_x, cursor_y, cw, ch, cursor_color);
        }

        render_input_editor(
            render,
            &mut self.font,
            &self.app.theme,
            self.ui_rects.input,
            &self.app.input_editor.render_data(),
        );
    }

    fn send_to_pty(&mut self, data: &[u8]) {
        if let Some(ref terminal) = self.terminal {
            if let Err(e) = terminal.send_input(data) {
                warn!("failed to send to PTY: {e}");
            }
        }
    }

    fn handle_semantic_events(&mut self, events: Vec<SemanticEvent>) {
        for event in events {
            if let SemanticEvent::TitleChanged(title) = &event {
                if let Some(window) = &self.window {
                    window.set_title(title);
                }
            }
            self.app.handle_semantic_event(&event);
        }
    }

    fn handle_action(&mut self, action: Action) {
        match action {
            Action::Copy => {
                if let Some(text) = self.selection_text() {
                    let _ = self.app.clipboard.copy(&text);
                }
            }
            Action::BlockCopy => {
                if let Some(text) = self.selected_block_text() {
                    let _ = self.app.clipboard.copy(&text);
                }
            }
            Action::SearchGlobal | Action::BlockSearch | Action::SearchInBlock => {
                self.app.global_search.activate();
                self.refresh_global_search();
            }
            other => {
                let previous_zoom = self.app.zoom.current_size();
                if let Some(data) = self.app.handle_action(&other) {
                    self.send_to_pty(&data);
                }
                if (self.app.zoom.current_size() - previous_zoom).abs() > f32::EPSILON {
                    self.apply_zoom();
                }
            }
        }

        self.needs_redraw = true;
    }

    fn handle_search_input(&mut self, event: &InputEvent) -> bool {
        if !self.app.global_search.is_active {
            return false;
        }

        match &event.action {
            KeyAction::Escape => self.app.global_search.deactivate(),
            KeyAction::Enter | KeyAction::ArrowDown => {
                self.app.global_search.next_match();
            }
            KeyAction::ArrowUp => {
                self.app.global_search.prev_match();
            }
            KeyAction::Backspace
                if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                self.app.global_search.search_input.pop();
                self.refresh_global_search();
            }
            KeyAction::Char(ch)
                if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
            {
                self.app.global_search.search_input.push(*ch);
                self.refresh_global_search();
            }
            _ => {}
        }

        self.needs_redraw = true;
        true
    }

    fn handle_editor_input(&mut self, event: &InputEvent) -> bool {
        let Some(editor_key) = input_event_to_editor_key(event) else {
            return false;
        };

        match self.app.input_editor.handle_key(editor_key) {
            EditorAction::Submit(command) => {
                self.app.block_manager.set_command_text(&command);
                if !command.is_empty() {
                    self.send_to_pty(command.as_bytes());
                }
                self.send_to_pty(b"\r");
            }
            EditorAction::SendEof => {
                self.send_to_pty(b"\x04");
            }
            EditorAction::None => {}
        }

        if let Some(window) = &self.window {
            self.update_grid(window.inner_size());
        }
        self.needs_redraw = true;
        true
    }

    fn apply_zoom(&mut self) {
        let target_size = self.app.zoom.current_size();
        if (self.font.font_size - target_size).abs() <= f32::EPSILON {
            return;
        }

        self.font.set_font_size(target_size);
        if let Some(window) = &self.window {
            self.update_grid(window.inner_size());
        }
        self.needs_redraw = true;
    }

    fn update_grid(&mut self, size: PhysicalSize<u32>) {
        if size.width == 0 || size.height == 0 {
            return;
        }

        self.ui_rects = compute_ui_rects(
            size,
            self.app.input_editor.render_data().position,
            self.app.input_editor.buffer.line_count(),
            self.font.metrics.cell_height,
        );
        let (cols, rows) = self
            .font
            .grid_dimensions(self.ui_rects.viewport.w, self.ui_rects.viewport.h);
        self.cols = cols;
        self.rows = rows;

        if let Some(ref mut terminal) = self.terminal {
            if let Err(e) = terminal.resize(cols, rows) {
                warn!("failed to resize terminal: {e}");
            }
        }
    }

    fn refresh_global_search(&mut self) {
        if !self.app.global_search.is_active {
            return;
        }

        if self.app.global_search.search_input.is_empty() {
            self.app.global_search.matches.clear();
            self.app.global_search.current = 0;
            self.app.global_search.query.clear();
            return;
        }

        if let Some(terminal) = &self.terminal {
            let lines = collect_visible_lines(terminal);
            self.app
                .global_search
                .search(&self.app.global_search.search_input.clone(), &lines);
        }
    }

    fn pixel_to_cell(&self, x: f64, y: f64) -> Option<CellPos> {
        if self.cols == 0 || self.rows == 0 {
            return None;
        }

        let viewport = self.ui_rects.viewport;
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
            .clamp(0, i64::from(self.cols.saturating_sub(1))) as u16;
        let row = ((local_y / f64::from(self.font.metrics.cell_height)).floor() as i64)
            .clamp(0, i64::from(self.rows.saturating_sub(1))) as u16;

        Some(CellPos { row, col })
    }

    fn selection_text(&self) -> Option<String> {
        let (start, end) = self.app.selection.selection_range()?;
        let terminal = self.terminal.as_ref()?;
        Some(extract_selection_text(terminal, start, end))
    }

    fn selected_block_text(&self) -> Option<String> {
        let selected = self
            .app
            .block_navigator
            .selected_block(&self.app.block_manager)?;
        let terminal = self.terminal.as_ref()?;
        Some(extract_block_text(terminal, selected))
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

        // Spawn the terminal
        self.spawn_terminal();
        self.needs_redraw = true;

        info!("GPU initialized, grid: {}x{}", self.cols, self.rows);
    }

    fn on_frame_tick(&mut self) -> bool {
        if let Some(ref mut terminal) = self.terminal {
            terminal.process_pty_output();
            let semantic_events = terminal.drain_semantic_events();
            let is_dirty = terminal.is_dirty();
            self.handle_semantic_events(semantic_events);
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
        if let Some(ref mut render) = self.render {
            let clear = [
                self.app.theme.background.r,
                self.app.theme.background.g,
                self.app.theme.background.b,
                self.app.theme.background.a,
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

        if let Some(ref mut terminal) = self.terminal {
            terminal.mark_clean();
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
        if let Some(action) = self.app.resolve_action(&event) {
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
                    self.app.selection.handle_mouse_down(cell);
                    self.needs_redraw = true;
                }
            }
            walk_app::input::MouseEvent::Release {
                button: MouseButton::Left,
                ..
            } => {
                let was_selecting =
                    matches!(self.app.selection.state, SelectionState::Selecting { .. });
                self.app.selection.handle_mouse_up();
                if was_selecting && self.app.config.copy_on_select {
                    if let Some(text) = self.selection_text() {
                        let _ = self.app.clipboard.copy(&text);
                    }
                }
                self.needs_redraw = true;
            }
            walk_app::input::MouseEvent::Move { x, y } => {
                if matches!(self.app.selection.state, SelectionState::Selecting { .. }) {
                    if let Some(cell) = self.pixel_to_cell(x, y) {
                        self.app.selection.handle_mouse_drag(cell);
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
        info!("walk closing");
    }
}

fn compute_ui_rects(
    size: PhysicalSize<u32>,
    input_position: walk_input::editor::InputPosition,
    input_lines: usize,
    cell_height: f32,
) -> UiRects {
    let width = size.width as f32;
    let height = size.height as f32;
    let line_count = input_lines.max(1).min(8) as f32;
    let input_height = (line_count * cell_height + 20.0).min((height * 0.45).max(cell_height));

    match input_position {
        walk_input::editor::InputPosition::Top => UiRects {
            viewport: Rect::new(0.0, input_height, width, (height - input_height).max(cell_height)),
            input: Rect::new(0.0, 0.0, width, input_height),
        },
        walk_input::editor::InputPosition::Bottom => UiRects {
            viewport: Rect::new(0.0, 0.0, width, (height - input_height).max(cell_height)),
            input: Rect::new(0.0, height - input_height, width, input_height),
        },
    }
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

fn collect_visible_lines(terminal: &Terminal) -> Vec<(i64, String)> {
    terminal
        .state
        .visible_rows()
        .into_iter()
        .map(|row| (row as i64, terminal.state.row_text(row)))
        .collect()
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
