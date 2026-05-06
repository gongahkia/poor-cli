//! Heuristic input classifier.
//!
//! Returns an [`InputKind`] for a buffer plus size/shape hints. Consumers use
//! it for paste bracketing decisions, NL-vs-shell annotation, and block
//! boundary hints. Pure: no I/O, no allocation beyond the result struct.
//!
//! Heuristics, in priority order:
//!   1. `Empty`         — trim is empty.
//!   2. `Heredoc`       — `<<` or `<<-` followed by an identifier/quoted tag.
//!   3. `Paste`         — multi-line and no shell-y first token, or very large.
//!   4. `Shell`         — starts w/ shell builtin/known cmd, or contains shell
//!                        metacharacters (`|&;><$` plus backticks) outside
//!                        quotes.
//!   5. `PossiblyNl`    — prose-ish: ≥3 words, sentence punctuation or no
//!                        metacharacters, no leading `/` or `./`.
//!   6. fallback        — `Shell`.

#![deny(missing_docs)]
#![forbid(unsafe_code)]

/// Classification result.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputKind {
    /// Empty (or whitespace-only) buffer.
    Empty,
    /// Heredoc-bearing shell input (`cmd <<TAG ... TAG`).
    Heredoc,
    /// Likely a paste (multi-line, large, or non-command-like).
    Paste,
    /// Looks like a shell command line.
    Shell,
    /// Looks like natural-language prose.
    PossiblyNl,
}

/// Side-channel hints surfaced alongside [`InputKind`].
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Hints {
    /// Total bytes (input length).
    pub bytes: usize,
    /// Number of newline characters.
    pub lines: usize,
    /// `true` if input contains CR+LF anywhere.
    pub has_crlf: bool,
    /// `true` if input contains a NUL byte.
    pub has_nul: bool,
}

/// Full classifier output.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Classification {
    /// Primary kind.
    pub kind: InputKind,
    /// Auxiliary hints.
    pub hints: Hints,
}

/// Threshold above which a single-line input is treated as a paste.
pub const PASTE_BYTE_THRESHOLD: usize = 4096;

/// Classify `buf`. Returns kind + hints in one pass.
pub fn classify(buf: &str) -> Classification {
    let hints = compute_hints(buf);
    let trimmed = buf.trim();
    if trimmed.is_empty() {
        return Classification {
            kind: InputKind::Empty,
            hints,
        };
    }
    if has_heredoc(trimmed) {
        return Classification {
            kind: InputKind::Heredoc,
            hints,
        };
    }
    if hints.bytes >= PASTE_BYTE_THRESHOLD {
        return Classification {
            kind: InputKind::Paste,
            hints,
        };
    }
    if hints.lines >= 2 && !looks_like_shell(trimmed) {
        return Classification {
            kind: InputKind::Paste,
            hints,
        };
    }
    if looks_like_shell(trimmed) {
        return Classification {
            kind: InputKind::Shell,
            hints,
        };
    }
    if looks_like_nl(trimmed) {
        return Classification {
            kind: InputKind::PossiblyNl,
            hints,
        };
    }
    Classification {
        kind: InputKind::Shell,
        hints,
    }
}

/// Convenience: kind only.
pub fn kind(buf: &str) -> InputKind {
    classify(buf).kind
}

fn compute_hints(buf: &str) -> Hints {
    let mut h = Hints {
        bytes: buf.len(),
        ..Hints::default()
    };
    let bytes = buf.as_bytes();
    for (i, &b) in bytes.iter().enumerate() {
        if b == b'\n' {
            h.lines += 1;
            if i > 0 && bytes[i - 1] == b'\r' {
                h.has_crlf = true;
            }
        } else if b == 0 {
            h.has_nul = true;
        }
    }
    h
}

fn has_heredoc(s: &str) -> bool {
    // scan for `<<` or `<<-` outside single-quoted spans, then a tag token.
    let bytes = s.as_bytes();
    let mut i = 0;
    let mut in_squote = false;
    while i + 1 < bytes.len() {
        let c = bytes[i];
        if c == b'\'' {
            in_squote = !in_squote;
            i += 1;
            continue;
        }
        if !in_squote && c == b'<' && bytes[i + 1] == b'<' {
            let mut j = i + 2;
            if j < bytes.len() && bytes[j] == b'-' {
                j += 1;
            }
            // skip horizontal whitespace
            while j < bytes.len() && (bytes[j] == b' ' || bytes[j] == b'\t') {
                j += 1;
            }
            // tag: optional quote then identifier-ish run
            if j < bytes.len() {
                let q = bytes[j];
                let kstart = if q == b'\'' || q == b'"' { j + 1 } else { j };
                let mut k = kstart;
                while k < bytes.len() && is_tag_byte(bytes[k]) {
                    k += 1;
                }
                if k > kstart {
                    return true;
                }
            }
        }
        i += 1;
    }
    false
}

fn is_tag_byte(b: u8) -> bool {
    b.is_ascii_alphanumeric() || b == b'_'
}

fn looks_like_shell(s: &str) -> bool {
    let first = first_token(s);
    if first.is_empty() {
        return false;
    }
    if first.starts_with("./") || first.starts_with('/') || first.starts_with("../") {
        return true;
    }
    if SHELL_CMDS.iter().any(|c| *c == first) {
        return true;
    }
    has_shell_meta(s)
}

fn looks_like_nl(s: &str) -> bool {
    if s.starts_with('/') || s.starts_with("./") {
        return false;
    }
    if has_shell_meta(s) {
        return false;
    }
    let words = s.split_whitespace().count();
    if words < 3 {
        return false;
    }
    let trailing = s.trim_end().chars().last();
    let ends_punct = matches!(trailing, Some('.') | Some('?') | Some('!'));
    ends_punct || s.contains(' ')
}

fn first_token(s: &str) -> &str {
    s.split_whitespace().next().unwrap_or("")
}

fn has_shell_meta(s: &str) -> bool {
    // top-level metas only; ignore within single quotes.
    let mut in_squote = false;
    let mut in_dquote = false;
    for b in s.bytes() {
        match b {
            b'\'' if !in_dquote => in_squote = !in_squote,
            b'"' if !in_squote => in_dquote = !in_dquote,
            b'|' | b'&' | b';' | b'>' | b'<' | b'$' | b'`' if !in_squote && !in_dquote => {
                return true;
            }
            _ => {}
        }
    }
    false
}

const SHELL_CMDS: &[&str] = &[
    "ls",
    "cd",
    "pwd",
    "echo",
    "cat",
    "cp",
    "mv",
    "rm",
    "mkdir",
    "rmdir",
    "touch",
    "ln",
    "chmod",
    "chown",
    "ps",
    "kill",
    "top",
    "htop",
    "df",
    "du",
    "find",
    "grep",
    "rg",
    "ag",
    "fd",
    "sed",
    "awk",
    "tr",
    "cut",
    "sort",
    "uniq",
    "wc",
    "head",
    "tail",
    "less",
    "more",
    "tar",
    "zip",
    "unzip",
    "gzip",
    "bzip2",
    "curl",
    "wget",
    "ssh",
    "scp",
    "rsync",
    "git",
    "svn",
    "hg",
    "make",
    "cmake",
    "cargo",
    "rustc",
    "rustup",
    "go",
    "node",
    "npm",
    "pnpm",
    "yarn",
    "deno",
    "bun",
    "python",
    "python3",
    "pip",
    "pipx",
    "ruby",
    "gem",
    "bundle",
    "java",
    "javac",
    "mvn",
    "gradle",
    "docker",
    "podman",
    "kubectl",
    "helm",
    "terraform",
    "ansible",
    "vagrant",
    "vim",
    "nvim",
    "emacs",
    "nano",
    "code",
    "tmux",
    "screen",
    "fish",
    "bash",
    "zsh",
    "sh",
    "pwsh",
    "powershell",
    "exit",
    "logout",
    "history",
    "alias",
    "unalias",
    "export",
    "unset",
    "source",
    "which",
    "whereis",
    "type",
    "man",
    "help",
    "true",
    "false",
    "yes",
    "no",
    "test",
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_classifies_as_empty() {
        assert_eq!(kind(""), InputKind::Empty);
        assert_eq!(kind("   \n\t"), InputKind::Empty);
    }

    #[test]
    fn known_command_is_shell() {
        assert_eq!(kind("ls -la"), InputKind::Shell);
        assert_eq!(kind("git status"), InputKind::Shell);
        assert_eq!(kind("cargo build --release"), InputKind::Shell);
    }

    #[test]
    fn absolute_path_is_shell() {
        assert_eq!(kind("/usr/bin/foo --bar"), InputKind::Shell);
        assert_eq!(kind("./run.sh"), InputKind::Shell);
    }

    #[test]
    fn metacharacters_force_shell() {
        assert_eq!(kind("foo | bar"), InputKind::Shell);
        assert_eq!(kind("foo && bar"), InputKind::Shell);
        assert_eq!(kind("echo $HOME > out.txt"), InputKind::Shell);
        assert_eq!(kind("echo `date`"), InputKind::Shell);
    }

    #[test]
    fn metas_in_single_quotes_are_ignored() {
        // first token is an unknown command and metas only inside quotes
        // → falls through to NL heuristic, which needs ≥3 words.
        assert_eq!(kind("foo 'a | b' x y"), InputKind::PossiblyNl);
    }

    #[test]
    fn heredoc_detected() {
        assert_eq!(kind("cat <<EOF\nhi\nEOF"), InputKind::Heredoc);
        assert_eq!(kind("cat <<- TAG\nhi\nTAG"), InputKind::Heredoc);
        assert_eq!(kind("cat <<'EOF'\nhi\nEOF"), InputKind::Heredoc);
    }

    #[test]
    fn heredoc_inside_quote_ignored() {
        // `<<` inside single quotes does not begin a heredoc.
        assert_eq!(kind("echo '<<EOF'"), InputKind::Shell);
    }

    #[test]
    fn multiline_non_command_is_paste() {
        let buf = "lorem ipsum dolor sit amet\nconsectetur adipiscing elit\n";
        assert_eq!(kind(buf), InputKind::Paste);
    }

    #[test]
    fn very_large_single_line_is_paste() {
        let big = "a".repeat(PASTE_BYTE_THRESHOLD + 1);
        assert_eq!(kind(&big), InputKind::Paste);
    }

    #[test]
    fn nl_prose_classified() {
        assert_eq!(
            kind("how do I find files modified today?"),
            InputKind::PossiblyNl
        );
        assert_eq!(
            kind("show me the running processes."),
            InputKind::PossiblyNl
        );
    }

    #[test]
    fn hints_count_lines_and_crlf() {
        let c = classify("a\r\nb\nc");
        assert_eq!(c.hints.bytes, 6);
        assert_eq!(c.hints.lines, 2);
        assert!(c.hints.has_crlf);
        assert!(!c.hints.has_nul);
    }

    #[test]
    fn hints_detect_nul() {
        let c = classify("ab\0cd");
        assert!(c.hints.has_nul);
    }

    #[test]
    fn shell_multiline_still_shell() {
        // multi-line but starts w/ a known cmd → still shell.
        assert_eq!(kind("git log\ngit status"), InputKind::Shell);
    }
}
