//! Gap buffer data structure for efficient text editing.

use thiserror::Error;

/// Errors that can occur during input buffer operations.
#[derive(Debug, Error)]
pub enum InputError {
    /// Cursor index is out of bounds.
    #[error("cursor index {index} is out of bounds (have {count} cursors)")]
    CursorOutOfBounds {
        /// The requested cursor index.
        index: usize,
        /// The total number of cursors.
        count: usize,
    },

    /// Position is out of bounds.
    #[error("position {position} is out of bounds (buffer length {length})")]
    PositionOutOfBounds {
        /// The requested position.
        position: usize,
        /// The buffer length.
        length: usize,
    },
}

/// A cursor within the buffer, with optional selection anchor.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Cursor {
    /// Current cursor position (character index in logical text).
    pub position: usize,
    /// Selection anchor. When set, the selection range is
    /// `min(position, anchor)..max(position, anchor)`.
    pub anchor: Option<usize>,
}

/// A gap-buffer-backed text buffer for the input editor.
///
/// The gap buffer provides O(1) amortized insertion and deletion at the cursor
/// position, which is the dominant operation pattern for interactive text editing.
pub struct InputBuffer {
    /// The underlying character storage with a gap.
    text: Vec<char>,
    /// Start of the gap (inclusive).
    gap_start: usize,
    /// End of the gap (exclusive).
    gap_end: usize,
    /// Active cursors.
    cursors: Vec<Cursor>,
}

impl InputBuffer {
    /// Create a new empty input buffer.
    ///
    /// Initial capacity is 1024 chars with a gap of 256.
    pub fn new() -> Self {
        let gap_size = 256;
        let capacity = 1_024;
        let mut text = Vec::with_capacity(capacity);
        text.resize(gap_size, '\0');
        Self {
            text,
            gap_start: 0,
            gap_end: gap_size,
            cursors: vec![Cursor {
                position: 0,
                anchor: None,
            }],
        }
    }

    /// Return the logical length of the text (excluding gap).
    pub fn len(&self) -> usize {
        self.text.len() - self.gap_len()
    }

    /// Return whether the buffer is empty.
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Return the gap size.
    fn gap_len(&self) -> usize {
        self.gap_end - self.gap_start
    }

    /// Convert a logical position to a physical index in the vec.
    fn logical_to_physical(&self, pos: usize) -> usize {
        if pos < self.gap_start {
            pos
        } else {
            pos + self.gap_len()
        }
    }

    /// Move the gap so that `gap_start` equals `pos`.
    fn move_gap_to(&mut self, pos: usize) {
        if pos == self.gap_start {
            return;
        }
        if pos < self.gap_start {
            let shift = self.gap_start - pos;
            let new_gap_end = self.gap_end - shift;
            self.text.copy_within(pos..self.gap_start, new_gap_end);
            self.gap_start = pos;
            self.gap_end = new_gap_end;
        } else {
            let shift = pos - self.gap_start;
            self.text
                .copy_within(self.gap_end..self.gap_end + shift, self.gap_start);
            self.gap_start = pos;
            self.gap_end = self.gap_end + shift;
        }
    }

    /// Ensure the gap is at least `needed` chars wide.
    fn ensure_gap(&mut self, needed: usize) {
        if self.gap_len() >= needed {
            return;
        }
        let grow = needed.max(256);
        let old_gap_end = self.gap_end;
        let old_len = self.text.len();
        self.text.resize(old_len + grow, '\0');
        // Shift everything after the gap right by `grow`
        self.text
            .copy_within(old_gap_end..old_len, old_gap_end + grow);
        self.gap_end += grow;
    }

    /// Insert text at the specified cursor position.
    ///
    /// # Errors
    ///
    /// Returns [`InputError::CursorOutOfBounds`] if `cursor_idx` exceeds the
    /// number of cursors.
    pub fn insert_at(&mut self, cursor_idx: usize, text: &str) -> Result<(), InputError> {
        if cursor_idx >= self.cursors.len() {
            return Err(InputError::CursorOutOfBounds {
                index: cursor_idx,
                count: self.cursors.len(),
            });
        }

        let pos = self.cursors[cursor_idx].position;
        let chars: Vec<char> = text.chars().collect();
        let char_count = chars.len();

        self.move_gap_to(pos);
        self.ensure_gap(char_count);

        for (i, &ch) in chars.iter().enumerate() {
            self.text[self.gap_start + i] = ch;
        }
        self.gap_start += char_count;

        // Update the cursor that did the insertion
        self.cursors[cursor_idx].position = pos + char_count;
        self.cursors[cursor_idx].anchor = None;

        // Adjust all other cursors at or after the insertion point
        for (i, cursor) in self.cursors.iter_mut().enumerate() {
            if i == cursor_idx {
                continue;
            }
            if cursor.position >= pos {
                cursor.position += char_count;
            }
            if let Some(ref mut anchor) = cursor.anchor {
                if *anchor >= pos {
                    *anchor += char_count;
                }
            }
        }

        Ok(())
    }

    /// Delete characters in the given range [start, end).
    ///
    /// # Errors
    ///
    /// Returns [`InputError::PositionOutOfBounds`] if the range is invalid.
    pub fn delete_range(&mut self, start: usize, end: usize) -> Result<(), InputError> {
        let len = self.len();
        if start > len || end > len || start > end {
            return Err(InputError::PositionOutOfBounds {
                position: end,
                length: len,
            });
        }
        if start == end {
            return Ok(());
        }

        let deleted = end - start;
        self.move_gap_to(start);
        self.gap_end += deleted;

        // Adjust all cursors
        for cursor in &mut self.cursors {
            if cursor.position >= end {
                cursor.position -= deleted;
            } else if cursor.position > start {
                cursor.position = start;
            }
            if let Some(ref mut anchor) = cursor.anchor {
                if *anchor >= end {
                    *anchor -= deleted;
                } else if *anchor > start {
                    *anchor = start;
                }
            }
        }

        Ok(())
    }

    /// Return the full text content as a String.
    pub fn text(&self) -> String {
        let mut result = String::with_capacity(self.len());
        for &ch in &self.text[..self.gap_start] {
            result.push(ch);
        }
        for &ch in &self.text[self.gap_end..] {
            result.push(ch);
        }
        result
    }

    /// Return the character at the given logical position.
    pub fn char_at(&self, pos: usize) -> Option<char> {
        if pos >= self.len() {
            return None;
        }
        Some(self.text[self.logical_to_physical(pos)])
    }

    /// Return the number of lines in the buffer.
    pub fn line_count(&self) -> usize {
        if self.is_empty() {
            return 1;
        }
        let txt = self.text();
        txt.chars().filter(|&c| c == '\n').count() + 1
    }

    /// Return the text of the given line (0-indexed).
    pub fn line_text(&self, line: usize) -> String {
        let txt = self.text();
        txt.split('\n').nth(line).unwrap_or("").to_string()
    }

    /// Return all cursor positions as (row, col) pairs.
    pub fn cursor_positions(&self) -> Vec<(usize, usize)> {
        let txt = self.text();
        self.cursors
            .iter()
            .map(|c| {
                let mut row = 0;
                let mut col = 0;
                for (i, ch) in txt.chars().enumerate() {
                    if i == c.position {
                        break;
                    }
                    if ch == '\n' {
                        row += 1;
                        col = 0;
                    } else {
                        col += 1;
                    }
                }
                (row, col)
            })
            .collect()
    }

    /// Return the current cursors.
    pub fn cursors(&self) -> &[Cursor] {
        &self.cursors
    }

    /// Return a mutable reference to the cursors.
    pub fn cursors_mut(&mut self) -> &mut Vec<Cursor> {
        &mut self.cursors
    }

    /// Add a new cursor at the given position.
    ///
    /// # Errors
    ///
    /// Returns [`InputError::PositionOutOfBounds`] if position exceeds buffer length.
    pub fn add_cursor(&mut self, position: usize) -> Result<(), InputError> {
        if position > self.len() {
            return Err(InputError::PositionOutOfBounds {
                position,
                length: self.len(),
            });
        }
        self.cursors.push(Cursor {
            position,
            anchor: None,
        });
        Ok(())
    }

    /// Remove the cursor at the given index.
    ///
    /// # Errors
    ///
    /// Returns [`InputError::CursorOutOfBounds`] if the index is invalid.
    /// Will not remove the last cursor.
    pub fn remove_cursor(&mut self, idx: usize) -> Result<(), InputError> {
        if idx >= self.cursors.len() {
            return Err(InputError::CursorOutOfBounds {
                index: idx,
                count: self.cursors.len(),
            });
        }
        if self.cursors.len() <= 1 {
            return Ok(()); // Don't remove the last cursor
        }
        self.cursors.remove(idx);
        Ok(())
    }

    /// Clear the buffer and reset to empty state.
    pub fn clear(&mut self) {
        self.text.clear();
        self.text.resize(256, '\0');
        self.gap_start = 0;
        self.gap_end = 256;
        self.cursors = vec![Cursor {
            position: 0,
            anchor: None,
        }];
    }

    /// Set the text content, replacing everything.
    pub fn set_text(&mut self, text: &str) {
        self.clear();
        if !text.is_empty() {
            self.insert_at(0, text).ok();
        }
    }
}

impl Default for InputBuffer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_insert_at_start() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "hello").unwrap();
        assert_eq!(buf.text(), "hello");
        assert_eq!(buf.cursors()[0].position, 5);
    }

    #[test]
    fn test_insert_at_middle() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "helo").unwrap();
        buf.cursors_mut()[0].position = 2;
        buf.insert_at(0, "l").unwrap();
        assert_eq!(buf.text(), "hello");
    }

    #[test]
    fn test_delete_range() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "abcdef").unwrap();
        buf.delete_range(2, 4).unwrap();
        assert_eq!(buf.text(), "abef");
    }

    #[test]
    fn test_multi_cursor_insert() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "helloworld").unwrap();
        buf.cursors_mut()[0].position = 0;
        buf.add_cursor(5).unwrap();
        // Insert at cursor 0 (pos 0)
        buf.insert_at(0, "_").unwrap();
        // Cursor 1 shifted to 6, insert there
        buf.insert_at(1, "_").unwrap();
        assert_eq!(buf.text(), "_hello_world");
    }

    #[test]
    fn test_line_count() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "a\nb\nc").unwrap();
        assert_eq!(buf.line_count(), 3);
    }

    #[test]
    fn test_line_text() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "line1\nline2\nline3").unwrap();
        assert_eq!(buf.line_text(0), "line1");
        assert_eq!(buf.line_text(1), "line2");
        assert_eq!(buf.line_text(2), "line3");
    }

    #[test]
    fn test_empty_buffer() {
        let buf = InputBuffer::new();
        assert!(buf.is_empty());
        assert_eq!(buf.len(), 0);
        assert_eq!(buf.line_count(), 1);
        assert_eq!(buf.text(), "");
    }

    #[test]
    fn test_error_on_invalid_cursor() {
        let mut buf = InputBuffer::new();
        let result = buf.insert_at(5, "oops");
        assert!(matches!(result, Err(InputError::CursorOutOfBounds { .. })));
    }

    #[test]
    fn test_cursor_positions() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "ab\ncd").unwrap();
        buf.cursors_mut()[0].position = 4; // 'd'
        let positions = buf.cursor_positions();
        assert_eq!(positions[0], (1, 1)); // row 1, col 1
    }

    #[test]
    fn test_clear() {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, "some text").unwrap();
        buf.clear();
        assert!(buf.is_empty());
        assert_eq!(buf.cursors().len(), 1);
        assert_eq!(buf.cursors()[0].position, 0);
    }

    #[test]
    fn test_set_text() {
        let mut buf = InputBuffer::new();
        buf.set_text("hello world");
        assert_eq!(buf.text(), "hello world");
    }

    #[test]
    fn test_large_insert() {
        let mut buf = InputBuffer::new();
        let long_text: String = "a".repeat(2000);
        buf.insert_at(0, &long_text).unwrap();
        assert_eq!(buf.len(), 2000);
        assert_eq!(buf.text(), long_text);
    }
}
