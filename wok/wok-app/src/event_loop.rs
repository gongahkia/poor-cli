//! Event loop: runs the winit event loop and dispatches events to the AppHandler.

use std::time::Instant;

use tracing::{debug, info, warn};
use winit::application::ApplicationHandler;
use winit::event::{StartCause, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop};
use winit::window::WindowId;

use crate::frame_clock::FrameClock;
use crate::handler::AppHandler;
use crate::input::{translate_key_event, MouseEvent};
use crate::window::{PlatformError, WokWindow, WindowConfig};

/// Runs the event loop with the given app handler.
///
/// # Errors
///
/// Returns [`PlatformError`] if the event loop fails to start.
pub fn run_event_loop<H: AppHandler + 'static>(
    config: WindowConfig,
    handler: H,
) -> Result<(), PlatformError> {
    let event_loop =
        EventLoop::new().map_err(|e| PlatformError::EventLoopCreation(e.to_string()))?;

    event_loop.set_control_flow(winit::event_loop::ControlFlow::Wait);

    let mut app = WinitApp {
        config,
        window: None,
        handler,
        current_modifiers: winit::event::Modifiers::default(),
        cursor_position: None,
        frame_clock: FrameClock::new(60),
        initialized: false,
    };

    event_loop
        .run_app(&mut app)
        .map_err(|e| PlatformError::EventLoopCreation(e.to_string()))?;

    Ok(())
}

struct WinitApp<H: AppHandler> {
    config: WindowConfig,
    window: Option<WokWindow>,
    handler: H,
    current_modifiers: winit::event::Modifiers,
    cursor_position: Option<(f64, f64)>,
    frame_clock: FrameClock,
    initialized: bool,
}

impl<H: AppHandler> ApplicationHandler for WinitApp<H> {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        if self.window.is_some() {
            return;
        }

        let attrs = WokWindow::default_attributes(&self.config);
        match event_loop.create_window(attrs) {
            Ok(window) => {
                info!("window created successfully");
                let wok_window = WokWindow::from_winit(window);
                let arc_window = wok_window.window.clone();
                self.window = Some(wok_window);
                // Notify handler with the Arc<Window> for GPU init
                self.handler.on_init(arc_window);
                self.initialized = true;
            }
            Err(e) => {
                warn!("failed to create window: {e}");
                event_loop.exit();
            }
        }
    }

    fn new_events(&mut self, _event_loop: &ActiveEventLoop, _cause: StartCause) {}

    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        if !self.initialized {
            event_loop.set_control_flow(winit::event_loop::ControlFlow::Wait);
            return;
        }

        let next_frame_at = Instant::now() + self.frame_clock.time_until_next_frame();
        event_loop.set_control_flow(winit::event_loop::ControlFlow::WaitUntil(next_frame_at));

        if self.frame_clock.should_render() && self.handler.on_frame_tick() {
            if let Some(win) = &self.window {
                win.window.request_redraw();
            }
        }
    }

    fn window_event(
        &mut self,
        event_loop: &ActiveEventLoop,
        _window_id: WindowId,
        event: WindowEvent,
    ) {
        match event {
            WindowEvent::CloseRequested => {
                info!("close requested");
                if self.handler.on_close_requested() {
                    event_loop.exit();
                } else if let Some(win) = &self.window {
                    win.window.request_redraw();
                }
            }
            WindowEvent::Resized(size) => {
                debug!(?size, "window resized");
                if let Some(win) = &mut self.window {
                    win.size = size;
                }
                self.handler.on_resize(size);
            }
            WindowEvent::Focused(focused) => {
                debug!(focused, "focus changed");
                if let Some(win) = &mut self.window {
                    win.is_focused = focused;
                }
                self.handler.on_focus_change(focused);
            }
            WindowEvent::ScaleFactorChanged { scale_factor, .. } => {
                debug!(scale_factor, "scale factor changed");
                if let Some(win) = &mut self.window {
                    win.scale_factor = scale_factor;
                    win.size = win.window.inner_size();
                    self.handler.on_scale_factor_changed(scale_factor, win.size);
                }
            }
            WindowEvent::ModifiersChanged(modifiers) => {
                self.current_modifiers = modifiers;
            }
            WindowEvent::KeyboardInput { event, .. } => {
                if let Some(input_event) =
                    translate_key_event(&event, &self.current_modifiers.state())
                {
                    self.handler.on_key_event(input_event);
                }
            }
            WindowEvent::CursorMoved { position, .. } => {
                self.cursor_position = Some((position.x, position.y));
                self.handler.on_mouse_event(MouseEvent::Move {
                    x: position.x,
                    y: position.y,
                });
            }
            WindowEvent::MouseInput { state, button, .. } => {
                let (x, y) = self.cursor_position.unwrap_or((0.0, 0.0));
                let modifiers = crate::input::Modifiers {
                    ctrl: self.current_modifiers.state().control_key(),
                    alt: self.current_modifiers.state().alt_key(),
                    shift: self.current_modifiers.state().shift_key(),
                    meta: self.current_modifiers.state().super_key(),
                };
                match state {
                    winit::event::ElementState::Pressed => {
                        self.handler.on_mouse_event(MouseEvent::Press {
                            button,
                            x,
                            y,
                            modifiers,
                        });
                    }
                    winit::event::ElementState::Released => {
                        self.handler
                            .on_mouse_event(MouseEvent::Release { button, x, y });
                    }
                }
            }
            WindowEvent::MouseWheel { delta, .. } => {
                let (dx, dy) = match delta {
                    winit::event::MouseScrollDelta::LineDelta(x, y) => (f64::from(x), f64::from(y)),
                    winit::event::MouseScrollDelta::PixelDelta(pos) => (pos.x, pos.y),
                };
                self.handler.on_mouse_event(MouseEvent::Scroll {
                    delta_x: dx,
                    delta_y: dy,
                });
            }
            WindowEvent::RedrawRequested => {
                self.handler.on_redraw();
            }
            _ => {}
        }
    }
}
