//! Theme hot-reloading: watches theme files for changes.

use std::path::Path;

use tracing::{debug, warn};
use wok_watcher::{PathWatcher, WatchError};

use crate::theme::Theme;
use crate::theme_loader::load_theme;

/// Watches a theme file for changes and reloads on modification.
pub struct ThemeWatcher {
    inner: PathWatcher,
}

impl ThemeWatcher {
    /// Create a new theme watcher for the given theme file.
    ///
    /// # Errors
    ///
    /// Returns an error if the file watcher cannot be created.
    pub fn new(theme_path: &Path) -> Result<Self, WatchError> {
        let inner = PathWatcher::new(theme_path)?;
        debug!("watching theme file: {}", theme_path.display());
        Ok(Self { inner })
    }

    /// Non-blocking poll for theme changes.
    ///
    /// Returns `Some(theme)` if the file was modified and the new theme
    /// loaded successfully. Returns `None` otherwise.
    pub fn poll(&mut self) -> Option<Theme> {
        if !self.inner.poll() {
            return None;
        }
        match load_theme(self.inner.path()) {
            Ok(theme) => {
                debug!("theme reloaded successfully");
                Some(theme)
            }
            Err(e) => {
                warn!("failed to reload theme: {e}");
                None
            }
        }
    }
}
