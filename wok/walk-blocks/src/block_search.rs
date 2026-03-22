//! Per-block search: search within a specific block's output.

/// A search match within a block.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SearchMatch {
    /// Line number within the block output.
    pub line: usize,
    /// Start column of the match.
    pub col_start: usize,
    /// End column of the match (exclusive).
    pub col_end: usize,
}

/// Search state for a single block.
pub struct BlockSearch {
    /// The search query.
    pub query: String,
    /// All matches found.
    pub matches: Vec<SearchMatch>,
    /// Index of the current match.
    pub current_match: usize,
    /// ID of the target block.
    pub target_block_id: u64,
}

impl BlockSearch {
    /// Create a new block search on the given output text.
    pub fn new(block_id: u64, query: &str, output_lines: &[String]) -> Self {
        let query_lower = query.to_lowercase();
        let mut matches = Vec::new();

        for (line_idx, line) in output_lines.iter().enumerate() {
            let line_lower = line.to_lowercase();
            let mut start = 0;
            while let Some(pos) = line_lower[start..].find(&query_lower) {
                let col_start = start + pos;
                let col_end = col_start + query.len();
                matches.push(SearchMatch {
                    line: line_idx,
                    col_start,
                    col_end,
                });
                start = col_end;
            }
        }

        Self {
            query: query.to_string(),
            matches,
            current_match: 0,
            target_block_id: block_id,
        }
    }

    /// Advance to the next match (wrapping).
    pub fn next_match(&mut self) -> Option<&SearchMatch> {
        if self.matches.is_empty() {
            return None;
        }
        self.current_match = (self.current_match + 1) % self.matches.len();
        Some(&self.matches[self.current_match])
    }

    /// Go to the previous match (wrapping).
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

    /// Return highlight ranges for rendering.
    pub fn highlight_ranges(&self) -> Vec<(usize, usize, usize)> {
        self.matches
            .iter()
            .map(|m| (m.line, m.col_start, m.col_end))
            .collect()
    }

    /// Return the total number of matches.
    pub fn match_count(&self) -> usize {
        self.matches.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_search_finds_matches() {
        let lines = vec![
            "line one with error".to_string(),
            "line two is fine".to_string(),
            "line three has error too".to_string(),
            "another error here".to_string(),
        ];
        let search = BlockSearch::new(1, "error", &lines);
        assert_eq!(search.match_count(), 3);
    }

    #[test]
    fn test_next_match_wraps() {
        let lines = vec!["error error".to_string()];
        let mut search = BlockSearch::new(1, "error", &lines);
        assert_eq!(search.match_count(), 2);

        let m1 = search.next_match().unwrap().clone();
        assert_eq!(m1.col_start, 6); // second match
        let m2 = search.next_match().unwrap().clone();
        assert_eq!(m2.col_start, 0); // wraps to first
    }

    #[test]
    fn test_case_insensitive() {
        let lines = vec!["Error ERROR error".to_string()];
        let search = BlockSearch::new(1, "error", &lines);
        assert_eq!(search.match_count(), 3);
    }

    #[test]
    fn test_highlight_ranges() {
        let lines = vec!["find me".to_string()];
        let search = BlockSearch::new(1, "me", &lines);
        let ranges = search.highlight_ranges();
        assert_eq!(ranges, vec![(0, 5, 7)]);
    }
}
