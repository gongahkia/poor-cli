//! Command palette index and filtering state.

/// Command palette category.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum PaletteCategory {
    /// Built-in action entries.
    Action,
    /// Lua registered command aliases.
    LuaCommand,
    /// Workflow templates.
    Workflow,
    /// Recent command history entries.
    RecentCommand,
    /// File path entries.
    FilePath,
}

/// Action performed when selecting a palette entry.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PaletteAction {
    /// Execute a built-in action by canonical action id.
    BuiltInAction(String),
    /// Execute a Lua command alias.
    LuaCommand(String),
    /// Activate a workflow by name.
    Workflow(String),
    /// Insert or execute a recent command.
    RecentCommand(String),
    /// Insert a file path.
    FilePath(String),
}

/// One command palette entry.
#[derive(Debug, Clone, PartialEq)]
pub struct PaletteEntry {
    /// Primary label.
    pub label: String,
    /// Secondary description.
    pub description: String,
    /// Category used for grouping and ranking.
    pub category: PaletteCategory,
    /// Calculated score for the active query.
    pub score: f64,
    /// Selection action.
    pub action: PaletteAction,
}

/// Runtime command-palette state.
#[derive(Debug, Clone)]
pub struct CommandPaletteState {
    /// Current user query.
    pub query: String,
    /// Full unfiltered entry list.
    pub entries: Vec<PaletteEntry>,
    /// Filtered entry indices.
    pub filtered: Vec<usize>,
    /// Selected index in `filtered`.
    pub selected_index: usize,
    /// Whether the palette is open.
    pub is_open: bool,
}

impl CommandPaletteState {
    /// Create an empty, closed palette state.
    pub fn new() -> Self {
        Self {
            query: String::new(),
            entries: Vec::new(),
            filtered: Vec::new(),
            selected_index: 0,
            is_open: false,
        }
    }

    /// Open the palette with a fresh index.
    pub fn open(&mut self, entries: Vec<PaletteEntry>) {
        self.entries = entries;
        self.query.clear();
        self.is_open = true;
        self.recompute();
    }

    /// Close the palette and clear transient query state.
    pub fn close(&mut self) {
        self.query.clear();
        self.filtered.clear();
        self.selected_index = 0;
        self.is_open = false;
    }

    /// Update the query and refresh filtered results.
    pub fn set_query(&mut self, query: &str) {
        self.query = query.to_string();
        self.recompute();
    }

    /// Move selection down by one result.
    pub fn select_next(&mut self) {
        if self.filtered.is_empty() {
            self.selected_index = 0;
            return;
        }
        self.selected_index = (self.selected_index + 1) % self.filtered.len();
    }

    /// Move selection up by one result.
    pub fn select_prev(&mut self) {
        if self.filtered.is_empty() {
            self.selected_index = 0;
            return;
        }
        if self.selected_index == 0 {
            self.selected_index = self.filtered.len().saturating_sub(1);
        } else {
            self.selected_index -= 1;
        }
    }

    /// Return the selected entry.
    pub fn selected(&self) -> Option<&PaletteEntry> {
        self.filtered
            .get(self.selected_index)
            .and_then(|index| self.entries.get(*index))
    }

    fn recompute(&mut self) {
        let mut query = self.query.trim().to_string();
        let category_filter = if let Some(stripped) = query.strip_prefix('>') {
            query = stripped.trim_start().to_string();
            Some(PaletteCategory::Action)
        } else if let Some(stripped) = query.strip_prefix('@') {
            query = stripped.trim_start().to_string();
            Some(PaletteCategory::Workflow)
        } else {
            None
        };

        let query_lower = query.to_ascii_lowercase();
        let workflow_priority = !query.is_empty();

        let mut ranked = self
            .entries
            .iter()
            .enumerate()
            .filter(|(_, entry)| category_filter.is_none_or(|category| entry.category == category))
            .filter_map(|(index, entry)| {
                if query_lower.is_empty() {
                    return Some((index, 0.0, category_rank(entry.category, workflow_priority)));
                }
                let haystack = format!("{} {}", entry.label, entry.description);
                fuzzy_score(&haystack, &query_lower).map(|score| {
                    (
                        index,
                        score,
                        category_rank(entry.category, workflow_priority),
                    )
                })
            })
            .collect::<Vec<_>>();

        ranked.sort_by(|left, right| {
            left.2
                .cmp(&right.2)
                .then_with(|| right.1.total_cmp(&left.1))
                .then_with(|| left.0.cmp(&right.0))
        });

        self.filtered = ranked.into_iter().map(|(index, _, _)| index).collect();
        if self.selected_index >= self.filtered.len() {
            self.selected_index = 0;
        }
    }
}

impl Default for CommandPaletteState {
    fn default() -> Self {
        Self::new()
    }
}

fn category_rank(category: PaletteCategory, workflow_priority: bool) -> u8 {
    if workflow_priority {
        match category {
            PaletteCategory::Workflow => 0,
            PaletteCategory::Action => 1,
            PaletteCategory::RecentCommand => 2,
            PaletteCategory::LuaCommand => 3,
            PaletteCategory::FilePath => 4,
        }
    } else {
        match category {
            PaletteCategory::Action => 0,
            PaletteCategory::Workflow => 1,
            PaletteCategory::RecentCommand => 2,
            PaletteCategory::LuaCommand => 3,
            PaletteCategory::FilePath => 4,
        }
    }
}

fn fuzzy_score(text: &str, query: &str) -> Option<f64> {
    wok_fuzzy::score(query, text)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_prefix_filter_actions_only() {
        let mut state = CommandPaletteState::new();
        state.open(vec![
            PaletteEntry {
                label: "Split Vertical".to_string(),
                description: "Action".to_string(),
                category: PaletteCategory::Action,
                score: 0.0,
                action: PaletteAction::BuiltInAction("split_vertical".to_string()),
            },
            PaletteEntry {
                label: "deploy".to_string(),
                description: "Workflow".to_string(),
                category: PaletteCategory::Workflow,
                score: 0.0,
                action: PaletteAction::Workflow("deploy".to_string()),
            },
        ]);
        state.set_query(">split");
        assert_eq!(state.filtered.len(), 1);
        assert_eq!(
            state.selected().map(|entry| entry.label.as_str()),
            Some("Split Vertical")
        );
    }

    #[test]
    fn test_prefix_filter_workflows_only() {
        let mut state = CommandPaletteState::new();
        state.open(vec![PaletteEntry {
            label: "deploy".to_string(),
            description: "Workflow".to_string(),
            category: PaletteCategory::Workflow,
            score: 0.0,
            action: PaletteAction::Workflow("deploy".to_string()),
        }]);
        state.set_query("@deploy");
        assert_eq!(state.filtered.len(), 1);
    }
}
