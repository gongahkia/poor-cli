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
use walk_blocks::block::Block;
use walk_input::editor::{EditorAction, EditorKey};
use walk_terminal::state::CellColor;
use walk_terminal::terminal::SemanticEvent;
use walk_app::window::WindowConfig;
use walk_renderer::atlas::GlyphAtlas;
use walk_renderer::font::FontSystem;
use walk_renderer::gpu::GpuContext;
use walk_renderer::pipeline::QuadBatch;
use walk_renderer::render_pipeline::TerminalRenderPipeline;
use walk_terminal::shell::ShellType;
use walk_terminal::terminal::Terminal;
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

/// Walk application handler.
struct WalkHandler {
    app: WalkApp,
    font: FontSystem,
    terminal: Option<Terminal>,
    render: Option<RenderState>,
    window: Option<Arc<Window>>,
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
                    self.app.config.shell,
                    self.cols,
                    self.rows
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
        let total_lines = terminal.state.screen_lines();
        let total_cols = terminal.state.columns();
        let (cursor_col, cursor_row) = terminal.state.cursor_position();

        for row_idx in 0..total_lines {
            for col_idx in 0..total_cols {
                let cell = terminal.state.cell_at(row_idx, col_idx);

                let x = col_idx as f32 * cw;
                let y = row_idx as f32 * ch;

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
                                glyph_x,
                                glyph_y,
                                gw as f32,
                                gh as f32,
                                &region,
                                fg,
                            );
                        }
                    }
                }
            }
        }

        // Draw cursor
        let cursor_x = cursor_col as f32 * cw;
        let cursor_y = cursor_row as f32 * ch;
        let cursor_color = [
            self.app.theme.cursor.r,
            self.app.theme.cursor.g,
            self.app.theme.cursor.b,
            0.7,
        ];
        render.batch.push_bg_quad(cursor_x, cursor_y, cw, ch, cursor_color);
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
                self.send_to_pty(b"\r");
            }
            EditorAction::SendEof => {
                self.send_to_pty(b"\x04");
            }
            EditorAction::None => {
                if let Some(data) = input_event_to_pty_bytes(event) {
                    self.send_to_pty(&data);
                }
            }
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

        let (cols, rows) = self
            .font
            .grid_dimensions(size.width as f32, size.height as f32);
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

        let col = ((x / f64::from(self.font.metrics.cell_width)).floor() as i64)
            .clamp(0, i64::from(self.cols.saturating_sub(1))) as u16;
        let row = ((y / f64::from(self.font.metrics.cell_height)).floor() as i64)
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
            if let Err(e) = render.pipeline.render_frame(
                &render.gpu,
                &render.surface,
                &render.batch,
                clear,
            ) {
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
            render.gpu.resize(&render.surface, new_size.width, new_size.height);
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
                let was_selecting = matches!(self.app.selection.state, SelectionState::Selecting { .. });
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

fn input_event_to_editor_key(event: &InputEvent) -> Option<EditorKey> {
    match &event.action {
        KeyAction::Char(ch)
            if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
        {
            Some(EditorKey::Char(*ch))
        }
        KeyAction::Char('d') if event.modifiers.ctrl && !event.modifiers.alt => Some(EditorKey::CtrlD),
        KeyAction::Enter => Some(EditorKey::Enter),
        KeyAction::Backspace => Some(EditorKey::Backspace),
        KeyAction::Delete => Some(EditorKey::Delete),
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
    (0..terminal.state.screen_lines())
        .map(|row| (row as i64, terminal_row_text(terminal, row)))
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
        lines.push(terminal_row_slice(terminal, row, row_start, row_end));
    }

    lines.join("\n")
}

fn extract_block_text(terminal: &Terminal, block: &Block) -> String {
    let total_rows = terminal.state.screen_lines();
    if total_rows == 0 {
        return block.command_text.clone();
    }

    let max_row = total_rows.saturating_sub(1);
    let start_row = block.output_start_line.min(max_row);
    let end_row = block.output_end_line.min(max_row);
    let mut lines = Vec::new();

    if !block.command_text.is_empty() {
        lines.push(block.command_text.clone());
    }

    for row in start_row..=end_row {
        lines.push(terminal_row_text(terminal, row));
    }

    lines.join("\n")
}

fn selection_end_col(terminal: &Terminal, end_col: u16) -> usize {
    if end_col == u16::MAX {
        terminal.state.columns()
    } else {
        (usize::from(end_col) + 1).min(terminal.state.columns())
    }
}

fn terminal_row_text(terminal: &Terminal, row: usize) -> String {
    terminal_row_slice(terminal, row, 0, terminal.state.columns())
        .trim_end_matches(' ')
        .to_string()
}

fn terminal_row_slice(terminal: &Terminal, row: usize, start_col: usize, end_col: usize) -> String {
    let end_col = end_col.min(terminal.state.columns());
    let mut text = String::new();

    for col in start_col..end_col {
        let ch = terminal.state.cell_at(row, col).character;
        text.push(if ch == '\0' { ' ' } else { ch });
    }

    text
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
                [theme.background.r, theme.background.g, theme.background.b, theme.background.a]
            } else {
                [theme.foreground.r, theme.foreground.g, theme.foreground.b, theme.foreground.a]
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
            tracing_subscriber::EnvFilter::try_from_default_env().unwrap_or_else(|_| {
                if cfg!(debug_assertions) {
                    "warn".into()
                } else {
                    "warn".into()
                }
            }),
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
