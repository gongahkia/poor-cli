//! Plugin host: runtime wrapper around the Lua scripting surface.

use std::io::{BufRead, BufReader, Write};
use std::path::Path;
use std::process::{Child, ChildStdin, Command, Stdio};
use std::sync::{mpsc, Mutex};
use std::thread;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use tracing::warn;

use crate::app::WokApp;
use crate::keybindings::{Action, Context, KeyCombo};
use crate::scripting::{
    LuaRuntime, QuickSelectPatternRequest, SetupRequest, StatusBarRequest, ThemeRequest,
    SystemNotificationRequest, TriggerRequest, WorkflowRequest,
};

/// Queued side effects emitted by plugins.
#[derive(Debug, Default)]
pub struct PluginEffects {
    /// Status notifications requested by plugins.
    pub notifications: Vec<String>,
    /// Native desktop notifications requested by plugins.
    pub system_notifications: Vec<SystemNotificationRequest>,
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
    /// Status bar customization requests requested by plugins.
    pub status_bar_requests: Vec<StatusBarRequest>,
    /// Setup lifecycle requests requested by plugins.
    pub setup_requests: Vec<SetupRequest>,
}

/// Thin runtime wrapper that isolates the scripting engine from app orchestration.
pub struct PluginHost {
    runtime: LuaRuntime,
    external_bridge: Option<ExternalPluginBridge>,
}

impl PluginHost {
    /// Create and initialize the plugin host from the configured directory.
    pub fn new(config_dir: &Path, external_command: Option<&str>) -> Option<Self> {
        let mut runtime = LuaRuntime::new().ok()?;
        if let Err(error) = runtime.init(config_dir) {
            warn!("failed to initialize Lua runtime: {error}");
            runtime.push_notification(format!("init.lua error: {error}"));
        }
        let external_bridge = external_command
            .and_then(|command| ExternalPluginBridge::spawn(command).ok())
            .or_else(|| {
                if let Some(command) = external_command {
                    warn!("failed to initialize external plugin bridge: {command}");
                }
                None
            });
        Some(Self {
            runtime,
            external_bridge,
        })
    }

    /// Update the read-only config table exposed to plugins.
    pub fn set_config_values(&self, values: &Value) {
        if let Err(error) = self.runtime.set_config_values(values) {
            warn!("failed to update plugin config table: {error}");
            self.runtime
                .push_notification(format!("plugin config sync failed: {error}"));
        }
        if let Some(bridge) = &self.external_bridge {
            bridge.send_event("wok.config", values);
        }
    }

    /// Apply plugin-provided keybindings to a pane-local app state.
    pub fn apply_keybindings<F>(&self, app: &mut WokApp, mut parse_action: F)
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
        if let Some(bridge) = &self.external_bridge {
            bridge.send_hook(hook, payload);
        }
    }

    /// Execute due plugin timers with a per-frame callback cap.
    pub fn pump_timers(&self, max_fires_per_tick: usize) {
        if let Err(error) = self.runtime.run_due_timers(max_fires_per_tick) {
            warn!("plugin timer callback failed: {error}");
            self.runtime
                .push_notification(format!("plugin timer callback failed: {error}"));
        }
    }

    /// Return whether any listener exists for a given hook.
    pub fn has_hook_listener(&self, hook: &str) -> bool {
        self.runtime.hook_listener_count(hook) > 0 || self.external_bridge.is_some()
    }

    /// Update the latest runtime snapshot visible to plugin accessors.
    pub fn update_snapshot(&self, snapshot: &Value) {
        self.runtime.set_runtime_snapshot(snapshot.clone());
        if let Some(bridge) = &self.external_bridge {
            bridge.send_event("wok.snapshot", snapshot);
        }
    }

    /// Drain queued plugin side effects.
    pub fn drain_effects(&self) -> PluginEffects {
        let mut effects = PluginEffects {
            notifications: self.runtime.take_notifications(),
            system_notifications: self.runtime.take_system_notifications(),
            exec_requests: self.runtime.take_exec_requests(),
            action_requests: self.runtime.take_action_requests(),
            theme_requests: self.runtime.take_theme_requests(),
            trigger_requests: self.runtime.take_trigger_requests(),
            quick_select_pattern_requests: self.runtime.take_quick_select_pattern_requests(),
            workflow_requests: self.runtime.take_workflow_requests(),
            status_bar_requests: self.runtime.take_status_bar_requests(),
            setup_requests: self.runtime.take_setup_requests(),
        };
        if let Some(bridge) = &self.external_bridge {
            bridge.extend_effects(&mut effects);
        }
        effects
    }
}

struct ExternalPluginBridge {
    _child: Mutex<Child>,
    stdin: Mutex<ChildStdin>,
    rx: Mutex<mpsc::Receiver<String>>,
}

#[derive(Debug, Deserialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum ExternalPluginMessage {
    Notify { message: String },
    SystemNotify {
        title: Option<String>,
        message: String,
        subtitle: Option<String>,
    },
    Exec { command: String },
    Action { action: String },
}

impl ExternalPluginBridge {
    fn spawn(command_line: &str) -> Result<Self, String> {
        let mut command = shell_command(command_line);
        let mut child = command
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|error| error.to_string())?;

        let stdin = child
            .stdin
            .take()
            .ok_or_else(|| "missing plugin bridge stdin".to_string())?;
        let stdout = child
            .stdout
            .take()
            .ok_or_else(|| "missing plugin bridge stdout".to_string())?;

        let (tx, rx) = mpsc::channel();
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                let Ok(line) = line else {
                    break;
                };
                if tx.send(line).is_err() {
                    break;
                }
            }
        });

        Ok(Self {
            _child: Mutex::new(child),
            stdin: Mutex::new(stdin),
            rx: Mutex::new(rx),
        })
    }

    fn send_hook<T: Serialize + ?Sized>(&self, hook: &str, payload: &T) {
        let body = serde_json::json!({
            "kind": "hook",
            "hook": hook,
            "payload": payload,
        });
        self.send_line(&body);
    }

    fn send_event<T: Serialize + ?Sized>(&self, event: &str, payload: &T) {
        let body = serde_json::json!({
            "kind": "event",
            "event": event,
            "payload": payload,
        });
        self.send_line(&body);
    }

    fn send_line(&self, payload: &Value) {
        let Ok(line) = serde_json::to_string(payload) else {
            return;
        };
        let Ok(mut stdin) = self.stdin.lock() else {
            return;
        };
        if stdin.write_all(line.as_bytes()).is_err() {
            return;
        }
        if stdin.write_all(b"\n").is_err() {
            return;
        }
        let _ = stdin.flush();
    }

    fn extend_effects(&self, effects: &mut PluginEffects) {
        let Ok(rx) = self.rx.lock() else {
            return;
        };
        for line in rx.try_iter() {
            match serde_json::from_str::<ExternalPluginMessage>(&line) {
                Ok(ExternalPluginMessage::Notify { message }) => {
                    effects.notifications.push(message);
                }
                Ok(ExternalPluginMessage::SystemNotify {
                    title,
                    message,
                    subtitle,
                }) => effects
                    .system_notifications
                    .push(SystemNotificationRequest {
                        title: title.unwrap_or_else(|| "Wok".to_string()),
                        message,
                        subtitle,
                    }),
                Ok(ExternalPluginMessage::Exec { command }) => effects.exec_requests.push(command),
                Ok(ExternalPluginMessage::Action { action }) => {
                    effects.action_requests.push(action);
                }
                Err(error) => effects
                    .notifications
                    .push(format!("external plugin bridge parse error: {error}")),
            }
        }
    }
}

fn shell_command(command_line: &str) -> Command {
    #[cfg(windows)]
    {
        let mut command = Command::new("cmd");
        command.arg("/C").arg(command_line);
        command
    }
    #[cfg(not(windows))]
    {
        let mut command = Command::new("sh");
        command.arg("-lc").arg(command_line);
        command
    }
}

fn parse_lua_context(mode: &str) -> Option<Context> {
    match mode {
        "normal" | "terminal" => Some(Context::Terminal),
        "input" => Some(Context::InputEditor),
        "block" => Some(Context::BlockSelected),
        "search" => Some(Context::SearchActive),
        "vi" => Some(Context::ViMode),
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
        let config_dir = std::env::temp_dir().join(format!("wok-plugin-host-{unique}"));
        std::fs::create_dir_all(&config_dir).expect("config dir should be created");
        std::fs::write(config_dir.join("init.lua"), "this is not valid lua !!!")
            .expect("invalid init.lua should be written");

        let host = PluginHost::new(&config_dir, None).expect("plugin host should still initialize");
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
