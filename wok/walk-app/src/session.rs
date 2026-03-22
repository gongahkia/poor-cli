//! Session persistence: save and restore terminal sessions across app restarts.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;

/// Errors from session operations.
#[derive(Debug, Error)]
pub enum SessionError {
    /// Failed to read/write session file.
    #[error("session I/O error: {0}")]
    Io(#[from] std::io::Error),
    /// Failed to parse session data.
    #[error("session parse error: {0}")]
    Parse(#[from] serde_json::Error),
}

/// Saved tab state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TabState {
    /// Working directory.
    pub cwd: PathBuf,
    /// Shell type name.
    pub shell: String,
    /// Scrollback text content.
    pub scrollback_text: String,
    /// Tab title.
    pub title: String,
}

/// Saved split tree node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SplitNodeState {
    /// A leaf node with a tab index.
    Leaf {
        /// Tab index.
        tab_index: usize,
    },
    /// A split node.
    Split {
        /// Split direction (horizontal or vertical).
        direction: String,
        /// Split ratio.
        ratio: f32,
        /// First child.
        first: Box<SplitNodeState>,
        /// Second child.
        second: Box<SplitNodeState>,
    },
}

/// Complete session state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionState {
    /// Saved tabs.
    pub tabs: Vec<TabState>,
    /// Split tree layout.
    pub split_tree: SplitNodeState,
    /// Index of the active tab.
    pub active_tab: usize,
    /// Window size.
    pub window_size: (u32, u32),
    /// Window position.
    pub window_position: (i32, i32),
}

/// Save a session state to file.
///
/// # Errors
///
/// Returns [`SessionError`] if the file cannot be written.
pub fn save_session(state: &SessionState, path: &Path) -> Result<(), SessionError> {
    let json = serde_json::to_string_pretty(state)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, json)?;
    Ok(())
}

/// Load a session state from file.
///
/// # Errors
///
/// Returns [`SessionError`] if the file cannot be read or parsed.
pub fn load_session(path: &Path) -> Result<SessionState, SessionError> {
    let content = std::fs::read_to_string(path)?;
    let state: SessionState = serde_json::from_str(&content)?;
    Ok(state)
}

/// Default session file path.
pub fn default_session_path() -> PathBuf {
    crate::config::WalkConfig::config_dir().join("session.json")
}
