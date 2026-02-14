use ratatui::prelude::*;
use ratatui::widgets::*;
use ratatui::style::{Color, Style, Modifier};
use crate::model::types::Id;
use super::app::{App, InputMode};

/// Render the TUI (Tasks 49-53)
pub fn draw(frame: &mut ratatui::Frame, app: &App) {
    let area = frame.area();

    // Split: main timeline view + optional detail panel
    let has_selection = app.selected_entity.is_some();
    let chunks = if has_selection {
        Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(70), Constraint::Percentage(30)])
            .split(area)
    } else {
        Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(100)])
            .split(area)
    };

    // Split main area: timeline + status bar
    let main_chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(3), Constraint::Length(1)])
        .split(chunks[0]);

    // Main timeline view (Task 49)
    draw_timeline_view(frame, main_chunks[0], app);

    // Status bar
    draw_status_bar(frame, main_chunks[1], app);

    // Entity detail panel (Task 50)
    if has_selection && chunks.len() > 1 {
        draw_entity_detail(frame, chunks[1], app);
    }

    // Help overlay (Task 62)
    if app.input_mode == InputMode::Help {
        draw_help_overlay(frame, area);
    }

    // Search bar
    if app.input_mode == InputMode::Search {
        draw_search_bar(frame, area, app);
    }
}

/// Main timeline view widget (Task 49)
fn draw_timeline_view(frame: &mut ratatui::Frame, area: Rect, app: &App) {
    let vp = &app.layout.viewport;
    let time_range = vp.time_end - vp.time_start;
    if time_range <= 0.0 || area.width < 2 || area.height < 2 {
        let block = Block::default().title("Timeline").borders(Borders::ALL);
        frame.render_widget(block, area);
        return;
    }

    let inner_width = area.width.saturating_sub(2) as f64;
    let inner_height = area.height.saturating_sub(2) as usize;

    let mut lines: Vec<Line> = Vec::new();

    // Time axis with tick marks
    let mut axis = vec![Span::raw("  ")];
    for tick in &app.layout.ticks {
        let x = ((tick.x - vp.time_start) / time_range * inner_width) as u16;
        if x < area.width.saturating_sub(2) {
            axis.push(Span::styled(
                format!("{:<6}", tick.label),
                Style::default().fg(Color::DarkGray),
            ));
        }
    }
    lines.push(Line::from(axis));

    // Timeline region backgrounds
    for tl in &app.layout.timelines {
        if tl.lane_start >= vp.lane_start && tl.lane_start < vp.lane_end {
            let label = format!("─── {} ({:?}) ", tl.name, tl.kind);
            let suffix = if tl.is_loop {
                format!(" ↻×{}", tl.loop_count.unwrap_or(1))
            } else { String::new() };
            lines.push(Line::from(Span::styled(
                format!("{}{}", label, suffix),
                Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD),
            )));
        }
    }

    // Entity swim lanes as horizontal bars (Task 49)
    for ent in &app.layout.entities {
        if ent.lane < vp.lane_start || ent.lane >= vp.lane_end { continue; }
        if lines.len() >= inner_height { break; }

        let x_start = ((ent.x_start - vp.time_start) / time_range * inner_width).max(0.0) as usize;
        let x_end = ((ent.x_end - vp.time_start) / time_range * inner_width).min(inner_width) as usize;
        let bar_len = x_end.saturating_sub(x_start).max(1);

        let is_selected = app.selected_entity == Some(ent.entity_id);
        let is_connected = app.selected_entity.map_or(true, |sel_id| {
            app.layout.edges.iter().any(|e| {
                let src = app.layout.entities.get(e.source_lane).map(|en| en.entity_id);
                let tgt = app.layout.entities.get(e.target_lane).map(|en| en.entity_id);
                (src == Some(sel_id) && tgt == Some(ent.entity_id))
                || (tgt == Some(sel_id) && src == Some(ent.entity_id))
                || sel_id == ent.entity_id
            })
        });

        let color = if is_selected {
            Color::Yellow
        } else {
            entity_color(&ent.entity_type, is_connected)
        };

        let mut spans = vec![Span::raw(" ".repeat(x_start.min(inner_width as usize)))];
        spans.push(Span::styled(
            "█".repeat(bar_len),
            Style::default().fg(color),
        ));
        spans.push(Span::styled(
            format!(" {}", ent.name),
            Style::default().fg(if is_selected { Color::Yellow } else { Color::White })
                .add_modifier(if is_selected { Modifier::BOLD } else { Modifier::empty() }),
        ));
        lines.push(Line::from(spans));

        // Relationship overlay (Task 51) - show edge indicators for selected
        if is_selected {
            for edge in &app.layout.edges {
                if edge.source_lane == ent.lane || edge.target_lane == ent.lane {
                    let arrow = if edge.directed { "→" } else { "─" };
                    let edge_x = ((edge.source_x - vp.time_start) / time_range * inner_width).max(0.0) as usize;
                    let mut espans = vec![Span::raw(" ".repeat(edge_x.min(inner_width as usize)))];
                    espans.push(Span::styled(
                        format!("{} {}", arrow, edge.label),
                        Style::default().fg(Color::Magenta),
                    ));
                    lines.push(Line::from(espans));
                }
            }
        }
    }

    // Branch/merge connectors
    for conn in &app.layout.connectors {
        if lines.len() >= inner_height { break; }
        let x = ((conn.from_x - vp.time_start) / time_range * inner_width).max(0.0) as usize;
        let symbol = match conn.kind {
            crate::layout::engine::ConnectorKind::Fork => "╱ fork",
            crate::layout::engine::ConnectorKind::Merge => "╲ merge",
        };
        let mut spans = vec![Span::raw(" ".repeat(x.min(inner_width as usize)))];
        spans.push(Span::styled(symbol, Style::default().fg(Color::Green)));
        lines.push(Line::from(spans));
    }

    let block = Block::default().title("Timeline").borders(Borders::ALL);
    let paragraph = Paragraph::new(lines).block(block);
    frame.render_widget(paragraph, area);
}

/// Entity detail panel (Task 50)
fn draw_entity_detail(frame: &mut ratatui::Frame, area: Rect, app: &App) {
    let Some(sel_id) = app.selected_entity else {
        return;
    };

    let mut lines: Vec<Line> = Vec::new();

    if let Some(ent) = app.layout.entities.iter().find(|e| e.entity_id == sel_id) {
        lines.push(Line::from(Span::styled(
            &ent.name,
            Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD),
        )));
        lines.push(Line::from(format!("Type: {}", ent.entity_type)));
        lines.push(Line::from(format!("Lane: {}", ent.lane)));
        lines.push(Line::from(format!("Time: {:.0}..{:.0}", ent.x_start, ent.x_end)));
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled("Relationships:", Style::default().add_modifier(Modifier::BOLD))));

        for edge in &app.layout.edges {
            let is_source = edge.source_lane == ent.lane;
            let is_target = edge.target_lane == ent.lane;
            if is_source || is_target {
                let other_lane = if is_source { edge.target_lane } else { edge.source_lane };
                let other_name = app.layout.entities.iter()
                    .find(|e| e.lane == other_lane)
                    .map(|e| e.name.as_str())
                    .unwrap_or("?");
                let arrow = if edge.directed {
                    if is_source { "→" } else { "←" }
                } else { "─" };
                lines.push(Line::from(format!("  {} {} {}", arrow, edge.label, other_name)));
            }
        }
    }

    let block = Block::default().title("Entity Detail").borders(Borders::ALL);
    let paragraph = Paragraph::new(lines).block(block);
    frame.render_widget(paragraph, area);
}

fn draw_status_bar(frame: &mut ratatui::Frame, area: Rect, app: &App) {
    let vp = &app.layout.viewport;
    let status = format!(
        " Time: {:.0}..{:.0} | Zoom: {:.1}x | Entities: {} | Rels: {} | {} ",
        vp.time_start, vp.time_end, vp.scale,
        app.layout.entities.len(),
        app.layout.edges.len(),
        app.status_message,
    );
    let bar = Paragraph::new(status)
        .style(Style::default().bg(Color::DarkGray).fg(Color::White));
    frame.render_widget(bar, area);
}

fn draw_help_overlay(frame: &mut ratatui::Frame, area: Rect) {
    let help_text = vec![
        Line::from(Span::styled("Keybindings", Style::default().add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from("Navigation:"),
        Line::from("  h/←  Pan left       l/→  Pan right"),
        Line::from("  k/↑  Pan up         j/↓  Pan down"),
        Line::from("  +    Zoom in        -    Zoom out"),
        Line::from(""),
        Line::from("Selection:"),
        Line::from("  Tab    Cycle entities"),
        Line::from("  Enter  Focus selected"),
        Line::from("  Esc    Deselect"),
        Line::from(""),
        Line::from("Other:"),
        Line::from("  /    Search          ?    Toggle help"),
        Line::from("  q    Quit"),
    ];

    let block = Block::default().title("Help").borders(Borders::ALL)
        .style(Style::default().bg(Color::Black));
    let w = area.width.min(50);
    let h = area.height.min(18);
    let popup = Rect::new(
        area.x + (area.width - w) / 2,
        area.y + (area.height - h) / 2,
        w, h,
    );
    frame.render_widget(Clear, popup);
    let paragraph = Paragraph::new(help_text).block(block);
    frame.render_widget(paragraph, popup);
}

fn draw_search_bar(frame: &mut ratatui::Frame, area: Rect, app: &App) {
    let search_area = Rect::new(area.x, area.y + area.height - 3, area.width, 3);
    let block = Block::default().title("Search").borders(Borders::ALL);
    let text = Paragraph::new(format!("/{}", app.search_query)).block(block);
    frame.render_widget(Clear, search_area);
    frame.render_widget(text, search_area);
}

fn entity_color(entity_type: &str, connected: bool) -> Color {
    if !connected { return Color::DarkGray; }
    match entity_type {
        "character" => Color::Blue,
        "event" => Color::Red,
        "location" => Color::Green,
        "artifact" => Color::Magenta,
        "org" | "faction" => Color::Cyan,
        _ => Color::White,
    }
}
