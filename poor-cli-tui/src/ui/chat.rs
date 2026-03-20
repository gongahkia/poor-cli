use ratatui::{
    style::{Modifier, Style},
    text::{Line, Span},
};
use std::cell::RefCell;
use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use crate::app::{App, MessageRole, ThemeMode};
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

pub(crate) fn cached_chat_lines(app: &App, mode: ThemeMode) -> Vec<Line<'static>> {
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

pub(crate) fn clear_cache() {
    CHAT_RENDER_CACHE.with(|cache| {
        cache.borrow_mut().take();
    });
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

#[derive(Debug, Clone, PartialEq, Eq)]
struct ConfidenceDisplay {
    label: String,
    percent: u8,
}

fn parse_confidence_display(text: &str) -> (String, Option<ConfidenceDisplay>) {
    let lines: Vec<&str> = text.lines().collect();
    let Some(confidence_index) = lines.iter().rposition(|line| !line.trim().is_empty()) else {
        return (String::new(), None);
    };

    let candidate = lines[confidence_index].trim();
    let lower = candidate.to_ascii_lowercase();
    if !lower.starts_with("confidence:") {
        return (text.to_string(), None);
    }

    let after_prefix = candidate["confidence:".len()..].trim();
    let Some(percent_start) = after_prefix.rfind('(') else {
        return (text.to_string(), None);
    };
    let Some(percent_end) = after_prefix[percent_start..].find('%') else {
        return (text.to_string(), None);
    };
    let label = after_prefix[..percent_start].trim();
    let percent_text = after_prefix[percent_start + 1..percent_start + percent_end].trim();
    let Ok(percent) = percent_text.parse::<u8>() else {
        return (text.to_string(), None);
    };

    let mut remaining = lines[..confidence_index]
        .iter()
        .map(|line| (*line).to_string())
        .collect::<Vec<_>>();
    while remaining.last().is_some_and(|line| line.trim().is_empty()) {
        remaining.pop();
    }

    (
        remaining.join("\n"),
        Some(ConfidenceDisplay {
            label: if label.is_empty() {
                "Unknown".to_string()
            } else {
                label.to_string()
            },
            percent,
        }),
    )
}

fn is_markdown_list_line(line: &str) -> bool {
    let trimmed = line.trim_start();
    if trimmed.starts_with("- ") || trimmed.starts_with("* ") {
        return true;
    }

    let Some(dot_pos) = trimmed.find(". ") else {
        return false;
    };
    let number = &trimmed[..dot_pos];
    !number.is_empty() && number.chars().all(|ch| ch.is_ascii_digit())
}

fn is_markdown_heading_line(line: &str) -> bool {
    let trimmed = line.trim_start();
    trimmed.starts_with("# ") || trimmed.starts_with("## ") || trimmed.starts_with("### ")
}

fn compact_assistant_display_text(text: &str) -> String {
    let lines: Vec<&str> = text.lines().collect();
    let mut compacted: Vec<String> = Vec::new();
    let mut in_code_block = false;
    let mut previous_blank = false;

    for (index, raw_line) in lines.iter().enumerate() {
        let line = raw_line.trim_end();
        if line.trim_start().starts_with("```") {
            in_code_block = !in_code_block;
            compacted.push(line.to_string());
            previous_blank = false;
            continue;
        }

        if in_code_block {
            compacted.push(line.to_string());
            previous_blank = line.trim().is_empty();
            continue;
        }

        if line.trim().is_empty() {
            if compacted.is_empty() || previous_blank {
                continue;
            }

            let previous_nonempty = compacted
                .iter()
                .rev()
                .find(|value| !value.trim().is_empty())
                .map(|value| value.as_str());
            let next_nonempty = lines[index + 1..]
                .iter()
                .map(|value| value.trim())
                .find(|value| !value.is_empty());

            let previous_is_compact_block = previous_nonempty.is_some_and(|value| {
                is_markdown_list_line(value) || is_markdown_heading_line(value)
            });
            let next_is_compact_block = next_nonempty.is_some_and(|value| {
                is_markdown_list_line(value) || is_markdown_heading_line(value)
            });

            if previous_is_compact_block || next_is_compact_block {
                continue;
            }

            compacted.push(String::new());
            previous_blank = true;
            continue;
        }

        compacted.push(line.to_string());
        previous_blank = false;
    }

    while compacted.first().is_some_and(|line| line.trim().is_empty()) {
        compacted.remove(0);
    }
    while compacted.last().is_some_and(|line| line.trim().is_empty()) {
        compacted.pop();
    }

    compacted.join("\n")
}

fn compact_rendered_blank_lines(lines: Vec<Line<'static>>) -> Vec<Line<'static>> {
    let mut compacted = Vec::new();
    let mut previous_blank = false;

    for line in lines {
        let is_blank = line.spans.iter().all(|span| span.content.trim().is_empty());
        if is_blank {
            if compacted.is_empty() || previous_blank {
                continue;
            }
            previous_blank = true;
            compacted.push(Line::from(""));
        } else {
            previous_blank = false;
            compacted.push(line);
        }
    }

    while compacted
        .last()
        .is_some_and(|line| line.spans.iter().all(|span| span.content.trim().is_empty()))
    {
        compacted.pop();
    }

    compacted
}

fn confidence_style(mode: ThemeMode, percent: u8) -> Style {
    let color = if percent >= 85 {
        theme::success(mode)
    } else if percent >= 65 {
        theme::accent(mode)
    } else if percent >= 40 {
        theme::warning(mode)
    } else {
        theme::error(mode)
    };
    Style::default().fg(color).add_modifier(Modifier::BOLD)
}

fn build_chat_lines(app: &App, mode: ThemeMode) -> Vec<Line<'static>> {
    let mut all_lines: Vec<Line<'static>> = Vec::new();

    for msg in &app.messages {
        if !all_lines.is_empty() {
            all_lines.push(Line::from(""));
        }

        match &msg.role {
            MessageRole::Welcome => {
                let lines: Vec<String> = msg.content.lines().map(ToString::to_string).collect();
                // find the blank line separating the logo from the info block
                let sep = lines.iter().position(|l| l.trim().is_empty()).unwrap_or(0);
                // logo lines
                for line in lines.iter().take(sep) {
                    all_lines.push(Line::from(Span::styled(
                        format!("  {line}"),
                        theme::brand_style(mode),
                    )));
                }
                // info block starts after the separator blank line
                let info = &lines[sep..];
                let info: Vec<&String> = info.iter().skip_while(|l| l.trim().is_empty()).collect();
                if let Some(title) = info.first() {
                    all_lines.push(Line::from(Span::styled(
                        format!("  {title}"),
                        theme::brand_style(mode),
                    )));
                }
                if let Some(model_line) = info.get(1) {
                    all_lines.push(Line::from(Span::styled(
                        format!("  {model_line}"),
                        Style::default().fg(theme::base_fg(mode)),
                    )));
                }
                if let Some(workspace_line) = info.get(2) {
                    all_lines.push(Line::from(Span::styled(
                        format!("  {workspace_line}"),
                        Style::default().fg(theme::muted_fg(mode)),
                    )));
                }
                let extra = info.iter().skip(3).skip_while(|l| l.trim().is_empty());
                for line in extra {
                    let style = if line.starts_with('?') {
                        Style::default().fg(theme::warning(mode))
                    } else {
                        Style::default().fg(theme::muted_fg(mode))
                    };
                    all_lines.push(Line::from(Span::styled(format!("  {line}"), style)));
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
                let (assistant_body, confidence) = parse_confidence_display(&msg.content);
                let compact_body = compact_assistant_display_text(&assistant_body);
                let mut header_spans = vec![
                    Span::styled("  ✦ ", Style::default().fg(theme::assistant_color(mode))),
                    Span::styled("poor-cli", theme::assistant_label_style(mode)),
                ];
                if let Some(confidence) = &confidence {
                    header_spans.push(Span::raw("  ".to_string()));
                    header_spans.push(Span::styled(
                        "confidence",
                        Style::default().fg(theme::muted_fg(mode)),
                    ));
                    header_spans.push(Span::raw(" ".to_string()));
                    header_spans.push(Span::styled(
                        confidence.label.clone(),
                        confidence_style(mode, confidence.percent),
                    ));
                    header_spans.push(Span::styled(
                        format!(" {}%", confidence.percent),
                        confidence_style(mode, confidence.percent),
                    ));
                } else {
                    header_spans.push(Span::raw("  ".to_string()));
                    header_spans.push(Span::styled(
                        "confidence unavailable",
                        Style::default().fg(theme::muted_fg(mode)),
                    ));
                }
                all_lines.push(Line::from(header_spans));

                let md_lines =
                    compact_rendered_blank_lines(markdown::render_markdown(&compact_body, mode));
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

#[cfg(test)]
mod tests {
    use super::*;

    fn line_text(line: &Line<'static>) -> String {
        line.spans
            .iter()
            .map(|span| span.content.as_ref())
            .collect::<Vec<_>>()
            .join("")
    }

    #[test]
    fn parse_confidence_display_extracts_trailing_confidence_line() {
        let (body, confidence) = parse_confidence_display("Answer body\n\nConfidence: High (70%)");

        assert_eq!(body, "Answer body");
        assert_eq!(
            confidence,
            Some(ConfidenceDisplay {
                label: "High".to_string(),
                percent: 70,
            })
        );
    }

    #[test]
    fn compact_assistant_display_text_removes_list_spacing() {
        let compacted = compact_assistant_display_text(
            "Intro paragraph.\n\n1. First item\n\n2. Second item\n\nClosing line.",
        );

        assert_eq!(
            compacted,
            "Intro paragraph.\n1. First item\n2. Second item\nClosing line."
        );
    }

    #[test]
    fn build_chat_lines_formats_confidence_in_header() {
        let mut app = App::new();
        app.messages.push(crate::app::ChatMessage::assistant(
            "One sentence answer.\n\nConfidence: Very High (90%)",
        ));

        let lines = build_chat_lines(&app, ThemeMode::Dark);

        assert!(line_text(&lines[0]).contains("poor-cli"));
        assert!(line_text(&lines[0]).contains("confidence"));
        assert!(line_text(&lines[0]).contains("Very High 90%"));
        assert!(line_text(&lines[1]).contains("One sentence answer."));
        assert!(!lines
            .iter()
            .any(|line| line_text(line).contains("Confidence: Very High")));
    }
}
