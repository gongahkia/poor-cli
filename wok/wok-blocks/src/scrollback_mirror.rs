//! Parallel scrollback mirror keyed by absolute row.
//!
//! `alacritty_terminal::Grid` owns the actual scrollback bytes; we don't
//! touch it. This module maintains a *separate* `SumTree<LineSnapshot>`
//! the renderer can consult for:
//!   * `O(log n)` row → block-boundary lookup (replaces the linear scan in
//!     `block_nav.rs`).
//!   * `O(log n)` "Nth visible line under a filter predicate" once block
//!     filtering (P7.1) ships.
//!
//! Updates are pushed by [`BlockManager`](crate::block_manager::BlockManager)
//! on block transitions and by the renderer on viewport scroll. The mirror
//! is gated by `wok_features::FeatureFlag::SumTreeScrollback` — callers
//! check the flag and either consult the mirror or fall back to linear
//! scans.

use wok_sumtree::{Item, SumTree, Summary};

use crate::block_id::BlockId;

/// One mirrored line.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct LineSnapshot {
    /// Absolute scrollback row this line represents.
    pub absolute_row: usize,
    /// Block this line belongs to (if any).
    pub block_id: Option<BlockId>,
    /// `true` if the line is visible under the current filter predicate.
    pub visible: bool,
    /// `true` if this line is the first row of its block (boundary marker).
    pub is_boundary: bool,
}

/// Aggregated counts over a contiguous run of [`LineSnapshot`]s.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct LineSummary {
    /// Total snapshots in the run.
    pub total: usize,
    /// Snapshots whose `visible == true`.
    pub visible: usize,
    /// Snapshots whose `is_boundary == true`.
    pub boundaries: usize,
}

impl Summary for LineSummary {
    fn add(&mut self, other: &Self) {
        self.total += other.total;
        self.visible += other.visible;
        self.boundaries += other.boundaries;
    }
}

impl Item for LineSnapshot {
    type Summary = LineSummary;

    fn summary(&self) -> Self::Summary {
        LineSummary {
            total: 1,
            visible: usize::from(self.visible),
            boundaries: usize::from(self.is_boundary),
        }
    }
}

/// Mirror state. Wraps a `SumTree<LineSnapshot>` w/ helpers tuned to the
/// scrollback use cases.
#[derive(Clone, Default)]
pub struct ScrollbackMirror {
    tree: SumTree<LineSnapshot>,
}

impl std::fmt::Debug for ScrollbackMirror {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("ScrollbackMirror")
            .field("len", &self.tree.len())
            .finish()
    }
}

impl ScrollbackMirror {
    /// Empty mirror.
    pub fn new() -> Self {
        Self::default()
    }

    /// Number of mirrored lines.
    pub fn len(&self) -> usize {
        self.tree.len()
    }

    /// `true` if no lines are tracked.
    pub fn is_empty(&self) -> bool {
        self.tree.is_empty()
    }

    /// Aggregate summary (totals across the whole mirror).
    pub fn summary(&self) -> LineSummary {
        self.tree.summary()
    }

    /// Append a snapshot (assumed to be the next absolute row).
    pub fn push(&mut self, snap: LineSnapshot) {
        self.tree.push(snap);
    }

    /// Borrow the i'th mirrored line.
    pub fn get(&self, i: usize) -> Option<&LineSnapshot> {
        self.tree.get(i)
    }

    /// Index of the `nth` boundary (0-based), if it exists.
    ///
    /// Uses `seek_by` over the `boundaries` projection — `O(log n)`.
    pub fn nth_boundary(&self, nth: usize) -> Option<usize> {
        let target = nth + 1;
        let total = self.summary().boundaries;
        if total < target {
            return None;
        }
        self.tree.seek_by(target, &|s: &LineSummary| s.boundaries)
    }

    /// Index of the `nth` visible line under the current filter, if it exists.
    pub fn nth_visible(&self, nth: usize) -> Option<usize> {
        let target = nth + 1;
        let total = self.summary().visible;
        if total < target {
            return None;
        }
        self.tree.seek_by(target, &|s: &LineSummary| s.visible)
    }

    /// Block id at row `absolute_row`, if any. Linear in `len()` for now —
    /// real `O(log n)` requires a separate sorted index by absolute_row,
    /// which is a follow-up.
    pub fn block_at_row(&self, absolute_row: usize) -> Option<BlockId> {
        self.tree
            .iter()
            .find(|s| s.absolute_row == absolute_row)
            .and_then(|s| s.block_id)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn line(row: usize, block: Option<BlockId>, visible: bool, boundary: bool) -> LineSnapshot {
        LineSnapshot {
            absolute_row: row,
            block_id: block,
            visible,
            is_boundary: boundary,
        }
    }

    #[test]
    fn empty_mirror_has_zero_summary() {
        let m = ScrollbackMirror::new();
        assert!(m.is_empty());
        assert_eq!(m.summary(), LineSummary::default());
    }

    #[test]
    fn push_accumulates_summary() {
        let mut m = ScrollbackMirror::new();
        m.push(line(0, Some(1), true, true));
        m.push(line(1, Some(1), true, false));
        m.push(line(2, Some(2), false, true));
        m.push(line(3, Some(2), true, false));
        let s = m.summary();
        assert_eq!(s.total, 4);
        assert_eq!(s.visible, 3);
        assert_eq!(s.boundaries, 2);
    }

    #[test]
    fn nth_boundary_seeks_correctly() {
        let mut m = ScrollbackMirror::new();
        m.push(line(0, Some(1), true, true));
        m.push(line(1, Some(1), true, false));
        m.push(line(2, Some(2), true, true));
        m.push(line(3, Some(3), true, true));
        assert_eq!(m.nth_boundary(0), Some(0));
        assert_eq!(m.nth_boundary(1), Some(2));
        assert_eq!(m.nth_boundary(2), Some(3));
        assert_eq!(m.nth_boundary(3), None);
    }

    #[test]
    fn nth_visible_seeks_correctly() {
        let mut m = ScrollbackMirror::new();
        m.push(line(0, None, false, false));
        m.push(line(1, None, true, false));
        m.push(line(2, None, false, false));
        m.push(line(3, None, true, false));
        m.push(line(4, None, true, false));
        assert_eq!(m.nth_visible(0), Some(1));
        assert_eq!(m.nth_visible(1), Some(3));
        assert_eq!(m.nth_visible(2), Some(4));
        assert_eq!(m.nth_visible(3), None);
    }

    #[test]
    fn block_at_row_lookup() {
        let mut m = ScrollbackMirror::new();
        m.push(line(0, Some(7), true, true));
        m.push(line(1, Some(7), true, false));
        m.push(line(2, Some(8), true, true));
        assert_eq!(m.block_at_row(1), Some(7));
        assert_eq!(m.block_at_row(2), Some(8));
        assert_eq!(m.block_at_row(99), None);
    }

    #[test]
    fn scales_to_many_lines() {
        let mut m = ScrollbackMirror::new();
        for i in 0..10_000 {
            m.push(line(i, Some(i as BlockId / 10), i % 2 == 0, i % 10 == 0));
        }
        assert_eq!(m.len(), 10_000);
        let s = m.summary();
        assert_eq!(s.total, 10_000);
        assert_eq!(s.visible, 5_000);
        assert_eq!(s.boundaries, 1_000);
        // 500th boundary is at row 500 * 10 = 5000.
        assert_eq!(m.nth_boundary(500), Some(5_000));
    }

    #[test]
    fn line_summary_add_combines_counts() {
        let mut a = LineSummary {
            total: 3,
            visible: 2,
            boundaries: 1,
        };
        let b = LineSummary {
            total: 4,
            visible: 1,
            boundaries: 2,
        };
        a.add(&b);
        assert_eq!(a.total, 7);
        assert_eq!(a.visible, 3);
        assert_eq!(a.boundaries, 3);
    }
}
