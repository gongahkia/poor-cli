//! Font zoom: runtime font size adjustment.

/// Manages font zoom level.
pub struct ZoomManager {
    /// Base font size from config.
    base_size: f32,
    /// Current font size.
    current_size: f32,
    /// Minimum font size.
    min_size: f32,
    /// Maximum font size.
    max_size: f32,
    /// Step size for zoom in/out.
    step: f32,
}

impl ZoomManager {
    /// Create a new zoom manager with the given base font size.
    pub fn new(base: f32) -> Self {
        Self {
            base_size: base,
            current_size: base,
            min_size: 8.0,
            max_size: 32.0,
            step: 1.0,
        }
    }

    /// Increase font size by one step.
    pub fn zoom_in(&mut self) {
        self.current_size = (self.current_size + self.step).min(self.max_size);
    }

    /// Decrease font size by one step.
    pub fn zoom_out(&mut self) {
        self.current_size = (self.current_size - self.step).max(self.min_size);
    }

    /// Reset to base font size.
    pub fn zoom_reset(&mut self) {
        self.current_size = self.base_size;
    }

    /// Get the current font size.
    pub fn current_size(&self) -> f32 {
        self.current_size
    }

    /// Check if zoom has changed from base.
    pub fn is_zoomed(&self) -> bool {
        (self.current_size - self.base_size).abs() > f32::EPSILON
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zoom_in() {
        let mut zm = ZoomManager::new(14.0);
        zm.zoom_in();
        assert!((zm.current_size() - 15.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_zoom_in_clamps_to_max() {
        let mut zm = ZoomManager::new(32.0);
        zm.zoom_in();
        assert!((zm.current_size() - 32.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_zoom_out_clamps_to_min() {
        let mut zm = ZoomManager::new(8.0);
        zm.zoom_out();
        assert!((zm.current_size() - 8.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_zoom_reset() {
        let mut zm = ZoomManager::new(14.0);
        zm.zoom_in();
        zm.zoom_in();
        zm.zoom_reset();
        assert!((zm.current_size() - 14.0).abs() < f32::EPSILON);
    }
}
