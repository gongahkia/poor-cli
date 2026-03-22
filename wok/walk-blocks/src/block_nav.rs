//! Block navigation: keyboard-driven block selection and actions.

use crate::block::{Block, BlockManager};

/// Block navigator for keyboard-driven block selection.
pub struct BlockNavigator {
    /// Index of the currently selected block (if any).
    pub selected_block_index: Option<usize>,
}

impl BlockNavigator {
    /// Create a new block navigator.
    pub fn new() -> Self {
        Self {
            selected_block_index: None,
        }
    }

    /// Select the previous block.
    pub fn select_prev(&mut self, block_count: usize) {
        if block_count == 0 {
            return;
        }
        match self.selected_block_index {
            Some(idx) if idx > 0 => self.selected_block_index = Some(idx - 1),
            None => self.selected_block_index = Some(block_count - 1),
            _ => {}
        }
    }

    /// Select the next block.
    pub fn select_next(&mut self, block_count: usize) {
        if block_count == 0 {
            return;
        }
        match self.selected_block_index {
            Some(idx) if idx < block_count - 1 => self.selected_block_index = Some(idx + 1),
            _ => {}
        }
    }

    /// Clear selection.
    pub fn deselect(&mut self) {
        self.selected_block_index = None;
    }

    /// Get the currently selected block.
    pub fn selected_block<'a>(&self, manager: &'a BlockManager) -> Option<&'a Block> {
        self.selected_block_index
            .and_then(|idx| manager.blocks.get(idx))
    }

    /// Toggle collapse/expand on the selected block.
    pub fn toggle_collapse(&self, manager: &mut BlockManager) {
        if let Some(idx) = self.selected_block_index {
            if let Some(block) = manager.blocks.get_mut(idx) {
                block.is_collapsed = !block.is_collapsed;
            }
        }
    }
}

impl Default for BlockNavigator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use walk_terminal::terminal::SemanticEvent;

    fn make_manager_with_blocks(n: usize) -> BlockManager {
        let mut mgr = BlockManager::new();
        for i in 0..n {
            let base = i * 4;
            mgr.handle_event(&SemanticEvent::PromptStart { line: base });
            mgr.handle_event(&SemanticEvent::CommandStart { line: base + 1 });
            mgr.handle_event(&SemanticEvent::OutputStart { line: base + 2 });
            mgr.handle_event(&SemanticEvent::CommandEnd {
                line: base + 3,
                exit_code: Some(0),
            });
        }
        mgr
    }

    #[test]
    fn test_select_prev() {
        let mgr = make_manager_with_blocks(5);
        let mut nav = BlockNavigator::new();

        nav.select_prev(mgr.len()); // selects last (4)
        assert_eq!(nav.selected_block_index, Some(4));

        nav.select_prev(mgr.len()); // selects 3
        assert_eq!(nav.selected_block_index, Some(3));

        nav.select_prev(mgr.len()); // selects 2
        nav.select_prev(mgr.len()); // selects 1
        nav.select_prev(mgr.len()); // selects 0
        assert_eq!(nav.selected_block_index, Some(0));

        nav.select_prev(mgr.len()); // stays at 0
        assert_eq!(nav.selected_block_index, Some(0));
    }

    #[test]
    fn test_select_next() {
        let mgr = make_manager_with_blocks(3);
        let mut nav = BlockNavigator::new();
        nav.selected_block_index = Some(0);

        nav.select_next(mgr.len());
        assert_eq!(nav.selected_block_index, Some(1));

        nav.select_next(mgr.len());
        assert_eq!(nav.selected_block_index, Some(2));

        nav.select_next(mgr.len()); // stays at 2
        assert_eq!(nav.selected_block_index, Some(2));
    }

    #[test]
    fn test_toggle_collapse() {
        let mut mgr = make_manager_with_blocks(1);
        let nav = BlockNavigator {
            selected_block_index: Some(0),
        };

        assert!(!mgr.blocks[0].is_collapsed);
        nav.toggle_collapse(&mut mgr);
        assert!(mgr.blocks[0].is_collapsed);
        nav.toggle_collapse(&mut mgr);
        assert!(!mgr.blocks[0].is_collapsed);
    }
}
