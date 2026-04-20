//! Theme hot-reloading: watches theme files for changes.

use std::path::{Path, PathBuf};
use std::sync::mpsc;

use notify::{Event, RecommendedWatcher, RecursiveMode, Watcher};
use tracing::{debug, warn};

use crate::theme::Theme;
use crate::theme_loader::load_theme;

/// Watches a theme file for changes and reloads on modification.
pub struct ThemeWatcher {
    _watcher: RecommendedWatcher,
    rx: mpsc::Receiver<Result<Event, notify::Error>>,
    active_path: PathBuf,
}

impl ThemeWatcher {
    /// Create a new theme watcher for the given theme file.
    ///
    /// # Errors
    ///
    /// Returns an error if the file watcher cannot be created.
    pub fn new(theme_path: &Path) -> Result<Self, notify::Error> {
        let (tx, rx) = mpsc::channel();

        let mut watcher = notify::recommended_watcher(move |res| {
            let _ = tx.send(res);
        })?;

        watcher.watch(theme_path, RecursiveMode::NonRecursive)?;
        debug!("watching theme file: {}", theme_path.display());

        Ok(Self {
            _watcher: watcher,
            rx,
            active_path: theme_path.to_path_buf(),
        })
    }

    /// Non-blocking poll for theme changes.
    ///
    /// Returns `Some(theme)` if the file was modified and the new theme
    /// loaded successfully. Returns `None` otherwise.
    pub fn poll(&self) -> Option<Theme> {
        // Drain all pending events
        let mut changed = false;
        while let Ok(Ok(event)) = self.rx.try_recv() {
            if event.kind.is_modify() {
                changed = true;
            }
        }

        if changed {
            match load_theme(&self.active_path) {
                Ok(theme) => {
                    debug!("theme reloaded successfully");
                    Some(theme)
                }
                Err(e) => {
                    warn!("failed to reload theme: {e}");
                    None
                }
            }
        } else {
            None
        }
    }
}
