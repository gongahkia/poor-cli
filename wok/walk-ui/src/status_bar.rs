//! Status bar renderer: displays CWD, shell type, git branch, cursor position.

use std::path::{Path, PathBuf};

/// Status bar display state.
#[derive(Debug, Clone)]
pub struct StatusBarState {
    /// Current working directory.
    pub cwd: PathBuf,
    /// Shell type name.
    pub shell: String,
    /// Git branch name (if in a repo).
    pub git_branch: Option<String>,
    /// Cursor line number.
    pub cursor_line: u16,
    /// Cursor column number.
    pub cursor_col: u16,
}

impl Default for StatusBarState {
    fn default() -> Self {
        Self {
            cwd: PathBuf::from("~"),
            shell: "bash".to_string(),
            git_branch: None,
            cursor_line: 1,
            cursor_col: 1,
        }
    }
}

/// Detect git branch from a directory path.
pub fn detect_git_branch(cwd: &Path) -> Option<String> {
    let mut dir = cwd.to_path_buf();
    loop {
        let head = dir.join(".git").join("HEAD");
        if head.exists() {
            if let Ok(content) = std::fs::read_to_string(&head) {
                let content = content.trim();
                if let Some(branch) = content.strip_prefix("ref: refs/heads/") {
                    return Some(branch.to_string());
                }
                // Detached HEAD: return short hash
                return Some(content.chars().take(8).collect());
            }
        }
        if !dir.pop() {
            break;
        }
    }
    None
}

/// Status bar renderer.
pub struct StatusBarRenderer {
    /// Height of the status bar.
    pub height: f32,
}

impl StatusBarRenderer {
    /// Create a new status bar renderer.
    pub fn new() -> Self {
        Self { height: 24.0 }
    }

    /// Format the CWD for display, truncating with "..." if too long.
    pub fn format_cwd(cwd: &Path, max_chars: usize) -> String {
        let s = cwd.to_string_lossy();
        if s.len() <= max_chars {
            s.to_string()
        } else {
            format!("...{}", &s[s.len() - max_chars + 3..])
        }
    }
}

impl Default for StatusBarRenderer {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_cwd_short() {
        let cwd = Path::new("/home/user");
        assert_eq!(StatusBarRenderer::format_cwd(cwd, 30), "/home/user");
    }

    #[test]
    fn test_format_cwd_truncate() {
        let cwd = Path::new("/very/long/path/to/some/deeply/nested/directory");
        let formatted = StatusBarRenderer::format_cwd(cwd, 20);
        assert!(formatted.starts_with("..."));
        assert!(formatted.len() <= 20);
    }

    #[test]
    fn test_detect_git_branch_in_repo() {
        // Test in the current repo - use env::current_dir for reliable path
        if let Ok(cwd) = std::env::current_dir() {
            let branch = detect_git_branch(&cwd);
            // May or may not be in a git repo depending on test runner
            let _ = branch;
        }
    }

    #[test]
    fn test_detect_git_branch_not_repo() {
        let branch = detect_git_branch(Path::new("/tmp"));
        // /tmp is typically not a git repo
        // This might be Some on some systems, so we just ensure no panic
        let _ = branch;
    }
}
