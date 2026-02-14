mod lang;
mod model;
mod eval;
mod layout;
mod tui;
mod render;
mod cli;

use clap::Parser;
use std::path::Path;

use cli::commands::{Cli, Commands};
use lang::reader::read_chron_file;
use lang::parser::parse_program;
use eval::evaluator::Evaluator;
use layout::engine::compute_layout;
use render::svg_render::{render_svg, Theme};
use tui::app::App;

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Run { file } => run_tui(&file, cli.verbose),
        Commands::Export { file, format, output, width, height, time_range } => {
            run_export(&file, &format, output.as_deref(), cli.verbose);
        }
        Commands::Check { file } => run_check(&file, cli.verbose),
        Commands::Import { file, from, output } => {
            eprintln!("import not yet implemented");
            std::process::exit(1);
        }
        Commands::Serve { file, port } => {
            eprintln!("serve not yet implemented");
            std::process::exit(1);
        }
    }
}

/// Run subcommand: parse → eval → layout → TUI (Task 99)
fn run_tui(file: &Path, verbose: bool) {
    let source = match read_chron_file(file) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Error: {}", e);
            std::process::exit(1);
        }
    };

    let file_str = file.to_string_lossy().to_string();
    let program = match parse_program(&source, &file_str) {
        Ok(p) => p,
        Err(errors) => {
            for e in &errors {
                eprintln!("Parse error: {}", e);
            }
            std::process::exit(1);
        }
    };

    if verbose {
        eprintln!("Parsed {} statements", program.len());
    }

    let mut evaluator = Evaluator::new();
    if let Err(e) = evaluator.eval_program(&program) {
        eprintln!("Runtime error: {}", e);
        std::process::exit(1);
    }

    if verbose {
        eprintln!("World: {} timelines, {} entities, {} relationships",
            evaluator.world.timelines.len(),
            evaluator.world.entities.len(),
            evaluator.world.relationships.len(),
        );
    }

    let layout = compute_layout(&evaluator.world);
    let app = App::new(layout, file.to_string_lossy().to_string());

    // Init terminal and run TUI
    if let Err(e) = run_tui_loop(app) {
        eprintln!("TUI error: {}", e);
        std::process::exit(1);
    }
}

fn run_tui_loop(mut app: App) -> Result<(), Box<dyn std::error::Error>> {
    use crossterm::{
        event::{self, Event, EnableMouseCapture, DisableMouseCapture},
        terminal::{enable_raw_mode, disable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
        execute,
    };
    use ratatui::prelude::*;
    use std::time::Duration;

    enable_raw_mode()?;
    let mut stdout = std::io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    loop {
        terminal.draw(|frame| {
            tui::ui::draw(frame, &app);
        })?;

        if event::poll(Duration::from_millis(100))? {
            match event::read()? {
                Event::Key(key) => {
                    app.handle_key(key);
                    if app.should_quit { break; }
                }
                Event::Mouse(mouse) => {
                    app.handle_mouse(mouse);
                }
                _ => {}
            }
        }
        app.tick();
    }

    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, DisableMouseCapture)?;
    Ok(())
}

fn run_export(file: &Path, format: &str, output: Option<&Path>, verbose: bool) {
    let source = match read_chron_file(file) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Error: {}", e);
            std::process::exit(1);
        }
    };

    let file_str = file.to_string_lossy().to_string();
    let program = match parse_program(&source, &file_str) {
        Ok(p) => p,
        Err(errors) => {
            for e in &errors {
                eprintln!("Parse error: {}", e);
            }
            std::process::exit(1);
        }
    };

    let mut evaluator = Evaluator::new();
    if let Err(e) = evaluator.eval_program(&program) {
        eprintln!("Runtime error: {}", e);
        std::process::exit(1);
    }

    let layout = compute_layout(&evaluator.world);
    let theme = Theme::default();

    match format {
        "svg" => {
            let svg = render_svg(&layout, &theme);
            let out_path = output.unwrap_or(Path::new("output.svg"));
            std::fs::write(out_path, &svg).expect("failed to write SVG");
            if verbose {
                eprintln!("Exported SVG to {}", out_path.display());
            }
        }
        _ => {
            eprintln!("Unsupported export format: {}. Use: svg", format);
            std::process::exit(1);
        }
    }
}

fn run_check(file: &Path, verbose: bool) {
    let source = match read_chron_file(file) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Error: {}", e);
            std::process::exit(1);
        }
    };

    let file_str = file.to_string_lossy().to_string();
    let program = match parse_program(&source, &file_str) {
        Ok(p) => p,
        Err(errors) => {
            for e in &errors {
                eprintln!("Parse error: {}", e);
            }
            std::process::exit(1);
        }
    };

    let mut evaluator = Evaluator::new();
    if let Err(e) = evaluator.eval_program(&program) {
        eprintln!("Validation error: {}", e);
        std::process::exit(1);
    }

    let w = &evaluator.world;
    println!("✓ {} valid ({} timelines, {} entities, {} relationships)",
        file.display(), w.timelines.len(), w.entities.len(), w.relationships.len());
}
