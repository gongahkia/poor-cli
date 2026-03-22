//! Clipboard integration: system clipboard access for copy/paste.

use thiserror::Error;

/// Errors from clipboard operations.
#[derive(Debug, Error)]
pub enum ClipboardError {
    /// Failed to access the system clipboard.
    #[error("clipboard error: {0}")]
    Access(String),
}

/// Manages system clipboard access.
pub struct ClipboardManager {
    clipboard: Option<arboard::Clipboard>,
}

impl ClipboardManager {
    /// Create a new clipboard manager.
    pub fn new() -> Self {
        let clipboard = arboard::Clipboard::new().ok();
        Self { clipboard }
    }

    /// Copy text to the system clipboard.
    ///
    /// # Errors
    ///
    /// Returns [`ClipboardError::Access`] if the clipboard cannot be written to.
    pub fn copy(&mut self, text: &str) -> Result<(), ClipboardError> {
        if let Some(ref mut cb) = self.clipboard {
            cb.set_text(text)
                .map_err(|e| ClipboardError::Access(e.to_string()))
        } else {
            Err(ClipboardError::Access("clipboard not available".to_string()))
        }
    }

    /// Get text from the system clipboard.
    ///
    /// # Errors
    ///
    /// Returns [`ClipboardError::Access`] if the clipboard cannot be read.
    pub fn paste(&mut self) -> Result<String, ClipboardError> {
        if let Some(ref mut cb) = self.clipboard {
            cb.get_text()
                .map_err(|e| ClipboardError::Access(e.to_string()))
        } else {
            Err(ClipboardError::Access("clipboard not available".to_string()))
        }
    }
}

impl Default for ClipboardManager {
    fn default() -> Self {
        Self::new()
    }
}
