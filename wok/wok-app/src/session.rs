//! Session persistence for workspace tabs and panes.

use std::path::{Path, PathBuf};
use std::time::{Duration, Instant};
use std::{io::Write, time::SystemTime};

use serde::{Deserialize, Serialize};
use thiserror::Error;
use wok_blocks::block::Block;
use wok_input::history::HistoryEntry;
use wok_ui::splits::{SplitDirection, SplitNode};

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
    /// Restored pane-local command history.
    #[serde(default)]
    pub command_history: Vec<HistoryEntryState>,
    /// Persisted plain-text terminal rows.
    #[serde(default)]
    pub buffer_lines: Vec<String>,
    /// Persisted viewport scroll offset.
    #[serde(default)]
    pub display_offset: usize,
    /// Whether the pane should stay pinned to live output.
    #[serde(default = "default_follow_output")]
    pub follow_output: bool,
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
    /// Whether the block is bookmarked.
    #[serde(default)]
    pub is_bookmarked: bool,
}

/// Serializable pane-local command history entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryEntryState {
    /// Command text as entered by the user.
    pub command: String,
    /// Working directory when known.
    pub cwd: Option<PathBuf>,
    /// Source pane identifier when known.
    pub source_pane_id: Option<u64>,
    /// Start timestamp in Unix milliseconds.
    pub started_at_ms: u64,
    /// Completion timestamp in Unix milliseconds when known.
    pub completed_at_ms: Option<u64>,
    /// Exit code when known.
    pub exit_code: Option<i32>,
    /// Duration in milliseconds when known.
    pub duration_ms: Option<u64>,
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
    /// Focused floating pane id when one is focused.
    #[serde(default)]
    pub focused_floating: Option<PaneId>,
    /// Split tree for the tab.
    pub split_tree: SplitNodeState,
    /// Floating panes overlaid on the split tree.
    #[serde(default)]
    pub floating_panes: Vec<FloatingPaneState>,
}

/// Saved floating pane metadata.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FloatingPaneState {
    /// Backing pane id.
    pub pane_id: PaneId,
    /// Pane rectangle in logical pixels.
    pub rect: (f32, f32, f32, f32),
    /// Z ordering for overlap.
    pub z_order: u32,
    /// Visibility state.
    pub is_visible: bool,
    /// User-facing title.
    pub title: String,
}

/// Complete saved workspace session.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct WorkspaceSessionState {
    /// Session schema version.
    #[serde(default = "default_session_schema_version")]
    pub schema_version: u32,
    /// Unix timestamp when this session was saved, in milliseconds.
    #[serde(default)]
    pub saved_at_unix_ms: u64,
    /// Wok package version that wrote this session.
    #[serde(default)]
    pub wok_version: String,
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
    /// Whether the failure trends panel is visible.
    #[serde(default)]
    pub show_failure_trends_panel: bool,
    /// Whether the workspace insights panel is visible.
    #[serde(default)]
    pub show_workspace_insights_panel: bool,
    /// Bucket size in milliseconds used by the failure trends panel.
    #[serde(default = "default_failure_trend_bucket_ms")]
    pub failure_trend_bucket_ms: u64,
}

fn default_follow_output() -> bool {
    true
}

fn default_failure_trend_bucket_ms() -> u64 {
    60 * 60 * 1000
}

fn default_session_schema_version() -> u32 {
    1
}

/// Save a session state to a JSON file.
pub fn save_session(state: &WorkspaceSessionState, path: &Path) -> Result<(), SessionError> {
    let json = serde_json::to_string_pretty(state)?;
    write_atomic(path, json.as_bytes())?;
    Ok(())
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), std::io::Error> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    let unique = SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos();
    let tmp_path = parent.join(format!(
        ".{}.tmp-{}-{unique}",
        path.file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("wok-session"),
        std::process::id()
    ));

    let persist_result = (|| -> Result<(), std::io::Error> {
        let mut file = std::fs::OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&tmp_path)?;
        file.write_all(bytes)?;
        file.sync_all()?;
        #[cfg(windows)]
        if path.exists() {
            let _ = std::fs::remove_file(path);
        }
        std::fs::rename(&tmp_path, path)?;
        #[cfg(unix)]
        {
            if let Ok(dir) = std::fs::File::open(parent) {
                let _ = dir.sync_all();
            }
        }
        Ok(())
    })();

    if persist_result.is_err() {
        let _ = std::fs::remove_file(&tmp_path);
    }
    persist_result
}

/// Load a session state from a JSON file.
pub fn load_session(path: &Path) -> Result<WorkspaceSessionState, SessionError> {
    let content = std::fs::read_to_string(path)?;
    Ok(serde_json::from_str(&content)?)
}

/// Default autosave session file path.
pub fn default_session_path() -> PathBuf {
    crate::config::WokConfig::config_dir().join("session.json")
}

/// Path for a named session snapshot.
pub fn named_session_path(name: &str) -> PathBuf {
    crate::config::WokConfig::config_dir()
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
        is_bookmarked: block.is_bookmarked,
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
        is_bookmarked: block.is_bookmarked,
        trigger_highlights: Vec::new(),
    }
}

/// Convert a runtime history entry into serializable state.
pub fn history_entry_to_state(entry: &HistoryEntry) -> HistoryEntryState {
    HistoryEntryState {
        command: entry.command.clone(),
        cwd: entry.cwd.clone(),
        source_pane_id: entry.source_pane_id,
        started_at_ms: entry.started_at_ms,
        completed_at_ms: entry.completed_at_ms,
        exit_code: entry.exit_code,
        duration_ms: entry.duration_ms,
    }
}

/// Convert serialized history back into runtime form.
pub fn history_entry_from_state(entry: &HistoryEntryState) -> HistoryEntry {
    HistoryEntry {
        command: entry.command.clone(),
        cwd: entry.cwd.clone(),
        source_pane_id: entry.source_pane_id,
        started_at_ms: entry.started_at_ms,
        completed_at_ms: entry.completed_at_ms,
        exit_code: entry.exit_code,
        duration_ms: entry.duration_ms,
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
        let path = std::env::temp_dir().join(format!("wok-session-{unique}.json"));
        let state = WorkspaceSessionState {
            schema_version: 1,
            saved_at_unix_ms: 123,
            wok_version: "test".to_string(),
            tabs: vec![WorkspaceTabState {
                id: 1,
                title: "Shell".to_string(),
                focused_pane: 7,
                focused_floating: None,
                split_tree: SplitNodeState::Leaf { pane_id: 7 },
                floating_panes: Vec::new(),
            }],
            panes: vec![PaneState {
                id: 7,
                cwd: PathBuf::from("/tmp"),
                shell: "zsh".to_string(),
                title: "demo".to_string(),
                input_draft: "echo hello".to_string(),
                search_query: "hello".to_string(),
                command_history: vec![HistoryEntryState {
                    command: "echo hello".to_string(),
                    cwd: Some(PathBuf::from("/tmp")),
                    source_pane_id: Some(7),
                    started_at_ms: 42,
                    completed_at_ms: Some(54),
                    exit_code: Some(0),
                    duration_ms: Some(12),
                }],
                buffer_lines: vec!["echo hello".to_string(), "hello".to_string()],
                display_offset: 3,
                follow_output: false,
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
                    is_bookmarked: true,
                }],
                selected_block: Some(1),
            }],
            active_tab: 0,
            window_size: (1280, 800),
            window_position: (32, 48),
            show_failure_trends_panel: true,
            show_workspace_insights_panel: true,
            failure_trend_bucket_ms: 120_000,
        };

        save_session(&state, &path).expect("session should save");
        let loaded = load_session(&path).expect("session should load");
        std::fs::remove_file(&path).ok();

        assert_eq!(loaded.tabs.len(), 1);
        assert_eq!(loaded.panes.len(), 1);
        assert_eq!(loaded.panes[0].shell, "zsh");
        assert_eq!(loaded.window_size, (1280, 800));
        assert_eq!(loaded.schema_version, 1);
        assert_eq!(loaded.saved_at_unix_ms, 123);
        assert_eq!(loaded.wok_version, "test");
        assert!(loaded.show_failure_trends_panel);
        assert!(loaded.show_workspace_insights_panel);
        assert_eq!(loaded.failure_trend_bucket_ms, 120_000);
        assert_eq!(loaded.panes[0].buffer_lines.len(), 2);
        assert_eq!(loaded.panes[0].blocks.len(), 1);
        assert_eq!(loaded.panes[0].command_history.len(), 1);
        assert!(!loaded.panes[0].follow_output);
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
            is_bookmarked: true,
            trigger_highlights: vec![wok_blocks::triggers::TriggerHighlight {
                absolute_row: 11,
                col_start: 2,
                col_end: 7,
                color: "#ff0000".to_string(),
            }],
        };

        let state = block_to_state(&runtime_block);
        let restored = block_from_state(&state);

        assert_eq!(restored.id, runtime_block.id);
        assert_eq!(restored.command_text, runtime_block.command_text);
        assert_eq!(restored.output_end_row, runtime_block.output_end_row);
        assert_eq!(restored.duration, Some(Duration::from_millis(250)));
        assert!(restored.is_bookmarked);
    }

    #[test]
    fn test_load_session_defaults_missing_bookmark_state() {
        let json = r#"{
          "tabs": [{
            "id": 1,
            "title": "Shell",
            "focused_pane": 7,
            "split_tree": { "Leaf": { "pane_id": 7 } }
          }],
          "panes": [{
            "id": 7,
            "cwd": "/tmp",
            "shell": "zsh",
            "title": "demo",
            "input_draft": "",
            "search_query": "",
            "buffer_lines": [],
            "display_offset": 0,
            "follow_output": true,
            "blocks": [{
              "id": 1,
              "prompt_text": "$",
              "command_text": "echo hello",
              "output_start_row": 0,
              "output_end_row": 1,
              "exit_code": 0,
              "duration_ms": 12,
              "is_collapsed": false,
              "scroll_offset": 0,
              "cwd": "/tmp",
              "git_branch": null,
              "git_dirty": null
            }],
            "selected_block": 1
          }],
          "active_tab": 0,
          "window_size": [1280, 800],
          "window_position": [0, 0]
        }"#;

        let loaded: WorkspaceSessionState =
            serde_json::from_str(json).expect("session should parse");

        assert!(!loaded.panes[0].blocks[0].is_bookmarked);
        assert!(!loaded.show_failure_trends_panel);
        assert!(!loaded.show_workspace_insights_panel);
        assert_eq!(loaded.schema_version, 1);
        assert_eq!(loaded.saved_at_unix_ms, 0);
        assert!(loaded.wok_version.is_empty());
        assert_eq!(
            loaded.failure_trend_bucket_ms,
            default_failure_trend_bucket_ms()
        );
    }

    #[test]
    fn test_history_entry_round_trip() {
        let entry = HistoryEntry {
            command: "cargo test".to_string(),
            cwd: Some(PathBuf::from("/repo")),
            source_pane_id: Some(9),
            started_at_ms: 100,
            completed_at_ms: Some(150),
            exit_code: Some(0),
            duration_ms: Some(50),
        };

        let state = history_entry_to_state(&entry);
        let restored = history_entry_from_state(&state);

        assert_eq!(restored, entry);
    }

    #[test]
    fn test_save_session_cleans_up_atomic_temp_file() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        let dir = std::env::temp_dir().join(format!("wok-session-atomic-{unique}"));
        std::fs::create_dir_all(&dir).expect("temp dir should exist");
        let path = dir.join("session.json");

        let state = WorkspaceSessionState {
            schema_version: 1,
            saved_at_unix_ms: 0,
            wok_version: String::new(),
            tabs: Vec::new(),
            panes: Vec::new(),
            active_tab: 0,
            window_size: (800, 600),
            window_position: (0, 0),
            show_failure_trends_panel: false,
            show_workspace_insights_panel: false,
            failure_trend_bucket_ms: default_failure_trend_bucket_ms(),
        };
        save_session(&state, &path).expect("session should save");
        assert!(path.exists(), "session file should be persisted");

        let leftovers = std::fs::read_dir(&dir)
            .expect("temp dir should be readable")
            .flatten()
            .filter_map(|entry| entry.file_name().into_string().ok())
            .filter(|name| name.contains(".session.json.tmp-"))
            .collect::<Vec<_>>();
        assert!(
            leftovers.is_empty(),
            "atomic temp file should not remain after save"
        );
        let _ = std::fs::remove_file(&path);
        let _ = std::fs::remove_dir_all(&dir);
    }
}
