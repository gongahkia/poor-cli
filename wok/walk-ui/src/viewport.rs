//! Terminal viewport renderer: draws the terminal grid, cursor, and block decorations.

use crate::layout::Rect;

/// Viewport scroll state.
pub struct ViewportRenderer {
    /// Current scroll position (fractional for smooth scrolling).
    pub scroll_position: f32,
    /// Target scroll position for smooth animation.
    smooth_scroll_target: f32,
    /// Whether the viewport needs a full re-render.
    needs_render: bool,
}

impl ViewportRenderer {
    /// Create a new viewport renderer.
    pub fn new() -> Self {
        Self {
            scroll_position: 0.0,
            smooth_scroll_target: 0.0,
            needs_render: true,
        }
    }

    /// Handle a scroll event.
    pub fn handle_scroll(&mut self, delta: f32) {
        self.smooth_scroll_target += delta;
        if self.smooth_scroll_target < 0.0 {
            self.smooth_scroll_target = 0.0;
        }
    }

    /// Advance smooth scrolling (call once per frame).
    ///
    /// Lerps scroll_position toward smooth_scroll_target by 0.2 each frame.
    pub fn tick(&mut self) {
        let diff = self.smooth_scroll_target - self.scroll_position;
        if diff.abs() > 0.01 {
            self.scroll_position += diff * 0.2;
            self.needs_render = true;
        } else {
            self.scroll_position = self.smooth_scroll_target;
        }
    }

    /// Scroll to the bottom (follow live output).
    pub fn scroll_to_bottom(&mut self, max_scroll: f32) {
        self.smooth_scroll_target = max_scroll;
    }

    /// Scroll to the top of scrollback.
    pub fn scroll_to_top(&mut self) {
        self.smooth_scroll_target = 0.0;
    }

    /// Check if a render is needed.
    pub fn needs_render(&self) -> bool {
        self.needs_render
    }

    /// Mark as rendered.
    pub fn mark_rendered(&mut self) {
        self.needs_render = false;
    }
}

impl Default for ViewportRenderer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_smooth_scroll() {
        let mut vp = ViewportRenderer::new();
        vp.handle_scroll(10.0);
        assert!((vp.smooth_scroll_target - 10.0).abs() < f32::EPSILON);

        // After tick, position moves toward target
        vp.tick();
        assert!(vp.scroll_position > 0.0);
        assert!(vp.scroll_position < 10.0);
    }

    #[test]
    fn test_scroll_to_bottom() {
        let mut vp = ViewportRenderer::new();
        vp.scroll_to_bottom(100.0);
        assert!((vp.smooth_scroll_target - 100.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_no_negative_scroll() {
        let mut vp = ViewportRenderer::new();
        vp.handle_scroll(-10.0);
        assert!((vp.smooth_scroll_target - 0.0).abs() < f32::EPSILON);
    }
}
