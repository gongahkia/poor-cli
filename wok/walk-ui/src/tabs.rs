//! Tab management: multiple terminal sessions as tabs.

/// A single tab holding a terminal session reference.
#[derive(Debug)]
pub struct Tab {
    /// Unique tab identifier.
    pub id: u64,
    /// Tab title.
    pub title: String,
    /// Whether the tab has unseen output.
    pub is_dirty: bool,
}

/// Manages multiple tabs.
pub struct TabManager {
    /// All open tabs.
    pub tabs: Vec<Tab>,
    /// Index of the active tab.
    pub active_tab: usize,
    /// Next tab ID.
    next_id: u64,
}

impl TabManager {
    /// Create a new tab manager.
    pub fn new() -> Self {
        Self {
            tabs: Vec::new(),
            active_tab: 0,
            next_id: 1,
        }
    }

    /// Create a new tab and return its ID.
    pub fn new_tab(&mut self, title: &str) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        self.tabs.push(Tab {
            id,
            title: title.to_string(),
            is_dirty: false,
        });
        self.active_tab = self.tabs.len() - 1;
        id
    }

    /// Close a tab by ID.
    pub fn close_tab(&mut self, id: u64) {
        if let Some(idx) = self.tabs.iter().position(|t| t.id == id) {
            self.tabs.remove(idx);
            if self.active_tab >= self.tabs.len() && !self.tabs.is_empty() {
                self.active_tab = self.tabs.len() - 1;
            }
        }
    }

    /// Switch to a tab by index.
    pub fn switch_tab(&mut self, index: usize) {
        if index < self.tabs.len() {
            self.active_tab = index;
        }
    }

    /// Switch to the next tab (wrapping).
    pub fn next_tab(&mut self) {
        if !self.tabs.is_empty() {
            self.active_tab = (self.active_tab + 1) % self.tabs.len();
        }
    }

    /// Switch to the previous tab (wrapping).
    pub fn prev_tab(&mut self) {
        if !self.tabs.is_empty() {
            if self.active_tab == 0 {
                self.active_tab = self.tabs.len() - 1;
            } else {
                self.active_tab -= 1;
            }
        }
    }

    /// Move a tab from one index to another.
    pub fn move_tab(&mut self, from: usize, to: usize) {
        if from < self.tabs.len() && to < self.tabs.len() && from != to {
            let tab = self.tabs.remove(from);
            self.tabs.insert(to, tab);
            self.active_tab = to;
        }
    }

    /// Get the active tab.
    pub fn active_tab(&self) -> Option<&Tab> {
        self.tabs.get(self.active_tab)
    }

    /// Get the number of tabs.
    pub fn len(&self) -> usize {
        self.tabs.len()
    }

    /// Check if there are no tabs.
    pub fn is_empty(&self) -> bool {
        self.tabs.is_empty()
    }
}

impl Default for TabManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_tab() {
        let mut tm = TabManager::new();
        let id = tm.new_tab("shell");
        assert_eq!(tm.len(), 1);
        assert_eq!(tm.active_tab().unwrap().id, id);
    }

    #[test]
    fn test_close_tab() {
        let mut tm = TabManager::new();
        let id = tm.new_tab("tab1");
        tm.new_tab("tab2");
        tm.close_tab(id);
        assert_eq!(tm.len(), 1);
    }

    #[test]
    fn test_next_tab_wraps() {
        let mut tm = TabManager::new();
        tm.new_tab("tab1");
        tm.new_tab("tab2");
        tm.new_tab("tab3");
        tm.active_tab = 2;
        tm.next_tab();
        assert_eq!(tm.active_tab, 0);
    }

    #[test]
    fn test_move_tab() {
        let mut tm = TabManager::new();
        tm.new_tab("a");
        tm.new_tab("b");
        tm.new_tab("c");
        tm.move_tab(0, 2);
        assert_eq!(tm.tabs[2].title, "a");
    }
}
