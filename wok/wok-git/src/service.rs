//! Thin Git command service built on the pure parsers.

use std::collections::HashMap;
use std::path::{Path, PathBuf};

use thiserror::Error;
use wok_process::{run, Cmd, ProcessError};

use crate::diff::{collapse_context_rows, parse_rows, DiffDisplayRow};
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

/// Parsed diff for one changed Git file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GitFileDiff {
    /// Repository worktree root.
    pub worktree_root: PathBuf,
    /// Current branch or detached HEAD short hash.
    pub branch: Option<String>,
    /// Repository-relative file path.
    pub path: String,
    /// Display-ready diff rows.
    pub rows: Vec<DiffDisplayRow>,
    /// Added line count.
    pub additions: usize,
    /// Deleted line count.
    pub deletions: usize,
}

/// One `git worktree list --porcelain` entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GitWorktree {
    /// Worktree root path.
    pub path: PathBuf,
    /// Current branch name, when attached to a branch.
    pub branch: Option<String>,
    /// HEAD commit hash, when Git reports one.
    pub head: Option<String>,
    /// Whether this is a bare worktree.
    pub is_bare: bool,
    /// Whether this worktree is detached.
    pub is_detached: bool,
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

/// Load a parsed diff for `path` in the repository containing `cwd`.
///
/// Both unstaged and staged hunks are included. Untracked files usually produce
/// an empty diff because Git has no index baseline for them yet.
pub fn load_file_diff(cwd: &Path, path: &str) -> Result<GitFileDiff, GitServiceError> {
    let repo = detect_repo_info(cwd)
        .ok_or_else(|| GitServiceError::NotGitRepository(cwd.to_path_buf()))?;
    let patch = combined_file_diff(&repo.worktree_root, path)?;
    let parsed = parse_rows(&patch);
    let rows = collapse_context_rows(&parsed.rows);

    Ok(GitFileDiff {
        worktree_root: repo.worktree_root,
        branch: repo.branch,
        path: path.to_string(),
        rows,
        additions: parsed.additions,
        deletions: parsed.deletions,
    })
}

/// List Git worktrees for the repository containing `cwd`.
pub fn load_worktrees(cwd: &Path) -> Result<Vec<GitWorktree>, GitServiceError> {
    let repo = detect_repo_info(cwd)
        .ok_or_else(|| GitServiceError::NotGitRepository(cwd.to_path_buf()))?;
    let output = run_git_text(&repo.worktree_root, &["worktree", "list", "--porcelain"])?;
    Ok(parse_worktree_list(&output))
}

/// Stage one repository-relative path.
pub fn stage_path(cwd: &Path, path: &str) -> Result<(), GitServiceError> {
    let repo = detect_repo_info(cwd)
        .ok_or_else(|| GitServiceError::NotGitRepository(cwd.to_path_buf()))?;
    run_git_bytes_dynamic(&repo.worktree_root, ["add", "--"], [path]).map(|_| ())
}

/// Remove one repository-relative path from the index.
pub fn unstage_path(cwd: &Path, path: &str) -> Result<(), GitServiceError> {
    let repo = detect_repo_info(cwd)
        .ok_or_else(|| GitServiceError::NotGitRepository(cwd.to_path_buf()))?;
    run_git_bytes_dynamic(&repo.worktree_root, ["restore", "--staged", "--"], [path]).map(|_| ())
}

/// Discard local changes for one repository-relative path.
///
/// For untracked paths this uses `git clean -f -- <path>`. For tracked paths it
/// restores both index and worktree state from HEAD.
pub fn discard_path(cwd: &Path, path: &str) -> Result<(), GitServiceError> {
    let repo = detect_repo_info(cwd)
        .ok_or_else(|| GitServiceError::NotGitRepository(cwd.to_path_buf()))?;
    let snapshot = load_status_for_repo(&repo)?;
    let is_untracked = snapshot
        .files
        .iter()
        .any(|file| file.path == path && file.index_status == '?' && file.worktree_status == '?');

    if is_untracked {
        run_git_bytes_dynamic(&repo.worktree_root, ["clean", "-f", "--"], [path]).map(|_| ())
    } else {
        run_git_bytes_dynamic(
            &repo.worktree_root,
            ["restore", "--staged", "--worktree", "--"],
            [path],
        )
        .map(|_| ())
    }
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

fn combined_file_diff(repo_root: &Path, path: &str) -> Result<String, GitServiceError> {
    let unstaged = run_git_text_dynamic(repo_root, ["diff", "--"], [path])?;
    let staged = run_git_text_dynamic(repo_root, ["diff", "--cached", "--"], [path])?;
    Ok(if staged.trim().is_empty() {
        unstaged
    } else if unstaged.trim().is_empty() {
        staged
    } else {
        format!("{staged}\n{unstaged}")
    })
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

fn run_git_bytes_dynamic<'a, A, P>(
    repo_root: &Path,
    args: A,
    pathspecs: P,
) -> Result<Vec<u8>, GitServiceError>
where
    A: IntoIterator<Item = &'a str>,
    P: IntoIterator<Item = &'a str>,
{
    Ok(run(Cmd::new("git").args(args).args(pathspecs).cwd(repo_root))?.stdout)
}

fn run_git_text(repo_root: &Path, args: &[&str]) -> Result<String, GitServiceError> {
    String::from_utf8(run_git_bytes(repo_root, args)?).map_err(|_| GitServiceError::InvalidUtf8)
}

fn run_git_text_dynamic<'a, A, P>(
    repo_root: &Path,
    args: A,
    pathspecs: P,
) -> Result<String, GitServiceError>
where
    A: IntoIterator<Item = &'a str>,
    P: IntoIterator<Item = &'a str>,
{
    String::from_utf8(run_git_bytes_dynamic(repo_root, args, pathspecs)?)
        .map_err(|_| GitServiceError::InvalidUtf8)
}

fn parse_worktree_list(output: &str) -> Vec<GitWorktree> {
    let mut worktrees = Vec::new();
    let mut current: Option<GitWorktree> = None;

    for line in output.lines() {
        if line.is_empty() {
            if let Some(worktree) = current.take() {
                worktrees.push(worktree);
            }
            continue;
        }

        if let Some(path) = line.strip_prefix("worktree ") {
            if let Some(worktree) = current.replace(GitWorktree {
                path: PathBuf::from(path),
                branch: None,
                head: None,
                is_bare: false,
                is_detached: false,
            }) {
                worktrees.push(worktree);
            }
            continue;
        }

        let Some(worktree) = current.as_mut() else {
            continue;
        };
        if let Some(head) = line.strip_prefix("HEAD ") {
            worktree.head = Some(head.to_string());
        } else if let Some(branch) = line.strip_prefix("branch ") {
            worktree.branch = Some(
                branch
                    .strip_prefix("refs/heads/")
                    .unwrap_or(branch)
                    .to_string(),
            );
        } else if line == "bare" {
            worktree.is_bare = true;
        } else if line == "detached" {
            worktree.is_detached = true;
        }
    }

    if let Some(worktree) = current {
        worktrees.push(worktree);
    }

    worktrees
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

    fn init_repo(name: &str) -> PathBuf {
        let dir = unique_path(name);
        fs::create_dir_all(&dir).expect("temp dir should be created");
        run(Cmd::new("git").args(["init"]).cwd(&dir)).expect("git init should pass");
        run(Cmd::new("git")
            .args(["config", "user.email", "wok@example.test"])
            .cwd(&dir))
        .expect("git config email should pass");
        run(Cmd::new("git")
            .args(["config", "user.name", "Wok Test"])
            .cwd(&dir))
        .expect("git config name should pass");
        dir
    }

    fn commit_file(dir: &Path, path: &str, contents: &str) {
        fs::write(dir.join(path), contents).expect("file should be written");
        run(Cmd::new("git").args(["add", path]).cwd(dir)).expect("git add should pass");
        run(Cmd::new("git").args(["commit", "-m", "initial"]).cwd(dir))
            .expect("git commit should pass");
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

    #[test]
    fn load_file_diff_parses_tracked_modifications() {
        let dir = init_repo("file-diff");
        commit_file(&dir, "file.txt", "old\nsame\n");

        fs::write(dir.join("file.txt"), "new\nsame\n").expect("file should be modified");
        let diff = load_file_diff(&dir, "file.txt").expect("diff should load");

        assert_eq!(diff.path, "file.txt");
        assert_eq!(diff.additions, 1);
        assert_eq!(diff.deletions, 1);
        assert!(diff.rows.iter().any(|row| row.text == "+new"));
        assert!(diff.rows.iter().any(|row| row.text == "-old"));
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn stage_and_unstage_path_update_index_state() {
        let dir = init_repo("stage-unstage");
        commit_file(&dir, "file.txt", "old\n");

        fs::write(dir.join("file.txt"), "new\n").expect("file should be modified");
        stage_path(&dir, "file.txt").expect("path should stage");
        let staged = load_status(&dir).expect("status should load");
        assert_eq!(staged.files[0].index_status, 'M');
        assert_eq!(staged.files[0].worktree_status, ' ');

        unstage_path(&dir, "file.txt").expect("path should unstage");
        let unstaged = load_status(&dir).expect("status should load");
        assert_eq!(unstaged.files[0].index_status, ' ');
        assert_eq!(unstaged.files[0].worktree_status, 'M');
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn discard_path_restores_tracked_file() {
        let dir = init_repo("discard-tracked");
        commit_file(&dir, "file.txt", "old\n");

        fs::write(dir.join("file.txt"), "new\n").expect("file should be modified");
        stage_path(&dir, "file.txt").expect("path should stage");
        discard_path(&dir, "file.txt").expect("path should discard");

        assert_eq!(
            fs::read_to_string(dir.join("file.txt")).expect("file should exist"),
            "old\n"
        );
        assert!(load_status(&dir).expect("status should load").is_clean());
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn discard_path_removes_untracked_file() {
        let dir = init_repo("discard-untracked");
        commit_file(&dir, "file.txt", "old\n");
        let untracked = dir.join("scratch.txt");
        fs::write(&untracked, "scratch\n").expect("untracked file should be written");

        discard_path(&dir, "scratch.txt").expect("path should discard");

        assert!(!untracked.exists());
        assert!(load_status(&dir).expect("status should load").is_clean());
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn parse_worktree_list_normalizes_branch_names() {
        let worktrees = parse_worktree_list(
            "worktree /repo\nHEAD abc123\nbranch refs/heads/main\n\nworktree /repo-feature\nHEAD def456\ndetached\n\n",
        );

        assert_eq!(worktrees.len(), 2);
        assert_eq!(worktrees[0].path, PathBuf::from("/repo"));
        assert_eq!(worktrees[0].branch.as_deref(), Some("main"));
        assert_eq!(worktrees[0].head.as_deref(), Some("abc123"));
        assert!(worktrees[1].is_detached);
    }
}
