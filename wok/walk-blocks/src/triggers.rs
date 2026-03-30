//! Trigger engine for regex-driven block actions.

use regex::Regex;

use crate::block::Block;

/// The source region a trigger should evaluate.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TriggerScope {
    /// Evaluate only command output text.
    Output,
    /// Evaluate only command text.
    Command,
    /// Evaluate both output and command text.
    Both,
}

impl TriggerScope {
    /// Return whether this trigger should run for the given target scope.
    pub const fn matches(self, target: Self) -> bool {
        match self {
            Self::Both => true,
            Self::Output => matches!(target, Self::Output),
            Self::Command => matches!(target, Self::Command),
        }
    }
}

/// Action emitted when a trigger matches.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TriggerAction {
    /// Highlight the match with the given color.
    Highlight {
        /// Hex color string for the highlight.
        color: String,
    },
    /// Show a notification.
    Notify {
        /// Notification message text.
        message: String,
    },
    /// Bookmark the containing block.
    BookmarkBlock,
    /// Open the matched text as a URL.
    OpenUrl,
    /// Copy the matched text.
    CopyMatch,
    /// Invoke a Lua hook by name.
    LuaHook {
        /// Hook name to invoke in Lua.
        hook_name: String,
    },
}

/// A configured regex trigger.
#[derive(Debug, Clone)]
pub struct Trigger {
    /// Trigger display name.
    pub name: String,
    /// Regex pattern to evaluate.
    pub pattern: Regex,
    /// Actions to run for each match.
    pub actions: Vec<TriggerAction>,
    /// Scope where the trigger should run.
    pub scope: TriggerScope,
}

/// A single trigger match result.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TriggerMatch {
    /// Trigger name.
    pub trigger_name: String,
    /// Block id that produced this match.
    pub block_id: u64,
    /// Matched text.
    pub matched_text: String,
    /// Byte range in the evaluated source text.
    pub byte_range: (usize, usize),
    /// Source scope for this match.
    pub scope: TriggerScope,
    /// Actions to execute.
    pub actions: Vec<TriggerAction>,
}

/// Highlight region resolved from a trigger match.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TriggerHighlight {
    /// Absolute row in terminal history.
    pub absolute_row: usize,
    /// Start column (inclusive).
    pub col_start: usize,
    /// End column (exclusive).
    pub col_end: usize,
    /// Hex color string.
    pub color: String,
}

/// Runtime trigger engine.
#[derive(Debug, Default, Clone)]
pub struct TriggerEngine {
    triggers: Vec<Trigger>,
}

impl TriggerEngine {
    /// Create an empty trigger engine.
    pub fn new() -> Self {
        Self {
            triggers: Vec::new(),
        }
    }

    /// Return the number of registered triggers.
    pub fn len(&self) -> usize {
        self.triggers.len()
    }

    /// Return whether the engine has no triggers.
    pub fn is_empty(&self) -> bool {
        self.triggers.is_empty()
    }

    /// Replace all triggers.
    pub fn set_triggers(&mut self, triggers: Vec<Trigger>) {
        self.triggers = triggers;
    }

    /// Add a trigger, replacing any existing one with the same name.
    pub fn add_trigger(&mut self, trigger: Trigger) {
        self.remove_trigger(&trigger.name);
        self.triggers.push(trigger);
    }

    /// Remove a trigger by name.
    pub fn remove_trigger(&mut self, name: &str) -> bool {
        let before = self.triggers.len();
        self.triggers.retain(|trigger| trigger.name != name);
        self.triggers.len() != before
    }

    /// Evaluate all matching triggers for a block and source text.
    pub fn evaluate(
        &self,
        block: &Block,
        text: &str,
        source_scope: TriggerScope,
    ) -> Vec<TriggerMatch> {
        if self.triggers.is_empty() || text.is_empty() {
            return Vec::new();
        }

        let mut matches = Vec::new();
        for trigger in &self.triggers {
            if !trigger.scope.matches(source_scope) {
                continue;
            }

            for regex_match in trigger.pattern.find_iter(text) {
                matches.push(TriggerMatch {
                    trigger_name: trigger.name.clone(),
                    block_id: block.id,
                    matched_text: regex_match.as_str().to_string(),
                    byte_range: (regex_match.start(), regex_match.end()),
                    scope: source_scope,
                    actions: trigger.actions.clone(),
                });
            }
        }
        matches
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::block::Block;
    use std::path::PathBuf;
    use std::time::Instant;

    fn mock_block() -> Block {
        Block {
            id: 7,
            prompt_text: String::new(),
            command_text: "echo ERROR".to_string(),
            output_start_row: 10,
            output_end_row: 10,
            exit_code: Some(0),
            start_time: Instant::now(),
            end_time: None,
            duration: None,
            is_collapsed: false,
            scroll_offset: 0,
            cwd: PathBuf::new(),
            git_branch: None,
            git_dirty: None,
            is_bookmarked: false,
            trigger_highlights: Vec::new(),
        }
    }

    #[test]
    fn test_trigger_engine_matches_and_captures_ranges() {
        let mut engine = TriggerEngine::new();
        engine.add_trigger(Trigger {
            name: "errors".to_string(),
            pattern: Regex::new("ERROR").expect("valid regex"),
            actions: vec![TriggerAction::BookmarkBlock],
            scope: TriggerScope::Output,
        });

        let matches = engine.evaluate(&mock_block(), "ERROR at line 12", TriggerScope::Output);
        assert_eq!(matches.len(), 1);
        assert_eq!(matches[0].byte_range, (0, 5));
        assert_eq!(matches[0].matched_text, "ERROR");
    }

    #[test]
    fn test_trigger_scope_filters_matches() {
        let mut engine = TriggerEngine::new();
        engine.add_trigger(Trigger {
            name: "command-only".to_string(),
            pattern: Regex::new("echo").expect("valid regex"),
            actions: vec![TriggerAction::CopyMatch],
            scope: TriggerScope::Command,
        });

        let output_matches = engine.evaluate(&mock_block(), "echo", TriggerScope::Output);
        let command_matches = engine.evaluate(&mock_block(), "echo", TriggerScope::Command);
        assert!(output_matches.is_empty());
        assert_eq!(command_matches.len(), 1);
    }
}
