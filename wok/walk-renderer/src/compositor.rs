//! Compositor: blends rendering layers for final frame output.

/// Rendering layer ordering for compositing.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum RenderLayer {
    /// Background color or image (lowest layer).
    Background = 0,
    /// Cell background colors.
    CellBackground = 1,
    /// Text glyphs.
    TextGlyphs = 2,
    /// Selection highlight overlay.
    Selection = 3,
    /// Search match highlights.
    SearchHighlight = 4,
    /// Block decorations (separators, exit code bars).
    BlockDecoration = 5,
    /// Cursor overlay (highest layer).
    Cursor = 6,
}

/// Configuration for the compositor.
pub struct CompositorConfig {
    /// Terminal content opacity (0.0-1.0).
    pub opacity: f32,
    /// Whether a background image is active.
    pub has_background_image: bool,
}

impl Default for CompositorConfig {
    fn default() -> Self {
        Self {
            opacity: 1.0,
            has_background_image: false,
        }
    }
}

/// Compositor manages the render pass ordering and blending.
pub struct Compositor {
    /// Configuration.
    pub config: CompositorConfig,
}

impl Compositor {
    /// Create a new compositor with the given config.
    pub fn new(config: CompositorConfig) -> Self {
        Self { config }
    }

    /// Return the ordered list of render layers.
    pub fn layer_order(&self) -> Vec<RenderLayer> {
        let mut layers = vec![
            RenderLayer::Background,
            RenderLayer::CellBackground,
            RenderLayer::TextGlyphs,
            RenderLayer::Selection,
            RenderLayer::SearchHighlight,
            RenderLayer::BlockDecoration,
            RenderLayer::Cursor,
        ];
        layers.sort();
        layers
    }
}

impl Default for Compositor {
    fn default() -> Self {
        Self::new(CompositorConfig::default())
    }
}
