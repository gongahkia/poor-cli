//! Cursor movement operations for the input editor.

use crate::buffer::InputBuffer;

/// Move cursor one character left.
pub fn move_left(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }
    if cursor.position > 0 {
        cursor.position -= 1;
    }
}

/// Move cursor one character right.
pub fn move_right(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let len = buf.len();
    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }
    if cursor.position < len {
        cursor.position += 1;
    }
}

/// Move cursor to previous word boundary.
pub fn move_word_left(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let text: Vec<char> = buf.text().chars().collect();
    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }

    let mut pos = cursor.position;
    // Skip whitespace/non-alnum going left
    while pos > 0 && !text[pos - 1].is_alphanumeric() {
        pos -= 1;
    }
    // Skip word chars going left
    while pos > 0 && text[pos - 1].is_alphanumeric() {
        pos -= 1;
    }
    cursor.position = pos;
}

/// Move cursor to next word boundary.
pub fn move_word_right(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let text: Vec<char> = buf.text().chars().collect();
    let len = text.len();
    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }

    let mut pos = cursor.position;
    // Skip word chars going right
    while pos < len && text[pos].is_alphanumeric() {
        pos += 1;
    }
    // Skip non-word chars going right
    while pos < len && !text[pos].is_alphanumeric() {
        pos += 1;
    }
    cursor.position = pos;
}

/// Move cursor to start of current line (smart home: toggles between col 0 and first non-space).
pub fn move_line_start(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let text = buf.text();
    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }

    // Find line start
    let chars: Vec<char> = text.chars().collect();
    let mut line_start = cursor.position;
    while line_start > 0 && chars[line_start - 1] != '\n' {
        line_start -= 1;
    }

    // Find first non-whitespace on this line
    let mut first_non_ws = line_start;
    while first_non_ws < chars.len() && chars[first_non_ws] != '\n' && chars[first_non_ws].is_whitespace() {
        first_non_ws += 1;
    }

    // Toggle: if at first_non_ws, go to line_start; otherwise go to first_non_ws
    if cursor.position == first_non_ws {
        cursor.position = line_start;
    } else {
        cursor.position = first_non_ws;
    }
}

/// Move cursor to end of current line.
pub fn move_line_end(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let text = buf.text();
    let chars: Vec<char> = text.chars().collect();
    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }

    let mut pos = cursor.position;
    while pos < chars.len() && chars[pos] != '\n' {
        pos += 1;
    }
    cursor.position = pos;
}

/// Move cursor up one line, maintaining column position.
pub fn move_up(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let text = buf.text();
    let positions = buf.cursor_positions();
    let (row, col) = positions[cursor_idx];

    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }

    if row == 0 {
        cursor.position = 0;
        return;
    }

    // Find target position on previous line
    let lines: Vec<&str> = text.split('\n').collect();
    let prev_line_len = lines[row - 1].len();
    let target_col = col.min(prev_line_len);

    // Calculate character offset
    let mut offset = 0;
    for (i, line) in lines.iter().enumerate() {
        if i == row - 1 {
            offset += target_col;
            break;
        }
        offset += line.len() + 1; // +1 for newline
    }
    cursor.position = offset;
}

/// Move cursor down one line, maintaining column position.
pub fn move_down(buf: &mut InputBuffer, cursor_idx: usize, extend_selection: bool) {
    let text = buf.text();
    let positions = buf.cursor_positions();
    let (row, col) = positions[cursor_idx];
    let lines: Vec<&str> = text.split('\n').collect();
    let buf_len = buf.len();

    // Pre-compute target position
    let target_pos = if row >= lines.len() - 1 {
        buf_len
    } else {
        let next_line_len = lines[row + 1].len();
        let target_col = col.min(next_line_len);
        let mut offset = 0;
        for (i, line) in lines.iter().enumerate() {
            if i == row + 1 {
                offset += target_col;
                break;
            }
            offset += line.len() + 1;
        }
        offset
    };

    let cursor = &mut buf.cursors_mut()[cursor_idx];
    if !extend_selection {
        cursor.anchor = None;
    } else if cursor.anchor.is_none() {
        cursor.anchor = Some(cursor.position);
    }
    cursor.position = target_pos;
}

/// Select all text in the buffer.
pub fn select_all(buf: &mut InputBuffer) {
    let len = buf.len();
    let cursor = &mut buf.cursors_mut()[0];
    cursor.anchor = Some(0);
    cursor.position = len;
}

/// Select the word at the given position.
pub fn select_word_at(buf: &mut InputBuffer, position: usize) {
    let text: Vec<char> = buf.text().chars().collect();
    if position >= text.len() {
        return;
    }

    let mut start = position;
    let mut end = position;

    // Expand to word boundaries
    while start > 0 && text[start - 1].is_alphanumeric() {
        start -= 1;
    }
    while end < text.len() && text[end].is_alphanumeric() {
        end += 1;
    }

    let cursor = &mut buf.cursors_mut()[0];
    cursor.anchor = Some(start);
    cursor.position = end;
}

/// Select an entire line.
pub fn select_line_at(buf: &mut InputBuffer, line: usize) {
    let text = buf.text();
    let lines: Vec<&str> = text.split('\n').collect();
    if line >= lines.len() {
        return;
    }

    let mut start = 0;
    for l in &lines[..line] {
        start += l.len() + 1;
    }
    let end = start + lines[line].len();

    let cursor = &mut buf.cursors_mut()[0];
    cursor.anchor = Some(start);
    cursor.position = end;
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_buffer(text: &str) -> InputBuffer {
        let mut buf = InputBuffer::new();
        buf.insert_at(0, text).unwrap();
        buf
    }

    #[test]
    fn test_move_word_left() {
        let mut buf = make_buffer("hello world");
        buf.cursors_mut()[0].position = 6;
        move_word_left(&mut buf, 0, false);
        assert_eq!(buf.cursors()[0].position, 0);
    }

    #[test]
    fn test_move_word_right() {
        let mut buf = make_buffer("hello world");
        buf.cursors_mut()[0].position = 0;
        move_word_right(&mut buf, 0, false);
        assert_eq!(buf.cursors()[0].position, 6);
    }

    #[test]
    fn test_move_line_start_smart_home() {
        let mut buf = make_buffer("  hello");
        buf.cursors_mut()[0].position = 5;
        move_line_start(&mut buf, 0, false);
        // Should go to first non-whitespace (position 2)
        assert_eq!(buf.cursors()[0].position, 2);
        // Pressing again goes to column 0
        move_line_start(&mut buf, 0, false);
        assert_eq!(buf.cursors()[0].position, 0);
    }

    #[test]
    fn test_select_all() {
        let mut buf = make_buffer("abc");
        select_all(&mut buf);
        assert_eq!(buf.cursors()[0].anchor, Some(0));
        assert_eq!(buf.cursors()[0].position, 3);
    }

    #[test]
    fn test_move_down_clamps_column() {
        let mut buf = make_buffer("long line\nhi");
        buf.cursors_mut()[0].position = 8; // col 8 on "long line"
        move_down(&mut buf, 0, false);
        // "hi" is only 2 chars, so clamp to end of line
        assert_eq!(buf.cursors()[0].position, 12); // 10 (line offset) + 2
    }

    #[test]
    fn test_move_up_from_first_line() {
        let mut buf = make_buffer("hello");
        buf.cursors_mut()[0].position = 3;
        move_up(&mut buf, 0, false);
        assert_eq!(buf.cursors()[0].position, 0);
    }

    #[test]
    fn test_extend_selection() {
        let mut buf = make_buffer("hello");
        buf.cursors_mut()[0].position = 2;
        move_right(&mut buf, 0, true);
        assert_eq!(buf.cursors()[0].position, 3);
        assert_eq!(buf.cursors()[0].anchor, Some(2));
    }
}
