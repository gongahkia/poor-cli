//! Global terminal search: search across all terminal output.

/// A global search match.
#[derive(Debug, Clone)]
pub struct GlobalMatch {
    /// Row offset (negative = scrollback).
    pub screen_row: i64,
    /// Start column.
    pub col_start: u16,
    /// End column (exclusive).
    pub col_end: u16,
}

/// Global search state.
pub struct GlobalSearch {
    /// The current search query.
    pub query: String,
    /// All found matches.
    pub matches: Vec<GlobalMatch>,
    /// Index of the current match.
    pub current: usize,
    /// Whether search mode is active.
    pub is_active: bool,
    /// The text being typed in the search bar.
    pub search_input: String,
}

impl GlobalSearch {
    /// Create a new inactive search.
    pub fn new() -> Self {
        Self {
            query: String::new(),
            matches: Vec::new(),
            current: 0,
            is_active: false,
            search_input: String::new(),
        }
    }

    /// Activate search mode.
    pub fn activate(&mut self) {
        self.is_active = true;
        self.search_input.clear();
    }

    /// Deactivate search mode.
    pub fn deactivate(&mut self) {
        self.is_active = false;
        self.matches.clear();
        self.query.clear();
        self.search_input.clear();
    }

    /// Execute a search over the given lines.
    ///
    /// `lines` is a list of (row_offset, text) pairs.
    pub fn search(&mut self, query: &str, lines: &[(i64, String)]) {
        self.query = query.to_string();
        self.matches.clear();
        self.current = 0;

        let query_lower = query.to_lowercase();
        for (row, text) in lines {
            let text_lower = text.to_lowercase();
            let mut start = 0;
            while let Some(pos) = text_lower[start..].find(&query_lower) {
                let col_start = (start + pos) as u16;
                let col_end = col_start + query.len() as u16;
                self.matches.push(GlobalMatch {
                    screen_row: *row,
                    col_start,
                    col_end,
                });
                start += pos + query.len();
            }
        }
    }

    /// Move to the next match.
    pub fn next_match(&mut self) -> Option<&GlobalMatch> {
        if self.matches.is_empty() {
            return None;
        }
        self.current = (self.current + 1) % self.matches.len();
        Some(&self.matches[self.current])
    }

    /// Move to the previous match.
    pub fn prev_match(&mut self) -> Option<&GlobalMatch> {
        if self.matches.is_empty() {
            return None;
        }
        if self.current == 0 {
            self.current = self.matches.len() - 1;
        } else {
            self.current -= 1;
        }
        Some(&self.matches[self.current])
    }

    /// Get match count display string.
    pub fn match_count_display(&self) -> String {
        if self.matches.is_empty() {
            "No matches".to_string()
        } else {
            format!("{} of {}", self.current + 1, self.matches.len())
        }
    }
}

impl Default for GlobalSearch {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_search_finds_matches() {
        let mut search = GlobalSearch::new();
        let lines = vec![
            (0, "hello world".to_string()),
            (1, "foo bar".to_string()),
            (2, "hello again".to_string()),
        ];
        search.search("hello", &lines);
        assert_eq!(search.matches.len(), 2);
    }

    #[test]
    fn test_match_count_display() {
        let mut search = GlobalSearch::new();
        let lines = vec![
            (0, "a b a".to_string()),
        ];
        search.search("a", &lines);
        assert_eq!(search.match_count_display(), "1 of 2");
    }

    #[test]
    fn test_next_match_wraps() {
        let mut search = GlobalSearch::new();
        let lines = vec![(0, "aa".to_string())];
        search.search("a", &lines);
        assert_eq!(search.matches.len(), 2);
        search.next_match(); // moves to 1
        search.next_match(); // wraps to 0
        assert_eq!(search.current, 0);
    }
}
