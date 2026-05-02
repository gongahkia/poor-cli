use super::*;
use std::path::Path;

#[allow(clippy::too_many_arguments)]
pub(crate) fn compute_chrome_rects(
    size: PhysicalSize<u32>,
    tab_bar_visible: bool,
    tab_bar_side: wok_app::config::ChromeSide,
    status_bar_visible: bool,
    status_bar_side: wok_app::config::ChromeSide,
    cell_height: f32,
    tab_bar_size: Option<f32>,
    status_bar_size: Option<f32>,
) -> ChromeRects {
    let width = size.width as f32;
    let height = size.height as f32;
    let chrome_height = chrome_bar_height(cell_height);
    let tab_thickness = tab_bar_size
        .unwrap_or_else(|| {
            if tab_bar_side.is_horizontal() {
                chrome_height
            } else {
                180.0
            }
        })
        .max(1.0);
    let status_thickness = status_bar_size.unwrap_or(chrome_height).max(1.0);
    let mut remaining = Rect::new(0.0, 0.0, width, height);

    let tab_bar = if tab_bar_visible {
        allocate_chrome_side(&mut remaining, tab_bar_side, tab_thickness)
    } else {
        Rect::new(0.0, 0.0, 0.0, 0.0)
    };

    let status = if status_bar_visible {
        allocate_chrome_side(&mut remaining, status_bar_side, status_thickness)
    } else {
        Rect::new(0.0, 0.0, 0.0, 0.0)
    };

    ChromeRects {
        tab_bar,
        content: remaining,
        status,
    }
}

pub(crate) fn chrome_bar_height(cell_height: f32) -> f32 {
    (cell_height + 10.0).ceil().max(32.0)
}

fn allocate_chrome_side(
    remaining: &mut Rect,
    side: wok_app::config::ChromeSide,
    thickness: f32,
) -> Rect {
    match side {
        wok_app::config::ChromeSide::Top => {
            let height = thickness.min(remaining.h).max(0.0);
            let rect = Rect::new(remaining.x, remaining.y, remaining.w, height);
            remaining.y += height;
            remaining.h = (remaining.h - height).max(0.0);
            rect
        }
        wok_app::config::ChromeSide::Bottom => {
            let height = thickness.min(remaining.h).max(0.0);
            remaining.h = (remaining.h - height).max(0.0);
            Rect::new(remaining.x, remaining.y + remaining.h, remaining.w, height)
        }
        wok_app::config::ChromeSide::Left => {
            let width = thickness.min(remaining.w).max(0.0);
            let rect = Rect::new(remaining.x, remaining.y, width, remaining.h);
            remaining.x += width;
            remaining.w = (remaining.w - width).max(0.0);
            rect
        }
        wok_app::config::ChromeSide::Right => {
            let width = thickness.min(remaining.w).max(0.0);
            remaining.w = (remaining.w - width).max(0.0);
            Rect::new(remaining.x + remaining.w, remaining.y, width, remaining.h)
        }
    }
}

pub(crate) fn compute_pane_ui_rects(
    container: Rect,
    input_position: wok_input::editor::InputPosition,
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
        wok_input::editor::InputPosition::Top => UiRects {
            viewport: Rect::new(
                container.x,
                container.y + input_height,
                container.w,
                (container.h - input_height).max(cell_height),
            ),
            input: Rect::new(container.x, container.y, container.w, input_height),
        },
        wok_input::editor::InputPosition::Bottom => UiRects {
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
    scroll_offset: f32,
    orientation: wok_app::config::TabBarOrientation,
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

    match orientation {
        wok_app::config::TabBarOrientation::Horizontal => {
            let widths = tab_bar_tab_widths(tabs, font.metrics.cell_width);
            let mut x = rect.x - scroll_offset;
            for ((is_active, label), tab_width) in tabs.iter().zip(widths) {
                render_tab_bar_item(
                    render,
                    font,
                    Rect::new(x, rect.y, tab_width, rect.h),
                    Rect::new(rect.x, rect.y, rect.w, rect.h),
                    *is_active,
                    label,
                    surface_opacity,
                );
                x += tab_width;
            }
        }
        wok_app::config::TabBarOrientation::Vertical => {
            let tab_height = 32.0;
            let mut y = rect.y - scroll_offset;
            for (is_active, label) in tabs {
                render_tab_bar_item(
                    render,
                    font,
                    Rect::new(rect.x, y, rect.w, tab_height),
                    Rect::new(rect.x, rect.y, rect.w, rect.h),
                    *is_active,
                    label,
                    surface_opacity,
                );
                y += tab_height;
            }
        }
    }
}

fn render_tab_bar_item(
    render: &mut RenderState,
    font: &mut FontSystem,
    item_rect: Rect,
    clip_rect: Rect,
    is_active: bool,
    label: &str,
    surface_opacity: f32,
) {
    let visible_left = item_rect.x.max(clip_rect.x);
    let visible_top = item_rect.y.max(clip_rect.y);
    let visible_right = (item_rect.x + item_rect.w).min(clip_rect.x + clip_rect.w);
    let visible_bottom = (item_rect.y + item_rect.h).min(clip_rect.y + clip_rect.h);
    if visible_right <= visible_left || visible_bottom <= visible_top {
        return;
    }

    let background = if is_active {
        [0.14, 0.16, 0.22, 1.0]
    } else {
        [0.10, 0.11, 0.15, 1.0]
    };
    render.batch.push_bg_quad(
        visible_left,
        visible_top,
        visible_right - visible_left,
        visible_bottom - visible_top,
        with_opacity(background, surface_opacity),
    );

    let text_x = (item_rect.x + TAB_TEXT_PAD_X).max(clip_rect.x + TAB_TEXT_PAD_X);
    let text_y =
        visible_top + ((visible_bottom - visible_top - font.metrics.cell_height) * 0.5).max(0.0);
    let available_width = (visible_right - text_x - TAB_TEXT_PAD_X).max(0.0);
    let visible_label = fit_text_to_width(label, available_width, font.metrics.cell_width);
    if visible_label.is_empty() {
        return;
    }
    push_text(
        render,
        font,
        text_x,
        text_y,
        &visible_label,
        with_opacity([0.75, 0.79, 0.96, 1.0], surface_opacity),
    );
}

const TAB_TEXT_PAD_X: f32 = 12.0;
const TAB_MIN_WIDTH: f32 = 96.0;
const TAB_MAX_WIDTH: f32 = 420.0;
const VERTICAL_TAB_HEIGHT: f32 = 32.0;

pub(crate) fn tab_bar_tab_widths(tabs: &[(bool, String)], cell_width: f32) -> Vec<f32> {
    tabs.iter()
        .map(|(_, label)| tab_bar_tab_width_for_label(label, cell_width))
        .collect()
}

pub(crate) fn tab_bar_tab_width_for_label(label: &str, cell_width: f32) -> f32 {
    let text_width = label.chars().count() as f32 * cell_width;
    (text_width + TAB_TEXT_PAD_X * 2.0).clamp(TAB_MIN_WIDTH, TAB_MAX_WIDTH)
}

pub(crate) fn tab_bar_content_extent(
    tabs: &[(bool, String)],
    cell_width: f32,
    orientation: wok_app::config::TabBarOrientation,
) -> f32 {
    match orientation {
        wok_app::config::TabBarOrientation::Horizontal => {
            tab_bar_tab_widths(tabs, cell_width).into_iter().sum()
        }
        wok_app::config::TabBarOrientation::Vertical => tabs.len() as f32 * VERTICAL_TAB_HEIGHT,
    }
}

pub(crate) fn tab_bar_max_scroll(
    rect: Rect,
    tabs: &[(bool, String)],
    cell_width: f32,
    orientation: wok_app::config::TabBarOrientation,
) -> f32 {
    let viewport_extent = match orientation {
        wok_app::config::TabBarOrientation::Horizontal => rect.w,
        wok_app::config::TabBarOrientation::Vertical => rect.h,
    };
    (tab_bar_content_extent(tabs, cell_width, orientation) - viewport_extent).max(0.0)
}

pub(crate) fn tab_bar_tab_range(
    tabs: &[(bool, String)],
    index: usize,
    cell_width: f32,
    orientation: wok_app::config::TabBarOrientation,
) -> Option<(f32, f32)> {
    if index >= tabs.len() {
        return None;
    }
    match orientation {
        wok_app::config::TabBarOrientation::Horizontal => {
            let widths = tab_bar_tab_widths(tabs, cell_width);
            let start = widths.iter().take(index).sum::<f32>();
            Some((start, start + widths[index]))
        }
        wok_app::config::TabBarOrientation::Vertical => {
            let start = index as f32 * VERTICAL_TAB_HEIGHT;
            Some((start, start + VERTICAL_TAB_HEIGHT))
        }
    }
}

pub(crate) fn tab_bar_index_at_point(
    rect: Rect,
    tabs: &[(bool, String)],
    scroll_offset: f32,
    x: f32,
    y: f32,
    cell_width: f32,
    orientation: wok_app::config::TabBarOrientation,
) -> Option<usize> {
    if tabs.is_empty() {
        return None;
    }
    match orientation {
        wok_app::config::TabBarOrientation::Horizontal => {
            let target = x - rect.x + scroll_offset;
            let mut cursor = 0.0;
            for (index, width) in tab_bar_tab_widths(tabs, cell_width).into_iter().enumerate() {
                if target >= cursor && target < cursor + width {
                    return Some(index);
                }
                cursor += width;
            }
        }
        wok_app::config::TabBarOrientation::Vertical => {
            let target = y - rect.y + scroll_offset;
            let index = (target / VERTICAL_TAB_HEIGHT).floor() as usize;
            if index < tabs.len() {
                return Some(index);
            }
        }
    }
    None
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

    if rect.h > rect.w {
        render_vertical_status_bar(render, font, rect, status_segments, surface_opacity);
        return;
    }

    let text_y = rect.y + ((rect.h - font.metrics.cell_height) * 0.5).max(0.0);
    let mut left_x = rect.x + 8.0;
    draw_status_segments(
        render,
        font,
        &status_segments.left,
        &mut left_x,
        text_y,
        false,
        surface_opacity,
    );

    let mut right_x = rect.x + rect.w - 8.0;
    draw_status_segments(
        render,
        font,
        &status_segments.right,
        &mut right_x,
        text_y,
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
        text_y,
        false,
        surface_opacity,
    );
}

fn render_vertical_status_bar(
    render: &mut RenderState,
    font: &mut FontSystem,
    rect: Rect,
    status_segments: &StatusBarSegments,
    surface_opacity: f32,
) {
    let mut y = rect.y + 8.0;
    let max_width = (rect.w - 12.0).max(font.metrics.cell_width);
    for segment in status_segments
        .left
        .iter()
        .chain(status_segments.center.iter())
        .chain(status_segments.right.iter())
    {
        if y + font.metrics.cell_height > rect.y + rect.h - 4.0 {
            break;
        }
        if let Some(bg) = segment.bg.as_deref().and_then(parse_hex_rgba) {
            render.batch.push_bg_quad(
                rect.x + 4.0,
                y - 1.0,
                rect.w - 8.0,
                font.metrics.cell_height + 2.0,
                with_opacity(bg, surface_opacity),
            );
        }
        let color = segment
            .fg
            .as_deref()
            .and_then(parse_hex_rgba)
            .unwrap_or([0.54, 0.58, 0.65, 1.0]);
        let text = fit_text_to_width(&segment.text, max_width, font.metrics.cell_width);
        push_text(
            render,
            font,
            rect.x + 6.0,
            y,
            &text,
            with_opacity(color, surface_opacity),
        );
        y += font.metrics.cell_height + 4.0;
    }
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

    let longest = lines
        .iter()
        .map(|line| line.chars().count())
        .max()
        .unwrap_or(0);
    let width = (longest as f32 * font.metrics.cell_width + 20.0)
        .clamp(260.0, 620.0)
        .min(content_rect.w.max(1.0));
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
        let visible_line = fit_text_to_width(line, width - 20.0, font.metrics.cell_width);
        push_text(
            render,
            font,
            x + 10.0,
            y + 6.0 + index as f32 * font.metrics.cell_height,
            &visible_line,
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
    input: &wok_input::editor::InputRenderData,
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
        let popup_y = if matches!(input.position, wok_input::editor::InputPosition::Bottom) {
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

pub(crate) fn completion_kind_token(kind: &wok_input::completion::CompletionKind) -> &'static str {
    match kind {
        wok_input::completion::CompletionKind::Command => "[cmd]",
        wok_input::completion::CompletionKind::FilePath => "[path]",
        wok_input::completion::CompletionKind::EnvVar => "[env]",
        wok_input::completion::CompletionKind::Argument => "[arg]",
    }
}

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_command_palette(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    input: &wok_input::editor::InputRenderData,
    palette: &CommandPaletteState,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    let panel_width = (viewport.w * 0.92)
        .clamp(420.0, 1180.0)
        .min((viewport.w - 24.0).max(240.0));
    let panel_height = (viewport.h * 0.78)
        .clamp(240.0, 640.0)
        .min((viewport.h - 24.0).max(180.0));
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
    let inner_width = (rect.w - padding_x * 2.0).max(font.metrics.cell_width);
    let input_line = input.lines.first().cloned().unwrap_or_default();
    let prefix = "Command Palette: ";
    let help_text = fit_text_to_width(
        "Run an action, workflow, alias, or recent command",
        inner_width,
        font.metrics.cell_width,
    );
    push_text(
        render,
        font,
        base_x,
        base_y,
        &help_text,
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
    let input_text = fit_text_to_width(
        &format!("{prefix}{input_line}"),
        inner_width,
        font.metrics.cell_width,
    );
    push_text(
        render,
        font,
        base_x,
        base_y + font.metrics.cell_height + 2.0,
        &input_text,
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

    let row_height = font.metrics.cell_height + 4.0;
    let list_top = base_y + font.metrics.cell_height * 2.0 + 8.0;
    let list_bottom = rect.y + rect.h - font.metrics.cell_height - 18.0;
    let entries_max = ((list_bottom - list_top) / row_height)
        .floor()
        .clamp(4.0, 15.0) as usize;
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
    let mut row_y = list_top;

    if available_entries.is_empty() {
        let empty_text = fit_text_to_width(
            "No matching entries. Press Enter to run raw command input.",
            inner_width,
            font.metrics.cell_width,
        );
        push_text(
            render,
            font,
            base_x,
            row_y,
            &empty_text,
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
                if row_y + font.metrics.cell_height > list_bottom {
                    break;
                }
                let category = fit_text_to_width(
                    palette_category_label(entry.category),
                    inner_width,
                    font.metrics.cell_width,
                );
                push_text(
                    render,
                    font,
                    base_x,
                    row_y,
                    &category,
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
            if row_y + font.metrics.cell_height > list_bottom {
                break;
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
            let label_width = (inner_width * 0.34).clamp(160.0, 320.0);
            let gap = 16.0;
            let description_x = base_x + label_width + gap;
            let description_width = (rect.x + rect.w - padding_x - description_x).max(0.0);
            let visible_label =
                fit_text_to_width(&entry.label, label_width, font.metrics.cell_width);
            let visible_label_cols = visible_label.chars().count();
            for column in palette_highlight_columns(&entry.label, query) {
                if column >= visible_label_cols {
                    continue;
                }
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
                &visible_label,
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
            let visible_description = fit_text_to_width(
                &entry.description,
                description_width,
                font.metrics.cell_width,
            );
            push_text(
                render,
                font,
                description_x,
                row_y,
                &visible_description,
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
            let indicator = fit_text_to_width(
                &format!(
                    "{}-{} of {}",
                    start_idx + 1,
                    end_idx,
                    available_entries.len()
                ),
                inner_width,
                font.metrics.cell_width,
            );
            let indicator_x = right_aligned_text_x(
                rect.x + rect.w - padding_x,
                &indicator,
                font.metrics.cell_width,
            )
            .max(base_x);
            push_text(
                render,
                font,
                indicator_x,
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
            let input_cols = columns_for_width(inner_width, font.metrics.cell_width);
            let max_cursor_col = input_cols
                .saturating_sub(prefix.chars().count() + 1)
                .min(cursor_col);
            let cursor_x = base_x
                + prefix.chars().count() as f32 * font.metrics.cell_width
                + max_cursor_col as f32 * font.metrics.cell_width;
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

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_settings_editor(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    path: &Path,
    input: &wok_input::editor::InputRenderData,
    cursor_shape: CursorShape,
    cursor_visible: bool,
    surface_opacity: f32,
) {
    let panel_width = (viewport.w * 0.9)
        .clamp(520.0, 1100.0)
        .min((viewport.w - 24.0).max(260.0));
    let panel_height = (viewport.h * 0.86)
        .clamp(320.0, 760.0)
        .min((viewport.h - 24.0).max(220.0));
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
        with_opacity([0.0, 0.0, 0.0, 0.36], surface_opacity),
    );
    render.batch.push_bg_quad(
        rect.x,
        rect.y,
        rect.w,
        rect.h,
        with_opacity(
            [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, 0.99],
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
                0.95,
            ],
            surface_opacity,
        ),
    );

    let padding_x = 16.0;
    let padding_y = 12.0;
    let base_x = rect.x + padding_x;
    let base_y = rect.y + padding_y;
    let inner_width = (rect.w - padding_x * 2.0).max(font.metrics.cell_width);
    let path_text = fit_text_to_width(
        &path.display().to_string(),
        inner_width,
        font.metrics.cell_width,
    );
    let help_text = fit_text_to_width(
        "Esc close  Mod+S save  Enter newline",
        inner_width,
        font.metrics.cell_width,
    );

    push_text(
        render,
        font,
        base_x,
        base_y,
        "Settings",
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
        base_x,
        base_y + font.metrics.cell_height,
        &path_text,
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
        base_y + font.metrics.cell_height * 2.0,
        &help_text,
        with_opacity(
            [
                theme.status_bar_text.r,
                theme.status_bar_text.g,
                theme.status_bar_text.b,
                0.82,
            ],
            surface_opacity,
        ),
    );

    let editor_top = base_y + font.metrics.cell_height * 3.0 + 12.0;
    let editor_bottom = rect.y + rect.h - 14.0;
    let editor_height = (editor_bottom - editor_top).max(font.metrics.cell_height);
    let editor_rect = Rect::new(base_x, editor_top, inner_width, editor_height);
    render.batch.push_bg_quad(
        editor_rect.x,
        editor_rect.y,
        editor_rect.w,
        editor_rect.h,
        with_opacity([0.03, 0.035, 0.05, 0.48], surface_opacity),
    );
    render.batch.push_bg_quad(
        editor_rect.x,
        editor_rect.y,
        editor_rect.w,
        1.0,
        with_opacity(
            [
                theme.block_separator.r,
                theme.block_separator.g,
                theme.block_separator.b,
                0.8,
            ],
            surface_opacity,
        ),
    );

    let line_count = input.lines.len().max(1);
    let max_visible_lines = (editor_rect.h / font.metrics.cell_height).floor().max(1.0) as usize;
    let (cursor_row, cursor_col) = input.cursors.first().copied().unwrap_or_default();
    let mut start = cursor_row.saturating_sub(max_visible_lines / 2);
    if start + max_visible_lines > line_count {
        start = line_count.saturating_sub(max_visible_lines);
    }
    let end = (start + max_visible_lines).min(line_count);
    let gutter_width = 5.0 * font.metrics.cell_width;
    let text_x = editor_rect.x + gutter_width + 8.0;
    let text_width = (editor_rect.x + editor_rect.w - text_x - 8.0).max(0.0);
    let line_number_width = (gutter_width - 8.0).max(font.metrics.cell_width);

    for visible_row in 0..end.saturating_sub(start) {
        let absolute_row = start + visible_row;
        let line = input
            .lines
            .get(absolute_row)
            .map_or("", std::string::String::as_str);
        let row_y = editor_rect.y + visible_row as f32 * font.metrics.cell_height;
        if absolute_row == cursor_row {
            render.batch.push_bg_quad(
                editor_rect.x + 4.0,
                row_y,
                editor_rect.w - 8.0,
                font.metrics.cell_height,
                with_opacity(
                    [
                        theme.selection.r,
                        theme.selection.g,
                        theme.selection.b,
                        0.14,
                    ],
                    surface_opacity,
                ),
            );
        }

        let line_number = fit_text_to_width(
            &format!("{:>4}", absolute_row + 1),
            line_number_width,
            font.metrics.cell_width,
        );
        let line_number_x = right_aligned_text_x(
            editor_rect.x + line_number_width,
            &line_number,
            font.metrics.cell_width,
        );
        push_text(
            render,
            font,
            line_number_x,
            row_y,
            &line_number,
            with_opacity(
                [
                    theme.status_bar_text.r,
                    theme.status_bar_text.g,
                    theme.status_bar_text.b,
                    0.58,
                ],
                surface_opacity,
            ),
        );

        let visible_line = fit_text_to_width(line, text_width, font.metrics.cell_width);
        push_text(
            render,
            font,
            text_x,
            row_y,
            &visible_line,
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

    if cursor_visible && cursor_row >= start && cursor_row < end {
        let text_columns = columns_for_width(text_width, font.metrics.cell_width);
        let cursor_col = cursor_col.min(text_columns.saturating_sub(1));
        let cursor_x = text_x + cursor_col as f32 * font.metrics.cell_width;
        let cursor_y = editor_rect.y + (cursor_row - start) as f32 * font.metrics.cell_height;
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

#[allow(clippy::too_many_arguments)]
pub(crate) fn render_recent_keys_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    labels: &[String],
    position: wok_app::config::OverlayPosition,
    overlay_opacity: f32,
    surface_opacity: f32,
) {
    if labels.is_empty() || viewport.w <= 0.0 || viewport.h <= 0.0 {
        return;
    }
    let max_width = (viewport.w * 0.28).clamp(88.0, 260.0).min(viewport.w);
    let text_width = (max_width - 20.0).max(font.metrics.cell_width);
    let visible_labels = labels
        .iter()
        .map(|label| fit_text_to_width(label, text_width, font.metrics.cell_width))
        .filter(|label| !label.is_empty())
        .collect::<Vec<_>>();
    if visible_labels.is_empty() {
        return;
    }
    let longest_label = visible_labels
        .iter()
        .map(|label| label.chars().count())
        .max()
        .unwrap_or(0);
    let width = (longest_label as f32 * font.metrics.cell_width + 20.0)
        .min(max_width)
        .max(72.0);
    let row_height = font.metrics.cell_height + 4.0;
    let height = row_height * visible_labels.len() as f32 + 10.0;
    let margin = 12.0;
    let x = match position {
        wok_app::config::OverlayPosition::TopLeft
        | wok_app::config::OverlayPosition::BottomLeft => viewport.x + margin,
        wok_app::config::OverlayPosition::TopRight
        | wok_app::config::OverlayPosition::BottomRight => viewport.x + viewport.w - width - margin,
    }
    .clamp(
        viewport.x,
        (viewport.x + viewport.w - width).max(viewport.x),
    );
    let y = match position {
        wok_app::config::OverlayPosition::TopLeft | wok_app::config::OverlayPosition::TopRight => {
            viewport.y + margin
        }
        wok_app::config::OverlayPosition::BottomLeft
        | wok_app::config::OverlayPosition::BottomRight => {
            viewport.y + viewport.h - height - margin
        }
    }
    .clamp(
        viewport.y,
        (viewport.y + viewport.h - height).max(viewport.y),
    );
    let alpha = (overlay_opacity * surface_opacity).clamp(0.0, 1.0);

    render.batch.push_bg_quad(
        x,
        y,
        width,
        height,
        [theme.input_bg.r, theme.input_bg.g, theme.input_bg.b, alpha],
    );
    render.batch.push_bg_quad(
        x,
        y,
        width,
        1.0,
        [
            theme.highlight_current_match.r,
            theme.highlight_current_match.g,
            theme.highlight_current_match.b,
            (0.72 * alpha).clamp(0.0, 1.0),
        ],
    );
    for (index, label) in visible_labels.iter().enumerate() {
        push_text(
            render,
            font,
            x + 10.0,
            y + 5.0 + index as f32 * row_height,
            label,
            [
                theme.foreground.r,
                theme.foreground.g,
                theme.foreground.b,
                (0.95 * surface_opacity).clamp(0.0, 1.0),
            ],
        );
    }
}

pub(crate) fn palette_category_label(category: PaletteCategory) -> &'static str {
    match category {
        PaletteCategory::Action => "Actions",
        PaletteCategory::LuaCommand => "Lua Commands",
        PaletteCategory::Workflow => "Workflows",
        PaletteCategory::RecentCommand => "Recent Commands",
        PaletteCategory::FilePath => "File Paths",
        PaletteCategory::Theme => "Themes",
        PaletteCategory::Keybinding => "Keybindings",
        PaletteCategory::SettingsField => "Settings Fields",
        PaletteCategory::GitFile => "Git Changes",
        PaletteCategory::GitWorktree => "Git Worktrees",
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

fn fit_text_to_width(text: &str, max_width: f32, cell_width: f32) -> String {
    if max_width <= 0.0 || cell_width <= 0.0 {
        return String::new();
    }
    let max_chars = columns_for_width(max_width, cell_width);
    fit_text_to_chars(text, max_chars)
}

fn columns_for_width(max_width: f32, cell_width: f32) -> usize {
    if max_width <= 0.0 || cell_width <= 0.0 {
        return 0;
    }
    (max_width / cell_width).floor() as usize
}

fn fit_text_to_chars(text: &str, max_chars: usize) -> String {
    let char_count = text.chars().count();
    if char_count <= max_chars {
        return text.to_string();
    }
    if max_chars == 0 {
        return String::new();
    }
    if max_chars <= 3 {
        return ".".repeat(max_chars);
    }

    let mut truncated = text.chars().take(max_chars - 3).collect::<String>();
    truncated.push_str("...");
    truncated
}

fn right_aligned_text_x(right_edge: f32, text: &str, cell_width: f32) -> f32 {
    right_edge - text.chars().count() as f32 * cell_width
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fit_text_to_width_never_exceeds_available_columns() {
        let fitted = fit_text_to_width("1-15 of 146", 90.0, 10.0);

        assert_eq!(fitted, "1-15 o...");
        assert!(fitted.chars().count() <= columns_for_width(90.0, 10.0));
    }

    #[test]
    fn right_aligned_text_x_keeps_text_inside_right_edge() {
        let x = right_aligned_text_x(200.0, "1-15 of 146", 10.0);

        assert_eq!(x, 90.0);
    }

    #[test]
    fn columns_for_width_rejects_invalid_metrics() {
        assert_eq!(columns_for_width(100.0, 0.0), 0);
        assert_eq!(columns_for_width(-1.0, 10.0), 0);
    }

    #[test]
    fn tab_bar_width_grows_to_fit_large_font_labels() {
        let width = tab_bar_tab_width_for_label("Wok  [147x59]", 18.0);

        assert!(width >= 13.0 * 18.0 + TAB_TEXT_PAD_X * 2.0);
    }

    #[test]
    fn horizontal_tab_hit_testing_uses_variable_widths() {
        let tabs = vec![
            (true, "Wok  [147x59]".to_string()),
            (false, "Shell".to_string()),
        ];
        let rect = Rect::new(0.0, 0.0, 640.0, 32.0);
        let first_width = tab_bar_tab_width_for_label("Wok  [147x59]", 18.0);

        assert_eq!(
            tab_bar_index_at_point(
                rect,
                &tabs,
                0.0,
                first_width + 4.0,
                12.0,
                18.0,
                wok_app::config::TabBarOrientation::Horizontal,
            ),
            Some(1)
        );
    }

    #[test]
    fn vertical_tab_hit_testing_uses_stacked_rows() {
        let tabs = vec![(true, "Wok".to_string()), (false, "Shell".to_string())];
        let rect = Rect::new(0.0, 0.0, 180.0, 300.0);

        assert_eq!(
            tab_bar_index_at_point(
                rect,
                &tabs,
                0.0,
                12.0,
                VERTICAL_TAB_HEIGHT + 4.0,
                12.0,
                wok_app::config::TabBarOrientation::Vertical,
            ),
            Some(1)
        );
    }

    #[test]
    fn chrome_bar_height_expands_to_fit_large_fonts() {
        assert_eq!(chrome_bar_height(18.0), 32.0);
        assert!(chrome_bar_height(36.0) >= 46.0);
    }

    #[test]
    fn chrome_bar_height_keeps_room_for_tab_text_padding() {
        let cell_height = 24.0;
        let bar_height = chrome_bar_height(cell_height);

        assert!(bar_height >= cell_height);
    }

    #[test]
    fn background_layout_stretches_to_window_by_default() {
        let rect = Rect::new(0.0, 0.0, 640.0, 360.0);
        let config = WokConfig::default();

        let (image_rect, uv) = background_image_layout(rect, (100, 100), &config);

        assert_eq!(image_rect, rect);
        assert_eq!(uv, [0.0, 0.0, 1.0, 1.0]);
    }

    #[test]
    fn background_layout_cover_crops_uvs() {
        let rect = Rect::new(0.0, 0.0, 100.0, 100.0);
        let config = WokConfig {
            background_fit: wok_app::config::BackgroundFit::Cover,
            ..WokConfig::default()
        };

        let (image_rect, uv) = background_image_layout(rect, (200, 100), &config);

        assert_eq!(image_rect, rect);
        assert_eq!(uv, [0.25, 0.0, 0.75, 1.0]);
    }

    #[test]
    fn background_layout_custom_width_preserves_aspect_ratio() {
        let rect = Rect::new(0.0, 0.0, 500.0, 300.0);
        let config = WokConfig {
            background_width: Some(200.0),
            background_position: wok_app::config::BackgroundPosition::TopLeft,
            ..WokConfig::default()
        };

        let (image_rect, uv) = background_image_layout(rect, (400, 200), &config);

        assert_eq!(image_rect, Rect::new(0.0, 0.0, 200.0, 100.0));
        assert_eq!(uv, [0.0, 0.0, 1.0, 1.0]);
    }
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
    search: &wok_ui::search::GlobalSearch,
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
    matches: &[wok_ui::quick_select::QuickSelectMatch],
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
    let is_diff = matches!(block_query.mode, BlockQueryMode::Diff);
    let width = if is_filter {
        (viewport.w * 0.48).clamp(280.0, 520.0)
    } else if is_diff {
        (viewport.w * 0.52).clamp(320.0, 640.0)
    } else {
        (viewport.w * 0.4).clamp(240.0, 420.0)
    };
    let list_height = if is_filter || is_diff {
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
        BlockQueryMode::Diff => "Diff Block",
    };
    let header_text = if is_diff {
        block_query.title.clone().unwrap_or_else(|| {
            let baseline = block_query
                .baseline_block_id
                .map_or_else(|| "?".to_string(), |id| id.to_string());
            format!(
                "{} #{} -> #{}",
                title, baseline, block_query.target_block_id
            )
        })
    } else if block_query.query.is_empty() {
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

    if !is_filter && !is_diff {
        return;
    }

    let lines_y = y + 12.0 + font.metrics.cell_height * 2.0;
    let max_chars = ((width - 24.0) / font.metrics.cell_width).floor().max(8.0) as usize;
    let max_visible_lines = filter_overlay_visible_lines(viewport, font.metrics.cell_height);
    let current_line = block_query.current_filtered_line();

    if is_diff {
        if block_query.diff_entries.is_empty() {
            push_text(
                render,
                font,
                x + 10.0,
                lines_y,
                if block_query.is_external_diff() {
                    "No diff hunks for this file"
                } else {
                    "No changed lines between these blocks"
                },
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

        for (visible_idx, (entry_idx, entry)) in block_query
            .diff_entries
            .iter()
            .enumerate()
            .skip(block_query.overlay_scroll_offset)
            .take(max_visible_lines)
            .enumerate()
        {
            let row_y = lines_y + visible_idx as f32 * font.metrics.cell_height;
            if current_line == Some(entry_idx) {
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

            let (prefix, accent) = match entry.kind {
                DiffLineKind::Added => (
                    "+",
                    [
                        theme.block_success_accent.r,
                        theme.block_success_accent.g,
                        theme.block_success_accent.b,
                        1.0,
                    ],
                ),
                DiffLineKind::Removed => (
                    "-",
                    [
                        theme.block_error_accent.r,
                        theme.block_error_accent.g,
                        theme.block_error_accent.b,
                        1.0,
                    ],
                ),
                DiffLineKind::Context => (
                    " ",
                    [
                        theme.status_bar_text.r,
                        theme.status_bar_text.g,
                        theme.status_bar_text.b,
                        1.0,
                    ],
                ),
                DiffLineKind::HunkHeader => (
                    "@",
                    [
                        theme.highlight_current_match.r,
                        theme.highlight_current_match.g,
                        theme.highlight_current_match.b,
                        1.0,
                    ],
                ),
            };
            let line_label = if matches!(entry.kind, DiffLineKind::HunkHeader) {
                truncate_overlay_text(&entry.text, max_chars)
            } else {
                format!("{prefix} {}", truncate_overlay_text(&entry.text, max_chars))
            };
            push_text(
                render,
                font,
                x + 10.0,
                row_y,
                &line_label,
                with_opacity(accent, surface_opacity),
            );
        }
        return;
    }

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
        if current_line == Some(*line_idx) {
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

pub(crate) fn render_failure_trends_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    rows: &[String],
    bucket_ms: u64,
    surface_opacity: f32,
) {
    let width = (viewport.w * 0.6).clamp(360.0, 760.0);
    let max_rows = 10usize;
    let visible_rows = rows.len().min(max_rows).max(1);
    let height = font.metrics.cell_height * (visible_rows as f32 + 2.0) + 14.0;
    let x = viewport.x + 12.0;
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

    let bucket_label = if bucket_ms >= 3_600_000 {
        format!("{}h", bucket_ms / 3_600_000)
    } else {
        format!("{}m", bucket_ms / 60_000)
    };
    let title = format!("Failure Trends ({bucket_label} buckets)");
    push_text(
        render,
        font,
        x + 10.0,
        y + 6.0,
        &title,
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

    let max_chars = ((width - 24.0) / font.metrics.cell_width).floor().max(8.0) as usize;
    if rows.is_empty() {
        push_text(
            render,
            font,
            x + 10.0,
            y + 6.0 + font.metrics.cell_height,
            "No recent failures for this pane",
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

    for (index, row) in rows.iter().take(max_rows).enumerate() {
        let row_y = y + 6.0 + (index as f32 + 1.0) * font.metrics.cell_height;
        push_text(
            render,
            font,
            x + 10.0,
            row_y,
            &truncate_overlay_text(row, max_chars),
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
}

pub(crate) fn render_workspace_insights_overlay(
    render: &mut RenderState,
    font: &mut FontSystem,
    theme: &Theme,
    viewport: Rect,
    rows: &[String],
    surface_opacity: f32,
) {
    let width = (viewport.w * 0.7).clamp(420.0, 880.0);
    let max_rows = 10usize;
    let visible_rows = rows.len().min(max_rows).max(1);
    let height = font.metrics.cell_height * (visible_rows as f32 + 2.0) + 14.0;
    let x = viewport.x + 12.0;
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
        "Workspace Insights",
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

    let max_chars = ((width - 24.0) / font.metrics.cell_width).floor().max(8.0) as usize;
    if rows.is_empty() {
        push_text(
            render,
            font,
            x + 10.0,
            y + 6.0 + font.metrics.cell_height,
            "No workspace insights available",
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

    for (index, row) in rows.iter().take(max_rows).enumerate() {
        let row_y = y + 6.0 + (index as f32 + 1.0) * font.metrics.cell_height;
        push_text(
            render,
            font,
            x + 10.0,
            row_y,
            &truncate_overlay_text(row, max_chars),
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

pub(crate) fn push_background_image(
    batch: &mut QuadBatch,
    rect: Rect,
    image_size: (u32, u32),
    config: &WokConfig,
    window_opacity: f32,
) {
    if rect.w <= 0.0 || rect.h <= 0.0 || image_size.0 == 0 || image_size.1 == 0 {
        return;
    }
    let opacity = (window_opacity * config.background_opacity).clamp(0.0, 1.0);
    if opacity <= 0.0 {
        return;
    }
    let (image_rect, uv_rect) = background_image_layout(rect, image_size, config);
    if image_rect.w <= 0.0 || image_rect.h <= 0.0 {
        return;
    }
    batch.push_image_quad_with_uv(
        image_rect.x,
        image_rect.y,
        image_rect.w,
        image_rect.h,
        uv_rect,
        [1.0, 1.0, 1.0, opacity],
    );
}

fn background_image_layout(
    rect: Rect,
    image_size: (u32, u32),
    config: &WokConfig,
) -> (Rect, [f32; 4]) {
    let source_w = image_size.0 as f32;
    let source_h = image_size.1 as f32;
    let custom_w = config.background_width;
    let custom_h = config.background_height;
    let (mut width, mut height) = match (custom_w, custom_h) {
        (Some(width), Some(height)) => (width, height),
        (Some(width), None) => (width, width * source_h / source_w),
        (None, Some(height)) => (height * source_w / source_h, height),
        (None, None) => match config.background_fit {
            wok_app::config::BackgroundFit::Stretch => (rect.w, rect.h),
            wok_app::config::BackgroundFit::Cover => {
                let scale = (rect.w / source_w).max(rect.h / source_h);
                (source_w * scale, source_h * scale)
            }
            wok_app::config::BackgroundFit::Contain => {
                let scale = (rect.w / source_w).min(rect.h / source_h);
                (source_w * scale, source_h * scale)
            }
            wok_app::config::BackgroundFit::Center => (source_w, source_h),
        },
    };
    if matches!(
        config.background_fit,
        wok_app::config::BackgroundFit::Stretch
    ) && custom_w.is_none()
        && custom_h.is_none()
    {
        width = rect.w;
        height = rect.h;
    }

    let x = match config.background_position {
        wok_app::config::BackgroundPosition::TopLeft
        | wok_app::config::BackgroundPosition::BottomLeft => rect.x,
        wok_app::config::BackgroundPosition::TopRight
        | wok_app::config::BackgroundPosition::BottomRight => rect.x + rect.w - width,
        wok_app::config::BackgroundPosition::Center => rect.x + (rect.w - width) * 0.5,
    };
    let y = match config.background_position {
        wok_app::config::BackgroundPosition::TopLeft
        | wok_app::config::BackgroundPosition::TopRight => rect.y,
        wok_app::config::BackgroundPosition::BottomLeft
        | wok_app::config::BackgroundPosition::BottomRight => rect.y + rect.h - height,
        wok_app::config::BackgroundPosition::Center => rect.y + (rect.h - height) * 0.5,
    };

    let mut image_rect = Rect::new(x, y, width, height);
    let original_width = image_rect.w;
    let original_height = image_rect.h;
    let mut uv = [0.0, 0.0, 1.0, 1.0];
    if image_rect.x < rect.x {
        let clipped = rect.x - image_rect.x;
        uv[0] += clipped / original_width;
        image_rect.w -= clipped;
        image_rect.x = rect.x;
    }
    if image_rect.y < rect.y {
        let clipped = rect.y - image_rect.y;
        uv[1] += clipped / original_height;
        image_rect.h -= clipped;
        image_rect.y = rect.y;
    }
    let overflow_x = image_rect.x + image_rect.w - (rect.x + rect.w);
    if overflow_x > 0.0 {
        uv[2] -= overflow_x / original_width;
        image_rect.w -= overflow_x;
    }
    let overflow_y = image_rect.y + image_rect.h - (rect.y + rect.h);
    if overflow_y > 0.0 {
        uv[3] -= overflow_y / original_height;
        image_rect.h -= overflow_y;
    }
    (image_rect, uv)
}

pub(crate) fn resolve_background_image_path(config: &WokConfig) -> Option<std::path::PathBuf> {
    config.background_image.clone().or_else(|| {
        config.theme_path.as_ref().and_then(|path| {
            wok_ui::theme_loader::load_theme(path)
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

    WokConfig::config_dir()
        .join("themes")
        .join(format!("{name}.toml"))
}

pub(crate) fn search_match_at_cell(
    search: &wok_ui::search::GlobalSearch,
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
    search: &wok_ui::search::GlobalSearch,
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

pub(crate) fn prewarm_common_glyphs(render: &mut RenderState, font: &mut FontSystem) -> usize {
    let (pipeline, gpu, atlas) = (&mut render.pipeline, &render.gpu, &mut render.atlas);
    let mut warmed = 0;
    for character in common_prewarm_glyphs() {
        if prewarm_glyph(pipeline, gpu, atlas, font, character) {
            warmed += 1;
        }
    }
    warmed
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

    let glyph_key = wok_renderer::atlas::GlyphKey {
        font_id: 0,
        glyph_id: character as u32,
        font_size_tenths: (font.font_size * 10.0) as u32,
    };
    let baseline = font.metrics.baseline;

    if let Some(glyph) = font.rasterize(character) {
        let width = glyph.width;
        let height = glyph.height;
        let offset_x = glyph.offset_x;
        let offset_y = glyph.offset_y;
        if let Some(allocation) = atlas.get_or_insert_with_status(glyph_key, width, height) {
            if allocation.inserted && width > 0 && height > 0 {
                pipeline.upload_glyph(
                    gpu,
                    allocation.region.x,
                    allocation.region.y,
                    width,
                    height,
                    &glyph.data,
                );
            }
            batch.push_glyph_quad(
                x + offset_x as f32,
                y + (baseline - offset_y as f32),
                width as f32,
                height as f32,
                &allocation.region,
                color,
            );
        }
    }
}

fn prewarm_glyph(
    pipeline: &mut TerminalRenderPipeline,
    gpu: &GpuContext,
    atlas: &mut GlyphAtlas,
    font: &mut FontSystem,
    character: char,
) -> bool {
    if character == ' ' || character == '\0' {
        return false;
    }

    let glyph_key = wok_renderer::atlas::GlyphKey {
        font_id: 0,
        glyph_id: character as u32,
        font_size_tenths: (font.font_size * 10.0) as u32,
    };

    let Some(glyph) = font.rasterize(character) else {
        return false;
    };
    let Some(allocation) = atlas.get_or_insert_with_status(glyph_key, glyph.width, glyph.height)
    else {
        return false;
    };
    if allocation.inserted && glyph.width > 0 && glyph.height > 0 {
        pipeline.upload_glyph(
            gpu,
            allocation.region.x,
            allocation.region.y,
            glyph.width,
            glyph.height,
            &glyph.data,
        );
    }
    allocation.inserted
}

fn common_prewarm_glyphs() -> impl Iterator<Item = char> {
    const EXTRA_CODEPOINTS: &[u32] = &[
        0x2500, 0x2502, 0x250c, 0x2510, 0x2514, 0x2518, 0x251c, 0x2524, 0x252c, 0x2534, 0x253c,
        0x2580, 0x2584, 0x2588, 0x258c, 0x2590, 0x2591, 0x2592, 0x2593, 0x25cf, 0x25cb, 0x2713,
        0x2717,
    ];

    (b'!'..=b'~').map(char::from).chain(
        EXTRA_CODEPOINTS
            .iter()
            .filter_map(|codepoint| char::from_u32(*codepoint)),
    )
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

pub(crate) fn build_visible_row_positions(
    visible_rows: &[usize],
    blocks: &[Block],
) -> Vec<Option<usize>> {
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
    global_search: &wok_ui::search::GlobalSearch,
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
            baseline_block_id: query.baseline_block_id,
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
            diff_entries: query
                .diff_entries
                .iter()
                .map(|entry| (entry.kind, entry.text.clone()))
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
    global_search: &wok_ui::search::GlobalSearch,
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
    push_row_background_runs(
        batch,
        theme,
        terminal,
        inline_images,
        absolute_row,
        total_cols,
        viewport,
        cell_width,
        cell_height,
        row_y,
        terminal_surface_alpha,
    );
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

#[allow(clippy::too_many_arguments)]
fn push_row_background_runs(
    batch: &mut QuadBatch,
    theme: &Theme,
    terminal: &Terminal,
    inline_images: &InlineImageStore,
    absolute_row: usize,
    total_cols: usize,
    viewport: Rect,
    cell_width: f32,
    cell_height: f32,
    row_y: f32,
    terminal_surface_alpha: f32,
) {
    let mut run_start = 0usize;
    let mut run_color: Option<[f32; 4]> = None;

    for col_idx in 0..total_cols {
        let cell = terminal.state.cell_at_absolute(absolute_row, col_idx);
        let color = resolve_cell_background_color(
            &cell,
            theme,
            inline_images.sample_cell_color(absolute_row, col_idx),
            terminal_surface_alpha,
        );

        match run_color {
            Some(current) if current == color => {}
            Some(current) => {
                push_background_run(
                    batch,
                    viewport,
                    cell_width,
                    cell_height,
                    row_y,
                    run_start,
                    col_idx,
                    current,
                );
                run_start = col_idx;
                run_color = Some(color);
            }
            None => {
                run_start = col_idx;
                run_color = Some(color);
            }
        }
    }

    if let Some(color) = run_color {
        push_background_run(
            batch,
            viewport,
            cell_width,
            cell_height,
            row_y,
            run_start,
            total_cols,
            color,
        );
    }
}

fn resolve_cell_background_color(
    cell: &CellRenderData,
    theme: &Theme,
    inline_color: Option<[f32; 4]>,
    terminal_surface_alpha: f32,
) -> [f32; 4] {
    let mut bg = resolve_cell_color(&cell.bg, theme, true);
    let mut fg = resolve_cell_color(&cell.fg, theme, false);
    if cell.is_inverse {
        std::mem::swap(&mut bg, &mut fg);
    }
    if matches!(cell.bg, CellColor::Named(idx) if idx >= 16) {
        bg[3] *= terminal_surface_alpha;
    }
    inline_color.unwrap_or(bg)
}

#[allow(clippy::too_many_arguments)]
fn push_background_run(
    batch: &mut QuadBatch,
    viewport: Rect,
    cell_width: f32,
    cell_height: f32,
    row_y: f32,
    start_col: usize,
    end_col: usize,
    color: [f32; 4],
) {
    if end_col <= start_col {
        return;
    }
    batch.push_bg_quad(
        viewport.x + start_col as f32 * cell_width,
        row_y,
        (end_col - start_col) as f32 * cell_width,
        cell_height,
        color,
    );
}

pub(crate) fn selection_end_col(terminal: &Terminal, end_col: u16) -> usize {
    if end_col == u16::MAX {
        terminal.state.columns()
    } else {
        (usize::from(end_col) + 1).min(terminal.state.columns())
    }
}

/// Resolve a CellColor to [r, g, b, a] using the Wok theme.
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
