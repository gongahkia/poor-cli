//! Command history: persists and navigates previously executed commands.

use std::fs;
use std::path::{Path, PathBuf};

use tracing::{debug, warn};

/// Manages command history with file persistence.
pub struct CommandHistory {
    /// History entries (oldest first).
    entries: Vec<String>,
    /// Current navigation position.
    cursor: usize,
    /// Path to the history file.
    history_file: PathBuf,
    /// Maximum number of entries to retain.
    max_entries: usize,
    /// Saved current input for navigation.
    saved_current: Option<String>,
}

impl CommandHistory {
    /// Load history from file, creating it if necessary.
    pub fn load(path: &Path, max: usize) -> Self {
        let entries = if path.exists() {
            match fs::read_to_string(path) {
                Ok(content) => content
                    .lines()
                    .filter(|l| !l.is_empty())
                    .map(String::from)
                    .collect(),
                Err(e) => {
                    warn!("failed to read history file: {e}");
                    Vec::new()
                }
            }
        } else {
            Vec::new()
        };

        let len = entries.len();
        debug!(count = len, "loaded history entries");

        Self {
            entries,
            cursor: len,
            history_file: path.to_path_buf(),
            max_entries: max,
            saved_current: None,
        }
    }

    /// Default history file path.
    pub fn default_path() -> PathBuf {
        dirs_path().join(".walk_history")
    }

    /// Push a new command to history.
    ///
    /// Skips duplicates of the immediately previous entry.
    pub fn push(&mut self, command: &str) {
        let trimmed = command.trim();
        if trimmed.is_empty() {
            return;
        }

        // Skip if duplicate of last entry
        if self.entries.last().map(String::as_str) == Some(trimmed) {
            self.cursor = self.entries.len();
            self.saved_current = None;
            return;
        }

        self.entries.push(trimmed.to_string());

        // Trim to max entries
        if self.entries.len() > self.max_entries {
            let excess = self.entries.len() - self.max_entries;
            self.entries.drain(..excess);
        }

        self.cursor = self.entries.len();
        self.saved_current = None;

        // Append to file
        self.append_to_file(trimmed);
    }

    /// Navigate to previous history entry (Up arrow).
    pub fn prev(&mut self, current_input: &str) -> Option<&str> {
        if self.entries.is_empty() || self.cursor == 0 {
            return None;
        }

        // Save current input on first navigation
        if self.cursor == self.entries.len() {
            self.saved_current = Some(current_input.to_string());
        }

        self.cursor -= 1;
        Some(&self.entries[self.cursor])
    }

    /// Navigate to next history entry (Down arrow).
    pub fn next(&mut self) -> Option<&str> {
        if self.cursor >= self.entries.len() {
            return None;
        }

        self.cursor += 1;

        if self.cursor == self.entries.len() {
            // Return to saved current input
            self.saved_current.as_deref()
        } else {
            Some(&self.entries[self.cursor])
        }
    }

    /// Search history for entries containing the query (most recent first).
    pub fn search(&self, query: &str) -> Vec<&str> {
        self.entries
            .iter()
            .rev()
            .filter(|e| e.contains(query))
            .map(String::as_str)
            .collect()
    }

    /// Save all entries to the history file.
    pub fn save(&self) {
        let content = self.entries.join("\n");
        if let Err(e) = fs::write(&self.history_file, content) {
            warn!("failed to save history: {e}");
        }
    }

    /// Return the number of history entries.
    pub fn len(&self) -> usize {
        self.entries.len()
    }

    /// Return whether the history is empty.
    pub fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    fn append_to_file(&self, command: &str) {
        use std::io::Write;
        if let Ok(mut file) = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.history_file)
        {
            let _ = writeln!(file, "{command}");
        }
    }
}

impl Drop for CommandHistory {
    fn drop(&mut self) {
        self.save();
    }
}

fn dirs_path() -> PathBuf {
    std::env::var("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("."))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_history() -> CommandHistory {
        let dir = std::env::temp_dir().join(format!("walk_test_{}", std::process::id()));
        let path = dir.join("history");
        CommandHistory::load(&path, 10_000)
    }

    #[test]
    fn test_push_and_navigate() {
        let mut history = temp_history();
        history.push("cmd1");
        history.push("cmd2");
        history.push("cmd3");

        assert_eq!(history.prev(""), Some("cmd3"));
        assert_eq!(history.prev(""), Some("cmd2"));
        assert_eq!(history.prev(""), Some("cmd1"));
        assert_eq!(history.prev(""), None);
    }

    #[test]
    fn test_next_returns_to_current() {
        let mut history = temp_history();
        history.push("cmd1");
        history.push("cmd2");

        assert_eq!(history.prev("current"), Some("cmd2"));
        assert_eq!(history.prev("current"), Some("cmd1"));
        assert_eq!(history.next(), Some("cmd2"));
        assert_eq!(history.next(), Some("current"));
    }

    #[test]
    fn test_skip_duplicate() {
        let mut history = temp_history();
        history.push("cmd1");
        history.push("cmd1");
        assert_eq!(history.len(), 1);
    }

    #[test]
    fn test_search() {
        let mut history = temp_history();
        history.push("git commit");
        history.push("ls -la");
        history.push("git push");

        let results = history.search("git");
        assert_eq!(results.len(), 2);
        assert_eq!(results[0], "git push");
        assert_eq!(results[1], "git commit");
    }

    #[test]
    fn test_persistence() {
        let path = std::env::temp_dir().join(format!("walk_persist_test_{}", std::process::id()));

        {
            let mut history = CommandHistory::load(&path, 10_000);
            history.push("persistent_cmd");
        } // Drop saves

        let history2 = CommandHistory::load(&path, 10_000);
        assert_eq!(history2.len(), 1);

        // Cleanup
        let _ = std::fs::remove_file(&path);
    }
}
