//! Input-event translation helpers for editor and PTY routing.

use wok_app::input::{InputEvent, InputEventType, KeyAction};
use wok_input::editor::EditorKey;

/// Convert one normalized input event into an editor key action.
pub(crate) fn input_event_to_editor_key(event: &InputEvent) -> Option<EditorKey> {
    match &event.action {
        KeyAction::Char(ch)
            if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta =>
        {
            Some(EditorKey::Char(*ch))
        }
        KeyAction::Char('d') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlD)
        }
        KeyAction::Char('u') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlU)
        }
        KeyAction::Char('a') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlA)
        }
        KeyAction::Char('e') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlE)
        }
        KeyAction::Char('b') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlB)
        }
        KeyAction::Char('f') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlF)
        }
        KeyAction::Char('p') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlP)
        }
        KeyAction::Char('n') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlN)
        }
        KeyAction::Char('k') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlK)
        }
        KeyAction::Char('w') if event.modifiers.ctrl && !event.modifiers.alt => {
            Some(EditorKey::CtrlW)
        }
        KeyAction::Enter if event.modifiers.shift => Some(EditorKey::ShiftEnter),
        KeyAction::Enter => Some(EditorKey::Enter),
        KeyAction::Backspace => Some(EditorKey::Backspace),
        KeyAction::Delete => Some(EditorKey::Delete),
        KeyAction::Escape => Some(EditorKey::Escape),
        KeyAction::Tab if event.modifiers.shift => Some(EditorKey::ShiftTab),
        KeyAction::Tab => Some(EditorKey::Tab),
        KeyAction::ArrowLeft if event.modifiers.ctrl => Some(EditorKey::WordLeft),
        KeyAction::ArrowLeft => Some(EditorKey::Left),
        KeyAction::ArrowRight if event.modifiers.ctrl => Some(EditorKey::WordRight),
        KeyAction::ArrowRight => Some(EditorKey::Right),
        KeyAction::ArrowUp => Some(EditorKey::Up),
        KeyAction::ArrowDown => Some(EditorKey::Down),
        KeyAction::Home => Some(EditorKey::Home),
        KeyAction::End => Some(EditorKey::End),
        _ => None,
    }
}

/// Encode one input event into PTY bytes, honoring kitty keyboard flags when set.
pub(crate) fn input_event_to_pty_bytes(
    event: &InputEvent,
    kitty_keyboard_flags: u32,
) -> Option<Vec<u8>> {
    if kitty_keyboard_flags > 0 {
        if let Some(encoded) = input_event_to_kitty_keyboard_bytes(event, kitty_keyboard_flags) {
            return Some(encoded);
        }
    }
    input_event_to_legacy_pty_bytes(event)
}

fn input_event_to_legacy_pty_bytes(event: &InputEvent) -> Option<Vec<u8>> {
    if event.event_type == InputEventType::Release {
        return None;
    }

    match &event.action {
        KeyAction::Char(c) => {
            if event.modifiers.ctrl && !event.modifiers.alt {
                let b = c.to_ascii_lowercase() as u8;
                if b.is_ascii_lowercase() {
                    Some(vec![b - b'a' + 1])
                } else {
                    Some(c.to_string().into_bytes())
                }
            } else if event.modifiers.alt && !event.modifiers.ctrl {
                let mut v = vec![0x1b];
                v.extend_from_slice(c.to_string().as_bytes());
                Some(v)
            } else if !event.modifiers.ctrl && !event.modifiers.alt && !event.modifiers.meta {
                Some(c.to_string().into_bytes())
            } else {
                None
            }
        }
        KeyAction::Enter => Some(b"\r".to_vec()),
        KeyAction::Backspace => Some(b"\x7f".to_vec()),
        KeyAction::Tab => Some(b"\t".to_vec()),
        KeyAction::Escape => Some(b"\x1b".to_vec()),
        KeyAction::ArrowUp => Some(b"\x1b[A".to_vec()),
        KeyAction::ArrowDown => Some(b"\x1b[B".to_vec()),
        KeyAction::ArrowRight => Some(b"\x1b[C".to_vec()),
        KeyAction::ArrowLeft => Some(b"\x1b[D".to_vec()),
        KeyAction::Home => Some(b"\x1b[H".to_vec()),
        KeyAction::End => Some(b"\x1b[F".to_vec()),
        KeyAction::Delete => Some(b"\x1b[3~".to_vec()),
        KeyAction::PageUp => Some(b"\x1b[5~".to_vec()),
        KeyAction::PageDown => Some(b"\x1b[6~".to_vec()),
        _ => None,
    }
}

fn input_event_to_kitty_keyboard_bytes(event: &InputEvent, flags: u32) -> Option<Vec<u8>> {
    if event.event_type == InputEventType::Release && flags & 0x2 == 0 {
        return None;
    }
    if is_modifier_only_action(&event.action) && flags & 0x8 == 0 {
        return None;
    }

    let key_code = match &event.action {
        KeyAction::Char(c) => *c as u32,
        KeyAction::Enter => 13,
        KeyAction::Tab => 9,
        KeyAction::Backspace => 127,
        KeyAction::Escape => 27,
        KeyAction::ArrowUp => 57362,
        KeyAction::ArrowDown => 57364,
        KeyAction::ArrowRight => 57363,
        KeyAction::ArrowLeft => 57361,
        KeyAction::Home => 57352,
        KeyAction::End => 57353,
        KeyAction::Delete => 57357,
        KeyAction::PageUp => 57354,
        KeyAction::PageDown => 57355,
        KeyAction::FunctionKey(index) => 57375 + u32::from(*index),
        KeyAction::ModifierShift => 57441,
        KeyAction::ModifierControl => 57442,
        KeyAction::ModifierAlt => 57443,
        KeyAction::ModifierMeta => 57444,
        _ => return None,
    };

    let mut modifier_bits = 0u32;
    if event.modifiers.shift {
        modifier_bits |= 1;
    }
    if event.modifiers.alt {
        modifier_bits |= 2;
    }
    if event.modifiers.ctrl {
        modifier_bits |= 4;
    }
    if event.modifiers.meta {
        modifier_bits |= 8;
    }
    let modifier_bits = modifier_bits + 1;
    let event_type = match event.event_type {
        InputEventType::Press => 1,
        InputEventType::Repeat => 2,
        InputEventType::Release => 3,
    };
    let key_code_repr = if flags & 0x4 != 0 {
        if let KeyAction::Char(c) = &event.action {
            let alt = c.to_lowercase().next().unwrap_or(*c) as u32;
            format!("{key_code}:{alt}")
        } else {
            key_code.to_string()
        }
    } else {
        key_code.to_string()
    };

    let payload = if flags & 0x2 != 0 {
        format!("\x1b[{key_code_repr};{modifier_bits}:{event_type}u")
    } else {
        format!("\x1b[{key_code_repr};{modifier_bits}u")
    };
    Some(payload.into_bytes())
}

fn is_modifier_only_action(action: &KeyAction) -> bool {
    matches!(
        action,
        KeyAction::ModifierShift
            | KeyAction::ModifierControl
            | KeyAction::ModifierAlt
            | KeyAction::ModifierMeta
    )
}
