//! Mouse-based text selection in the terminal viewport.

use std::time::Instant;

/// A cell position in the terminal grid.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CellPos {
    /// Row (0-indexed from top).
    pub row: u16,
    /// Column (0-indexed from left).
    pub col: u16,
}

/// Selection state machine.
#[derive(Debug, Clone)]
pub enum SelectionState {
    /// No selection active.
    None,
    /// Currently dragging to select.
    Selecting {
        /// Start position.
        start: CellPos,
        /// Current end position.
        end: CellPos,
    },
    /// Selection completed.
    Selected {
        /// Start position.
        start: CellPos,
        /// End position.
        end: CellPos,
    },
}

/// Manages mouse text selection.
pub struct SelectionManager {
    /// Current selection state.
    pub state: SelectionState,
    /// Last click time and position for double/triple click detection.
    last_click: Option<(Instant, CellPos)>,
    /// Click count for multi-click detection.
    click_count: u8,
}

impl SelectionManager {
    /// Create a new selection manager.
    pub fn new() -> Self {
        Self {
            state: SelectionState::None,
            last_click: None,
            click_count: 0,
        }
    }

    /// Handle mouse press, converting pixel position to cell position.
    pub fn handle_mouse_down(&mut self, cell: CellPos) {
        let now = Instant::now();

        // Detect multi-click
        if let Some((last_time, last_pos)) = self.last_click {
            if now.duration_since(last_time).as_millis() < 300 && last_pos == cell {
                self.click_count += 1;
            } else {
                self.click_count = 1;
            }
        } else {
            self.click_count = 1;
        }

        self.last_click = Some((now, cell));

        match self.click_count {
            1 => {
                self.state = SelectionState::Selecting {
                    start: cell,
                    end: cell,
                };
            }
            2 => {
                // Double-click: word selection (handled by caller)
                self.state = SelectionState::Selected {
                    start: cell,
                    end: cell,
                };
            }
            _ => {
                // Triple-click: line selection (handled by caller)
                self.state = SelectionState::Selected {
                    start: CellPos {
                        row: cell.row,
                        col: 0,
                    },
                    end: CellPos {
                        row: cell.row,
                        col: u16::MAX,
                    },
                };
            }
        }
    }

    /// Handle mouse drag, updating the selection end point.
    pub fn handle_mouse_drag(&mut self, cell: CellPos) {
        if let SelectionState::Selecting { start, .. } = self.state {
            self.state = SelectionState::Selecting { start, end: cell };
        }
    }

    /// Handle mouse release, finalizing the selection.
    pub fn handle_mouse_up(&mut self) {
        if let SelectionState::Selecting { start, end } = self.state {
            self.state = SelectionState::Selected { start, end };
        }
    }

    /// Clear the selection.
    pub fn clear(&mut self) {
        self.state = SelectionState::None;
    }

    /// Check if there is an active selection.
    pub fn has_selection(&self) -> bool {
        matches!(self.state, SelectionState::Selected { .. })
    }

    /// Get the selection range (normalized so start <= end).
    pub fn selection_range(&self) -> Option<(CellPos, CellPos)> {
        match &self.state {
            SelectionState::Selected { start, end } | SelectionState::Selecting { start, end } => {
                let (s, e) =
                    if start.row < end.row || (start.row == end.row && start.col <= end.col) {
                        (*start, *end)
                    } else {
                        (*end, *start)
                    };
                Some((s, e))
            }
            SelectionState::None => None,
        }
    }
}

impl Default for SelectionManager {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_single_click_starts_selection() {
        let mut sm = SelectionManager::new();
        sm.handle_mouse_down(CellPos { row: 5, col: 10 });
        assert!(matches!(sm.state, SelectionState::Selecting { .. }));
    }

    #[test]
    fn test_drag_updates_end() {
        let mut sm = SelectionManager::new();
        sm.handle_mouse_down(CellPos { row: 0, col: 0 });
        sm.handle_mouse_drag(CellPos { row: 0, col: 5 });
        if let SelectionState::Selecting { end, .. } = sm.state {
            assert_eq!(end.col, 5);
        } else {
            panic!("expected Selecting state");
        }
    }

    #[test]
    fn test_mouse_up_finalizes() {
        let mut sm = SelectionManager::new();
        sm.handle_mouse_down(CellPos { row: 0, col: 0 });
        sm.handle_mouse_drag(CellPos { row: 0, col: 5 });
        sm.handle_mouse_up();
        assert!(sm.has_selection());
    }
}
