//! Input event normalization: converts raw winit key events into Walk-internal types.

use winit::event::{ElementState, MouseButton};
use winit::keyboard::{Key, ModifiersState, NamedKey};

/// Actions that can be triggered by keyboard input.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum KeyAction {
    /// A regular character was typed.
    Char(char),
    /// Enter/Return key.
    Enter,
    /// Tab key.
    Tab,
    /// Backspace key.
    Backspace,
    /// Delete key.
    Delete,
    /// Escape key.
    Escape,
    /// Up arrow.
    ArrowUp,
    /// Down arrow.
    ArrowDown,
    /// Left arrow.
    ArrowLeft,
    /// Right arrow.
    ArrowRight,
    /// Home key.
    Home,
    /// End key.
    End,
    /// Page up.
    PageUp,
    /// Page down.
    PageDown,
    /// Function key F1-F12.
    FunctionKey(u8),
    /// Shift modifier key.
    ModifierShift,
    /// Control modifier key.
    ModifierControl,
    /// Alt modifier key.
    ModifierAlt,
    /// Meta/Super modifier key.
    ModifierMeta,
    /// Copy action (Cmd+C / Ctrl+C).
    Copy,
    /// Paste action (Cmd+V / Ctrl+V).
    Paste,
    /// Cut action (Cmd+X / Ctrl+X).
    Cut,
    /// Select all (Cmd+A / Ctrl+A).
    SelectAll,
    /// Undo (Cmd+Z / Ctrl+Z).
    Undo,
    /// Redo (Cmd+Shift+Z / Ctrl+Shift+Z).
    Redo,
}

/// Modifier key state.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Hash)]
pub struct Modifiers {
    /// Control key is held.
    pub ctrl: bool,
    /// Alt/Option key is held.
    pub alt: bool,
    /// Shift key is held.
    pub shift: bool,
    /// Meta key is held (Cmd on macOS, Win on Windows).
    pub meta: bool,
}

/// A normalized input event.
#[derive(Debug, Clone)]
pub struct InputEvent {
    /// The action represented by this key press.
    pub action: KeyAction,
    /// Active modifier keys.
    pub modifiers: Modifiers,
    /// Whether this is a key repeat event.
    pub is_repeat: bool,
    /// Key event transition type.
    pub event_type: InputEventType,
}

/// Key event transition type.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InputEventType {
    /// Key press transition.
    Press,
    /// Repeated key press while held.
    Repeat,
    /// Key release transition.
    Release,
}

/// Mouse event types for the application.
#[derive(Debug, Clone)]
pub enum MouseEvent {
    /// Mouse button pressed.
    Press {
        /// The button that was pressed.
        button: MouseButton,
        /// X position in physical pixels.
        x: f64,
        /// Y position in physical pixels.
        y: f64,
        /// Active modifiers.
        modifiers: Modifiers,
    },
    /// Mouse button released.
    Release {
        /// The button that was released.
        button: MouseButton,
        /// X position in physical pixels.
        x: f64,
        /// Y position in physical pixels.
        y: f64,
    },
    /// Mouse moved.
    Move {
        /// X position in physical pixels.
        x: f64,
        /// Y position in physical pixels.
        y: f64,
    },
    /// Mouse wheel scrolled.
    Scroll {
        /// Horizontal scroll delta.
        delta_x: f64,
        /// Vertical scroll delta.
        delta_y: f64,
    },
}

/// Convert winit modifiers state to Walk's Modifiers.
fn convert_modifiers(state: &ModifiersState) -> Modifiers {
    Modifiers {
        ctrl: state.control_key(),
        alt: state.alt_key(),
        shift: state.shift_key(),
        meta: state.super_key(),
    }
}

/// Check if the platform modifier is active (Cmd on macOS, Ctrl elsewhere).
fn has_platform_modifier(mods: &Modifiers) -> bool {
    #[cfg(target_os = "macos")]
    {
        mods.meta
    }
    #[cfg(not(target_os = "macos"))]
    {
        mods.ctrl
    }
}

/// Translate a raw winit key event into a Walk `InputEvent`.
pub fn translate_key_event(
    event: &winit::event::KeyEvent,
    modifiers: &ModifiersState,
) -> Option<InputEvent> {
    let mods = convert_modifiers(modifiers);
    let is_repeat = event.repeat;
    let event_type = match (event.state, event.repeat) {
        (ElementState::Released, _) => InputEventType::Release,
        (ElementState::Pressed, true) => InputEventType::Repeat,
        (ElementState::Pressed, false) => InputEventType::Press,
    };

    // Check for platform modifier combos first
    if has_platform_modifier(&mods) && event_type != InputEventType::Release {
        let action = match &event.logical_key {
            Key::Character(c) => match c.as_str() {
                "c" => Some(KeyAction::Copy),
                "v" => Some(KeyAction::Paste),
                "x" => Some(KeyAction::Cut),
                "a" => Some(KeyAction::SelectAll),
                "z" if mods.shift => Some(KeyAction::Redo),
                "z" => Some(KeyAction::Undo),
                _ => None,
            },
            _ => None,
        };
        if let Some(action) = action {
            return Some(InputEvent {
                action,
                modifiers: mods,
                is_repeat,
                event_type,
            });
        }
    }

    let action = match &event.logical_key {
        Key::Named(named) => match named {
            NamedKey::Enter => Some(KeyAction::Enter),
            NamedKey::Tab => Some(KeyAction::Tab),
            NamedKey::Backspace => Some(KeyAction::Backspace),
            NamedKey::Delete => Some(KeyAction::Delete),
            NamedKey::Escape => Some(KeyAction::Escape),
            NamedKey::ArrowUp => Some(KeyAction::ArrowUp),
            NamedKey::ArrowDown => Some(KeyAction::ArrowDown),
            NamedKey::ArrowLeft => Some(KeyAction::ArrowLeft),
            NamedKey::ArrowRight => Some(KeyAction::ArrowRight),
            NamedKey::Home => Some(KeyAction::Home),
            NamedKey::End => Some(KeyAction::End),
            NamedKey::PageUp => Some(KeyAction::PageUp),
            NamedKey::PageDown => Some(KeyAction::PageDown),
            NamedKey::F1 => Some(KeyAction::FunctionKey(1)),
            NamedKey::F2 => Some(KeyAction::FunctionKey(2)),
            NamedKey::F3 => Some(KeyAction::FunctionKey(3)),
            NamedKey::F4 => Some(KeyAction::FunctionKey(4)),
            NamedKey::F5 => Some(KeyAction::FunctionKey(5)),
            NamedKey::F6 => Some(KeyAction::FunctionKey(6)),
            NamedKey::F7 => Some(KeyAction::FunctionKey(7)),
            NamedKey::F8 => Some(KeyAction::FunctionKey(8)),
            NamedKey::F9 => Some(KeyAction::FunctionKey(9)),
            NamedKey::F10 => Some(KeyAction::FunctionKey(10)),
            NamedKey::F11 => Some(KeyAction::FunctionKey(11)),
            NamedKey::F12 => Some(KeyAction::FunctionKey(12)),
            NamedKey::Shift => Some(KeyAction::ModifierShift),
            NamedKey::Control => Some(KeyAction::ModifierControl),
            NamedKey::Alt => Some(KeyAction::ModifierAlt),
            NamedKey::Meta | NamedKey::Super => Some(KeyAction::ModifierMeta),
            _ => None,
        },
        Key::Character(c) => {
            let ch = c.chars().next()?;
            Some(KeyAction::Char(ch))
        }
        _ => None,
    };

    action.map(|action| InputEvent {
        action,
        modifiers: mods,
        is_repeat,
        event_type,
    })
}
