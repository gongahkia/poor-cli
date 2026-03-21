use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, List, ListItem, Padding, Paragraph, Wrap},
    Frame,
};

use crate::app::{
    App, ProviderSelectPane,
};
use crate::markdown;
use crate::onboarding::{owl_for_step, ONBOARDING_STEPS};
use crate::theme;
use super::{centered_rect, ellipsize_middle, render_popup_surface};

// ── Provider select overlay ──────────────────────────────────────────

pub(crate) fn draw_provider_select(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(78, 68, frame.area());
    render_popup_surface(frame, area, mode);

    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(48), Constraint::Percentage(52)])
        .split(area);

    let provider_pane_focused = app.provider.select_pane == ProviderSelectPane::Providers;
    let model_pane_focused = app.provider.select_pane == ProviderSelectPane::Models;

    let items: Vec<ListItem> = app
        .provider
        .list
        .iter()
        .enumerate()
        .map(|(i, p)| {
            let marker = if i == app.provider.select_idx {
                "▸ "
            } else {
                "  "
            };
            let style = if i == app.provider.select_idx {
                let base = if provider_pane_focused {
                    theme::accent(mode)
                } else {
                    theme::base_fg(mode)
                };
                Style::default().fg(base).add_modifier(Modifier::BOLD)
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
            let model_count = if p.models.is_empty() {
                "no models".to_string()
            } else if p.models.len() == 1 {
                "1 model".to_string()
            } else {
                format!("{} models", p.models.len())
            };
            let dot_style = if p.ready {
                Style::default().fg(theme::success(mode))
            } else {
                Style::default().fg(theme::error(mode))
            };

            ListItem::new(Line::from(vec![
                Span::styled(marker.to_string(), style),
                Span::styled("● ".to_string(), dot_style),
                Span::styled(p.name.clone(), style),
                Span::styled(local_tag.to_string(), theme::local_badge_style(mode)),
                Span::styled(
                    format!("  {model_count}"),
                    Style::default().fg(theme::muted_fg(mode)),
                ),
            ]))
        })
        .collect();

    let list = List::new(items).block(
        Block::default()
            .title(Span::styled(
                " Switch ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(if provider_pane_focused {
                Style::default().fg(theme::accent(mode))
            } else {
                Style::default().fg(theme::muted_fg(mode))
            })
            .padding(Padding::new(1, 1, 1, 1)),
    );
    frame.render_widget(list, chunks[0]);

    let selected = app.provider.list.get(app.provider.select_idx);
    let selected_provider_name = selected
        .map(|provider| provider.name.as_str())
        .unwrap_or("unknown");
    let selected_model = app.selected_provider_model().unwrap_or_else(|| {
        if selected_provider_name.eq_ignore_ascii_case(&app.provider.name)
            && !app.provider.model.trim().is_empty()
            && app.provider.model != "unknown"
        {
            app.provider.model.clone()
        } else {
            "default".to_string()
        }
    });
    let selected_model_idx = app.selected_provider_model_index();
    let provider_note = match selected_provider_name.to_ascii_lowercase().as_str() {
        "gemini" => "Fast inference with a broad free-tier path and strong coding output.",
        "openai" => "Strong general reasoning with broad tool-calling support.",
        "anthropic" | "claude" => {
            "Strong analysis and long-form reasoning, especially for review work."
        }
        "ollama" => "Runs locally. Best when you want data locality and no per-call API cost.",
        _ => "Provider metadata is limited to the configured model list.",
    };

    let mut detail_lines = vec![
        Line::from(vec![
            Span::styled(" Provider ", theme::tool_title_style(mode)),
            Span::styled(
                selected_provider_name.to_string(),
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ),
        ]),
        Line::from(Span::styled(
            provider_note.to_string(),
            Style::default().fg(theme::muted_fg(mode)),
        )),
        Line::from(""),
        Line::from(vec![
            Span::styled("Status: ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(
                selected
                    .map(|provider| provider.status_label.clone())
                    .filter(|label| !label.trim().is_empty())
                    .unwrap_or_else(|| "unknown".to_string()),
                if selected.map(|provider| provider.ready).unwrap_or(false) {
                    Style::default()
                        .fg(theme::success(mode))
                        .add_modifier(Modifier::BOLD)
                } else {
                    Style::default()
                        .fg(theme::error(mode))
                        .add_modifier(Modifier::BOLD)
                },
            ),
        ]),
        Line::from(vec![
            Span::styled(
                "Selected model: ",
                Style::default().fg(theme::muted_fg(mode)),
            ),
            Span::styled(
                selected_model.clone(),
                Style::default()
                    .fg(theme::base_fg(mode))
                    .add_modifier(Modifier::BOLD),
            ),
        ]),
    ];

    if selected_provider_name.eq_ignore_ascii_case(&app.provider.name) {
        detail_lines.push(Line::from(Span::styled(
            "This is the provider active in the current session.",
            Style::default().fg(theme::success(mode)),
        )));
    } else {
        detail_lines.push(Line::from(Span::styled(
            "Press Enter to switch to this provider using the highlighted model below.",
            Style::default().fg(theme::muted_fg(mode)),
        )));
    }

    detail_lines.push(Line::from(""));
    detail_lines.push(Line::from(Span::styled(
        "Use ←/→ to switch panes. Use ↑/↓ to change the active provider or model.",
        Style::default().fg(theme::muted_fg(mode)),
    )));
    detail_lines.push(Line::from(""));
    detail_lines.push(Line::from(Span::styled(
        "Available models",
        Style::default()
            .fg(theme::accent(mode))
            .add_modifier(Modifier::BOLD),
    )));

    if let Some(provider) = selected {
        if provider.models.is_empty() {
            detail_lines.push(Line::from(Span::styled(
                "- No model metadata reported",
                Style::default().fg(theme::muted_fg(mode)),
            )));
        } else {
            let selected_idx = selected_model_idx.unwrap_or(0);
            let max_visible = 8usize;
            let start = if provider.models.len() <= max_visible {
                0
            } else {
                selected_idx
                    .saturating_sub(3)
                    .min(provider.models.len() - max_visible)
            };
            let end = (start + max_visible).min(provider.models.len());
            if start > 0 {
                detail_lines.push(Line::from(Span::styled(
                    format!("… {} earlier model(s)", start),
                    Style::default().fg(theme::muted_fg(mode)),
                )));
            }
            for (index, model) in provider
                .models
                .iter()
                .enumerate()
                .skip(start)
                .take(end - start)
            {
                let is_selected_model = Some(index) == selected_model_idx;
                detail_lines.push(Line::from(vec![
                    Span::styled(
                        if is_selected_model { "▸ " } else { "  " },
                        if is_selected_model {
                            Style::default().fg(if model_pane_focused {
                                theme::accent(mode)
                            } else {
                                theme::muted_fg(mode)
                            })
                        } else {
                            Style::default().fg(theme::muted_fg(mode))
                        },
                    ),
                    Span::styled(
                        model.clone(),
                        if is_selected_model {
                            Style::default()
                                .fg(if model_pane_focused {
                                    theme::accent(mode)
                                } else {
                                    theme::base_fg(mode)
                                })
                                .add_modifier(Modifier::BOLD)
                        } else {
                            Style::default().fg(theme::base_fg(mode))
                        },
                    ),
                ]));
            }
            if end < provider.models.len() {
                detail_lines.push(Line::from(Span::styled(
                    format!("… {} more model(s)", provider.models.len() - end),
                    Style::default().fg(theme::muted_fg(mode)),
                )));
            }
        }
    } else {
        detail_lines.push(Line::from(Span::styled(
            "- No provider selected",
            Style::default().fg(theme::muted_fg(mode)),
        )));
    }

    let details = Paragraph::new(detail_lines)
        .wrap(Wrap { trim: false })
        .block(
            Block::default()
                .title(Span::styled(
                    " Model Info ",
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD),
                ))
                .borders(Borders::ALL)
                .border_style(if model_pane_focused {
                    Style::default().fg(theme::accent(mode))
                } else {
                    Style::default().fg(theme::muted_fg(mode))
                })
                .padding(Padding::new(1, 1, 1, 1)),
        );
    frame.render_widget(details, chunks[1]);
}

pub(crate) fn annotate_copyable_items(content: &str, selected_idx: usize) -> String {
    let parts: Vec<&str> = content.split('`').collect();
    if parts.len() < 3 { return content.to_string(); }
    let mut result = String::with_capacity(content.len() + 64);
    let mut copy_idx = 0usize;
    for (i, part) in parts.iter().enumerate() {
        if i % 2 == 1 && !part.trim().is_empty() {
            let marker = if copy_idx == selected_idx { "> " } else { "  " };
            result.push_str(&format!("{marker}`{part}`"));
            copy_idx += 1;
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

pub(crate) fn draw_info_popup(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(72, 72, frame.area());
    render_popup_surface(frame, area, mode);

    let title = if app.info_popup_title.trim().is_empty() {
        " Info "
    } else {
        app.info_popup_title.as_str()
    };

    let annotated = annotate_copyable_items(&app.info_popup_content, app.info_popup_selected_idx);
    let markdown_lines = markdown::render_markdown(&annotated, mode);
    let hint = " ↑↓ navigate • Enter run/copy • c copy all • Esc close ".to_string();
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
                .title_bottom(Span::styled(hint, Style::default().fg(theme::muted_fg(mode))))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(theme::accent(mode)))
                .padding(Padding::new(1, 1, 1, 1)),
        );
    frame.render_widget(popup, area);
}

pub(crate) fn mask_secret_preview(value: &str) -> String {
    if value.is_empty() {
        return "(empty)".to_string();
    }
    let chars: Vec<char> = value.chars().collect();
    if chars.len() <= 4 {
        return "•".repeat(chars.len());
    }
    let tail: String = chars[chars.len().saturating_sub(4)..].iter().collect();
    format!("{}{}", "•".repeat(chars.len().saturating_sub(4)), tail)
}

pub(crate) fn draw_api_key_editor(frame: &mut Frame, app: &App) {
    let Some(editor) = app.api_key_editor.as_ref() else {
        return;
    };

    let mode = app.theme_mode;
    let area = centered_rect(78, 68, frame.area());
    render_popup_surface(frame, area, mode);

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(8),
            Constraint::Min(8),
            Constraint::Length(6),
        ])
        .split(area);

    let mut header_lines = vec![
        Line::from(vec![
            Span::styled(
                " Setup Credentials ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                if editor.env_exists {
                    " editing existing .env"
                } else {
                    " creating .env from template"
                },
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ]),
        Line::from(Span::styled(
            format!("env: {}", ellipsize_middle(&editor.env_path, 64)),
            Style::default().fg(theme::base_fg(mode)),
        )),
        Line::from(Span::styled(
            format!("template: {}", ellipsize_middle(&editor.template_path, 59)),
            Style::default().fg(theme::muted_fg(mode)),
        )),
        Line::from(Span::styled(
            format!(
                "active provider: {} / {}",
                editor.target_provider, editor.target_model
            ),
            Style::default().fg(theme::muted_fg(mode)),
        )),
    ];

    if !editor.init_error.trim().is_empty() {
        header_lines.push(Line::from(Span::styled(
            format!("last error: {}", ellipsize_middle(&editor.init_error, 68)),
            Style::default().fg(theme::error(mode)),
        )));
    }

    if !editor.status.trim().is_empty() {
        header_lines.push(Line::from(Span::styled(
            editor.status.clone(),
            Style::default().fg(theme::success(mode)),
        )));
    } else if !editor.error.trim().is_empty() {
        header_lines.push(Line::from(Span::styled(
            editor.error.clone(),
            Style::default().fg(theme::error(mode)),
        )));
    }

    let header = Paragraph::new(header_lines).block(
        Block::default()
            .title(Span::styled(
                " Setup ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(header, chunks[0]);

    let items: Vec<ListItem> = editor
        .fields
        .iter()
        .enumerate()
        .map(|(idx, field)| {
            let is_selected = idx == editor.selected_index;
            let marker = if is_selected { "▸ " } else { "  " };
            let provider_tag = field
                .provider
                .as_deref()
                .filter(|provider| *provider == editor.target_provider)
                .map(|_| " [active]")
                .unwrap_or("");
            let display_value = if is_selected {
                format!("{}_", field.value)
            } else {
                mask_secret_preview(&field.value)
            };
            let style = if is_selected {
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default().fg(theme::base_fg(mode))
            };
            let meta_style = if is_selected {
                Style::default().fg(theme::base_fg(mode))
            } else {
                Style::default().fg(theme::muted_fg(mode))
            };

            ListItem::new(Line::from(vec![
                Span::styled(marker.to_string(), style),
                Span::styled(format!("{:<12}", field.label), style),
                Span::styled(format!("{}{}", field.env_var, provider_tag), meta_style),
                Span::styled("  ".to_string(), meta_style),
                Span::styled(display_value, style),
            ]))
        })
        .collect();

    let fields = List::new(items).block(
        Block::default()
            .title(Span::styled(
                " Managed Keys ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(fields, chunks[1]);

    let footer_text = editor
        .fields
        .get(editor.selected_index)
        .map(|field| {
            format!(
                "{}\nSaving writes `{}` and retries backend initialization.",
                field.help, field.env_var
            )
        })
        .unwrap_or_else(|| "Select a field to edit.".to_string());
    let footer = Paragraph::new(footer_text)
        .wrap(Wrap { trim: false })
        .block(
            Block::default()
                .title(Span::styled(
                    " Guidance ",
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD),
                ))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(theme::accent(mode)))
                .padding(Padding::new(1, 1, 0, 0)),
        )
        .style(Style::default().fg(theme::muted_fg(mode)));
    frame.render_widget(footer, chunks[2]);
}

pub(crate) fn draw_quick_open(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(72, 70, frame.area());
    render_popup_surface(frame, area, mode);

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
                    .bg(theme::surface_bg(mode))
                    .add_modifier(Modifier::BOLD)
            } else {
                Style::default()
                    .fg(theme::base_fg(mode))
                    .bg(theme::elevated_bg(mode))
            };
            let detail_style = if is_selected {
                Style::default()
                    .fg(theme::base_fg(mode))
                    .bg(theme::surface_bg(mode))
            } else {
                Style::default()
                    .fg(theme::muted_fg(mode))
                    .bg(theme::elevated_bg(mode))
            };
            ListItem::new(Line::from(vec![
                Span::styled(if is_selected { "▸ " } else { "  " }, style),
                Span::styled(item.label.clone(), style),
                Span::styled(format!("  {}", item.detail), detail_style),
            ]))
        })
        .collect();

    let list = List::new(items)
        .style(Style::default().bg(theme::elevated_bg(mode)))
        .block(
            Block::default()
                .style(Style::default().bg(theme::elevated_bg(mode)))
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


pub(crate) fn draw_join_wizard(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(55, 30, frame.area());
    render_popup_surface(frame, area, mode);
    let step_label = "1/1";
    let prompt = "Invite code";
    let hint = "Paste a signed collaboration invite to join this session.";
    let mut lines = vec![
        Line::from(""),
        Line::from(Span::styled(
            format!("  Join Collaboration — Step {step_label}"),
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
        Line::from(""),
        Line::from(Span::styled(
            format!("  {hint}"),
            Style::default().fg(theme::muted_fg(mode)),
        )),
    ];
    if !app.join_wizard_error.is_empty() {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            format!("  ⚠ {}", app.join_wizard_error),
            Style::default().fg(theme::error(mode)),
        )));
    }
    lines.push(Line::from(""));
    let popup = Paragraph::new(lines).block(
        Block::default()
            .title(Span::styled(
                " Join Collaboration ",
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

// ── Graph overlay (repo indexing animation) ─────────────────────────

const DIR_COLORS: &[Color] = &[
    Color::Rgb(176, 187, 143), // green
    Color::Rgb(200, 150, 220), // purple
    Color::Rgb(130, 190, 220), // blue
    Color::Rgb(220, 180, 120), // orange
    Color::Rgb(180, 220, 180), // light green
    Color::Rgb(220, 150, 150), // pink
];

pub(crate) fn draw_graph_overlay(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(64, 60, frame.area());
    render_popup_surface(frame, area, mode);
    let border_block = Block::default()
        .title(Span::styled(
            " Indexing Repository ",
            Style::default()
                .fg(theme::accent(mode))
                .add_modifier(Modifier::BOLD),
        ))
        .borders(Borders::ALL)
        .border_style(Style::default().fg(theme::accent(mode)));
    frame.render_widget(border_block, area);
    let inner = Rect {
        x: area.x + 2,
        y: area.y + 2,
        width: area.width.saturating_sub(4),
        height: area.height.saturating_sub(5),
    };
    if inner.width < 10 || inner.height < 6 { return; }
    let elapsed = app.graph_overlay.started_at.elapsed().as_millis() as f64;
    let cx = inner.x as f64 + inner.width as f64 / 2.0;
    let cy = inner.y as f64 + (inner.height as f64 - 3.0) / 2.0;
    let rx = (inner.width as f64 / 2.0 - 5.0).max(4.0);
    let ry = ((inner.height as f64 - 3.0) / 2.0 - 1.0).max(2.0);
    let buf = frame.buffer_mut();
    let nodes = &app.graph_overlay.nodes;
    // build flat list: (label, x, y, color, parent_idx)
    // ring 1 = directories at equal angles, ring 2 = children offset from parent
    let dir_count = nodes.len().max(1);
    struct PlotNode { x: f64, y: f64, color: Color, label: String, parent: Option<usize> }
    let mut plot_nodes: Vec<PlotNode> = Vec::new();
    // center node: repo root (use cwd basename)
    let root_label = ".".to_string();
    plot_nodes.push(PlotNode {
        x: cx, y: cy,
        color: Color::Rgb(255, 200, 87),
        label: root_label, parent: None,
    });
    // ring 1: directories
    for (i, (dir_name, children)) in nodes.iter().enumerate() {
        let angle = 2.0 * std::f64::consts::PI * i as f64 / dir_count as f64 - std::f64::consts::FRAC_PI_2;
        let dx = cx + angle.cos() * rx * 0.5;
        let dy = cy + angle.sin() * ry * 0.5;
        let color = DIR_COLORS[i % DIR_COLORS.len()];
        let dir_idx = plot_nodes.len();
        plot_nodes.push(PlotNode {
            x: dx, y: dy, color,
            label: truncate_label(dir_name, 10), parent: Some(0),
        });
        // ring 2: children spread around parent
        let child_count = children.len().max(1);
        for (ci, child) in children.iter().enumerate() {
            let child_angle = angle + (ci as f64 - child_count as f64 / 2.0) * 0.3;
            let child_x = cx + child_angle.cos() * rx * 0.9;
            let child_y = cy + child_angle.sin() * ry * 0.9;
            plot_nodes.push(PlotNode {
                x: child_x, y: child_y,
                color: Color::Rgb(
                    ((color.to_string().len() * 7 + ci * 31) % 60 + 140) as u8,
                    ((color.to_string().len() * 13 + ci * 17) % 60 + 160) as u8,
                    ((color.to_string().len() * 3 + ci * 23) % 60 + 150) as u8,
                ),
                label: truncate_label(child, 8),
                parent: Some(dir_idx),
            });
        }
    }
    // if no dynamic nodes yet, use a simple loading animation
    if nodes.is_empty() {
        let spin_idx = (elapsed / 200.0) as usize % 4;
        let spin = ["⠋", "⠙", "⠹", "⠸"][spin_idx];
        buf.set_string(
            cx as u16, cy as u16, spin,
            Style::default().fg(Color::Rgb(255, 200, 87)).add_modifier(Modifier::BOLD),
        );
        buf.set_string(
            cx as u16 + 2, cy as u16, "scanning...",
            Style::default().fg(theme::muted_fg(mode)),
        );
    } else {
        // adaptive reveal: always takes ANIM_DURATION_MS regardless of node count
        const ANIM_DURATION_MS: f64 = 4000.0;
        let total = plot_nodes.len().max(1);
        let interval = ANIM_DURATION_MS / total as f64;
        let visible = ((elapsed / interval) as usize).min(total);
        let edge_color = theme::muted_fg(mode);
        // draw edges first
        for i in 1..visible {
            if let Some(pi) = plot_nodes[i].parent {
                if pi < visible {
                    let (x1, y1) = (plot_nodes[pi].x, plot_nodes[pi].y);
                    let (x2, y2) = (plot_nodes[i].x, plot_nodes[i].y);
                    let steps = ((x2 - x1).abs().max((y2 - y1).abs() * 2.0)) as usize;
                    if steps == 0 { continue; }
                    for s in 1..steps {
                        let t = s as f64 / steps as f64;
                        let px = (x1 + (x2 - x1) * t) as u16;
                        let py = (y1 + (y2 - y1) * t) as u16;
                        if px > inner.x && px < inner.x + inner.width - 1
                            && py >= inner.y && py < inner.y + inner.height - 2
                        {
                            buf.set_string(px, py, "·", Style::default().fg(edge_color));
                        }
                    }
                }
            }
        }
        // draw nodes
        for i in 0..visible {
            let n = &plot_nodes[i];
            let nx = n.x as u16;
            let ny = n.y as u16;
            if nx < inner.x || nx >= inner.x + inner.width
                || ny < inner.y || ny >= inner.y + inner.height - 2 { continue; }
            let ch = if n.parent.is_none() { "◉" } else if n.parent == Some(0) { "●" } else { "○" };
            buf.set_string(nx, ny, ch, Style::default().fg(n.color).add_modifier(Modifier::BOLD));
            if nx as f64 >= cx {
                let lx = nx + 2;
                if lx + n.label.len() as u16 <= inner.x + inner.width {
                    buf.set_string(lx, ny, &n.label, Style::default().fg(n.color));
                }
            } else {
                let lx = nx.saturating_sub(n.label.len() as u16 + 1);
                if lx >= inner.x {
                    buf.set_string(lx, ny, &n.label, Style::default().fg(n.color));
                }
            }
        }
    }
    // loading bar + animated status text
    let status_y = area.y + area.height - 3;
    let bar_x = inner.x;
    let bar_y = area.y + area.height - 2;
    let bar_width = inner.width.saturating_sub(6);
    const ANIM_DURATION_MS: f64 = 4000.0;
    let anim_progress = (elapsed / ANIM_DURATION_MS).min(1.0);
    // render status text with numbers counting up from 0
    let status = &app.graph_overlay.status_text;
    if !status.is_empty() && status_y > inner.y {
        let max_w = inner.width as usize;
        let animated = interpolate_numbers(status, anim_progress);
        let s = if animated.len() > max_w { &animated[..max_w] } else { animated.as_str() };
        buf.set_string(bar_x, status_y, s, Style::default().fg(theme::muted_fg(mode)));
    }
    if bar_width > 0 {
        let visual_pct = anim_progress * 100.0;
        let filled = ((bar_width as f64 * anim_progress) as u16).min(bar_width);
        let bar: String = "█".repeat(filled as usize) + &"░".repeat((bar_width - filled) as usize);
        buf.set_string(bar_x, bar_y, &bar, Style::default().fg(theme::accent(mode)));
        buf.set_string(
            bar_x + bar_width, bar_y,
            &format!(" {:.0}%", visual_pct),
            Style::default().fg(theme::muted_fg(mode)),
        );
        // show dismiss hint top-right after animation completes
        if anim_progress >= 1.0 {
            let hint = " press any key to continue ";
            let hx = (area.x + area.width).saturating_sub(hint.len() as u16 + 1);
            buf.set_string(
                hx, area.y,
                hint,
                Style::default().fg(theme::accent(mode)).add_modifier(Modifier::BOLD),
            );
        }
    }
}

fn truncate_label(s: &str, max: usize) -> String {
    if s.len() <= max { s.to_string() } else { format!("{}…", &s[..max - 1]) }
}

/// Replace all numeric sequences in `s` with values interpolated from 0 to their final value.
fn interpolate_numbers(s: &str, progress: f64) -> String {
    let mut result = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        if c.is_ascii_digit() {
            let mut num_str = String::from(c);
            while let Some(&next) = chars.peek() {
                if next.is_ascii_digit() { num_str.push(chars.next().unwrap()); } else { break; }
            }
            if let Ok(final_val) = num_str.parse::<u64>() {
                let current = (final_val as f64 * progress).round() as u64;
                result.push_str(&current.to_string());
            } else {
                result.push_str(&num_str);
            }
        } else {
            result.push(c);
        }
    }
    result
}

// ── List selector overlay ───────────────────────────────────────────

pub(crate) fn draw_list_selector(frame: &mut Frame, app: &App) {
    let Some(state) = app.list_selector.as_ref() else { return; };
    let mode = app.theme_mode;
    let area = centered_rect(72, 68, frame.area());
    render_popup_surface(frame, area, mode);
    let items: Vec<ListItem> = state.items.iter().enumerate().map(|(i, item)| {
        let selected = i == state.selected_idx;
        let marker = if selected { "> " } else { "  " };
        let style = if selected {
            Style::default().fg(theme::accent(mode)).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(theme::base_fg(mode))
        };
        ListItem::new(Line::from(Span::styled(format!("{marker}{}", item.label), style)))
    }).collect();
    let hint = if let Some(ref override_hint) = state.action_hint_override {
        format!(" \u{2191}\u{2193}/jk navigate \u{2502} {} ", override_hint)
    } else {
        let action_preview = state.items.get(state.selected_idx)
            .map(|item| state.command_template.replace("{}", &item.value))
            .unwrap_or_default();
        format!(" ↑↓/jk navigate • Enter → {} • c copy • Esc close ", action_preview)
    };
    let list = List::new(items).block(
        Block::default()
            .title(Span::styled(
                format!(" {} ", state.title),
                Style::default().fg(theme::accent(mode)).add_modifier(Modifier::BOLD),
            ))
            .title_bottom(Span::styled(hint, Style::default().fg(theme::muted_fg(mode))))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 1, 1)),
    );
    frame.render_widget(list, area);
}

pub(crate) fn draw_onboarding(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(78, 70, frame.area());
    if area.width < 30 || area.height < 12 {
        return;
    }
    render_popup_surface(frame, area, mode);
    let step = app.onboarding_step;
    let total = app.onboarding_total_steps.max(1);
    let owl = owl_for_step(step);
    let step_data = ONBOARDING_STEPS.get(step);
    // step dots
    let dots: Vec<Span> = (0..total).map(|i| {
        if i <= step {
            Span::styled("\u{25cf} ", Style::default().fg(theme::accent(mode)))
        } else {
            Span::styled("\u{25cb} ", Style::default().fg(theme::muted_fg(mode)))
        }
    }).collect();
    let mut title_spans = vec![
        Span::styled(" Onboarding ", Style::default().fg(theme::accent(mode)).add_modifier(Modifier::BOLD)),
    ];
    title_spans.push(Span::raw("  "));
    title_spans.extend(dots);
    let hint = " h/\u{2190} prev  l/\u{2192} next  Enter try it  Esc exit ";
    // outer block
    let outer = Block::default()
        .title(Line::from(title_spans))
        .title_bottom(Span::styled(hint, Style::default().fg(theme::muted_fg(mode))))
        .borders(Borders::ALL)
        .border_style(Style::default().fg(theme::accent(mode)))
        .padding(Padding::new(1, 1, 1, 0));
    let inner = outer.inner(area);
    frame.render_widget(outer, area);
    // split into left (mascot) and right (content)
    let show_mascot = app.mascot_enabled;
    let constraints = if show_mascot {
        vec![Constraint::Percentage(30), Constraint::Percentage(70)]
    } else {
        vec![Constraint::Percentage(100)]
    };
    let cols = Layout::default()
        .direction(Direction::Horizontal)
        .constraints(constraints)
        .split(inner);
    let right = if show_mascot { cols[1] } else { cols[0] };
    // ── left panel: owl + speech bubble ──
    if show_mascot {
        let left = cols[0];
        let mut left_lines: Vec<Line> = Vec::new();
        left_lines.push(Line::raw(""));
        for art_line in owl.lines {
            left_lines.push(Line::from(Span::styled(*art_line, Style::default().fg(theme::accent(mode)))));
        }
        left_lines.push(Line::raw(""));
        let bubble_w = (left.width as usize).saturating_sub(2).max(8);
        let wrapped = textwrap::fill(owl.speech, bubble_w.saturating_sub(4));
        let speech_lines: Vec<&str> = wrapped.lines().collect();
        let bar_w = speech_lines.iter().map(|l| l.len()).max().unwrap_or(4).max(4);
        left_lines.push(Line::from(Span::styled(
            format!(" .{}.  ", "-".repeat(bar_w + 2)),
            Style::default().fg(theme::muted_fg(mode)),
        )));
        for sl in &speech_lines {
            left_lines.push(Line::from(Span::styled(
                format!(" | {:<width$} | ", sl, width = bar_w),
                Style::default().fg(theme::muted_fg(mode)),
            )));
        }
        left_lines.push(Line::from(Span::styled(
            format!(" '{}'  ", "-".repeat(bar_w + 2)),
            Style::default().fg(theme::muted_fg(mode)),
        )));
        let left_para = Paragraph::new(Text::from(left_lines));
        frame.render_widget(left_para, left);
    }
    // ── right panel: step content ──
    let mut right_lines: Vec<Line> = Vec::new();
    if let Some(s) = step_data {
        right_lines.push(Line::raw(""));
        right_lines.push(Line::from(Span::styled(
            s.title,
            Style::default().fg(theme::accent(mode)).add_modifier(Modifier::BOLD),
        )));
        right_lines.push(Line::raw(""));
        right_lines.push(Line::from(Span::styled(
            s.objective,
            Style::default().fg(theme::base_fg(mode)),
        )));
        right_lines.push(Line::raw(""));
        right_lines.push(Line::from(Span::styled(
            "Commands:",
            Style::default().fg(theme::muted_fg(mode)),
        )));
        for cmd in s.commands {
            right_lines.push(Line::from(vec![
                Span::raw("  "),
                Span::styled(*cmd, Style::default().fg(theme::accent(mode))),
            ]));
        }
        right_lines.push(Line::raw(""));
        right_lines.push(Line::from(vec![
            Span::styled("Try now: ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(s.try_now, Style::default().fg(theme::accent(mode)).add_modifier(Modifier::BOLD)),
        ]));
    }
    let right_para = Paragraph::new(Text::from(right_lines))
        .wrap(Wrap { trim: false });
    frame.render_widget(right_para, right);
}
