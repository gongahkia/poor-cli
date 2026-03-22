//! Lua scripting runtime for user configuration and extensions.

use std::cell::RefCell;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::{Arc, Mutex};

use mlua::{Function, Lua, LuaSerdeExt, RegistryKey, Result as LuaResult, Table, Value};
use serde::Serialize;
use tracing::{info, warn};

/// Collected keybinding overrides from Lua.
#[derive(Debug, Clone)]
pub struct LuaKeybinding {
    /// Mode: "normal", "input", "search".
    pub mode: String,
    /// Key combo string like "ctrl+t".
    pub key: String,
    /// Action name or "lua_callback".
    pub action: String,
}

/// Shared state for Lua callbacks to write to.
#[derive(Default, Clone)]
pub struct LuaState {
    /// Keybinding overrides registered by Lua.
    pub keybindings: Arc<Mutex<Vec<LuaKeybinding>>>,
    /// Theme overrides from Lua.
    pub theme_overrides: Arc<Mutex<HashMap<String, String>>>,
    /// Status messages from Lua.
    pub notifications: Arc<Mutex<Vec<String>>>,
    /// Pending shell commands requested by Lua.
    pub exec_requests: Arc<Mutex<Vec<String>>>,
    /// Named commands registered from Lua as action aliases.
    pub commands: Arc<Mutex<HashMap<String, String>>>,
}

/// Lua scripting runtime for Walk.
pub struct LuaRuntime {
    lua: Lua,
    init_path: Option<PathBuf>,
    /// Shared state accessible from Lua callbacks.
    pub state: LuaState,
    hooks: Rc<RefCell<HashMap<String, Vec<RegistryKey>>>>,
}

impl LuaRuntime {
    /// Create a new Lua runtime.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if the VM cannot be initialized.
    pub fn new() -> LuaResult<Self> {
        let lua = Lua::new();
        let state = LuaState::default();
        Ok(Self {
            lua,
            init_path: None,
            state,
            hooks: Rc::new(RefCell::new(HashMap::new())),
        })
    }

    /// Initialize the runtime and load init.lua if present.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if init.lua has syntax or runtime errors.
    pub fn init(&mut self, config_dir: &Path) -> LuaResult<()> {
        self.register_walk_api()?;

        let init_path = config_dir.join("init.lua");
        if init_path.exists() {
            info!("loading init.lua from {}", init_path.display());
            match self.load_file(&init_path) {
                Ok(()) => {
                    self.init_path = Some(init_path);
                }
                Err(e) => {
                    warn!("error in init.lua: {e}");
                    return Err(e);
                }
            }
        }
        Ok(())
    }

    /// Register the `walk` global API table.
    fn register_walk_api(&self) -> LuaResult<()> {
        let walk = self.lua.create_table()?;

        // walk.config table (read-only config values)
        let config = self.lua.create_table()?;
        config.set("font_size", 14.0)?;
        config.set("font_family", "JetBrains Mono")?;
        config.set("scrollback_lines", 10_000)?;
        walk.set("config", config)?;

        // walk.bind_key(mode, key, action) — register keybinding
        let kb_state = self.state.keybindings.clone();
        let bind_key_fn =
            self.lua
                .create_function(move |_, (mode, key, action): (String, String, Value)| {
                    let action_str = match action {
                        Value::String(s) => s.to_string_lossy().to_string(),
                        Value::Function(_) => "lua_callback".to_string(),
                        _ => {
                            return Err(mlua::Error::runtime("action must be a string or function"))
                        }
                    };
                    kb_state.lock().unwrap().push(LuaKeybinding {
                        mode,
                        key,
                        action: action_str,
                    });
                    Ok(())
                })?;
        walk.set("bind_key", bind_key_fn.clone())?;
        walk.set("keymap", bind_key_fn)?;

        // walk.theme table with set() and load()
        let theme_table = self.lua.create_table()?;
        let theme_state = self.state.theme_overrides.clone();
        let theme_set_fn = self.lua.create_function(move |_, table: Table| {
            let mut overrides = theme_state.lock().unwrap();
            for pair in table.pairs::<String, String>() {
                if let Ok((key, value)) = pair {
                    overrides.insert(key, value);
                }
            }
            Ok(())
        })?;
        theme_table.set("set", theme_set_fn)?;

        let theme_load_fn = self.lua.create_function(|_, name: String| {
            info!("loading theme: {name}");
            Ok(())
        })?;
        theme_table.set("load", theme_load_fn)?;
        walk.set("theme", theme_table)?;

        // walk.on(event, callback) — register event hook
        let hook_state = self.hooks.clone();
        let on_fn =
            self.lua
                .create_function(move |lua, (event, callback): (String, Function)| {
                    let key = lua.create_registry_value(callback)?;
                    hook_state
                        .borrow_mut()
                        .entry(event.clone())
                        .or_default()
                        .push(key);
                    info!("registered event hook: {event}");
                    Ok(())
                })?;
        walk.set("on", on_fn)?;

        // walk.register_command(name, action) — register named action aliases
        let command_state = self.state.commands.clone();
        let register_command_fn =
            self.lua
                .create_function(move |_, (name, action): (String, String)| {
                    command_state.lock().unwrap().insert(name, action);
                    Ok(())
                })?;
        walk.set("register_command", register_command_fn)?;

        // walk.exec(command) — queue a shell command for the active pane
        let exec_state = self.state.exec_requests.clone();
        let exec_fn = self.lua.create_function(move |_, command: String| {
            exec_state.lock().unwrap().push(command);
            Ok(())
        })?;
        walk.set("exec", exec_fn)?;

        // walk.notify(message) — show status message
        let notify_state = self.state.notifications.clone();
        let notify_fn = self.lua.create_function(move |_, message: String| {
            notify_state.lock().unwrap().push(message);
            Ok(())
        })?;
        walk.set("notify", notify_fn)?;

        self.lua.globals().set("walk", walk)?;
        Ok(())
    }

    /// Load and execute a Lua file.
    fn load_file(&self, path: &Path) -> LuaResult<()> {
        let content = std::fs::read_to_string(path)
            .map_err(|e| mlua::Error::runtime(format!("cannot read {}: {e}", path.display())))?;
        self.lua.load(&content).exec()
    }

    /// Reload init.lua.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if the reload fails.
    pub fn reload(&self) -> LuaResult<()> {
        if let Some(ref path) = self.init_path {
            self.load_file(path)
        } else {
            Ok(())
        }
    }

    /// Execute a Lua string.
    ///
    /// # Errors
    ///
    /// Returns a Lua error on syntax or runtime errors.
    pub fn exec(&self, code: &str) -> LuaResult<()> {
        self.lua.load(code).exec()
    }

    /// Trigger a lifecycle hook with optional JSON-like payload.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if any registered callback fails.
    pub fn trigger_hook<T>(&self, event: &str, payload: &T) -> LuaResult<()>
    where
        T: Serialize + ?Sized,
    {
        let payload = self.lua.to_value(payload)?;
        if let Some(callbacks) = self.hooks.borrow().get(event) {
            for callback_key in callbacks {
                let callback: Function = self.lua.registry_value(callback_key)?;
                callback.call::<()>(payload.clone())?;
            }
        }
        Ok(())
    }

    /// Drain pending shell commands queued from Lua.
    pub fn take_exec_requests(&self) -> Vec<String> {
        std::mem::take(&mut *self.state.exec_requests.lock().unwrap())
    }

    /// Drain pending notifications queued from Lua.
    pub fn take_notifications(&self) -> Vec<String> {
        std::mem::take(&mut *self.state.notifications.lock().unwrap())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trigger_hook_passes_structured_payload() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                walk.on("demo", function(event)
                    walk.notify(event.message .. ":" .. tostring(event.code))
                end)
                "#,
            )
            .expect("register hook");

        runtime
            .trigger_hook("demo", &serde_json::json!({"message": "ok", "code": 7}))
            .expect("hook should run");

        assert_eq!(runtime.take_notifications(), vec!["ok:7".to_string()]);
    }
}
