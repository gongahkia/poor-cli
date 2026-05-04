//! Event loop: runs the winit event loop and dispatches events to the AppHandler.

use std::sync::Arc;
use std::time::{Duration, Instant};

use tracing::{debug, info, warn};
use winit::application::ApplicationHandler;
use winit::event::{StartCause, WindowEvent};
use winit::event_loop::{ActiveEventLoop, EventLoop, EventLoopProxy};
use winit::window::WindowId;

use crate::frame_clock::FrameClock;
use crate::handler::{AppHandler, AppMenuAction};
use crate::input::{translate_key_event, MouseEvent};
use crate::window::{PlatformError, WindowConfig, WokWindow};

const IDLE_BACKOFF_TICKS: u32 = 8;
const IDLE_FRAME_INTERVAL: Duration = Duration::from_millis(100);

#[derive(Clone, Copy)]
enum WokUserEvent {
    RuntimeWake,
}

/// Thread-safe handle that wakes the GUI runtime from background work.
#[derive(Clone)]
pub struct RuntimeWaker {
    proxy: EventLoopProxy<WokUserEvent>,
}

impl RuntimeWaker {
    fn new(proxy: EventLoopProxy<WokUserEvent>) -> Self {
        Self { proxy }
    }

    /// Wake the event loop as soon as possible.
    pub fn wake(&self) {
        let _ = self.proxy.send_event(WokUserEvent::RuntimeWake);
    }

    /// Build a callback suitable for PTY and background I/O threads.
    pub fn wake_callback(&self) -> Arc<dyn Fn() + Send + Sync + 'static> {
        let waker = self.clone();
        Arc::new(move || waker.wake())
    }
}

/// Runs the event loop with the given app handler.
///
/// # Errors
///
/// Returns [`PlatformError`] if the event loop fails to start.
pub fn run_event_loop<H: AppHandler + 'static>(
    config: WindowConfig,
    handler: H,
) -> Result<(), PlatformError> {
    let event_loop = EventLoop::<WokUserEvent>::with_user_event()
        .build()
        .map_err(|e| PlatformError::EventLoopCreation(e.to_string()))?;

    event_loop.set_control_flow(winit::event_loop::ControlFlow::Wait);
    let runtime_waker = RuntimeWaker::new(event_loop.create_proxy());
    let mut handler = handler;
    handler.on_runtime_waker(runtime_waker);

    let mut app = WinitApp {
        config,
        window: None,
        handler,
        current_modifiers: winit::event::Modifiers::default(),
        cursor_position: None,
        frame_clock: FrameClock::new(60),
        idle_ticks: 0,
        initialized: false,
        #[cfg(target_os = "macos")]
        mac_menu: None,
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
    idle_ticks: u32,
    initialized: bool,
    #[cfg(target_os = "macos")]
    mac_menu: Option<muda::Menu>,
}

impl<H: AppHandler> WinitApp<H> {
    fn note_user_activity(&mut self) {
        self.idle_ticks = 0;
        if let Some(win) = &self.window {
            win.window.request_redraw();
        }
    }

    fn pump_handler_tick(&mut self, event_loop: &ActiveEventLoop) {
        let should_redraw = self.handler.on_frame_tick();
        if self.handler.should_exit() {
            event_loop.exit();
            return;
        }
        if should_redraw {
            self.idle_ticks = 0;
            if let Some(win) = &self.window {
                win.window.request_redraw();
            }
        } else {
            self.idle_ticks = self.idle_ticks.saturating_add(1);
        }
    }
}

impl<H: AppHandler> ApplicationHandler<WokUserEvent> for WinitApp<H> {
    fn resumed(&mut self, event_loop: &ActiveEventLoop) {
        if self.window.is_some() {
            return;
        }

        let attrs = WokWindow::default_attributes(&self.config);
        match event_loop.create_window(attrs) {
            Ok(window) => {
                info!("window created successfully");
                #[cfg(target_os = "macos")]
                if self.mac_menu.is_none() {
                    match create_macos_menu() {
                        Ok(menu) => {
                            menu.init_for_nsapp();
                            self.mac_menu = Some(menu);
                        }
                        Err(error) => warn!("failed to initialize macOS app menu: {error}"),
                    }
                }
                let wok_window = WokWindow::from_winit(window);
                if let Some(target_fps) = display_target_fps(&wok_window.window) {
                    self.frame_clock.set_target_fps(target_fps);
                    info!(target_fps, "frame clock matched display refresh");
                }
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

    fn user_event(&mut self, event_loop: &ActiveEventLoop, event: WokUserEvent) {
        match event {
            WokUserEvent::RuntimeWake => {
                self.idle_ticks = 0;
                if self.initialized {
                    self.pump_handler_tick(event_loop);
                }
            }
        }
    }

    fn about_to_wait(&mut self, event_loop: &ActiveEventLoop) {
        if !self.initialized {
            event_loop.set_control_flow(winit::event_loop::ControlFlow::Wait);
            return;
        }

        #[cfg(target_os = "macos")]
        self.drain_macos_menu_events(event_loop);

        if self.frame_clock.should_render() {
            self.pump_handler_tick(event_loop);
        }

        let next_frame_delay = if self.idle_ticks >= IDLE_BACKOFF_TICKS {
            IDLE_FRAME_INTERVAL
        } else {
            self.frame_clock.time_until_next_frame()
        };
        let next_frame_at = Instant::now() + next_frame_delay;
        event_loop.set_control_flow(winit::event_loop::ControlFlow::WaitUntil(next_frame_at));
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
                self.idle_ticks = 0;
            }
            WindowEvent::Resized(size) => {
                debug!(?size, "window resized");
                if let Some(win) = &mut self.window {
                    win.size = size;
                }
                self.handler.on_resize(size);
                self.note_user_activity();
            }
            WindowEvent::Focused(focused) => {
                debug!(focused, "focus changed");
                if let Some(win) = &mut self.window {
                    win.is_focused = focused;
                }
                self.handler.on_focus_change(focused);
                self.note_user_activity();
            }
            WindowEvent::ScaleFactorChanged { scale_factor, .. } => {
                debug!(scale_factor, "scale factor changed");
                if let Some(win) = &mut self.window {
                    win.scale_factor = scale_factor;
                    win.size = win.window.inner_size();
                    self.handler.on_scale_factor_changed(scale_factor, win.size);
                }
                self.note_user_activity();
            }
            WindowEvent::ModifiersChanged(modifiers) => {
                self.current_modifiers = modifiers;
            }
            WindowEvent::KeyboardInput { event, .. } => {
                if let Some(input_event) =
                    translate_key_event(&event, &self.current_modifiers.state())
                {
                    self.handler.on_key_event(input_event);
                    self.note_user_activity();
                }
            }
            WindowEvent::CursorMoved { position, .. } => {
                self.cursor_position = Some((position.x, position.y));
                let modifiers = crate::input::Modifiers {
                    ctrl: self.current_modifiers.state().control_key(),
                    alt: self.current_modifiers.state().alt_key(),
                    shift: self.current_modifiers.state().shift_key(),
                    meta: self.current_modifiers.state().super_key(),
                };
                self.handler.on_mouse_event(MouseEvent::Move {
                    x: position.x,
                    y: position.y,
                    modifiers,
                });
                self.note_user_activity();
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
                        self.note_user_activity();
                    }
                    winit::event::ElementState::Released => {
                        self.handler.on_mouse_event(MouseEvent::Release {
                            button,
                            x,
                            y,
                            modifiers,
                        });
                        self.note_user_activity();
                    }
                }
            }
            WindowEvent::MouseWheel { delta, .. } => {
                let (x, y) = self.cursor_position.unwrap_or((0.0, 0.0));
                let (dx, dy, is_pixel_delta) = match delta {
                    winit::event::MouseScrollDelta::LineDelta(x, y) => {
                        (f64::from(x), f64::from(y), false)
                    }
                    winit::event::MouseScrollDelta::PixelDelta(pos) => (pos.x, pos.y, true),
                };
                let modifiers = crate::input::Modifiers {
                    ctrl: self.current_modifiers.state().control_key(),
                    alt: self.current_modifiers.state().alt_key(),
                    shift: self.current_modifiers.state().shift_key(),
                    meta: self.current_modifiers.state().super_key(),
                };
                self.handler.on_mouse_event(MouseEvent::Scroll {
                    x,
                    y,
                    delta_x: dx,
                    delta_y: dy,
                    is_pixel_delta,
                    modifiers,
                });
                self.note_user_activity();
            }
            WindowEvent::DroppedFile(path) => {
                self.handler.on_file_drop(path);
                self.note_user_activity();
            }
            WindowEvent::RedrawRequested => {
                self.handler.on_redraw();
            }
            _ => {}
        }
    }
}

fn display_target_fps(window: &winit::window::Window) -> Option<u32> {
    let refresh_millihertz = window
        .current_monitor()?
        .video_modes()
        .map(|mode| mode.refresh_rate_millihertz())
        .max()?;
    let refresh_hz = refresh_millihertz as f64 / 1000.0;
    if refresh_hz <= 0.0 {
        return None;
    }
    Some((refresh_hz.round() as u32).clamp(60, 144))
}

#[cfg(target_os = "macos")]
impl<H: AppHandler> WinitApp<H> {
    fn drain_macos_menu_events(&mut self, event_loop: &ActiveEventLoop) {
        while let Ok(event) = muda::MenuEvent::receiver().try_recv() {
            let Some(action) = mac_menu_action(event.id.as_ref()) else {
                continue;
            };
            if self.handler.on_menu_action(action) {
                event_loop.exit();
                return;
            }
            self.note_user_activity();
        }
    }
}

#[cfg(target_os = "macos")]
const MENU_SETTINGS: &str = "wok.menu.settings";
#[cfg(target_os = "macos")]
const MENU_RELOAD_CONFIG: &str = "wok.menu.reload_config";
#[cfg(target_os = "macos")]
const MENU_COMMAND_PALETTE: &str = "wok.menu.command_palette";
#[cfg(target_os = "macos")]
const MENU_NEW_TAB: &str = "wok.menu.new_tab";
#[cfg(target_os = "macos")]
const MENU_CLOSE_TAB: &str = "wok.menu.close_tab";
#[cfg(target_os = "macos")]
const MENU_COPY: &str = "wok.menu.copy";
#[cfg(target_os = "macos")]
const MENU_PASTE: &str = "wok.menu.paste";
#[cfg(target_os = "macos")]
const MENU_SELECT_ALL: &str = "wok.menu.select_all";
#[cfg(target_os = "macos")]
const MENU_ZOOM_IN: &str = "wok.menu.zoom_in";
#[cfg(target_os = "macos")]
const MENU_ZOOM_OUT: &str = "wok.menu.zoom_out";
#[cfg(target_os = "macos")]
const MENU_ZOOM_RESET: &str = "wok.menu.zoom_reset";
#[cfg(target_os = "macos")]
const MENU_TOGGLE_INPUT_POSITION: &str = "wok.menu.toggle_input_position";
#[cfg(target_os = "macos")]
const MENU_NEXT_TAB: &str = "wok.menu.next_tab";
#[cfg(target_os = "macos")]
const MENU_PREV_TAB: &str = "wok.menu.prev_tab";
#[cfg(target_os = "macos")]
const MENU_QUIT: &str = "wok.menu.quit";

#[cfg(target_os = "macos")]
fn mac_menu_action(id: &str) -> Option<AppMenuAction> {
    match id {
        MENU_SETTINGS => Some(AppMenuAction::OpenSettings),
        MENU_RELOAD_CONFIG => Some(AppMenuAction::ReloadConfiguration),
        MENU_COMMAND_PALETTE => Some(AppMenuAction::OpenCommandPalette),
        MENU_NEW_TAB => Some(AppMenuAction::NewTab),
        MENU_CLOSE_TAB => Some(AppMenuAction::CloseTab),
        MENU_COPY => Some(AppMenuAction::Copy),
        MENU_PASTE => Some(AppMenuAction::Paste),
        MENU_SELECT_ALL => Some(AppMenuAction::SelectAll),
        MENU_ZOOM_IN => Some(AppMenuAction::ZoomIn),
        MENU_ZOOM_OUT => Some(AppMenuAction::ZoomOut),
        MENU_ZOOM_RESET => Some(AppMenuAction::ZoomReset),
        MENU_TOGGLE_INPUT_POSITION => Some(AppMenuAction::ToggleInputPosition),
        MENU_NEXT_TAB => Some(AppMenuAction::NextTab),
        MENU_PREV_TAB => Some(AppMenuAction::PrevTab),
        MENU_QUIT => Some(AppMenuAction::Quit),
        _ => None,
    }
}

#[cfg(target_os = "macos")]
fn create_macos_menu() -> muda::Result<muda::Menu> {
    use muda::{accelerator::Accelerator, Menu, MenuItem, PredefinedMenuItem, Submenu};

    fn accel(value: &str) -> Option<Accelerator> {
        value.parse().ok()
    }

    let settings = MenuItem::with_id(MENU_SETTINGS, "Settings...", true, accel("super+Comma"));
    let reload_config = MenuItem::with_id(
        MENU_RELOAD_CONFIG,
        "Reload Configuration",
        true,
        accel("super+shift+Comma"),
    );
    let quit = MenuItem::with_id(MENU_QUIT, "Quit Wok", true, accel("super+KeyQ"));
    let app_menu = Submenu::with_items(
        "Wok",
        true,
        &[
            &PredefinedMenuItem::about(Some("About Wok"), None),
            &PredefinedMenuItem::separator(),
            &settings,
            &reload_config,
            &PredefinedMenuItem::separator(),
            &PredefinedMenuItem::services(Some("Services")),
            &PredefinedMenuItem::separator(),
            &PredefinedMenuItem::hide(Some("Hide Wok")),
            &PredefinedMenuItem::hide_others(Some("Hide Others")),
            &PredefinedMenuItem::show_all(Some("Show All")),
            &PredefinedMenuItem::separator(),
            &quit,
        ],
    )?;

    let new_tab = MenuItem::with_id(MENU_NEW_TAB, "New Tab", true, accel("super+KeyT"));
    let close_tab = MenuItem::with_id(MENU_CLOSE_TAB, "Close Tab", true, accel("super+KeyW"));
    let file_menu = Submenu::with_items("File", true, &[&new_tab, &close_tab])?;

    let copy = MenuItem::with_id(MENU_COPY, "Copy", true, accel("super+KeyC"));
    let paste = MenuItem::with_id(MENU_PASTE, "Paste", true, accel("super+KeyV"));
    let select_all = MenuItem::with_id(MENU_SELECT_ALL, "Select All", true, accel("super+KeyA"));
    let edit_menu = Submenu::with_items(
        "Edit",
        true,
        &[&copy, &paste, &PredefinedMenuItem::separator(), &select_all],
    )?;

    let command_palette = MenuItem::with_id(
        MENU_COMMAND_PALETTE,
        "Command Palette...",
        true,
        accel("super+shift+KeyP"),
    );
    let zoom_in = MenuItem::with_id(MENU_ZOOM_IN, "Zoom In", true, accel("super+Equal"));
    let zoom_out = MenuItem::with_id(MENU_ZOOM_OUT, "Zoom Out", true, accel("super+Minus"));
    let zoom_reset = MenuItem::with_id(MENU_ZOOM_RESET, "Actual Size", true, accel("super+Digit0"));
    let toggle_input_position = MenuItem::with_id(
        MENU_TOGGLE_INPUT_POSITION,
        "Toggle Input Position",
        true,
        None,
    );
    let view_menu = Submenu::with_items(
        "View",
        true,
        &[
            &command_palette,
            &PredefinedMenuItem::separator(),
            &zoom_in,
            &zoom_out,
            &zoom_reset,
            &PredefinedMenuItem::separator(),
            &toggle_input_position,
        ],
    )?;

    let next_tab = MenuItem::with_id(
        MENU_NEXT_TAB,
        "Next Tab",
        true,
        accel("super+shift+BracketRight"),
    );
    let prev_tab = MenuItem::with_id(
        MENU_PREV_TAB,
        "Previous Tab",
        true,
        accel("super+shift+BracketLeft"),
    );
    let window_menu = Submenu::with_items(
        "Window",
        true,
        &[
            &PredefinedMenuItem::minimize(Some("Minimize")),
            &PredefinedMenuItem::fullscreen(Some("Enter Full Screen")),
            &PredefinedMenuItem::separator(),
            &next_tab,
            &prev_tab,
            &PredefinedMenuItem::separator(),
            &PredefinedMenuItem::bring_all_to_front(Some("Bring All to Front")),
        ],
    )?;

    Menu::with_items(&[&app_menu, &file_menu, &edit_menu, &view_menu, &window_menu])
}
