//! Walk terminal emulator entry point.

use std::collections::HashMap;
use std::error::Error;
use std::sync::Arc;

use clap::Parser;
use tracing::{info, warn};
use walk_app::config::WalkConfig;
use walk_app::event_loop::run_event_loop;
use walk_app::handler::AppHandler;
use walk_app::input::{InputEvent, KeyAction};
use walk_terminal::state::CellColor;
use walk_app::window::WindowConfig;
use walk_renderer::atlas::GlyphAtlas;
use walk_renderer::font::FontSystem;
use walk_renderer::gpu::GpuContext;
use walk_renderer::pipeline::QuadBatch;
use walk_renderer::render_pipeline::TerminalRenderPipeline;
use walk_terminal::shell::ShellType;
use walk_terminal::terminal::Terminal;
use walk_ui::theme::Theme;
use winit::dpi::PhysicalSize;
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
    config: WalkConfig,
    theme: Theme,
    font: FontSystem,
    terminal: Option<Terminal>,
    render: Option<RenderState>,
    window: Option<Arc<Window>>,
    cols: u16,
    rows: u16,
}

impl WalkHandler {
    fn new(config: WalkConfig) -> Self {
        let theme = Theme::default();
        let font = FontSystem::new(&config.font_family, config.font_size);

        Self {
            config,
            theme,
            font,
            terminal: None,
            render: None,
            window: None,
            cols: 80,
            rows: 24,
        }
    }

    fn spawn_terminal(&mut self) {
        let env = HashMap::new();
        match Terminal::new(
            &self.config.shell,
            self.cols,
            self.rows,
            self.config.scrollback_lines,
            env,
        ) {
            Ok(term) => {
                info!("terminal spawned: {} ({}x{})", self.config.shell, self.cols, self.rows);
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

                let mut bg = resolve_cell_color(&cell.bg, &self.theme, true);
                let mut fg = resolve_cell_color(&cell.fg, &self.theme, false);

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
            self.theme.cursor.r,
            self.theme.cursor.g,
            self.theme.cursor.b,
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
        let (cols, rows) = self.font.grid_dimensions(size.width as f32, size.height as f32);
        self.cols = cols;
        self.rows = rows;

        // Spawn the terminal
        self.spawn_terminal();

        info!("GPU initialized, grid: {}x{}", cols, rows);
    }

    fn on_redraw(&mut self) {
        // Process PTY output
        if let Some(ref mut terminal) = self.terminal {
            terminal.process_pty_output();
        }

        // Build vertex data from terminal grid
        self.build_quads();

        // Render
        if let Some(ref mut render) = self.render {
            let clear = [
                self.theme.background.r,
                self.theme.background.g,
                self.theme.background.b,
                self.theme.background.a,
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
    }

    fn on_resize(&mut self, new_size: PhysicalSize<u32>) {
        if new_size.width == 0 || new_size.height == 0 {
            return;
        }

        if let Some(ref mut render) = self.render {
            render.gpu.resize(&render.surface, new_size.width, new_size.height);
        }

        let (cols, rows) = self.font.grid_dimensions(new_size.width as f32, new_size.height as f32);
        self.cols = cols;
        self.rows = rows;

        if let Some(ref mut terminal) = self.terminal {
            terminal.resize(cols, rows);
        }
    }

    fn on_key_event(&mut self, event: InputEvent) {
        // Convert key events to byte sequences for the PTY
        let bytes: Option<Vec<u8>> = match &event.action {
            KeyAction::Char(c) => {
                if event.modifiers.ctrl && !event.modifiers.alt {
                    // Ctrl+letter -> control character
                    let b = c.to_ascii_lowercase() as u8;
                    if b >= b'a' && b <= b'z' {
                        Some(vec![b - b'a' + 1])
                    } else {
                        Some(c.to_string().into_bytes())
                    }
                } else if event.modifiers.alt && !event.modifiers.ctrl {
                    // Alt+letter -> ESC prefix
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
        };

        if let Some(data) = bytes {
            self.send_to_pty(&data);
        }
    }

    fn on_close_requested(&mut self) {
        info!("walk closing");
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
