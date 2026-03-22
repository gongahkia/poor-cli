//! Font system: loading, shaping, and glyph rasterization using cosmic-text.

use std::collections::HashMap;

use cosmic_text::{
    Attrs, Buffer, FamilyOwned, FontSystem as CosmicFontSystem, Metrics, Shaping, SwashCache,
};

/// Font metrics for cell grid layout.
#[derive(Debug, Clone, Copy)]
pub struct CellMetrics {
    /// Width of a single cell in pixels.
    pub cell_width: f32,
    /// Height of a single cell (line height) in pixels.
    pub cell_height: f32,
    /// Baseline offset from the top of the cell.
    pub baseline: f32,
}

/// Rasterized glyph data.
pub struct RasterizedGlyph {
    /// Pixel data (alpha channel, one byte per pixel).
    pub data: Vec<u8>,
    /// Width in pixels.
    pub width: u32,
    /// Height in pixels.
    pub height: u32,
    /// X offset from cell origin.
    pub offset_x: i32,
    /// Y offset from cell origin.
    pub offset_y: i32,
}

/// Font system wrapper around cosmic-text with glyph rasterization cache.
pub struct FontSystem {
    /// The cosmic-text font system.
    pub inner: CosmicFontSystem,
    /// Swash cache for glyph rasterization.
    swash_cache: SwashCache,
    /// Current cell metrics.
    pub metrics: CellMetrics,
    /// Font size in pixels.
    pub font_size: f32,
    /// Requested font family.
    pub font_family: FamilyOwned,
    /// Cached rasterized glyphs.
    glyph_cache: HashMap<char, Option<RasterizedGlyph>>,
}

impl FontSystem {
    /// Create a new font system with the given font family and size.
    pub fn new(font_family: &str, font_size: f32) -> Self {
        let mut inner = CosmicFontSystem::new();
        let swash_cache = SwashCache::new();
        let family = parse_family(font_family);
        let metrics = compute_metrics(&mut inner, font_size, &family);

        Self {
            inner,
            swash_cache,
            metrics,
            font_size,
            font_family: family,
            glyph_cache: HashMap::new(),
        }
    }

    /// Update the font size and recompute metrics.
    pub fn set_font_size(&mut self, size: f32) {
        self.font_size = size;
        self.metrics = compute_metrics(&mut self.inner, size, &self.font_family);
        self.glyph_cache.clear();
    }

    /// Calculate terminal grid dimensions from pixel dimensions.
    pub fn grid_dimensions(&self, width: f32, height: f32) -> (u16, u16) {
        let cols = (width / self.metrics.cell_width).floor() as u16;
        let rows = (height / self.metrics.cell_height).floor() as u16;
        (cols.max(2), rows.max(1))
    }

    /// Rasterize a single character glyph.
    ///
    /// Returns the rasterized glyph data, or None if the character cannot be rendered.
    pub fn rasterize(&mut self, ch: char) -> Option<&RasterizedGlyph> {
        if !self.glyph_cache.contains_key(&ch) {
            let glyph = self.rasterize_inner(ch);
            self.glyph_cache.insert(ch, glyph);
        }
        self.glyph_cache.get(&ch).and_then(|g| g.as_ref())
    }

    fn rasterize_inner(&mut self, ch: char) -> Option<RasterizedGlyph> {
        let metrics = Metrics::new(self.font_size, self.font_size * 1.2);
        let attrs = Attrs::new().family(self.font_family.as_family());
        let mut buffer = Buffer::new(&mut self.inner, metrics);
        buffer.set_text(&mut self.inner, &ch.to_string(), attrs, Shaping::Advanced);
        buffer.shape_until_scroll(&mut self.inner, false);

        // Iterate layout runs to find the glyph
        for run in buffer.layout_runs() {
            for glyph in run.glyphs.iter() {
                let physical = glyph.physical((0.0, 0.0), 1.0);
                if let Some(image) = self
                    .swash_cache
                    .get_image(&mut self.inner, physical.cache_key)
                {
                    let width = image.placement.width;
                    let height = image.placement.height;
                    if width == 0 || height == 0 {
                        return None;
                    }

                    // Convert to alpha-only data
                    let data = match image.content {
                        cosmic_text::SwashContent::Mask => image.data.clone(),
                        cosmic_text::SwashContent::Color => {
                            // RGBA -> take alpha channel
                            image
                                .data
                                .chunks(4)
                                .map(|px| px.get(3).copied().unwrap_or(255))
                                .collect()
                        }
                        cosmic_text::SwashContent::SubpixelMask => {
                            // RGB subpixel -> average to grayscale
                            image
                                .data
                                .chunks(3)
                                .map(|px| {
                                    let r = u16::from(px.first().copied().unwrap_or(0));
                                    let g = u16::from(px.get(1).copied().unwrap_or(0));
                                    let b = u16::from(px.get(2).copied().unwrap_or(0));
                                    ((r + g + b) / 3) as u8
                                })
                                .collect()
                        }
                    };

                    return Some(RasterizedGlyph {
                        data,
                        width,
                        height,
                        offset_x: image.placement.left,
                        offset_y: image.placement.top,
                    });
                }
            }
        }
        None
    }
}

fn compute_metrics(
    font_system: &mut CosmicFontSystem,
    font_size: f32,
    font_family: &FamilyOwned,
) -> CellMetrics {
    let metrics = Metrics::new(font_size, font_size * 1.2);
    let attrs = Attrs::new().family(font_family.as_family());
    let mut buffer = Buffer::new(font_system, metrics);
    buffer.set_text(font_system, "M", attrs, Shaping::Advanced);
    buffer.shape_until_scroll(font_system, false);

    let (cell_width, cell_height, baseline) = buffer.layout_runs().next().map_or_else(
        || {
            (
                (font_size * 0.6).ceil(),
                metrics.line_height.ceil(),
                (font_size * 0.85).ceil(),
            )
        },
        |run| {
            (
                run.line_w.max(font_size * 0.5).ceil(),
                run.line_height.max(metrics.line_height).ceil(),
                run.line_y.max(font_size * 0.75).ceil(),
            )
        },
    );

    CellMetrics {
        cell_width,
        cell_height,
        baseline,
    }
}

fn parse_family(font_family: &str) -> FamilyOwned {
    match font_family.trim().to_ascii_lowercase().as_str() {
        "serif" => FamilyOwned::Serif,
        "sans" | "sans-serif" | "sansserif" => FamilyOwned::SansSerif,
        "cursive" => FamilyOwned::Cursive,
        "fantasy" => FamilyOwned::Fantasy,
        "mono" | "monospace" => FamilyOwned::Monospace,
        _ => FamilyOwned::Name(font_family.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_grid_dimensions() {
        let font = FontSystem::new("monospace", 14.0);
        let (cols, rows) = font.grid_dimensions(800.0, 600.0);
        assert!(cols > 0);
        assert!(rows > 0);
    }

    #[test]
    fn test_cell_metrics() {
        let font = FontSystem::new("monospace", 14.0);
        assert!(font.metrics.cell_width > 0.0);
        assert!(font.metrics.cell_height > font.metrics.cell_width);
    }

    #[test]
    fn test_custom_font_family_is_stored() {
        let font = FontSystem::new("JetBrains Mono", 14.0);
        assert_eq!(
            font.font_family,
            FamilyOwned::Name("JetBrains Mono".to_string())
        );
    }

    #[test]
    fn test_rasterize_ascii() {
        let mut font = FontSystem::new("monospace", 14.0);
        // 'A' should be rasterizable on any system with fonts
        let glyph = font.rasterize('A');
        // May be None in CI without fonts, so just check no panic
        if let Some(g) = glyph {
            assert!(g.width > 0);
            assert!(g.height > 0);
            assert_eq!(g.data.len(), (g.width * g.height) as usize);
        }
    }
}
