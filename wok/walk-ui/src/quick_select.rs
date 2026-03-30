//! Quick select overlay state and shared pattern registry.

use std::collections::HashSet;

use regex::Regex;

/// Pattern categories supported by quick select.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum PatternType {
    /// URL links.
    Url,
    /// Filesystem-like paths.
    FilePath,
    /// Git hash identifiers.
    GitHash,
    /// IPv4 addresses.
    IpAddress,
    /// Hexadecimal values.
    HexValue,
    /// User-defined custom pattern.
    Custom(String),
}

/// A single quick-select match.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct QuickSelectMatch {
    /// Match label shown in the overlay.
    pub label: String,
    /// Matched text content.
    pub text: String,
    /// Absolute terminal row.
    pub row: usize,
    /// Start column (inclusive).
    pub col_start: usize,
    /// End column (exclusive).
    pub col_end: usize,
    /// Matched pattern category.
    pub pattern_type: PatternType,
}

/// Scope used when collecting matches.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum QuickSelectScope {
    /// Match across the visible viewport.
    Viewport,
    /// Match only inside the selected block.
    SelectedBlock,
}

#[derive(Debug, Clone)]
struct PatternRule {
    pattern_type: PatternType,
    regex: Regex,
}

/// Shared regex pattern registry used by links and quick select.
#[derive(Debug, Clone)]
pub struct PatternRegistry {
    rules: Vec<PatternRule>,
}

impl PatternRegistry {
    /// Create the default pattern registry.
    pub fn new() -> Self {
        Self {
            rules: vec![
                PatternRule {
                    pattern_type: PatternType::Url,
                    regex: Regex::new(r#"https?://[^\s"'<>]+"#).expect("url regex should compile"),
                },
                PatternRule {
                    pattern_type: PatternType::FilePath,
                    regex: Regex::new(r"(?x)(?:~|/)[\w\./\-_~]+")
                        .expect("file path regex should compile"),
                },
                PatternRule {
                    pattern_type: PatternType::GitHash,
                    regex: Regex::new(r"\b[a-f0-9]{7,40}\b")
                        .expect("git hash regex should compile"),
                },
                PatternRule {
                    pattern_type: PatternType::IpAddress,
                    regex: Regex::new(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
                        .expect("ip regex should compile"),
                },
                PatternRule {
                    pattern_type: PatternType::HexValue,
                    regex: Regex::new(r"\b0x[a-fA-F0-9]+\b").expect("hex regex should compile"),
                },
            ],
        }
    }

    /// Add or replace a custom pattern.
    ///
    /// # Errors
    ///
    /// Returns a regex error if `regex` cannot compile.
    pub fn add_pattern(&mut self, name: &str, regex: &str) -> Result<(), regex::Error> {
        let compiled = Regex::new(regex)?;
        self.remove_pattern(name);
        self.rules.push(PatternRule {
            pattern_type: PatternType::Custom(name.to_string()),
            regex: compiled,
        });
        Ok(())
    }

    /// Remove a custom pattern by name.
    pub fn remove_pattern(&mut self, name: &str) {
        self.rules.retain(|rule| {
            !matches!(
                &rule.pattern_type,
                PatternType::Custom(custom) if custom == name
            )
        });
    }

    /// Detect all matches in one line.
    pub fn detect_line(&self, row: usize, text: &str) -> Vec<QuickSelectMatch> {
        let mut seen = HashSet::new();
        let mut matches = Vec::new();
        for rule in &self.rules {
            for capture in rule.regex.find_iter(text) {
                let col_start = text[..capture.start()].chars().count();
                let col_end = text[..capture.end()].chars().count();
                let key = (row, col_start, col_end);
                if !seen.insert(key) {
                    continue;
                }
                matches.push(QuickSelectMatch {
                    label: String::new(),
                    text: capture.as_str().to_string(),
                    row,
                    col_start,
                    col_end,
                    pattern_type: rule.pattern_type.clone(),
                });
            }
        }
        matches.sort_by_key(|candidate| (candidate.row, candidate.col_start));
        matches
    }

    /// Detect all matches across provided rows.
    pub fn detect_rows(&self, rows: &[(usize, String)]) -> Vec<QuickSelectMatch> {
        let mut matches = rows
            .iter()
            .flat_map(|(row, text)| self.detect_line(*row, text))
            .collect::<Vec<_>>();
        matches.sort_by_key(|candidate| (candidate.row, candidate.col_start));
        assign_labels(&mut matches);
        matches
    }
}

impl Default for PatternRegistry {
    fn default() -> Self {
        Self::new()
    }
}

/// Quick-select overlay state.
#[derive(Debug, Clone)]
pub struct QuickSelectState {
    /// Matches visible in the active scope.
    pub matches: Vec<QuickSelectMatch>,
    /// Whether the overlay is active.
    pub active: bool,
    /// Active scope.
    pub scope: QuickSelectScope,
    /// Current typed label prefix.
    pub typed_label: String,
}

impl QuickSelectState {
    /// Create an inactive quick-select state.
    pub fn new() -> Self {
        Self {
            matches: Vec::new(),
            active: false,
            scope: QuickSelectScope::Viewport,
            typed_label: String::new(),
        }
    }

    /// Activate the overlay with matches from the given rows.
    pub fn activate(
        &mut self,
        scope: QuickSelectScope,
        rows: &[(usize, String)],
        registry: &PatternRegistry,
    ) {
        self.scope = scope;
        self.matches = registry.detect_rows(rows);
        self.active = true;
        self.typed_label.clear();
    }

    /// Dismiss the overlay and clear transient state.
    pub fn dismiss(&mut self) {
        self.active = false;
        self.typed_label.clear();
        self.matches.clear();
    }

    /// Handle one typed label character and resolve a chosen match when exact.
    pub fn handle_label_char(&mut self, ch: char) -> Option<QuickSelectMatch> {
        if !self.active {
            return None;
        }

        let next = format!("{}{}", self.typed_label, ch);
        let has_prefix = self
            .matches
            .iter()
            .any(|candidate| candidate.label.starts_with(&next));
        if has_prefix {
            self.typed_label = next;
        } else {
            self.typed_label = ch.to_string();
        }

        let exact = self
            .matches
            .iter()
            .find(|candidate| candidate.label == self.typed_label)
            .cloned();
        if exact.is_some() {
            self.dismiss();
        }
        exact
    }

    /// Resolve the currently typed label to a unique match.
    pub fn selected(&self) -> Option<&QuickSelectMatch> {
        (!self.typed_label.is_empty())
            .then(|| {
                self.matches
                    .iter()
                    .find(|candidate| candidate.label == self.typed_label)
            })
            .flatten()
    }
}

impl Default for QuickSelectState {
    fn default() -> Self {
        Self::new()
    }
}

fn assign_labels(matches: &mut [QuickSelectMatch]) {
    let labels = generate_labels(matches.len());
    for (candidate, label) in matches.iter_mut().zip(labels) {
        candidate.label = label;
    }
}

fn generate_labels(count: usize) -> Vec<String> {
    const HOME_ROW: &[char] = &['a', 's', 'd', 'f', 'j', 'k', 'l'];
    let mut labels = Vec::new();

    for key in HOME_ROW {
        if labels.len() >= count {
            return labels;
        }
        labels.push(key.to_string());
    }

    'outer: for first in HOME_ROW {
        for second in HOME_ROW {
            if labels.len() >= count {
                break 'outer;
            }
            labels.push(format!("{first}{second}"));
        }
    }

    let mut fallback_idx = 0usize;
    while labels.len() < count {
        labels.push(format!("x{fallback_idx}"));
        fallback_idx += 1;
    }

    labels
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_detect_rows_assigns_home_row_labels() {
        let registry = PatternRegistry::new();
        let rows = vec![(
            1,
            "https://example.com /tmp/file abcdef1 127.0.0.1 0xfeed".to_string(),
        )];
        let matches = registry.detect_rows(&rows);
        assert!(!matches.is_empty());
        assert_eq!(matches[0].label, "a");
    }

    #[test]
    fn test_handle_label_char_selects_exact_match() {
        let registry = PatternRegistry::new();
        let rows = vec![(1, "https://example.com https://example.org".to_string())];
        let mut state = QuickSelectState::new();
        state.activate(QuickSelectScope::Viewport, &rows, &registry);
        let selected = state.handle_label_char('a');
        assert!(selected.is_some());
        assert!(!state.active);
    }

    #[test]
    fn test_custom_pattern_is_detected() {
        let mut registry = PatternRegistry::new();
        registry
            .add_pattern("ticket", r"TICKET-\d+")
            .expect("regex should compile");
        let matches = registry.detect_rows(&[(2, "open TICKET-42 now".to_string())]);
        assert!(matches
            .iter()
            .any(|candidate| matches!(candidate.pattern_type, PatternType::Custom(ref name) if name == "ticket")));
    }
}
