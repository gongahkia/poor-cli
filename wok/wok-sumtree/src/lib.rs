//! Indexed B-tree of summarisable items.
//!
//! A `SumTree<T>` stores a sequence of `T: Item` and maintains a hierarchical
//! `T::Summary` so positional queries are `O(log n)` instead of `O(n)`.
//!
//! Operations:
//!   * `push` — append an item.
//!   * `extend` — append many.
//!   * `get(i)` — borrow the i'th item.
//!   * `len`, `is_empty`, `summary` — totals.
//!   * `iter` — depth-first item iteration.
//!   * `seek_by` — find the first index whose cumulative summary projection
//!     reaches a target. Useful for "row at line N" / "byte at offset M".
//!
//! The tree is balanced by amortised splits on overflow. Min fan-out is 4,
//! max is 8 — small enough that internal nodes remain cache friendly while
//! keeping height low for typical scrollback sizes (10⁵–10⁶ items).

#![deny(missing_docs)]

mod node;

pub use node::{Item, Summary};

use node::Node;

/// Indexed B-tree of `T`.
#[derive(Clone)]
pub struct SumTree<T: Item> {
    root: Node<T>,
}

impl<T: Item> SumTree<T> {
    /// Empty tree.
    pub fn new() -> Self {
        Self { root: Node::leaf() }
    }

    /// Total item count.
    pub fn len(&self) -> usize {
        self.root.count()
    }

    /// `true` if `len() == 0`.
    pub fn is_empty(&self) -> bool {
        self.root.count() == 0
    }

    /// Aggregate summary of every item.
    pub fn summary(&self) -> T::Summary {
        self.root.summary().clone()
    }

    /// Append `item`.
    pub fn push(&mut self, item: T) {
        if let Some(extra) = self.root.push(item) {
            // Root split — grow upward.
            self.root =
                Node::internal_from(vec![std::mem::replace(&mut self.root, Node::leaf()), extra]);
        }
    }

    /// Append many items.
    pub fn extend<I: IntoIterator<Item = T>>(&mut self, iter: I) {
        for item in iter {
            self.push(item);
        }
    }

    /// Borrow the i'th item, or `None` if out of bounds.
    pub fn get(&self, index: usize) -> Option<&T> {
        if index >= self.len() {
            return None;
        }
        Some(self.root.get(index))
    }

    /// Depth-first iterator over items.
    pub fn iter(&self) -> Iter<'_, T> {
        Iter {
            stack: vec![Frame::node(&self.root)],
        }
    }

    /// Find the first index `i` such that `project(prefix_summary[0..=i]) >= target`.
    /// Returns `None` if the projected total never reaches `target`.
    ///
    /// `project` is called on cumulative summaries during descent.
    pub fn seek_by<F>(&self, target: usize, project: &F) -> Option<usize>
    where
        F: Fn(&T::Summary) -> usize,
    {
        let mut acc = T::Summary::default();
        self.root.seek_by(target, project, &mut acc, 0)
    }
}

impl<T: Item> Default for SumTree<T> {
    fn default() -> Self {
        Self::new()
    }
}

/// Iterator over `&T`.
pub struct Iter<'a, T: Item> {
    stack: Vec<Frame<'a, T>>,
}

enum Frame<'a, T: Item> {
    Internal { children: &'a [Node<T>], idx: usize },
    Leaf { items: &'a [T], idx: usize },
}

impl<'a, T: Item> Frame<'a, T> {
    fn node(n: &'a Node<T>) -> Self {
        match n {
            Node::Internal { children, .. } => Frame::Internal { children, idx: 0 },
            Node::Leaf { items, .. } => Frame::Leaf { items, idx: 0 },
        }
    }
}

impl<'a, T: Item> Iterator for Iter<'a, T> {
    type Item = &'a T;
    fn next(&mut self) -> Option<&'a T> {
        loop {
            let frame = self.stack.last_mut()?;
            match frame {
                Frame::Leaf { items, idx } => {
                    if *idx < items.len() {
                        let item = &items[*idx];
                        *idx += 1;
                        return Some(item);
                    }
                    self.stack.pop();
                }
                Frame::Internal { children, idx } => {
                    if *idx < children.len() {
                        let child = &children[*idx];
                        *idx += 1;
                        self.stack.push(Frame::node(child));
                    } else {
                        self.stack.pop();
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[derive(Debug, Clone, Default, PartialEq, Eq)]
    struct CountSummary(usize);
    impl Summary for CountSummary {
        fn add(&mut self, other: &Self) {
            self.0 += other.0;
        }
    }

    #[derive(Debug, Clone, Copy, PartialEq, Eq)]
    struct U(u32);
    impl Item for U {
        type Summary = CountSummary;
        fn summary(&self) -> CountSummary {
            CountSummary(1)
        }
    }

    #[test]
    fn empty_basics() {
        let t: SumTree<U> = SumTree::new();
        assert_eq!(t.len(), 0);
        assert!(t.is_empty());
        assert_eq!(t.summary(), CountSummary(0));
        assert!(t.get(0).is_none());
        assert_eq!(t.iter().count(), 0);
    }

    #[test]
    fn push_grows() {
        let mut t = SumTree::new();
        for i in 0..200u32 {
            t.push(U(i));
        }
        assert_eq!(t.len(), 200);
        assert_eq!(t.summary(), CountSummary(200));
    }

    #[test]
    fn get_matches_push_order() {
        let mut t = SumTree::new();
        for i in 0..1000u32 {
            t.push(U(i));
        }
        for i in 0..1000usize {
            assert_eq!(t.get(i).copied(), Some(U(i as u32)));
        }
        assert!(t.get(1000).is_none());
    }

    #[test]
    fn iter_in_order() {
        let mut t = SumTree::new();
        for i in 0..500u32 {
            t.push(U(i));
        }
        let collected: Vec<u32> = t.iter().map(|u| u.0).collect();
        let expected: Vec<u32> = (0..500).collect();
        assert_eq!(collected, expected);
    }

    #[test]
    fn seek_by_finds_first_hit() {
        let mut t = SumTree::new();
        for i in 0..100u32 {
            t.push(U(i));
        }
        // CountSummary projects to "items so far"; seeking row N finds index N.
        for target in 1..=100 {
            assert_eq!(t.seek_by(target, &|s: &CountSummary| s.0), Some(target - 1));
        }
        assert_eq!(t.seek_by(101, &|s: &CountSummary| s.0), None);
    }

    #[test]
    fn extend_works() {
        let mut t = SumTree::new();
        t.extend((0..50u32).map(U));
        assert_eq!(t.len(), 50);
        assert_eq!(t.iter().count(), 50);
    }

    /// Variable-weight items: projection sums weights, not counts.
    #[test]
    fn seek_by_with_variable_weights() {
        #[derive(Debug, Clone, Default, PartialEq, Eq)]
        struct ByteSummary(usize);
        impl Summary for ByteSummary {
            fn add(&mut self, other: &Self) {
                self.0 += other.0;
            }
        }
        #[derive(Debug, Clone)]
        struct Line(String);
        impl Item for Line {
            type Summary = ByteSummary;
            fn summary(&self) -> ByteSummary {
                ByteSummary(self.0.len())
            }
        }

        let mut t: SumTree<Line> = SumTree::new();
        t.push(Line("hello".into())); // 5
        t.push(Line("world".into())); // 5
        t.push(Line("!".into())); // 1
                                  // Cumulative bytes: 5, 10, 11.
        assert_eq!(t.seek_by(1, &|s: &ByteSummary| s.0), Some(0));
        assert_eq!(t.seek_by(5, &|s: &ByteSummary| s.0), Some(0));
        assert_eq!(t.seek_by(6, &|s: &ByteSummary| s.0), Some(1));
        assert_eq!(t.seek_by(11, &|s: &ByteSummary| s.0), Some(2));
        assert_eq!(t.seek_by(12, &|s: &ByteSummary| s.0), None);
    }
}
