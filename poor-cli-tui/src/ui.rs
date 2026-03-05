/// TUI layout renderer — Claude Code / Codex inspired interface.
///
/// Layout:
/// ┌───────────────────────────────────────────┐
/// │ status bar (provider, model, streaming)    │
/// ├───────────────────────────────────────────┤
/// │ chat messages area (scrollable)           │
/// │   ● You / ● Assistant / tool panels       │
/// ├───────────────────────────────────────────┤
/// │ input bar + hints                          │
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

use crate::app::{App, AppMode, MessageRole, ThemeMode};
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
    let input_height = {
        let newlines = app.input_buffer.matches('\n').count();
        (newlines as u16 + 3).min(8) // 3 base + extra lines, cap at 8
    };
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(1),            // status bar
            Constraint::Min(5),               // chat area
            Constraint::Length(input_height), // input area (grows for multi-line)
            Constraint::Length(1),            // hint bar
        ])
        .split(frame.area());

    draw_status_bar(frame, app, chunks[0]);
    draw_chat_area(frame, app, chunks[1]);
    draw_input_bar(frame, app, chunks[2]);
    draw_hint_bar(frame, app, chunks[3]);
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
    if app.mode == AppMode::PlanReview {
        draw_plan_review(frame, app);
    }
}

// ── Status bar ───────────────────────────────────────────────────────

fn draw_status_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let dim = theme::muted_fg(mode);
    let model_full = format!("{}/{}", app.provider_name, app.model_name);
    let model_display = ellipsize_middle(&model_full, 34);
    let (status_label, status_color) = if !app.server_connected {
        ("offline", theme::error(mode))
    } else if app.waiting || app.streaming_message.is_some() {
        ("busy", theme::warning(mode))
    } else {
        ("online", theme::success(mode))
    };

    let mut spans = vec![
        Span::styled(
            "  poor-cli",
            Style::default()
                .fg(theme::accent(mode))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(format!(" v{} ", app.version), Style::default().fg(dim)),
        Span::styled("│ ", Style::default().fg(dim)),
        Span::styled("model:", Style::default().fg(dim)),
        Span::styled(
            format!(" {model_display}"),
            Style::default()
                .fg(theme::system_color(mode))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" │ ", Style::default().fg(dim)),
        Span::styled("status:", Style::default().fg(dim)),
        Span::styled(" ", Style::default().fg(dim)),
        Span::styled("●", Style::default().fg(status_color)),
        Span::styled(
            format!(" {status_label}"),
            Style::default().fg(status_color),
        ),
    ];

    if app.streaming_enabled {
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled(
            "streaming",
            Style::default().fg(theme::success(mode)),
        ));
    }

    if app.is_local_provider {
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled("[local]", theme::local_badge_style(mode)));
    }

    // Show real token counts if available, else estimates
    let real_total = app.cumulative_input_tokens + app.cumulative_output_tokens;
    if real_total > 0 {
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled(
            format!("{}tok", real_total),
            Style::default().fg(dim),
        ));
        if app.turn_input_tokens + app.turn_output_tokens > 0 {
            spans.push(Span::styled(
                format!(
                    " (turn: {})",
                    app.turn_input_tokens + app.turn_output_tokens
                ),
                Style::default().fg(theme::muted_fg(mode)),
            ));
        }
    } else {
        let total_tokens = app.input_tokens_estimate + app.output_tokens_estimate;
        if total_tokens > 0 {
            spans.push(Span::styled(" │ ", Style::default().fg(dim)));
            spans.push(Span::styled(
                format!("~{total_tokens}tok"),
                Style::default().fg(dim),
            ));
        }
    }

    if !app.cwd.is_empty() {
        let cwd_short = app.cwd.split('/').last().unwrap_or(&app.cwd);
        spans.push(Span::styled(" │ ", Style::default().fg(dim)));
        spans.push(Span::styled(
            format!("~/{cwd_short}"),
            Style::default().fg(dim),
        ));
    }

    // Waiting indicator on the right side
    if app.waiting {
        let elapsed = app.wait_elapsed();
        let right_text = if let Some(tool) = &app.active_tool {
            format!(
                " [{}/{}] Running: {tool}… {elapsed} ",
                app.current_iteration, app.iteration_cap
            )
        } else if app.streaming_message.is_some() {
            format!(" {} streaming… {elapsed} ", app.spinner_frame())
        } else {
            format!(" {} thinking… {elapsed} ", app.spinner_frame())
        };
        let used_width: usize = spans.iter().map(|s| s.content.len()).sum();
        let remaining = (area.width as usize).saturating_sub(used_width + right_text.len());
        if remaining > 0 {
            spans.push(Span::raw(" ".repeat(remaining)));
        }
        spans.push(Span::styled(
            right_text,
            Style::default().fg(theme::accent(mode)),
        ));
    }

    let bar = Paragraph::new(Line::from(spans)).style(theme::status_bar_style(mode));
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
        MessageRole::User => 0u8.hash(hasher),
        MessageRole::Assistant => 1u8.hash(hasher),
        MessageRole::System => 2u8.hash(hasher),
        MessageRole::ToolCall { name } => {
            3u8.hash(hasher);
            name.hash(hasher);
        }
        MessageRole::ToolResult { name } => {
            4u8.hash(hasher);
            name.hash(hasher);
        }
        MessageRole::DiffView { name } => {
            5u8.hash(hasher);
            name.hash(hasher);
        }
        MessageRole::Error => 6u8.hash(hasher),
    }
}

fn build_chat_lines(app: &App, mode: ThemeMode) -> Vec<Line<'static>> {
    let mut all_lines: Vec<Line<'static>> = Vec::new();

    for msg in &app.messages {
        all_lines.push(Line::from("")); // spacing

        match &msg.role {
            MessageRole::User => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ● ", Style::default().fg(theme::user_color(mode))),
                    Span::styled("You", theme::user_label_style(mode)),
                ]));
                // Render user content with simple wrapping
                for line in msg.content.lines() {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(theme::base_fg(mode)),
                    )));
                }
            }
            MessageRole::Assistant => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ● ", Style::default().fg(theme::assistant_color(mode))),
                    Span::styled("Assistant", theme::assistant_label_style(mode)),
                ]));
                // Render assistant content as markdown
                let md_lines = markdown::render_markdown(&msg.content, mode);
                for ml in md_lines {
                    let mut padded_spans: Vec<Span<'static>> = vec![Span::raw("    ".to_string())];
                    padded_spans.extend(ml.spans);
                    all_lines.push(Line::from(padded_spans));
                }
            }
            MessageRole::System => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ◆ ", Style::default().fg(theme::system_color(mode))),
                    Span::styled(
                        "System",
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
                    Span::styled("  ┌─ ", theme::tool_border_style(mode)),
                    Span::styled(name.clone(), theme::tool_title_style(mode)),
                    Span::styled(" ──────────────", theme::tool_border_style(mode)),
                ]));
                for line in msg.content.lines() {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style(mode)),
                        Span::styled(line.to_string(), Style::default().fg(theme::muted_fg(mode))),
                    ]));
                }
                all_lines.push(Line::from(Span::styled(
                    "  └────────────────────",
                    theme::tool_border_style(mode),
                )));
            }
            MessageRole::ToolResult { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ┌─ ", theme::tool_border_style(mode)),
                    Span::styled(format!("{name} result"), theme::tool_title_style(mode)),
                    Span::styled(" ─────", theme::tool_border_style(mode)),
                ]));
                // Truncate long tool output
                let content = if msg.content.len() > 500 {
                    format!("{}…", &msg.content[..500])
                } else {
                    msg.content.clone()
                };
                for line in content.lines().take(15) {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style(mode)),
                        Span::styled(line.to_string(), Style::default().fg(theme::muted_fg(mode))),
                    ]));
                }
                if msg.content.lines().count() > 15 {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style(mode)),
                        Span::styled(
                            "... (truncated)".to_string(),
                            Style::default().fg(theme::muted_fg(mode)),
                        ),
                    ]));
                }
                all_lines.push(Line::from(Span::styled(
                    "  └────────────────────",
                    theme::tool_border_style(mode),
                )));
            }
            MessageRole::DiffView { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ┌─ ", theme::tool_border_style(mode)),
                    Span::styled(format!("{name} diff"), theme::tool_title_style(mode)),
                    Span::styled(" ─────", theme::tool_border_style(mode)),
                ]));
                for line in msg.content.lines().take(40) {
                    let (prefix, style) = if line.starts_with('+') && !line.starts_with("+++") {
                        ("  │+", Style::default().fg(theme::success(mode)))
                    } else if line.starts_with('-') && !line.starts_with("---") {
                        ("  │-", Style::default().fg(theme::error(mode)))
                    } else if line.starts_with("@@") {
                        ("  │ ", Style::default().fg(theme::accent(mode)))
                    } else {
                        ("  │ ", Style::default().fg(theme::muted_fg(mode)))
                    };
                    all_lines.push(Line::from(vec![
                        Span::styled(prefix.to_string(), theme::tool_border_style(mode)),
                        Span::styled(line.to_string(), style),
                    ]));
                }
                if msg.content.lines().count() > 40 {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style(mode)),
                        Span::styled(
                            "... (truncated)".to_string(),
                            Style::default().fg(theme::muted_fg(mode)),
                        ),
                    ]));
                }
                all_lines.push(Line::from(Span::styled(
                    "  └────────────────────",
                    theme::tool_border_style(mode),
                )));
            }
            MessageRole::Error => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ⚠ ", Style::default().fg(theme::error(mode))),
                    Span::styled("Error", theme::error_style(mode)),
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
    if app.waiting {
        let prompt_spans = vec![
            Span::styled("  ", Style::default()),
            Span::styled(app.spinner_frame(), theme::spinner_style(mode)),
            Span::styled(
                " Waiting for response... ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ];
        let input = Paragraph::new(Line::from(prompt_spans)).block(
            Block::default()
                .borders(Borders::TOP)
                .border_style(Style::default().fg(theme::input_border_color(mode)))
                .padding(Padding::new(0, 0, 0, 0)),
        );
        frame.render_widget(input, area);
        return;
    }

    let provider_short = if app.provider_name.len() > 4 {
        &app.provider_name[..4]
    } else {
        &app.provider_name
    };

    // Multi-line input: split by newlines
    let line_count = app.input_buffer.matches('\n').count() + 1;
    if line_count > 1 {
        let mut lines: Vec<Line<'static>> = Vec::new();
        for (i, part) in app.input_buffer.split('\n').enumerate() {
            let prefix = if i == 0 { "  ❯ " } else { "  … " };
            lines.push(Line::from(vec![
                Span::styled(
                    prefix.to_string(),
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD),
                ),
                Span::styled(part.to_string(), theme::input_style(mode)),
            ]));
        }
        let input = Paragraph::new(lines).block(
            Block::default()
                .borders(Borders::TOP)
                .border_style(Style::default().fg(theme::input_border_color(mode))),
        );
        frame.render_widget(input, area);
    } else {
        let prompt_spans = vec![
            Span::styled("  ", Style::default()),
            Span::styled(
                "❯ ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(app.input_buffer.clone(), theme::input_style(mode)),
            Span::styled("█", theme::input_cursor_style(mode)),
            if app.input_buffer.is_empty() {
                Span::styled(
                    format!(" Type your message ({})...", provider_short.to_uppercase()),
                    Style::default().fg(theme::muted_fg(mode)),
                )
            } else {
                Span::raw("")
            },
        ];
        let input = Paragraph::new(Line::from(prompt_spans)).block(
            Block::default()
                .borders(Borders::TOP)
                .border_style(Style::default().fg(theme::input_border_color(mode)))
                .padding(Padding::new(0, 0, 0, 0)),
        );
        frame.render_widget(input, area);
    }
}

// ── Hint bar ─────────────────────────────────────────────────────────

fn draw_hint_bar(frame: &mut Frame, app: &App, area: Rect) {
    let mode = app.theme_mode;
    let spans = if let Some((status, _)) = &app.status_message {
        vec![Span::styled(
            format!("  {status}"),
            Style::default().fg(theme::warning(mode)),
        )]
    } else if app.mode == AppMode::InfoPopup {
        vec![
            Span::styled("  Esc/Enter", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": close  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("↑↓", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": scroll  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("PgUp/PgDn", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": fast scroll", Style::default().fg(theme::muted_fg(mode))),
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
        let mut spans = Vec::new();
        if app.multiplayer_enabled {
            let room = if app.multiplayer_room.is_empty() {
                "?"
            } else {
                &app.multiplayer_room
            };
            let role = if app.multiplayer_role.is_empty() {
                "?"
            } else {
                &app.multiplayer_role
            };
            spans.push(Span::styled(
                format!(
                    "  mp:{room}/{role} members:{} queue:{}  ",
                    app.multiplayer_member_count, app.multiplayer_queue_depth
                ),
                Style::default().fg(theme::accent(mode)),
            ));
        }
        if !app.execution_profile.is_empty() {
            spans.push(Span::styled(
                format!(" profile:{}  ", app.execution_profile),
                Style::default().fg(theme::system_color(mode)),
            ));
        }
        if app.qa_mode_enabled {
            spans.push(Span::styled(
                " qa:running  ",
                Style::default().fg(theme::success(mode)),
            ));
        }
        spans.extend(vec![
            Span::styled("  /help", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("  /quit", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("  /switch", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("  Ctrl+C", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": cancel  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Esc", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": cancel  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("Alt+↵", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": newline  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("PgUp/PgDn", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": scroll  ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled("↑↓", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(": history", Style::default().fg(theme::muted_fg(mode))),
        ]);
        spans
    };

    let hint = Paragraph::new(Line::from(spans)).style(theme::hint_style(mode));
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

fn draw_info_popup(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(72, 72, frame.area());
    frame.render_widget(Clear, area);

    let title = if app.info_popup_title.trim().is_empty() {
        " Info "
    } else {
        app.info_popup_title.as_str()
    };

    let markdown_lines = markdown::render_markdown(&app.info_popup_content, mode);
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
        Span::styled(" to execute, ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(
            "Esc",
            Style::default()
                .fg(theme::error(mode))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(" to cancel", Style::default().fg(theme::muted_fg(mode))),
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
