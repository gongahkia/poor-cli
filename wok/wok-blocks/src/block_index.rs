//! Block id ↔ vector-position lookup table.
//!
//! Backs O(1) `get` calls on top of a `Vec<Block>` storage. Rebuild with
//! [`BlockIndex::rebuild`] whenever the underlying vector is reordered or
//! restored from a session snapshot.

use std::collections::HashMap;

use crate::block::Block;
use crate::block_id::BlockId;

/// Maps `BlockId → position in the block vector`.
#[derive(Debug, Clone, Default)]
pub struct BlockIndex {
    by_id: HashMap<BlockId, usize>,
}

impl BlockIndex {
    /// Empty index.
    pub fn new() -> Self {
        Self::default()
    }

    /// Build an index from the current block slice.
    pub fn rebuild(&mut self, blocks: &[Block]) {
        self.by_id.clear();
        self.by_id.reserve(blocks.len());
        for (pos, block) in blocks.iter().enumerate() {
            self.by_id.insert(block.id, pos);
        }
    }

    /// Append a freshly pushed block.
    pub fn push(&mut self, id: BlockId, pos: usize) {
        self.by_id.insert(id, pos);
    }

    /// Look up vector position for `id`.
    pub fn position(&self, id: BlockId) -> Option<usize> {
        self.by_id.get(&id).copied()
    }

    /// Number of indexed blocks.
    pub fn len(&self) -> usize {
        self.by_id.len()
    }

    /// Whether the index is empty.
    pub fn is_empty(&self) -> bool {
        self.by_id.is_empty()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::time::Instant;

    fn block_with_id(id: BlockId) -> Block {
        Block {
            id,
            prompt_text: String::new(),
            command_text: String::new(),
            output_start_row: 0,
            output_end_row: 0,
            exit_code: None,
            start_time: Instant::now(),
            end_time: None,
            duration: None,
            is_collapsed: false,
            scroll_offset: 0,
            cwd: PathBuf::new(),
            git_branch: None,
            git_dirty: None,
            is_bookmarked: false,
            trigger_highlights: Vec::new(),
        }
    }

    #[test]
    fn rebuild_indexes_all() {
        let blocks = vec![block_with_id(10), block_with_id(20), block_with_id(30)];
        let mut idx = BlockIndex::new();
        idx.rebuild(&blocks);
        assert_eq!(idx.position(10), Some(0));
        assert_eq!(idx.position(20), Some(1));
        assert_eq!(idx.position(30), Some(2));
        assert_eq!(idx.position(99), None);
        assert_eq!(idx.len(), 3);
    }

    #[test]
    fn push_appends() {
        let mut idx = BlockIndex::new();
        idx.push(5, 0);
        idx.push(7, 1);
        assert_eq!(idx.position(5), Some(0));
        assert_eq!(idx.position(7), Some(1));
    }
}
