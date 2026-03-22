//! Bracket matching for the input editor.

/// Bracket pairs to match.
const BRACKET_PAIRS: &[(char, char)] = &[('(', ')'), ('[', ']'), ('{', '}')];

/// Find the matching bracket for the character at the given position.
///
/// Returns `None` if the character at `position` (or `position - 1`) is not
/// a bracket, or if no match is found.
pub fn find_matching_bracket(text: &str, position: usize) -> Option<usize> {
    let chars: Vec<char> = text.chars().collect();

    // Try current position, then position - 1
    for &pos in &[position, position.wrapping_sub(1)] {
        if pos >= chars.len() {
            continue;
        }
        let ch = chars[pos];
        if let Some(result) = try_match_at(&chars, pos, ch) {
            return Some(result);
        }
    }
    None
}

fn try_match_at(chars: &[char], pos: usize, ch: char) -> Option<usize> {
    // Check if it's an opening bracket
    for &(open, close) in BRACKET_PAIRS {
        if ch == open {
            return scan_forward(chars, pos, open, close);
        }
        if ch == close {
            return scan_backward(chars, pos, open, close);
        }
    }
    None
}

fn is_in_quote(chars: &[char], pos: usize) -> bool {
    let mut in_single = false;
    let mut in_double = false;
    for &ch in &chars[..pos] {
        if ch == '\'' && !in_double {
            in_single = !in_single;
        } else if ch == '"' && !in_single {
            in_double = !in_double;
        }
    }
    in_single || in_double
}

fn scan_forward(chars: &[char], start: usize, open: char, close: char) -> Option<usize> {
    // If the bracket itself is inside quotes, no match
    if is_in_quote(chars, start) {
        return None;
    }

    let mut depth = 0;
    let mut in_single_quote = false;
    let mut in_double_quote = false;

    for (i, &ch) in chars.iter().enumerate().skip(start) {
        if ch == '\'' && !in_double_quote {
            in_single_quote = !in_single_quote;
            continue;
        }
        if ch == '"' && !in_single_quote {
            in_double_quote = !in_double_quote;
            continue;
        }

        if in_single_quote || in_double_quote {
            continue;
        }

        if ch == open {
            depth += 1;
        } else if ch == close {
            depth -= 1;
            if depth == 0 {
                return Some(i);
            }
        }
    }
    None
}

fn scan_backward(chars: &[char], start: usize, open: char, close: char) -> Option<usize> {
    if is_in_quote(chars, start) {
        return None;
    }

    let mut depth = 0;
    let mut in_single_quote = false;
    let mut in_double_quote = false;

    for i in (0..=start).rev() {
        let ch = chars[i];

        if ch == '\'' && !in_double_quote {
            in_single_quote = !in_single_quote;
            continue;
        }
        if ch == '"' && !in_single_quote {
            in_double_quote = !in_double_quote;
            continue;
        }

        if in_single_quote || in_double_quote {
            continue;
        }

        if ch == close {
            depth += 1;
        } else if ch == open {
            depth -= 1;
            if depth == 0 {
                return Some(i);
            }
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_matching_parens() {
        let text = "echo $(cat file)";
        // Position 5 is the '$' -- position 6 is '('
        assert_eq!(find_matching_bracket(text, 6), Some(15)); // matching ')'
    }

    #[test]
    fn test_nested_brackets() {
        let text = "echo $((1+2))";
        // Outer ( is at position 6
        assert_eq!(find_matching_bracket(text, 6), Some(12));
    }

    #[test]
    fn test_unmatched_bracket() {
        let text = "echo (foo";
        assert_eq!(find_matching_bracket(text, 5), None);
    }

    #[test]
    fn test_brackets_inside_quotes_ignored() {
        let text = "echo '(not a bracket)'";
        // The ( at pos 6 is inside quotes, should not match
        // This tests the quote-skipping logic
        assert_eq!(find_matching_bracket(text, 6), None);
    }

    #[test]
    fn test_square_brackets() {
        let text = "arr[0]";
        assert_eq!(find_matching_bracket(text, 3), Some(5));
    }

    #[test]
    fn test_curly_braces() {
        let text = "${VAR}";
        assert_eq!(find_matching_bracket(text, 1), Some(5));
    }
}
