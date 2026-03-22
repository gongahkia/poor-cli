//! Split pane management: binary tree of horizontal/vertical splits.

use std::collections::HashMap;

use crate::layout::Rect;

/// Split direction.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SplitDirection {
    /// Split left/right.
    Horizontal,
    /// Split top/bottom.
    Vertical,
}

/// A node in the split tree.
#[derive(Debug, Clone)]
pub enum SplitNode {
    /// A leaf pane containing a tab.
    Leaf {
        /// Tab ID.
        tab_id: u64,
    },
    /// A split containing two children.
    Split {
        /// Split direction.
        direction: SplitDirection,
        /// Split ratio (0.0-1.0, first child's fraction).
        ratio: f32,
        /// First child (left or top).
        first: Box<SplitNode>,
        /// Second child (right or bottom).
        second: Box<SplitNode>,
    },
}

/// Manages the split pane tree.
pub struct SplitManager {
    /// Root of the split tree.
    pub root: SplitNode,
    /// Currently focused leaf's tab ID.
    pub focused_leaf: u64,
}

impl SplitManager {
    /// Create a new split manager with a single pane.
    pub fn new(tab_id: u64) -> Self {
        Self {
            root: SplitNode::Leaf { tab_id },
            focused_leaf: tab_id,
        }
    }

    /// Split the focused pane in the given direction.
    pub fn split_active(&mut self, direction: SplitDirection, new_tab_id: u64) {
        let old_id = self.focused_leaf;
        self.root = split_node(self.root.clone(), old_id, direction, new_tab_id);
        self.focused_leaf = new_tab_id;
    }

    /// Close a pane, collapsing its parent split.
    pub fn close_split(&mut self, tab_id: u64) {
        if let Some(new_root) = remove_leaf(self.root.clone(), tab_id) {
            self.root = new_root;
            // Update focus to first available leaf
            self.focused_leaf = first_leaf(&self.root);
        }
    }

    /// Resize a split by adjusting its ratio.
    pub fn resize_split(&mut self, tab_id: u64, delta: f32) {
        resize_in_tree(&mut self.root, tab_id, delta);
    }

    /// Compute screen rects for all leaf panes.
    pub fn compute_rects(&self, available: Rect) -> HashMap<u64, Rect> {
        let mut rects = HashMap::new();
        compute_rects_recursive(&self.root, available, &mut rects);
        rects
    }
}

fn split_node(
    node: SplitNode,
    target: u64,
    direction: SplitDirection,
    new_id: u64,
) -> SplitNode {
    match node {
        SplitNode::Leaf { tab_id } if tab_id == target => SplitNode::Split {
            direction,
            ratio: 0.5,
            first: Box::new(SplitNode::Leaf { tab_id }),
            second: Box::new(SplitNode::Leaf { tab_id: new_id }),
        },
        SplitNode::Split {
            direction: d,
            ratio,
            first,
            second,
        } => SplitNode::Split {
            direction: d,
            ratio,
            first: Box::new(split_node(*first, target, direction, new_id)),
            second: Box::new(split_node(*second, target, direction, new_id)),
        },
        other => other,
    }
}

fn remove_leaf(node: SplitNode, target: u64) -> Option<SplitNode> {
    match node {
        SplitNode::Leaf { tab_id } if tab_id == target => None,
        SplitNode::Leaf { .. } => Some(node),
        SplitNode::Split {
            first, second, ..
        } => {
            let f = remove_leaf(*first, target);
            let s = remove_leaf(*second, target);
            match (f, s) {
                (Some(f), Some(s)) => Some(SplitNode::Split {
                    direction: SplitDirection::Vertical,
                    ratio: 0.5,
                    first: Box::new(f),
                    second: Box::new(s),
                }),
                (Some(n), None) | (None, Some(n)) => Some(n),
                (None, None) => None,
            }
        }
    }
}

fn first_leaf(node: &SplitNode) -> u64 {
    match node {
        SplitNode::Leaf { tab_id } => *tab_id,
        SplitNode::Split { first, .. } => first_leaf(first),
    }
}

fn resize_in_tree(node: &mut SplitNode, target: u64, delta: f32) {
    if let SplitNode::Split {
        ratio,
        first,
        second,
        ..
    } = node
    {
        if contains_leaf(first, target) {
            *ratio = (*ratio + delta).clamp(0.1, 0.9);
        } else if contains_leaf(second, target) {
            *ratio = (*ratio - delta).clamp(0.1, 0.9);
        }
        resize_in_tree(first, target, delta);
        resize_in_tree(second, target, delta);
    }
}

fn contains_leaf(node: &SplitNode, target: u64) -> bool {
    match node {
        SplitNode::Leaf { tab_id } => *tab_id == target,
        SplitNode::Split { first, second, .. } => {
            contains_leaf(first, target) || contains_leaf(second, target)
        }
    }
}

fn compute_rects_recursive(
    node: &SplitNode,
    available: Rect,
    rects: &mut HashMap<u64, Rect>,
) {
    match node {
        SplitNode::Leaf { tab_id } => {
            rects.insert(*tab_id, available);
        }
        SplitNode::Split {
            direction,
            ratio,
            first,
            second,
        } => {
            let (r1, r2) = match direction {
                SplitDirection::Vertical => {
                    let h1 = available.h * ratio;
                    let h2 = available.h - h1;
                    (
                        Rect::new(available.x, available.y, available.w, h1),
                        Rect::new(available.x, available.y + h1, available.w, h2),
                    )
                }
                SplitDirection::Horizontal => {
                    let w1 = available.w * ratio;
                    let w2 = available.w - w1;
                    (
                        Rect::new(available.x, available.y, w1, available.h),
                        Rect::new(available.x + w1, available.y, w2, available.h),
                    )
                }
            };
            compute_rects_recursive(first, r1, rects);
            compute_rects_recursive(second, r2, rects);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_split_vertical() {
        let mut sm = SplitManager::new(1);
        sm.split_active(SplitDirection::Vertical, 2);
        let rects = sm.compute_rects(Rect::new(0.0, 0.0, 800.0, 600.0));
        assert_eq!(rects.len(), 2);
        assert!((rects[&1].h - 300.0).abs() < f32::EPSILON);
        assert!((rects[&2].h - 300.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_split_horizontal() {
        let mut sm = SplitManager::new(1);
        sm.split_active(SplitDirection::Horizontal, 2);
        let rects = sm.compute_rects(Rect::new(0.0, 0.0, 800.0, 600.0));
        assert!((rects[&1].w - 400.0).abs() < f32::EPSILON);
        assert!((rects[&2].w - 400.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_close_split() {
        let mut sm = SplitManager::new(1);
        sm.split_active(SplitDirection::Vertical, 2);
        sm.close_split(2);
        let rects = sm.compute_rects(Rect::new(0.0, 0.0, 800.0, 600.0));
        assert_eq!(rects.len(), 1);
        assert!(rects.contains_key(&1));
    }

    #[test]
    fn test_nested_splits() {
        let mut sm = SplitManager::new(1);
        sm.split_active(SplitDirection::Horizontal, 2);
        sm.split_active(SplitDirection::Vertical, 3);
        let rects = sm.compute_rects(Rect::new(0.0, 0.0, 800.0, 600.0));
        assert_eq!(rects.len(), 3);
    }
}
