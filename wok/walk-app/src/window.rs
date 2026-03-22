//! Window management: creates and configures the Walk application window.

use thiserror::Error;
use winit::dpi::{LogicalSize, PhysicalSize};
use winit::window::Window;

/// Errors that can occur during platform/window operations.
#[derive(Debug, Error)]
pub enum PlatformError {
    /// Failed to create the application window.
    #[error("failed to create window: {0}")]
    WindowCreation(String),

    /// Failed to initialize the event loop.
    #[error("failed to create event loop: {0}")]
    EventLoopCreation(String),
}

/// Configuration for creating a Walk window.
#[derive(Debug, Clone)]
pub struct WindowConfig {
    /// Window title.
    pub title: String,
    /// Initial logical width.
    pub width: u32,
    /// Initial logical height.
    pub height: u32,
}

impl Default for WindowConfig {
    fn default() -> Self {
        Self {
            title: "Walk".to_string(),
            width: 1_200,
            height: 800,
        }
    }
}

/// Wraps a winit window with Walk-specific state.
pub struct WalkWindow {
    /// The underlying winit window.
    pub window: Window,
    /// Window title.
    pub title: String,
    /// Current physical size.
    pub size: PhysicalSize<u32>,
    /// Current scale factor.
    pub scale_factor: f64,
    /// Whether the window is focused.
    pub is_focused: bool,
}

impl WalkWindow {
    /// Create a new Walk window from a winit window.
    ///
    /// # Errors
    ///
    /// Returns [`PlatformError::WindowCreation`] if the window cannot be created.
    pub fn from_winit(window: Window) -> Self {
        let size = window.inner_size();
        let scale_factor = window.scale_factor();
        let title = "Walk".to_string();
        Self {
            window,
            title,
            size,
            scale_factor,
            is_focused: true,
        }
    }

    /// Get the window attributes for creating a new window.
    pub fn default_attributes(config: &WindowConfig) -> winit::window::WindowAttributes {
        let logical_size = LogicalSize::new(config.width as f64, config.height as f64);
        let min_size = LogicalSize::new(400.0, 300.0);

        winit::window::WindowAttributes::default()
            .with_title(&config.title)
            .with_inner_size(logical_size)
            .with_min_inner_size(min_size)
            .with_resizable(true)
    }
}
