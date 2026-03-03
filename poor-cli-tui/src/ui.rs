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
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, Clear, List, ListItem, Padding, Paragraph, Wrap},
    Frame,
};

use crate::app::{App, AppMode, MessageRole};
use crate::input::{SlashCommandSpec, SLASH_COMMANDS};
use crate::markdown;
use crate::theme;

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
            Constraint::Length(input_height),  // input area (grows for multi-line)
            Constraint::Length(1),             // hint bar
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
    if app.mode == AppMode::PermissionPrompt {
        draw_permission_prompt(frame, app);
    }
}

// ── Status bar ───────────────────────────────────────────────────────

fn draw_status_bar(frame: &mut Frame, app: &App, area: Rect) {
    let provider_short = if app.provider_name.len() > 4 {
        &app.provider_name[..4]
    } else {
        &app.provider_name
    };
    let provider_upper = provider_short.to_uppercase();

    let model_display = app.model_name.split('-').last().unwrap_or(&app.model_name);

    let mut spans = vec![
        Span::styled(
            "  poor-cli",
            Style::default()
                .fg(Color::Cyan)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!(" v{} ", app.version),
            Style::default().fg(Color::DarkGray),
        ),
        Span::styled("│ ", Style::default().fg(Color::DarkGray)),
        Span::styled(
            format!("{provider_upper}"),
            Style::default()
                .fg(Color::Magenta)
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            format!("/{model_display}"),
            Style::default().fg(Color::DarkGray),
        ),
    ];

    if app.streaming_enabled {
        spans.push(Span::styled(" │ ", Style::default().fg(Color::DarkGray)));
        spans.push(Span::styled("streaming", Style::default().fg(Color::Green)));
    }

    if app.is_local_provider {
        spans.push(Span::styled(" │ ", Style::default().fg(Color::DarkGray)));
        spans.push(Span::styled("[local]", theme::local_badge_style()));
    }

    // Show real token counts if available, else estimates
    let real_total = app.cumulative_input_tokens + app.cumulative_output_tokens;
    if real_total > 0 {
        spans.push(Span::styled(" │ ", Style::default().fg(Color::DarkGray)));
        spans.push(Span::styled(
            format!("{}tok", real_total),
            Style::default().fg(Color::DarkGray),
        ));
        if app.turn_input_tokens + app.turn_output_tokens > 0 {
            spans.push(Span::styled(
                format!(" (turn: {})", app.turn_input_tokens + app.turn_output_tokens),
                Style::default().fg(Color::Rgb(80, 80, 100)),
            ));
        }
    } else {
        let total_tokens = app.input_tokens_estimate + app.output_tokens_estimate;
        if total_tokens > 0 {
            spans.push(Span::styled(" │ ", Style::default().fg(Color::DarkGray)));
            spans.push(Span::styled(
                format!("~{total_tokens}tok"),
                Style::default().fg(Color::DarkGray),
            ));
        }
    }

    if app.server_connected {
        spans.push(Span::styled(" │ ", Style::default().fg(Color::DarkGray)));
        let dot_color = if app.is_local_provider {
            Color::Magenta
        } else {
            Color::Green
        };
        spans.push(Span::styled("●", Style::default().fg(dot_color)));
    } else {
        spans.push(Span::styled(" │ ", Style::default().fg(Color::DarkGray)));
        spans.push(Span::styled("●", Style::default().fg(Color::Red)));
    }

    if !app.cwd.is_empty() {
        let cwd_short = app.cwd.split('/').last().unwrap_or(&app.cwd);
        spans.push(Span::styled(" │ ", Style::default().fg(Color::DarkGray)));
        spans.push(Span::styled(
            format!("~/{cwd_short}"),
            Style::default().fg(Color::DarkGray),
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
        spans.push(Span::styled(right_text, Style::default().fg(Color::Cyan)));
    }

    let bar = Paragraph::new(Line::from(spans)).style(theme::status_bar_style());
    frame.render_widget(bar, area);
}

// ── Chat area ────────────────────────────────────────────────────────

fn draw_chat_area(frame: &mut Frame, app: &App, area: Rect) {
    if app.messages.is_empty() {
        let empty = Paragraph::new("Start typing to begin a conversation...")
            .style(Style::default().fg(Color::DarkGray))
            .block(
                Block::default()
                    .borders(Borders::NONE)
                    .padding(Padding::new(2, 2, 1, 0)),
            );
        frame.render_widget(empty, area);
        return;
    }

    // Render all messages into lines
    let mut all_lines: Vec<Line<'static>> = Vec::new();

    for msg in &app.messages {
        all_lines.push(Line::from("")); // spacing

        match &msg.role {
            MessageRole::User => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ● ", Style::default().fg(theme::USER_COLOR)),
                    Span::styled("You", theme::user_label_style()),
                ]));
                // Render user content with simple wrapping
                for line in msg.content.lines() {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(Color::White),
                    )));
                }
            }
            MessageRole::Assistant => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ● ", Style::default().fg(theme::ASSISTANT_COLOR)),
                    Span::styled("Assistant", theme::assistant_label_style()),
                ]));
                // Render assistant content as markdown
                let md_lines = markdown::render_markdown(&msg.content);
                for ml in md_lines {
                    let mut padded_spans: Vec<Span<'static>> = vec![Span::raw("    ".to_string())];
                    padded_spans.extend(ml.spans);
                    all_lines.push(Line::from(padded_spans));
                }
            }
            MessageRole::System => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ◆ ", Style::default().fg(theme::SYSTEM_COLOR)),
                    Span::styled(
                        "System",
                        Style::default()
                            .fg(theme::SYSTEM_COLOR)
                            .add_modifier(Modifier::BOLD),
                    ),
                ]));
                for line in msg.content.lines() {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(Color::DarkGray),
                    )));
                }
            }
            MessageRole::ToolCall { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ┌─ ", theme::tool_border_style()),
                    Span::styled(name.clone(), theme::tool_title_style()),
                    Span::styled(" ──────────────", theme::tool_border_style()),
                ]));
                for line in msg.content.lines() {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style()),
                        Span::styled(line.to_string(), Style::default().fg(Color::DarkGray)),
                    ]));
                }
                all_lines.push(Line::from(Span::styled(
                    "  └────────────────────",
                    theme::tool_border_style(),
                )));
            }
            MessageRole::ToolResult { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ┌─ ", theme::tool_border_style()),
                    Span::styled(format!("{name} result"), theme::tool_title_style()),
                    Span::styled(" ─────", theme::tool_border_style()),
                ]));
                // Truncate long tool output
                let content = if msg.content.len() > 500 {
                    format!("{}…", &msg.content[..500])
                } else {
                    msg.content.clone()
                };
                for line in content.lines().take(15) {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style()),
                        Span::styled(line.to_string(), Style::default().fg(Color::DarkGray)),
                    ]));
                }
                if msg.content.lines().count() > 15 {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style()),
                        Span::styled(
                            "... (truncated)".to_string(),
                            Style::default().fg(Color::DarkGray),
                        ),
                    ]));
                }
                all_lines.push(Line::from(Span::styled(
                    "  └────────────────────",
                    theme::tool_border_style(),
                )));
            }
            MessageRole::DiffView { name } => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ┌─ ", theme::tool_border_style()),
                    Span::styled(format!("{name} diff"), theme::tool_title_style()),
                    Span::styled(" ─────", theme::tool_border_style()),
                ]));
                for line in msg.content.lines().take(40) {
                    let (prefix, style) = if line.starts_with('+') && !line.starts_with("+++") {
                        ("  │+", Style::default().fg(Color::Green))
                    } else if line.starts_with('-') && !line.starts_with("---") {
                        ("  │-", Style::default().fg(Color::Red))
                    } else if line.starts_with("@@") {
                        ("  │ ", Style::default().fg(Color::Cyan))
                    } else {
                        ("  │ ", Style::default().fg(Color::DarkGray))
                    };
                    all_lines.push(Line::from(vec![
                        Span::styled(prefix.to_string(), theme::tool_border_style()),
                        Span::styled(line.to_string(), style),
                    ]));
                }
                if msg.content.lines().count() > 40 {
                    all_lines.push(Line::from(vec![
                        Span::styled("  │ ", theme::tool_border_style()),
                        Span::styled("... (truncated)".to_string(), Style::default().fg(Color::DarkGray)),
                    ]));
                }
                all_lines.push(Line::from(Span::styled(
                    "  └────────────────────",
                    theme::tool_border_style(),
                )));
            }
            MessageRole::Error => {
                all_lines.push(Line::from(vec![
                    Span::styled("  ⚠ ", Style::default().fg(theme::ERROR)),
                    Span::styled("Error", theme::error_style()),
                ]));
                for line in msg.content.lines() {
                    all_lines.push(Line::from(Span::styled(
                        format!("    {line}"),
                        Style::default().fg(theme::ERROR),
                    )));
                }
            }
        }
    }

    // Apply scroll offset (from bottom)
    let total_lines = all_lines.len() as u16;
    let visible_height = area.height;
    let max_scroll = total_lines.saturating_sub(visible_height);
    let effective_scroll = app.scroll_offset.min(max_scroll);

    let text = Text::from(all_lines);
    let para = Paragraph::new(text)
        .wrap(Wrap { trim: false })
        .scroll((max_scroll.saturating_sub(effective_scroll), 0));

    frame.render_widget(para, area);
}

// ── Input bar ────────────────────────────────────────────────────────

fn draw_input_bar(frame: &mut Frame, app: &App, area: Rect) {
    if app.waiting {
        let prompt_spans = vec![
            Span::styled("  ", Style::default()),
            Span::styled(app.spinner_frame(), theme::spinner_style()),
            Span::styled(
                " Waiting for response... ",
                Style::default().fg(Color::DarkGray),
            ),
        ];
        let input = Paragraph::new(Line::from(prompt_spans)).block(
            Block::default()
                .borders(Borders::TOP)
                .border_style(Style::default().fg(Color::Rgb(50, 50, 70)))
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
                Span::styled(prefix.to_string(), Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
                Span::styled(part.to_string(), theme::input_style()),
            ]));
        }
        let input = Paragraph::new(lines).block(
            Block::default()
                .borders(Borders::TOP)
                .border_style(Style::default().fg(Color::Rgb(50, 50, 70))),
        );
        frame.render_widget(input, area);
    } else {
        let prompt_spans = vec![
            Span::styled("  ", Style::default()),
            Span::styled(
                "❯ ",
                Style::default()
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(app.input_buffer.clone(), theme::input_style()),
            Span::styled("█", theme::input_cursor_style()),
            if app.input_buffer.is_empty() {
                Span::styled(
                    format!(" Type your message ({})...", provider_short.to_uppercase()),
                    Style::default().fg(Color::DarkGray),
                )
            } else {
                Span::raw("")
            },
        ];
        let input = Paragraph::new(Line::from(prompt_spans)).block(
            Block::default()
                .borders(Borders::TOP)
                .border_style(Style::default().fg(Color::Rgb(50, 50, 70)))
                .padding(Padding::new(0, 0, 0, 0)),
        );
        frame.render_widget(input, area);
    }
}

// ── Hint bar ─────────────────────────────────────────────────────────

fn draw_hint_bar(frame: &mut Frame, app: &App, area: Rect) {
    let spans = if let Some((status, _)) = &app.status_message {
        vec![Span::styled(
            format!("  {status}"),
            Style::default().fg(Color::Yellow),
        )]
    } else if app.mode == AppMode::Command {
        // Show matching commands
        let prefix = &app.input_buffer;
        let matches = matching_commands(prefix);
        let mut spans = vec![Span::styled("  ", Style::default())];
        for (i, m) in matches.into_iter().take(6).enumerate() {
            if i > 0 {
                spans.push(Span::styled("  ", Style::default()));
            }
            spans.push(Span::styled(
                m.command.to_string(),
                Style::default().fg(Color::DarkGray),
            ));
        }
        spans
    } else {
        vec![
            Span::styled("  /help", Style::default().fg(Color::DarkGray)),
            Span::styled("  /quit", Style::default().fg(Color::DarkGray)),
            Span::styled("  /switch", Style::default().fg(Color::DarkGray)),
            Span::styled("  Ctrl+C", Style::default().fg(Color::DarkGray)),
            Span::styled(": cancel  ", Style::default().fg(Color::DarkGray)),
            Span::styled("Esc", Style::default().fg(Color::DarkGray)),
            Span::styled(": cancel  ", Style::default().fg(Color::DarkGray)),
            Span::styled("PgUp/PgDn", Style::default().fg(Color::DarkGray)),
            Span::styled(": scroll  ", Style::default().fg(Color::DarkGray)),
            Span::styled("↑↓", Style::default().fg(Color::DarkGray)),
            Span::styled(": history", Style::default().fg(Color::DarkGray)),
        ]
    };

    let hint = Paragraph::new(Line::from(spans)).style(Style::default().fg(Color::DarkGray));
    frame.render_widget(hint, area);
}

fn draw_command_palette(frame: &mut Frame, app: &App) {
    if app.waiting || !app.input_buffer.starts_with('/') {
        return;
    }

    let commands = if app.input_buffer.trim() == "/" {
        SLASH_COMMANDS
            .iter()
            .filter(|spec| spec.recommended)
            .collect::<Vec<&SlashCommandSpec>>()
    } else {
        matching_commands(&app.input_buffer)
    };

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

    let items: Vec<ListItem> = display_items
        .iter()
        .map(|spec| {
            let desc_style = if spec.recommended {
                Style::default().fg(Color::Cyan)
            } else {
                Style::default().fg(Color::DarkGray)
            };
            ListItem::new(Line::from(vec![
                Span::styled(
                    format!("{:<14}", spec.command),
                    Style::default()
                        .fg(Color::White)
                        .add_modifier(Modifier::BOLD),
                ),
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
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Rgb(60, 70, 95))),
    );
    frame.render_widget(list, area);
}

fn matching_commands(prefix: &str) -> Vec<&'static SlashCommandSpec> {
    SLASH_COMMANDS
        .iter()
        .filter(|spec| spec.command.starts_with(prefix))
        .collect()
}

// ── Provider select overlay ──────────────────────────────────────────

fn draw_provider_select(frame: &mut Frame, app: &App) {
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
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD)
            } else if p.available {
                Style::default().fg(Color::White)
            } else {
                Style::default().fg(Color::DarkGray)
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
                    .fg(Color::Cyan)
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Cyan))
            .padding(Padding::new(1, 1, 1, 1)),
    );
    frame.render_widget(list, area);
}

// ── Permission prompt overlay ────────────────────────────────────────

fn draw_permission_prompt(frame: &mut Frame, app: &App) {
    let area = centered_rect(60, 30, frame.area());
    frame.render_widget(Clear, area);

    let text = vec![
        Line::from(""),
        Line::from(Span::styled(
            "  ⚠  Permission Required",
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )),
        Line::from(""),
        Line::from(Span::styled(
            format!("  {}", app.permission_message),
            Style::default().fg(Color::White),
        )),
        Line::from(""),
        Line::from(vec![
            Span::styled("  Press ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "y",
                Style::default()
                    .fg(Color::Green)
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(" to allow, ", Style::default().fg(Color::DarkGray)),
            Span::styled(
                "n",
                Style::default().fg(Color::Red).add_modifier(Modifier::BOLD),
            ),
            Span::styled(" to deny", Style::default().fg(Color::DarkGray)),
        ]),
        Line::from(""),
    ];

    let para = Paragraph::new(text).block(
        Block::default()
            .borders(Borders::ALL)
            .border_style(Style::default().fg(Color::Yellow))
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
