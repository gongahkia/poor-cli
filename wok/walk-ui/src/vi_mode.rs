//! Vi-mode navigation state for terminal output.

/// Vi submodes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ViSubMode {
    /// Normal vi mode.
    Normal,
    /// Character-wise visual selection mode.
    Visual,
    /// Line-wise visual mode.
    VisualLine,
    /// Block visual mode.
    VisualBlock,
}

/// Pending multi-key vi motion state.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ViPending {
    /// Waiting for a second `g` in `gg`.
    G,
    /// Waiting for block jump suffix after `[`.
    BlockBackward,
    /// Waiting for block jump suffix after `]`.
    BlockForward,
    /// Waiting for target char in `f<char>`.
    FindForward,
    /// Waiting for target char in `F<char>`.
    FindBackward,
}

/// Vi mode state stored per pane.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ViModeState {
    /// Absolute terminal row.
    pub cursor_row: usize,
    /// Column within `cursor_row`.
    pub cursor_col: usize,
    /// Active vi mode.
    pub mode: ViSubMode,
    /// Visual anchor when in a visual submode.
    pub visual_anchor: Option<(usize, usize)>,
    /// Pending multi-key motion state.
    pub pending: Option<ViPending>,
}

impl ViModeState {
    /// Create a new vi mode state.
    pub fn new(cursor_row: usize, cursor_col: usize) -> Self {
        Self {
            cursor_row,
            cursor_col,
            mode: ViSubMode::Normal,
            visual_anchor: None,
            pending: None,
        }
    }

    /// Return status-bar label for current mode.
    pub fn mode_label(&self) -> &'static str {
        match self.mode {
            ViSubMode::Normal => "-- VI --",
            ViSubMode::Visual => "-- VISUAL --",
            ViSubMode::VisualLine => "-- VISUAL LINE --",
            ViSubMode::VisualBlock => "-- VISUAL BLOCK --",
        }
    }

    /// Enter visual mode if not already active.
    pub fn enter_visual(&mut self, mode: ViSubMode) {
        if self.visual_anchor.is_none() {
            self.visual_anchor = Some((self.cursor_row, self.cursor_col));
        }
        self.mode = mode;
    }

    /// Return to normal mode and clear visual selection.
    pub fn clear_visual(&mut self) {
        self.mode = ViSubMode::Normal;
        self.visual_anchor = None;
    }

    /// Move left by one cell.
    pub fn left(&mut self) {
        self.cursor_col = self.cursor_col.saturating_sub(1);
    }

    /// Move right by one cell, clamped to line length.
    pub fn right(&mut self, line_len: usize) {
        let max_col = line_len.saturating_sub(1);
        self.cursor_col = (self.cursor_col + 1).min(max_col);
    }

    /// Move up by one row.
    pub fn up(&mut self, min_row: usize, line_len: usize) {
        self.cursor_row = self.cursor_row.saturating_sub(1).max(min_row);
        self.cursor_col = self.cursor_col.min(line_len.saturating_sub(1));
    }

    /// Move down by one row.
    pub fn down(&mut self, max_row: usize, line_len: usize) {
        self.cursor_row = (self.cursor_row + 1).min(max_row);
        self.cursor_col = self.cursor_col.min(line_len.saturating_sub(1));
    }

    /// Jump to line start.
    pub fn line_start(&mut self) {
        self.cursor_col = 0;
    }

    /// Jump to line end.
    pub fn line_end(&mut self, line_len: usize) {
        self.cursor_col = line_len.saturating_sub(1);
    }

    /// Jump to top of buffer.
    pub fn top(&mut self, min_row: usize, line_len: usize) {
        self.cursor_row = min_row;
        self.cursor_col = self.cursor_col.min(line_len.saturating_sub(1));
    }

    /// Jump to bottom of buffer.
    pub fn bottom(&mut self, max_row: usize, line_len: usize) {
        self.cursor_row = max_row;
        self.cursor_col = self.cursor_col.min(line_len.saturating_sub(1));
    }

    /// Half-page down.
    pub fn half_page_down(&mut self, max_row: usize, page_rows: usize, line_len: usize) {
        self.cursor_row = (self.cursor_row + (page_rows / 2).max(1)).min(max_row);
        self.cursor_col = self.cursor_col.min(line_len.saturating_sub(1));
    }

    /// Half-page up.
    pub fn half_page_up(&mut self, min_row: usize, page_rows: usize, line_len: usize) {
        self.cursor_row = self
            .cursor_row
            .saturating_sub((page_rows / 2).max(1))
            .max(min_row);
        self.cursor_col = self.cursor_col.min(line_len.saturating_sub(1));
    }

    /// Jump to next word start.
    pub fn word_forward(&mut self, line: &str) {
        let chars = line.chars().collect::<Vec<_>>();
        if chars.is_empty() {
            self.cursor_col = 0;
            return;
        }
        let mut idx = self.cursor_col.min(chars.len().saturating_sub(1));
        while idx < chars.len() && !chars[idx].is_ascii_whitespace() {
            idx += 1;
        }
        while idx < chars.len() && chars[idx].is_ascii_whitespace() {
            idx += 1;
        }
        self.cursor_col = idx.min(chars.len().saturating_sub(1));
    }

    /// Jump to previous word start.
    pub fn word_backward(&mut self, line: &str) {
        let chars = line.chars().collect::<Vec<_>>();
        if chars.is_empty() {
            self.cursor_col = 0;
            return;
        }
        let mut idx = self.cursor_col.min(chars.len().saturating_sub(1));
        if idx > 0 {
            idx -= 1;
        }
        while idx > 0 && chars[idx].is_ascii_whitespace() {
            idx -= 1;
        }
        while idx > 0 && !chars[idx - 1].is_ascii_whitespace() {
            idx -= 1;
        }
        self.cursor_col = idx;
    }

    /// Jump to end of current word.
    pub fn word_end(&mut self, line: &str) {
        let chars = line.chars().collect::<Vec<_>>();
        if chars.is_empty() {
            self.cursor_col = 0;
            return;
        }
        let mut idx = self.cursor_col.min(chars.len().saturating_sub(1));
        while idx < chars.len() && chars[idx].is_ascii_whitespace() {
            idx += 1;
        }
        while idx + 1 < chars.len() && !chars[idx + 1].is_ascii_whitespace() {
            idx += 1;
        }
        self.cursor_col = idx.min(chars.len().saturating_sub(1));
    }

    /// Jump to the previous block boundary.
    pub fn prev_boundary(&mut self, boundaries: &[usize]) {
        if let Some(row) = boundaries
            .iter()
            .copied()
            .filter(|row| *row < self.cursor_row)
            .max()
        {
            self.cursor_row = row;
        }
    }

    /// Jump to the next block boundary.
    pub fn next_boundary(&mut self, boundaries: &[usize]) {
        if let Some(row) = boundaries
            .iter()
            .copied()
            .filter(|row| *row > self.cursor_row)
            .min()
        {
            self.cursor_row = row;
        }
    }

    /// Jump to next search match.
    pub fn next_search_match(&mut self, matches: &[(usize, usize)]) {
        if let Some((row, col)) = matches
            .iter()
            .copied()
            .find(|(row, col)| (*row, *col) > (self.cursor_row, self.cursor_col))
            .or_else(|| matches.first().copied())
        {
            self.cursor_row = row;
            self.cursor_col = col;
        }
    }

    /// Jump to previous search match.
    pub fn prev_search_match(&mut self, matches: &[(usize, usize)]) {
        if let Some((row, col)) = matches
            .iter()
            .copied()
            .rev()
            .find(|(row, col)| (*row, *col) < (self.cursor_row, self.cursor_col))
            .or_else(|| matches.last().copied())
        {
            self.cursor_row = row;
            self.cursor_col = col;
        }
    }

    /// Find a character forward in a line.
    pub fn find_forward(&mut self, line: &str, target: char) {
        let chars = line.chars().collect::<Vec<_>>();
        let start = (self.cursor_col + 1).min(chars.len());
        if let Some(found) = chars
            .iter()
            .enumerate()
            .skip(start)
            .find_map(|(idx, ch)| (*ch == target).then_some(idx))
        {
            self.cursor_col = found;
        }
    }

    /// Find a character backward in a line.
    pub fn find_backward(&mut self, line: &str, target: char) {
        let chars = line.chars().collect::<Vec<_>>();
        if chars.is_empty() {
            return;
        }
        let start = self.cursor_col.min(chars.len().saturating_sub(1));
        if let Some(found) = chars
            .iter()
            .enumerate()
            .take(start)
            .rev()
            .find_map(|(idx, ch)| (*ch == target).then_some(idx))
        {
            self.cursor_col = found;
        }
    }

    /// Return the normalized visual selection range.
    pub fn visual_range(&self) -> Option<((usize, usize), (usize, usize))> {
        let anchor = self.visual_anchor?;
        let cursor = (self.cursor_row, self.cursor_col);
        if anchor <= cursor {
            Some((anchor, cursor))
        } else {
            Some((cursor, anchor))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_word_motions_move_cursor() {
        let mut state = ViModeState::new(0, 0);
        state.word_forward("hello world");
        assert_eq!(state.cursor_col, 6);
        state.word_end("hello world");
        assert_eq!(state.cursor_col, 10);
        state.word_backward("hello world");
        assert_eq!(state.cursor_col, 6);
    }

    #[test]
    fn test_visual_range_normalizes_order() {
        let mut state = ViModeState::new(10, 5);
        state.enter_visual(ViSubMode::Visual);
        state.cursor_row = 8;
        state.cursor_col = 2;
        let range = state.visual_range().expect("visual range");
        assert_eq!(range.0, (8, 2));
        assert_eq!(range.1, (10, 5));
    }
}
