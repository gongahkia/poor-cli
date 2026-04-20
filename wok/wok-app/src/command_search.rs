//! Pane-local command history search state.

use wok_input::history::{fuzzy_search_entries, HistoryEntry};

/// Search scope for one command-search result.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CommandSearchScope {
    /// Result came from the active pane's local history.
    Pane,
    /// Result came from the merged global history.
    Global,
}

/// One ranked result in the command-search overlay.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommandSearchResult {
    /// Where the result came from.
    pub scope: CommandSearchScope,
    /// Matching history entry.
    pub entry: HistoryEntry,
    /// Ranking score from the fuzzy matcher.
    pub score: i64,
}

/// Active command-search overlay state for one pane.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CommandSearchState {
    /// Current query string.
    pub query: String,
    /// Ranked results in display order.
    pub results: Vec<CommandSearchResult>,
    /// Index of the current result.
    pub current: usize,
}

impl CommandSearchState {
    /// Create a new empty command-search overlay.
    pub fn new() -> Self {
        Self {
            query: String::new(),
            results: Vec::new(),
            current: 0,
        }
    }

    /// Refresh results from pane-local and global history.
    pub fn search(
        &mut self,
        query: &str,
        pane_entries: &[HistoryEntry],
        global_entries: &[HistoryEntry],
    ) {
        self.query = query.to_string();
        self.current = 0;
        self.results.clear();

        let pane_results = fuzzy_search_entries(pane_entries, query, 8)
            .into_iter()
            .map(|candidate| CommandSearchResult {
                scope: CommandSearchScope::Pane,
                entry: candidate.entry,
                score: candidate.score,
            })
            .collect::<Vec<_>>();

        let global_results = fuzzy_search_entries(global_entries, query, 8)
            .into_iter()
            .filter(|candidate| {
                !pane_results.iter().any(|pane_result| {
                    same_origin(&pane_result.entry, &candidate.entry)
                        || pane_result.entry.command == candidate.entry.command
                })
            })
            .map(|candidate| CommandSearchResult {
                scope: CommandSearchScope::Global,
                entry: candidate.entry,
                score: candidate.score,
            })
            .collect::<Vec<_>>();

        self.results.extend(pane_results);
        self.results.extend(global_results);
    }

    /// Move to the next result, wrapping when needed.
    pub fn next_match(&mut self) -> Option<&CommandSearchResult> {
        if self.results.is_empty() {
            return None;
        }

        self.current = (self.current + 1) % self.results.len();
        self.results.get(self.current)
    }

    /// Move to the previous result, wrapping when needed.
    pub fn prev_match(&mut self) -> Option<&CommandSearchResult> {
        if self.results.is_empty() {
            return None;
        }

        if self.current == 0 {
            self.current = self.results.len() - 1;
        } else {
            self.current -= 1;
        }
        self.results.get(self.current)
    }

    /// Return the currently selected result.
    pub fn current_match(&self) -> Option<&CommandSearchResult> {
        self.results.get(self.current)
    }

    /// Human-readable match count display.
    pub fn match_count_display(&self) -> String {
        if self.results.is_empty() {
            "No matches".to_string()
        } else {
            format!("{} of {}", self.current + 1, self.results.len())
        }
    }
}

impl Default for CommandSearchState {
    fn default() -> Self {
        Self::new()
    }
}

fn same_origin(left: &HistoryEntry, right: &HistoryEntry) -> bool {
    left.source_pane_id == right.source_pane_id
        && left.started_at_ms == right.started_at_ms
        && left.started_at_ms != 0
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_entry(command: &str, pane_id: u64, started_at_ms: u64) -> HistoryEntry {
        let mut entry = HistoryEntry::pending(command, None, Some(pane_id));
        entry.started_at_ms = started_at_ms;
        entry
    }

    #[test]
    fn test_command_search_groups_pane_before_global() {
        let pane_entries = vec![make_entry("cargo test", 1, 10)];
        let global_entries = vec![make_entry("git status", 2, 20)];
        let mut state = CommandSearchState::new();

        state.search("", &pane_entries, &global_entries);

        assert_eq!(state.results[0].scope, CommandSearchScope::Pane);
        assert_eq!(state.results[1].scope, CommandSearchScope::Global);
    }

    #[test]
    fn test_command_search_deduplicates_same_command() {
        let pane_entries = vec![make_entry("cargo test", 1, 10)];
        let global_entries = vec![make_entry("cargo test", 1, 10)];
        let mut state = CommandSearchState::new();

        state.search("cargo", &pane_entries, &global_entries);

        assert_eq!(state.results.len(), 1);
        assert_eq!(state.results[0].scope, CommandSearchScope::Pane);
    }
}
