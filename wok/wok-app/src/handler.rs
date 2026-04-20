//! Application handler trait for dispatching window events.

use std::sync::Arc;

use winit::dpi::PhysicalSize;
use winit::window::Window;

use crate::input::{InputEvent, MouseEvent};

/// Native application menu actions routed back into the runtime.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AppMenuAction {
    /// Open the settings file.
    OpenSettings,
    /// Reload configuration from disk.
    ReloadConfiguration,
    /// Open the command palette.
    OpenCommandPalette,
    /// Create a new tab.
    NewTab,
    /// Close the active tab.
    CloseTab,
    /// Copy selection.
    Copy,
    /// Paste clipboard contents.
    Paste,
    /// Select all visible text or editor text.
    SelectAll,
    /// Increase font size.
    ZoomIn,
    /// Decrease font size.
    ZoomOut,
    /// Reset font size.
    ZoomReset,
    /// Toggle input position.
    ToggleInputPosition,
    /// Focus next tab.
    NextTab,
    /// Focus previous tab.
    PrevTab,
    /// Quit the app.
    Quit,
}

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

    /// Called after the frame tick to determine whether the app should quit.
    fn should_exit(&mut self) -> bool {
        false
    }

    /// Called when the window should be redrawn.
    fn on_redraw(&mut self) {}

    /// Called when the window is resized.
    fn on_resize(&mut self, _new_size: PhysicalSize<u32>) {}

    /// Called when the window scale factor changes.
    fn on_scale_factor_changed(&mut self, _new_scale_factor: f64, _new_size: PhysicalSize<u32>) {}

    /// Called when a keyboard event is received.
    fn on_key_event(&mut self, _event: InputEvent) {}

    /// Called when a mouse event is received.
    fn on_mouse_event(&mut self, _event: MouseEvent) {}

    /// Called when a native app menu action is selected.
    ///
    /// Return `true` to request app exit.
    fn on_menu_action(&mut self, _action: AppMenuAction) -> bool {
        false
    }

    /// Called when the window gains or loses focus.
    fn on_focus_change(&mut self, _focused: bool) {}

    /// Called when the window close is requested.
    ///
    /// Return `true` to allow the window to close, or `false` to keep it open.
    fn on_close_requested(&mut self) -> bool {
        true
    }
}
