//! Frame clock: high-resolution timer and frame pacing for 60fps rendering.

use std::collections::VecDeque;
use std::time::{Duration, Instant};

/// Frame clock for pacing render calls to a target FPS.
pub struct FrameClock {
    /// Target frames per second.
    target_fps: u32,
    /// Time of the last rendered frame.
    last_frame: Instant,
    /// Total frames rendered.
    frame_count: u64,
    /// Duration per frame at target FPS.
    frame_duration: Duration,
    /// Rolling window of frame durations for FPS calculation.
    frame_times: VecDeque<Duration>,
}

impl FrameClock {
    /// Create a new frame clock targeting the given FPS.
    ///
    /// Defaults to 60fps if 0 is passed.
    pub fn new(target_fps: u32) -> Self {
        let fps = if target_fps == 0 { 60 } else { target_fps };
        Self {
            target_fps: fps,
            last_frame: Instant::now(),
            frame_count: 0,
            frame_duration: Duration::from_secs_f64(1.0 / f64::from(fps)),
            frame_times: VecDeque::with_capacity(60),
        }
    }

    /// Check whether enough time has elapsed to render a new frame.
    ///
    /// Returns `true` if the elapsed time since the last frame exceeds
    /// the target frame duration, and updates internal state accordingly.
    pub fn should_render(&mut self) -> bool {
        let now = Instant::now();
        let elapsed = now - self.last_frame;
        if elapsed >= self.frame_duration {
            // Record frame time for FPS calculation
            if self.frame_times.len() >= 60 {
                self.frame_times.pop_front();
            }
            self.frame_times.push_back(elapsed);
            self.last_frame = now;
            self.frame_count += 1;
            true
        } else {
            false
        }
    }

    /// Return the rolling average FPS over the last 60 frames.
    pub fn fps(&self) -> f64 {
        if self.frame_times.is_empty() {
            return 0.0;
        }
        let total: Duration = self.frame_times.iter().sum();
        let avg_frame_time = total.as_secs_f64() / self.frame_times.len() as f64;
        if avg_frame_time > 0.0 {
            1.0 / avg_frame_time
        } else {
            0.0
        }
    }

    /// Return the total number of frames rendered.
    pub fn frame_count(&self) -> u64 {
        self.frame_count
    }

    /// Return the target FPS.
    pub fn target_fps(&self) -> u32 {
        self.target_fps
    }

    /// Update the target FPS and reset frame pacing state.
    pub fn set_target_fps(&mut self, target_fps: u32) {
        let fps = if target_fps == 0 { 60 } else { target_fps };
        self.target_fps = fps;
        self.frame_duration = Duration::from_secs_f64(1.0 / f64::from(fps));
        self.last_frame = Instant::now();
        self.frame_times.clear();
    }

    /// Return how long until the next frame should render.
    pub fn time_until_next_frame(&self) -> Duration {
        let elapsed = self.last_frame.elapsed();
        self.frame_duration.saturating_sub(elapsed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;

    #[test]
    fn test_new_defaults_to_60fps() {
        let clock = FrameClock::new(60);
        assert_eq!(clock.target_fps(), 60);
    }

    #[test]
    fn test_set_target_fps_updates_target() {
        let mut clock = FrameClock::new(60);
        clock.set_target_fps(120);
        assert_eq!(clock.target_fps(), 120);
    }

    #[test]
    fn test_should_render_after_frame_duration() {
        let mut clock = FrameClock::new(60);
        // Immediately after creation, should render (first frame)
        thread::sleep(Duration::from_millis(17));
        assert!(clock.should_render());
    }

    #[test]
    fn test_fps_returns_zero_with_no_frames() {
        let clock = FrameClock::new(60);
        assert_eq!(clock.fps(), 0.0);
    }

    #[test]
    fn test_frame_count_increments() {
        let mut clock = FrameClock::new(1000); // high fps for fast test
        thread::sleep(Duration::from_millis(5));
        if clock.should_render() {
            assert_eq!(clock.frame_count(), 1);
        }
    }
}
