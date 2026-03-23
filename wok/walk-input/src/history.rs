//! Command history: pane-local entries, global persistence, and search helpers.

use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use tracing::{debug, warn};

/// A single command history entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HistoryEntry {
    /// Command text as entered by the user.
    pub command: String,
    /// Working directory captured for the command when known.
    pub cwd: Option<PathBuf>,
    /// Source pane for session-local ranking when known.
    pub source_pane_id: Option<u64>,
    /// Start timestamp in Unix milliseconds.
    pub started_at_ms: u64,
    /// Completion timestamp in Unix milliseconds when known.
    pub completed_at_ms: Option<u64>,
    /// Exit code when the command completed.
    pub exit_code: Option<i32>,
    /// Execution duration when known.
    pub duration_ms: Option<u64>,
}

impl HistoryEntry {
    /// Create a pending history entry for a just-submitted command.
    pub fn pending(command: &str, cwd: Option<PathBuf>, source_pane_id: Option<u64>) -> Self {
        Self {
            command: command.trim().to_string(),
            cwd,
            source_pane_id,
            started_at_ms: unix_time_ms(SystemTime::now()),
            completed_at_ms: None,
            exit_code: None,
            duration_ms: None,
        }
    }

    /// Create a text-only history entry loaded from the long-term history file.
    pub fn from_command(command: &str) -> Self {
        Self {
            command: command.trim().to_string(),
            cwd: None,
            source_pane_id: None,
            started_at_ms: 0,
            completed_at_ms: None,
            exit_code: None,
            duration_ms: None,
        }
    }

    /// Return whether the entry has enough information to be treated as completed.
    pub fn is_completed(&self) -> bool {
        self.completed_at_ms.is_some() || self.exit_code.is_some() || self.duration_ms.is_some()
    }

    /// Mark an entry as completed, refreshing its metadata from runtime state.
    pub fn mark_completed(
        &mut self,
        exit_code: Option<i32>,
        duration: Option<Duration>,
        cwd: Option<PathBuf>,
    ) {
        self.completed_at_ms = Some(unix_time_ms(SystemTime::now()));
        self.exit_code = exit_code;
        self.duration_ms = duration.map(|value| value.as_millis() as u64);
        if cwd.is_some() {
            self.cwd = cwd;
        }
    }
}

/// Ranked fuzzy-search result for one history entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HistorySearchMatch {
    /// Matching entry.
    pub entry: HistoryEntry,
    /// Search relevance score. Higher is better.
    pub score: i64,
}

/// File-backed long-term command history.
pub struct CommandHistory {
    /// History entries, oldest first.
    entries: Vec<HistoryEntry>,
    /// Path to the plain-text history file.
    history_file: PathBuf,
    /// Maximum number of entries to retain in memory and on save.
    max_entries: usize,
}

impl CommandHistory {
    /// Load history from file, creating an empty in-memory history if needed.
    pub fn load(path: &Path, max: usize) -> Self {
        let entries = if path.exists() {
            match fs::read_to_string(path) {
                Ok(content) => content
                    .lines()
                    .filter(|line| !line.trim().is_empty())
                    .map(HistoryEntry::from_command)
                    .collect(),
                Err(error) => {
                    warn!("failed to read history file: {error}");
                    Vec::new()
                }
            }
        } else {
            Vec::new()
        };

        debug!(count = entries.len(), "loaded history entries");

        Self {
            entries,
            history_file: path.to_path_buf(),
            max_entries: max,
        }
    }

    /// Default history file path.
    pub fn default_path() -> PathBuf {
        dirs_path().join(".walk_history")
    }

    /// Return all entries in chronological order.
    pub fn entries(&self) -> &[HistoryEntry] {
        &self.entries
    }

    /// Record a completed command in the long-term history.
    ///
    /// Immediate duplicate commands are coalesced to preserve the previous
    /// behavior of the plain-text history file.
    pub fn record_completed(&mut self, entry: HistoryEntry) {
        if entry.command.trim().is_empty() {
            return;
        }

        let trimmed = entry.command.trim();
        if self
            .entries
            .last()
            .is_some_and(|last| last.command == trimmed)
        {
            if let Some(last) = self.entries.last_mut() {
                *last = entry.clone();
            }
            self.save();
            return;
        }

        self.entries.push(entry.clone());
        self.trim_to_max();
        self.append_to_file(trimmed);
    }

    /// Search the global history with fuzzy ranking.
    pub fn search(&self, query: &str, limit: usize) -> Vec<HistorySearchMatch> {
        fuzzy_search_entries(&self.entries, query, limit)
    }

    /// Save all commands back to the plain-text history file.
    pub fn save(&self) {
        let content = self
            .entries
            .iter()
            .map(|entry| entry.command.as_str())
            .collect::<Vec<_>>()
            .join("\n");

        if let Err(error) = fs::write(&self.history_file, content) {
            warn!("failed to save history: {error}");
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

    fn trim_to_max(&mut self) {
        if self.entries.len() <= self.max_entries {
            return;
        }

        let excess = self.entries.len() - self.max_entries;
        self.entries.drain(..excess);
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

/// Return prefix-matching entries ordered from most recent to oldest.
pub fn prefix_matches<'a>(entries: &'a [HistoryEntry], prefix: &str) -> Vec<&'a HistoryEntry> {
    let prefix = prefix.trim();
    let prefix_lower = prefix.to_ascii_lowercase();

    entries
        .iter()
        .rev()
        .filter(|entry| {
            if prefix_lower.is_empty() {
                return true;
            }
            entry
                .command
                .to_ascii_lowercase()
                .starts_with(&prefix_lower)
        })
        .collect()
}

/// Search the provided entries with simple Warp-like fuzzy ranking.
pub fn fuzzy_search_entries(
    entries: &[HistoryEntry],
    query: &str,
    limit: usize,
) -> Vec<HistorySearchMatch> {
    let trimmed = query.trim();
    if trimmed.is_empty() {
        return entries
            .iter()
            .rev()
            .take(limit)
            .map(|entry| HistorySearchMatch {
                entry: entry.clone(),
                score: 0,
            })
            .collect();
    }

    let mut matches = entries
        .iter()
        .rev()
        .filter_map(|entry| fuzzy_score(&entry.command, trimmed).map(|score| (entry, score)))
        .map(|(entry, score)| HistorySearchMatch {
            entry: entry.clone(),
            score,
        })
        .collect::<Vec<_>>();

    matches.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then(right.entry.started_at_ms.cmp(&left.entry.started_at_ms))
            .then(right.entry.completed_at_ms.cmp(&left.entry.completed_at_ms))
    });
    matches.truncate(limit);
    matches
}

fn fuzzy_score(text: &str, query: &str) -> Option<i64> {
    if query.is_empty() {
        return Some(0);
    }

    let text_lower = text.to_ascii_lowercase();
    let query_lower = query.to_ascii_lowercase();

    if let Some(position) = text_lower.find(&query_lower) {
        let prefix_bonus = if position == 0 { 150 } else { 0 };
        let compact_bonus = 100_i64.saturating_sub(position as i64);
        let length_bonus = 40_i64.saturating_sub((text.len().saturating_sub(query.len())) as i64);
        return Some(1_000 + prefix_bonus + compact_bonus + length_bonus);
    }

    let mut score = 0_i64;
    let mut query_chars = query_lower.chars();
    let mut current = query_chars.next()?;
    let mut consecutive = 0_i64;
    let mut last_match_index = None;
    let mut previous_char = None;

    for (index, ch) in text_lower.chars().enumerate() {
        if ch == current {
            score += 20 + consecutive * 5;
            if index == 0
                || previous_char.is_some_and(|value: char| {
                    value == ' ' || value == '/' || value == '-' || value == '_'
                })
            {
                score += 25;
            }
            if let Some(last_index) = last_match_index {
                score -= (index.saturating_sub(last_index + 1)) as i64;
            }
            consecutive += 1;
            last_match_index = Some(index);
            if let Some(next) = query_chars.next() {
                current = next;
            } else {
                return Some(score - text.len() as i64);
            }
        } else {
            consecutive = 0;
        }
        previous_char = Some(ch);
    }

    None
}

fn unix_time_ms(time: SystemTime) -> u64 {
    time.duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
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
    fn test_record_completed_skips_immediate_duplicate_command() {
        let mut history = temp_history();
        history.record_completed(HistoryEntry::pending("git status", None, Some(1)));
        history.record_completed(HistoryEntry::pending("git status", None, Some(2)));

        assert_eq!(history.len(), 1);
    }

    #[test]
    fn test_prefix_matches_returns_recent_entries_first() {
        let entries = vec![
            HistoryEntry::from_command("git status"),
            HistoryEntry::from_command("git commit"),
            HistoryEntry::from_command("ls"),
        ];

        let matches = prefix_matches(&entries, "git");
        assert_eq!(matches.len(), 2);
        assert_eq!(matches[0].command, "git commit");
        assert_eq!(matches[1].command, "git status");
    }

    #[test]
    fn test_fuzzy_search_prefers_compact_prefix_matches() {
        let entries = vec![
            HistoryEntry::from_command("cargo test"),
            HistoryEntry::from_command("git commit"),
            HistoryEntry::from_command("cargo clippy"),
        ];

        let matches = fuzzy_search_entries(&entries, "ct", 10);
        assert_eq!(matches[0].entry.command, "cargo test");
    }

    #[test]
    fn test_mark_completed_hydrates_runtime_metadata() {
        let mut entry = HistoryEntry::pending("cargo test", None, Some(7));
        entry.mark_completed(
            Some(1),
            Some(Duration::from_secs(3)),
            Some(PathBuf::from("/tmp")),
        );

        assert_eq!(entry.exit_code, Some(1));
        assert_eq!(entry.duration_ms, Some(3_000));
        assert_eq!(entry.cwd, Some(PathBuf::from("/tmp")));
        assert!(entry.is_completed());
    }

    #[test]
    fn test_global_search_returns_recent_matches() {
        let mut history = temp_history();
        history.record_completed(HistoryEntry::pending("git status", None, Some(1)));
        history.record_completed(HistoryEntry::pending("cargo test", None, Some(1)));
        history.record_completed(HistoryEntry::pending("git commit", None, Some(2)));

        let results = history.search("git", 10);
        assert_eq!(results.len(), 2);
        assert_eq!(results[0].entry.command, "git commit");
        assert_eq!(results[1].entry.command, "git status");
    }
}
