//! DPI/scale-factor awareness for crisp rendering on HiDPI displays.

use winit::dpi::{LogicalSize, PhysicalSize};

/// Holds scale factor and size information for coordinate conversion.
#[derive(Debug, Clone, Copy)]
pub struct ScaleContext {
    /// The display scale factor (e.g., 2.0 for Retina).
    pub scale_factor: f64,
    /// Physical pixel size of the window.
    pub physical_size: PhysicalSize<u32>,
    /// Logical point size of the window.
    pub logical_size: LogicalSize<f64>,
}

impl ScaleContext {
    /// Create a `ScaleContext` from a scale factor and physical size.
    pub fn new(scale_factor: f64, physical_size: PhysicalSize<u32>) -> Self {
        let logical_size = LogicalSize::new(
            f64::from(physical_size.width) / scale_factor,
            f64::from(physical_size.height) / scale_factor,
        );
        Self {
            scale_factor,
            physical_size,
            logical_size,
        }
    }

    /// Convert logical coordinates to physical pixels.
    pub fn logical_to_physical(&self, x: f64, y: f64) -> (u32, u32) {
        (
            (x * self.scale_factor) as u32,
            (y * self.scale_factor) as u32,
        )
    }

    /// Convert physical pixels to logical coordinates.
    pub fn physical_to_logical(&self, x: u32, y: u32) -> (f64, f64) {
        (
            f64::from(x) / self.scale_factor,
            f64::from(y) / self.scale_factor,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_logical_to_physical_at_2x() {
        let ctx = ScaleContext::new(2.0, PhysicalSize::new(2400, 1600));
        assert_eq!(ctx.logical_to_physical(100.0, 50.0), (200, 100));
    }

    #[test]
    fn test_physical_to_logical_at_2x() {
        let ctx = ScaleContext::new(2.0, PhysicalSize::new(2400, 1600));
        let (x, y) = ctx.physical_to_logical(200, 100);
        assert!((x - 100.0).abs() < f64::EPSILON);
        assert!((y - 50.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_logical_size_computed_correctly() {
        let ctx = ScaleContext::new(2.0, PhysicalSize::new(2400, 1600));
        assert!((ctx.logical_size.width - 1200.0).abs() < f64::EPSILON);
        assert!((ctx.logical_size.height - 800.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_1x_scale_identity() {
        let ctx = ScaleContext::new(1.0, PhysicalSize::new(1200, 800));
        assert_eq!(ctx.logical_to_physical(100.0, 50.0), (100, 50));
    }
}
