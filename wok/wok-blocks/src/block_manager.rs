//! Block manager: state machine that turns semantic events into blocks.

use std::path::PathBuf;
use std::time::Instant;

use wok_git::repo;
use wok_terminal::terminal::{SemanticEvent, Terminal};

use crate::block::{Block, BlockBuildState, OutputLineEvent};
use crate::block_id::{BlockId, BlockIdGenerator};
use crate::block_index::BlockIndex;
use crate::scrollback_mirror::{LineSnapshot, ScrollbackMirror};

/// Manages all blocks in a terminal session.
pub struct BlockManager {
    /// All completed and in-progress blocks.
    pub blocks: Vec<Block>,
    /// Currently selected/active block.
    pub active_block: Option<BlockId>,
    /// Id minter.
    ids: BlockIdGenerator,
    /// id → position lookup, kept in sync with `blocks`.
    index: BlockIndex,
    /// Command text submitted for the next block.
    pending_command_text: Option<String>,
    /// Latest current working directory reported by the terminal.
    current_cwd: PathBuf,
    /// Current build state.
    pub state: BlockBuildState,
    /// Parallel sumtree mirror for O(log n) row→boundary queries (gated by
    /// `wok_features::FeatureFlag::SumTreeScrollback`).
    pub mirror: ScrollbackMirror,
}

impl BlockManager {
    /// Create a new empty block manager.
    pub fn new() -> Self {
        Self {
            blocks: Vec::new(),
            active_block: None,
            ids: BlockIdGenerator::new(),
            index: BlockIndex::new(),
            pending_command_text: None,
            current_cwd: PathBuf::new(),
            state: BlockBuildState::WaitingForPrompt,
            mirror: ScrollbackMirror::new(),
        }
    }

    /// Handle a semantic event, potentially creating or completing a block.
    pub fn handle_event(&mut self, event: &SemanticEvent) {
        match event {
            SemanticEvent::PromptStart { row } => {
                self.pending_command_text = None;
                self.state = BlockBuildState::InPrompt { start_row: *row };
            }
            SemanticEvent::CommandStart { .. } => {
                if !matches!(self.state, BlockBuildState::InOutput { .. }) {
                    self.state = BlockBuildState::InCommand {
                        prompt_text: String::new(),
                    };
                }
            }
            SemanticEvent::CommandText { text, .. } => {
                self.pending_command_text = Some(text.clone());

                if let Some(block) = self.blocks.last_mut() {
                    if block.exit_code.is_none() {
                        block.command_text.clone_from(text);
                    }
                }
            }
            SemanticEvent::OutputStart { row } => {
                let prompt_text = if let BlockBuildState::InCommand { prompt_text } = &self.state {
                    Some(prompt_text.clone())
                } else if self.pending_command_text.is_some() {
                    Some(String::new())
                } else {
                    None
                };

                if let Some(prompt_text) = prompt_text {
                    let id = self.ids.next_id();

                    let block = Block {
                        id,
                        prompt_text,
                        command_text: self.pending_command_text.take().unwrap_or_default(),
                        output_start_row: *row,
                        output_end_row: *row,
                        exit_code: None,
                        start_time: Instant::now(),
                        end_time: None,
                        duration: None,
                        is_collapsed: false,
                        scroll_offset: 0,
                        cwd: self.current_cwd.clone(),
                        git_branch: repo::detect_branch(&self.current_cwd),
                        git_dirty: None,
                        is_bookmarked: false,
                        trigger_highlights: Vec::new(),
                    };
                    let pos = self.blocks.len();
                    let row_for_mirror = block.output_start_row;
                    self.blocks.push(block);
                    self.index.push(id, pos);
                    self.active_block = Some(id);
                    self.state = BlockBuildState::InOutput { block_id: id };
                    // sumtree mirror: record this block's first row as a
                    // boundary for O(log n) navigation.
                    self.mirror.push(LineSnapshot {
                        absolute_row: row_for_mirror,
                        block_id: Some(id),
                        visible: true,
                        is_boundary: true,
                    });
                }
            }
            SemanticEvent::CommandEnd { row, exit_code } => {
                if let BlockBuildState::InOutput { block_id } = &self.state {
                    if let Some(pos) = self.index.position(*block_id) {
                        let block = &mut self.blocks[pos];
                        block.output_end_row = *row;
                        block.exit_code = *exit_code;
                        block.end_time = Some(Instant::now());
                        block.duration = block.end_time.map(|end| end - block.start_time);
                    }
                    self.state = BlockBuildState::WaitingForPrompt;
                }
            }
            SemanticEvent::CwdChanged(path) => {
                self.current_cwd.clone_from(path);
                if let BlockBuildState::InOutput { block_id } = &self.state {
                    if let Some(pos) = self.index.position(*block_id) {
                        self.blocks[pos].cwd.clone_from(path);
                        self.blocks[pos].git_branch = repo::detect_branch(path);
                    }
                }
            }
            SemanticEvent::TitleChanged(_) => {}
            SemanticEvent::InlineImage(_) => {}
        }
    }

    /// Set the command text on the most recent in-progress block.
    pub fn set_command_text(&mut self, text: &str) {
        self.pending_command_text = Some(text.to_string());

        if let Some(block) = self.blocks.last_mut() {
            if block.exit_code.is_none() {
                block.command_text = text.to_string();
            }
        }
    }

    /// Get a block by ID.
    pub fn get_block(&self, id: BlockId) -> Option<&Block> {
        self.index.position(id).map(|pos| &self.blocks[pos])
    }

    /// Get a mutable block by ID.
    pub fn get_block_mut(&mut self, id: BlockId) -> Option<&mut Block> {
        self.index.position(id).map(|pos| &mut self.blocks[pos])
    }

    /// Return blocks visible in the current viewport.
    pub fn visible_blocks(&self) -> &[Block] {
        &self.blocks
    }

    /// Return the number of blocks.
    pub fn len(&self) -> usize {
        self.blocks.len()
    }

    /// Return whether there are no blocks.
    pub fn is_empty(&self) -> bool {
        self.blocks.is_empty()
    }

    /// Restore a previously serialized block timeline.
    pub fn restore_blocks(&mut self, blocks: Vec<Block>, active_block: Option<BlockId>) {
        let highest = blocks.iter().map(|block| block.id).max().unwrap_or(0);
        self.ids = BlockIdGenerator::after(highest);
        self.active_block = active_block;
        self.blocks = blocks;
        self.index.rebuild(&self.blocks);
        self.pending_command_text = None;
        self.current_cwd = self
            .blocks
            .last()
            .map(|block| block.cwd.clone())
            .unwrap_or_default();
        self.state = BlockBuildState::WaitingForPrompt;
        // rebuild mirror to match restored timeline.
        self.mirror = ScrollbackMirror::new();
        for block in &self.blocks {
            self.mirror.push(LineSnapshot {
                absolute_row: block.output_start_row,
                block_id: Some(block.id),
                visible: true,
                is_boundary: true,
            });
        }
    }

    /// Return the selected block when known, otherwise the latest block.
    pub fn selected_or_latest_block(&self) -> Option<&Block> {
        self.active_block
            .and_then(|block_id| self.get_block(block_id))
            .or_else(|| self.blocks.last())
    }

    /// Toggle the bookmark state for the targeted block.
    pub fn toggle_bookmark(&mut self, block_id: Option<BlockId>) -> Option<bool> {
        let block_id = block_id.or(self.selected_or_latest_block().map(|block| block.id))?;
        let block = self.get_block_mut(block_id)?;
        block.is_bookmarked = !block.is_bookmarked;
        Some(block.is_bookmarked)
    }

    /// Return the currently active output block id while command output is streaming.
    pub fn active_output_block_id(&self) -> Option<BlockId> {
        match self.state {
            BlockBuildState::InOutput { block_id } => Some(block_id),
            _ => None,
        }
    }

    /// Build output-line events for one block across an absolute row range.
    pub fn output_line_events_for_range(
        &self,
        terminal: &Terminal,
        pane_id: u64,
        block_id: BlockId,
        row_start: usize,
        row_end: usize,
    ) -> Vec<OutputLineEvent> {
        let Some(block) = self.get_block(block_id) else {
            return Vec::new();
        };
        if row_start > row_end {
            return Vec::new();
        }

        (row_start..=row_end)
            .map(|absolute_row| OutputLineEvent {
                pane_id,
                block_id,
                line_number: absolute_row.saturating_sub(block.output_start_row),
                text: terminal.state.row_text(absolute_row),
            })
            .collect()
    }

    /// Return the next bookmarked block id, wrapping when needed.
    pub fn next_bookmark(&self, current_block_id: Option<BlockId>) -> Option<BlockId> {
        let bookmarks = self
            .blocks
            .iter()
            .filter(|block| block.is_bookmarked)
            .map(|block| block.id)
            .collect::<Vec<_>>();
        if bookmarks.is_empty() {
            return None;
        }

        let current_index = current_block_id.and_then(|block_id| {
            bookmarks
                .iter()
                .position(|candidate_id| *candidate_id == block_id)
        });
        match current_index {
            Some(index) => Some(bookmarks[(index + 1) % bookmarks.len()]),
            None => bookmarks.first().copied(),
        }
    }

    /// Return the previous bookmarked block id, wrapping when needed.
    pub fn prev_bookmark(&self, current_block_id: Option<BlockId>) -> Option<BlockId> {
        let bookmarks = self
            .blocks
            .iter()
            .filter(|block| block.is_bookmarked)
            .map(|block| block.id)
            .collect::<Vec<_>>();
        if bookmarks.is_empty() {
            return None;
        }

        let current_index = current_block_id.and_then(|block_id| {
            bookmarks
                .iter()
                .position(|candidate_id| *candidate_id == block_id)
        });
        match current_index {
            Some(0) => bookmarks.last().copied(),
            Some(index) => Some(bookmarks[index - 1]),
            None => bookmarks.last().copied(),
        }
    }

    /// Return the next failed block id, wrapping when needed.
    pub fn next_failed(&self, current_block_id: Option<BlockId>) -> Option<BlockId> {
        let failed = self
            .blocks
            .iter()
            .filter(|block| block.exit_code.is_some_and(|code| code != 0))
            .map(|block| block.id)
            .collect::<Vec<_>>();
        if failed.is_empty() {
            return None;
        }

        let current_index = current_block_id.and_then(|block_id| {
            failed
                .iter()
                .position(|candidate_id| *candidate_id == block_id)
        });
        match current_index {
            Some(index) => Some(failed[(index + 1) % failed.len()]),
            None => failed.first().copied(),
        }
    }

    /// Return the previous failed block id, wrapping when needed.
    pub fn prev_failed(&self, current_block_id: Option<BlockId>) -> Option<BlockId> {
        let failed = self
            .blocks
            .iter()
            .filter(|block| block.exit_code.is_some_and(|code| code != 0))
            .map(|block| block.id)
            .collect::<Vec<_>>();
        if failed.is_empty() {
            return None;
        }

        let current_index = current_block_id.and_then(|block_id| {
            failed
                .iter()
                .position(|candidate_id| *candidate_id == block_id)
        });
        match current_index {
            Some(0) => failed.last().copied(),
            Some(index) => Some(failed[index - 1]),
            None => failed.last().copied(),
        }
    }
}

impl Default for BlockManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};
    use wok_terminal::terminal::SemanticEvent;

    fn temp_repo(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock should be after unix epoch")
            .as_nanos();
        let path = std::env::temp_dir().join(format!("wok-blocks-{name}-{stamp}"));
        fs::create_dir_all(path.join(".git")).expect("repo directory should be created");
        fs::write(path.join(".git").join("HEAD"), "ref: refs/heads/main\n")
            .expect("HEAD should be written");
        path
    }

    #[test]
    fn test_single_command_block() {
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::PromptStart { row: 0 });
        mgr.handle_event(&SemanticEvent::CommandStart { row: 1 });
        mgr.handle_event(&SemanticEvent::CommandText {
            row: 1,
            text: "echo hello".to_string(),
        });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });
        mgr.handle_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        assert_eq!(mgr.len(), 1);
        let block = &mgr.blocks[0];
        assert_eq!(block.command_text, "echo hello");
        assert_eq!(block.exit_code, Some(0));
        assert!(block.duration.is_some());
        assert!(!block.is_bookmarked);
    }

    #[test]
    fn test_multiple_commands() {
        let mut mgr = BlockManager::new();
        for i in 0..3 {
            let base = i * 4;
            mgr.handle_event(&SemanticEvent::PromptStart { row: base });
            mgr.handle_event(&SemanticEvent::CommandStart { row: base + 1 });
            mgr.handle_event(&SemanticEvent::OutputStart { row: base + 2 });
            mgr.handle_event(&SemanticEvent::CommandEnd {
                row: base + 3,
                exit_code: Some(0),
            });
        }
        assert_eq!(mgr.len(), 3);
    }

    #[test]
    fn test_failed_command() {
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::PromptStart { row: 0 });
        mgr.handle_event(&SemanticEvent::CommandStart { row: 1 });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });
        mgr.handle_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(1),
        });

        assert_eq!(mgr.blocks[0].exit_code, Some(1));
    }

    #[test]
    fn test_toggle_bookmark_and_wrap_navigation() {
        let mut mgr = BlockManager::new();
        for i in 0..3 {
            let base = i * 4;
            mgr.handle_event(&SemanticEvent::PromptStart { row: base });
            mgr.handle_event(&SemanticEvent::CommandStart { row: base + 1 });
            mgr.handle_event(&SemanticEvent::OutputStart { row: base + 2 });
            mgr.handle_event(&SemanticEvent::CommandEnd {
                row: base + 3,
                exit_code: Some(0),
            });
        }

        assert_eq!(mgr.toggle_bookmark(Some(1)), Some(true));
        assert_eq!(mgr.toggle_bookmark(Some(3)), Some(true));
        assert_eq!(mgr.next_bookmark(Some(3)), Some(1));
        assert_eq!(mgr.prev_bookmark(Some(1)), Some(3));
    }

    #[test]
    fn test_failed_navigation_wraps() {
        let mut mgr = BlockManager::new();
        for (i, exit_code) in [Some(0), Some(1), Some(2), Some(0), Some(1)]
            .into_iter()
            .enumerate()
        {
            let base = i * 4;
            mgr.handle_event(&SemanticEvent::PromptStart { row: base });
            mgr.handle_event(&SemanticEvent::CommandStart { row: base + 1 });
            mgr.handle_event(&SemanticEvent::OutputStart { row: base + 2 });
            mgr.handle_event(&SemanticEvent::CommandEnd {
                row: base + 3,
                exit_code,
            });
        }

        assert_eq!(mgr.next_failed(Some(2)), Some(3));
        assert_eq!(mgr.next_failed(Some(5)), Some(2));
        assert_eq!(mgr.prev_failed(Some(2)), Some(5));
        assert_eq!(mgr.prev_failed(Some(5)), Some(3));
        assert_eq!(mgr.next_failed(None), Some(2));
        assert_eq!(mgr.prev_failed(None), Some(5));
    }

    #[test]
    fn test_command_text_recorded_before_output_start() {
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::PromptStart { row: 0 });
        mgr.handle_event(&SemanticEvent::CommandStart { row: 1 });
        mgr.handle_event(&SemanticEvent::CommandText {
            row: 1,
            text: "cargo test".to_string(),
        });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });
        mgr.handle_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        assert_eq!(mgr.blocks[0].command_text, "cargo test");
    }

    #[test]
    fn test_command_start_without_prompt_still_builds_block() {
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::CommandStart { row: 1 });
        mgr.handle_event(&SemanticEvent::CommandText {
            row: 1,
            text: "echo from preexec".to_string(),
        });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });
        mgr.handle_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        assert_eq!(mgr.len(), 1);
        assert_eq!(mgr.blocks[0].command_text, "echo from preexec");
        assert_eq!(mgr.blocks[0].exit_code, Some(0));
    }

    #[test]
    fn test_command_text_without_prompt_still_builds_block() {
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::CommandText {
            row: 1,
            text: "echo from marker".to_string(),
        });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });
        mgr.handle_event(&SemanticEvent::CommandEnd {
            row: 3,
            exit_code: Some(0),
        });

        assert_eq!(mgr.len(), 1);
        assert_eq!(mgr.blocks[0].command_text, "echo from marker");
    }

    #[test]
    fn test_malformed_events_no_panic() {
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::CommandEnd {
            row: 0,
            exit_code: Some(0),
        });
        assert_eq!(mgr.len(), 0);

        mgr.handle_event(&SemanticEvent::OutputStart { row: 0 });
        assert_eq!(mgr.len(), 0);
    }

    #[test]
    fn test_cwd_changed() {
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::PromptStart { row: 0 });
        mgr.handle_event(&SemanticEvent::CommandStart { row: 1 });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });
        mgr.handle_event(&SemanticEvent::CwdChanged("/tmp".into()));

        assert_eq!(mgr.blocks[0].cwd, std::path::PathBuf::from("/tmp"));
    }

    #[test]
    fn cwd_before_output_populates_block_git_branch() {
        let repo = temp_repo("branch");
        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::CwdChanged(repo.clone()));
        mgr.handle_event(&SemanticEvent::PromptStart { row: 0 });
        mgr.handle_event(&SemanticEvent::CommandStart { row: 1 });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });

        assert_eq!(mgr.blocks[0].cwd, repo);
        assert_eq!(mgr.blocks[0].git_branch.as_deref(), Some("main"));
        fs::remove_dir_all(&mgr.blocks[0].cwd).ok();
    }

    #[test]
    fn cwd_during_output_refreshes_block_git_branch() {
        let repo = temp_repo("refresh");
        let nested = repo.join("src");
        fs::create_dir_all(&nested).expect("nested directory should be created");

        let mut mgr = BlockManager::new();
        mgr.handle_event(&SemanticEvent::PromptStart { row: 0 });
        mgr.handle_event(&SemanticEvent::CommandStart { row: 1 });
        mgr.handle_event(&SemanticEvent::OutputStart { row: 2 });
        mgr.handle_event(&SemanticEvent::CwdChanged(nested.clone()));

        assert_eq!(mgr.blocks[0].cwd, nested);
        assert_eq!(mgr.blocks[0].git_branch.as_deref(), Some("main"));
        fs::remove_dir_all(repo).ok();
    }

    #[test]
    fn test_index_lookup_after_restore() {
        let mut mgr = BlockManager::new();
        for i in 0..3 {
            let base = i * 4;
            mgr.handle_event(&SemanticEvent::PromptStart { row: base });
            mgr.handle_event(&SemanticEvent::CommandStart { row: base + 1 });
            mgr.handle_event(&SemanticEvent::OutputStart { row: base + 2 });
            mgr.handle_event(&SemanticEvent::CommandEnd {
                row: base + 3,
                exit_code: Some(0),
            });
        }
        let snapshot = mgr.blocks.clone();
        let mut other = BlockManager::new();
        other.restore_blocks(snapshot, Some(2));
        assert_eq!(other.get_block(1).unwrap().id, 1);
        assert_eq!(other.get_block(2).unwrap().id, 2);
        assert_eq!(other.get_block(3).unwrap().id, 3);
        // Next minted id resumes after highest.
        other.handle_event(&SemanticEvent::PromptStart { row: 100 });
        other.handle_event(&SemanticEvent::CommandStart { row: 101 });
        other.handle_event(&SemanticEvent::OutputStart { row: 102 });
        assert_eq!(other.blocks.last().unwrap().id, 4);
    }
}
