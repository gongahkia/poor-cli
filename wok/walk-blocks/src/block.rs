//! Block data model: each command-output pair as a navigable unit.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use walk_terminal::terminal::SemanticEvent;

/// A single command block: prompt + command + output.
#[derive(Debug, Clone)]
pub struct Block {
    /// Unique block identifier.
    pub id: u64,
    /// The prompt text that preceded the command.
    pub prompt_text: String,
    /// The command that was executed.
    pub command_text: String,
    /// Start row of output in the terminal buffer.
    pub output_start_row: usize,
    /// End row of output in the terminal buffer.
    pub output_end_row: usize,
    /// Exit code of the command (None if still running).
    pub exit_code: Option<i32>,
    /// When the command started.
    pub start_time: Instant,
    /// When the command finished.
    pub end_time: Option<Instant>,
    /// Duration of the command execution.
    pub duration: Option<Duration>,
    /// Whether the block output is collapsed.
    pub is_collapsed: bool,
    /// Scroll offset within the block.
    pub scroll_offset: usize,
    /// Current working directory when command ran.
    pub cwd: PathBuf,
    /// Git branch when command ran (if in a repo).
    pub git_branch: Option<String>,
    /// Whether git working tree was dirty.
    pub git_dirty: Option<bool>,
}

/// State machine for building blocks from semantic events.
#[derive(Debug, Clone)]
pub enum BlockBuildState {
    /// Waiting for a prompt marker.
    WaitingForPrompt,
    /// Inside a prompt (between PromptStart and CommandStart).
    InPrompt {
        /// Row where prompt started.
        start_row: usize,
    },
    /// Inside a command (between CommandStart and OutputStart).
    InCommand {
        /// Captured prompt text.
        prompt_text: String,
    },
    /// Inside output (between OutputStart and CommandEnd).
    InOutput {
        /// ID of the block being built.
        block_id: u64,
    },
}

/// Manages all blocks in a terminal session.
pub struct BlockManager {
    /// All completed and in-progress blocks.
    pub blocks: Vec<Block>,
    /// Currently selected/active block.
    pub active_block: Option<u64>,
    /// Next block ID to assign.
    next_id: u64,
    /// Command text submitted for the next block.
    pending_command_text: Option<String>,
    /// Current build state.
    pub state: BlockBuildState,
}

impl BlockManager {
    /// Create a new empty block manager.
    pub fn new() -> Self {
        Self {
            blocks: Vec::new(),
            active_block: None,
            next_id: 1,
            pending_command_text: None,
            state: BlockBuildState::WaitingForPrompt,
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
                if let BlockBuildState::InPrompt { .. } = &self.state {
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
                if let BlockBuildState::InCommand { prompt_text } = &self.state {
                    let id = self.next_id;
                    self.next_id += 1;

                    let block = Block {
                        id,
                        prompt_text: prompt_text.clone(),
                        command_text: self.pending_command_text.take().unwrap_or_default(),
                        output_start_row: *row,
                        output_end_row: *row,
                        exit_code: None,
                        start_time: Instant::now(),
                        end_time: None,
                        duration: None,
                        is_collapsed: false,
                        scroll_offset: 0,
                        cwd: PathBuf::new(),
                        git_branch: None,
                        git_dirty: None,
                    };
                    self.blocks.push(block);
                    self.active_block = Some(id);
                    self.state = BlockBuildState::InOutput { block_id: id };
                }
            }
            SemanticEvent::CommandEnd { row, exit_code } => {
                if let BlockBuildState::InOutput { block_id } = &self.state {
                    if let Some(block) = self.blocks.iter_mut().find(|b| b.id == *block_id) {
                        block.output_end_row = *row;
                        block.exit_code = *exit_code;
                        block.end_time = Some(Instant::now());
                        block.duration = block.end_time.map(|end| end - block.start_time);
                    }
                    self.state = BlockBuildState::WaitingForPrompt;
                }
            }
            SemanticEvent::CwdChanged(path) => {
                // Update the current block's CWD if in progress
                if let BlockBuildState::InOutput { block_id } = &self.state {
                    if let Some(block) = self.blocks.iter_mut().find(|b| b.id == *block_id) {
                        block.cwd.clone_from(path);
                    }
                }
            }
            SemanticEvent::TitleChanged(_) => {}
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
    pub fn get_block(&self, id: u64) -> Option<&Block> {
        self.blocks.iter().find(|b| b.id == id)
    }

    /// Get a mutable block by ID.
    pub fn get_block_mut(&mut self, id: u64) -> Option<&mut Block> {
        self.blocks.iter_mut().find(|b| b.id == id)
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
    pub fn restore_blocks(&mut self, blocks: Vec<Block>, active_block: Option<u64>) {
        self.next_id = blocks.iter().map(|block| block.id).max().unwrap_or(0) + 1;
        self.active_block = active_block;
        self.blocks = blocks;
        self.pending_command_text = None;
        self.state = BlockBuildState::WaitingForPrompt;
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
    fn test_malformed_events_no_panic() {
        let mut mgr = BlockManager::new();
        // CommandEnd before CommandStart
        mgr.handle_event(&SemanticEvent::CommandEnd {
            row: 0,
            exit_code: Some(0),
        });
        assert_eq!(mgr.len(), 0);

        // OutputStart without CommandStart
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
}
