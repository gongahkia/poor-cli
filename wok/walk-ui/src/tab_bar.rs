//! Tab bar renderer: draws the tab strip with active tab highlighting.

use crate::layout::Rect;
use crate::tabs::TabManager;

/// Actions that can result from clicking in the tab bar.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TabBarAction {
    /// Switch to a tab by index.
    SwitchTab(usize),
    /// Close a tab by ID.
    CloseTab(u64),
    /// Create a new tab.
    NewTab,
    /// Start dragging a tab.
    DragStart(usize),
}

/// Tab bar renderer.
pub struct TabBarRenderer {
    /// Height of each tab (in pixels).
    pub tab_height: f32,
}

impl TabBarRenderer {
    /// Create a new tab bar renderer.
    pub fn new() -> Self {
        Self { tab_height: 32.0 }
    }

    /// Determine which tab bar action (if any) corresponds to a click position.
    pub fn handle_click(&self, pos_x: f32, rect: &Rect, tabs: &TabManager) -> Option<TabBarAction> {
        if tabs.is_empty() {
            return Some(TabBarAction::NewTab);
        }

        let tab_width = rect.w / (tabs.len() as f32 + 1.0); // +1 for new tab button
        let index = (pos_x / tab_width) as usize;

        if index < tabs.len() {
            Some(TabBarAction::SwitchTab(index))
        } else {
            Some(TabBarAction::NewTab)
        }
    }
}

impl Default for TabBarRenderer {
    fn default() -> Self {
        Self::new()
    }
}
