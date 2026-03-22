//! Text layout: arranges characters into positioned glyph runs.

use crate::atlas::AtlasRegion;

/// RGBA color.
#[derive(Debug, Clone, Copy)]
pub struct Color {
    /// Red component.
    pub r: f32,
    /// Green component.
    pub g: f32,
    /// Blue component.
    pub b: f32,
    /// Alpha component.
    pub a: f32,
}

/// Style for a glyph.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GlyphStyle {
    /// Normal weight.
    Regular,
    /// Bold weight.
    Bold,
    /// Italic style.
    Italic,
    /// Bold and italic.
    BoldItalic,
}

/// A positioned glyph within a glyph run.
#[derive(Debug, Clone)]
pub struct PositionedGlyph {
    /// Atlas region for this glyph's texture data.
    pub atlas_entry: AtlasRegion,
    /// X position in pixels.
    pub x: f32,
    /// Y position in pixels (baseline).
    pub y: f32,
    /// Foreground color.
    pub color: Color,
}

/// A run of positioned glyphs for a single line or segment.
#[derive(Debug, Clone)]
pub struct GlyphRun {
    /// The positioned glyphs in this run.
    pub glyphs: Vec<PositionedGlyph>,
}

/// Layout a single line of text into positioned glyphs.
pub fn layout_line(
    text: &str,
    start_x: f32,
    baseline_y: f32,
    cell_width: f32,
    color: Color,
) -> GlyphRun {
    let mut glyphs = Vec::new();
    let mut x = start_x;

    for ch in text.chars() {
        let char_width = if is_wide_char(ch) { 2.0 } else { 1.0 };

        glyphs.push(PositionedGlyph {
            atlas_entry: AtlasRegion {
                x: 0,
                y: 0,
                width: 0,
                height: 0,
                u_min: 0.0,
                v_min: 0.0,
                u_max: 0.0,
                v_max: 0.0,
            },
            x,
            y: baseline_y,
            color,
        });

        x += cell_width * char_width;
    }

    GlyphRun { glyphs }
}

/// Check if a character is a wide (double-width) character.
fn is_wide_char(ch: char) -> bool {
    unicode_width::UnicodeWidthChar::width(ch).unwrap_or(1) > 1
}

/// Layout a grid of cells into glyph runs.
pub fn layout_grid(
    lines: &[String],
    origin_x: f32,
    origin_y: f32,
    cell_width: f32,
    line_height: f32,
    color: Color,
) -> Vec<GlyphRun> {
    lines
        .iter()
        .enumerate()
        .map(|(row, line)| {
            let baseline_y = origin_y + (row as f32) * line_height;
            layout_line(line, origin_x, baseline_y, cell_width, color)
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_layout_line_positions() {
        let color = Color {
            r: 1.0,
            g: 1.0,
            b: 1.0,
            a: 1.0,
        };
        let run = layout_line("Hello", 0.0, 20.0, 10.0, color);
        assert_eq!(run.glyphs.len(), 5);
        // Positions should be strictly increasing
        for i in 1..run.glyphs.len() {
            assert!(run.glyphs[i].x > run.glyphs[i - 1].x);
        }
    }

    #[test]
    fn test_wide_char_occupies_two_cells() {
        let color = Color {
            r: 1.0,
            g: 1.0,
            b: 1.0,
            a: 1.0,
        };
        // CJK character U+6F22 (漢) is double-width
        let run = layout_line("a漢b", 0.0, 0.0, 10.0, color);
        assert_eq!(run.glyphs.len(), 3);
        assert!((run.glyphs[0].x - 0.0).abs() < f32::EPSILON); // 'a' at 0
        assert!((run.glyphs[1].x - 10.0).abs() < f32::EPSILON); // '漢' at 10
        assert!((run.glyphs[2].x - 30.0).abs() < f32::EPSILON); // 'b' at 30 (wide=2 cells)
    }

    #[test]
    fn test_layout_grid() {
        let color = Color {
            r: 1.0,
            g: 1.0,
            b: 1.0,
            a: 1.0,
        };
        let lines = vec!["Hello".to_string(), "World".to_string()];
        let runs = layout_grid(&lines, 0.0, 0.0, 10.0, 20.0, color);
        assert_eq!(runs.len(), 2);
        // First line at y=0, second at y=20
        assert!((runs[0].glyphs[0].y - 0.0).abs() < f32::EPSILON);
        assert!((runs[1].glyphs[0].y - 20.0).abs() < f32::EPSILON);
    }
}
