//! Status bar renderer: displays CWD, shell type, git branch, cursor position.

use std::path::{Path, PathBuf};

/// One status bar segment with optional colors and emphasis.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StatusSegment {
    /// Segment text (rendered verbatim).
    pub text: String,
    /// Optional foreground override as `#rrggbb`.
    pub fg: Option<String>,
    /// Optional background override as `#rrggbb`.
    pub bg: Option<String>,
    /// Whether to render with bold emphasis.
    pub bold: bool,
}

impl StatusSegment {
    /// Create a plain segment from text.
    pub fn plain(text: impl Into<String>) -> Self {
        Self {
            text: text.into(),
            fg: None,
            bg: None,
            bold: false,
        }
    }
}

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
    /// Custom segments inserted into the left section.
    pub custom_left: Vec<StatusSegment>,
    /// Custom segments inserted into the center section.
    pub custom_center: Vec<StatusSegment>,
    /// Custom segments inserted into the right section.
    pub custom_right: Vec<StatusSegment>,
}

impl Default for StatusBarState {
    fn default() -> Self {
        Self {
            cwd: PathBuf::from("~"),
            shell: "bash".to_string(),
            git_branch: None,
            cursor_line: 1,
            cursor_col: 1,
            custom_left: Vec::new(),
            custom_center: Vec::new(),
            custom_right: Vec::new(),
        }
    }
}

impl StatusBarState {
    /// Replace custom left segments.
    pub fn set_left(&mut self, segments: Vec<StatusSegment>) {
        self.custom_left = segments;
    }

    /// Replace custom center segments.
    pub fn set_center(&mut self, segments: Vec<StatusSegment>) {
        self.custom_center = segments;
    }

    /// Replace custom right segments.
    pub fn set_right(&mut self, segments: Vec<StatusSegment>) {
        self.custom_right = segments;
    }

    /// Clear all custom segments.
    pub fn clear_custom(&mut self) {
        self.custom_left.clear();
        self.custom_center.clear();
        self.custom_right.clear();
    }
}

/// Detect git branch from a directory path.
pub fn detect_git_branch(cwd: &Path) -> Option<String> {
    wok_git::repo::detect_branch(cwd)
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

    #[test]
    fn test_custom_segment_setters() {
        let mut state = StatusBarState::default();
        state.set_left(vec![StatusSegment::plain("left")]);
        state.set_center(vec![StatusSegment::plain("center")]);
        state.set_right(vec![StatusSegment::plain("right")]);

        assert_eq!(state.custom_left[0].text, "left");
        assert_eq!(state.custom_center[0].text, "center");
        assert_eq!(state.custom_right[0].text, "right");

        state.clear_custom();
        assert!(state.custom_left.is_empty());
        assert!(state.custom_center.is_empty());
        assert!(state.custom_right.is_empty());
    }
}
