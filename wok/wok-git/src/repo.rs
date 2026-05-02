//! Lightweight repository metadata detection.

use std::fs;
use std::path::{Path, PathBuf};

/// Basic Git repository metadata discoverable without invoking `git`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GitRepoInfo {
    /// Worktree root containing the `.git` directory or gitdir file.
    pub worktree_root: PathBuf,
    /// Resolved Git metadata directory.
    pub git_dir: PathBuf,
    /// Current branch, or detached HEAD short hash.
    pub branch: Option<String>,
}

/// Detect basic Git metadata by walking upward from `cwd`.
pub fn detect_repo_info(cwd: &Path) -> Option<GitRepoInfo> {
    let mut dir = cwd.to_path_buf();
    loop {
        if let Some(git_dir) = resolve_git_dir(&dir) {
            let branch = read_head_branch(&git_dir);
            return Some(GitRepoInfo {
                worktree_root: dir,
                git_dir,
                branch,
            });
        }
        if !dir.pop() {
            break;
        }
    }
    None
}

/// Detect the current branch, or detached HEAD short hash, from `cwd`.
pub fn detect_branch(cwd: &Path) -> Option<String> {
    detect_repo_info(cwd).and_then(|info| info.branch)
}

fn resolve_git_dir(worktree_root: &Path) -> Option<PathBuf> {
    let dot_git = worktree_root.join(".git");
    if dot_git.is_dir() {
        return Some(dot_git);
    }

    let content = fs::read_to_string(&dot_git).ok()?;
    let gitdir = content.trim().strip_prefix("gitdir:")?.trim();
    if gitdir.is_empty() {
        return None;
    }

    let path = PathBuf::from(gitdir);
    Some(if path.is_absolute() {
        path
    } else {
        worktree_root.join(path)
    })
}

fn read_head_branch(git_dir: &Path) -> Option<String> {
    let content = fs::read_to_string(git_dir.join("HEAD")).ok()?;
    let content = content.trim();
    if let Some(branch) = content.strip_prefix("ref: refs/heads/") {
        return Some(branch.to_string());
    }
    (!content.is_empty()).then(|| content.chars().take(8).collect())
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_path(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("wok-git-{name}-{stamp}"))
    }

    fn temp_repo(name: &str) -> PathBuf {
        let path = unique_path(name);
        fs::create_dir_all(path.join(".git")).expect("repo directory should be created");
        path
    }

    #[test]
    fn detects_branch_from_git_head() {
        let repo = temp_repo("branch");
        fs::write(repo.join(".git").join("HEAD"), "ref: refs/heads/main\n")
            .expect("HEAD should be written");

        assert_eq!(detect_branch(&repo), Some("main".to_string()));
        fs::remove_dir_all(repo).ok();
    }

    #[test]
    fn walks_up_from_nested_directory() {
        let repo = temp_repo("nested");
        let nested = repo.join("src/bin");
        fs::create_dir_all(&nested).expect("nested directory should be created");
        fs::write(
            repo.join(".git").join("HEAD"),
            "ref: refs/heads/feature/x\n",
        )
        .expect("HEAD should be written");

        let info = detect_repo_info(&nested).expect("repo should be detected");
        assert_eq!(info.worktree_root, repo);
        assert_eq!(info.branch.as_deref(), Some("feature/x"));
        fs::remove_dir_all(info.worktree_root).ok();
    }

    #[test]
    fn detects_detached_head_short_hash() {
        let repo = temp_repo("detached");
        fs::write(
            repo.join(".git").join("HEAD"),
            "0123456789abcdef0123456789abcdef01234567\n",
        )
        .expect("HEAD should be written");

        assert_eq!(detect_branch(&repo), Some("01234567".to_string()));
        fs::remove_dir_all(repo).ok();
    }

    #[test]
    fn resolves_gitdir_file() {
        let repo = unique_path("file");
        let git_dir = unique_path("actual-git-dir");
        fs::create_dir_all(&repo).expect("repo directory should be created");
        fs::create_dir_all(&git_dir).expect("git dir should be created");
        fs::write(
            repo.join(".git"),
            format!("gitdir: {}\n", git_dir.display()),
        )
        .expect("gitdir file should be written");
        fs::write(git_dir.join("HEAD"), "ref: refs/heads/worktree\n")
            .expect("HEAD should be written");

        assert_eq!(detect_branch(&repo), Some("worktree".to_string()));
        fs::remove_dir_all(repo).ok();
        fs::remove_dir_all(git_dir).ok();
    }
}
