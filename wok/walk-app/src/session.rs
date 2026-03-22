//! Session persistence for workspace tabs and panes.

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use walk_blocks::block::Block;
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
    /// Persisted plain-text terminal rows.
    #[serde(default)]
    pub buffer_lines: Vec<String>,
    /// Persisted viewport scroll offset.
    #[serde(default)]
    pub display_offset: usize,
    /// Persisted block timeline.
    #[serde(default)]
    pub blocks: Vec<BlockState>,
    /// Persisted selected block.
    #[serde(default)]
    pub selected_block: Option<u64>,
}

/// Serializable block state used for session restore.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BlockState {
    /// Unique block identifier.
    pub id: u64,
    /// Prompt text displayed before the command.
    pub prompt_text: String,
    /// Command text submitted by the user.
    pub command_text: String,
    /// First output row for the block.
    pub output_start_row: usize,
    /// Last output row for the block.
    pub output_end_row: usize,
    /// Exit code if the command completed.
    pub exit_code: Option<i32>,
    /// Execution duration in milliseconds when known.
    pub duration_ms: Option<u64>,
    /// Whether the block is collapsed.
    pub is_collapsed: bool,
    /// Scroll offset within the block.
    pub scroll_offset: usize,
    /// Working directory captured for the block.
    pub cwd: PathBuf,
    /// Git branch metadata when available.
    pub git_branch: Option<String>,
    /// Dirty flag metadata when available.
    pub git_dirty: Option<bool>,
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

/// Convert a runtime block into serializable session state.
pub fn block_to_state(block: &Block) -> BlockState {
    BlockState {
        id: block.id,
        prompt_text: block.prompt_text.clone(),
        command_text: block.command_text.clone(),
        output_start_row: block.output_start_row,
        output_end_row: block.output_end_row,
        exit_code: block.exit_code,
        duration_ms: block.duration.map(|duration| duration.as_millis() as u64),
        is_collapsed: block.is_collapsed,
        scroll_offset: block.scroll_offset,
        cwd: block.cwd.clone(),
        git_branch: block.git_branch.clone(),
        git_dirty: block.git_dirty,
    }
}

/// Convert a serialized block back into runtime state.
pub fn block_from_state(block: &BlockState) -> Block {
    let duration = block.duration_ms.map(Duration::from_millis);
    let start_time = Instant::now();
    let end_time = duration.and_then(|duration| start_time.checked_add(duration));

    Block {
        id: block.id,
        prompt_text: block.prompt_text.clone(),
        command_text: block.command_text.clone(),
        output_start_row: block.output_start_row,
        output_end_row: block.output_end_row,
        exit_code: block.exit_code,
        start_time,
        end_time,
        duration,
        is_collapsed: block.is_collapsed,
        scroll_offset: block.scroll_offset,
        cwd: block.cwd.clone(),
        git_branch: block.git_branch.clone(),
        git_dirty: block.git_dirty,
    }
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
    use std::time::{SystemTime, UNIX_EPOCH};

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
                direction, ratio, ..
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

    #[test]
    fn test_save_and_load_session_round_trip() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("walk-session-{unique}.json"));
        let state = WorkspaceSessionState {
            tabs: vec![WorkspaceTabState {
                id: 1,
                title: "Shell".to_string(),
                focused_pane: 7,
                split_tree: SplitNodeState::Leaf { pane_id: 7 },
            }],
            panes: vec![PaneState {
                id: 7,
                cwd: PathBuf::from("/tmp"),
                shell: "zsh".to_string(),
                title: "demo".to_string(),
                input_draft: "echo hello".to_string(),
                search_query: "hello".to_string(),
                buffer_lines: vec!["echo hello".to_string(), "hello".to_string()],
                display_offset: 3,
                blocks: vec![BlockState {
                    id: 1,
                    prompt_text: "$".to_string(),
                    command_text: "echo hello".to_string(),
                    output_start_row: 0,
                    output_end_row: 1,
                    exit_code: Some(0),
                    duration_ms: Some(12),
                    is_collapsed: false,
                    scroll_offset: 0,
                    cwd: PathBuf::from("/tmp"),
                    git_branch: Some("main".to_string()),
                    git_dirty: Some(false),
                }],
                selected_block: Some(1),
            }],
            active_tab: 0,
            window_size: (1280, 800),
            window_position: (32, 48),
        };

        save_session(&state, &path).expect("session should save");
        let loaded = load_session(&path).expect("session should load");
        std::fs::remove_file(&path).ok();

        assert_eq!(loaded.tabs.len(), 1);
        assert_eq!(loaded.panes.len(), 1);
        assert_eq!(loaded.panes[0].shell, "zsh");
        assert_eq!(loaded.window_size, (1280, 800));
        assert_eq!(loaded.panes[0].buffer_lines.len(), 2);
        assert_eq!(loaded.panes[0].blocks.len(), 1);
    }

    #[test]
    fn test_block_round_trip() {
        let runtime_block = Block {
            id: 4,
            prompt_text: "$".to_string(),
            command_text: "cargo test".to_string(),
            output_start_row: 10,
            output_end_row: 14,
            exit_code: Some(0),
            start_time: Instant::now(),
            end_time: None,
            duration: Some(Duration::from_millis(250)),
            is_collapsed: true,
            scroll_offset: 2,
            cwd: PathBuf::from("/repo"),
            git_branch: Some("main".to_string()),
            git_dirty: Some(true),
        };

        let state = block_to_state(&runtime_block);
        let restored = block_from_state(&state);

        assert_eq!(restored.id, runtime_block.id);
        assert_eq!(restored.command_text, runtime_block.command_text);
        assert_eq!(restored.output_end_row, runtime_block.output_end_row);
        assert_eq!(restored.duration, Some(Duration::from_millis(250)));
    }
}
