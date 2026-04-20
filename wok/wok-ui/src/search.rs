//! Global terminal search: search across all terminal output.

/// A searchable line in the terminal experience.
#[derive(Debug, Clone)]
pub struct SearchLine {
    /// Pane containing the line.
    pub pane_id: u64,
    /// Tab containing the line.
    pub tab_id: u64,
    /// Absolute row anchor for the line.
    pub row: usize,
    /// Block owning the line when the source is block metadata.
    pub block_id: Option<u64>,
    /// Whether this line comes from block command text instead of terminal output.
    pub is_command: bool,
    /// Searchable text content.
    pub text: String,
}

/// A global search match.
#[derive(Debug, Clone)]
pub struct GlobalMatch {
    /// Pane containing the match.
    pub pane_id: u64,
    /// Tab containing the match.
    pub tab_id: u64,
    /// Absolute row anchor for the match.
    pub row: usize,
    /// Block owning the match when it came from block command text.
    pub block_id: Option<u64>,
    /// Whether the match came from block command text.
    pub is_command: bool,
    /// Start column.
    pub col_start: u16,
    /// End column (exclusive).
    pub col_end: u16,
}

/// Global search state.
#[derive(Clone)]
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
    pub fn search(&mut self, query: &str, lines: &[SearchLine]) {
        self.query = query.to_string();
        self.matches.clear();
        self.current = 0;

        if query.is_empty() {
            return;
        }

        let query_lower = query.to_lowercase();
        for line in lines {
            if query.is_ascii() && line.text.is_ascii() {
                for col_start in ascii_case_insensitive_matches(&line.text, query) {
                    let col_start = col_start as u16;
                    let col_end = col_start + query.len() as u16;
                    self.matches.push(GlobalMatch {
                        pane_id: line.pane_id,
                        tab_id: line.tab_id,
                        row: line.row,
                        block_id: line.block_id,
                        is_command: line.is_command,
                        col_start,
                        col_end,
                    });
                }
                continue;
            }

            let text_lower = line.text.to_lowercase();
            let mut start = 0;
            while let Some(pos) = text_lower[start..].find(&query_lower) {
                let col_start = start + pos;
                let col_end = col_start + query.len();
                self.matches.push(GlobalMatch {
                    pane_id: line.pane_id,
                    tab_id: line.tab_id,
                    row: line.row,
                    block_id: line.block_id,
                    is_command: line.is_command,
                    col_start: col_start as u16,
                    col_end: col_end as u16,
                });
                start = col_end;
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

fn ascii_case_insensitive_matches<'a>(
    text: &'a str,
    query: &'a str,
) -> impl Iterator<Item = usize> + 'a {
    let text = text.as_bytes();
    let query = query.as_bytes();
    let mut start = 0;

    std::iter::from_fn(move || {
        if query.is_empty() || start + query.len() > text.len() {
            return None;
        }

        let position = text[start..]
            .windows(query.len())
            .position(|candidate| candidate.eq_ignore_ascii_case(query))?;
        let match_start = start + position;
        start = match_start + query.len();
        Some(match_start)
    })
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
            SearchLine {
                pane_id: 1,
                tab_id: 1,
                row: 0,
                block_id: None,
                is_command: false,
                text: "hello world".to_string(),
            },
            SearchLine {
                pane_id: 1,
                tab_id: 1,
                row: 1,
                block_id: None,
                is_command: false,
                text: "foo bar".to_string(),
            },
            SearchLine {
                pane_id: 2,
                tab_id: 3,
                row: 2,
                block_id: None,
                is_command: false,
                text: "hello again".to_string(),
            },
        ];
        search.search("hello", &lines);
        assert_eq!(search.matches.len(), 2);
    }

    #[test]
    fn test_match_count_display() {
        let mut search = GlobalSearch::new();
        let lines = vec![SearchLine {
            pane_id: 1,
            tab_id: 1,
            row: 0,
            block_id: None,
            is_command: false,
            text: "a b a".to_string(),
        }];
        search.search("a", &lines);
        assert_eq!(search.match_count_display(), "1 of 2");
    }

    #[test]
    fn test_next_match_wraps() {
        let mut search = GlobalSearch::new();
        let lines = vec![SearchLine {
            pane_id: 1,
            tab_id: 1,
            row: 0,
            block_id: None,
            is_command: false,
            text: "aa".to_string(),
        }];
        search.search("a", &lines);
        assert_eq!(search.matches.len(), 2);
        search.next_match(); // moves to 1
        search.next_match(); // wraps to 0
        assert_eq!(search.current, 0);
    }

    #[test]
    fn test_ascii_case_insensitive_search() {
        let mut search = GlobalSearch::new();
        let lines = vec![SearchLine {
            pane_id: 1,
            tab_id: 1,
            row: 0,
            block_id: None,
            is_command: false,
            text: "Error ERROR error".to_string(),
        }];
        search.search("error", &lines);
        assert_eq!(search.matches.len(), 3);
        assert_eq!(search.matches[1].col_start, 6);
    }
}
