/// TUI layout renderer for the terminal agent surface.
///
/// Layout:
/// ┌───────────────────────────────────────────┐
/// │ optional presence row                     │
/// │ chat transcript                           │
/// │ optional activity row                     │
/// │ composer                                  │
/// │ footer                                    │
/// └───────────────────────────────────────────┘
pub(crate) mod chat;
pub(crate) mod overlays;

use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Clear, List, ListItem, Padding, Paragraph, Wrap},
    Frame,
};

use crate::app::{
    App, AppMode, OverlayKind, ThemeMode,
};
use crate::input::{command_palette_matches, SlashCommandSpec};
use crate::theme;

/// Main render function called each frame.
pub fn draw(frame: &mut Frame, app: &App) {
    frame.render_widget(
        Block::default().style(theme::app_background_style(app.theme_mode)),
        frame.area(),
    );

    let input_height = compute_input_height(app, frame.area().width);
    let activity_height = if show_activity_bar(app) { 1 } else { 0 };
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),  // header bar
            Constraint::Min(5),    // chat area
            Constraint::Length(activity_height), // activity bar
            Constraint::Length(input_height),    // input bar
            Constraint::Length(1), // hint bar
        ])
        .split(frame.area());

    draw_header_bar(frame, app, chunks[0]);
    draw_main_area(frame, app, chunks[1]);
    if activity_height > 0 {
        draw_activity_bar(frame, app, chunks[2]);
    }
    draw_input_bar(frame, app, chunks[3]);
    draw_hint_bar(frame, app, chunks[4]);
    draw_command_palette(frame, app);
    draw_at_path_completion(frame, app);

    // Overlays
    if app.mode == AppMode::Overlay {
        match app.overlay_kind {
            Some(OverlayKind::ProviderSelect) => overlays::draw_provider_select(frame, app),
            Some(OverlayKind::InfoPopup) => overlays::draw_info_popup(frame, app),
            Some(OverlayKind::ApiKeyEditor) => overlays::draw_api_key_editor(frame, app),
            Some(OverlayKind::JoinWizard) => overlays::draw_join_wizard(frame, app),
            Some(OverlayKind::GraphOverlay) => overlays::draw_graph_overlay(frame, app),
            Some(OverlayKind::ListSelector) => overlays::draw_list_selector(frame, app),
            Some(OverlayKind::Onboarding) => overlays::draw_onboarding(frame, app),
            None => {}
        }
    }
    // graph overlay renders passively ONLY when no other overlay is active
    if app.graph_overlay.active
        && app.mode != AppMode::Overlay
        && app.overlay_kind.is_none()
    {
        overlays::draw_graph_overlay(frame, app);
    }
    if app.mode == AppMode::QuickOpen {
        overlays::draw_quick_open(frame, app);
    }
}

fn build_input_lines(app: &App, mode: ThemeMode) -> Vec<Line<'static>> {
    let mut lines: Vec<Line<'static>> = Vec::new();
    let parts: Vec<&str> = app.input_buffer.split('\n').collect();

    for (idx, part) in parts.iter().enumerate() {
        let is_first = idx == 0;
        let is_last = idx + 1 == parts.len();
        let prefix = if is_first { "  > " } else { "    " };
        let mut spans = vec![
            Span::styled(
                prefix.to_string(),
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled((*part).to_string(), theme::input_style(mode)),
        ];

        if is_last {
            spans.push(Span::styled("█", theme::input_cursor_style(mode)));
            if app.input_buffer.is_empty() {
                spans.push(Span::styled(
                    if app.waiting {
                        " Queue another prompt or @path/to/file".to_string()
                    } else {
                        " Type your message or @path/to/file".to_string()
                    },
                    Style::default().fg(theme::muted_fg(mode)),
                ));
            }
        }

        lines.push(Line::from(spans));
    }

    lines
}

fn compute_input_height(app: &App, terminal_width: u16) -> u16 {
    let mode = app.theme_mode;
    let input_lines = build_input_lines(app, mode);
    let input_paragraph = Paragraph::new(input_lines).wrap(Wrap { trim: false });
    let visual_lines = input_paragraph
        .line_count(terminal_width.max(1))
        .max(1)
        .min(u16::MAX as usize) as u16;

    visual_lines.saturating_add(2).clamp(3, 6)
}

fn show_activity_bar(app: &App) -> bool {
    app.streaming.active_tool.is_some() || app.streaming.message.is_some() || app.waiting
}

fn draw_activity_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let mut spans = vec![Span::styled("  ", Style::default())];

    let (label, detail) = if let Some(tool) = &app.streaming.active_tool {
        (
            format!("{} {}", app.spinner_frame(), ellipsize_middle(tool, 22)),
            format!(
                "  [{}/{}]  {}",
                app.streaming.current_iteration,
                app.streaming.iteration_cap,
                app.wait_elapsed()
            ),
        )
    } else if app.streaming.message.is_some() {
        let label = if app.streaming.thinking_active {
            let line_count = app.streaming.thinking_buffer.lines().count();
            format!("{} reasoning ({} lines)", app.thinking_frame(), line_count)
        } else {
            format!("{} responding", app.thinking_frame())
        };
        (label, format!("  {}  ·  Esc cancel", app.wait_elapsed()))
    } else {
        let queue_detail = if app.prompt_queue.is_empty() {
            "type to queue".to_string()
        } else {
            format!("{} queued", app.prompt_queue.len())
        };
        (
            format!("{} thinking", app.thinking_frame()),
            format!(
                "  {}  ·  {}  ·  Esc cancel",
                app.wait_elapsed(),
                queue_detail
            ),
        )
    };

    spans.push(Span::styled(
        label,
        Style::default()
            .fg(theme::accent(mode))
            .add_modifier(Modifier::BOLD),
    ));
    spans.push(Span::styled(
        detail,
        Style::default().fg(theme::muted_fg(mode)),
    ));

    let bar = Paragraph::new(Line::from(spans)).style(theme::activity_style(mode));
    frame.render_widget(bar, area);
}

pub(crate) fn ellipsize_middle(value: &str, max_chars: usize) -> String {
    let chars: Vec<char> = value.chars().collect();
    if chars.len() <= max_chars {
        return value.to_string();
    }
    if max_chars <= 3 {
        return "...".to_string();
    }

    let head_len = (max_chars - 1) / 2;
    let tail_len = max_chars - head_len - 1;
    let head: String = chars.iter().take(head_len).collect();
    let tail: String = chars
        .iter()
        .rev()
        .take(tail_len)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .collect();
    format!("{head}…{tail}")
}

// ── Chat area ────────────────────────────────────────────────────────

fn draw_main_area(frame: &mut Frame, app: &App, area: Rect) {
    draw_chat_area(frame, app, area);
}

// ── Header bar ───────────────────────────────────────────────────────

fn draw_header_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let dim = theme::muted_fg(mode);
    let mut spans = vec![
        Span::styled("  ", Style::default()),
        Span::styled(
            format!("poor-cli v{}", app.version),
            theme::brand_style(mode),
        ),
    ];
    // provider/model
    let provider_known = !app.provider.name.trim().is_empty() && app.provider.name != "unknown";
    let model_known = !app.provider.model.trim().is_empty() && app.provider.model != "unknown";
    if provider_known || model_known {
        spans.push(Span::styled("  ", Style::default()));
        let label = if provider_known && model_known {
            format!("{}/{}", app.provider.name, app.provider.model)
        } else if provider_known {
            app.provider.name.clone()
        } else {
            app.provider.model.clone()
        };
        spans.push(Span::styled(label, Style::default().fg(theme::base_fg(mode))));
    }
    // sandbox mode
    if !app.permission_mode_label.is_empty() {
        spans.push(Span::styled("  ", Style::default()));
        let sandbox_color = match app.permission_mode_label.as_str() {
            "prompt" => theme::success(mode),
            "auto-safe" => theme::warning(mode),
            _ => theme::error(mode), // danger-full-access or unknown
        };
        spans.push(Span::styled(
            app.permission_mode_label.clone(),
            Style::default().fg(sandbox_color),
        ));
    }
    // cost estimate
    let input_cost = app.tokens.cumulative_input_tokens as f64 * 0.01 / 1000.0;
    let output_cost = app.tokens.cumulative_output_tokens as f64 * 0.03 / 1000.0;
    let total_cost = input_cost + output_cost;
    if total_cost > 0.001 {
        spans.push(Span::styled("  ", Style::default()));
        spans.push(Span::styled(
            format!("${total_cost:.2}"),
            Style::default().fg(dim),
        ));
    }
    // checkpoint count
    let cp_count = app.recent_checkpoints.len();
    if cp_count > 0 {
        spans.push(Span::styled("  ", Style::default()));
        spans.push(Span::styled(
            format!("[{cp_count} cp]"),
            Style::default().fg(dim),
        ));
    }
    // activity spinner
    if app.waiting {
        spans.push(Span::styled("  ", Style::default()));
        spans.push(Span::styled(
            format!("{} responding", app.spinner_frame()),
            Style::default().fg(theme::accent(mode)),
        ));
    }
    // multiplayer
    if app.multiplayer.enabled && app.multiplayer.member_count > 0 {
        spans.push(Span::styled("  ", Style::default()));
        spans.push(Span::styled(
            format!("[{} users]", app.multiplayer.member_count),
            Style::default().fg(dim),
        ));
    }
    let bar = Paragraph::new(Line::from(spans)).style(theme::footer_style(mode));
    frame.render_widget(bar, area);
}

fn draw_chat_area(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    if app.messages.is_empty() {
        chat::clear_cache();
        let text = if app.mascot_enabled {
            "          {o,o}/\n          /)__)\n          -\"-\"-\n\n   \"Hey! Type a message or\n    try /help to get started.\""
        } else {
            "Start typing to begin a conversation..."
        };
        let empty = Paragraph::new(text)
            .style(Style::default().fg(if app.mascot_enabled { theme::accent(mode) } else { theme::muted_fg(mode) }))
            .block(
                Block::default()
                    .borders(Borders::NONE)
                    .padding(Padding::new(2, 2, 1, 0)),
            );
        frame.render_widget(empty, area);
        return;
    }

    let all_lines = chat::cached_chat_lines(app, mode);
    let text = Text::from(all_lines);
    let base_para = Paragraph::new(text).wrap(Wrap { trim: false });
    let total_lines = base_para.line_count(area.width).min(u16::MAX as usize) as u16;
    let visible_height = area.height;
    let max_scroll = total_lines.saturating_sub(visible_height);
    let effective_scroll = app.scroll_offset.min(max_scroll);
    let para = base_para.scroll((max_scroll.saturating_sub(effective_scroll), 0));

    frame.render_widget(para, area);
}

// ── Input bar ────────────────────────────────────────────────────────

fn draw_input_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let input_lines = build_input_lines(app, mode);
    let input = Paragraph::new(input_lines)
        .wrap(Wrap { trim: false })
        .style(theme::input_panel_style(mode))
        .block(Block::default().style(theme::input_panel_style(mode)));
    frame.render_widget(input, area);
}

// ── Hint bar ─────────────────────────────────────────────────────────

fn draw_hint_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let dim = theme::muted_fg(mode);
    let spans = if let Some((status, _)) = &app.status_message {
        vec![Span::styled(format!("  {status}"), Style::default().fg(theme::warning(mode)))]
    } else if let Some(suggestion) = app.latest_suggestion() {
        let remaining = crate::app::SUGGESTION_HINT_TTL
            .checked_sub(suggestion.received_at.elapsed())
            .map(|d| d.as_secs())
            .unwrap_or(0);
        vec![
            Span::styled(format!("  [{}]: {}", suggestion.sender, suggestion.text), Style::default().fg(theme::accent(mode))),
            Span::styled(format!(" ({remaining}s)"), Style::default().fg(dim)),
        ]
    } else if app.mode == AppMode::Quitting {
        vec![]
    } else if app.mode == AppMode::Overlay {
        vec![Span::styled("  Esc close", Style::default().fg(dim))]
    } else if app.mode == AppMode::InlineApproval {
        vec![Span::styled("  y allow  n deny  d diff  ? help", Style::default().fg(dim))]
    } else if app.mode == AppMode::QuickOpen {
        vec![Span::styled("  Enter select  Esc close  Type to filter", Style::default().fg(dim))]
    } else {
        // Normal mode
        vec![Span::styled("  / commands  Ctrl+P palette  F2 provider  Esc cancel", Style::default().fg(dim))]
    };
    let hint = Paragraph::new(Line::from(spans)).style(theme::hint_style(mode));
    frame.render_widget(hint, area);
}


fn draw_command_palette(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    if !app.input_buffer.starts_with('/') || app.at_path_completion.active {
        return;
    }

    let commands = command_palette_matches(&app.input_buffer);

    if commands.is_empty() {
        return;
    }

    let display_items: Vec<&SlashCommandSpec> = commands.into_iter().take(8).collect();
    let palette_height =
        (display_items.len() as u16 + 2).min(frame.area().height.saturating_sub(5));
    if palette_height < 3 {
        return;
    }

    let width = frame.area().width.min(72);
    let x = 2.min(frame.area().width.saturating_sub(width));
    let y = frame
        .area()
        .height
        .saturating_sub(palette_height + 4)
        .max(1);
    let area = Rect::new(x, y, width, palette_height);

    render_popup_surface(frame, area, mode);

    let selected_index = app
        .command_match_index
        .min(display_items.len().saturating_sub(1));

    let items: Vec<ListItem> = display_items
        .iter()
        .enumerate()
        .map(|(idx, spec)| {
            let is_selected = idx == selected_index;
            let command_style = if is_selected {
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default()
                    .fg(theme::base_fg(mode))
                    .add_modifier(Modifier::BOLD)
            };
            let desc_style = if is_selected {
                Style::default().fg(theme::base_fg(mode))
            } else if spec.recommended {
                Style::default().fg(theme::accent(mode))
            } else {
                Style::default().fg(theme::muted_fg(mode))
            };
            let marker = if is_selected { "▸ " } else { "  " };
            ListItem::new(Line::from(vec![
                Span::styled(format!("{marker}{:<12}", spec.command), command_style),
                Span::styled(spec.description.to_string(), desc_style),
            ]))
        })
        .collect();

    let title = if app.input_buffer.trim() == "/" {
        " Commands (recommended first) "
    } else {
        " Commands "
    };

    let list = List::new(items).block(
        Block::default()
            .title(Span::styled(
                title,
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::input_border_color(mode))),
    );
    frame.render_widget(list, area);
}

fn draw_at_path_completion(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    if !app.at_path_completion.active || app.mode != AppMode::Normal {
        return;
    }

    let row_count = app.at_path_completion.items.len().max(1).min(8) as u16;
    let popup_height = row_count + 3;
    if frame.area().height <= popup_height + 4 {
        return;
    }

    let width = frame.area().width.min(78);
    let x = 2.min(frame.area().width.saturating_sub(width));
    let y = frame.area().height.saturating_sub(popup_height + 4).max(1);
    let area = Rect::new(x, y, width, popup_height);
    render_popup_surface(frame, area, mode);

    let items: Vec<ListItem> = if app.at_path_completion.items.is_empty() {
        vec![ListItem::new(Line::from(Span::styled(
            "  No matching files",
            Style::default().fg(theme::muted_fg(mode)),
        )))]
    } else {
        app.at_path_completion
            .items
            .iter()
            .enumerate()
            .map(|(index, item)| {
                let is_selected = index == app.at_path_completion.selected_index;
                let marker = if is_selected { "▸ " } else { "  " };
                let path_style = if is_selected {
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(theme::base_fg(mode))
                };
                let detail_style = if is_selected {
                    Style::default().fg(theme::base_fg(mode))
                } else {
                    Style::default().fg(theme::muted_fg(mode))
                };
                ListItem::new(Line::from(vec![
                    Span::styled(format!("{marker}{}", item.path), path_style),
                    Span::styled(format!("  {}", item.detail), detail_style),
                ]))
            })
            .collect()
    };

    let title = if app.at_path_completion.query.trim().is_empty() {
        " Attach File "
    } else {
        " Attach File (@...) "
    };

    let list = List::new(items).block(
        Block::default()
            .title(Span::styled(
                title,
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::input_border_color(mode))),
    );
    frame.render_widget(list, area);
}

// ── Helpers ──────────────────────────────────────────────────────────

pub(crate) fn render_popup_surface(frame: &mut Frame, area: Rect, mode: ThemeMode) {
    frame.render_widget(Clear, area);
    frame.render_widget(
        Block::default().style(
            Style::default()
                .fg(theme::base_fg(mode))
                .bg(theme::elevated_bg(mode)),
        ),
        area,
    );
}

/// Create a centered rectangle with percentage-based width/height.
pub(crate) fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(area);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}
