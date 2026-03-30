//! Plugin host: runtime wrapper around the Lua scripting surface.

use std::path::Path;

use serde::Serialize;
use serde_json::Value;
use tracing::warn;

use crate::app::WalkApp;
use crate::keybindings::{Action, Context, KeyCombo};
use crate::scripting::{
    LuaRuntime, QuickSelectPatternRequest, ThemeRequest, TriggerRequest, WorkflowRequest,
};

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
    /// Trigger requests requested by plugins.
    pub trigger_requests: Vec<TriggerRequest>,
    /// Quick-select pattern requests requested by plugins.
    pub quick_select_pattern_requests: Vec<QuickSelectPatternRequest>,
    /// Workflow registration requests requested by plugins.
    pub workflow_requests: Vec<WorkflowRequest>,
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
            runtime.push_notification(format!("init.lua error: {error}"));
        }
        Some(Self { runtime })
    }

    /// Update the read-only config table exposed to plugins.
    pub fn set_config_values(&self, values: &Value) {
        if let Err(error) = self.runtime.set_config_values(values) {
            warn!("failed to update plugin config table: {error}");
            self.runtime
                .push_notification(format!("plugin config sync failed: {error}"));
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
            self.runtime
                .push_notification(format!("plugin hook '{hook}' failed: {error}"));
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
            trigger_requests: self.runtime.take_trigger_requests(),
            quick_select_pattern_requests: self.runtime.take_quick_select_pattern_requests(),
            workflow_requests: self.runtime.take_workflow_requests(),
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

#[cfg(test)]
mod tests {
    use std::time::{SystemTime, UNIX_EPOCH};

    use super::*;

    #[test]
    fn test_invalid_init_lua_surfaces_notification() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("clock should be after epoch")
            .as_nanos();
        let config_dir = std::env::temp_dir().join(format!("walk-plugin-host-{unique}"));
        std::fs::create_dir_all(&config_dir).expect("config dir should be created");
        std::fs::write(config_dir.join("init.lua"), "this is not valid lua !!!")
            .expect("invalid init.lua should be written");

        let host = PluginHost::new(&config_dir).expect("plugin host should still initialize");
        let effects = host.drain_effects();

        std::fs::remove_file(config_dir.join("init.lua")).ok();
        std::fs::remove_dir_all(&config_dir).ok();

        assert_eq!(effects.exec_requests.len(), 0);
        assert_eq!(effects.action_requests.len(), 0);
        assert!(effects
            .notifications
            .iter()
            .any(|message| message.contains("init.lua error")));
    }
}
