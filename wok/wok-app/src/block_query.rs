//! Block-scoped find and filter state for a pane.

use wok_blocks::block_search::{BlockSearch, SearchMatch};

/// Supported block query overlay modes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlockQueryMode {
    /// Search within a single block and jump between matches.
    Find,
    /// Filter a single block down to matching output lines.
    Filter,
}

/// Active block find/filter state for one pane.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BlockQueryState {
    /// The target block being queried.
    pub target_block_id: u64,
    /// The active query mode.
    pub mode: BlockQueryMode,
    /// The current user-entered query.
    pub query: String,
    /// All matches in block-output-relative coordinates.
    pub matches: Vec<SearchMatch>,
    /// Index of the current match.
    pub current_match: usize,
    /// Scroll offset for the filter overlay list.
    pub overlay_scroll_offset: usize,
}

impl BlockQueryState {
    /// Create a new block query targeting the given block.
    pub fn new(mode: BlockQueryMode, target_block_id: u64) -> Self {
        Self {
            target_block_id,
            mode,
            query: String::new(),
            matches: Vec::new(),
            current_match: 0,
            overlay_scroll_offset: 0,
        }
    }

    /// Re-run the query against the current block output.
    pub fn search(&mut self, query: &str, output_lines: &[String]) {
        self.query = query.to_string();
        self.current_match = 0;
        self.overlay_scroll_offset = 0;

        if query.is_empty() {
            self.matches.clear();
            return;
        }

        self.matches = BlockSearch::new(self.target_block_id, query, output_lines).matches;
    }

    /// Advance to the next match, wrapping when needed.
    pub fn next_match(&mut self) -> Option<&SearchMatch> {
        if self.matches.is_empty() {
            return None;
        }
        self.current_match = (self.current_match + 1) % self.matches.len();
        Some(&self.matches[self.current_match])
    }

    /// Move to the previous match, wrapping when needed.
    pub fn prev_match(&mut self) -> Option<&SearchMatch> {
        if self.matches.is_empty() {
            return None;
        }
        if self.current_match == 0 {
            self.current_match = self.matches.len() - 1;
        } else {
            self.current_match -= 1;
        }
        Some(&self.matches[self.current_match])
    }

    /// Return the current match if one exists.
    pub fn current_match(&self) -> Option<&SearchMatch> {
        self.matches.get(self.current_match)
    }

    /// Return display text for the current match count.
    pub fn match_count_display(&self) -> String {
        if self.matches.is_empty() {
            "No matches".to_string()
        } else {
            format!("{} of {}", self.current_match + 1, self.matches.len())
        }
    }

    /// Return the unique matching output line indices in first-match order.
    pub fn filtered_line_indices(&self) -> Vec<usize> {
        let mut lines = Vec::new();
        let mut last_line = None;

        for search_match in &self.matches {
            if last_line != Some(search_match.line) {
                lines.push(search_match.line);
                last_line = Some(search_match.line);
            }
        }

        lines
    }

    /// Return the currently selected filtered line index.
    pub fn current_filtered_line(&self) -> Option<usize> {
        self.current_match().map(|search_match| search_match.line)
    }

    /// Ensure the current filtered line is visible in the overlay viewport.
    pub fn ensure_current_line_visible(&mut self, max_visible_lines: usize) {
        if max_visible_lines == 0 {
            self.overlay_scroll_offset = 0;
            return;
        }

        let filtered = self.filtered_line_indices();
        let Some(current_line) = self.current_filtered_line() else {
            self.overlay_scroll_offset = self.overlay_scroll_offset.min(filtered.len());
            return;
        };
        let Some(filtered_index) = filtered.iter().position(|line| *line == current_line) else {
            return;
        };

        if filtered_index < self.overlay_scroll_offset {
            self.overlay_scroll_offset = filtered_index;
        } else {
            let visible_end = self.overlay_scroll_offset + max_visible_lines;
            if filtered_index >= visible_end {
                self.overlay_scroll_offset = filtered_index + 1 - max_visible_lines;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_search_preserves_case_insensitive_matches() {
        let mut query = BlockQueryState::new(BlockQueryMode::Find, 7);
        let lines = vec![
            "Error one".to_string(),
            "all clear".to_string(),
            "error two".to_string(),
        ];

        query.search("error", &lines);

        assert_eq!(query.matches.len(), 2);
        assert_eq!(query.current_match, 0);
    }

    #[test]
    fn test_filtered_line_indices_deduplicate_lines() {
        let mut query = BlockQueryState::new(BlockQueryMode::Filter, 9);
        let lines = vec!["error error".to_string(), "ok".to_string()];

        query.search("error", &lines);

        assert_eq!(query.filtered_line_indices(), vec![0]);
    }

    #[test]
    fn test_ensure_current_line_visible_scrolls_overlay() {
        let mut query = BlockQueryState::new(BlockQueryMode::Filter, 1);
        let lines = vec![
            "one".to_string(),
            "two".to_string(),
            "three".to_string(),
            "four".to_string(),
        ];
        query.search("o", &lines);
        query.current_match = 2;

        query.ensure_current_line_visible(1);

        assert_eq!(query.overlay_scroll_offset, 2);
    }
}
