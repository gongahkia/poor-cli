//! Internal B-tree node.

const MAX_LEAF: usize = 8;
const MAX_INTERNAL: usize = 8;

/// Aggregable summary attached to each item.
pub trait Summary: Default + Clone {
    /// Fold `other` into `self`.
    fn add(&mut self, other: &Self);
}

/// An item carrying a [`Summary`].
pub trait Item: Clone {
    /// Summary type produced by this item.
    type Summary: Summary;
    /// Compute this item's summary.
    fn summary(&self) -> Self::Summary;
}

#[derive(Clone)]
pub(crate) enum Node<T: Item> {
    Leaf {
        items: Vec<T>,
        summary: T::Summary,
    },
    Internal {
        children: Vec<Node<T>>,
        summary: T::Summary,
        // Cached child counts, parallel to `children`. Used for O(log n) get.
        counts: Vec<usize>,
    },
}

impl<T: Item> Node<T> {
    pub(crate) fn leaf() -> Self {
        Node::Leaf {
            items: Vec::new(),
            summary: T::Summary::default(),
        }
    }

    pub(crate) fn internal_from(children: Vec<Node<T>>) -> Self {
        let mut summary = T::Summary::default();
        let mut counts = Vec::with_capacity(children.len());
        for c in &children {
            summary.add(c.summary());
            counts.push(c.count());
        }
        Node::Internal {
            children,
            summary,
            counts,
        }
    }

    pub(crate) fn summary(&self) -> &T::Summary {
        match self {
            Node::Leaf { summary, .. } | Node::Internal { summary, .. } => summary,
        }
    }

    pub(crate) fn count(&self) -> usize {
        match self {
            Node::Leaf { items, .. } => items.len(),
            Node::Internal { counts, .. } => counts.iter().sum(),
        }
    }

    /// Push `item`. If a split occurs, return the right-sibling that the
    /// caller must place alongside this node.
    pub(crate) fn push(&mut self, item: T) -> Option<Node<T>> {
        match self {
            Node::Leaf { items, summary } => {
                summary.add(&item.summary());
                items.push(item);
                if items.len() > MAX_LEAF {
                    Some(self.split_leaf())
                } else {
                    None
                }
            }
            Node::Internal {
                children,
                summary,
                counts,
            } => {
                summary.add(&item.summary());
                let last = children.len() - 1;
                let split = children[last].push(item);
                counts[last] = children[last].count();
                if let Some(extra) = split {
                    counts.push(extra.count());
                    children.push(extra);
                    if children.len() > MAX_INTERNAL {
                        Some(self.split_internal())
                    } else {
                        None
                    }
                } else {
                    None
                }
            }
        }
    }

    fn split_leaf(&mut self) -> Node<T> {
        let Node::Leaf { items, summary } = self else {
            unreachable!()
        };
        let mid = items.len() / 2;
        let right_items: Vec<T> = items.split_off(mid);
        let mut left_sum = T::Summary::default();
        for it in items.iter() {
            left_sum.add(&it.summary());
        }
        let mut right_sum = T::Summary::default();
        for it in right_items.iter() {
            right_sum.add(&it.summary());
        }
        *summary = left_sum;
        Node::Leaf {
            items: right_items,
            summary: right_sum,
        }
    }

    fn split_internal(&mut self) -> Node<T> {
        let Node::Internal {
            children,
            summary,
            counts,
        } = self
        else {
            unreachable!()
        };
        let mid = children.len() / 2;
        let right_children: Vec<Node<T>> = children.split_off(mid);
        let right_counts: Vec<usize> = counts.split_off(mid);
        let mut left_sum = T::Summary::default();
        for c in children.iter() {
            left_sum.add(c.summary());
        }
        let mut right_sum = T::Summary::default();
        for c in right_children.iter() {
            right_sum.add(c.summary());
        }
        *summary = left_sum;
        Node::Internal {
            children: right_children,
            summary: right_sum,
            counts: right_counts,
        }
    }

    /// O(log n) lookup; caller must guarantee `index < self.count()`.
    pub(crate) fn get(&self, mut index: usize) -> &T {
        let mut node = self;
        loop {
            match node {
                Node::Leaf { items, .. } => return &items[index],
                Node::Internal {
                    children, counts, ..
                } => {
                    let mut child_idx = 0;
                    while child_idx < children.len() && index >= counts[child_idx] {
                        index -= counts[child_idx];
                        child_idx += 1;
                    }
                    node = &children[child_idx];
                }
            }
        }
    }

    /// Find the first absolute index whose cumulative summary projection
    /// reaches `target`. `acc` accumulates the prefix to the *left* of `node`.
    /// `offset` is the absolute index of the leftmost item in `node`.
    pub(crate) fn seek_by<F>(
        &self,
        target: usize,
        project: &F,
        acc: &mut T::Summary,
        offset: usize,
    ) -> Option<usize>
    where
        F: Fn(&T::Summary) -> usize,
    {
        match self {
            Node::Leaf { items, .. } => {
                for (i, item) in items.iter().enumerate() {
                    acc.add(&item.summary());
                    if project(acc) >= target {
                        return Some(offset + i);
                    }
                }
                None
            }
            Node::Internal {
                children, counts, ..
            } => {
                let mut local_offset = offset;
                for (i, child) in children.iter().enumerate() {
                    let mut probe = acc.clone();
                    probe.add(child.summary());
                    if project(&probe) >= target {
                        return child.seek_by(target, project, acc, local_offset);
                    }
                    *acc = probe;
                    local_offset += counts[i];
                }
                None
            }
        }
    }
}
