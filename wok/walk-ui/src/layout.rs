//! Layout engine: flexbox-inspired layout system for Walk UI elements.

use std::collections::HashMap;

/// A rectangle defined by position and size.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Rect {
    /// X position (left edge).
    pub x: f32,
    /// Y position (top edge).
    pub y: f32,
    /// Width.
    pub w: f32,
    /// Height.
    pub h: f32,
}

impl Rect {
    /// Create a new rectangle.
    pub const fn new(x: f32, y: f32, w: f32, h: f32) -> Self {
        Self { x, y, w, h }
    }
}

/// A 2D size.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Size {
    /// Width.
    pub w: f32,
    /// Height.
    pub h: f32,
}

/// Unique identifier for a layout node.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct NodeId(pub u32);

/// Well-known node IDs for standard UI elements.
impl NodeId {
    /// Tab bar area.
    pub const TAB_BAR: Self = Self(1);
    /// Terminal viewport area.
    pub const TERMINAL_VIEWPORT: Self = Self(2);
    /// Input editor area.
    pub const INPUT_EDITOR: Self = Self(3);
    /// Status bar area.
    pub const STATUS_BAR: Self = Self(4);
    /// Split divider.
    pub const SPLIT_DIVIDER: Self = Self(5);
}

/// Position of the input editor relative to the terminal viewport.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputPosition {
    /// Input editor at the top (above viewport).
    Top,
    /// Input editor at the bottom (below viewport).
    Bottom,
}

/// A node in the layout tree.
#[derive(Debug, Clone)]
pub enum LayoutNode {
    /// A leaf node with a fixed or flexible size.
    Leaf {
        /// Node identifier.
        id: NodeId,
        /// Minimum size constraint.
        min_size: Size,
        /// Flex grow factor (0 = fixed size using min_size).
        flex: f32,
    },
    /// A horizontal row of children.
    Row {
        /// Child nodes.
        children: Vec<LayoutNode>,
        /// Gap between children.
        gap: f32,
    },
    /// A vertical column of children.
    Column {
        /// Child nodes.
        children: Vec<LayoutNode>,
        /// Gap between children.
        gap: f32,
    },
}

/// The result of a layout computation.
#[derive(Debug, Clone)]
pub struct LayoutResult {
    /// Computed rectangles for each leaf node.
    pub rects: HashMap<NodeId, Rect>,
}

/// Compute layout for the given tree within the available rectangle.
pub fn compute_layout(root: &LayoutNode, available: Rect) -> LayoutResult {
    let mut rects = HashMap::new();
    compute_node(root, available, &mut rects);
    LayoutResult { rects }
}

fn compute_node(node: &LayoutNode, available: Rect, rects: &mut HashMap<NodeId, Rect>) {
    match node {
        LayoutNode::Leaf { id, .. } => {
            rects.insert(*id, available);
        }
        LayoutNode::Column { children, gap } => {
            compute_flex(children, available, *gap, false, rects);
        }
        LayoutNode::Row { children, gap } => {
            compute_flex(children, available, *gap, true, rects);
        }
    }
}

fn compute_flex(
    children: &[LayoutNode],
    available: Rect,
    gap: f32,
    horizontal: bool,
    rects: &mut HashMap<NodeId, Rect>,
) {
    if children.is_empty() {
        return;
    }

    let total_gap = gap * (children.len() as f32 - 1.0).max(0.0);
    let total_available = if horizontal {
        available.w - total_gap
    } else {
        available.h - total_gap
    };

    // First pass: calculate fixed sizes and total flex
    let mut fixed_total = 0.0_f32;
    let mut flex_total = 0.0_f32;
    for child in children {
        match child {
            LayoutNode::Leaf { min_size, flex, .. } => {
                if *flex == 0.0 {
                    fixed_total += if horizontal { min_size.w } else { min_size.h };
                } else {
                    flex_total += flex;
                }
            }
            _ => {
                flex_total += 1.0; // nested containers get flex 1.0
            }
        }
    }

    let flex_space = (total_available - fixed_total).max(0.0);

    // Second pass: assign sizes and positions
    let mut offset = if horizontal { available.x } else { available.y };

    for child in children {
        let size = match child {
            LayoutNode::Leaf { min_size, flex, .. } => {
                if *flex == 0.0 {
                    if horizontal {
                        min_size.w
                    } else {
                        min_size.h
                    }
                } else if flex_total > 0.0 {
                    (flex / flex_total) * flex_space
                } else {
                    0.0
                }
            }
            _ => {
                if flex_total > 0.0 {
                    (1.0 / flex_total) * flex_space
                } else {
                    0.0
                }
            }
        };

        let child_rect = if horizontal {
            Rect::new(offset, available.y, size, available.h)
        } else {
            Rect::new(available.x, offset, available.w, size)
        };

        compute_node(child, child_rect, rects);
        offset += size + gap;
    }
}

/// Build the default terminal layout.
///
/// Layout is a column: TabBar (32px) -> [InputEditor | Viewport | InputEditor] -> StatusBar (24px)
pub fn build_default_layout(input_position: InputPosition) -> LayoutNode {
    let tab_bar = LayoutNode::Leaf {
        id: NodeId::TAB_BAR,
        min_size: Size { w: 0.0, h: 32.0 },
        flex: 0.0,
    };

    let viewport = LayoutNode::Leaf {
        id: NodeId::TERMINAL_VIEWPORT,
        min_size: Size { w: 0.0, h: 100.0 },
        flex: 1.0,
    };

    let input_editor = LayoutNode::Leaf {
        id: NodeId::INPUT_EDITOR,
        min_size: Size { w: 0.0, h: 40.0 },
        flex: 0.0,
    };

    let status_bar = LayoutNode::Leaf {
        id: NodeId::STATUS_BAR,
        min_size: Size { w: 0.0, h: 24.0 },
        flex: 0.0,
    };

    let children = match input_position {
        InputPosition::Bottom => vec![tab_bar, viewport, input_editor, status_bar],
        InputPosition::Top => vec![tab_bar, input_editor, viewport, status_bar],
    };

    LayoutNode::Column { children, gap: 0.0 }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_bottom_layout() {
        let layout = build_default_layout(InputPosition::Bottom);
        let result = compute_layout(&layout, Rect::new(0.0, 0.0, 1200.0, 800.0));

        let tab_bar = result.rects[&NodeId::TAB_BAR];
        assert!((tab_bar.x).abs() < f32::EPSILON);
        assert!((tab_bar.y).abs() < f32::EPSILON);
        assert!((tab_bar.w - 1200.0).abs() < f32::EPSILON);
        assert!((tab_bar.h - 32.0).abs() < f32::EPSILON);

        let viewport = result.rects[&NodeId::TERMINAL_VIEWPORT];
        assert!((viewport.y - 32.0).abs() < f32::EPSILON);
        assert!((viewport.w - 1200.0).abs() < f32::EPSILON);
        // Viewport gets remaining space: 800 - 32 - 40 - 24 = 704
        assert!((viewport.h - 704.0).abs() < f32::EPSILON);

        let input = result.rects[&NodeId::INPUT_EDITOR];
        assert!((input.y - 736.0).abs() < f32::EPSILON);
        assert!((input.h - 40.0).abs() < f32::EPSILON);

        let status = result.rects[&NodeId::STATUS_BAR];
        assert!((status.y - 776.0).abs() < f32::EPSILON);
        assert!((status.h - 24.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_top_layout_puts_input_before_viewport() {
        let layout = build_default_layout(InputPosition::Top);
        let result = compute_layout(&layout, Rect::new(0.0, 0.0, 1200.0, 800.0));

        let input = result.rects[&NodeId::INPUT_EDITOR];
        let viewport = result.rects[&NodeId::TERMINAL_VIEWPORT];
        assert!(input.y < viewport.y);
    }

    #[test]
    fn test_small_window_layout() {
        let layout = build_default_layout(InputPosition::Bottom);
        let result = compute_layout(&layout, Rect::new(0.0, 0.0, 600.0, 400.0));

        let viewport = result.rects[&NodeId::TERMINAL_VIEWPORT];
        // 400 - 32 - 40 - 24 = 304
        assert!((viewport.h - 304.0).abs() < f32::EPSILON);
        assert!((viewport.w - 600.0).abs() < f32::EPSILON);
    }
}
