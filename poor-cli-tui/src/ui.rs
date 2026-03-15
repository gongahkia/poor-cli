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
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Clear, List, ListItem, Padding, Paragraph, Wrap},
    Frame,
};
use std::cell::RefCell;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use crate::app::{
    App, AppMode, MessageRole, ReviewDecisionState, ThemeMode, TimelineEntryKind,
    TranscriptSearchItemKind,
};
use crate::input::{command_palette_matches, SlashCommandSpec};
use crate::markdown;
use crate::theme;

struct ChatRenderCache {
    fingerprint: u64,
    theme_mode: ThemeMode,
    lines: Vec<Line<'static>>,
}

thread_local! {
    static CHAT_RENDER_CACHE: RefCell<Option<ChatRenderCache>> = const { RefCell::new(None) };
}

/// Main render function called each frame.
pub fn draw(frame: &mut Frame, app: &App) {
    frame.render_widget(
        Block::default().style(theme::app_background_style(app.theme_mode)),
        frame.area(),
    );

    let input_height = compute_input_height(app, frame.area().width);
    let activity_height = if show_activity_bar(app) { 1 } else { 0 };
    let has_presence = app.pair_mode_active && !app.connected_users.is_empty();
    let mut constraints = Vec::new();
    if has_presence {
        constraints.push(Constraint::Length(1));
    }
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
    draw_chat_area(frame, app, chunks[idx]);
    idx += 1;
    if activity_height > 0 {
        draw_activity_bar(frame, app, chunks[idx]);
    }
    idx += 1;
    draw_input_bar(frame, app, chunks[idx]);
    idx += 1;
    draw_hint_bar(frame, app, chunks[idx]);
    draw_command_palette(frame, app);

    // Overlays
    if app.mode == AppMode::ProviderSelect {
        draw_provider_select(frame, app);
    }
    if app.mode == AppMode::InfoPopup {
        draw_info_popup(frame, app);
    }
    if app.mode == AppMode::PermissionPrompt {
        draw_permission_prompt(frame, app);
    }
    if app.mode == AppMode::MutationReview {
        draw_mutation_review(frame, app);
    }
    if app.mode == AppMode::ContextInspector {
        draw_context_inspector(frame, app);
    }
    if app.mode == AppMode::QuickOpen {
        draw_quick_open(frame, app);
    }
    if app.mode == AppMode::Timeline {
        draw_timeline(frame, app);
    }
    if app.mode == AppMode::TranscriptSearch {
        draw_transcript_search(frame, app);
    }
    if app.mode == AppMode::PlanReview {
        draw_plan_review(frame, app);
    }
    if app.mode == AppMode::CompactSelect {
        draw_compact_select(frame, app);
    }
    if app.mode == AppMode::JoinWizard {
        draw_join_wizard(frame, app);
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
    for (i, user) in app.connected_users.iter().enumerate() {
        if i > 0 {
            spans.push(Span::styled(" · ", Style::default().fg(dim)));
        }
        spans.push(Span::styled(format!("{}", i + 1), Style::default().fg(dim)));
        spans.push(Span::styled(" ", Style::default()));
        let role_color = match user.role {
            crate::app::PairRole::Driver => theme::success(mode),
            crate::app::PairRole::Navigator => theme::accent(mode),
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
    if app.multiplayer_queue_depth > 0 {
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled(
            format!("queue:{}", app.multiplayer_queue_depth),
            Style::default().fg(theme::warning(mode)),
        ));
    }
    if !app.pair_short_code.is_empty() {
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled(
            format!("room:{}", app.pair_short_code),
            Style::default().fg(dim),
        ));
    }
    let bar = Paragraph::new(Line::from(spans)).style(theme::footer_style(mode));
    frame.render_widget(bar, area);
}

fn show_activity_bar(app: &App) -> bool {
    app.active_tool.is_some() || app.streaming_message.is_some() || app.waiting
}

fn draw_activity_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let mut spans = vec![Span::styled("  ", Style::default())];

    let (label, detail) = if let Some(tool) = &app.active_tool {
        (
            format!("{} {}", app.spinner_frame(), ellipsize_middle(tool, 22)),
            format!(
                "  [{}/{}]  {}",
                app.current_iteration,
                app.iteration_cap,
                app.wait_elapsed()
            ),
        )
    } else if app.streaming_message.is_some() {
        (
            format!("{} responding", app.thinking_frame()),
            format!("  {}  ·  Ctrl+C cancel", app.wait_elapsed()),
        )
    } else {
        let queue_detail = if app.prompt_queue.is_empty() {
            "type to queue".to_string()
        } else {
            format!("{} queued", app.prompt_queue.len())
        };
        (
            format!("{} thinking", app.thinking_frame()),
            format!(
                "  {}  ·  {}  ·  Ctrl+C cancel",
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

fn ellipsize_middle(value: &str, max_chars: usize) -> String {
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

fn draw_chat_area(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    if app.messages.is_empty() {
        CHAT_RENDER_CACHE.with(|cache| {
            cache.borrow_mut().take();
        });
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

    let all_lines = cached_chat_lines(app, mode);
    let text = Text::from(all_lines);
    let base_para = Paragraph::new(text).wrap(Wrap { trim: false });
    let total_lines = base_para.line_count(area.width).min(u16::MAX as usize) as u16;
    let visible_height = area.height;
    let max_scroll = total_lines.saturating_sub(visible_height);
    let effective_scroll = app.scroll_offset.min(max_scroll);
    let para = base_para.scroll((max_scroll.saturating_sub(effective_scroll), 0));

    frame.render_widget(para, area);
}

fn cached_chat_lines(app: &App, mode: ThemeMode) -> Vec<Line<'static>> {
    CHAT_RENDER_CACHE.with(|cache_cell| {
        let mut cache_ref = cache_cell.borrow_mut();
        let fingerprint = chat_fingerprint(app);

        let needs_rebuild = match cache_ref.as_ref() {
            Some(cache) => cache.fingerprint != fingerprint || cache.theme_mode != mode,
            None => true,
        };

        if needs_rebuild {
            *cache_ref = Some(ChatRenderCache {
                fingerprint,
                theme_mode: mode,
                lines: build_chat_lines(app, mode),
            });
        }

        let cache = cache_ref.as_mut().expect("chat cache must exist");
        cache.lines.clone()
    })
}

fn chat_fingerprint(app: &App) -> u64 {
    let mut hasher = DefaultHasher::new();
    app.messages.len().hash(&mut hasher);
    app.waiting.hash(&mut hasher);
    if app.waiting {
        app.spinner_tick.hash(&mut hasher);
    }
    for msg in &app.messages {
        role_fingerprint(&msg.role, &mut hasher);
        msg.content.len().hash(&mut hasher);
        if let Some(first) = msg.content.as_bytes().first() {
            first.hash(&mut hasher);
        }
        if let Some(last) = msg.content.as_bytes().last() {
            last.hash(&mut hasher);
        }
    }
    hasher.finish()
}

fn role_fingerprint(role: &MessageRole, hasher: &mut impl Hasher) {
    match role {
        MessageRole::Welcome => 0u8.hash(hasher),
        MessageRole::User => 1u8.hash(hasher),
        MessageRole::Assistant => 2u8.hash(hasher),
        MessageRole::System => 3u8.hash(hasher),
        MessageRole::ToolCall { name } => {
            4u8.hash(hasher);
            name.hash(hasher);
        }
        MessageRole::ToolResult { name } => {
            5u8.hash(hasher);
            name.hash(hasher);
        }
        MessageRole::DiffView { name } => {
            6u8.hash(hasher);
            name.hash(hasher);
        }
        MessageRole::Error => 7u8.hash(hasher),
    }
}

fn build_chat_lines(app: &App, mode: ThemeMode) -> Vec<Line<'static>> {
    let mut all_lines: Vec<Line<'static>> = Vec::new();

    for msg in &app.messages {
        if !all_lines.is_empty() {
            all_lines.push(Line::from(""));
        }

        match &msg.role {
            MessageRole::Welcome => {
                for (idx, line) in msg.content.lines().enumerate() {
                    let style = match idx {
                        0 => theme::brand_style(mode),
                        1 => Style::default()
                            .fg(theme::base_fg(mode))
                            .add_modifier(Modifier::BOLD),
                        2 | 3 => Style::default().fg(theme::muted_fg(mode)),
                        _ if line.starts_with('?') => Style::default()
                            .fg(theme::warning(mode))
                            .add_modifier(Modifier::BOLD),
                        _ if line.starts_with('/')
                            || line.starts_with('@')
                            || line.starts_with("Ctrl") =>
                        {
                            Style::default().fg(theme::base_fg(mode))
                        }
                        _ => Style::default().fg(theme::muted_fg(mode)),
                    };
                    let prefix = if idx == 0 { "  " } else { "    " };
                    all_lines.push(Line::from(Span::styled(format!("{prefix}{line}"), style)));
                }
            }
            MessageRole::User => {
                all_lines.push(Line::from(vec![
                    Span::styled("  › ", Style::default().fg(theme::user_color(mode))),
                    Span::styled("you", theme::user_label_style(mode)),
                ]));
                for line in msg.content.lines() {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(theme::base_fg(mode)),
                    )));
                }
            }
            MessageRole::Assistant => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ✦ ", Style::default().fg(theme::assistant_color(mode))),
                    Span::styled("poor-cli", theme::assistant_label_style(mode)),
                ]));
                let md_lines = markdown::render_markdown(&msg.content, mode);
                for ml in md_lines {
                    let mut padded_spans: Vec<Span<'static>> = vec![Span::raw("    ".to_string())];
                    padded_spans.extend(ml.spans);
                    all_lines.push(Line::from(padded_spans));
                }
            }
            MessageRole::System => {
                all_lines.push(Line::from(vec![
                    Span::styled("  · ", Style::default().fg(theme::system_color(mode))),
                    Span::styled(
                        "notice",
                        Style::default()
                            .fg(theme::system_color(mode))
                            .add_modifier(Modifier::BOLD),
                    ),
                ]));
                for line in msg.content.lines() {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(theme::muted_fg(mode)),
                    )));
                }
            }
            MessageRole::ToolCall { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ↳ ", theme::tool_border_style(mode)),
                    Span::styled(format!("tool {name}"), theme::tool_title_style(mode)),
                ]));
                for line in msg.content.lines().take(8) {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(theme::muted_fg(mode)),
                    )));
                }
                if msg.content.lines().count() > 8 {
                    all_lines.push(Line::from(Span::styled(
                        "    …".to_string(),
                        Style::default().fg(theme::muted_fg(mode)),
                    )));
                }
            }
            MessageRole::ToolResult { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ✓ ", Style::default().fg(theme::success(mode))),
                    Span::styled(format!("{name} result"), theme::tool_title_style(mode)),
                ]));
                let content = if msg.content.len() > 500 {
                    format!("{}…", &msg.content[..500])
                } else {
                    msg.content.clone()
                };
                for line in content.lines().take(15) {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(theme::muted_fg(mode)),
                    )));
                }
                if msg.content.lines().count() > 15 {
                    all_lines.push(Line::from(Span::styled(
                        "    …".to_string(),
                        Style::default().fg(theme::muted_fg(mode)),
                    )));
                }
            }
            MessageRole::DiffView { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ± ", Style::default().fg(theme::accent(mode))),
                    Span::styled(format!("{name} diff"), theme::tool_title_style(mode)),
                ]));
                for line in msg.content.lines().take(40) {
                    let (prefix, color) = if line.starts_with('+') && !line.starts_with("+++") {
                        ("    ", theme::success(mode))
                    } else if line.starts_with('-') && !line.starts_with("---") {
                        ("    ", theme::error(mode))
                    } else if line.starts_with("@@") {
                        ("    ", theme::accent(mode))
                    } else {
                        ("    ", theme::muted_fg(mode))
                    };
                    all_lines.push(Line::from(vec![
                        Span::styled(prefix.to_string(), Style::default().fg(color)),
                        Span::styled(line.to_string(), Style::default().fg(color)),
                    ]));
                }
                if msg.content.lines().count() > 40 {
                    all_lines.push(Line::from(Span::styled(
                        "    …".to_string(),
                        Style::default().fg(theme::muted_fg(mode)),
                    )));
                }
            }
            MessageRole::Error => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ! ", Style::default().fg(theme::error(mode))),
                    Span::styled("error", theme::error_style(mode)),
                ]));
                for line in msg.content.lines() {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(theme::error(mode)),
                    )));
                }
            }
        }
    }

    all_lines
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
            Span::styled(": open file", Style::default().fg(theme::muted_fg(mode))),
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

    let branch = if app.git_branch.is_empty() {
        String::new()
    } else {
        format!(
            " ({}{})",
            app.git_branch,
            if app.git_dirty { "*" } else { "" }
        )
    };
    let workspace = if app.cwd.trim().is_empty() {
        "~".to_string()
    } else {
        ellipsize_middle(&app.cwd, 22)
    };
    let model = if app.model_name.is_empty() {
        app.provider_name.clone()
    } else {
        format!("{}/{}", app.provider_name, app.model_name)
    };
    let transport = if app.server_connected {
        if app.is_local_provider {
            "local"
        } else {
            "remote"
        }
    } else {
        "offline"
    };
    let mut right = format!(
        "{}{} · {} · {}",
        workspace,
        branch,
        app.permission_mode_label,
        ellipsize_middle(&model, 20)
    );
    if app.multiplayer_enabled && !app.multiplayer_room.is_empty() {
        let role = if app.multiplayer_role.is_empty() {
            "?"
        } else {
            &app.multiplayer_role
        };
        right.push_str(&format!(" · {}/{}", app.multiplayer_room, role));
    } else if !app.execution_profile.is_empty() {
        right.push_str(&format!(" · {}", app.execution_profile));
    } else {
        right.push_str(&format!(" · {transport}"));
    }

    let left_candidates: Vec<String> = if !app.prompt_queue.is_empty() {
        vec![
            format!("queue {} · type to add more", app.prompt_queue.len()),
            format!("queue {}", app.prompt_queue.len()),
        ]
    } else if app.input_buffer.trim().is_empty() {
        vec![
            "? shortcuts · @ attach · /switch · /pair".to_string(),
            "? shortcuts".to_string(),
        ]
    } else {
        vec![
            "Enter send · Alt+↵ newline · Ctrl+P open".to_string(),
            "Enter send".to_string(),
        ]
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
    if app.waiting || !app.input_buffer.starts_with('/') {
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

    frame.render_widget(Clear, area);

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

// ── Provider select overlay ──────────────────────────────────────────

fn draw_provider_select(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(50, 60, frame.area());
    frame.render_widget(Clear, area);

    let items: Vec<ListItem> = app
        .providers
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let marker = if i == app.provider_select_idx {
                "▸ "
            } else {
                "  "
            };
            let status = if p.available { "✓" } else { "✗" };
            let models = if p.models.is_empty() {
                String::new()
            } else {
                format!(" ({})", p.models.join(", "))
            };
            let style = if i == app.provider_select_idx {
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD)
            } else if p.available {
                Style::default().fg(theme::base_fg(mode))
            } else {
                Style::default().fg(theme::muted_fg(mode))
            };

            let local_tag = if p.name.to_lowercase() == "ollama" {
                " [local]"
            } else {
                ""
            };

            ListItem::new(Line::from(Span::styled(
                format!("{marker}{status} {}{local_tag}{models}", p.name),
                style,
            )))
        })
        .collect();

    let list = List::new(items).block(
        Block::default()
            .title(Span::styled(
                " Switch Provider ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 1, 1)),
    );
    frame.render_widget(list, area);
}

fn annotate_copyable_items(content: &str) -> String {
    let parts: Vec<&str> = content.split('`').collect();
    if parts.len() < 3 {
        return content.to_string();
    } // no backtick pairs
    let mut result = String::with_capacity(content.len() + 64);
    let mut copy_idx = 0usize;
    for (i, part) in parts.iter().enumerate() {
        if i % 2 == 1 && !part.trim().is_empty() {
            copy_idx += 1;
            if copy_idx <= 9 {
                result.push_str(&format!("[{copy_idx}]`{part}`"));
            } else {
                result.push('`');
                result.push_str(part);
                result.push('`');
            }
        } else if i % 2 == 1 {
            result.push('`');
            result.push_str(part);
            result.push('`');
        } else {
            result.push_str(part);
        }
    }
    result
}

fn draw_info_popup(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(72, 72, frame.area());
    frame.render_widget(Clear, area);

    let title = if app.info_popup_title.trim().is_empty() {
        " Info "
    } else {
        app.info_popup_title.as_str()
    };

    let annotated = annotate_copyable_items(&app.info_popup_content);
    let markdown_lines = markdown::render_markdown(&annotated, mode);
    let popup = Paragraph::new(Text::from(markdown_lines))
        .wrap(Wrap { trim: false })
        .scroll((app.info_popup_scroll, 0))
        .block(
            Block::default()
                .title(Span::styled(
                    format!(" {title} "),
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD),
                ))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(theme::accent(mode)))
                .padding(Padding::new(1, 1, 1, 1)),
        );
    frame.render_widget(popup, area);
}

// ── Permission prompt overlay ────────────────────────────────────────

fn draw_permission_prompt(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(60, 30, frame.area());
    frame.render_widget(Clear, area);

    let text = vec![
        Line::from(""),
        Line::from(Span::styled(
            "  ⚠  Permission Required",
            Style::default()
                .fg(theme::warning(mode))
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
        Line::from(Span::styled(
            format!("  {}", app.permission_message),
            Style::default().fg(theme::base_fg(mode)),
        )),
        Line::from(""),
        Line::from(vec![
            Span::styled("  Press ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(
                "y",
                Style::default()
                    .fg(theme::success(mode))
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(" to allow, ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(
                "n",
                Style::default()
                    .fg(theme::error(mode))
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(" to deny", Style::default().fg(theme::muted_fg(mode))),
        ]),
        Line::from(""),
    ];

    let para = Paragraph::new(text).block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::warning(mode)))
            .padding(Padding::new(0, 0, 0, 0)),
    );
    frame.render_widget(para, area);
}

fn draw_mutation_review(frame: &mut Frame, app: &App) {
    let Some(review) = app.mutation_review.as_ref() else {
        return;
    };
    let mode = app.theme_mode;
    let area = centered_rect(82, 82, frame.area());
    frame.render_widget(Clear, area);

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),
            Constraint::Min(10),
            Constraint::Length(4),
        ])
        .split(area);

    let file_groups = review.file_groups();

    let mut header_lines = vec![
        Line::from(vec![
            Span::styled(" Review Before Apply ", theme::tool_title_style(mode)),
            Span::styled(
                format!("  {} / {}", review.tool_name, review.operation),
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ]),
        Line::from(Span::styled(
            if review.message.is_empty() {
                "Pending mutation preview".to_string()
            } else {
                review.message.clone()
            },
            Style::default().fg(theme::base_fg(mode)),
        )),
        Line::from(Span::styled(
            format!(
                "checkpoint: {}    changed: {}",
                review.checkpoint_id.as_deref().unwrap_or("(pending)"),
                review
                    .changed
                    .map(|changed| changed.to_string())
                    .unwrap_or_else(|| "unknown".to_string())
            ),
            Style::default().fg(theme::muted_fg(mode)),
        )),
    ];
    if review.supports_chunk_approval() {
        let selected_count = review.chunks.iter().filter(|chunk| chunk.selected).count();
        header_lines.push(Line::from(Span::styled(
            format!(
                "files: {}    hunks: {} selected / {} total",
                file_groups.len(),
                selected_count,
                review.chunks.len()
            ),
            Style::default().fg(theme::muted_fg(mode)),
        )));
    }
    if review.paths.is_empty() {
        header_lines.push(Line::from(Span::styled(
            "paths: (none reported)".to_string(),
            Style::default().fg(theme::muted_fg(mode)),
        )));
    } else {
        for (idx, path) in review.paths.iter().enumerate().take(3) {
            let marker = if idx == review.selected_path_index {
                "▸"
            } else {
                " "
            };
            header_lines.push(Line::from(Span::styled(
                format!("{marker} {path}"),
                if idx == review.selected_path_index {
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default().fg(theme::muted_fg(mode))
                },
            )));
        }
        if review.paths.len() > 3 {
            header_lines.push(Line::from(Span::styled(
                format!("… {} more paths", review.paths.len() - 3),
                Style::default().fg(theme::muted_fg(mode)),
            )));
        }
    }

    let header = Paragraph::new(header_lines).block(
        Block::default()
            .title(Span::styled(
                " Mutation Review ",
                Style::default()
                    .fg(theme::warning(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::warning(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(header, chunks[0]);

    let mut diff_lines: Vec<Line<'static>> = Vec::new();
    if review.diff.trim().is_empty() {
        diff_lines.push(Line::from(Span::styled(
            "No diff available for this mutation preview.".to_string(),
            Style::default().fg(theme::muted_fg(mode)),
        )));
    } else if review.chunks.is_empty() {
        diff_lines.extend(review.diff.lines().take(60).map(|line| {
            let style = if line.starts_with('+') && !line.starts_with("+++") {
                Style::default().fg(theme::success(mode))
            } else if line.starts_with('-') && !line.starts_with("---") {
                Style::default().fg(theme::error(mode))
            } else if line.starts_with("@@") {
                Style::default().fg(theme::accent(mode))
            } else {
                Style::default().fg(theme::base_fg(mode))
            };
            Line::from(Span::styled(line.to_string(), style))
        }));
    } else {
        let selected_file_group = review.selected_file_group_index();
        for (group_index, group) in file_groups.iter().enumerate() {
            let active_group = selected_file_group == Some(group_index);
            let (state_label, state_style) = match group.decision_state() {
                ReviewDecisionState::Accepted => {
                    ("accepted", Style::default().fg(theme::success(mode)))
                }
                ReviewDecisionState::Partial => {
                    ("partial", Style::default().fg(theme::warning(mode)))
                }
                ReviewDecisionState::Rejected => {
                    ("rejected", Style::default().fg(theme::error(mode)))
                }
            };
            diff_lines.push(Line::from(vec![
                Span::styled(
                    if active_group { "▾ " } else { "▸ " },
                    if active_group {
                        Style::default()
                            .fg(theme::accent(mode))
                            .add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(theme::muted_fg(mode))
                    },
                ),
                Span::styled(
                    group.path.clone(),
                    if active_group {
                        Style::default()
                            .fg(theme::base_fg(mode))
                            .add_modifier(Modifier::BOLD)
                    } else {
                        Style::default().fg(theme::base_fg(mode))
                    },
                ),
                Span::styled(
                    format!(
                        "  {}  {}/{} hunks selected",
                        state_label,
                        group.selected_chunks,
                        group.total_chunks()
                    ),
                    state_style,
                ),
            ]));

            for chunk_index in &group.chunk_indexes {
                let Some(chunk) = review.chunks.get(*chunk_index) else {
                    continue;
                };
                let selected = *chunk_index == review.selected_chunk_index;
                let marker = if chunk.selected { "[x]" } else { "[ ]" };
                diff_lines.push(Line::from(vec![
                    Span::styled(
                        format!(
                            "  {} {} hunk {}",
                            if selected { "▸" } else { " " },
                            marker,
                            chunk.hunk_index + 1
                        ),
                        if selected {
                            Style::default()
                                .fg(theme::accent(mode))
                                .add_modifier(Modifier::BOLD)
                        } else {
                            Style::default().fg(theme::muted_fg(mode))
                        },
                    ),
                    Span::styled(
                        format!("  {}", chunk.header),
                        Style::default().fg(theme::base_fg(mode)),
                    ),
                ]));
                if selected {
                    for line in chunk.diff.lines().take(12) {
                        let style = if line.starts_with('+') && !line.starts_with("+++") {
                            Style::default().fg(theme::success(mode))
                        } else if line.starts_with('-') && !line.starts_with("---") {
                            Style::default().fg(theme::error(mode))
                        } else if line.starts_with("@@") {
                            Style::default().fg(theme::accent(mode))
                        } else {
                            Style::default().fg(theme::muted_fg(mode))
                        };
                        diff_lines.push(Line::from(Span::styled(format!("      {line}"), style)));
                    }
                }
            }
            diff_lines.push(Line::from(""));
        }
    }
    let diff = Paragraph::new(Text::from(diff_lines))
        .wrap(Wrap { trim: false })
        .block(
            Block::default()
                .title(Span::styled(
                    " Diff ",
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD),
                ))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(theme::input_border_color(mode)))
                .padding(Padding::new(1, 1, 0, 0)),
        );
    frame.render_widget(diff, chunks[1]);

    let footer = Paragraph::new(Line::from(vec![
        Span::styled(" y/Enter ", Style::default().fg(theme::success(mode))),
        Span::styled("approve  ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(" n/Esc ", Style::default().fg(theme::error(mode))),
        Span::styled("reject  ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(" Space ", Style::default().fg(theme::accent(mode))),
        Span::styled("toggle hunk  ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(" Tab ", Style::default().fg(theme::accent(mode))),
        Span::styled("next file  ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(" Shift+Tab ", Style::default().fg(theme::accent(mode))),
        Span::styled("prev file", Style::default().fg(theme::muted_fg(mode))),
    ]))
    .wrap(Wrap { trim: false });

    let footer_block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(theme::input_border_color(mode)));
    frame.render_widget(footer_block, chunks[2]);
    frame.render_widget(
        footer,
        Rect {
            x: chunks[2].x + 1,
            y: chunks[2].y + 1,
            width: chunks[2].width.saturating_sub(2),
            height: 1,
        },
    );

    let footer_extra = Paragraph::new(Line::from(vec![
        Span::styled(" s/r ", Style::default().fg(theme::accent(mode))),
        Span::styled(
            "select or clear file  ",
            Style::default().fg(theme::muted_fg(mode)),
        ),
        Span::styled(" a/x ", Style::default().fg(theme::accent(mode))),
        Span::styled("all or none  ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(" h ", Style::default().fg(theme::accent(mode))),
        Span::styled(
            "approve hunks  ",
            Style::default().fg(theme::muted_fg(mode)),
        ),
        Span::styled(" f ", Style::default().fg(theme::accent(mode))),
        Span::styled(
            if review.paths.len() > 1 {
                "approve file  "
            } else {
                "approve current file  "
            },
            Style::default().fg(theme::muted_fg(mode)),
        ),
        Span::styled(" u/o ", Style::default().fg(theme::accent(mode))),
        Span::styled(
            "undo or open file",
            Style::default().fg(theme::muted_fg(mode)),
        ),
    ]))
    .wrap(Wrap { trim: false })
    .block(Block::default());
    frame.render_widget(
        footer_extra,
        Rect {
            x: chunks[2].x + 1,
            y: chunks[2].y + 2,
            width: chunks[2].width.saturating_sub(2),
            height: 1,
        },
    );
}

fn draw_context_inspector(frame: &mut Frame, app: &App) {
    let Some(inspector) = app.context_inspector.as_ref() else {
        return;
    };
    let mode = app.theme_mode;
    let area = centered_rect(82, 82, frame.area());
    frame.render_widget(Clear, area);

    let mut lines: Vec<Line<'static>> = vec![Line::from(Span::styled(
        format!(
            "Context budget: {} tokens  •  selected: ~{}  •  truncated: {}",
            inspector.budget_tokens, inspector.total_tokens, inspector.truncated
        ),
        Style::default().fg(theme::muted_fg(mode)),
    ))];
    if !inspector.message.is_empty() {
        lines.push(Line::from(Span::styled(
            inspector.message.clone(),
            Style::default().fg(theme::base_fg(mode)),
        )));
    }
    if !inspector.keywords.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("keywords: {}", inspector.keywords.join(", ")),
            Style::default().fg(theme::muted_fg(mode)),
        )));
    }
    lines.push(Line::from(""));

    for group in ["explicit", "pinned", "git", "auto"] {
        let group_files: Vec<_> = inspector
            .files
            .iter()
            .enumerate()
            .filter(|(_, file)| file.source == group)
            .collect();
        if group_files.is_empty() {
            continue;
        }
        lines.push(Line::from(Span::styled(
            format!("{} files", group.to_uppercase()),
            Style::default()
                .fg(theme::accent(mode))
                .add_modifier(Modifier::BOLD),
        )));
        for (index, file) in group_files {
            let marker = if index == inspector.selected_index {
                "▸"
            } else {
                " "
            };
            let label_style = if index == inspector.selected_index {
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme::base_fg(mode))
            };
            lines.push(Line::from(vec![
                Span::styled(format!("{marker} "), label_style),
                Span::styled(file.path.clone(), label_style),
                Span::styled(
                    format!(
                        "  (~{} tok{})",
                        file.estimated_tokens,
                        if file.include_full_content {
                            ", full"
                        } else {
                            ""
                        }
                    ),
                    Style::default().fg(theme::muted_fg(mode)),
                ),
            ]));
            if !file.reason.is_empty() {
                lines.push(Line::from(Span::styled(
                    format!("    {}", file.reason),
                    Style::default().fg(theme::muted_fg(mode)),
                )));
            }
        }
        lines.push(Line::from(""));
    }

    let para = Paragraph::new(lines).wrap(Wrap { trim: false }).block(
        Block::default()
            .title(Span::styled(
                " Context Inspector ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 1, 1)),
    );
    frame.render_widget(para, area);
}

fn draw_quick_open(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(72, 70, frame.area());
    frame.render_widget(Clear, area);

    let query = app.quick_open.query.trim().to_lowercase();
    let filtered: Vec<_> = app
        .quick_open
        .items
        .iter()
        .filter(|item| {
            query.is_empty()
                || item.label.to_lowercase().contains(&query)
                || item.detail.to_lowercase().contains(&query)
                || item.value.to_lowercase().contains(&query)
        })
        .take(12)
        .collect();

    let items: Vec<ListItem> = filtered
        .iter()
        .enumerate()
        .map(|(idx, item)| {
            let is_selected = idx == app.quick_open.selected_index;
            let style = if is_selected {
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme::base_fg(mode))
            };
            ListItem::new(Line::from(vec![
                Span::styled(if is_selected { "▸ " } else { "  " }, style),
                Span::styled(item.label.clone(), style),
                Span::styled(
                    format!("  {}", item.detail),
                    Style::default().fg(theme::muted_fg(mode)),
                ),
            ]))
        })
        .collect();

    let list = List::new(items).block(
        Block::default()
            .title(Span::styled(
                format!(" Quick Open  query=`{}` ", app.quick_open.query),
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 1, 1)),
    );
    frame.render_widget(list, area);
}

fn draw_timeline(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(82, 82, frame.area());
    frame.render_widget(Clear, area);

    let mut lines: Vec<Line<'static>> = Vec::new();
    for entry in app.timeline_entries.iter().rev() {
        let (label, color) = match entry.kind {
            TimelineEntryKind::Phase => ("phase", theme::accent(mode)),
            TimelineEntryKind::ToolCall => ("call", theme::warning(mode)),
            TimelineEntryKind::ToolResult => ("result", theme::success(mode)),
            TimelineEntryKind::Permission => ("review", theme::warning(mode)),
            TimelineEntryKind::Diff => ("diff", theme::accent(mode)),
            TimelineEntryKind::Cost => ("cost", theme::muted_fg(mode)),
            TimelineEntryKind::Note => ("note", theme::system_color(mode)),
        };
        lines.push(Line::from(vec![
            Span::styled(format!("[{label}] "), Style::default().fg(color)),
            Span::styled(
                entry.title.clone(),
                Style::default()
                    .fg(theme::base_fg(mode))
                    .add_modifier(Modifier::BOLD),
            ),
        ]));
        if !entry.detail.is_empty() {
            lines.push(Line::from(Span::styled(
                format!("  {}", entry.detail),
                Style::default().fg(theme::muted_fg(mode)),
            )));
        }
        if !entry.paths.is_empty() {
            lines.push(Line::from(Span::styled(
                format!("  paths: {}", entry.paths.join(", ")),
                Style::default().fg(theme::muted_fg(mode)),
            )));
        }
        if let Some(checkpoint_id) = &entry.checkpoint_id {
            lines.push(Line::from(Span::styled(
                format!("  checkpoint: {checkpoint_id}"),
                Style::default().fg(theme::muted_fg(mode)),
            )));
        }
        if let Some(summary) = &entry.review_summary {
            let max_files = 8usize;
            for file_summary in summary.files.iter().take(max_files) {
                let style = match file_summary.state {
                    ReviewDecisionState::Accepted => Style::default().fg(theme::success(mode)),
                    ReviewDecisionState::Partial => Style::default().fg(theme::warning(mode)),
                    ReviewDecisionState::Rejected => Style::default().fg(theme::error(mode)),
                };
                lines.push(Line::from(Span::styled(
                    format!("  {}", file_summary.summary_line()),
                    style,
                )));
            }
            if summary.files.len() > max_files {
                lines.push(Line::from(Span::styled(
                    format!(
                        "  … {} more reviewed files",
                        summary.files.len() - max_files
                    ),
                    Style::default().fg(theme::muted_fg(mode)),
                )));
            }
        }
        if !entry.diff.is_empty() {
            for diff_line in entry.diff.lines().take(8) {
                let style = if diff_line.starts_with('+') && !diff_line.starts_with("+++") {
                    Style::default().fg(theme::success(mode))
                } else if diff_line.starts_with('-') && !diff_line.starts_with("---") {
                    Style::default().fg(theme::error(mode))
                } else if diff_line.starts_with("@@") {
                    Style::default().fg(theme::accent(mode))
                } else {
                    Style::default().fg(theme::muted_fg(mode))
                };
                lines.push(Line::from(Span::styled(format!("  {diff_line}"), style)));
            }
        }
        lines.push(Line::from(""));
    }

    let para = Paragraph::new(lines)
        .scroll((app.timeline_scroll, 0))
        .wrap(Wrap { trim: false })
        .block(
            Block::default()
                .title(Span::styled(
                    " Agent Timeline ",
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD),
                ))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(theme::accent(mode)))
                .padding(Padding::new(1, 1, 1, 1)),
        );
    frame.render_widget(para, area);
}

fn draw_transcript_search(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(84, 84, frame.area());
    frame.render_widget(Clear, area);

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(4),
            Constraint::Min(10),
            Constraint::Length(2),
        ])
        .split(area);

    let filters = if app.transcript_search.include_messages
        && app.transcript_search.include_tools
        && app.transcript_search.include_diffs
    {
        "all"
    } else if app.transcript_search.include_messages {
        "messages"
    } else if app.transcript_search.include_tools {
        "tools"
    } else if app.transcript_search.include_diffs {
        "diffs"
    } else {
        "none"
    };

    let header = Paragraph::new(vec![
        Line::from(vec![
            Span::styled(" Query: ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(
                if app.transcript_search.query.is_empty() {
                    "(latest transcript entries)".to_string()
                } else {
                    app.transcript_search.query.clone()
                },
                Style::default().fg(theme::base_fg(mode)),
            ),
        ]),
        Line::from(Span::styled(
            format!("Filter group: {filters}  •  Tab cycles all / messages / tools / diffs"),
            Style::default().fg(theme::muted_fg(mode)),
        )),
    ])
    .block(
        Block::default()
            .title(Span::styled(
                " Transcript Search ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(header, chunks[0]);

    let items = app.transcript_search_items();
    let mut lines: Vec<Line<'static>> = Vec::new();
    if items.is_empty() {
        lines.push(Line::from(Span::styled(
            "No transcript entries match the current search.",
            Style::default().fg(theme::muted_fg(mode)),
        )));
    } else {
        for (idx, item) in items.iter().enumerate() {
            let selected = idx == app.transcript_search.selected_index;
            let accent = if selected {
                theme::accent(mode)
            } else {
                theme::muted_fg(mode)
            };
            let kind_label = match item.kind {
                TranscriptSearchItemKind::Message => "msg",
                TranscriptSearchItemKind::Tool => "tool",
                TranscriptSearchItemKind::Diff => "diff",
            };
            lines.push(Line::from(vec![
                Span::styled(
                    if selected { "▸ " } else { "  " },
                    Style::default().fg(accent),
                ),
                Span::styled(format!("[{kind_label}] "), Style::default().fg(accent)),
                Span::styled(
                    item.label.clone(),
                    Style::default()
                        .fg(theme::base_fg(mode))
                        .add_modifier(if selected {
                            Modifier::BOLD
                        } else {
                            Modifier::empty()
                        }),
                ),
            ]));

            if !item.paths.is_empty() {
                lines.push(Line::from(Span::styled(
                    format!("    paths: {}", item.paths.join(", ")),
                    Style::default().fg(theme::muted_fg(mode)),
                )));
            }

            let detail = if item.kind == TranscriptSearchItemKind::Diff && !item.diff.is_empty() {
                item.diff.clone()
            } else {
                item.detail.clone()
            };
            for detail_line in detail.lines().take(if selected { 8 } else { 2 }) {
                let style = if detail_line.starts_with('+') && !detail_line.starts_with("+++") {
                    Style::default().fg(theme::success(mode))
                } else if detail_line.starts_with('-') && !detail_line.starts_with("---") {
                    Style::default().fg(theme::error(mode))
                } else if detail_line.starts_with("@@") {
                    Style::default().fg(theme::accent(mode))
                } else {
                    Style::default().fg(theme::muted_fg(mode))
                };
                lines.push(Line::from(Span::styled(
                    format!("    {detail_line}"),
                    style,
                )));
            }
            lines.push(Line::from(""));
        }
    }

    let body = Paragraph::new(lines).wrap(Wrap { trim: false }).block(
        Block::default()
            .title(Span::styled(
                format!(" Results ({}) ", items.len()),
                Style::default()
                    .fg(theme::input_border_color(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::input_border_color(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(body, chunks[1]);

    let footer = Paragraph::new(Line::from(vec![
        Span::styled(" type ", Style::default().fg(theme::accent(mode))),
        Span::styled("search  ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled("Tab ", Style::default().fg(theme::accent(mode))),
        Span::styled("cycle filter  ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled("Esc ", Style::default().fg(theme::accent(mode))),
        Span::styled("close", Style::default().fg(theme::muted_fg(mode))),
    ]))
    .block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::input_border_color(mode))),
    );
    frame.render_widget(footer, chunks[2]);
}

// ── Plan review overlay ──────────────────────────────────────────────

fn draw_plan_review(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(70, 70, frame.area());
    frame.render_widget(Clear, area);

    let mut lines: Vec<Line<'static>> = vec![
        Line::from(""),
        Line::from(Span::styled(
            "  📋 Plan Review",
            Style::default()
                .fg(theme::accent(mode))
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
    ];

    if !app.plan_summary.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("  {}", app.plan_summary),
            Style::default().fg(theme::muted_fg(mode)),
        )));
        lines.push(Line::from(""));
    }

    if !app.plan_original_request.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("  Request: ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(
                app.plan_original_request.clone(),
                Style::default().fg(theme::base_fg(mode)),
            ),
        ]));
        lines.push(Line::from(""));
    }

    for (i, step) in app.plan_steps.iter().enumerate() {
        let (marker, style) = match step.status {
            crate::app::PlanStepStatus::Pending => {
                if i == app.plan_current_step {
                    (
                        "▸ ",
                        Style::default()
                            .fg(theme::base_fg(mode))
                            .add_modifier(Modifier::BOLD),
                    )
                } else {
                    ("  ", Style::default().fg(theme::muted_fg(mode)))
                }
            }
            crate::app::PlanStepStatus::Running => ("⠋ ", Style::default().fg(theme::accent(mode))),
            crate::app::PlanStepStatus::Done => ("✓ ", Style::default().fg(theme::success(mode))),
            crate::app::PlanStepStatus::Skipped => {
                ("✗ ", Style::default().fg(theme::muted_fg(mode)))
            }
        };
        lines.push(Line::from(Span::styled(
            format!("  {marker}{}", step.description),
            style,
        )));
    }

    lines.push(Line::from(""));
    lines.push(Line::from(vec![
        Span::styled("  Press ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(
            "Enter",
            Style::default()
                .fg(theme::success(mode))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            if app.plan_is_execution_gate {
                " to approve, "
            } else {
                " to execute, "
            },
            Style::default().fg(theme::muted_fg(mode)),
        ),
        Span::styled(
            "Esc",
            Style::default()
                .fg(theme::error(mode))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            if app.plan_is_execution_gate {
                " to reject"
            } else {
                " to cancel"
            },
            Style::default().fg(theme::muted_fg(mode)),
        ),
    ]));
    lines.push(Line::from(""));

    let para = Paragraph::new(lines).block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(0, 0, 0, 0)),
    );
    frame.render_widget(para, area);
}

// ── Compact select overlay ───────────────────────────────────────────

fn draw_compact_select(frame: &mut Frame, app: &App) {
    use crate::app::COMPACT_STRATEGIES;
    let mode = app.theme_mode;
    let area = frame.area();
    let popup_width = 52.min(area.width.saturating_sub(4));
    let popup_height = (COMPACT_STRATEGIES.len() as u16 + 4).min(area.height.saturating_sub(4));
    let x = (area.width.saturating_sub(popup_width)) / 2;
    let y = (area.height.saturating_sub(popup_height)) / 2;
    let popup_area = Rect::new(x, y, popup_width, popup_height);

    frame.render_widget(Clear, popup_area);

    let items: Vec<ListItem> = COMPACT_STRATEGIES
        .iter()
        .enumerate()
        .map(|(i, (key, desc))| {
            let marker = if i == app.compact_select_idx {
                "▸ "
            } else {
                "  "
            };
            let style = if i == app.compact_select_idx {
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme::base_fg(mode))
            };
            ListItem::new(Line::from(Span::styled(
                format!("{marker}{key:<10} {desc}"),
                style,
            )))
        })
        .collect();

    let list = List::new(items).block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .title(" Context Strategy (↑/↓ Enter) ")
            .title_style(
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            )
            .padding(Padding::new(1, 1, 1, 0)),
    );
    frame.render_widget(list, popup_area);
}

// ── Join wizard overlay ──────────────────────────────────────────────

fn draw_join_wizard(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(55, 30, frame.area());
    frame.render_widget(Clear, area);
    let step = app.join_wizard_step;
    let (step_label, prompt) = match step {
        0 => ("1/3", "WebSocket URL (ws://host:port/rpc)"),
        1 => ("2/3", "Room name"),
        _ => ("3/3", "Invite token"),
    };
    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            format!("  Join Server — Step {step_label}"),
            Style::default()
                .fg(theme::accent(mode))
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
        Line::from(Span::styled(
            format!("  {prompt}:"),
            Style::default().fg(theme::base_fg(mode)),
        )),
        Line::from(Span::styled(
            format!("  > {}_", app.join_wizard_input),
            Style::default().fg(theme::accent(mode)),
        )),
    ];
    if !app.join_wizard_error.is_empty() {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            format!("  ⚠ {}", app.join_wizard_error),
            Style::default().fg(theme::error(mode)),
        )));
    }
    if step > 0 {
        lines.push(Line::from(""));
        if !app.join_wizard_url.is_empty() {
            lines.push(Line::from(Span::styled(
                format!("  URL: {}", app.join_wizard_url),
                Style::default().fg(theme::muted_fg(mode)),
            )));
        }
        if step > 1 && !app.join_wizard_room.is_empty() {
            lines.push(Line::from(Span::styled(
                format!("  Room: {}", app.join_wizard_room),
                Style::default().fg(theme::muted_fg(mode)),
            )));
        }
    }
    lines.push(Line::from(""));
    let popup = Paragraph::new(lines).block(
        Block::default()
            .title(Span::styled(
                " Join Server ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(popup, area);
}

// ── Helpers ──────────────────────────────────────────────────────────

/// Create a centered rectangle with percentage-based width/height.
fn centered_rect(percent_x: u16, percent_y: u16, area: Rect) -> Rect {
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
