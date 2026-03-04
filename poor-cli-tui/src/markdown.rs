/// Lightweight markdown-to-ratatui renderer.
///
/// Parses a subset of markdown (headings, bold, italic, code blocks, inline code,
/// lists, links) and converts them into styled `ratatui` `Line`/`Span` sequences.
use ratatui::style::Modifier;
use ratatui::text::{Line, Span};

use crate::app::ThemeMode;
use crate::theme;

/// Render a markdown string into a vec of styled `Line`s for ratatui.
pub fn render_markdown(text: &str, theme_mode: ThemeMode) -> Vec<Line<'static>> {
    let mut lines: Vec<Line<'static>> = Vec::new();
    let mut in_code_block = false;
    let mut code_lang = String::new();
    let mut code_lines: Vec<String> = Vec::new();

    for raw_line in text.lines() {
        if raw_line.starts_with("```") {
            if in_code_block {
                // End code block — flush
                lines.push(Line::from(Span::styled(
                    format!(
                        "─── {} ",
                        if code_lang.is_empty() {
                            "code"
                        } else {
                            &code_lang
                        }
                    ),
                    theme::code_block_border_style(theme_mode),
                )));
                for cl in &code_lines {
                    lines.push(Line::from(Span::styled(
                        format!("  {cl}"),
                        theme::code_block_line_style(theme_mode, &code_lang),
                    )));
                }
                lines.push(Line::from(Span::styled(
                    "───────",
                    theme::code_block_border_style(theme_mode),
                )));
                code_lines.clear();
                code_lang.clear();
                in_code_block = false;
            } else {
                // Start code block
                in_code_block = true;
                code_lang = raw_line[3..].trim().to_string();
            }
            continue;
        }

        if in_code_block {
            code_lines.push(raw_line.to_string());
            continue;
        }

        // Headings
        if raw_line.starts_with("### ") {
            lines.push(Line::from(Span::styled(
                raw_line[4..].to_string(),
                theme::heading_style(theme_mode)
                    .add_modifier(Modifier::BOLD | Modifier::UNDERLINED),
            )));
            continue;
        }
        if raw_line.starts_with("## ") {
            lines.push(Line::from(Span::styled(
                raw_line[3..].to_string(),
                theme::heading_style(theme_mode)
                    .add_modifier(Modifier::BOLD | Modifier::UNDERLINED),
            )));
            continue;
        }
        if raw_line.starts_with("# ") {
            lines.push(Line::from(Span::styled(
                raw_line[2..].to_string(),
                theme::heading_style(theme_mode)
                    .add_modifier(Modifier::BOLD | Modifier::UNDERLINED),
            )));
            continue;
        }

        // Horizontal rule
        if raw_line.trim() == "---" || raw_line.trim() == "***" || raw_line.trim() == "___" {
            lines.push(Line::from(Span::styled(
                "────────────────────────────────",
                theme::list_bullet_style(theme_mode),
            )));
            continue;
        }

        // Unordered list items
        let list_match = if raw_line.starts_with("- ") || raw_line.starts_with("* ") {
            Some(&raw_line[2..])
        } else if raw_line.starts_with("  - ") || raw_line.starts_with("  * ") {
            Some(&raw_line[4..])
        } else {
            None
        };

        if let Some(item_text) = list_match {
            let mut spans = vec![Span::styled("  • ", theme::list_bullet_style(theme_mode))];
            spans.extend(parse_inline_spans(item_text, theme_mode));
            lines.push(Line::from(spans));
            continue;
        }

        // Ordered list items (simple: "1. ", "2. ", etc.)
        if let Some(rest) = strip_ordered_list_prefix(raw_line) {
            let num_end = raw_line.find('.').unwrap_or(0);
            let num_str = &raw_line[..=num_end];
            let mut spans = vec![Span::styled(
                format!("  {num_str} "),
                theme::list_bullet_style(theme_mode),
            )];
            spans.extend(parse_inline_spans(rest, theme_mode));
            lines.push(Line::from(spans));
            continue;
        }

        // Empty line
        if raw_line.trim().is_empty() {
            lines.push(Line::from(""));
            continue;
        }

        // Normal paragraph — parse inline formatting
        let spans = parse_inline_spans(raw_line, theme_mode);
        lines.push(Line::from(spans));
    }

    // Flush trailing code block
    if in_code_block && !code_lines.is_empty() {
        lines.push(Line::from(Span::styled(
            format!(
                "─── {} ",
                if code_lang.is_empty() {
                    "code"
                } else {
                    &code_lang
                }
            ),
            theme::code_block_border_style(theme_mode),
        )));
        for cl in &code_lines {
            lines.push(Line::from(Span::styled(
                format!("  {cl}"),
                theme::code_block_line_style(theme_mode, &code_lang),
            )));
        }
        lines.push(Line::from(Span::styled(
            "───────",
            theme::code_block_border_style(theme_mode),
        )));
    }

    lines
}

/// Parse inline markdown spans: `**bold**`, `*italic*`, `` `code` ``, `[text](url)`.
fn parse_inline_spans(text: &str, theme_mode: ThemeMode) -> Vec<Span<'static>> {
    let mut spans: Vec<Span<'static>> = Vec::new();
    let mut remaining = text;

    while !remaining.is_empty() {
        // Try to find the next special marker
        let bold_pos = remaining.find("**");
        let italic_pos = remaining.find('*').filter(|&p| {
            // Make sure it's not the start of a ** pair
            remaining.get(p..p + 2) != Some("**")
        });
        let code_pos = remaining.find('`');
        let link_pos = remaining.find('[');

        // Find earliest marker
        let positions: Vec<(usize, &str)> = [
            bold_pos.map(|p| (p, "**")),
            italic_pos.map(|p| (p, "*")),
            code_pos.map(|p| (p, "`")),
            link_pos.map(|p| (p, "[")),
        ]
        .into_iter()
        .flatten()
        .collect();

        let next = positions.iter().min_by_key(|(pos, _)| *pos);

        match next {
            None => {
                // No more markers; push the rest as plain text
                spans.push(Span::raw(remaining.to_string()));
                break;
            }
            Some(&(pos, marker)) => {
                // Push text before the marker
                if pos > 0 {
                    spans.push(Span::raw(remaining[..pos].to_string()));
                }

                let after_marker = &remaining[pos + marker.len()..];

                match marker {
                    "**" => {
                        if let Some(end) = after_marker.find("**") {
                            let bold_text = &after_marker[..end];
                            spans.push(Span::styled(
                                bold_text.to_string(),
                                theme::bold_style(theme_mode),
                            ));
                            remaining = &after_marker[end + 2..];
                        } else {
                            spans.push(Span::raw("**".to_string()));
                            remaining = after_marker;
                        }
                    }
                    "*" => {
                        if let Some(end) = after_marker.find('*') {
                            let italic_text = &after_marker[..end];
                            spans.push(Span::styled(
                                italic_text.to_string(),
                                theme::italic_style(theme_mode),
                            ));
                            remaining = &after_marker[end + 1..];
                        } else {
                            spans.push(Span::raw("*".to_string()));
                            remaining = after_marker;
                        }
                    }
                    "`" => {
                        if let Some(end) = after_marker.find('`') {
                            let code_text = &after_marker[..end];
                            spans.push(Span::styled(
                                code_text.to_string(),
                                theme::inline_code_style(theme_mode),
                            ));
                            remaining = &after_marker[end + 1..];
                        } else {
                            spans.push(Span::raw("`".to_string()));
                            remaining = after_marker;
                        }
                    }
                    "[" => {
                        // Try to parse [text](url)
                        if let Some(close_bracket) = after_marker.find(']') {
                            let link_text = &after_marker[..close_bracket];
                            let after_bracket = &after_marker[close_bracket + 1..];
                            if after_bracket.starts_with('(') {
                                if let Some(close_paren) = after_bracket.find(')') {
                                    let _url = &after_bracket[1..close_paren];
                                    spans.push(Span::styled(
                                        link_text.to_string(),
                                        theme::link_style(theme_mode),
                                    ));
                                    remaining = &after_bracket[close_paren + 1..];
                                } else {
                                    spans.push(Span::raw("[".to_string()));
                                    remaining = after_marker;
                                }
                            } else {
                                spans.push(Span::raw("[".to_string()));
                                remaining = after_marker;
                            }
                        } else {
                            spans.push(Span::raw("[".to_string()));
                            remaining = after_marker;
                        }
                    }
                    _ => {
                        spans.push(Span::raw(marker.to_string()));
                        remaining = after_marker;
                    }
                }
            }
        }
    }

    spans
}

/// Strip an ordered list prefix like "1. " and return the rest.
fn strip_ordered_list_prefix(line: &str) -> Option<&str> {
    let trimmed = line.trim_start();
    let dot_pos = trimmed.find(". ")?;
    let num_part = &trimmed[..dot_pos];
    if num_part.chars().all(|c| c.is_ascii_digit()) && !num_part.is_empty() {
        Some(&trimmed[dot_pos + 2..])
    } else {
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_render_heading() {
        let lines = render_markdown("# Hello", ThemeMode::Dark);
        assert_eq!(lines.len(), 1);
    }

    #[test]
    fn test_render_code_block() {
        let md = "```python\nprint('hi')\n```";
        let lines = render_markdown(md, ThemeMode::Dark);
        assert!(lines.len() >= 3);
    }

    #[test]
    fn test_render_code_block_in_light_mode() {
        let md = "```rust\nfn main() {}\n```";
        let lines = render_markdown(md, ThemeMode::Light);
        assert!(lines.len() >= 3);
    }

    #[test]
    fn test_inline_bold() {
        let spans = parse_inline_spans("Hello **world**!", ThemeMode::Dark);
        assert!(spans.len() >= 3);
    }
}
