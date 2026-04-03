use super::*;

pub(crate) fn compute_chrome_rects(
    size: PhysicalSize<u32>,
    tab_bar_visible: bool,
    status_bar_visible: bool,
) -> ChromeRects {
    let width = size.width as f32;
    let height = size.height as f32;
    let tab_bar_height = if tab_bar_visible { 32.0 } else { 0.0 };
    let status_height = if status_bar_visible { 24.0 } else { 0.0 };

    ChromeRects {
        tab_bar: Rect::new(0.0, 0.0, width, tab_bar_height),
        content: Rect::new(
            0.0,
            tab_bar_height,
            width,
            (height - tab_bar_height - status_height).max(0.0),
        ),
        status: Rect::new(0.0, (height - status_height).max(0.0), width, status_height),
    }
}

pub(crate) fn compute_pane_ui_rects(
    container: Rect,
    input_position: walk_input::editor::InputPosition,
    input_lines: usize,
    cell_height: f32,
    show_input: bool,
) -> UiRects {
    let line_count = input_lines.clamp(1, 8) as f32;
    let input_height = if show_input {
        (line_count * cell_height + 20.0).min((container.h * 0.45).max(cell_height))
    } else {
        0.0
    };

    match input_position {
        walk_input::editor::InputPosition::Top => UiRects {
            viewport: Rect::new(
                container.x,
                container.y + input_height,
                container.w,
                (container.h - input_height).max(cell_height),
            ),
            input: Rect::new(container.x, container.y, container.w, input_height),
        },
        walk_input::editor::InputPosition::Bottom => UiRects {
            viewport: Rect::new(
                container.x,
                container.y,
                container.w,
                (container.h - input_height).max(cell_height),
            ),
            input: Rect::new(
                container.x,
                container.y + container.h - input_height,
                container.w,
                input_height,
            ),
        },
    }
}

pub(crate) fn pane_max_scroll(pane: &PaneRuntime) -> f32 {
    pane.terminal.state.scrollback_len() as f32
}

pub(crate) fn render_tab_bar(
    render: &mut RenderState,
    font: &mut FontSystem,
    rect: Rect,
    tabs: &[(bool, String)],
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity([0.08, 0.09, 0.13, 1.0], surface_opacity),
    );
    if tabs.is_empty() {
        return;
    }

    let tab_width = (rect.w / tabs.len() as f32).clamp(120.0, 220.0);
    for (index, (is_active, label)) in tabs.iter().enumerate() {
        let x = rect.x + index as f32 * tab_width;
        let background = if *is_active {
            [0.14, 0.16, 0.22, 1.0]
        } else {
            [0.10, 0.11, 0.15, 1.0]
        };
        render.batch.push_bg_quad(
            x,
            rect.y,
            tab_width,
            rect.h,
            with_opacity(background, surface_opacity),
        );
        push_text(
            render,
            font,
            x + 12.0,
            rect.y + 8.0,
            label,
            with_opacity([0.75, 0.79, 0.96, 1.0], surface_opacity),
        );
    }
}

pub(crate) fn render_status_bar(
    render: &mut RenderState,
    font: &mut FontSystem,
    rect: Rect,
    status_segments: Option<&StatusBarSegments>,
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity([0.08, 0.09, 0.13, 1.0], surface_opacity),
    );
    let Some(status_segments) = status_segments else {
        return;
    };

    let mut left_x = rect.x + 8.0;
    draw_status_segments(
        render,
        font,
        &status_segments.left,
        &mut left_x,
        rect.y + 4.0,
        false,
        surface_opacity,
    );

    let mut right_x = rect.x + rect.w - 8.0;
    draw_status_segments(
        render,
        font,
        &status_segments.right,
        &mut right_x,
        rect.y + 4.0,
        true,
        surface_opacity,
    );

    let center_width = status_segments
        .center
        .iter()
        .map(|segment| status_segment_width(font, segment))
        .sum::<f32>()
        + ((status_segments.center.len().saturating_sub(1) as f32) * 4.0);
    let mut center_x = rect.x + (rect.w - center_width) * 0.5;
    draw_status_segments(
        render,
        font,
        &status_segments.center,
        &mut center_x,
        rect.y + 4.0,
        false,
        surface_opacity,
    );
}

pub(crate) fn status_segment_width(font: &FontSystem, segment: &StatusSegment) -> f32 {
    let text_width = segment.text.chars().count() as f32 * font.metrics.cell_width;
    text_width + 12.0
}

pub(crate) fn draw_status_segments(
    render: &mut RenderState,
    font: &mut FontSystem,
    segments: &[StatusSegment],
    cursor_x: &mut f32,
    y: f32,
    rtl: bool,
    surface_opacity: f32,
) {
    for segment in segments {
        let width = status_segment_width(font, segment);
        let x = if rtl { *cursor_x - width } else { *cursor_x };
        if let Some(bg) = segment.bg.as_deref().and_then(parse_hex_rgba) {
            render.batch.push_bg_quad(
                x,
                y - 1.0,
                width,
                font.metrics.cell_height + 2.0,
                with_opacity(bg, surface_opacity),
            );
        }
        let color = segment
            .fg
            .as_deref()
            .and_then(parse_hex_rgba)
            .unwrap_or([0.54, 0.58, 0.65, 1.0]);
        push_text(
            render,
            font,
            x + 6.0,
            y,
            &segment.text,
            with_opacity(color, surface_opacity),
        );
        if segment.bold {
            push_text(
                render,
                font,
                x + 6.6,
                y,
                &segment.text,
                with_opacity(color, surface_opacity),
            );
        }
        if rtl {
            *cursor_x = x - 4.0;
        } else {
            *cursor_x = x + width + 4.0;
        }
    }
}

pub(crate) fn parse_hex_rgba(value: &str) -> Option<[f32; 4]> {
    let hex = value.trim().trim_start_matches('#');
    if hex.len() != 6 {
        return None;
    }
    let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
    let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
    let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
    Some([
        f32::from(r) / 255.0,
        f32::from(g) / 255.0,
        f32::from(b) / 255.0,
        1.0,
    ])
}

pub(crate) fn render_debug_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    content_rect: Rect,
    lines: &[String],
    surface_opacity: f32,
) {
    if lines.is_empty() {
        return;
    }

    let width = 260.0;
    let height = (lines.len() as f32 * font.metrics.cell_height) + 14.0;
    let x = content_rect.x + 12.0;
    let y = content_rect.y + 12.0;

    render.batch.push_bg_quad(
        x,
        y,
        width,
        height,
        with_opacity([0.06, 0.07, 0.10, 0.92], surface_opacity),
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        with_opacity([0.65, 0.77, 0.95, 0.95], surface_opacity),
    );

    for (index, line) in lines.iter().enumerate() {
        push_text(
            render,
            font,
            x + 10.0,
            y + 6.0 + index as f32 * font.metrics.cell_height,
            line,
            with_opacity([0.84, 0.88, 0.95, 1.0], surface_opacity),
        );
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_owned_input(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    rect: Rect,
    input: &walk_input::editor::InputRenderData,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity(
            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.9,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 12.0;
    let padding_y = 8.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;

    if let Some((row, col_start, col_end)) = input.parameter_placeholder {
        let width = (col_end.saturating_sub(col_start).max(1) as f32) * font.metrics.cell_width;
        render.batch.push_bg_quad(
            base_x + col_start as f32 * font.metrics.cell_width,
            base_y + row as f32 * font.metrics.cell_height,
            width,
            font.metrics.cell_height,
            with_opacity(
                [
                    theme.highlight_current_match.r,
                    theme.highlight_current_match.g,
                    theme.highlight_current_match.b,
                    0.3,
                ],
                surface_opacity,
            ),
        );
    }

    for (row, line) in input.lines.iter().enumerate() {
        push_text(
            render,
            font,
            base_x,
            base_y + row as f32 * font.metrics.cell_height,
            line,
            with_opacity(
                [
                    theme.foreground.r,
                    theme.foreground.g,
                    theme.foreground.b,
                    theme.foreground.a,
                ],
                surface_opacity,
            ),
        );
    }

    if let Some(popup) = input.completion_popup.as_ref() {
        let max_visible = 10usize;
        let mut start = popup.selected.saturating_sub(max_visible / 2);
        if start + max_visible > popup.items.len() {
            start = popup.items.len().saturating_sub(max_visible);
        }
        let end = (start + max_visible).min(popup.items.len());
        let visible = popup.items[start..end].len();
        let popup_height = (visible as f32 + 1.0) * (font.metrics.cell_height + 2.0) + 8.0;
        let popup_width = (rect.w * 0.72).clamp(260.0, 680.0);
        let anchor_x = base_x + popup.anchor_col as f32 * font.metrics.cell_width;
        let popup_x = anchor_x.clamp(rect.x + 8.0, rect.x + rect.w - popup_width - 8.0);
        let popup_y = if matches!(input.position, walk_input::editor::InputPosition::Bottom) {
            (rect.y - popup_height - 6.0).max(0.0)
        } else {
            rect.y + rect.h + 6.0
        };

        render.batch.push_bg_quad(
            popup_x,
            popup_y,
            popup_width,
            popup_height,
            with_opacity(
                [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98],
                surface_opacity,
            ),
        );
        render.batch.push_bg_quad(
            popup_x,
            popup_y,
            popup_width,
            1.0,
            with_opacity(
                [
                    theme.highlight_current_match.r,
                    theme.highlight_current_match.g,
                    theme.highlight_current_match.b,
                    0.95,
                ],
                surface_opacity,
            ),
        );

        let mut row_y = popup_y + 5.0;
        push_text(
            render,
            font,
            popup_x + 8.0,
            row_y,
            "Completions",
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.92,
                ],
                surface_opacity,
            ),
        );
        row_y += font.metrics.cell_height + 2.0;

        for (visible_offset, item) in popup.items[start..end].iter().enumerate() {
            let absolute = start + visible_offset;
            if absolute == popup.selected {
                render.batch.push_bg_quad(
                    popup_x + 4.0,
                    row_y - 1.0,
                    popup_width - 8.0,
                    font.metrics.cell_height + 2.0,
                    with_opacity(
                        [
                            theme.selection.r,
                            theme.selection.g,
                            theme.selection.b,
                            0.24,
                        ],
                        surface_opacity,
                    ),
                );
            }
            let label = format!("{} {}", completion_kind_token(&item.kind), item.text);
            push_text(
                render,
                font,
                popup_x + 8.0,
                row_y,
                &label,
                with_opacity(
                    [
                        theme.foreground.r,
                        theme.foreground.g,
                        theme.foreground.b,
                        theme.foreground.a,
                    ],
                    surface_opacity,
                ),
            );
            push_text(
                render,
                font,
                popup_x + popup_width * 0.45,
                row_y,
                &item.description,
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.9,
                    ],
                    surface_opacity,
                ),
            );
            row_y += font.metrics.cell_height + 2.0;
        }
    }

    if cursor_visible {
        if let Some((cursor_row, cursor_col)) = input.cursors.first().copied() {
            render.batch.push_cursor(
                base_x + cursor_col as f32 * font.metrics.cell_width,
                base_y + cursor_row as f32 * font.metrics.cell_height,
                font.metrics.cell_width,
                font.metrics.cell_height,
                cursor_shape,
                with_opacity(
                    [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.95],
                    surface_opacity,
                ),
            );
        }
    }
}

pub(crate) fn completion_kind_token(kind: &walk_input::completion::CompletionKind) -> &'static str {
    match kind {
        walk_input::completion::CompletionKind::Command => "[cmd]",
        walk_input::completion::CompletionKind::FilePath => "[path]",
        walk_input::completion::CompletionKind::EnvVar => "[env]",
        walk_input::completion::CompletionKind::Argument => "[arg]",
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_command_palette(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    input: &walk_input::editor::InputRenderData,
    palette: &CommandPaletteState,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    let panel_width = (viewport.w * 0.78).clamp(520.0, 980.0);
    let panel_height = (viewport.h * 0.72).clamp(220.0, 560.0);
    let rect = Rect::new(
        viewport.x + (viewport.w - panel_width) * 0.5,
        viewport.y + (viewport.h - panel_height) * 0.5,
        panel_width,
        panel_height,
    );

    render.batch.push_bg_quad(
        viewport.x,
        viewport.y,
        viewport.w,
        viewport.h,
        with_opacity([0.0, 0.0, 0.0, 0.32], surface_opacity),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity(
            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.9,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 14.0;
    let padding_y = 10.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;
    let input_line = input.lines.first().cloned().unwrap_or_default();
    let prefix = "Command Palette: ";
    push_text(
        render,
        font,
        base_x,
        base_y,
        "Run an action, workflow, alias, or recent command",
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                0.9,
            ],
            surface_opacity,
        ),
    );
    push_text(
        render,
        font,
        base_x,
        base_y + font.metrics.cell_height + 2.0,
        &format!("{prefix}{input_line}"),
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );

    let entries_max = 15usize;
    let available_entries = &palette.filtered;
    let mut start_idx = 0usize;
    if !available_entries.is_empty() {
        start_idx = palette.selected_index.saturating_sub(entries_max / 2);
        if start_idx + entries_max > available_entries.len() {
            start_idx = available_entries.len().saturating_sub(entries_max);
        }
    }
    let end_idx = (start_idx + entries_max).min(available_entries.len());
    let query = palette_query_content(&palette.query);
    let mut row_y = base_y + font.metrics.cell_height * 2.0 + 8.0;

    if available_entries.is_empty() {
        push_text(
            render,
            font,
            base_x,
            row_y,
            "No matching entries. Press Enter to run raw command input.",
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.85,
                ],
                surface_opacity,
            ),
        );
    } else {
        let mut last_category = None;
        for (visible_offset, filtered_idx) in
            available_entries[start_idx..end_idx].iter().enumerate()
        {
            let absolute_idx = start_idx + visible_offset;
            let Some(entry) = palette.entries.get(*filtered_idx) else {
                continue;
            };
            if last_category != Some(entry.category) {
                push_text(
                    render,
                    font,
                    base_x,
                    row_y,
                    palette_category_label(entry.category),
                    with_opacity(
                        [
                            theme.status_bar_text.r,
                            theme.status_bar_text.g,
                            theme.status_bar_text.b,
                            0.95,
                        ],
                        surface_opacity,
                    ),
                );
                row_y += font.metrics.cell_height + 2.0;
                last_category = Some(entry.category);
            }
            if absolute_idx == palette.selected_index {
                render.batch.push_bg_quad(
                    rect.x + 8.0,
                    row_y - 2.0,
                    rect.w - 16.0,
                    font.metrics.cell_height + 4.0,
                    with_opacity(
                        [theme.selection.r, theme.selection.g, theme.selection.b, 0.2],
                        surface_opacity,
                    ),
                );
            }
            for column in palette_highlight_columns(&entry.label, query) {
                render.batch.push_bg_quad(
                    base_x + column as f32 * font.metrics.cell_width,
                    row_y - 1.0,
                    font.metrics.cell_width,
                    font.metrics.cell_height + 2.0,
                    with_opacity(
                        [
                            theme.highlight_current_match.r,
                            theme.highlight_current_match.g,
                            theme.highlight_current_match.b,
                            0.22,
                        ],
                        surface_opacity,
                    ),
                );
            }
            push_text(
                render,
                font,
                base_x,
                row_y,
                &entry.label,
                with_opacity(
                    [
                        theme.foreground.r,
                        theme.foreground.g,
                        theme.foreground.b,
                        theme.foreground.a,
                    ],
                    surface_opacity,
                ),
            );
            push_text(
                render,
                font,
                base_x + 220.0,
                row_y,
                &entry.description,
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.9,
                    ],
                    surface_opacity,
                ),
            );
            row_y += font.metrics.cell_height + 4.0;
        }
        if available_entries.len() > entries_max {
            let indicator = format!(
                "{}-{} of {}",
                start_idx + 1,
                end_idx,
                available_entries.len()
            );
            push_text(
                render,
                font,
                rect.x + rect.w - 130.0,
                rect.y + rect.h - font.metrics.cell_height - 8.0,
                &indicator,
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.85,
                    ],
                    surface_opacity,
                ),
            );
        }
    }

    if cursor_visible {
        if let Some((cursor_row, cursor_col)) = input.cursors.first().copied() {
            let cursor_x = base_x
                + prefix.chars().count() as f32 * font.metrics.cell_width
                + cursor_col as f32 * font.metrics.cell_width;
            let cursor_y = base_y
                + font.metrics.cell_height
                + 2.0
                + cursor_row as f32 * font.metrics.cell_height;
            render.batch.push_cursor(
                cursor_x,
                cursor_y,
                font.metrics.cell_width,
                font.metrics.cell_height,
                cursor_shape,
                with_opacity(
                    [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.95],
                    surface_opacity,
                ),
            );
        }
    }
}

pub(crate) fn palette_category_label(category: PaletteCategory) -> &'static str {
    match category {
        PaletteCategory::Action => "Actions",
        PaletteCategory::LuaCommand => "Lua Commands",
        PaletteCategory::Workflow => "Workflows",
        PaletteCategory::RecentCommand => "Recent Commands",
        PaletteCategory::FilePath => "File Paths",
    }
}

pub(crate) fn palette_query_content(query: &str) -> &str {
    let trimmed = query.trim();
    if let Some(stripped) = trimmed.strip_prefix('>') {
        return stripped.trim_start();
    }
    if let Some(stripped) = trimmed.strip_prefix('@') {
        return stripped.trim_start();
    }
    trimmed
}

pub(crate) fn palette_highlight_columns(label: &str, query: &str) -> Vec<usize> {
    if query.is_empty() {
        return Vec::new();
    }

    let label_chars = label.chars().collect::<Vec<_>>();
    let query_chars = query.to_ascii_lowercase().chars().collect::<Vec<_>>();
    let mut columns = Vec::new();
    let mut cursor = 0usize;

    for query_char in query_chars {
        let mut matched = None;
        for (idx, label_char) in label_chars.iter().enumerate().skip(cursor) {
            if label_char.to_ascii_lowercase() == query_char {
                matched = Some(idx);
                break;
            }
        }
        let Some(idx) = matched else {
            return Vec::new();
        };
        columns.push(idx);
        cursor = idx + 1;
    }

    columns
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_command_search(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    rect: Rect,
    command_search: &CommandSearchState,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity(
            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.98],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.9,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 12.0;
    let padding_y = 8.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;
    let prefix = "History: ";
    push_text(
        render,
        font,
        base_x,
        base_y,
        &format!("{prefix}{}", command_search.query),
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );

    let counter = command_search.match_count_display();
    push_text(
        render,
        font,
        rect.x + rect.w - 100.0,
        base_y,
        &counter,
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                0.85,
            ],
            surface_opacity,
        ),
    );

    let mut row_y = base_y + font.metrics.cell_height + 6.0;
    if command_search.results.is_empty() {
        push_text(
            render,
            font,
            base_x,
            row_y,
            "No matching commands",
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.85,
                ],
                surface_opacity,
            ),
        );
    } else {
        let mut last_scope = None;
        for (index, result) in command_search.results.iter().take(6).enumerate() {
            if last_scope != Some(result.scope) {
                let section_title = match result.scope {
                    CommandSearchScope::Pane => "Current Pane",
                    CommandSearchScope::Global => "Global History",
                };
                push_text(
                    render,
                    font,
                    base_x,
                    row_y,
                    section_title,
                    with_opacity(
                        [
                            theme.highlight_current_match.r,
                            theme.highlight_current_match.g,
                            theme.highlight_current_match.b,
                            0.95,
                        ],
                        surface_opacity,
                    ),
                );
                row_y += font.metrics.cell_height;
                last_scope = Some(result.scope);
            }

            if index == command_search.current {
                render.batch.push_bg_quad(
                    rect.x + 8.0,
                    row_y - 2.0,
                    rect.w - 16.0,
                    font.metrics.cell_height + 4.0,
                    with_opacity(
                        [theme.selection.r, theme.selection.g, theme.selection.b, 0.2],
                        surface_opacity,
                    ),
                );
            }

            push_text(
                render,
                font,
                base_x,
                row_y,
                &result.entry.command,
                with_opacity(
                    [
                        theme.foreground.r,
                        theme.foreground.g,
                        theme.foreground.b,
                        theme.foreground.a,
                    ],
                    surface_opacity,
                ),
            );
            push_text(
                render,
                font,
                base_x + 260.0,
                row_y,
                &history_metadata_label(&result.entry),
                with_opacity(
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        0.9,
                    ],
                    surface_opacity,
                ),
            );
            row_y += font.metrics.cell_height + 4.0;
        }
    }

    if cursor_visible {
        render.batch.push_cursor(
            base_x
                + prefix.chars().count() as f32 * font.metrics.cell_width
                + command_search.query.chars().count() as f32 * font.metrics.cell_width,
            base_y,
            font.metrics.cell_width,
            font.metrics.cell_height,
            cursor_shape,
            with_opacity(
                [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.95],
                surface_opacity,
            ),
        );
    }
}

pub(crate) fn history_metadata_label(entry: &HistoryEntry) -> String {
    let cwd = entry
        .cwd
        .as_ref()
        .map_or_else(|| "~".to_string(), |path| path.display().to_string());
    let exit = entry
        .exit_code
        .map_or_else(|| "exit ?".to_string(), |code| format!("exit {code}"));
    let duration = entry
        .duration_ms
        .map_or_else(String::new, |ms| format!(" | {}ms", ms));
    format!("{cwd} | {exit}{duration}")
}

pub(crate) fn render_search_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    search: &walk_ui::search::GlobalSearch,
    surface_opacity: f32,
) {
    let width = (viewport.w * 0.38).clamp(220.0, 420.0);
    let height = font.metrics.cell_height * 2.0 + 16.0;
    let x = viewport.x + viewport.w - width - 12.0;
    let y = viewport.y + 12.0;

    render.batch.push_bg_quad(
        x,
        y,
        width,
        height,
        with_opacity(
            [
                theme.tab_bar_bg.r,
                theme.tab_bar_bg.g,
                theme.tab_bar_bg.b,
                0.96,
            ],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.85,
            ],
            surface_opacity,
        ),
    );

    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0,
        &format!("Search: {}", search.search_input),
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0 + font.metrics.cell_height,
        &search.match_count_display(),
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                theme.status_bar_text.a,
            ],
            surface_opacity,
        ),
    );
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_quick_select_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    visible_start_row: usize,
    visible_screen_lines: usize,
    matches: &[walk_ui::quick_select::QuickSelectMatch],
    typed_label: &str,
    surface_opacity: f32,
) {
    if visible_screen_lines == 0 {
        return;
    }

    for candidate in matches {
        if candidate.row < visible_start_row {
            continue;
        }
        let viewport_row = candidate.row - visible_start_row;
        if viewport_row >= visible_screen_lines {
            continue;
        }

        let row_y = viewport.y + viewport_row as f32 * font.metrics.cell_height;
        let x = viewport.x + candidate.col_start as f32 * font.metrics.cell_width;
        let width = (candidate.col_end.saturating_sub(candidate.col_start) as f32).max(1.0)
            * font.metrics.cell_width;
        let active = !typed_label.is_empty() && candidate.label.starts_with(typed_label);
        let fill = if active {
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.55,
            ]
        } else {
            [
                theme.highlight_match.r,
                theme.highlight_match.g,
                theme.highlight_match.b,
                0.35,
            ]
        };
        render.batch.push_bg_quad(
            x,
            row_y,
            width,
            font.metrics.cell_height,
            with_opacity(fill, surface_opacity),
        );

        let label_x = x;
        let label_y = row_y;
        render.batch.push_bg_quad(
            label_x,
            label_y,
            candidate.label.chars().count() as f32 * font.metrics.cell_width + 4.0,
            font.metrics.cell_height,
            with_opacity(
                [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.85],
                surface_opacity,
            ),
        );
        push_text(
            render,
            font,
            label_x + 2.0,
            label_y,
            &candidate.label,
            with_opacity(
                [
                    theme.background.r,
                    theme.background.g,
                    theme.background.b,
                    0.95,
                ],
                surface_opacity,
            ),
        );
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_replay_snapshot(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    snapshot: &ReplaySnapshot,
    replay_store: &ReplayStore,
    snapshot_index: usize,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    focused: bool,
    broadcast_input: bool,
    window_opacity: f32,
    terminal_surface_alpha: f32,
) {
    let rows = snapshot.visible_rows();
    if rows.is_empty() {
        return;
    }

    let cell_width = font.metrics.cell_width;
    let cell_height = font.metrics.cell_height;
    for (row_idx, row) in rows.iter().enumerate() {
        let row_y = viewport.y + row_idx as f32 * cell_height;
        for (col_idx, cell) in row.iter().enumerate() {
            let x = viewport.x + col_idx as f32 * cell_width;
            let mut bg = resolve_cell_color(&cell.bg, theme, true);
            let mut fg = resolve_cell_color(&cell.fg, theme, false);
            if cell.is_inverse {
                std::mem::swap(&mut bg, &mut fg);
            }
            if matches!(cell.bg, CellColor::Named(idx) if idx >= 16) {
                bg[3] *= terminal_surface_alpha;
            }

            render
                .batch
                .push_bg_quad(x, row_y, cell_width, cell_height, bg);
            if cell.character != ' ' && cell.character != '\0' {
                push_glyph(render, font, x, row_y, cell.character, fg);
            }
        }
    }

    if cursor_visible {
        let visible_start = snapshot.visible_start_row();
        let visible_end = visible_start + rows.len();
        if (visible_start..visible_end).contains(&snapshot.cursor_row) {
            let cursor_row = snapshot.cursor_row - visible_start;
            render.batch.push_cursor(
                viewport.x + snapshot.cursor_col as f32 * cell_width,
                viewport.y + cursor_row as f32 * cell_height,
                cell_width,
                cell_height,
                cursor_shape,
                [
                    theme.cursor.r,
                    theme.cursor.g,
                    theme.cursor.b,
                    0.7 * window_opacity,
                ],
            );
        }
    }

    let border_color = if broadcast_input {
        [
            theme.block_error_accent.r,
            theme.block_error_accent.g,
            theme.block_error_accent.b,
            0.95,
        ]
    } else {
        [
            theme.block_separator.r,
            theme.block_separator.g,
            theme.block_separator.b,
            0.9,
        ]
    };
    render
        .batch
        .push_bg_quad(viewport.x, viewport.y, viewport.w, 1.0, border_color);
    render
        .batch
        .push_bg_quad(viewport.x, viewport.y, 1.0, viewport.h, border_color);
    if focused {
        render.batch.push_bg_quad(
            viewport.x,
            viewport.y,
            viewport.w,
            2.0,
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.8,
            ],
        );
    }

    let timeline = ReplayTimeline {
        snapshot_count: replay_store.len(),
        current_index: snapshot_index,
        marker_indices: replay_store.marker_indices(),
    };
    let bar_x = viewport.x + 10.0;
    let bar_w = (viewport.w - 20.0).max(24.0);
    let bar_y = viewport.y + viewport.h - 6.0;
    render.batch.push_bg_quad(
        bar_x,
        bar_y,
        bar_w,
        2.0,
        [
            theme.status_bar_text.r,
            theme.status_bar_text.g,
            theme.status_bar_text.b,
            0.35,
        ],
    );
    for marker in timeline.marker_positions() {
        render.batch.push_bg_quad(
            bar_x + marker * bar_w,
            bar_y - 2.0,
            1.5,
            6.0,
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.85,
            ],
        );
    }
    render.batch.push_bg_quad(
        bar_x + timeline.cursor_position() * bar_w,
        bar_y - 3.0,
        2.0,
        8.0,
        [theme.cursor.r, theme.cursor.g, theme.cursor.b, 0.92],
    );
}

pub(crate) fn render_block_query_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    block_query: &BlockQueryState,
    filtered_lines: &[(usize, String)],
    surface_opacity: f32,
) {
    let is_filter = matches!(block_query.mode, BlockQueryMode::Filter);
    let width = if is_filter {
        (viewport.w * 0.48).clamp(280.0, 520.0)
    } else {
        (viewport.w * 0.4).clamp(240.0, 420.0)
    };
    let list_height = if is_filter {
        (viewport.h * 0.42).clamp(
            font.metrics.cell_height * 4.0,
            font.metrics.cell_height * 12.0,
        )
    } else {
        0.0
    };
    let height = font.metrics.cell_height * 2.0 + 16.0 + list_height;
    let x = viewport.x + viewport.w - width - 12.0;
    let y = viewport.y + 12.0;

    render.batch.push_bg_quad(
        x,
        y,
        width,
        height,
        with_opacity(
            [
                theme.tab_bar_bg.r,
                theme.tab_bar_bg.g,
                theme.tab_bar_bg.b,
                0.96,
            ],
            surface_opacity,
        ),
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        with_opacity(
            [
                theme.highlight_current_match.r,
                theme.highlight_current_match.g,
                theme.highlight_current_match.b,
                0.85,
            ],
            surface_opacity,
        ),
    );

    let title = match block_query.mode {
        BlockQueryMode::Find => "Find Block",
        BlockQueryMode::Filter => "Filter Block",
    };
    let header_text = if block_query.query.is_empty() {
        title.to_string()
    } else {
        format!("{title}: {}", block_query.query)
    };
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0,
        &header_text,
        with_opacity(
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                theme.foreground.a,
            ],
            surface_opacity,
        ),
    );
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0 + font.metrics.cell_height,
        &block_query.match_count_display(),
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                theme.status_bar_text.a,
            ],
            surface_opacity,
        ),
    );

    if !is_filter {
        return;
    }

    let lines_y = y + 12.0 + font.metrics.cell_height * 2.0;
    let max_chars = ((width - 24.0) / font.metrics.cell_width).floor().max(8.0) as usize;
    let max_visible_lines = filter_overlay_visible_lines(viewport, font.metrics.cell_height);
    let current_filtered_line = block_query.current_filtered_line();

    if filtered_lines.is_empty() {
        let empty_text = if block_query.query.is_empty() {
            "Type to filter block output"
        } else {
            "No lines matched"
        };
        push_text(
            render,
            font,
            x + 10.0,
            lines_y,
            empty_text,
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    theme.status_bar_text.a,
                ],
                surface_opacity,
            ),
        );
        return;
    }

    for (visible_idx, (line_idx, text)) in filtered_lines
        .iter()
        .skip(block_query.overlay_scroll_offset)
        .take(max_visible_lines)
        .enumerate()
    {
        let row_y = lines_y + visible_idx as f32 * font.metrics.cell_height;
        if current_filtered_line == Some(*line_idx) {
            render.batch.push_bg_quad(
                x + 8.0,
                row_y,
                width - 16.0,
                font.metrics.cell_height,
                with_opacity(
                    [
                        theme.highlight_current_match.r,
                        theme.highlight_current_match.g,
                        theme.highlight_current_match.b,
                        0.28,
                    ],
                    surface_opacity,
                ),
            );
        }

        let line_label = format!(
            "{:>4} {}",
            line_idx + 1,
            truncate_overlay_text(text, max_chars)
        );
        push_text(
            render,
            font,
            x + 10.0,
            row_y,
            &line_label,
            with_opacity(
                [
                    theme.foreground.r,
                    theme.foreground.g,
                    theme.foreground.b,
                    theme.foreground.a,
                ],
                surface_opacity,
            ),
        );
    }
}

pub(crate) fn filter_overlay_visible_lines(viewport: Rect, cell_height: f32) -> usize {
    (((viewport.h * 0.42).clamp(cell_height * 4.0, cell_height * 12.0)) / cell_height)
        .floor()
        .max(1.0) as usize
}

pub(crate) fn truncate_overlay_text(text: &str, max_chars: usize) -> String {
    let mut truncated = text.chars().take(max_chars).collect::<String>();
    if text.chars().count() > max_chars && max_chars > 3 {
        truncated.truncate(max_chars.saturating_sub(3));
        truncated.push_str("...");
    }
    truncated
}

pub(crate) fn with_opacity(mut color: [f32; 4], opacity: f32) -> [f32; 4] {
    color[3] *= opacity.clamp(0.0, 1.0);
    color
}

pub(crate) fn push_background_image(batch: &mut QuadBatch, rect: Rect, opacity: f32) {
    if rect.w <= 0.0 || rect.h <= 0.0 {
        return;
    }
    batch.push_image_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        [1.0, 1.0, 1.0, opacity.clamp(0.0, 1.0)],
    );
}

pub(crate) fn resolve_background_image_path(config: &WalkConfig) -> Option<std::path::PathBuf> {
    config.background_image.clone().or_else(|| {
        config.theme_path.as_ref().and_then(|path| {
            walk_ui::theme_loader::load_theme(path)
                .ok()
                .and_then(|theme| theme.background_image)
        })
    })
}

pub(crate) fn resolve_plugin_theme_path(name: &str) -> std::path::PathBuf {
    let candidate = std::path::PathBuf::from(name);
    if candidate.is_absolute()
        || candidate.extension().is_some()
        || candidate.components().count() > 1
    {
        return candidate;
    }

    WalkConfig::config_dir()
        .join("themes")
        .join(format!("{name}.toml"))
}

pub(crate) fn search_match_at_cell(
    search: &walk_ui::search::GlobalSearch,
    pane_id: PaneId,
    absolute_row: usize,
    column: u16,
) -> Option<bool> {
    if search.matches.is_empty() {
        return None;
    }

    for (index, search_match) in search.matches.iter().enumerate() {
        if search_match.is_command
            || search_match.pane_id != pane_id
            || search_match.row != absolute_row
        {
            continue;
        }
        if (search_match.col_start..search_match.col_end).contains(&column) {
            return Some(index == search.current);
        }
    }

    None
}

pub(crate) fn search_match_for_block_command(
    search: &walk_ui::search::GlobalSearch,
    pane_id: PaneId,
    block_id: u64,
) -> Option<bool> {
    if search.matches.is_empty() {
        return None;
    }

    search
        .matches
        .iter()
        .enumerate()
        .find(|(_, search_match)| {
            search_match.is_command
                && search_match.pane_id == pane_id
                && search_match.block_id == Some(block_id)
        })
        .map(|(index, _)| index == search.current)
}

pub(crate) fn block_query_match_at_cell(
    block_query: Option<&BlockQueryState>,
    blocks: &[Block],
    absolute_row: usize,
    column: u16,
) -> Option<bool> {
    let query = block_query?;
    let block = blocks
        .iter()
        .find(|block| block.id == query.target_block_id)?;
    if absolute_row < block.output_start_row || absolute_row > block.output_end_row {
        return None;
    }

    let line_index = absolute_row.saturating_sub(block.output_start_row);
    query
        .matches
        .iter()
        .enumerate()
        .find(|(_, search_match)| {
            search_match.line == line_index
                && (search_match.col_start as u16..search_match.col_end as u16).contains(&column)
        })
        .map(|(index, _)| index == query.current_match)
}

pub(crate) fn push_text(
    render: &mut RenderState,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    text: &str,
    color: [f32; 4],
) {
    let cell_width = font.metrics.cell_width;
    for (index, ch) in text.chars().enumerate() {
        push_glyph(render, font, x + index as f32 * cell_width, y, ch, color);
    }
}

pub(crate) fn push_glyph(
    render: &mut RenderState,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    character: char,
    color: [f32; 4],
) {
    let (pipeline, gpu, atlas, batch) = (
        &mut render.pipeline,
        &render.gpu,
        &mut render.atlas,
        &mut render.batch,
    );
    push_glyph_impl(pipeline, gpu, atlas, batch, font, x, y, character, color);
}

pub(crate) fn push_glyph_to_batch(
    render: &mut RenderState,
    batch: &mut QuadBatch,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    character: char,
    color: [f32; 4],
) {
    let (pipeline, gpu, atlas) = (&mut render.pipeline, &render.gpu, &mut render.atlas);
    push_glyph_impl(pipeline, gpu, atlas, batch, font, x, y, character, color);
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn push_glyph_impl(
    pipeline: &mut TerminalRenderPipeline,
    gpu: &GpuContext,
    atlas: &mut GlyphAtlas,
    batch: &mut QuadBatch,
    font: &mut FontSystem,
    x: f32,
    y: f32,
    character: char,
    color: [f32; 4],
) {
    if character == ' ' || character == '\0' {
        return;
    }

    let glyph_key = walk_renderer::atlas::GlyphKey {
        font_id: 0,
        glyph_id: character as u32,
        font_size_tenths: (font.font_size * 10.0) as u32,
    };

    if let Some(glyph) = font.rasterize(character) {
        let width = glyph.width;
        let height = glyph.height;
        let data = glyph.data.clone();
        let offset_x = glyph.offset_x;
        let offset_y = glyph.offset_y;
        if let Some(region) = atlas.get_or_insert(glyph_key, width, height) {
            if width > 0 && height > 0 {
                pipeline.upload_glyph(gpu, region.x, region.y, width, height, &data);
            }
            batch.push_glyph_quad(
                x + offset_x as f32,
                y + (font.metrics.baseline - offset_y as f32),
                width as f32,
                height as f32,
                &region,
                color,
            );
        }
    }
}

pub(crate) fn collect_search_lines(
    terminal: &Terminal,
    blocks: &[Block],
    pane_id: PaneId,
    tab_id: u64,
) -> Vec<SearchLine> {
    let mut lines: Vec<SearchLine> = terminal
        .state
        .text_rows()
        .into_iter()
        .map(|row| SearchLine {
            pane_id,
            tab_id,
            row: row.absolute_row,
            block_id: None,
            is_command: false,
            text: row.text,
        })
        .collect();

    for block in blocks {
        if block.command_text.is_empty() {
            continue;
        }
        lines.push(SearchLine {
            pane_id,
            tab_id,
            row: block.output_start_row,
            block_id: Some(block.id),
            is_command: true,
            text: block.command_text.clone(),
        });
    }

    lines
}

pub(crate) fn quick_select_rows_for_scope(
    pane: &PaneRuntime,
    scope: QuickSelectScope,
) -> Vec<(usize, String)> {
    match scope {
        QuickSelectScope::Viewport => pane
            .terminal
            .state
            .visible_rows()
            .into_iter()
            .map(|absolute_row| (absolute_row, pane.terminal.state.row_text(absolute_row)))
            .collect(),
        QuickSelectScope::SelectedBlock => pane
            .app
            .selected_or_latest_block()
            .map(|block| {
                (block.output_start_row..=block.output_end_row)
                    .map(|absolute_row| (absolute_row, pane.terminal.state.row_text(absolute_row)))
                    .collect()
            })
            .unwrap_or_default(),
    }
}

pub(crate) fn extract_selection_text(terminal: &Terminal, start: CellPos, end: CellPos) -> String {
    let total_rows = terminal.state.screen_lines();
    if total_rows == 0 {
        return String::new();
    }

    let max_row = total_rows.saturating_sub(1);
    let start_row = usize::from(start.row).min(max_row);
    let end_row = usize::from(end.row).min(max_row);
    let mut lines = Vec::new();

    for row in start_row..=end_row {
        let absolute_row = terminal.state.viewport_row_to_absolute(row);
        let row_start = if row == start_row {
            usize::from(start.col)
        } else {
            0
        };
        let row_end = if row == end_row {
            selection_end_col(terminal, end.col)
        } else {
            terminal.state.columns()
        };
        lines.push(terminal.state.row_slice(absolute_row, row_start, row_end));
    }

    lines.join("\n")
}

pub(crate) fn extract_absolute_selection_text(
    terminal: &Terminal,
    start: (usize, usize),
    end: (usize, usize),
) -> String {
    let total_rows = terminal.state.total_rows();
    if total_rows == 0 {
        return String::new();
    }

    let (start, end) = if start <= end {
        (start, end)
    } else {
        (end, start)
    };
    let start_row = start.0.min(total_rows.saturating_sub(1));
    let end_row = end.0.min(total_rows.saturating_sub(1));
    let mut lines = Vec::new();

    for row in start_row..=end_row {
        let row_text = terminal.state.row_text(row);
        let row_chars = row_text.chars().collect::<Vec<_>>();
        let row_start = if row == start_row {
            start.1.min(row_chars.len())
        } else {
            0
        };
        let row_end = if row == end_row {
            (end.1 + 1).min(row_chars.len())
        } else {
            row_chars.len()
        };
        lines.push(
            row_chars[row_start..row_end]
                .iter()
                .collect::<String>()
                .trim_end()
                .to_string(),
        );
    }

    lines.join("\n")
}

pub(crate) fn extract_block_text(terminal: &Terminal, block: &Block) -> String {
    let mut lines = Vec::new();

    if !block.command_text.is_empty() {
        lines.push(block.command_text.clone());
    }
    lines.extend(collect_block_output_lines(terminal, block));

    lines.join("\n")
}

pub(crate) fn extract_block_command_text(block: &Block) -> String {
    block.command_text.clone()
}

pub(crate) fn extract_block_output_text(terminal: &Terminal, block: &Block) -> String {
    collect_block_output_lines(terminal, block).join("\n")
}

pub(crate) fn collect_block_output_lines(terminal: &Terminal, block: &Block) -> Vec<String> {
    let total_rows = terminal.state.total_rows();
    if total_rows == 0 {
        return Vec::new();
    }

    let max_row = total_rows.saturating_sub(1);
    let start_row = block.output_start_row.min(max_row);
    let end_row = block.output_end_row.min(max_row);
    let mut lines = Vec::new();

    for row in start_row..=end_row {
        lines.push(terminal.state.row_text(row));
    }

    lines
}

pub(crate) fn build_visible_row_positions(visible_rows: &[usize], blocks: &[Block]) -> Vec<Option<usize>> {
    let mut hidden_rows = vec![false; visible_rows.len()];

    for block in blocks {
        if !block.is_collapsed {
            continue;
        }

        for (index, absolute_row) in visible_rows.iter().copied().enumerate() {
            if absolute_row > block.output_start_row && absolute_row <= block.output_end_row {
                hidden_rows[index] = true;
            }
        }
    }

    let mut next_visible_row = 0;
    hidden_rows
        .into_iter()
        .map(|hidden| {
            if hidden {
                None
            } else {
                let visible_row = Some(next_visible_row);
                next_visible_row += 1;
                visible_row
            }
        })
        .collect()
}

pub(crate) fn pane_overlay_signature(
    blocks: &[Block],
    selected_block_id: Option<u64>,
    global_search: &walk_ui::search::GlobalSearch,
    block_query: Option<&BlockQueryState>,
    pane_id: PaneId,
) -> PaneOverlaySignature {
    PaneOverlaySignature {
        selected_block_id,
        blocks: blocks
            .iter()
            .map(|block| {
                (
                    block.id,
                    block.output_start_row,
                    block.output_end_row,
                    block.exit_code,
                    block.is_collapsed,
                    block.is_bookmarked,
                )
            })
            .collect(),
        search_query: global_search.query.clone(),
        search_current: global_search.current,
        search_matches: global_search
            .matches
            .iter()
            .filter(|search_match| search_match.pane_id == pane_id)
            .map(|search_match| {
                (
                    search_match.row,
                    search_match.col_start,
                    search_match.col_end,
                    search_match.block_id,
                    search_match.is_command,
                )
            })
            .collect(),
        block_query: block_query.map(|query| BlockQueryOverlaySignature {
            mode: query.mode,
            target_block_id: query.target_block_id,
            query: query.query.clone(),
            current_match: query.current_match,
            overlay_scroll_offset: query.overlay_scroll_offset,
            matches: query
                .matches
                .iter()
                .map(|search_match| {
                    (
                        search_match.line,
                        search_match.col_start,
                        search_match.col_end,
                    )
                })
                .collect(),
        }),
    }
}

#[derive(Debug, Clone)]
pub(crate) struct RowLinkSpan {
    pub(crate) col_start: usize,
    pub(crate) col_end: usize,
    pub(crate) uri: String,
}

pub(crate) fn collect_row_links(terminal: &Terminal, absolute_row: usize) -> Vec<RowLinkSpan> {
    let mut links = terminal
        .state
        .explicit_links_on_row(absolute_row)
        .into_iter()
        .map(|span| RowLinkSpan {
            col_start: span.col_start,
            col_end: span.col_end,
            uri: span.link.uri.clone(),
        })
        .collect::<Vec<_>>();

    let text = terminal.state.row_text(absolute_row);
    for detected in detect_links(absolute_row, &text) {
        let overlaps_explicit = links.iter().any(|span| {
            spans_overlap(
                span.col_start,
                span.col_end,
                detected.range.col_start,
                detected.range.col_end,
            )
        });
        if overlaps_explicit {
            continue;
        }
        links.push(RowLinkSpan {
            col_start: detected.range.col_start,
            col_end: detected.range.col_end,
            uri: detected.uri,
        });
    }

    links.sort_by_key(|span| span.col_start);
    links
}

pub(crate) fn link_at_cell(terminal: &Terminal, absolute_row: usize, col: usize) -> Option<String> {
    if let Some(explicit) = terminal.state.explicit_link_at(absolute_row, col) {
        return Some(explicit.uri.clone());
    }

    collect_row_links(terminal, absolute_row)
        .into_iter()
        .find(|span| (span.col_start..span.col_end).contains(&col))
        .map(|span| span.uri)
}

pub(crate) fn spans_overlap(start_a: usize, end_a: usize, start_b: usize, end_b: usize) -> bool {
    start_a < end_b && start_b < end_a
}

pub(crate) fn collect_row_cells(
    terminal: &Terminal,
    absolute_row: usize,
    total_cols: usize,
) -> Vec<CellRenderData> {
    (0..total_cols)
        .map(|col_idx| terminal.state.cell_at_absolute(absolute_row, col_idx))
        .collect()
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn rebuild_visible_row_batch(
    batch: &mut QuadBatch,
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    blocks: &[Block],
    selected_block_id: Option<u64>,
    global_search: &walk_ui::search::GlobalSearch,
    block_query: Option<&BlockQueryState>,
    pane_id: PaneId,
    terminal: &Terminal,
    inline_images: &InlineImageStore,
    absolute_row: usize,
    render_row: Option<usize>,
    total_cols: usize,
    viewport: Rect,
    cell_width: f32,
    cell_height: f32,
    terminal_surface_alpha: f32,
) {
    batch.clear();
    let Some(render_row) = render_row else {
        return;
    };

    let row_y = viewport.y + render_row as f32 * cell_height;
    let row_links = collect_row_links(terminal, absolute_row);
    for col_idx in 0..total_cols {
        let cell = terminal.state.cell_at_absolute(absolute_row, col_idx);
        let x = viewport.x + col_idx as f32 * cell_width;
        let mut bg = resolve_cell_color(&cell.bg, theme, true);
        let mut fg = resolve_cell_color(&cell.fg, theme, false);
        let inline_color = inline_images.sample_cell_color(absolute_row, col_idx);
        let is_hyperlink_cell = row_links
            .iter()
            .any(|link| (link.col_start..link.col_end).contains(&col_idx));

        if cell.is_inverse {
            std::mem::swap(&mut bg, &mut fg);
        }
        if matches!(cell.bg, CellColor::Named(idx) if idx >= 16) {
            bg[3] *= terminal_surface_alpha;
        }
        if let Some(color) = inline_color {
            bg = color;
        }
        if is_hyperlink_cell {
            fg = [
                theme.hyperlink_color.r,
                theme.hyperlink_color.g,
                theme.hyperlink_color.b,
                theme.hyperlink_color.a,
            ];
        }

        batch.push_bg_quad(x, row_y, cell_width, cell_height, bg);
        if let Some(current_match) =
            search_match_at_cell(global_search, pane_id, absolute_row, col_idx as u16)
        {
            let highlight = if current_match {
                theme.highlight_current_match
            } else {
                theme.highlight_match
            };
            batch.push_bg_quad(
                x,
                row_y,
                cell_width,
                cell_height,
                [highlight.r, highlight.g, highlight.b, highlight.a],
            );
        }
        if let Some(current_match) =
            block_query_match_at_cell(block_query, blocks, absolute_row, col_idx as u16)
        {
            let highlight = if current_match {
                theme.highlight_current_match
            } else {
                theme.highlight_match
            };
            batch.push_bg_quad(
                x,
                row_y,
                cell_width,
                cell_height,
                [highlight.r, highlight.g, highlight.b, highlight.a * 0.9],
            );
        }
        if let Some(trigger_color) = trigger_highlight_color_at_cell(blocks, absolute_row, col_idx)
        {
            batch.push_bg_quad(
                x,
                row_y,
                cell_width,
                cell_height,
                [trigger_color[0], trigger_color[1], trigger_color[2], 0.36],
            );
        }

        if inline_color.is_none() && cell.character != ' ' && cell.character != '\0' {
            push_glyph_to_batch(render, batch, font, x, row_y, cell.character, fg);
        }
        if is_hyperlink_cell {
            batch.push_bg_quad(
                x,
                row_y + cell_height - 1.5,
                cell_width,
                1.0,
                [
                    theme.hyperlink_color.r,
                    theme.hyperlink_color.g,
                    theme.hyperlink_color.b,
                    0.9,
                ],
            );
        }
    }

    if let Some(block) = blocks.iter().find(|block| {
        absolute_row >= block.output_start_row && absolute_row <= block.output_end_row
    }) {
        let accent = if block.exit_code.unwrap_or(0) == 0 {
            theme.block_success_accent
        } else {
            theme.block_error_accent
        };

        if absolute_row == block.output_start_row {
            batch.push_bg_quad(
                viewport.x,
                row_y,
                viewport.w,
                1.0,
                [
                    theme.block_separator.r,
                    theme.block_separator.g,
                    theme.block_separator.b,
                    0.65,
                ],
            );
        }

        batch.push_bg_quad(
            viewport.x,
            row_y,
            4.0,
            cell_height,
            [accent.r, accent.g, accent.b, 0.9],
        );

        if block.is_bookmarked {
            batch.push_bg_quad(
                viewport.x + 4.0,
                row_y,
                3.0,
                cell_height,
                [
                    theme.highlight_current_match.r,
                    theme.highlight_current_match.g,
                    theme.highlight_current_match.b,
                    0.9,
                ],
            );
        }

        if selected_block_id == Some(block.id) {
            batch.push_bg_quad(
                viewport.x,
                row_y,
                viewport.w,
                cell_height,
                [
                    theme.selection.r,
                    theme.selection.g,
                    theme.selection.b,
                    0.12,
                ],
            );
        }

        if absolute_row == block.output_start_row {
            if let Some(current_match) =
                search_match_for_block_command(global_search, pane_id, block.id)
            {
                let highlight = if current_match {
                    theme.highlight_current_match
                } else {
                    theme.highlight_match
                };
                batch.push_bg_quad(
                    viewport.x + 4.0,
                    row_y,
                    viewport.w - 4.0,
                    cell_height,
                    [highlight.r, highlight.g, highlight.b, highlight.a],
                );
            }

            if block.is_collapsed {
                batch.push_bg_quad(
                    viewport.x + 4.0,
                    row_y,
                    viewport.w - 4.0,
                    cell_height,
                    [
                        theme.block_separator.r,
                        theme.block_separator.g,
                        theme.block_separator.b,
                        0.25,
                    ],
                );
            }
        }
    }
}

pub(crate) fn selection_end_col(terminal: &Terminal, end_col: u16) -> usize {
    if end_col == u16::MAX {
        terminal.state.columns()
    } else {
        (usize::from(end_col) + 1).min(terminal.state.columns())
    }
}

/// Resolve a CellColor to [r, g, b, a] using the Walk theme.
pub(crate) fn resolve_cell_color(color: &CellColor, theme: &Theme, is_bg: bool) -> [f32; 4] {
    match color {
        CellColor::Named(idx) => {
            let i = *idx as usize;
            if i < 16 {
                let c = &theme.ansi_colors[i];
                [c.r, c.g, c.b, c.a]
            } else if is_bg {
                [
                    theme.background.r,
                    theme.background.g,
                    theme.background.b,
                    theme.background.a,
                ]
            } else {
                [
                    theme.foreground.r,
                    theme.foreground.g,
                    theme.foreground.b,
                    theme.foreground.a,
                ]
            }
        }
        CellColor::Rgb(r, g, b) => [
            f32::from(*r) / 255.0,
            f32::from(*g) / 255.0,
            f32::from(*b) / 255.0,
            1.0,
        ],
        CellColor::Indexed(idx) => {
            let i = *idx as usize;
            if i < 16 {
                let c = &theme.ansi_colors[i];
                [c.r, c.g, c.b, c.a]
            } else if i < 232 {
                let i = i - 16;
                let r = (i / 36) as f32 / 5.0;
                let g = ((i / 6) % 6) as f32 / 5.0;
                let b = (i % 6) as f32 / 5.0;
                [r, g, b, 1.0]
            } else {
                let gray = (i - 232) as f32 / 23.0;
                [gray, gray, gray, 1.0]
            }
        }
    }
}
