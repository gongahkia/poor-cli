//! Workspace layout state for tabs and split panes.

use std::collections::HashMap;

use wok_ui::layout::Rect;
use wok_ui::splits::{SplitDirection, SplitDividerHit, SplitManager, SplitNode};

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
    /// Floating panes that overlay the split tree.
    pub floating_panes: Vec<FloatingPane>,
    /// Focused floating pane id, when one is focused.
    pub focused_floating: Option<PaneId>,
}

/// Metadata for one floating pane overlay.
#[derive(Debug, Clone)]
pub struct FloatingPane {
    /// Backing pane id.
    pub pane_id: PaneId,
    /// Floating rectangle in window logical pixels.
    pub rect: Rect,
    /// Z-order (higher values draw on top).
    pub z_order: u32,
    /// Visibility flag.
    pub is_visible: bool,
    /// Title shown in the floating pane title bar.
    pub title: String,
}

/// The mutable workspace layout state used by the runtime.
pub struct WorkspaceState {
    /// All open tabs.
    pub tabs: Vec<WorkspaceTab>,
    /// Index of the active tab.
    pub active_tab: usize,
    /// Whether raw input should be broadcast to every pane.
    pub broadcast_input: bool,
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
                floating_panes: Vec::new(),
                focused_floating: None,
            }],
            active_tab: 0,
            broadcast_input: false,
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
            .flat_map(collect_tab_pane_ids)
            .max()
            .unwrap_or(0)
            + 1;

        Self {
            tabs,
            active_tab,
            broadcast_input: false,
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
        self.active_tab().map(|tab| {
            tab.focused_floating
                .filter(|pane_id| {
                    tab.floating_panes
                        .iter()
                        .any(|pane| pane.pane_id == *pane_id && pane.is_visible)
                })
                .unwrap_or(tab.split_manager.focused_leaf)
        })
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
            floating_panes: Vec::new(),
            focused_floating: None,
        });
        self.active_tab = self.tabs.len().saturating_sub(1);
        pane_id
    }

    /// Close the active tab and return all pane ids that should be dropped.
    pub fn close_active_tab(&mut self) -> Option<Vec<PaneId>> {
        self.close_tab(self.active_tab)
    }

    /// Close a tab by index and return all pane ids that should be dropped.
    pub fn close_tab(&mut self, index: usize) -> Option<Vec<PaneId>> {
        if self.tabs.len() <= 1 || index >= self.tabs.len() {
            return None;
        }

        let removed = self.tabs.remove(index);
        if self.active_tab > index {
            self.active_tab -= 1;
        }
        if self.active_tab >= self.tabs.len() {
            self.active_tab = self.tabs.len().saturating_sub(1);
        }
        Some(collect_tab_pane_ids(&removed))
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
        active_tab.focused_floating = None;
        active_tab
            .split_manager
            .split_active(direction, new_pane_id);
        self.next_pane_id += 1;
        Some(new_pane_id)
    }

    /// Close the focused pane in the active tab and return its id.
    pub fn close_active_pane(&mut self) -> Option<PaneId> {
        let pane_id = self.active_pane_id()?;
        self.close_pane(pane_id)
    }

    /// Close a pane anywhere in the workspace and return its id when removed.
    pub fn close_pane(&mut self, pane_id: PaneId) -> Option<PaneId> {
        let tab_index = self.find_tab_index_for_pane(pane_id)?;
        let active_tab = self.tabs.get_mut(tab_index)?;
        if let Some(focused) = active_tab.focused_floating.take() {
            if focused != pane_id {
                active_tab.focused_floating = Some(focused);
            }
        }
        if let Some(index) = active_tab
            .floating_panes
            .iter()
            .position(|pane| pane.pane_id == pane_id)
        {
            active_tab.floating_panes.remove(index);
            if active_tab.focused_floating == Some(pane_id) {
                active_tab.focused_floating = None;
            }
            return Some(pane_id);
        }
        let leaf_ids = collect_leaf_ids(&active_tab.split_manager.root);
        if leaf_ids.len() <= 1 || !leaf_ids.contains(&pane_id) {
            return None;
        }

        active_tab.split_manager.close_split(pane_id);
        Some(pane_id)
    }

    /// Return all pane ids in a tab by index.
    pub fn pane_ids_for_tab_index(&self, index: usize) -> Vec<PaneId> {
        self.tabs
            .get(index)
            .map_or_else(Vec::new, collect_tab_pane_ids)
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

    /// Hit-test draggable split dividers in the active tab.
    pub fn hit_test_split_divider(
        &self,
        available: Rect,
        x: f32,
        y: f32,
        tolerance: f32,
    ) -> Option<SplitDividerHit> {
        self.active_tab()?
            .split_manager
            .hit_test_divider(available, x, y, tolerance)
    }

    /// Resize a split divider in the active tab by its tree path.
    pub fn resize_split_divider(&mut self, path: &[u8], delta: f32) -> bool {
        self.active_tab_mut()
            .is_some_and(|tab| tab.split_manager.resize_split_at_path(path, delta))
    }

    /// Focus the pane nearest to the current one in the requested direction.
    pub fn focus_in_direction(&mut self, direction: FocusDirection, available: Rect) -> bool {
        let current_id = self.active_pane_id();
        let Some(current_id) = current_id else {
            return false;
        };
        let rects = self.active_pane_rects(available);
        let Some(current_rect) = rects.get(&current_id) else {
            return false;
        };

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
            self.set_focus_on_active_tab(pane_id);
            return true;
        }

        if let Some(active_tab) = self.active_tab() {
            let mut floating = active_tab
                .floating_panes
                .iter()
                .filter(|pane| pane.is_visible && pane.pane_id != current_id)
                .collect::<Vec<_>>();
            floating.sort_by_key(|pane| pane.z_order);
            if let Some(next) = floating.last() {
                self.set_focus_on_active_tab(next.pane_id);
                return true;
            }
        }

        false
    }

    /// Compute pane rectangles for the active tab.
    pub fn active_pane_rects(&self, available: Rect) -> HashMap<PaneId, Rect> {
        self.active_tab().map_or_else(HashMap::new, |tab| {
            let mut rects = tab.split_manager.compute_rects(available);
            for floating in &tab.floating_panes {
                if !floating.is_visible {
                    continue;
                }
                rects.insert(floating.pane_id, clip_rect(floating.rect, available));
            }
            rects
        })
    }

    /// Get all pane ids for the active tab.
    pub fn active_pane_ids(&self) -> Vec<PaneId> {
        self.active_tab().map_or_else(Vec::new, |tab| {
            let mut ids = collect_leaf_ids(&tab.split_manager.root);
            let mut floating = tab
                .floating_panes
                .iter()
                .filter(|pane| pane.is_visible)
                .collect::<Vec<_>>();
            floating.sort_by_key(|pane| pane.z_order);
            ids.extend(floating.into_iter().map(|pane| pane.pane_id));
            ids
        })
    }

    /// Return all pane ids in the currently active workspace tab.
    pub fn all_pane_ids(&self) -> Vec<PaneId> {
        self.active_tab()
            .map_or_else(Vec::new, collect_tab_pane_ids)
    }

    /// Find the index of the tab containing the given pane.
    pub fn find_tab_index_for_pane(&self, pane_id: PaneId) -> Option<usize> {
        self.tabs.iter().position(|tab| {
            contains_pane(&tab.split_manager.root, pane_id)
                || tab
                    .floating_panes
                    .iter()
                    .any(|pane| pane.pane_id == pane_id)
        })
    }

    /// Focus a pane anywhere in the workspace and switch to its tab.
    pub fn focus_pane(&mut self, pane_id: PaneId) -> bool {
        let Some(tab_index) = self.find_tab_index_for_pane(pane_id) else {
            return false;
        };
        self.active_tab = tab_index;
        if let Some(tab) = self.tabs.get_mut(tab_index) {
            if let Some(index) = tab
                .floating_panes
                .iter()
                .position(|floating| floating.pane_id == pane_id && floating.is_visible)
            {
                tab.focused_floating = Some(pane_id);
                let next_z = tab
                    .floating_panes
                    .iter()
                    .map(|pane| pane.z_order)
                    .max()
                    .unwrap_or(0)
                    .saturating_add(1);
                tab.floating_panes[index].z_order = next_z;
            } else {
                tab.focused_floating = None;
                tab.split_manager.focused_leaf = pane_id;
            }
            return true;
        }
        false
    }

    /// Return the total number of panes in the workspace.
    pub fn pane_count(&self) -> usize {
        self.tabs
            .iter()
            .map(|tab| collect_tab_pane_ids(tab).len())
            .sum()
    }

    /// Return split-tree pane ids for the active tab (excluding floating panes).
    pub fn active_split_pane_ids(&self) -> Vec<PaneId> {
        self.active_tab()
            .map_or_else(Vec::new, |tab| collect_leaf_ids(&tab.split_manager.root))
    }

    /// Reserve and return a new pane id.
    pub fn allocate_pane_id(&mut self) -> PaneId {
        let pane_id = self.next_pane_id;
        self.next_pane_id = self.next_pane_id.saturating_add(1);
        pane_id
    }

    /// Replace the active tab split tree and focused split pane.
    pub fn set_active_split_tree(&mut self, root: SplitNode, focused_leaf: PaneId) {
        if let Some(tab) = self.active_tab_mut() {
            tab.split_manager.root = root;
            tab.split_manager.focused_leaf = focused_leaf;
            tab.focused_floating = None;
        }
    }

    /// Create a new floating pane in the active tab.
    pub fn new_floating_pane(&mut self, bounds: Rect, title: &str) -> Option<PaneId> {
        let pane_id = self.next_pane_id;
        self.next_pane_id = self.next_pane_id.saturating_add(1);
        let active_tab = self.active_tab_mut()?;
        let z_order = active_tab
            .floating_panes
            .iter()
            .map(|pane| pane.z_order)
            .max()
            .unwrap_or(0)
            .saturating_add(1);
        active_tab.floating_panes.push(FloatingPane {
            pane_id,
            rect: bounds,
            z_order,
            is_visible: true,
            title: title.to_string(),
        });
        active_tab.focused_floating = Some(pane_id);
        Some(pane_id)
    }

    /// Toggle visibility for all floating panes in the active tab.
    pub fn toggle_floating_panes(&mut self) -> Option<bool> {
        let active_tab = self.active_tab_mut()?;
        if active_tab.floating_panes.is_empty() {
            return None;
        }
        let any_visible = active_tab.floating_panes.iter().any(|pane| pane.is_visible);
        let next_visible = !any_visible;
        for pane in &mut active_tab.floating_panes {
            pane.is_visible = next_visible;
        }
        if !next_visible {
            active_tab.focused_floating = None;
        } else if let Some(topmost) = active_tab
            .floating_panes
            .iter()
            .filter(|pane| pane.is_visible)
            .max_by_key(|pane| pane.z_order)
        {
            active_tab.focused_floating = Some(topmost.pane_id);
        }
        Some(next_visible)
    }

    /// Return metadata for one visible floating pane in the active tab.
    pub fn active_floating_pane(&self, pane_id: PaneId) -> Option<&FloatingPane> {
        self.active_tab()?
            .floating_panes
            .iter()
            .find(|pane| pane.pane_id == pane_id && pane.is_visible)
    }

    /// Move a floating pane by a delta, clipping to available bounds.
    pub fn move_floating_pane(&mut self, pane_id: PaneId, dx: f32, dy: f32, bounds: Rect) -> bool {
        let Some(tab) = self.active_tab_mut() else {
            return false;
        };
        let Some(pane) = tab
            .floating_panes
            .iter_mut()
            .find(|pane| pane.pane_id == pane_id)
        else {
            return false;
        };
        pane.rect.x = (pane.rect.x + dx).clamp(bounds.x, bounds.x + bounds.w - pane.rect.w);
        pane.rect.y = (pane.rect.y + dy).clamp(bounds.y, bounds.y + bounds.h - pane.rect.h);
        true
    }

    /// Resize a floating pane by a delta, clipping to available bounds.
    pub fn resize_floating_pane(
        &mut self,
        pane_id: PaneId,
        dw: f32,
        dh: f32,
        bounds: Rect,
    ) -> bool {
        let Some(tab) = self.active_tab_mut() else {
            return false;
        };
        let Some(pane) = tab
            .floating_panes
            .iter_mut()
            .find(|pane| pane.pane_id == pane_id)
        else {
            return false;
        };
        pane.rect.w = (pane.rect.w + dw).clamp(320.0, bounds.w.max(320.0));
        pane.rect.h = (pane.rect.h + dh).clamp(200.0, bounds.h.max(200.0));
        pane.rect.x = pane
            .rect
            .x
            .clamp(bounds.x, bounds.x + bounds.w - pane.rect.w);
        pane.rect.y = pane
            .rect
            .y
            .clamp(bounds.y, bounds.y + bounds.h - pane.rect.h);
        true
    }

    /// Resize a floating pane from any edge or corner.
    pub fn resize_floating_pane_edges(
        &mut self,
        pane_id: PaneId,
        edges: FloatingResizeEdges,
        dx: f32,
        dy: f32,
        bounds: Rect,
    ) -> bool {
        let Some(tab) = self.active_tab_mut() else {
            return false;
        };
        let Some(pane) = tab
            .floating_panes
            .iter_mut()
            .find(|pane| pane.pane_id == pane_id)
        else {
            return false;
        };

        let min_w = 320.0_f32.min(bounds.w.max(1.0));
        let min_h = 200.0_f32.min(bounds.h.max(1.0));
        let mut left = pane.rect.x;
        let mut right = pane.rect.x + pane.rect.w;
        let mut top = pane.rect.y;
        let mut bottom = pane.rect.y + pane.rect.h;

        if edges.left {
            left = (left + dx).clamp(bounds.x, right - min_w);
        }
        if edges.right {
            right = (right + dx).clamp(left + min_w, bounds.x + bounds.w);
        }
        if edges.top {
            top = (top + dy).clamp(bounds.y, bottom - min_h);
        }
        if edges.bottom {
            bottom = (bottom + dy).clamp(top + min_h, bounds.y + bounds.h);
        }

        pane.rect = Rect::new(left, top, right - left, bottom - top);
        true
    }

    /// Hit-test panes for a point, prioritizing top-most floating panes.
    pub fn pane_at_point(&self, available: Rect, x: f32, y: f32) -> Option<PaneId> {
        let tab = self.active_tab()?;
        let mut floating = tab
            .floating_panes
            .iter()
            .filter(|pane| pane.is_visible)
            .collect::<Vec<_>>();
        floating.sort_by_key(|pane| pane.z_order);
        for pane in floating.into_iter().rev() {
            let rect = clip_rect(pane.rect, available);
            if contains_point(rect, x, y) {
                return Some(pane.pane_id);
            }
        }

        let split_rects = tab.split_manager.compute_rects(available);
        split_rects
            .into_iter()
            .find_map(|(pane_id, rect)| contains_point(rect, x, y).then_some(pane_id))
    }

    /// Close the focused floating pane when one is focused.
    pub fn close_focused_floating_pane(&mut self) -> Option<PaneId> {
        let tab = self.active_tab_mut()?;
        let focused = tab.focused_floating?;
        let idx = tab
            .floating_panes
            .iter()
            .position(|pane| pane.pane_id == focused)?;
        tab.floating_panes.remove(idx);
        tab.focused_floating = None;
        Some(focused)
    }

    /// Return whether a pane is tracked as floating in the active tab.
    pub fn is_active_floating_pane(&self, pane_id: PaneId) -> bool {
        self.active_tab().is_some_and(|tab| {
            tab.floating_panes
                .iter()
                .any(|pane| pane.pane_id == pane_id && pane.is_visible)
        })
    }

    fn set_focus_on_active_tab(&mut self, pane_id: PaneId) {
        let Some(tab) = self.active_tab_mut() else {
            return;
        };
        if let Some(index) = tab
            .floating_panes
            .iter()
            .position(|pane| pane.pane_id == pane_id && pane.is_visible)
        {
            tab.focused_floating = Some(pane_id);
            let next_z = tab
                .floating_panes
                .iter()
                .map(|pane| pane.z_order)
                .max()
                .unwrap_or(0)
                .saturating_add(1);
            tab.floating_panes[index].z_order = next_z;
        } else {
            tab.focused_floating = None;
            tab.split_manager.focused_leaf = pane_id;
        }
    }
}

impl Default for WorkspaceState {
    fn default() -> Self {
        Self::new("Wok").0
    }
}

/// Edges involved in a floating pane resize.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct FloatingResizeEdges {
    /// Left edge.
    pub left: bool,
    /// Right edge.
    pub right: bool,
    /// Top edge.
    pub top: bool,
    /// Bottom edge.
    pub bottom: bool,
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

fn contains_pane(node: &SplitNode, target: PaneId) -> bool {
    match node {
        SplitNode::Leaf { tab_id } => *tab_id == target,
        SplitNode::Split { first, second, .. } => {
            contains_pane(first, target) || contains_pane(second, target)
        }
    }
}

fn collect_tab_pane_ids(tab: &WorkspaceTab) -> Vec<PaneId> {
    let mut ids = collect_leaf_ids(&tab.split_manager.root);
    ids.extend(tab.floating_panes.iter().map(|pane| pane.pane_id));
    ids
}

fn clip_rect(rect: Rect, bounds: Rect) -> Rect {
    let x = rect.x.max(bounds.x);
    let y = rect.y.max(bounds.y);
    let right = (rect.x + rect.w).min(bounds.x + bounds.w);
    let bottom = (rect.y + rect.h).min(bounds.y + bounds.h);
    Rect::new(x, y, (right - x).max(0.0), (bottom - y).max(0.0))
}

fn contains_point(rect: Rect, x: f32, y: f32) -> bool {
    x >= rect.x && y >= rect.y && x <= rect.x + rect.w && y <= rect.y + rect.h
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_workspace_has_one_tab_and_pane() {
        let (workspace, pane_id) = WorkspaceState::new("Wok");
        assert_eq!(workspace.tabs.len(), 1);
        assert_eq!(workspace.active_pane_id(), Some(pane_id));
    }

    #[test]
    fn test_split_active_creates_new_pane() {
        let (mut workspace, initial_pane) = WorkspaceState::new("Wok");
        let new_pane = workspace
            .split_active(SplitDirection::Horizontal)
            .expect("split should create a pane");

        assert_ne!(new_pane, initial_pane);
        assert_eq!(workspace.active_pane_ids().len(), 2);
        assert_eq!(workspace.active_pane_id(), Some(new_pane));
    }

    #[test]
    fn test_close_active_tab_returns_removed_panes() {
        let (mut workspace, _) = WorkspaceState::new("Wok");
        let new_pane = workspace.new_tab("Second");
        let removed = workspace
            .close_active_tab()
            .expect("second tab should close");
        assert_eq!(removed, vec![new_pane]);
        assert_eq!(workspace.tabs.len(), 1);
    }

    #[test]
    fn test_close_pane_by_id_removes_split_leaf() {
        let (mut workspace, first_pane) = WorkspaceState::new("Wok");
        let second_pane = workspace
            .split_active(SplitDirection::Horizontal)
            .expect("split should create a pane");

        assert_eq!(workspace.close_pane(second_pane), Some(second_pane));
        assert_eq!(workspace.active_pane_ids(), vec![first_pane]);
    }

    #[test]
    fn test_close_tab_by_index_preserves_active_tab() {
        let (mut workspace, _) = WorkspaceState::new("Wok");
        let second_pane = workspace.new_tab("Second");
        let third_pane = workspace.new_tab("Third");

        assert_eq!(workspace.close_tab(1), Some(vec![second_pane]));
        assert_eq!(workspace.tabs.len(), 2);
        assert_eq!(workspace.active_pane_id(), Some(third_pane));
    }

    #[test]
    fn test_resize_split_divider_by_hit_path() {
        let (mut workspace, first_pane) = WorkspaceState::new("Wok");
        workspace
            .split_active(SplitDirection::Horizontal)
            .expect("split should create a pane");
        let bounds = Rect::new(0.0, 0.0, 800.0, 600.0);
        let hit = workspace
            .hit_test_split_divider(bounds, 400.0, 200.0, 8.0)
            .expect("divider should hit");

        assert!(workspace.resize_split_divider(&hit.path, 0.1));
        let rects = workspace.active_pane_rects(bounds);
        assert!((rects[&first_pane].w - 480.0).abs() < 0.01);
    }

    #[test]
    fn test_resize_floating_pane_from_left_edge() {
        let (mut workspace, _) = WorkspaceState::new("Wok");
        let bounds = Rect::new(0.0, 0.0, 900.0, 700.0);
        let pane_id = workspace
            .new_floating_pane(Rect::new(100.0, 100.0, 400.0, 300.0), "Float")
            .expect("floating pane should be created");

        assert!(workspace.resize_floating_pane_edges(
            pane_id,
            FloatingResizeEdges {
                left: true,
                right: false,
                top: false,
                bottom: false,
            },
            -40.0,
            0.0,
            bounds,
        ));
        let floating = workspace
            .active_floating_pane(pane_id)
            .expect("floating pane should remain");
        assert!((floating.rect.x - 60.0).abs() < 0.01);
        assert!((floating.rect.w - 440.0).abs() < 0.01);
    }
}
