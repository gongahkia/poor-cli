//! Application handler trait for dispatching window events.

use std::sync::Arc;

use winit::dpi::PhysicalSize;
use winit::window::Window;

use crate::input::{InputEvent, MouseEvent};

/// Trait for handling application events dispatched by the event loop.
///
/// All methods have default no-op implementations so handlers can
/// selectively override only the events they care about.
pub trait AppHandler {
    /// Called when the window is first created (provides `Arc<Window>` for GPU surface).
    fn on_init(&mut self, _window: Arc<Window>) {}

    /// Called on the frame clock cadence before any redraw is requested.
    ///
    /// Return `true` to request a redraw for this frame.
    fn on_frame_tick(&mut self) -> bool {
        false
    }

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
    ///
    /// Return `true` to allow the window to close, or `false` to keep it open.
    fn on_close_requested(&mut self) -> bool {
        true
    }
}
