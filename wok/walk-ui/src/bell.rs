//! Terminal bell handling: visual or audible feedback for BEL character.

use std::time::Instant;

/// Bell style configuration.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BellStyle {
    /// Visual bell (flash screen).
    Visual,
    /// Audible bell (system sound).
    Audible,
    /// No bell.
    None,
}

/// Manages bell events.
pub struct BellHandler {
    /// Configured bell style.
    pub style: BellStyle,
    /// When the last visual bell started (for flash duration).
    visual_bell_start: Option<Instant>,
}

impl BellHandler {
    /// Create a new bell handler.
    pub fn new(style: BellStyle) -> Self {
        Self {
            style,
            visual_bell_start: None,
        }
    }

    /// Trigger the bell.
    pub fn ring(&mut self) {
        match self.style {
            BellStyle::Visual => {
                self.visual_bell_start = Some(Instant::now());
            }
            BellStyle::Audible => {
                // Platform-specific audio handled by the renderer
            }
            BellStyle::None => {}
        }
    }

    /// Check if the visual bell flash is still active (100ms duration).
    pub fn is_visual_bell_active(&self) -> bool {
        self.visual_bell_start
            .map(|start| start.elapsed().as_millis() < 100)
            .unwrap_or(false)
    }

    /// Clear the visual bell state.
    pub fn clear_visual_bell(&mut self) {
        self.visual_bell_start = None;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bell_none_does_nothing() {
        let mut bell = BellHandler::new(BellStyle::None);
        bell.ring();
        assert!(!bell.is_visual_bell_active());
    }

    #[test]
    fn test_visual_bell_is_active() {
        let mut bell = BellHandler::new(BellStyle::Visual);
        bell.ring();
        assert!(bell.is_visual_bell_active());
    }
}
