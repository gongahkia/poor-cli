//! Background image and transparency support.

use std::path::Path;

use thiserror::Error;

/// Errors from background image operations.
#[derive(Debug, Error)]
pub enum BackgroundError {
    /// Failed to load the image file.
    #[error("failed to load image: {0}")]
    ImageLoad(String),
    /// Image format not supported.
    #[error("unsupported image format")]
    UnsupportedFormat,
}

/// Background image data loaded into CPU memory.
pub struct BackgroundImage {
    /// RGBA pixel data.
    pub pixels: Vec<u8>,
    /// Image width.
    pub width: u32,
    /// Image height.
    pub height: u32,
}

/// Background renderer state.
pub struct BackgroundRenderer {
    /// Loaded background image (if any).
    pub image: Option<BackgroundImage>,
}

impl BackgroundRenderer {
    /// Create a new background renderer.
    pub fn new() -> Self {
        Self { image: None }
    }

    /// Load an image from the filesystem.
    ///
    /// # Errors
    ///
    /// Returns [`BackgroundError`] if the image cannot be loaded.
    pub fn load_image(&mut self, path: &Path) -> Result<(), BackgroundError> {
        let img = image::open(path)
            .map_err(|e| BackgroundError::ImageLoad(e.to_string()))?;
        let rgba = img.to_rgba8();
        let (width, height) = rgba.dimensions();

        self.image = Some(BackgroundImage {
            pixels: rgba.into_raw(),
            width,
            height,
        });

        Ok(())
    }

    /// Check if a background image is loaded.
    pub fn has_image(&self) -> bool {
        self.image.is_some()
    }

    /// Clear the loaded image.
    pub fn clear(&mut self) {
        self.image = None;
    }
}

impl Default for BackgroundRenderer {
    fn default() -> Self {
        Self::new()
    }
}
