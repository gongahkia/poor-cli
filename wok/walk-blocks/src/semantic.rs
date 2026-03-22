//! Semantic event types from shell integration markers (OSC 133).

use std::path::PathBuf;

/// Semantic events emitted by shell integration markers.
#[derive(Debug, Clone)]
pub enum SemanticEvent {
    /// Shell prompt started (OSC 133;A).
    PromptStart {
        /// Line number where the prompt starts.
        line: usize,
    },
    /// Command input started (OSC 133;B).
    CommandStart {
        /// Line number where command input starts.
        line: usize,
    },
    /// Command output started (OSC 133;C).
    OutputStart {
        /// Line number where output starts.
        line: usize,
    },
    /// Command finished (OSC 133;D).
    CommandEnd {
        /// Line number.
        line: usize,
        /// Exit code if available.
        exit_code: Option<i32>,
    },
    /// Current working directory changed (OSC 7).
    CwdChanged(PathBuf),
}
