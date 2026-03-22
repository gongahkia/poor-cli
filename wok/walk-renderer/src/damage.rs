//! Damage tracking: avoids re-rendering unchanged regions of the grid.

/// Tracks which rows of the terminal grid have changed and need re-rendering.
pub struct DirtyRegion {
    /// One bit per row: true = needs re-render.
    dirty_rows: Vec<bool>,
    /// Whether the entire viewport is dirty.
    full_damage: bool,
}

impl DirtyRegion {
    /// Create a new dirty region tracker for the given number of rows.
    pub fn new(rows: usize) -> Self {
        Self {
            dirty_rows: vec![true; rows], // initially all dirty
            full_damage: true,
        }
    }

    /// Mark a specific row as dirty.
    pub fn mark_row_dirty(&mut self, row: usize) {
        if row < self.dirty_rows.len() {
            self.dirty_rows[row] = true;
        }
    }

    /// Mark all rows as dirty (e.g., after scroll or resize).
    pub fn mark_fully_damaged(&mut self) {
        self.full_damage = true;
        for row in &mut self.dirty_rows {
            *row = true;
        }
    }

    /// Check if a row is dirty.
    pub fn is_row_dirty(&self, row: usize) -> bool {
        self.full_damage || self.dirty_rows.get(row).copied().unwrap_or(false)
    }

    /// Check if any damage needs rendering.
    pub fn has_damage(&self) -> bool {
        self.full_damage || self.dirty_rows.iter().any(|&d| d)
    }

    /// Clear all dirty bits after rendering.
    pub fn clear(&mut self) {
        self.full_damage = false;
        for row in &mut self.dirty_rows {
            *row = false;
        }
    }

    /// Resize the tracker for a new number of rows.
    pub fn resize(&mut self, rows: usize) {
        self.dirty_rows.resize(rows, true);
        self.mark_fully_damaged();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initial_full_damage() {
        let region = DirtyRegion::new(24);
        assert!(region.has_damage());
        assert!(region.is_row_dirty(0));
        assert!(region.is_row_dirty(23));
    }

    #[test]
    fn test_clear_and_mark() {
        let mut region = DirtyRegion::new(24);
        region.clear();
        assert!(!region.has_damage());
        assert!(!region.is_row_dirty(5));

        region.mark_row_dirty(5);
        assert!(region.has_damage());
        assert!(region.is_row_dirty(5));
        assert!(!region.is_row_dirty(6));
    }

    #[test]
    fn test_full_damage() {
        let mut region = DirtyRegion::new(24);
        region.clear();
        region.mark_fully_damaged();
        assert!(region.is_row_dirty(0));
        assert!(region.is_row_dirty(23));
    }
}
