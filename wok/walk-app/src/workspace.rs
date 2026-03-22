//! Workspace layout state for tabs and split panes.

use std::collections::HashMap;

use walk_ui::layout::Rect;
use walk_ui::splits::{SplitDirection, SplitManager, SplitNode};

/// Unique identifier for a pane in the workspace.
pub type PaneId = u64;

/// A top-level workspace tab containing a split tree of panes.
pub struct WorkspaceTab {
    /// Unique tab identifier.
    pub id: u64,
    /// User-facing title for the tab.
    pub title: String,
    /// Split layout for panes inside the tab.
    pub split_manager: SplitManager,
}

/// The mutable workspace layout state used by the runtime.
pub struct WorkspaceState {
    /// All open tabs.
    pub tabs: Vec<WorkspaceTab>,
    /// Index of the active tab.
    pub active_tab: usize,
    next_tab_id: u64,
    next_pane_id: PaneId,
}

impl WorkspaceState {
    /// Create a new workspace with a single tab and pane.
    pub fn new(initial_title: &str) -> (Self, PaneId) {
        let first_pane = 1;
        let state = Self {
            tabs: vec![WorkspaceTab {
                id: 1,
                title: initial_title.to_string(),
                split_manager: SplitManager::new(first_pane),
            }],
            active_tab: 0,
            next_tab_id: 2,
            next_pane_id: 2,
        };

        (state, first_pane)
    }

    /// Rebuild a workspace from previously serialized tabs.
    pub fn from_tabs(tabs: Vec<WorkspaceTab>, active_tab: usize) -> Self {
        let active_tab = active_tab.min(tabs.len().saturating_sub(1));
        let next_tab_id = tabs.iter().map(|tab| tab.id).max().unwrap_or(0) + 1;
        let next_pane_id = tabs
            .iter()
            .flat_map(|tab| collect_leaf_ids(&tab.split_manager.root))
            .max()
            .unwrap_or(0)
            + 1;

        Self {
            tabs,
            active_tab,
            next_tab_id,
            next_pane_id,
        }
    }

    /// Get the active tab.
    pub fn active_tab(&self) -> Option<&WorkspaceTab> {
        self.tabs.get(self.active_tab)
    }

    /// Get the active tab mutably.
    pub fn active_tab_mut(&mut self) -> Option<&mut WorkspaceTab> {
        self.tabs.get_mut(self.active_tab)
    }

    /// Get the focused pane for the active tab.
    pub fn active_pane_id(&self) -> Option<PaneId> {
        self.active_tab().map(|tab| tab.split_manager.focused_leaf)
    }

    /// Create and switch to a new tab.
    pub fn new_tab(&mut self, title: &str) -> PaneId {
        let tab_id = self.next_tab_id;
        self.next_tab_id += 1;

        let pane_id = self.next_pane_id;
        self.next_pane_id += 1;

        self.tabs.push(WorkspaceTab {
            id: tab_id,
            title: title.to_string(),
            split_manager: SplitManager::new(pane_id),
        });
        self.active_tab = self.tabs.len().saturating_sub(1);
        pane_id
    }

    /// Close the active tab and return all pane ids that should be dropped.
    pub fn close_active_tab(&mut self) -> Option<Vec<PaneId>> {
        if self.tabs.len() <= 1 {
            return None;
        }

        let removed = self.tabs.remove(self.active_tab);
        if self.active_tab >= self.tabs.len() {
            self.active_tab = self.tabs.len().saturating_sub(1);
        }
        Some(collect_leaf_ids(&removed.split_manager.root))
    }

    /// Switch to a tab by index.
    pub fn switch_tab(&mut self, index: usize) {
        if index < self.tabs.len() {
            self.active_tab = index;
        }
    }

    /// Switch to the next tab.
    pub fn next_tab(&mut self) {
        if !self.tabs.is_empty() {
            self.active_tab = (self.active_tab + 1) % self.tabs.len();
        }
    }

    /// Switch to the previous tab.
    pub fn prev_tab(&mut self) {
        if self.tabs.is_empty() {
            return;
        }
        if self.active_tab == 0 {
            self.active_tab = self.tabs.len().saturating_sub(1);
        } else {
            self.active_tab -= 1;
        }
    }

    /// Split the focused pane in the active tab.
    pub fn split_active(&mut self, direction: SplitDirection) -> Option<PaneId> {
        let new_pane_id = self.next_pane_id;
        let active_tab = self.active_tab_mut()?;
        active_tab
            .split_manager
            .split_active(direction, new_pane_id);
        self.next_pane_id += 1;
        Some(new_pane_id)
    }

    /// Close the focused pane in the active tab and return its id.
    pub fn close_active_pane(&mut self) -> Option<PaneId> {
        let active_tab = self.active_tab_mut()?;
        let leaf_ids = collect_leaf_ids(&active_tab.split_manager.root);
        if leaf_ids.len() <= 1 {
            return None;
        }

        let pane_id = active_tab.split_manager.focused_leaf;
        active_tab.split_manager.close_split(pane_id);
        Some(pane_id)
    }

    /// Resize the focused split in the active tab.
    pub fn resize_active_split(&mut self, direction: SplitDirection, delta: f32) {
        if let Some(active_tab) = self.active_tab_mut() {
            let signed_delta = match direction {
                SplitDirection::Horizontal => delta,
                SplitDirection::Vertical => delta,
            };
            active_tab
                .split_manager
                .resize_split(active_tab.split_manager.focused_leaf, signed_delta);
        }
    }

    /// Focus the pane nearest to the current one in the requested direction.
    pub fn focus_in_direction(&mut self, direction: FocusDirection, available: Rect) -> bool {
        let Some(active_tab) = self.active_tab_mut() else {
            return false;
        };
        let rects = active_tab.split_manager.compute_rects(available);
        let Some(current_rect) = rects.get(&active_tab.split_manager.focused_leaf) else {
            return false;
        };

        let current_id = active_tab.split_manager.focused_leaf;
        let next = rects
            .iter()
            .filter(|(pane_id, _)| **pane_id != current_id)
            .filter_map(|(pane_id, rect)| {
                directional_distance(direction, current_rect, rect)
                    .map(|distance| (*pane_id, distance))
            })
            .min_by(|(_, left), (_, right)| {
                left.partial_cmp(right).unwrap_or(std::cmp::Ordering::Equal)
            })
            .map(|(pane_id, _)| pane_id);

        if let Some(pane_id) = next {
            active_tab.split_manager.focused_leaf = pane_id;
            return true;
        }

        false
    }

    /// Compute pane rectangles for the active tab.
    pub fn active_pane_rects(&self, available: Rect) -> HashMap<PaneId, Rect> {
        self.active_tab().map_or_else(HashMap::new, |tab| {
            tab.split_manager.compute_rects(available)
        })
    }

    /// Get all pane ids for the active tab.
    pub fn active_pane_ids(&self) -> Vec<PaneId> {
        self.active_tab()
            .map_or_else(Vec::new, |tab| collect_leaf_ids(&tab.split_manager.root))
    }
}

impl Default for WorkspaceState {
    fn default() -> Self {
        Self::new("Walk").0
    }
}

/// Directions for pane focus navigation.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FocusDirection {
    /// Focus the pane to the left.
    Left,
    /// Focus the pane to the right.
    Right,
    /// Focus the pane above.
    Up,
    /// Focus the pane below.
    Down,
}

fn collect_leaf_ids(node: &SplitNode) -> Vec<PaneId> {
    match node {
        SplitNode::Leaf { tab_id } => vec![*tab_id],
        SplitNode::Split { first, second, .. } => {
            let mut ids = collect_leaf_ids(first);
            ids.extend(collect_leaf_ids(second));
            ids
        }
    }
}

fn directional_distance(
    direction: FocusDirection,
    current: &Rect,
    candidate: &Rect,
) -> Option<f32> {
    let current_center_x = current.x + current.w / 2.0;
    let current_center_y = current.y + current.h / 2.0;
    let candidate_center_x = candidate.x + candidate.w / 2.0;
    let candidate_center_y = candidate.y + candidate.h / 2.0;

    match direction {
        FocusDirection::Left if candidate_center_x < current_center_x => Some(
            (current_center_x - candidate_center_x) + (candidate_center_y - current_center_y).abs(),
        ),
        FocusDirection::Right if candidate_center_x > current_center_x => Some(
            (candidate_center_x - current_center_x) + (candidate_center_y - current_center_y).abs(),
        ),
        FocusDirection::Up if candidate_center_y < current_center_y => Some(
            (current_center_y - candidate_center_y) + (candidate_center_x - current_center_x).abs(),
        ),
        FocusDirection::Down if candidate_center_y > current_center_y => Some(
            (candidate_center_y - current_center_y) + (candidate_center_x - current_center_x).abs(),
        ),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_workspace_has_one_tab_and_pane() {
        let (workspace, pane_id) = WorkspaceState::new("Walk");
        assert_eq!(workspace.tabs.len(), 1);
        assert_eq!(workspace.active_pane_id(), Some(pane_id));
    }

    #[test]
    fn test_split_active_creates_new_pane() {
        let (mut workspace, initial_pane) = WorkspaceState::new("Walk");
        let new_pane = workspace
            .split_active(SplitDirection::Horizontal)
            .expect("split should create a pane");

        assert_ne!(new_pane, initial_pane);
        assert_eq!(workspace.active_pane_ids().len(), 2);
        assert_eq!(workspace.active_pane_id(), Some(new_pane));
    }

    #[test]
    fn test_close_active_tab_returns_removed_panes() {
        let (mut workspace, _) = WorkspaceState::new("Walk");
        let new_pane = workspace.new_tab("Second");
        let removed = workspace
            .close_active_tab()
            .expect("second tab should close");
        assert_eq!(removed, vec![new_pane]);
        assert_eq!(workspace.tabs.len(), 1);
    }
}
