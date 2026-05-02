//! Parsers and models for `git status --porcelain=v1 -z` and `git diff --numstat`.

use std::collections::HashMap;

/// Per-file line statistics from `git diff --numstat`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct NumstatEntry {
    /// Added lines, or `None` for binary files.
    pub additions: Option<usize>,
    /// Deleted lines, or `None` for binary files.
    pub deletions: Option<usize>,
    /// Whether Git reported the file as binary.
    pub is_binary: bool,
}

/// One changed file from porcelain status output.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GitStatusFile {
    /// Current path. For renames and copies this is the destination path.
    pub path: String,
    /// Previous path for renames and copies.
    pub old_path: Option<String>,
    /// Index status column.
    pub index_status: char,
    /// Working-tree status column.
    pub worktree_status: char,
    /// Added lines from numstat, if available.
    pub additions: Option<usize>,
    /// Deleted lines from numstat, if available.
    pub deletions: Option<usize>,
    /// Whether the file is binary.
    pub is_binary: bool,
}

impl GitStatusFile {
    /// Return true when the index column represents a staged change.
    pub fn is_staged(&self) -> bool {
        matches!(self.index_status, 'A' | 'M' | 'D' | 'R' | 'C')
    }

    /// Return true when the working-tree column represents an unstaged change.
    pub fn is_unstaged(&self) -> bool {
        matches!(self.worktree_status, 'M' | 'D' | '?')
            || (self.index_status == '?' && self.worktree_status == '?')
    }

    /// Compact status label suitable for changed-file lists.
    pub fn status_text(&self) -> char {
        match (self.index_status, self.worktree_status) {
            ('A', _) | (_, 'A') => 'A',
            ('D', _) | (_, 'D') => 'D',
            ('R', _) | (_, 'R') => 'R',
            ('C', _) | (_, 'C') => 'C',
            ('M', _) | (_, 'M') => 'M',
            ('U', _) | (_, 'U') => 'U',
            _ => '?',
        }
    }

    /// Compact status label for the index column.
    pub fn staged_status_text(&self) -> char {
        self.index_status
    }

    /// Compact status label for the working-tree column.
    pub fn unstaged_status_text(&self) -> char {
        if self.index_status == '?' && self.worktree_status == '?' {
            'U'
        } else {
            self.worktree_status
        }
    }
}

/// Parse porcelain-v1 NUL-delimited status output.
///
/// For rename/copy records, Git emits the source path in the status token and
/// the destination path as the following NUL-delimited token.
pub fn parse_status_porcelain_z(
    data: &[u8],
    stats: &HashMap<String, NumstatEntry>,
) -> Vec<GitStatusFile> {
    if data.is_empty() {
        return Vec::new();
    }

    let mut tokens = data
        .split(|byte| *byte == 0)
        .filter(|token| !token.is_empty())
        .map(|token| String::from_utf8_lossy(token).into_owned())
        .peekable();

    let mut files = Vec::new();
    while let Some(token) = tokens.next() {
        let Some((index_status, worktree_status, path)) = parse_status_token(&token) else {
            continue;
        };

        let is_rename_or_copy =
            matches!(index_status, 'R' | 'C') || matches!(worktree_status, 'R' | 'C');
        let (path, old_path) = if is_rename_or_copy {
            let new_path = tokens.next().unwrap_or_else(|| path.clone());
            (new_path, Some(path))
        } else {
            (path, None)
        };

        let stat = stats.get(&path);
        files.push(GitStatusFile {
            path,
            old_path,
            index_status,
            worktree_status,
            additions: stat.and_then(|entry| entry.additions),
            deletions: stat.and_then(|entry| entry.deletions),
            is_binary: stat.is_some_and(|entry| entry.is_binary),
        });
    }

    files.sort_by(|left, right| left.path.cmp(&right.path));
    files
}

fn parse_status_token(token: &str) -> Option<(char, char, String)> {
    let mut chars = token.chars();
    let index_status = chars.next()?;
    let worktree_status = chars.next()?;
    let separator = chars.next()?;
    if separator != ' ' {
        return None;
    }
    let path: String = chars.collect();
    (!path.is_empty()).then_some((index_status, worktree_status, path))
}

/// Parse `git diff --numstat` output into a path-indexed map.
///
/// The map contains both the raw path and the normalized destination path for
/// rename rows, allowing status records to join against either representation.
pub fn parse_numstat(output: &str) -> HashMap<String, NumstatEntry> {
    let mut stats = HashMap::new();

    for line in output.lines().filter(|line| !line.is_empty()) {
        let fields: Vec<&str> = line.splitn(3, '\t').collect();
        if fields.len() != 3 {
            continue;
        }

        let additions = fields[0].parse::<usize>().ok();
        let deletions = fields[1].parse::<usize>().ok();
        let is_binary = fields[0] == "-" || fields[1] == "-";
        let entry = NumstatEntry {
            additions,
            deletions,
            is_binary,
        };

        let raw_path = fields[2].to_string();
        let normalized_path = normalize_numstat_path(&raw_path);
        stats.insert(raw_path, entry);
        stats.insert(normalized_path, entry);
    }

    stats
}

/// Normalize a numstat rename path to its destination path.
///
/// Handles both `old => new` and brace-renames such as
/// `src/{old => new}/file.rs`.
pub fn normalize_numstat_path(raw_path: &str) -> String {
    if let (Some(brace_start), Some(brace_end), Some(arrow)) = (
        raw_path.find('{'),
        raw_path.rfind('}'),
        raw_path.find(" => "),
    ) {
        if brace_start < arrow && arrow < brace_end {
            let prefix = &raw_path[..brace_start];
            let right = &raw_path[arrow + 4..brace_end];
            let suffix = &raw_path[brace_end + 1..];
            return format!("{prefix}{right}{suffix}");
        }
    }

    raw_path.find(" => ").map_or_else(
        || raw_path.to_string(),
        |arrow| raw_path[arrow + 4..].to_string(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_porcelain_returns_empty() {
        let result = parse_status_porcelain_z(&[], &HashMap::new());
        assert!(result.is_empty());
    }

    #[test]
    fn porcelain_parses_modified_file() {
        let result = parse_status_porcelain_z(b"M  src/file.rs\0", &HashMap::new());
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].path, "src/file.rs");
        assert_eq!(result[0].index_status, 'M');
        assert_eq!(result[0].worktree_status, ' ');
        assert_eq!(result[0].old_path, None);
    }

    #[test]
    fn porcelain_parses_untracked_file() {
        let result = parse_status_porcelain_z(b"?? newfile.txt\0", &HashMap::new());
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].path, "newfile.txt");
        assert_eq!(result[0].index_status, '?');
        assert_eq!(result[0].worktree_status, '?');
        assert!(result[0].is_unstaged());
        assert_eq!(result[0].unstaged_status_text(), 'U');
    }

    #[test]
    fn porcelain_parses_staged_rename() {
        let result = parse_status_porcelain_z(b"R  old.rs\0new.rs\0", &HashMap::new());
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].path, "new.rs");
        assert_eq!(result[0].old_path.as_deref(), Some("old.rs"));
        assert_eq!(result[0].index_status, 'R');
        assert_eq!(result[0].status_text(), 'R');
    }

    #[test]
    fn porcelain_parses_unstaged_rename() {
        let result = parse_status_porcelain_z(b" R old.rs\0new.rs\0", &HashMap::new());
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].path, "new.rs");
        assert_eq!(result[0].old_path.as_deref(), Some("old.rs"));
        assert_eq!(result[0].index_status, ' ');
        assert_eq!(result[0].worktree_status, 'R');
    }

    #[test]
    fn porcelain_merges_numstat_by_current_path() {
        let mut stats = HashMap::new();
        stats.insert(
            "file.rs".to_string(),
            NumstatEntry {
                additions: Some(10),
                deletions: Some(3),
                is_binary: false,
            },
        );
        let result = parse_status_porcelain_z(b"M  file.rs\0", &stats);
        assert_eq!(result[0].additions, Some(10));
        assert_eq!(result[0].deletions, Some(3));
        assert!(!result[0].is_binary);
    }

    #[test]
    fn porcelain_sorts_output_by_path() {
        let result = parse_status_porcelain_z(b"M  z.rs\0M  a.rs\0", &HashMap::new());
        assert_eq!(result[0].path, "a.rs");
        assert_eq!(result[1].path, "z.rs");
    }

    #[test]
    fn porcelain_skips_malformed_tokens() {
        let result = parse_status_porcelain_z(b"M  valid.rs\0ab\0", &HashMap::new());
        assert_eq!(result.len(), 1);
        assert_eq!(result[0].path, "valid.rs");
    }

    #[test]
    fn numstat_parses_basic_entry() {
        let stats = parse_numstat("5\t3\tfile.rs");
        assert_eq!(stats["file.rs"].additions, Some(5));
        assert_eq!(stats["file.rs"].deletions, Some(3));
        assert!(!stats["file.rs"].is_binary);
    }

    #[test]
    fn numstat_parses_binary_entry() {
        let stats = parse_numstat("-\t-\tbinary.png");
        assert_eq!(stats["binary.png"].additions, None);
        assert_eq!(stats["binary.png"].deletions, None);
        assert!(stats["binary.png"].is_binary);
    }

    #[test]
    fn numstat_parses_multiple_entries() {
        let stats = parse_numstat("5\t3\tfile1.rs\n10\t0\tfile2.rs\n");
        assert!(stats.contains_key("file1.rs"));
        assert_eq!(stats["file2.rs"].additions, Some(10));
    }

    #[test]
    fn numstat_normalizes_simple_rename() {
        assert_eq!(normalize_numstat_path("old.rs => new.rs"), "new.rs");
    }

    #[test]
    fn numstat_normalizes_brace_rename() {
        assert_eq!(
            normalize_numstat_path("src/{old => new}/file.rs"),
            "src/new/file.rs"
        );
    }

    #[test]
    fn numstat_keeps_non_rename_path() {
        assert_eq!(normalize_numstat_path("file.rs"), "file.rs");
    }
}
