//! Predefined and user-defined pane layout presets.

use crate::splits::{SplitDirection, SplitNode};

/// One named layout preset.
#[derive(Debug, Clone)]
pub struct LayoutPreset {
    /// User-facing preset name.
    pub name: String,
    /// Longer preset description.
    pub description: String,
    /// Preset topology tree.
    pub tree: PresetNode,
}

/// A layout tree node for preset definitions.
#[derive(Debug, Clone)]
pub enum PresetNode {
    /// Leaf pane position.
    Leaf {
        /// Optional relative leaf weight hint.
        weight: f64,
    },
    /// Split with one or more children.
    Split {
        /// Split direction.
        direction: SplitDirection,
        /// Split ratio for the first branch.
        ratio: f64,
        /// Child nodes.
        children: Vec<PresetNode>,
    },
}

/// Return the built-in layout preset set.
pub fn default_layout_presets() -> Vec<LayoutPreset> {
    vec![
        LayoutPreset {
            name: "single".to_string(),
            description: "One pane".to_string(),
            tree: PresetNode::Leaf { weight: 1.0 },
        },
        LayoutPreset {
            name: "side-by-side".to_string(),
            description: "Two equal vertical panes".to_string(),
            tree: PresetNode::Split {
                direction: SplitDirection::Horizontal,
                ratio: 0.5,
                children: vec![
                    PresetNode::Leaf { weight: 1.0 },
                    PresetNode::Leaf { weight: 1.0 },
                ],
            },
        },
        LayoutPreset {
            name: "main-right".to_string(),
            description: "Main pane plus narrow right pane".to_string(),
            tree: PresetNode::Split {
                direction: SplitDirection::Horizontal,
                ratio: 0.7,
                children: vec![
                    PresetNode::Leaf { weight: 1.0 },
                    PresetNode::Leaf { weight: 1.0 },
                ],
            },
        },
        LayoutPreset {
            name: "main-bottom".to_string(),
            description: "Main pane plus bottom strip".to_string(),
            tree: PresetNode::Split {
                direction: SplitDirection::Vertical,
                ratio: 0.7,
                children: vec![
                    PresetNode::Leaf { weight: 1.0 },
                    PresetNode::Leaf { weight: 1.0 },
                ],
            },
        },
        LayoutPreset {
            name: "three-column".to_string(),
            description: "Three equal columns".to_string(),
            tree: PresetNode::Split {
                direction: SplitDirection::Horizontal,
                ratio: 1.0 / 3.0,
                children: vec![
                    PresetNode::Leaf { weight: 1.0 },
                    PresetNode::Leaf { weight: 1.0 },
                    PresetNode::Leaf { weight: 1.0 },
                ],
            },
        },
        LayoutPreset {
            name: "quad".to_string(),
            description: "2x2 grid".to_string(),
            tree: PresetNode::Split {
                direction: SplitDirection::Vertical,
                ratio: 0.5,
                children: vec![
                    PresetNode::Split {
                        direction: SplitDirection::Horizontal,
                        ratio: 0.5,
                        children: vec![
                            PresetNode::Leaf { weight: 1.0 },
                            PresetNode::Leaf { weight: 1.0 },
                        ],
                    },
                    PresetNode::Split {
                        direction: SplitDirection::Horizontal,
                        ratio: 0.5,
                        children: vec![
                            PresetNode::Leaf { weight: 1.0 },
                            PresetNode::Leaf { weight: 1.0 },
                        ],
                    },
                ],
            },
        },
        LayoutPreset {
            name: "dashboard".to_string(),
            description: "Large top pane, two bottom panes".to_string(),
            tree: PresetNode::Split {
                direction: SplitDirection::Vertical,
                ratio: 0.65,
                children: vec![
                    PresetNode::Leaf { weight: 1.0 },
                    PresetNode::Split {
                        direction: SplitDirection::Horizontal,
                        ratio: 0.5,
                        children: vec![
                            PresetNode::Leaf { weight: 1.0 },
                            PresetNode::Leaf { weight: 1.0 },
                        ],
                    },
                ],
            },
        },
    ]
}

/// Count leaf slots in a preset tree.
pub fn leaf_count(node: &PresetNode) -> usize {
    match node {
        PresetNode::Leaf { .. } => 1,
        PresetNode::Split { children, .. } => children.iter().map(leaf_count).sum(),
    }
}

/// Build a split tree from a preset and an ordered pane-id list.
pub fn build_tree_for_panes(node: &PresetNode, panes: &[u64]) -> Option<SplitNode> {
    let mut cursor = 0usize;
    let tree = build_tree_recursive(node, panes, &mut cursor)?;
    Some(tree)
}

/// Append extra panes onto the right-most branch to preserve all panes.
pub fn append_panes_to_last_leaf(mut root: SplitNode, extras: &[u64]) -> SplitNode {
    for pane_id in extras {
        root = split_rightmost_leaf(root, *pane_id);
    }
    root
}

fn build_tree_recursive(node: &PresetNode, panes: &[u64], cursor: &mut usize) -> Option<SplitNode> {
    match node {
        PresetNode::Leaf { .. } => {
            let pane_id = panes.get(*cursor).copied()?;
            *cursor = cursor.saturating_add(1);
            Some(SplitNode::Leaf { tab_id: pane_id })
        }
        PresetNode::Split {
            direction,
            ratio,
            children,
        } => {
            if children.is_empty() {
                return None;
            }
            if children.len() == 1 {
                return build_tree_recursive(&children[0], panes, cursor);
            }
            let first = build_tree_recursive(&children[0], panes, cursor)?;
            let second = if children.len() == 2 {
                build_tree_recursive(&children[1], panes, cursor)?
            } else {
                let rest = PresetNode::Split {
                    direction: *direction,
                    ratio: 0.5,
                    children: children[1..].to_vec(),
                };
                build_tree_recursive(&rest, panes, cursor)?
            };
            Some(SplitNode::Split {
                direction: *direction,
                ratio: (*ratio as f32).clamp(0.1, 0.9),
                first: Box::new(first),
                second: Box::new(second),
            })
        }
    }
}

fn split_rightmost_leaf(node: SplitNode, new_pane: u64) -> SplitNode {
    match node {
        SplitNode::Leaf { tab_id } => SplitNode::Split {
            direction: SplitDirection::Horizontal,
            ratio: 0.5,
            first: Box::new(SplitNode::Leaf { tab_id }),
            second: Box::new(SplitNode::Leaf { tab_id: new_pane }),
        },
        SplitNode::Split {
            direction,
            ratio,
            first,
            second,
        } => SplitNode::Split {
            direction,
            ratio,
            first,
            second: Box::new(split_rightmost_leaf(*second, new_pane)),
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_presets_exist() {
        let presets = default_layout_presets();
        assert!(presets.iter().any(|preset| preset.name == "single"));
        assert!(presets.iter().any(|preset| preset.name == "dashboard"));
    }

    #[test]
    fn test_leaf_count() {
        let preset = default_layout_presets()
            .into_iter()
            .find(|preset| preset.name == "three-column")
            .expect("three-column preset");
        assert_eq!(leaf_count(&preset.tree), 3);
    }

    #[test]
    fn test_build_tree_for_panes() {
        let preset = default_layout_presets()
            .into_iter()
            .find(|preset| preset.name == "side-by-side")
            .expect("side-by-side preset");
        let tree = build_tree_for_panes(&preset.tree, &[1, 2]).expect("tree");
        match tree {
            SplitNode::Split { .. } => {}
            _ => panic!("expected split tree"),
        }
    }
}
