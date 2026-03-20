use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Modifier, Style},
    text::{Line, Span, Text},
    widgets::{Block, Borders, List, ListItem, Padding, Paragraph, Wrap},
    Frame,
};

use crate::app::{
    App, ProviderSelectPane, ReviewDecisionState, TimelineEntryKind,
    TranscriptSearchItemKind,
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

pub(crate) fn draw_queue_manager(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(82, 72, frame.area());
    render_popup_surface(frame, area, mode);

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(6),
            Constraint::Min(8),
            Constraint::Length(8),
        ])
        .split(area);

    let queue_status = if app.queue_paused {
        "paused after error"
    } else if app.waiting {
        "waiting for active request"
    } else {
        "ready"
    };
    let header = Paragraph::new(vec![
        Line::from(vec![
            Span::styled(" Prompt Queue ", theme::tool_title_style(mode)),
            Span::styled(
                format!("  {} item(s)", app.prompt_queue.len()),
                Style::default().fg(theme::muted_fg(mode)),
            ),
        ]),
        Line::from(Span::styled(
            format!("status: {queue_status}"),
            if app.queue_paused {
                Style::default().fg(theme::warning(mode))
            } else {
                Style::default().fg(theme::muted_fg(mode))
            },
        )),
        Line::from(Span::styled(
            "Open / manage queued prompts without leaving the chat composer.",
            Style::default().fg(theme::muted_fg(mode)),
        )),
    ])
    .block(
        Block::default()
            .title(Span::styled(
                " Queue ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::accent(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(header, chunks[0]);

    let items: Vec<ListItem> = if app.prompt_queue.is_empty() {
        vec![ListItem::new(Line::from(Span::styled(
            "  Queue is empty",
            Style::default().fg(theme::muted_fg(mode)),
        )))]
    } else {
        app.prompt_queue
            .iter()
            .enumerate()
            .map(|(index, prompt)| {
                let is_selected = index == app.queue_manager.selected_index;
                let marker = if is_selected { "▸ " } else { "  " };
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
                    Span::styled(format!("{marker}{}. ", index + 1), style),
                    Span::styled(format!("[{}] ", prompt.source), meta_style),
                    Span::styled(ellipsize_middle(&prompt.display, 72), style),
                ]))
            })
            .collect()
    };
    let list = List::new(items).block(
        Block::default()
            .title(Span::styled(
                " Items ",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ))
            .borders(Borders::ALL)
            .border_style(Style::default().fg(theme::input_border_color(mode)))
            .padding(Padding::new(1, 1, 0, 0)),
    );
    frame.render_widget(list, chunks[1]);

    let preview_text = app
        .prompt_queue
        .get(app.queue_manager.selected_index)
        .map(|prompt| {
            if prompt.backend == prompt.display {
                prompt.backend.clone()
            } else {
                format!("Display\n{}\n\nBackend\n{}", prompt.display, prompt.backend)
            }
        })
        .unwrap_or_else(|| "No queued prompts.".to_string());
    let preview = Paragraph::new(preview_text)
        .wrap(Wrap { trim: false })
        .style(Style::default().fg(theme::base_fg(mode)))
        .block(
            Block::default()
                .title(Span::styled(
                    " Preview ",
                    Style::default()
                        .fg(theme::accent(mode))
                        .add_modifier(Modifier::BOLD),
                ))
                .borders(Borders::ALL)
                .border_style(Style::default().fg(theme::input_border_color(mode)))
                .padding(Padding::new(1, 1, 0, 0)),
        );
    frame.render_widget(preview, chunks[2]);
}

// ── Permission prompt overlay ────────────────────────────────────────

pub(crate) fn draw_permission_prompt(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(60, 30, frame.area());
    render_popup_surface(frame, area, mode);

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
        Line::from(vec![
            Span::styled("  Press ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(
                "?",
                Style::default()
                    .fg(theme::accent(mode))
                    .add_modifier(Modifier::BOLD),
            ),
            Span::styled(
                " to inspect why this request needs approval",
                Style::default().fg(theme::muted_fg(mode)),
            ),
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

pub(crate) fn draw_mutation_review(frame: &mut Frame, app: &App) {
    let Some(review) = app.mutation_review.as_ref() else {
        return;
    };
    let mode = app.theme_mode;
    let area = centered_rect(82, 82, frame.area());
    render_popup_surface(frame, area, mode);

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

pub(crate) fn draw_context_inspector(frame: &mut Frame, app: &App) {
    let Some(inspector) = app.context_inspector.as_ref() else {
        return;
    };
    let mode = app.theme_mode;
    let area = centered_rect(82, 82, frame.area());
    render_popup_surface(frame, area, mode);

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

pub(crate) fn draw_timeline(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(82, 82, frame.area());
    render_popup_surface(frame, area, mode);

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

pub(crate) fn draw_transcript_search(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(84, 84, frame.area());
    render_popup_surface(frame, area, mode);

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

pub(crate) fn draw_plan_review(frame: &mut Frame, app: &App) {
    let mode = app.theme_mode;
    let area = centered_rect(70, 70, frame.area());
    render_popup_surface(frame, area, mode);

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

    if !app.plan.summary.is_empty() {
        lines.push(Line::from(Span::styled(
            format!("  {}", app.plan.summary),
            Style::default().fg(theme::muted_fg(mode)),
        )));
        lines.push(Line::from(""));
    }

    if !app.plan.original_request.is_empty() {
        lines.push(Line::from(vec![
            Span::styled("  Request: ", Style::default().fg(theme::muted_fg(mode))),
            Span::styled(
                app.plan.original_request.clone(),
                Style::default().fg(theme::base_fg(mode)),
            ),
        ]));
        lines.push(Line::from(""));
    }

    for (i, step) in app.plan.steps.iter().enumerate() {
        let (marker, style) = match step.status {
            crate::app::PlanStepStatus::Pending => {
                if i == app.plan.current_step {
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
            if app.plan.review_read_only {
                "Enter"
            } else {
                "Enter"
            },
            Style::default()
                .fg(if app.plan.review_read_only {
                    theme::accent(mode)
                } else {
                    theme::success(mode)
                })
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            if app.plan.review_read_only {
                " to close, "
            } else if app.plan.is_execution_gate {
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
            if app.plan.review_read_only {
                " to dismiss"
            } else if app.plan.is_execution_gate {
                " to reject"
            } else {
                " to cancel"
            },
            Style::default().fg(theme::muted_fg(mode)),
        ),
    ]));
    lines.push(Line::from(vec![
        Span::styled("  Press ", Style::default().fg(theme::muted_fg(mode))),
        Span::styled(
            "?",
            Style::default()
                .fg(theme::accent(mode))
                .add_modifier(Modifier::BOLD),
        ),
        Span::styled(
            " to inspect what this approval gate means",
            Style::default().fg(theme::muted_fg(mode)),
        ),
    ]));
    if app.plan.review_read_only {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled(
            "  Driver review in progress. This client is read-only for plan approval prompts.",
            Style::default().fg(theme::warning(mode)),
        )));
    }
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

pub(crate) fn draw_compact_select(frame: &mut Frame, app: &App) {
    use crate::app::COMPACT_STRATEGIES;
    let mode = app.theme_mode;
    let area = frame.area();
    let popup_width = 52.min(area.width.saturating_sub(4));
    let popup_height = (COMPACT_STRATEGIES.len() as u16 + 4).min(area.height.saturating_sub(4));
    let x = (area.width.saturating_sub(popup_width)) / 2;
    let y = (area.height.saturating_sub(popup_height)) / 2;
    let popup_area = Rect::new(x, y, popup_width, popup_height);

    render_popup_surface(frame, popup_area, mode);

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
