//! Thin Git command service built on the pure parsers.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use thiserror::Error;
use wok_process::{run, Cmd, ProcessError};

use crate::repo::{detect_repo_info, GitRepoInfo};
use crate::status::{parse_numstat, parse_status_porcelain_z, GitStatusFile, NumstatEntry};

/// Snapshot of changed files for one repository.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GitStatusSnapshot {
    /// Repository worktree root.
    pub worktree_root: PathBuf,
    /// Current branch or detached HEAD short hash.
    pub branch: Option<String>,
    /// Changed files, sorted by path.
    pub files: Vec<GitStatusFile>,
}

impl GitStatusSnapshot {
    /// Return true when there are no changed files.
    pub fn is_clean(&self) -> bool {
        self.files.is_empty()
    }
}

/// Errors from the Git command service.
#[derive(Debug, Error)]
pub enum GitServiceError {
    /// No Git repository could be found from the given path.
    #[error("not a git repository: {0}")]
    NotGitRepository(PathBuf),
    /// Git process execution failed.
    #[error("{0}")]
    Process(#[from] ProcessError),
    /// Git output was not valid UTF-8 where text output was expected.
    #[error("git output was not valid UTF-8")]
    InvalidUtf8,
}

/// Load changed-file status for the repository containing `cwd`.
pub fn load_status(cwd: &Path) -> Result<GitStatusSnapshot, GitServiceError> {
    let repo = detect_repo_info(cwd)
        .ok_or_else(|| GitServiceError::NotGitRepository(cwd.to_path_buf()))?;
    load_status_for_repo(&repo)
}

fn load_status_for_repo(repo: &GitRepoInfo) -> Result<GitStatusSnapshot, GitServiceError> {
    let status = run_git_bytes(
        &repo.worktree_root,
        &["status", "--porcelain=v1", "-z", "--untracked-files=all"],
    )?;
    let stats = combined_numstat(&repo.worktree_root)?;
    let files = parse_status_porcelain_z(&status, &stats);

    Ok(GitStatusSnapshot {
        worktree_root: repo.worktree_root.clone(),
        branch: repo.branch.clone(),
        files,
    })
}

fn combined_numstat(repo_root: &Path) -> Result<HashMap<String, NumstatEntry>, GitServiceError> {
    let unstaged = run_git_text(repo_root, &["diff", "--numstat"])?;
    let staged = run_git_text(repo_root, &["diff", "--cached", "--numstat"])?;
    let mut stats = parse_numstat(&unstaged);

    for (path, entry) in parse_numstat(&staged) {
        stats
            .entry(path)
            .and_modify(|existing| *existing = merge_numstat(*existing, entry))
            .or_insert(entry);
    }

    Ok(stats)
}

fn merge_numstat(left: NumstatEntry, right: NumstatEntry) -> NumstatEntry {
    NumstatEntry {
        additions: add_optional_counts(left.additions, right.additions),
        deletions: add_optional_counts(left.deletions, right.deletions),
        is_binary: left.is_binary || right.is_binary,
    }
}

fn add_optional_counts(left: Option<usize>, right: Option<usize>) -> Option<usize> {
    match (left, right) {
        (Some(left), Some(right)) => Some(left + right),
        (Some(value), None) | (None, Some(value)) => Some(value),
        (None, None) => None,
    }
}

fn run_git_bytes(repo_root: &Path, args: &[&str]) -> Result<Vec<u8>, GitServiceError> {
    Ok(run(Cmd::new("git").args(args).cwd(repo_root))?.stdout)
}

fn run_git_text(repo_root: &Path, args: &[&str]) -> Result<String, GitServiceError> {
    String::from_utf8(run_git_bytes(repo_root, args)?).map_err(|_| GitServiceError::InvalidUtf8)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_path(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("wok-git-service-{name}-{stamp}"))
    }

    #[test]
    fn non_repo_returns_not_git_repository() {
        let dir = unique_path("not-repo");
        fs::create_dir_all(&dir).expect("temp dir should be created");
        let err = load_status(&dir).expect_err("plain directory should not be a repo");
        assert!(matches!(err, GitServiceError::NotGitRepository(_)));
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn merge_numstat_adds_text_counts_and_preserves_binary() {
        let left = NumstatEntry {
            additions: Some(2),
            deletions: Some(3),
            is_binary: false,
        };
        let right = NumstatEntry {
            additions: Some(5),
            deletions: None,
            is_binary: true,
        };
        let merged = merge_numstat(left, right);
        assert_eq!(merged.additions, Some(7));
        assert_eq!(merged.deletions, Some(3));
        assert!(merged.is_binary);
    }
}
