//! Instant replay snapshot storage for terminal panes.

use std::collections::VecDeque;
use std::time::{Duration, Instant};

use crate::state::{CellRenderData, TerminalState};

/// One captured terminal replay snapshot.
#[derive(Debug, Clone)]
pub struct ReplaySnapshot {
    /// Capture timestamp.
    pub timestamp: Instant,
    /// Absolute row index for the first captured row.
    pub row_start: usize,
    /// Captured rows and columns of rendered terminal cells.
    pub rows: Vec<Vec<CellRenderData>>,
    /// Offset into `rows` where the visible viewport starts.
    pub viewport_row_offset: usize,
    /// Number of visible rows in the viewport at capture time.
    pub viewport_rows: usize,
    /// Cursor absolute row at capture time.
    pub cursor_row: usize,
    /// Cursor column at capture time.
    pub cursor_col: usize,
    /// Viewport scrollback offset.
    pub viewport_offset: usize,
    /// Block count when captured.
    pub block_count: usize,
    /// Whether this snapshot corresponds to a block completion marker.
    pub block_marker: bool,
}

impl ReplaySnapshot {
    /// Return absolute row index at the top of the captured viewport.
    pub fn visible_start_row(&self) -> usize {
        self.row_start + self.viewport_row_offset
    }

    /// Return visible viewport rows for this snapshot.
    pub fn visible_rows(&self) -> &[Vec<CellRenderData>] {
        let start = self.viewport_row_offset.min(self.rows.len());
        let end = (start + self.viewport_rows).min(self.rows.len());
        &self.rows[start..end]
    }
}

/// Result metadata from one replay capture attempt.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ReplayCaptureResult {
    /// Whether a new snapshot was captured.
    pub captured: bool,
    /// Whether the oldest snapshot was dropped to enforce memory bounds.
    pub dropped_oldest: bool,
}

/// Per-pane replay history.
#[derive(Debug, Clone)]
pub struct ReplayStore {
    /// Stored snapshots in chronological order.
    pub snapshots: VecDeque<ReplaySnapshot>,
    /// Maximum number of snapshots retained.
    pub max_snapshots: usize,
    /// Snapshot capture interval.
    pub interval: Duration,
    last_capture_at: Option<Instant>,
}

impl ReplayStore {
    /// Create a replay store with explicit bounds and interval.
    pub fn new(max_snapshots: usize, interval: Duration) -> Self {
        Self {
            snapshots: VecDeque::new(),
            max_snapshots: max_snapshots.max(1),
            interval,
            last_capture_at: None,
        }
    }

    /// Capture a new snapshot if due or when forced.
    pub fn capture_snapshot(
        &mut self,
        state: &TerminalState,
        block_count: usize,
        margin_rows: usize,
        block_marker: bool,
        force: bool,
    ) -> ReplayCaptureResult {
        let now = Instant::now();
        if !force
            && self
                .last_capture_at
                .is_some_and(|last| now.saturating_duration_since(last) < self.interval)
        {
            return ReplayCaptureResult {
                captured: false,
                dropped_oldest: false,
            };
        }

        let snapshot = snapshot_from_state(state, now, block_count, margin_rows, block_marker);
        self.snapshots.push_back(snapshot);
        self.last_capture_at = Some(now);

        let mut dropped_oldest = false;
        while self.snapshots.len() > self.max_snapshots {
            self.snapshots.pop_front();
            dropped_oldest = true;
        }

        ReplayCaptureResult {
            captured: true,
            dropped_oldest,
        }
    }

    /// Return the number of snapshots currently retained.
    pub fn len(&self) -> usize {
        self.snapshots.len()
    }

    /// Return whether no snapshots are currently retained.
    pub fn is_empty(&self) -> bool {
        self.snapshots.is_empty()
    }

    /// Return one snapshot by chronological index.
    pub fn snapshot(&self, index: usize) -> Option<&ReplaySnapshot> {
        self.snapshots.get(index)
    }

    /// Return the newest snapshot index when available.
    pub fn newest_index(&self) -> Option<usize> {
        self.snapshots.len().checked_sub(1)
    }

    /// Return all marker snapshot indices.
    pub fn marker_indices(&self) -> Vec<usize> {
        self.snapshots
            .iter()
            .enumerate()
            .filter_map(|(index, snapshot)| snapshot.block_marker.then_some(index))
            .collect()
    }

    /// Return the previous marker index before the current snapshot.
    pub fn previous_marker(&self, current_index: usize) -> Option<usize> {
        self.marker_indices()
            .into_iter()
            .rev()
            .find(|index| *index < current_index)
    }

    /// Return the next marker index after the current snapshot.
    pub fn next_marker(&self, current_index: usize) -> Option<usize> {
        self.marker_indices()
            .into_iter()
            .find(|index| *index > current_index)
    }
}

impl Default for ReplayStore {
    fn default() -> Self {
        Self::new(300, Duration::from_secs(2))
    }
}

fn snapshot_from_state(
    state: &TerminalState,
    timestamp: Instant,
    block_count: usize,
    margin_rows: usize,
    block_marker: bool,
) -> ReplaySnapshot {
    let visible_start_row = state.visible_start_row();
    let viewport_rows = state.screen_lines();
    let total_rows = state.total_rows();
    let columns = state.columns();
    let row_start = visible_start_row.saturating_sub(margin_rows);
    let row_end = (visible_start_row + viewport_rows + margin_rows).min(total_rows);

    let rows = (row_start..row_end)
        .map(|absolute_row| {
            (0..columns)
                .map(|column| state.cell_at_absolute(absolute_row, column))
                .collect::<Vec<_>>()
        })
        .collect::<Vec<_>>();

    ReplaySnapshot {
        timestamp,
        row_start,
        rows,
        viewport_row_offset: visible_start_row.saturating_sub(row_start),
        viewport_rows,
        cursor_row: state.absolute_cursor_row(),
        cursor_col: state.cursor_position().0,
        viewport_offset: state.display_offset(),
        block_count,
        block_marker,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_replay_store_discards_oldest_when_full() {
        let mut store = ReplayStore::new(2, Duration::from_secs(0));
        let mut state = TerminalState::new(80, 24, 1_000);
        state.process_bytes(b"hello\r\nworld");

        let first = store.capture_snapshot(&state, 0, 5, false, true);
        assert!(first.captured);
        assert!(!first.dropped_oldest);

        let second = store.capture_snapshot(&state, 1, 5, true, true);
        assert!(second.captured);
        assert!(!second.dropped_oldest);

        let third = store.capture_snapshot(&state, 2, 5, false, true);
        assert!(third.captured);
        assert!(third.dropped_oldest);
        assert_eq!(store.len(), 2);
    }

    #[test]
    fn test_marker_navigation_finds_previous_and_next() {
        let mut store = ReplayStore::new(8, Duration::from_secs(0));
        let state = TerminalState::new(80, 24, 1_000);

        for marker in [false, true, false, true] {
            let _ = store.capture_snapshot(&state, 0, 5, marker, true);
        }

        assert_eq!(store.previous_marker(3), Some(1));
        assert_eq!(store.next_marker(1), Some(3));
        assert_eq!(store.next_marker(3), None);
    }
}

