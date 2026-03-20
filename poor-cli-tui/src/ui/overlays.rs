use ratatui::{
    layout::{Constraint, Direction, Layout},
    style::{Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, List, ListItem, Padding, Paragraph, Wrap},
    Frame,
};

use crate::app::{
    App, ProviderSelectPane,
};
use crate::markdown;
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

pub(crate) fn annotate_copyable_items(content: &str) -> String {
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

pub(crate) fn draw_info_popup(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(72, 72, frame.area());
    render_popup_surface(frame, area, mode);

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
