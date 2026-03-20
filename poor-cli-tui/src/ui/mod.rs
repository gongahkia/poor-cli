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
    App, AppMode, AppWorkspace, ThemeMode,
};
use crate::input::{command_palette_matches, SlashCommandSpec};
use crate::markdown;
use crate::theme;

/// Main render function called each frame.
pub fn draw(frame: &mut Frame, app: &App) {
    frame.render_widget(
        Block::default().style(theme::app_background_style(app.theme_mode)),
        frame.area(),
    );

    let input_height = compute_input_height(app, frame.area().width);
    let activity_height = if show_activity_bar(app) { 1 } else { 0 };
    let has_presence = app.multiplayer.enabled && !app.pair.connected_users.is_empty();
    let mut constraints = Vec::new();
    if has_presence {
        constraints.push(Constraint::Length(1));
    }
    constraints.push(Constraint::Length(1));
    constraints.push(Constraint::Min(5));
    constraints.push(Constraint::Length(activity_height));
    constraints.push(Constraint::Length(input_height));
    constraints.push(Constraint::Length(1));
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints(constraints)
        .split(frame.area());

    let mut idx = 0usize;
    if has_presence {
        draw_presence_bar(frame, app, chunks[idx]);
        idx += 1;
    }
    draw_workspace_bar(frame, app, chunks[idx]);
    idx += 1;
    draw_main_area(frame, app, chunks[idx]);
    idx += 1;
    if activity_height > 0 {
        draw_activity_bar(frame, app, chunks[idx]);
    }
    idx += 1;
    draw_input_bar(frame, app, chunks[idx]);
    idx += 1;
    draw_hint_bar(frame, app, chunks[idx]);
    draw_command_palette(frame, app);
    draw_at_path_completion(frame, app);

    // Overlays
    if app.mode == AppMode::ProviderSelect {
        overlays::draw_provider_select(frame, app);
    }
    if app.mode == AppMode::InfoPopup {
        overlays::draw_info_popup(frame, app);
    }
    if app.mode == AppMode::ApiKeyEditor {
        overlays::draw_api_key_editor(frame, app);
    }
    if app.mode == AppMode::QueueManager {
        overlays::draw_queue_manager(frame, app);
    }
    if app.mode == AppMode::PermissionPrompt {
        overlays::draw_permission_prompt(frame, app);
    }
    if app.mode == AppMode::MutationReview {
        overlays::draw_mutation_review(frame, app);
    }
    if app.mode == AppMode::ContextInspector {
        overlays::draw_context_inspector(frame, app);
    }
    if app.mode == AppMode::QuickOpen {
        overlays::draw_quick_open(frame, app);
    }
    if app.mode == AppMode::Timeline {
        overlays::draw_timeline(frame, app);
    }
    if app.mode == AppMode::TranscriptSearch {
        overlays::draw_transcript_search(frame, app);
    }
    if app.mode == AppMode::PlanReview {
        overlays::draw_plan_review(frame, app);
    }
    if app.mode == AppMode::CompactSelect {
        overlays::draw_compact_select(frame, app);
    }
    if app.mode == AppMode::JoinWizard {
        overlays::draw_join_wizard(frame, app);
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

// ── Presence bar (pair mode) ──────────────────────────────────────────

fn draw_presence_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let dim = theme::muted_fg(mode);
    let mut spans = vec![Span::styled("  ", Style::default())];
    for (i, user) in app.pair.connected_users.iter().enumerate() {
        if i > 0 {
            spans.push(Span::styled(" · ", Style::default().fg(dim)));
        }
        spans.push(Span::styled(format!("{}", i + 1), Style::default().fg(dim)));
        spans.push(Span::styled(" ", Style::default()));
        let role_color = match user.role {
            crate::app::PairRole::Driver => theme::success(mode),
            crate::app::PairRole::Navigator => theme::accent(mode),
            crate::app::PairRole::Reviewer => theme::warning(mode),
        };
        spans.push(Span::styled(
            user.role.label().to_string(),
            Style::default().fg(role_color).add_modifier(Modifier::BOLD),
        ));
        spans.push(Span::styled(
            format!(" {}", user.name),
            Style::default().fg(theme::base_fg(mode)),
        ));
        if user.is_active {
            spans.push(Span::styled(" ●", Style::default().fg(theme::accent(mode))));
        }
    }
    if app.multiplayer.queue_depth > 0 {
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled(
            format!("queue:{}", app.multiplayer.queue_depth),
            Style::default().fg(theme::warning(mode)),
        ));
    }
    let room_label = if !app.pair.short_code.is_empty() {
        app.pair.short_code.as_str()
    } else {
        app.multiplayer.room.as_str()
    };
    if !room_label.is_empty() {
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled(
            format!("room:{room_label}"),
            Style::default().fg(dim),
        ));
    }
    let bar = Paragraph::new(Line::from(spans)).style(theme::footer_style(mode));
    frame.render_widget(bar, area);
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
    if app.active_workspace == AppWorkspace::Chat {
        draw_chat_area(frame, app, area);
    } else {
        draw_workspace_panel(frame, app, area);
    }
}

fn draw_workspace_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let mut spans = vec![Span::styled("  ", Style::default())];
    for (idx, workspace) in AppWorkspace::ALL.iter().enumerate() {
        if idx > 0 {
            spans.push(Span::styled("  ", Style::default()));
        }
        let is_active = *workspace == app.active_workspace;
        let label = format!("{} {}", workspace.shortcut(), workspace.label());
        let style = if is_active {
            Style::default()
                .fg(theme::accent(mode))
                .add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(theme::muted_fg(mode))
        };
        spans.push(Span::styled(label, style));
    }
    let bar = Paragraph::new(Line::from(spans)).style(theme::footer_style(mode));
    frame.render_widget(bar, area);
}

fn draw_chat_area(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    if app.messages.is_empty() {
        chat::clear_cache();
        let empty = Paragraph::new("Start typing to begin a conversation...")
            .style(Style::default().fg(theme::muted_fg(mode)))
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

fn draw_workspace_panel(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let title = format!(" {} Workspace ", app.active_workspace.label());
    let body = app
        .workspace_content()
        .filter(|content| !content.trim().is_empty())
        .unwrap_or("No workspace data loaded yet.");
    let lines = markdown::render_markdown(body, mode);
    let panel = Paragraph::new(lines)
        .wrap(Wrap { trim: false })
        .style(theme::surface_style(mode))
        .block(
            Block::default()
                .borders(Borders::TOP)
                .title(Span::styled(title, theme::brand_style(mode)))
                .style(theme::surface_style(mode))
                .padding(Padding::new(1, 1, 0, 0)),
        );
    frame.render_widget(panel, area);
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
    let spans = if let Some((status, _)) = &app.status_message {
        vec![Span::styled(
            format!("  {status}"),
            Style::default().fg(theme::warning(mode)),
        )]
    } else if let Some(suggestion) = app.latest_suggestion() {
        let remaining = crate::app::SUGGESTION_HINT_TTL
            .checked_sub(suggestion.received_at.elapsed())
            .map(|d| d.as_secs())
            .unwrap_or(0);
        vec![
            Span::styled(
                format!("  [{}]: {}", suggestion.sender, suggestion.text),
                Style::default().fg(theme::accent(mode)),
            ),
            Span::styled(
                format!(" ({remaining}s)"),
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ]
    } else if app.mode == AppMode::InfoPopup {
        vec![
            Span::styled("  Esc/Enter", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": close  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("c", Style::default().fg(theme::accent(mode))),
            Span::styled(": copy all  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("1-9", Style::default().fg(theme::accent(mode))),
            Span::styled(": copy item  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("↑↓", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": scroll  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("PgUp/PgDn", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": fast scroll", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::ApiKeyEditor {
        vec![
            Span::styled("  ↑↓/Tab", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": switch field  ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("Enter", Style::default().fg(theme::success(mode))),
            Span::styled(": next/save  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Ctrl+S", Style::default().fg(theme::success(mode))),
            Span::styled(": save  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": cancel", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::ProviderSelect {
        vec![
            Span::styled("  ←→", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": switch pane  ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("↑↓", Style::default().fg(theme::accent(mode))),
            Span::styled(": navigate  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Enter", Style::default().fg(theme::success(mode))),
            Span::styled(
                ": switch provider/model  ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": close", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::PermissionPrompt {
        vec![
            Span::styled("  y/Enter", Style::default().fg(theme::success(mode))),
            Span::styled(": allow  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("n/Esc", Style::default().fg(theme::error(mode))),
            Span::styled(": deny  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("?", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": explain request",
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ]
    } else if app.mode == AppMode::QueueManager {
        vec![
            Span::styled("  ↑↓", Style::default().fg(theme::accent(mode))),
            Span::styled(": select  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Enter/s", Style::default().fg(theme::success(mode))),
            Span::styled(": send  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("e", Style::default().fg(theme::accent(mode))),
            Span::styled(": edit  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("d", Style::default().fg(theme::accent(mode))),
            Span::styled(": drop  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("u/j", Style::default().fg(theme::accent(mode))),
            Span::styled(": reorder  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("c", Style::default().fg(theme::accent(mode))),
            Span::styled(": clear", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.at_path_completion.active
        && matches!(app.mode, AppMode::Normal | AppMode::Command)
    {
        vec![
            Span::styled("  ↑↓", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": select file  ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("Tab/Enter", Style::default().fg(theme::success(mode))),
            Span::styled(": attach  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": close", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::JoinWizard {
        vec![
            Span::styled("  Enter", Style::default().fg(theme::accent(mode))),
            Span::styled(": confirm  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": cancel", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::ContextInspector {
        vec![
            Span::styled("  ↑↓", Style::default().fg(theme::accent(mode))),
            Span::styled(": select  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("d", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": remove attachment  ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("c", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": copy summary  ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": close", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::MutationReview {
        let approve_file_label = if app
            .mutation_review
            .as_ref()
            .map(|review| review.paths.len() > 1)
            .unwrap_or(false)
        {
            ": approve selected file  "
        } else {
            ": approve file  "
        };
        let supports_chunk_approval = app
            .mutation_review
            .as_ref()
            .map(|review| review.supports_chunk_approval())
            .unwrap_or(false);
        vec![
            Span::styled("  y/Enter", Style::default().fg(theme::success(mode))),
            Span::styled(": approve  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("n/Esc", Style::default().fg(theme::error(mode))),
            Span::styled(": reject  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Space", Style::default().fg(theme::accent(mode))),
            Span::styled(
                if supports_chunk_approval {
                    ": toggle hunk  "
                } else {
                    ": no-op  "
                },
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("h", Style::default().fg(theme::accent(mode))),
            Span::styled(
                if supports_chunk_approval {
                    ": approve hunks  "
                } else {
                    ": no-op  "
                },
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("f", Style::default().fg(theme::accent(mode))),
            Span::styled(
                approve_file_label,
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("u", Style::default().fg(theme::accent(mode))),
            Span::styled(": undo  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("o", Style::default().fg(theme::accent(mode))),
            Span::styled(": open file  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("?", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": explain review",
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ]
    } else if app.mode == AppMode::QuickOpen {
        vec![
            Span::styled("  type", Style::default().fg(theme::accent(mode))),
            Span::styled(": filter  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("↑↓", Style::default().fg(theme::accent(mode))),
            Span::styled(": move  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Enter", Style::default().fg(theme::success(mode))),
            Span::styled(": open  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": close", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::Timeline {
        vec![
            Span::styled("  ↑↓", Style::default().fg(theme::accent(mode))),
            Span::styled(": scroll  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("c", Style::default().fg(theme::accent(mode))),
            Span::styled(": copy diff  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("u", Style::default().fg(theme::accent(mode))),
            Span::styled(": undo  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": close", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::TranscriptSearch {
        vec![
            Span::styled("  type", Style::default().fg(theme::accent(mode))),
            Span::styled(": search  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("↑↓", Style::default().fg(theme::accent(mode))),
            Span::styled(": select  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Tab", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": filter group  ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled("Esc", Style::default().fg(theme::accent(mode))),
            Span::styled(": close", Style::default().fg(theme::muted_fg(mode))),
        ]
    } else if app.mode == AppMode::PlanReview {
        vec![
            Span::styled("  Enter", Style::default().fg(theme::success(mode))),
            Span::styled(": continue  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Esc", Style::default().fg(theme::error(mode))),
            Span::styled(": back  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("?", Style::default().fg(theme::accent(mode))),
            Span::styled(
                ": explain plan gate",
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ]
    } else if app.mode == AppMode::Command {
        // Show matching commands
        let prefix = &app.input_buffer;
        let matches = command_palette_matches(prefix);
        let mut spans = vec![Span::styled("  ", Style::default())];
        for (i, m) in matches.into_iter().take(6).enumerate() {
            if i > 0 {
                spans.push(Span::styled("  ", Style::default()));
            }
            spans.push(Span::styled(
                m.command.to_string(),
                Style::default().fg(theme::muted_fg(mode)),
            ));
        }
        spans
    } else {
        draw_default_footer_bar(frame, app, area);
        return;
    };

    let hint = Paragraph::new(Line::from(spans)).style(theme::hint_style(mode));
    frame.render_widget(hint, area);
}

fn draw_default_footer_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let width = usize::from(area.width);
    if width == 0 {
        return;
    }

    let model = if app.provider.model.trim().is_empty() || app.provider.model == "unknown" {
        app.provider.name.clone()
    } else {
        app.provider.model.clone()
    };
    let branch = if app.git_branch.is_empty() {
        String::new()
    } else if app.git_dirty {
        format!(" ({})", format!("{}*", app.git_branch))
    } else {
        format!(" ({})", app.git_branch)
    };
    let workspace = if app.cwd.trim().is_empty() {
        "~".to_string()
    } else {
        ellipsize_middle(&app.cwd, 28)
    };
    let mut right_segments = vec![ellipsize_middle(&model, 24)];
    if app.context_budget_tokens > 0 {
        let used = app
            .context_budget_estimated_tokens
            .min(app.context_budget_tokens);
        let remaining_pct = 100usize.saturating_sub((used * 100) / app.context_budget_tokens);
        right_segments.push(format!("ctx {remaining_pct}% left"));
    }
    right_segments.push(app.permission_mode_label.clone());
    right_segments.push(format!("{workspace}{branch}"));
    let mut right = right_segments.join(" · ");
    if app.multiplayer.enabled && !app.multiplayer.room.is_empty() {
        let role = if app.multiplayer.ui_role.is_empty() {
            "?"
        } else {
            &app.multiplayer.ui_role
        };
        let mode = if app.multiplayer.mode.is_empty() {
            "collab"
        } else {
            &app.multiplayer.mode
        };
        right.push_str(&format!(" · {}/{} ({mode})", app.multiplayer.room, role));
    }

    let left_candidates: Vec<String> = if app.queue_paused && !app.prompt_queue.is_empty() {
        vec!["Queue paused · /queue to review".to_string()]
    } else if app.waiting || !app.prompt_queue.is_empty() {
        vec!["Tab to queue message".to_string()]
    } else if app.input_buffer.trim().is_empty() {
        let workspace_hint = if cfg!(target_os = "macos") {
            "Alt+1..6 switch workspaces"
        } else {
            "F1-F6 or Alt+1..6 switch workspaces"
        };
        vec![workspace_hint.to_string(), "? for shortcuts".to_string()]
    } else {
        vec!["Shift+Enter for newline".to_string()]
    };

    let mut chosen_left: Option<String> = None;
    for candidate in &left_candidates {
        if candidate.chars().count() + right.chars().count() + 4 <= width {
            chosen_left = Some(candidate.clone());
            break;
        }
    }

    let line = if let Some(left) = chosen_left {
        let spacing = width.saturating_sub(left.chars().count() + right.chars().count());
        format!("{left}{}{}", " ".repeat(spacing), right)
    } else if right.chars().count() < width {
        format!(
            "{}{}",
            " ".repeat(width.saturating_sub(right.chars().count())),
            right
        )
    } else {
        ellipsize_middle(&right, width.saturating_sub(1).max(1))
    };

    let hint = Paragraph::new(Line::from(Span::styled(
        format!("  {line}"),
        Style::default().fg(theme::muted_fg(mode)),
    )))
    .style(theme::footer_style(mode));
    frame.render_widget(hint, area);
}

fn draw_command_palette(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    if app.waiting || !app.input_buffer.starts_with('/') || app.at_path_completion.active {
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
    if !app.at_path_completion.active || !matches!(app.mode, AppMode::Normal | AppMode::Command) {
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
