//! Syntax highlighting for shell commands in the input editor.

use wok_terminal::shell::ShellType;

/// A highlighted span within the input text.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HighlightSpan {
    /// Start byte offset.
    pub start: usize,
    /// End byte offset (exclusive).
    pub end: usize,
    /// The kind of syntax element.
    pub kind: SpanKind,
}

/// The type of syntax element for coloring.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SpanKind {
    /// Command name (first word).
    Command,
    /// Argument to a command.
    Argument,
    /// Flag (starts with - or --).
    Flag,
    /// File path (contains / or ~).
    Path,
    /// Quoted string.
    String,
    /// Numeric literal.
    Number,
    /// Pipe operator |.
    Pipe,
    /// Redirect operators > >> <.
    Redirect,
    /// Variable reference ($VAR).
    Variable,
    /// Comment (starts with #).
    Comment,
    /// Invalid/unknown command.
    Error,
    /// Default/unclassified text.
    Default,
}

/// Tokenize and highlight a shell command string.
pub fn highlight(text: &str, _shell: &ShellType) -> Vec<HighlightSpan> {
    if text.is_empty() {
        return Vec::new();
    }

    let mut spans = Vec::new();
    let mut pos = 0;
    let chars: Vec<char> = text.chars().collect();
    let mut is_first_token = true;
    let mut after_pipe = false;

    while pos < chars.len() {
        // Skip whitespace
        if chars[pos].is_whitespace() {
            pos += 1;
            continue;
        }

        // Comment
        if chars[pos] == '#' {
            let start = pos;
            while pos < chars.len() && chars[pos] != '\n' {
                pos += 1;
            }
            spans.push(HighlightSpan {
                start,
                end: pos,
                kind: SpanKind::Comment,
            });
            continue;
        }

        // Pipe
        if chars[pos] == '|' {
            spans.push(HighlightSpan {
                start: pos,
                end: pos + 1,
                kind: SpanKind::Pipe,
            });
            pos += 1;
            is_first_token = true;
            after_pipe = true;
            continue;
        }

        // Redirect
        if chars[pos] == '>' || chars[pos] == '<' {
            let start = pos;
            pos += 1;
            if pos < chars.len() && chars[pos] == '>' {
                pos += 1; // >>
            }
            spans.push(HighlightSpan {
                start,
                end: pos,
                kind: SpanKind::Redirect,
            });
            continue;
        }

        // Quoted string
        if chars[pos] == '"' || chars[pos] == '\'' {
            let quote = chars[pos];
            let start = pos;
            pos += 1;
            while pos < chars.len() && chars[pos] != quote {
                if chars[pos] == '\\' && quote == '"' {
                    pos += 1; // skip escaped char
                }
                pos += 1;
            }
            if pos < chars.len() {
                pos += 1; // closing quote
            }
            spans.push(HighlightSpan {
                start,
                end: pos,
                kind: SpanKind::String,
            });
            continue;
        }

        // Variable
        if chars[pos] == '$' {
            let start = pos;
            pos += 1;
            if pos < chars.len() && chars[pos] == '{' {
                pos += 1;
                while pos < chars.len() && chars[pos] != '}' {
                    pos += 1;
                }
                if pos < chars.len() {
                    pos += 1;
                }
            } else if pos < chars.len() && chars[pos] == '(' {
                // subshell: skip to matching )
                let mut depth = 1;
                pos += 1;
                while pos < chars.len() && depth > 0 {
                    if chars[pos] == '(' {
                        depth += 1;
                    } else if chars[pos] == ')' {
                        depth -= 1;
                    }
                    pos += 1;
                }
            } else {
                while pos < chars.len() && (chars[pos].is_alphanumeric() || chars[pos] == '_') {
                    pos += 1;
                }
            }
            spans.push(HighlightSpan {
                start,
                end: pos,
                kind: SpanKind::Variable,
            });
            continue;
        }

        // Regular token
        let start = pos;
        while pos < chars.len() && !chars[pos].is_whitespace() && !"|><".contains(chars[pos]) {
            pos += 1;
        }
        let token: String = chars[start..pos].iter().collect();

        let kind = if is_first_token || after_pipe {
            is_first_token = false;
            after_pipe = false;
            SpanKind::Command
        } else if token.starts_with("--") || token.starts_with('-') {
            SpanKind::Flag
        } else if token.contains('/') || token.starts_with('~') {
            SpanKind::Path
        } else if token.chars().all(|c| c.is_ascii_digit() || c == '.') {
            SpanKind::Number
        } else {
            SpanKind::Argument
        };

        spans.push(HighlightSpan {
            start,
            end: pos,
            kind,
        });
    }

    spans
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_highlight_simple_command() {
        let spans = highlight("git commit -m 'hello'", &ShellType::Bash);
        assert_eq!(spans[0].kind, SpanKind::Command);
        assert_eq!(spans[0].start, 0);
        assert_eq!(spans[0].end, 3);
        assert_eq!(spans[1].kind, SpanKind::Argument);
        assert_eq!(spans[2].kind, SpanKind::Flag);
        assert_eq!(spans[3].kind, SpanKind::String);
    }

    #[test]
    fn test_highlight_pipe() {
        let spans = highlight("cat /tmp/file | grep 'err'", &ShellType::Bash);
        assert_eq!(spans[0].kind, SpanKind::Command); // cat
        assert_eq!(spans[1].kind, SpanKind::Path); // /tmp/file
        assert_eq!(spans[2].kind, SpanKind::Pipe); // |
        assert_eq!(spans[3].kind, SpanKind::Command); // grep
        assert_eq!(spans[4].kind, SpanKind::String); // 'err'
    }

    #[test]
    fn test_highlight_variable() {
        let spans = highlight("echo $HOME", &ShellType::Bash);
        assert_eq!(spans[0].kind, SpanKind::Command);
        assert_eq!(spans[1].kind, SpanKind::Variable);
    }

    #[test]
    fn test_highlight_redirect() {
        let spans = highlight("echo hello > output.txt", &ShellType::Bash);
        assert!(spans.iter().any(|s| s.kind == SpanKind::Redirect));
    }

    #[test]
    fn test_highlight_comment() {
        let spans = highlight("echo hi # comment", &ShellType::Bash);
        assert!(spans.iter().any(|s| s.kind == SpanKind::Comment));
    }
}
