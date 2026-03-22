//! Session persistence for workspace tabs and panes.

use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use walk_ui::splits::{SplitDirection, SplitNode};

use crate::workspace::PaneId;

/// Errors from session operations.
#[derive(Debug, Error)]
pub enum SessionError {
    /// Failed to read or write a session file.
    #[error("session I/O error: {0}")]
    Io(#[from] std::io::Error),
    /// Failed to encode or decode JSON session state.
    #[error("session parse error: {0}")]
    Parse(#[from] serde_json::Error),
}

/// Saved pane metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaneState {
    /// Pane identifier.
    pub id: PaneId,
    /// Working directory.
    pub cwd: PathBuf,
    /// Shell type string.
    pub shell: String,
    /// Pane title.
    pub title: String,
    /// Draft input buffer for the pane.
    pub input_draft: String,
    /// Active search query for the pane.
    pub search_query: String,
}

/// Saved split tree node.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum SplitNodeState {
    /// A leaf node containing a pane id.
    Leaf {
        /// Pane identifier.
        pane_id: PaneId,
    },
    /// A split node containing two children.
    Split {
        /// Split direction.
        direction: String,
        /// Split ratio.
        ratio: f32,
        /// First child.
        first: Box<SplitNodeState>,
        /// Second child.
        second: Box<SplitNodeState>,
    },
}

/// Saved top-level tab state.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceTabState {
    /// Tab identifier.
    pub id: u64,
    /// Tab title.
    pub title: String,
    /// Focused pane in the tab.
    pub focused_pane: PaneId,
    /// Split tree for the tab.
    pub split_tree: SplitNodeState,
}

/// Complete saved workspace session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceSessionState {
    /// Saved tabs.
    pub tabs: Vec<WorkspaceTabState>,
    /// Saved panes.
    pub panes: Vec<PaneState>,
    /// Active tab index.
    pub active_tab: usize,
    /// Window size.
    pub window_size: (u32, u32),
    /// Window position.
    pub window_position: (i32, i32),
}

/// Save a session state to a JSON file.
pub fn save_session(state: &WorkspaceSessionState, path: &Path) -> Result<(), SessionError> {
    let json = serde_json::to_string_pretty(state)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, json)?;
    Ok(())
}

/// Load a session state from a JSON file.
pub fn load_session(path: &Path) -> Result<WorkspaceSessionState, SessionError> {
    let content = std::fs::read_to_string(path)?;
    Ok(serde_json::from_str(&content)?)
}

/// Default autosave session file path.
pub fn default_session_path() -> PathBuf {
    crate::config::WalkConfig::config_dir().join("session.json")
}

/// Path for a named session snapshot.
pub fn named_session_path(name: &str) -> PathBuf {
    crate::config::WalkConfig::config_dir()
        .join("sessions")
        .join(format!("{name}.json"))
}

/// Convert a runtime split tree into a serializable shape.
pub fn split_node_to_state(node: &SplitNode) -> SplitNodeState {
    match node {
        SplitNode::Leaf { tab_id } => SplitNodeState::Leaf { pane_id: *tab_id },
        SplitNode::Split {
            direction,
            ratio,
            first,
            second,
        } => SplitNodeState::Split {
            direction: match direction {
                SplitDirection::Horizontal => "horizontal".to_string(),
                SplitDirection::Vertical => "vertical".to_string(),
            },
            ratio: *ratio,
            first: Box::new(split_node_to_state(first)),
            second: Box::new(split_node_to_state(second)),
        },
    }
}

/// Convert a serialized split tree back into a runtime shape.
pub fn split_node_from_state(node: &SplitNodeState) -> SplitNode {
    match node {
        SplitNodeState::Leaf { pane_id } => SplitNode::Leaf { tab_id: *pane_id },
        SplitNodeState::Split {
            direction,
            ratio,
            first,
            second,
        } => SplitNode::Split {
            direction: if direction == "horizontal" {
                SplitDirection::Horizontal
            } else {
                SplitDirection::Vertical
            },
            ratio: *ratio,
            first: Box::new(split_node_from_state(first)),
            second: Box::new(split_node_from_state(second)),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_split_node_round_trip() {
        let node = SplitNode::Split {
            direction: SplitDirection::Horizontal,
            ratio: 0.6,
            first: Box::new(SplitNode::Leaf { tab_id: 1 }),
            second: Box::new(SplitNode::Leaf { tab_id: 2 }),
        };
        let state = split_node_to_state(&node);
        let restored = split_node_from_state(&state);

        match restored {
            SplitNode::Split {
                direction,
                ratio,
                ..
            } => {
                assert_eq!(direction, SplitDirection::Horizontal);
                assert!((ratio - 0.6).abs() < f32::EPSILON);
            }
            SplitNode::Leaf { .. } => panic!("expected split node"),
        }
    }

    #[test]
    fn test_named_session_path_uses_sessions_dir() {
        let path = named_session_path("demo");
        assert!(path.to_string_lossy().contains("sessions"));
    }
}
