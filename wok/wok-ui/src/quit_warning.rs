//! Quit-warning confirm modal — pure state machine.
//!
//! Owns three pieces of state:
//!   - whether a quit was requested
//!   - the number of running child processes (e.g. PTY children)
//!   - whether the user has confirmed the warning
//!
//! UI bindings call [`on_quit_request`], [`on_running_children`], [`confirm`],
//! and [`dismiss`]; the renderer reads [`should_show`]; the event loop reads
//! [`should_quit`]. No allocation, no I/O.

/// State machine modeling a quit-warning modal.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct QuitWarning {
    quit_requested: bool,
    running_children: usize,
    confirmed: bool,
}

/// Effect produced by a state-machine transition.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Effect {
    /// Quit immediately (no children, or user confirmed).
    Quit,
    /// Show the modal (quit pending, children running, not confirmed).
    Show,
    /// Hide the modal (quit cancelled or no quit pending).
    Hide,
    /// Nothing changes.
    NoChange,
}

impl QuitWarning {
    /// Construct a new, idle state machine.
    pub const fn new() -> Self {
        Self {
            quit_requested: false,
            running_children: 0,
            confirmed: false,
        }
    }

    /// Update the count of running child processes.
    pub fn on_running_children(&mut self, count: usize) -> Effect {
        let prev_show = self.should_show();
        self.running_children = count;
        // if children went to zero and a quit is pending, we can quit now.
        if self.quit_requested && self.running_children == 0 {
            return Effect::Quit;
        }
        if self.should_show() && !prev_show {
            Effect::Show
        } else if !self.should_show() && prev_show {
            Effect::Hide
        } else {
            Effect::NoChange
        }
    }

    /// User asked to quit (window close, Cmd-Q, etc).
    pub fn on_quit_request(&mut self) -> Effect {
        self.quit_requested = true;
        if self.running_children == 0 || self.confirmed {
            return Effect::Quit;
        }
        Effect::Show
    }

    /// User confirmed the warning.
    pub fn confirm(&mut self) -> Effect {
        self.confirmed = true;
        if self.quit_requested {
            Effect::Quit
        } else {
            Effect::NoChange
        }
    }

    /// User dismissed the warning (cancel quit).
    pub fn dismiss(&mut self) -> Effect {
        let was_showing = self.should_show();
        self.quit_requested = false;
        self.confirmed = false;
        if was_showing {
            Effect::Hide
        } else {
            Effect::NoChange
        }
    }

    /// `true` while the modal should be visible.
    pub const fn should_show(&self) -> bool {
        self.quit_requested && self.running_children > 0 && !self.confirmed
    }

    /// `true` once the application should actually exit.
    pub const fn should_quit(&self) -> bool {
        self.quit_requested && (self.running_children == 0 || self.confirmed)
    }

    /// Number of running children currently tracked.
    pub const fn running_children(&self) -> usize {
        self.running_children
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn quit_with_no_children_is_immediate() {
        let mut q = QuitWarning::new();
        assert_eq!(q.on_quit_request(), Effect::Quit);
        assert!(q.should_quit());
        assert!(!q.should_show());
    }

    #[test]
    fn quit_with_children_shows_modal() {
        let mut q = QuitWarning::new();
        let _ = q.on_running_children(2);
        assert_eq!(q.on_quit_request(), Effect::Show);
        assert!(q.should_show());
        assert!(!q.should_quit());
    }

    #[test]
    fn confirm_quits_when_request_pending() {
        let mut q = QuitWarning::new();
        let _ = q.on_running_children(2);
        let _ = q.on_quit_request();
        assert_eq!(q.confirm(), Effect::Quit);
        assert!(q.should_quit());
    }

    #[test]
    fn dismiss_cancels_pending_quit() {
        let mut q = QuitWarning::new();
        let _ = q.on_running_children(2);
        let _ = q.on_quit_request();
        assert_eq!(q.dismiss(), Effect::Hide);
        assert!(!q.should_show());
        assert!(!q.should_quit());
    }

    #[test]
    fn child_count_drops_to_zero_during_pending_quit_quits() {
        let mut q = QuitWarning::new();
        let _ = q.on_running_children(2);
        let _ = q.on_quit_request();
        assert_eq!(q.on_running_children(0), Effect::Quit);
    }

    #[test]
    fn confirm_alone_without_request_is_inert() {
        let mut q = QuitWarning::new();
        assert_eq!(q.confirm(), Effect::NoChange);
    }

    #[test]
    fn dismiss_when_idle_is_inert() {
        let mut q = QuitWarning::new();
        assert_eq!(q.dismiss(), Effect::NoChange);
    }

    #[test]
    fn child_changes_without_quit_intent_are_inert() {
        let mut q = QuitWarning::new();
        assert_eq!(q.on_running_children(3), Effect::NoChange);
        assert_eq!(q.on_running_children(0), Effect::NoChange);
    }
}
