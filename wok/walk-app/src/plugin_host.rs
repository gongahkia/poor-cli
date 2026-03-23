//! Plugin host: runtime wrapper around the Lua scripting surface.

use std::path::Path;

use serde::Serialize;
use serde_json::Value;
use tracing::warn;

use crate::app::WalkApp;
use crate::keybindings::{Action, Context, KeyCombo};
use crate::scripting::{LuaRuntime, ThemeRequest};

/// Queued side effects emitted by plugins.
#[derive(Debug, Default)]
pub struct PluginEffects {
    /// Status notifications requested by plugins.
    pub notifications: Vec<String>,
    /// Shell commands requested by plugins.
    pub exec_requests: Vec<String>,
    /// Built-in action requests requested by plugins.
    pub action_requests: Vec<String>,
    /// Theme requests requested by plugins.
    pub theme_requests: Vec<ThemeRequest>,
}

/// Thin runtime wrapper that isolates the scripting engine from app orchestration.
pub struct PluginHost {
    runtime: LuaRuntime,
}

impl PluginHost {
    /// Create and initialize the plugin host from the configured directory.
    pub fn new(config_dir: &Path) -> Option<Self> {
        let mut runtime = LuaRuntime::new().ok()?;
        if let Err(error) = runtime.init(config_dir) {
            warn!("failed to initialize Lua runtime: {error}");
            return None;
        }
        Some(Self { runtime })
    }

    /// Update the read-only config table exposed to plugins.
    pub fn set_config_values(&self, values: &Value) {
        if let Err(error) = self.runtime.set_config_values(values) {
            warn!("failed to update plugin config table: {error}");
        }
    }

    /// Apply plugin-provided keybindings to a pane-local app state.
    pub fn apply_keybindings<F>(&self, app: &mut WalkApp, mut parse_action: F)
    where
        F: FnMut(&str) -> Option<Action>,
    {
        let bindings = self.runtime.state.keybindings.lock().unwrap().clone();
        let commands = self.runtime.state.commands.lock().unwrap().clone();
        for binding in bindings {
            let Some(combo) = parse_lua_key_combo(&binding.key) else {
                continue;
            };
            let action_name = commands
                .get(&binding.action)
                .map(String::as_str)
                .unwrap_or(&binding.action);
            let Some(action) = parse_action(action_name) else {
                continue;
            };
            let Some(context) = parse_lua_context(&binding.mode) else {
                continue;
            };
            app.keybindings
                .context_bindings
                .entry(context)
                .or_default()
                .insert(combo, action);
        }
    }

    /// Resolve a named plugin command alias to a built-in action string.
    pub fn resolve_command_action(&self, name: &str) -> Option<String> {
        self.runtime.resolve_command_action(name)
    }

    /// Return the current command aliases registered by plugins.
    pub fn command_aliases(&self) -> Vec<(String, String)> {
        self.runtime.command_aliases().into_iter().collect()
    }

    /// Trigger a structured plugin hook.
    pub fn trigger_hook<T>(&self, hook: &str, payload: &T)
    where
        T: Serialize + ?Sized,
    {
        if let Err(error) = self.runtime.trigger_hook(hook, payload) {
            warn!("plugin hook '{hook}' failed: {error}");
        }
    }

    /// Update the latest runtime snapshot visible to plugin accessors.
    pub fn update_snapshot(&self, snapshot: Value) {
        self.runtime.set_runtime_snapshot(snapshot);
    }

    /// Drain queued plugin side effects.
    pub fn drain_effects(&self) -> PluginEffects {
        PluginEffects {
            notifications: self.runtime.take_notifications(),
            exec_requests: self.runtime.take_exec_requests(),
            action_requests: self.runtime.take_action_requests(),
            theme_requests: self.runtime.take_theme_requests(),
        }
    }
}

fn parse_lua_context(mode: &str) -> Option<Context> {
    match mode {
        "normal" | "terminal" => Some(Context::Terminal),
        "input" => Some(Context::InputEditor),
        "block" => Some(Context::BlockSelected),
        "search" => Some(Context::SearchActive),
        _ => None,
    }
}

fn parse_lua_key_combo(key: &str) -> Option<KeyCombo> {
    let mut modifiers = crate::input::Modifiers::default();
    let mut key_action = None;

    for part in key.split('+') {
        match part.trim().to_ascii_lowercase().as_str() {
            "ctrl" => modifiers.ctrl = true,
            "alt" => modifiers.alt = true,
            "shift" => modifiers.shift = true,
            "cmd" | "meta" => modifiers.meta = true,
            "left" => key_action = Some(crate::input::KeyAction::ArrowLeft),
            "right" => key_action = Some(crate::input::KeyAction::ArrowRight),
            "up" => key_action = Some(crate::input::KeyAction::ArrowUp),
            "down" => key_action = Some(crate::input::KeyAction::ArrowDown),
            "enter" => key_action = Some(crate::input::KeyAction::Enter),
            "tab" => key_action = Some(crate::input::KeyAction::Tab),
            "escape" | "esc" => key_action = Some(crate::input::KeyAction::Escape),
            "backspace" => key_action = Some(crate::input::KeyAction::Backspace),
            "delete" => key_action = Some(crate::input::KeyAction::Delete),
            "home" => key_action = Some(crate::input::KeyAction::Home),
            "end" => key_action = Some(crate::input::KeyAction::End),
            value if value.len() == 1 => {
                key_action = value.chars().next().map(crate::input::KeyAction::Char);
            }
            _ => {}
        }
    }

    key_action.map(|key| KeyCombo { key, modifiers })
}
