//! Lua scripting runtime for user configuration and extensions.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};

use mlua::{Function, Lua, Result as LuaResult, Table, Value};
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

/// Collected event callbacks from Lua.
#[derive(Debug, Clone)]
pub struct LuaEventHook {
    /// Event name.
    pub event: String,
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
}

/// Lua scripting runtime for Walk.
pub struct LuaRuntime {
    lua: Lua,
    init_path: Option<PathBuf>,
    /// Shared state accessible from Lua callbacks.
    pub state: LuaState,
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

        // walk.keymap(mode, key, action) — register keybinding
        let kb_state = self.state.keybindings.clone();
        let keymap_fn = self.lua.create_function(move |_, (mode, key, action): (String, String, Value)| {
            let action_str = match action {
                Value::String(s) => s.to_string_lossy().to_string(),
                Value::Function(_) => "lua_callback".to_string(),
                _ => return Err(mlua::Error::runtime("action must be a string or function")),
            };
            kb_state.lock().unwrap().push(LuaKeybinding {
                mode,
                key,
                action: action_str,
            });
            Ok(())
        })?;
        walk.set("keymap", keymap_fn)?;

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
        let on_fn = self.lua.create_function(|_, (event, _callback): (String, Function)| {
            info!("registered event hook: {event}");
            Ok(())
        })?;
        walk.set("on", on_fn)?;

        // walk.exec(command) — execute shell command
        let exec_fn = self.lua.create_function(|_, _command: String| {
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
}
