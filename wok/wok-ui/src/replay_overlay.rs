//! Replay overlay timeline helpers.

/// Timeline model used by replay rendering.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReplayTimeline {
    /// Total number of snapshots in the replay store.
    pub snapshot_count: usize,
    /// Current selected snapshot index.
    pub current_index: usize,
    /// Snapshot indices that correspond to block completion markers.
    pub marker_indices: Vec<usize>,
}

impl ReplayTimeline {
    /// Build normalized [0..1] positions for marker ticks.
    pub fn marker_positions(&self) -> Vec<f32> {
        if self.snapshot_count <= 1 {
            return Vec::new();
        }
        let max = (self.snapshot_count - 1) as f32;
        self.marker_indices
            .iter()
            .map(|index| (*index as f32 / max).clamp(0.0, 1.0))
            .collect()
    }

    /// Return normalized [0..1] position for current snapshot cursor.
    pub fn cursor_position(&self) -> f32 {
        if self.snapshot_count <= 1 {
            return 1.0;
        }
        let max = (self.snapshot_count - 1) as f32;
        (self.current_index as f32 / max).clamp(0.0, 1.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_marker_positions_are_normalized() {
        let timeline = ReplayTimeline {
            snapshot_count: 5,
            current_index: 2,
            marker_indices: vec![1, 3],
        };

        assert_eq!(timeline.marker_positions(), vec![0.25, 0.75]);
        assert_eq!(timeline.cursor_position(), 0.5);
    }
}
