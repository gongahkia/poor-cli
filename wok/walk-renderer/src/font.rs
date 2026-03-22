//! Font system: loading, shaping, and fallback using cosmic-text.

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

/// Font system wrapper around cosmic-text.
pub struct FontSystem {
    /// The cosmic-text font system.
    pub inner: cosmic_text::FontSystem,
    /// Current cell metrics.
    pub metrics: CellMetrics,
}

impl FontSystem {
    /// Create a new font system with the given font family and size.
    pub fn new(font_family: &str, font_size: f32) -> Self {
        let inner = cosmic_text::FontSystem::new();
        let metrics = compute_metrics(font_size);

        Self { inner, metrics }
    }

    /// Update the font size and recompute metrics.
    pub fn set_font_size(&mut self, size: f32) {
        self.metrics = compute_metrics(size);
    }

    /// Calculate terminal grid dimensions from pixel dimensions.
    pub fn grid_dimensions(&self, width: f32, height: f32) -> (u16, u16) {
        let cols = (width / self.metrics.cell_width).floor() as u16;
        let rows = (height / self.metrics.cell_height).floor() as u16;
        (cols.max(2), rows.max(1))
    }
}

fn compute_metrics(font_size: f32) -> CellMetrics {
    // Approximate metrics based on font size (monospace assumption)
    let cell_width = font_size * 0.6;  // typical monospace width ratio
    let cell_height = font_size * 1.2; // typical line height
    let baseline = font_size * 0.8;    // approximate baseline

    CellMetrics {
        cell_width,
        cell_height,
        baseline,
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
}
