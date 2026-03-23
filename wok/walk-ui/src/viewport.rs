//! Viewport state for scrolling, follow-output, and smooth offset changes.

/// Viewport scroll state.
pub struct ViewportRenderer {
    /// Current scroll position (fractional for smooth scrolling).
    pub scroll_position: f32,
    /// Target scroll position for smooth animation.
    smooth_scroll_target: f32,
    /// Whether new output should snap the viewport back to the live prompt.
    follow_output: bool,
    /// Whether the viewport needs a full re-render.
    needs_render: bool,
}

impl ViewportRenderer {
    /// Create a new viewport renderer.
    pub fn new() -> Self {
        Self {
            scroll_position: 0.0,
            smooth_scroll_target: 0.0,
            follow_output: true,
            needs_render: true,
        }
    }

    /// Handle a scroll event measured in display-offset rows.
    pub fn handle_scroll(&mut self, delta: f32, max_scroll: f32) {
        self.follow_output = false;
        self.smooth_scroll_target = (self.smooth_scroll_target + delta).clamp(0.0, max_scroll);
        self.needs_render = true;
    }

    /// Scroll by a number of rows.
    pub fn scroll_lines(&mut self, lines: i32, max_scroll: f32) {
        self.handle_scroll(lines as f32, max_scroll);
    }

    /// Scroll by a number of viewport pages.
    pub fn scroll_pages(&mut self, pages: i32, page_size: usize, max_scroll: f32) {
        self.handle_scroll(pages as f32 * page_size as f32, max_scroll);
    }

    /// Advance smooth scrolling and return whether the rendered offset changed.
    pub fn tick(&mut self, max_scroll: f32) -> bool {
        self.smooth_scroll_target = self.smooth_scroll_target.clamp(0.0, max_scroll);
        let diff = self.smooth_scroll_target - self.scroll_position;
        if diff.abs() > 0.01 {
            self.scroll_position += diff * 0.2;
            self.scroll_position = self.scroll_position.clamp(0.0, max_scroll);
            self.needs_render = true;
            true
        } else {
            self.scroll_position = self.smooth_scroll_target;
            false
        }
    }

    /// Scroll to the live output position.
    pub fn scroll_to_bottom(&mut self) {
        self.follow_output = true;
        self.smooth_scroll_target = 0.0;
        self.scroll_position = 0.0;
        self.needs_render = true;
    }

    /// Scroll to the oldest available scrollback row.
    pub fn scroll_to_top(&mut self, max_scroll: f32) {
        self.follow_output = false;
        self.smooth_scroll_target = max_scroll.clamp(0.0, max_scroll);
        self.scroll_position = self.smooth_scroll_target;
        self.needs_render = true;
    }

    /// Snap the viewport to an exact display offset.
    pub fn set_display_offset(&mut self, offset: usize, max_scroll: f32) {
        let clamped = (offset as f32).clamp(0.0, max_scroll);
        self.scroll_position = clamped;
        self.smooth_scroll_target = clamped;
        self.follow_output = clamped == 0.0;
        self.needs_render = true;
    }

    /// Return the current integral display offset.
    pub fn display_offset(&self) -> usize {
        self.scroll_position.round().max(0.0) as usize
    }

    /// Return whether the viewport is following live output.
    pub fn follow_output(&self) -> bool {
        self.follow_output
    }

    /// Set follow-output mode explicitly.
    pub fn set_follow_output(&mut self, follow_output: bool, max_scroll: f32) {
        self.follow_output = follow_output;
        if follow_output {
            self.scroll_to_bottom();
        } else {
            self.smooth_scroll_target = self.smooth_scroll_target.clamp(0.0, max_scroll);
            self.scroll_position = self.scroll_position.clamp(0.0, max_scroll);
            self.needs_render = true;
        }
    }

    /// Update viewport state after terminal output changed.
    pub fn on_output(&mut self, max_scroll: f32) {
        if self.follow_output {
            self.scroll_to_bottom();
        } else {
            self.smooth_scroll_target = self.smooth_scroll_target.clamp(0.0, max_scroll);
            self.scroll_position = self.scroll_position.clamp(0.0, max_scroll);
        }
    }

    /// Reveal a specific display offset and disable follow-output mode.
    pub fn reveal_offset(&mut self, offset: usize, max_scroll: f32) {
        self.follow_output = false;
        self.set_display_offset(offset, max_scroll);
    }

    /// Clamp the current state to the current maximum scrollback size.
    pub fn clamp_to_max(&mut self, max_scroll: f32) {
        self.smooth_scroll_target = self.smooth_scroll_target.clamp(0.0, max_scroll);
        self.scroll_position = self.scroll_position.clamp(0.0, max_scroll);
        if self.follow_output {
            self.scroll_to_bottom();
        }
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
        vp.handle_scroll(10.0, 100.0);
        assert!((vp.smooth_scroll_target - 10.0).abs() < f32::EPSILON);

        vp.tick(100.0);
        assert!(vp.scroll_position > 0.0);
        assert!(vp.scroll_position < 10.0);
        assert!(!vp.follow_output());
    }

    #[test]
    fn test_scroll_to_bottom() {
        let mut vp = ViewportRenderer::new();
        vp.scroll_lines(25, 100.0);
        vp.scroll_to_bottom();
        assert!((vp.smooth_scroll_target - 0.0).abs() < f32::EPSILON);
        assert!(vp.follow_output());
    }

    #[test]
    fn test_no_negative_scroll() {
        let mut vp = ViewportRenderer::new();
        vp.handle_scroll(-10.0, 100.0);
        assert!((vp.smooth_scroll_target - 0.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_scroll_to_top_uses_max_offset() {
        let mut vp = ViewportRenderer::new();
        vp.scroll_to_top(42.0);
        assert_eq!(vp.display_offset(), 42);
        assert!(!vp.follow_output());
    }
}
