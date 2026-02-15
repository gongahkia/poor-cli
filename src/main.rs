mod lang;
mod model;
mod eval;
mod layout;
mod tui;
mod render;
mod cli;
mod import;
mod config;
mod web;
mod ext;
mod embed;
mod tooling;

use clap::Parser;
use std::path::Path;

use cli::commands::{Cli, Commands};
use lang::reader::read_seuss_file;
use lang::parser::parse_program;
use eval::evaluator::Evaluator;
use layout::engine::compute_layout;
use render::svg_render::{render_svg, Theme};
use tui::app::App;
use config::loader::SeussConfig;

fn main() {
    let cli = Cli::parse();

    // Wire config file loading: load and merge with CLI args
    let cfg = SeussConfig::load(cli.config.as_deref());

    // Wire --verbose to structured logging
    if cli.verbose {
        std::env::set_var("RUST_LOG", "debug");
    }

    // Wire --theme CLI flag to Theme selection
    let svg_theme = resolve_svg_theme(cli.theme.as_deref(), &cfg);

    match cli.command {
        Commands::Run { file } => run_tui(&file, cli.verbose),
        Commands::Export { file, format, output, width, height, time_range, dpi } => {
            let effective_dpi = if dpi == 150 { cfg.export.as_ref().and_then(|e| e.default_dpi).unwrap_or(dpi) } else { dpi };
            let effective_width = width.or_else(|| cfg.export.as_ref().and_then(|e| e.default_width));
            let effective_height = height.or_else(|| cfg.export.as_ref().and_then(|e| e.default_height));
            let effective_format = if format == "svg" {
                cfg.export.as_ref().and_then(|e| e.default_format.clone()).unwrap_or(format)
            } else { format };
            run_export(&file, &effective_format, output.as_deref(), effective_width, effective_height, time_range.as_deref(), effective_dpi, &svg_theme, cli.verbose);
        }
        Commands::Check { file } => run_check(&file, cli.verbose),
        Commands::Import { file, from, output } => {
            run_import(&file, &from, output.as_deref());
        }
        Commands::Serve { file, port } => {
            run_serve(&file, port, cli.verbose);
        }
        Commands::Repl => run_repl(),
        Commands::Diff { file1, file2 } => run_diff(&file1, &file2),
    }
}

/// Resolve SVG theme from --theme flag or config file
fn resolve_svg_theme(theme_flag: Option<&str>, cfg: &SeussConfig) -> Theme {
    match theme_flag {
        Some("dark") | None => {
            // Apply config theme overrides if present
            if let Some(ref tc) = cfg.theme {
                let tui = tc.to_tui_theme();
                let mut theme = Theme::default();
                // Transfer any custom entity colors from config
                for (k, v) in &tui.entity_colors {
                    let hex = ratatui_color_to_hex(*v);
                    theme.entity_colors.insert(k.clone(), hex);
                }
                theme
            } else {
                Theme::default()
            }
        }
        Some("light") => {
            let mut theme = Theme::default();
            theme.bg = "#f5f5f5".into();
            theme.text = "#1a1a1a".into();
            theme.timeline_bg = "#e0e0e0".into();
            theme
        }
        Some(path) => {
            // Try loading custom theme from TOML path
            if let Ok(content) = std::fs::read_to_string(path) {
                if let Ok(tc) = toml::from_str::<config::theme::ThemeConfig>(&content) {
                    let tui = tc.to_tui_theme();
                    let mut theme = Theme::default();
                    for (k, v) in &tui.entity_colors {
                        theme.entity_colors.insert(k.clone(), ratatui_color_to_hex(*v));
                    }
                    return theme;
                }
            }
            eprintln!("Warning: could not load theme '{}', using default", path);
            Theme::default()
        }
    }
}

fn ratatui_color_to_hex(c: ratatui::style::Color) -> String {
    match c {
        ratatui::style::Color::Rgb(r, g, b) => format!("#{:02x}{:02x}{:02x}", r, g, b),
        ratatui::style::Color::Blue => "#4a9eff".into(),
        ratatui::style::Color::Red => "#ff4a4a".into(),
        ratatui::style::Color::Green => "#4aff4a".into(),
        ratatui::style::Color::Magenta => "#ff4aff".into(),
        ratatui::style::Color::Cyan => "#4affff".into(),
        ratatui::style::Color::Yellow => "#ffcc00".into(),
        _ => "#888888".into(),
    }
}

/// Run subcommand: parse → eval → layout → TUI (Task 99)
fn run_tui(file: &Path, verbose: bool) {
    let source = match read_seuss_file(file) {
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

fn run_export(file: &Path, format: &str, output: Option<&Path>, width: Option<u32>, height: Option<u32>, time_range: Option<&str>, dpi: u32, theme: &Theme, verbose: bool) {
    let source = match read_seuss_file(file) {
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

    let mut layout = compute_layout(&evaluator.world);
    let theme = theme.clone();

    // Time-range cropping (Task 16)
    if let Some(tr) = time_range {
        if let Some((start_str, end_str)) = tr.split_once("..") {
            if let (Ok(s), Ok(e)) = (start_str.parse::<f64>(), end_str.parse::<f64>()) {
                layout.viewport.time_start = s;
                layout.viewport.time_end = e;
            }
        }
    }

    // Configurable dimensions (Task 15)
    let export_width = width.unwrap_or(layout.total_width.max(800.0) as u32);
    let export_height = match (width, height) {
        (_, Some(h)) => h,
        (Some(w), None) => {
            let aspect = layout.total_lanes as f64 * 40.0 / layout.total_width.max(1.0);
            (w as f64 * aspect) as u32
        }
        _ => (layout.total_lanes as u32) * 40,
    };

    match format {
        "svg" => {
            let svg = render_svg(&layout, &theme);
            let out_path = output.unwrap_or(Path::new("output.svg"));
            std::fs::write(out_path, &svg).expect("failed to write SVG");
            if verbose {
                eprintln!("Exported SVG to {}", out_path.display());
            }
        }
        "png" => {
            let svg = render_svg(&layout, &theme);
            let out_path = output.unwrap_or(Path::new("output.png"));
            if let Err(e) = render::png_render::render_png(&svg, out_path, dpi) {
                eprintln!("PNG export error: {}", e);
                std::process::exit(1);
            }
            if verbose {
                eprintln!("Exported PNG to {}", out_path.display());
            }
        }
        "pdf" => {
            let svg = render_svg(&layout, &theme);
            let out_path = output.unwrap_or(Path::new("output.pdf"));
            let w = layout.total_width as f32 * 0.264; // px to mm approx
            let h = (layout.total_lanes as f32) * 10.0; // 10mm per lane
            if let Err(e) = render::pdf_render::render_pdf(&svg, out_path, w.max(210.0), h.max(297.0)) {
                eprintln!("PDF export error: {}", e);
                std::process::exit(1);
            }
            if verbose {
                eprintln!("Exported PDF to {}", out_path.display());
            }
        }
        _ => {
            eprintln!("Unsupported export format: {}. Use: svg, png, pdf", format);
            std::process::exit(1);
        }
    }
}

fn run_check(file: &Path, verbose: bool) {
    let source = match read_seuss_file(file) {
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
    let report = eval::validator::validate(w);
    for warning in &report.warnings {
        eprintln!("warning: {}", warning);
    }
    for error in &report.errors {
        eprintln!("error: {}", error);
    }
    if !report.errors.is_empty() {
        eprintln!("{} error(s), {} warning(s)", report.errors.len(), report.warnings.len());
        std::process::exit(1);
    }
    println!("✓ {} valid ({} timelines, {} entities, {} relationships{})",
        file.display(), w.timelines.len(), w.entities.len(), w.relationships.len(),
        if report.warnings.is_empty() { String::new() } else { format!(", {} warning(s)", report.warnings.len()) });
}

fn run_import(file: &Path, from: &str, output: Option<&Path>) {
    let content = match std::fs::read_to_string(file) {
        Ok(s) => s,
        Err(e) => {
            eprintln!("Error reading {}: {}", file.display(), e);
            std::process::exit(1);
        }
    };

    let result = match from {
        "csv" | "csv-entities" => {
            import::csv_import::import_entities_csv(&content)
                .map_err(|errs| errs.iter().map(|e| e.to_string()).collect::<Vec<_>>().join("\n"))
        }
        "csv-relationships" => {
            import::csv_import::import_relationships_csv(&content)
                .map_err(|errs| errs.iter().map(|e| e.to_string()).collect::<Vec<_>>().join("\n"))
        }
        "gedcom" => {
            let records = import::gedcom::parse_gedcom(&content);
            Ok(import::gedcom::gedcom_to_seuss(&records))
        }
        "jsonld" => {
            import::jsonld::import_jsonld(&content)
        }
        _ => {
            eprintln!("Unsupported format: {}. Use: csv, csv-relationships, gedcom, jsonld", from);
            std::process::exit(1);
        }
    };

    match result {
        Ok(seuss_source) => {
            // Validate
            let validation = import::validate::validate_seuss_source(&seuss_source);
            for w in &validation.warnings {
                eprintln!("warning: {}", w);
            }
            for e in &validation.errors {
                eprintln!("error: {}", e);
            }

            let out_path = output.unwrap_or(Path::new("imported.seuss"));
            std::fs::write(out_path, &seuss_source).expect("failed to write output");
            println!("✓ Imported {} → {}", file.display(), out_path.display());
        }
        Err(e) => {
            eprintln!("Import failed:\n{}", e);
            std::process::exit(1);
        }
    }
}

fn run_serve(file: &Path, port: u16, verbose: bool) {
    let source = match read_seuss_file(file) {
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
    let svg = render_svg(&layout, &theme);

    if verbose {
        eprintln!("Starting server with {} entities on port {}", evaluator.world.entities.len(), port);
    }

    let rt = tokio::runtime::Runtime::new().expect("failed to create tokio runtime");
    rt.block_on(async {
        if let Err(e) = web::server::start_server(port, svg).await {
            eprintln!("Server error: {}", e);
            std::process::exit(1);
        }
    });
}

fn run_repl() {
    use std::io::{self, Write, BufRead};

    println!("Seuss REPL v0.1.0 — type declarations, then :world to inspect, :quit to exit");
    let mut evaluator = Evaluator::new();
    let mut line_num = 0;

    loop {
        print!("seuss> ");
        io::stdout().flush().ok();

        let mut input = String::new();
        if io::stdin().lock().read_line(&mut input).is_err() || input.is_empty() {
            break;
        }
        let trimmed = input.trim();
        if trimmed.is_empty() { continue; }

        // Meta-commands
        match trimmed {
            ":quit" | ":q" | ":exit" => break,
            ":world" | ":w" => {
                let w = &evaluator.world;
                println!("Timelines: {}", w.timelines.len());
                for tl in w.timelines.values() {
                    println!("  {} ({:?})", tl.name, tl.kind);
                }
                println!("Entities: {}", w.entities.len());
                for ent in w.entities.values() {
                    println!("  {} : {}", ent.name, ent.type_id);
                }
                println!("Relationships: {}", w.relationships.len());
                for rel in &w.relationships {
                    let src = w.entities.get(&rel.source_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
                    let tgt = w.entities.get(&rel.target_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
                    println!("  {} -[{}]-> {}", src, rel.label, tgt);
                }
                continue;
            }
            ":entities" | ":e" => {
                let w = &evaluator.world;
                if w.entities.is_empty() {
                    println!("(no entities)");
                } else {
                    println!("{:<20} {:<15} {:<15} {}", "NAME", "TYPE", "TIMELINE", "TIME_RANGE");
                    println!("{}", "-".repeat(70));
                    for ent in w.entities.values() {
                        let (tl_name, time_range) = ent.timeline_appearances.first()
                            .map(|(tid, tr)| {
                                let tl = w.timelines.get(tid).map(|t| t.name.as_str()).unwrap_or("?");
                                let range = format!("{}..{}", tr.start.to_ordinal(), tr.end.to_ordinal());
                                (tl, range)
                            })
                            .unwrap_or(("-", "-".to_string()));
                        println!("{:<20} {:<15} {:<15} {}", ent.name, ent.type_id, tl_name, time_range);
                    }
                }
                continue;
            }
            ":rels" | ":r" => {
                let w = &evaluator.world;
                if w.relationships.is_empty() {
                    println!("(no relationships)");
                } else {
                    println!("{:<15} {:<15} {:<15} {:<10} {}", "SOURCE", "LABEL", "TARGET", "DIRECTED", "SCOPE");
                    println!("{}", "-".repeat(70));
                    for rel in &w.relationships {
                        let src = w.entities.get(&rel.source_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
                        let tgt = w.entities.get(&rel.target_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
                        let dir = if rel.directed { "→" } else { "─" };
                        let scope = rel.temporal_scope.as_ref()
                            .map(|ts| format!("{}..{}", ts.start.to_ordinal(), ts.end.to_ordinal()))
                            .unwrap_or_else(|| "-".to_string());
                        println!("{:<15} {:<15} {:<15} {:<10} {}", src, rel.label, tgt, dir, scope);
                    }
                }
                continue;
            }
            ":validate" | ":v" => {
                let w = &evaluator.world;
                let report = eval::validator::validate(w);
                if report.errors.is_empty() && report.warnings.is_empty() {
                    println!("✓ No issues found");
                } else {
                    for err in &report.errors {
                        println!("ERROR: {}", err);
                    }
                    for warn in &report.warnings {
                        println!("WARN: {}", warn);
                    }
                    println!("Total: {} errors, {} warnings", report.errors.len(), report.warnings.len());
                }
                continue;
            }
            ":timeline" | ":t" => {
                // ASCII mini-timeline
                let w = &evaluator.world;
                if w.entities.is_empty() {
                    println!("(no entities)");
                } else {
                    let layout = compute_layout(w);
                    let width = 60;
                    let time_range = layout.viewport.time_end - layout.viewport.time_start;
                    if time_range > 0.0 {
                        for ent in &layout.entities {
                            let start = ((ent.x_start - layout.viewport.time_start) / time_range * width as f64) as usize;
                            let end = ((ent.x_end - layout.viewport.time_start) / time_range * width as f64) as usize;
                            let bar_start = start.min(width);
                            let bar_len = end.saturating_sub(start).max(1).min(width - bar_start);
                            println!("{:>15} |{}{}|",
                                ent.name,
                                " ".repeat(bar_start),
                                "█".repeat(bar_len),
                            );
                        }
                    }
                }
                continue;
            }
            _ => {}
        }

        line_num += 1;
        let file_str = format!("repl:{}", line_num);
        match parse_program(trimmed, &file_str) {
            Ok(program) => {
                match evaluator.eval_program(&program) {
                    Ok(_) => println!("ok"),
                    Err(e) => eprintln!("error: {}", e),
                }
            }
            Err(errors) => {
                // Improved error recovery: show line numbers relative to input block
                let input_lines: Vec<&str> = trimmed.lines().collect();
                for e in &errors {
                    let err_str = e.to_string();
                    eprintln!("parse error: {}", err_str);
                }
                if input_lines.len() > 1 {
                    eprintln!("  (multi-line input had {} lines, re-enter to try again)", input_lines.len());
                    for (i, line) in input_lines.iter().enumerate() {
                        eprintln!("  {:>3} | {}", i + 1, line);
                    }
                }
            }
        }
    }
}

fn run_diff(file1: &Path, file2: &Path) {
    use crossterm::style::{Stylize};

    fn load_world(file: &Path) -> Result<crate::model::world::World, String> {
        let source = read_seuss_file(file).map_err(|e| format!("{}", e))?;
        let file_str = file.to_string_lossy().to_string();
        let program = parse_program(&source, &file_str)
            .map_err(|errors| errors.iter().map(|e| e.to_string()).collect::<Vec<_>>().join("; "))?;
        let mut evaluator = Evaluator::new();
        evaluator.eval_program(&program).map_err(|e| e.to_string())?;
        Ok(evaluator.world)
    }

    let is_tty = std::io::IsTerminal::is_terminal(&std::io::stdout());

    fn print_added(msg: &str, is_tty: bool) {
        if is_tty {
            use crossterm::style::Stylize;
            println!("{}", format!("+ {}", msg).green());
        } else {
            println!("+ {}", msg);
        }
    }
    fn print_removed(msg: &str, is_tty: bool) {
        if is_tty {
            use crossterm::style::Stylize;
            println!("{}", format!("- {}", msg).red());
        } else {
            println!("- {}", msg);
        }
    }
    fn print_changed(msg: &str, is_tty: bool) {
        if is_tty {
            use crossterm::style::Stylize;
            println!("{}", format!("~ {}", msg).yellow());
        } else {
            println!("~ {}", msg);
        }
    }

    let w1 = match load_world(file1) {
        Ok(w) => w,
        Err(e) => { eprintln!("Error in {}: {}", file1.display(), e); std::process::exit(1); }
    };
    let w2 = match load_world(file2) {
        Ok(w) => w,
        Err(e) => { eprintln!("Error in {}: {}", file2.display(), e); std::process::exit(1); }
    };

    let mut changes = 0;

    // Compare timelines
    let names1: std::collections::HashSet<_> = w1.timelines.values().map(|t| &t.name).collect();
    let names2: std::collections::HashSet<_> = w2.timelines.values().map(|t| &t.name).collect();
    for name in names2.difference(&names1) {
        print_added(&format!("timeline {}", name), is_tty);
        changes += 1;
    }
    for name in names1.difference(&names2) {
        print_removed(&format!("timeline {}", name), is_tty);
        changes += 1;
    }

    // Compare entities
    let ents1: std::collections::HashMap<_, _> = w1.entities.values().map(|e| (&e.name, e)).collect();
    let ents2: std::collections::HashMap<_, _> = w2.entities.values().map(|e| (&e.name, e)).collect();
    for (name, _) in &ents2 {
        if !ents1.contains_key(name) {
            print_added(&format!("entity {}", name), is_tty);
            changes += 1;
        }
    }
    for (name, _) in &ents1 {
        if !ents2.contains_key(name) {
            print_removed(&format!("entity {}", name), is_tty);
            changes += 1;
        }
    }
    for (name, e1) in &ents1 {
        if let Some(e2) = ents2.get(name) {
            if e1.type_id != e2.type_id {
                print_changed(&format!("entity {} type: {} → {}", name, e1.type_id, e2.type_id), is_tty);
                changes += 1;
            }
            if e1.attributes.len() != e2.attributes.len() {
                print_changed(&format!("entity {} attrs: {} → {}", name, e1.attributes.len(), e2.attributes.len()), is_tty);
                changes += 1;
            }
        }
    }

    // Compare relationships
    let rels1: Vec<_> = w1.relationships.iter().map(|r| {
        let src = w1.entities.get(&r.source_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
        let tgt = w1.entities.get(&r.target_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
        format!("{}-[{}]->{}", src, r.label, tgt)
    }).collect();
    let rels2: Vec<_> = w2.relationships.iter().map(|r| {
        let src = w2.entities.get(&r.source_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
        let tgt = w2.entities.get(&r.target_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
        format!("{}-[{}]->{}", src, r.label, tgt)
    }).collect();

    let set1: std::collections::HashSet<_> = rels1.iter().collect();
    let set2: std::collections::HashSet<_> = rels2.iter().collect();
    for r in set2.difference(&set1) {
        print_added(&format!("rel {}", r), is_tty);
        changes += 1;
    }
    for r in set1.difference(&set2) {
        print_removed(&format!("rel {}", r), is_tty);
        changes += 1;
    }

    // Compare relationship directionality changes
    for r2 in &w2.relationships {
        let src2 = w2.entities.get(&r2.source_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
        let tgt2 = w2.entities.get(&r2.target_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
        for r1 in &w1.relationships {
            let src1 = w1.entities.get(&r1.source_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
            let tgt1 = w1.entities.get(&r1.target_entity_id).map(|e| e.name.as_str()).unwrap_or("?");
            if src1 == src2 && tgt1 == tgt2 && r1.label == r2.label && r1.directed != r2.directed {
                let dir = if r2.directed { "directed" } else { "undirected" };
                print_changed(&format!("rel {}-[{}]->{} now {}", src2, r2.label, tgt2, dir), is_tty);
                changes += 1;
            }
        }
    }

    if changes == 0 {
        println!("No differences found");
    } else {
        println!("\n{} change(s)", changes);
    }
}
