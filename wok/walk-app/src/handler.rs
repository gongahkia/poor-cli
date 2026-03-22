//! Application handler trait for dispatching window events.

use winit::dpi::PhysicalSize;

use crate::input::{InputEvent, MouseEvent};

/// Trait for handling application events dispatched by the event loop.
///
/// All methods have default no-op implementations so handlers can
/// selectively override only the events they care about.
pub trait AppHandler {
    /// Called when the window should be redrawn.
    fn on_redraw(&mut self) {}

    /// Called when the window is resized.
    fn on_resize(&mut self, _new_size: PhysicalSize<u32>) {}

    /// Called when a keyboard event is received.
    fn on_key_event(&mut self, _event: InputEvent) {}

    /// Called when a mouse event is received.
    fn on_mouse_event(&mut self, _event: MouseEvent) {}

    /// Called when the window gains or loses focus.
    fn on_focus_change(&mut self, _focused: bool) {}

    /// Called when the window close is requested.
    fn on_close_requested(&mut self) {}
}
