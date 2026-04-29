//! Block filtering — predicate combinators over [`Block`].
//!
//! Filters are pure `Fn(&Block) -> bool` closures wrapped in [`BlockFilter`]
//! so callers can compose them with `and`/`or`/`not`. Built-ins cover the
//! common warp-style "show only failed", "matching regex", "cwd under",
//! "since command N" cases. Renderer consumes via [`apply`].
//!
//! Pure: no I/O, no allocation beyond the wrapper closures.

use std::path::Path;
use std::sync::Arc;

use regex::Regex;

use crate::block::Block;
use crate::block_id::BlockId;

type Predicate = Arc<dyn Fn(&Block) -> bool + Send + Sync>;

/// Composable block predicate.
#[derive(Clone)]
pub struct BlockFilter {
    inner: Predicate,
}

impl BlockFilter {
    /// Wrap an arbitrary closure.
    pub fn new<F>(f: F) -> Self
    where
        F: Fn(&Block) -> bool + Send + Sync + 'static,
    {
        Self { inner: Arc::new(f) }
    }

    /// Always-true filter.
    pub fn any() -> Self {
        Self::new(|_| true)
    }

    /// Always-false filter.
    pub fn none() -> Self {
        Self::new(|_| false)
    }

    /// Logical AND.
    pub fn and(self, other: Self) -> Self {
        let a = self.inner;
        let b = other.inner;
        Self::new(move |block| a(block) && b(block))
    }

    /// Logical OR.
    pub fn or(self, other: Self) -> Self {
        let a = self.inner;
        let b = other.inner;
        Self::new(move |block| a(block) || b(block))
    }

    /// Logical NOT.
    pub fn not(self) -> Self {
        let a = self.inner;
        Self::new(move |block| !a(block))
    }

    /// Evaluate against one block.
    pub fn matches(&self, block: &Block) -> bool {
        (self.inner)(block)
    }
}

impl std::fmt::Debug for BlockFilter {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("BlockFilter").finish_non_exhaustive()
    }
}

/// Apply a filter, returning indices of matching blocks (preserves order).
pub fn apply<'a, I>(blocks: I, filter: &BlockFilter) -> Vec<usize>
where
    I: IntoIterator<Item = &'a Block>,
{
    blocks
        .into_iter()
        .enumerate()
        .filter(|(_, b)| filter.matches(b))
        .map(|(i, _)| i)
        .collect()
}

// --- built-ins ---------------------------------------------------------------

/// Match blocks whose exit code is non-zero.
pub fn failed_only() -> BlockFilter {
    BlockFilter::new(|b| matches!(b.exit_code, Some(c) if c != 0))
}

/// Match blocks whose exit code is zero.
pub fn succeeded_only() -> BlockFilter {
    BlockFilter::new(|b| matches!(b.exit_code, Some(0)))
}

/// Match blocks still running (no exit code yet).
pub fn running_only() -> BlockFilter {
    BlockFilter::new(|b| b.exit_code.is_none())
}

/// Match blocks whose `command_text` matches `pattern`.
///
/// Returns `Err` if the regex fails to compile.
pub fn matching_regex(pattern: &str) -> Result<BlockFilter, regex::Error> {
    let re = Regex::new(pattern)?;
    Ok(BlockFilter::new(move |b| re.is_match(&b.command_text)))
}

/// Match blocks whose `cwd` is under `root` (path prefix match).
pub fn cwd_under(root: impl AsRef<Path>) -> BlockFilter {
    let root = root.as_ref().to_path_buf();
    BlockFilter::new(move |b| b.cwd.starts_with(&root))
}

/// Match blocks whose id is greater than `since` (i.e. "after this command").
pub fn since_id(since: BlockId) -> BlockFilter {
    BlockFilter::new(move |b| b.id > since)
}

/// Match blocks whose `command_text` literally contains `needle` (case-sensitive).
pub fn command_contains(needle: impl Into<String>) -> BlockFilter {
    let needle = needle.into();
    BlockFilter::new(move |b| b.command_text.contains(&needle))
}

/// Match bookmarked blocks.
pub fn bookmarked_only() -> BlockFilter {
    BlockFilter::new(|b| b.is_bookmarked)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::time::Instant;

    fn block(id: BlockId, exit: Option<i32>, cmd: &str, cwd: &str) -> Block {
        Block {
            id,
            prompt_text: String::new(),
            command_text: cmd.into(),
            output_start_row: 0,
            output_end_row: 0,
            exit_code: exit,
            start_time: Instant::now(),
            end_time: None,
            duration: None,
            is_collapsed: false,
            scroll_offset: 0,
            cwd: PathBuf::from(cwd),
            git_branch: None,
            git_dirty: None,
            is_bookmarked: false,
            trigger_highlights: Vec::new(),
        }
    }

    #[test]
    fn failed_only_filters_nonzero_exit() {
        let blocks = vec![
            block(1, Some(0), "ok", "/a"),
            block(2, Some(2), "fail", "/a"),
            block(3, None, "running", "/a"),
        ];
        let idx = apply(&blocks, &failed_only());
        assert_eq!(idx, vec![1]);
    }

    #[test]
    fn succeeded_only_filters_zero_exit() {
        let blocks = vec![
            block(1, Some(0), "ok", "/a"),
            block(2, Some(2), "fail", "/a"),
        ];
        let idx = apply(&blocks, &succeeded_only());
        assert_eq!(idx, vec![0]);
    }

    #[test]
    fn running_only_filters_no_exit() {
        let blocks = vec![block(1, Some(0), "x", "/a"), block(2, None, "y", "/a")];
        let idx = apply(&blocks, &running_only());
        assert_eq!(idx, vec![1]);
    }

    #[test]
    fn matching_regex_filters_command_text() {
        let blocks = vec![
            block(1, None, "git commit", "/a"),
            block(2, None, "ls -la", "/a"),
            block(3, None, "git push", "/a"),
        ];
        let f = matching_regex(r"^git ").unwrap();
        let idx = apply(&blocks, &f);
        assert_eq!(idx, vec![0, 2]);
    }

    #[test]
    fn matching_regex_invalid_returns_err() {
        assert!(matching_regex("[unclosed").is_err());
    }

    #[test]
    fn cwd_under_filters_path_prefix() {
        let blocks = vec![
            block(1, None, "x", "/home/u/proj"),
            block(2, None, "y", "/tmp"),
            block(3, None, "z", "/home/u/proj/sub"),
        ];
        let idx = apply(&blocks, &cwd_under("/home/u/proj"));
        assert_eq!(idx, vec![0, 2]);
    }

    #[test]
    fn since_id_filters_strict_greater() {
        let blocks = vec![
            block(1, None, "a", "/"),
            block(5, None, "b", "/"),
            block(7, None, "c", "/"),
        ];
        let idx = apply(&blocks, &since_id(5));
        assert_eq!(idx, vec![2]);
    }

    #[test]
    fn command_contains_substring_match() {
        let blocks = vec![
            block(1, None, "git commit", "/a"),
            block(2, None, "git push", "/a"),
            block(3, None, "ls", "/a"),
        ];
        let idx = apply(&blocks, &command_contains("git"));
        assert_eq!(idx, vec![0, 1]);
    }

    #[test]
    fn and_combines() {
        let blocks = vec![
            block(1, Some(0), "git ok", "/a"),
            block(2, Some(2), "git fail", "/a"),
            block(3, Some(2), "ls fail", "/a"),
        ];
        let f = failed_only().and(command_contains("git"));
        let idx = apply(&blocks, &f);
        assert_eq!(idx, vec![1]);
    }

    #[test]
    fn or_combines() {
        let blocks = vec![
            block(1, Some(0), "git ok", "/a"),
            block(2, Some(2), "ls fail", "/a"),
            block(3, Some(0), "ls ok", "/a"),
        ];
        let f = failed_only().or(command_contains("git"));
        let idx = apply(&blocks, &f);
        assert_eq!(idx, vec![0, 1]);
    }

    #[test]
    fn not_inverts() {
        let blocks = vec![
            block(1, Some(0), "ok", "/a"),
            block(2, Some(2), "fail", "/a"),
        ];
        let f = failed_only().not();
        let idx = apply(&blocks, &f);
        assert_eq!(idx, vec![0]);
    }

    #[test]
    fn any_and_none() {
        let blocks = vec![block(1, None, "x", "/a"), block(2, None, "y", "/b")];
        assert_eq!(apply(&blocks, &BlockFilter::any()).len(), 2);
        assert!(apply(&blocks, &BlockFilter::none()).is_empty());
    }

    #[test]
    fn bookmarked_only_filters() {
        let mut blocks = vec![block(1, None, "a", "/"), block(2, None, "b", "/")];
        blocks[1].is_bookmarked = true;
        let idx = apply(&blocks, &bookmarked_only());
        assert_eq!(idx, vec![1]);
    }
}
