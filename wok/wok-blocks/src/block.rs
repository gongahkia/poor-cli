//! Block record types.
//!
//! For backwards compatibility this module re-exports `BlockManager` so
//! existing call sites at `wok_blocks::block::BlockManager` keep working.

use std::path::PathBuf;
use std::time::{Duration, Instant};

use crate::block_id::BlockId;
use crate::triggers::TriggerHighlight;

pub use crate::block_manager::BlockManager;

/// One streaming output line emitted from a block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OutputLineEvent {
    /// Pane id that produced this line.
    pub pane_id: u64,
    /// Block id that produced this line.
    pub block_id: BlockId,
    /// Line number relative to block output start.
    pub line_number: usize,
    /// Output text content for this line.
    pub text: String,
}

/// A single command block: prompt + command + output.
#[derive(Debug, Clone)]
pub struct Block {
    /// Unique block identifier.
    pub id: BlockId,
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
    /// Whether the block is bookmarked for quick navigation.
    pub is_bookmarked: bool,
    /// Trigger-derived highlight regions anchored to absolute rows.
    pub trigger_highlights: Vec<TriggerHighlight>,
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
        block_id: BlockId,
    },
}
