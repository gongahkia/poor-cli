//! Lua scripting runtime for user configuration and extensions.

use std::cell::RefCell;
use std::collections::{BinaryHeap, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mlua::{Function, Lua, LuaSerdeExt, RegistryKey, Result as LuaResult, Table, Value};
use serde::Serialize;
use serde_json::Value as JsonValue;
use tracing::{info, warn};
use walk_input::workflows::{Workflow, WorkflowParam};
use walk_ui::status_bar::StatusSegment;

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

/// Theme work requested by Lua.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ThemeRequest {
    /// Load a named or explicit theme path.
    Load(String),
    /// Apply live theme overrides.
    Override(HashMap<String, String>),
}

/// Trigger work requested by Lua.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TriggerRequest {
    /// Add or replace a trigger.
    Add {
        /// Trigger name.
        name: String,
        /// Regex pattern.
        pattern: String,
        /// Action descriptors.
        actions: Vec<String>,
    },
    /// Remove a trigger by name.
    Remove {
        /// Trigger name.
        name: String,
    },
}

/// Quick-select pattern work requested by Lua.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum QuickSelectPatternRequest {
    /// Add or replace a custom quick-select regex pattern.
    Add {
        /// Pattern display name.
        name: String,
        /// Regex expression.
        regex: String,
    },
    /// Remove a custom quick-select pattern.
    Remove {
        /// Pattern display name.
        name: String,
    },
}

/// Workflow registration work requested by Lua.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WorkflowRequest {
    /// Register or replace a workflow.
    Register(Workflow),
}

/// Status bar update work requested by Lua.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StatusBarRequest {
    /// Replace custom left segments.
    SetLeft(Vec<StatusSegment>),
    /// Replace custom center segments.
    SetCenter(Vec<StatusSegment>),
    /// Replace custom right segments.
    SetRight(Vec<StatusSegment>),
    /// Clear all custom segments.
    Clear,
    /// Set refresh hook interval in milliseconds.
    SetRefreshInterval(u64),
}

/// Shared state for Lua callbacks to write to.
#[derive(Default, Clone)]
pub struct LuaState {
    /// Keybinding overrides registered by Lua.
    pub keybindings: Arc<Mutex<Vec<LuaKeybinding>>>,
    /// Theme overrides from Lua.
    pub theme_overrides: Arc<Mutex<HashMap<String, String>>>,
    /// Pending theme requests from Lua.
    pub theme_requests: Arc<Mutex<Vec<ThemeRequest>>>,
    /// Status messages from Lua.
    pub notifications: Arc<Mutex<Vec<String>>>,
    /// Pending shell commands requested by Lua.
    pub exec_requests: Arc<Mutex<Vec<String>>>,
    /// Pending built-in action requests requested by Lua.
    pub action_requests: Arc<Mutex<Vec<String>>>,
    /// Pending trigger registration requests requested by Lua.
    pub trigger_requests: Arc<Mutex<Vec<TriggerRequest>>>,
    /// Pending quick-select pattern requests requested by Lua.
    pub quick_select_pattern_requests: Arc<Mutex<Vec<QuickSelectPatternRequest>>>,
    /// Pending workflow registration requests requested by Lua.
    pub workflow_requests: Arc<Mutex<Vec<WorkflowRequest>>>,
    /// Lua-registered workflow cache for `walk.workflows()`.
    pub workflows: Arc<Mutex<Vec<Workflow>>>,
    /// Pending status bar customization requests requested by Lua.
    pub status_bar_requests: Arc<Mutex<Vec<StatusBarRequest>>>,
    /// Named commands registered from Lua as action aliases.
    pub commands: Arc<Mutex<HashMap<String, String>>>,
    /// Latest runtime snapshot exposed to plugin callbacks.
    pub runtime_snapshot: Arc<Mutex<JsonValue>>,
}

/// Scheduled Lua timer callback entry.
struct TimerEntry {
    id: u64,
    fire_at: Instant,
    callback: RegistryKey,
    interval: Option<Duration>,
}

impl PartialEq for TimerEntry {
    fn eq(&self, other: &Self) -> bool {
        self.id == other.id && self.fire_at == other.fire_at
    }
}

impl Eq for TimerEntry {}

impl PartialOrd for TimerEntry {
    fn partial_cmp(&self, other: &Self) -> Option<std::cmp::Ordering> {
        Some(self.cmp(other))
    }
}

impl Ord for TimerEntry {
    fn cmp(&self, other: &Self) -> std::cmp::Ordering {
        // Reverse ordering so BinaryHeap pops the earliest fire time first.
        other
            .fire_at
            .cmp(&self.fire_at)
            .then_with(|| other.id.cmp(&self.id))
    }
}

/// Lua scripting runtime for Walk.
pub struct LuaRuntime {
    lua: Lua,
    init_path: Option<PathBuf>,
    /// Shared state accessible from Lua callbacks.
    pub state: LuaState,
    hooks: Rc<RefCell<HashMap<String, Vec<RegistryKey>>>>,
    timers: Rc<RefCell<BinaryHeap<TimerEntry>>>,
    cancelled_timers: Rc<RefCell<HashSet<u64>>>,
    next_timer_id: Rc<RefCell<u64>>,
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
            timers: Rc::new(RefCell::new(BinaryHeap::new())),
            cancelled_timers: Rc::new(RefCell::new(HashSet::new())),
            next_timer_id: Rc::new(RefCell::new(1)),
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
        let theme_request_state = self.state.theme_requests.clone();
        let theme_set_fn = self.lua.create_function(move |_, table: Table| {
            let mut overrides = theme_state.lock().unwrap();
            let mut delta = HashMap::new();
            for pair in table.pairs::<String, Value>() {
                let (key, value) = pair?;
                let value = match value {
                    Value::String(s) => s.to_string_lossy().to_string(),
                    Value::Integer(i) => i.to_string(),
                    Value::Number(n) => n.to_string(),
                    Value::Boolean(b) => b.to_string(),
                    _ => {
                        return Err(mlua::Error::runtime(
                            "theme overrides must be string, number, or boolean values",
                        ));
                    }
                };
                overrides.insert(key.clone(), value.clone());
                delta.insert(key, value);
            }
            theme_request_state
                .lock()
                .unwrap()
                .push(ThemeRequest::Override(delta));
            Ok(())
        })?;
        theme_table.set("set", theme_set_fn)?;

        let theme_request_state = self.state.theme_requests.clone();
        let theme_load_fn = self.lua.create_function(move |_, name: String| {
            theme_request_state
                .lock()
                .unwrap()
                .push(ThemeRequest::Load(name));
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

        // walk.register_workflow(table)
        let workflow_request_state = self.state.workflow_requests.clone();
        let workflow_state = self.state.workflows.clone();
        let register_workflow_fn = self.lua.create_function(move |_, table: Table| {
            let name: String = table.get("name")?;
            let template: String = table.get("template")?;
            let description = table
                .get::<Option<String>>("description")?
                .unwrap_or_default();
            let params = table
                .get::<Option<Table>>("params")?
                .map(|params_table| {
                    params_table
                        .sequence_values::<Table>()
                        .map(|item| {
                            let item = item?;
                            Ok(WorkflowParam {
                                name: item.get::<String>("name")?,
                                placeholder: item
                                    .get::<Option<String>>("placeholder")?
                                    .unwrap_or_default(),
                                default: item.get::<Option<String>>("default")?,
                                description: item
                                    .get::<Option<String>>("description")?
                                    .unwrap_or_default(),
                            })
                        })
                        .collect::<LuaResult<Vec<_>>>()
                })
                .transpose()?
                .unwrap_or_default();

            let workflow = Workflow {
                name,
                description,
                template,
                params,
            };
            workflow_state
                .lock()
                .unwrap()
                .retain(|existing| existing.name != workflow.name);
            workflow_state.lock().unwrap().push(workflow.clone());
            workflow_request_state
                .lock()
                .unwrap()
                .push(WorkflowRequest::Register(workflow));
            Ok(())
        })?;
        walk.set("register_workflow", register_workflow_fn)?;

        // walk.workflows()
        let workflow_state = self.state.workflows.clone();
        let workflows_fn = self.lua.create_function(move |lua, ()| {
            let workflows = workflow_state.lock().unwrap().clone();
            lua.to_value(&workflows)
        })?;
        walk.set("workflows", workflows_fn)?;

        // walk.add_trigger(name, pattern, actions)
        let trigger_request_state = self.state.trigger_requests.clone();
        let add_trigger_fn = self.lua.create_function(
            move |_, (name, pattern, actions): (String, String, Table)| {
                let actions = actions
                    .sequence_values::<String>()
                    .collect::<LuaResult<Vec<_>>>()?;
                trigger_request_state
                    .lock()
                    .unwrap()
                    .push(TriggerRequest::Add {
                        name,
                        pattern,
                        actions,
                    });
                Ok(())
            },
        )?;
        walk.set("add_trigger", add_trigger_fn)?;

        // walk.remove_trigger(name)
        let trigger_request_state = self.state.trigger_requests.clone();
        let remove_trigger_fn = self.lua.create_function(move |_, name: String| {
            trigger_request_state
                .lock()
                .unwrap()
                .push(TriggerRequest::Remove { name });
            Ok(())
        })?;
        walk.set("remove_trigger", remove_trigger_fn)?;

        // walk.quick_select.add_pattern(name, regex)
        let quick_select_table = self.lua.create_table()?;
        let quick_select_state = self.state.quick_select_pattern_requests.clone();
        let add_quick_pattern_fn =
            self.lua
                .create_function(move |_, (name, regex): (String, String)| {
                    quick_select_state
                        .lock()
                        .unwrap()
                        .push(QuickSelectPatternRequest::Add { name, regex });
                    Ok(())
                })?;
        quick_select_table.set("add_pattern", add_quick_pattern_fn)?;

        // walk.quick_select.remove_pattern(name)
        let quick_select_state = self.state.quick_select_pattern_requests.clone();
        let remove_quick_pattern_fn = self.lua.create_function(move |_, name: String| {
            quick_select_state
                .lock()
                .unwrap()
                .push(QuickSelectPatternRequest::Remove { name });
            Ok(())
        })?;
        quick_select_table.set("remove_pattern", remove_quick_pattern_fn)?;
        walk.set("quick_select", quick_select_table)?;

        // walk.status_bar.{set_left,set_center,set_right,clear,set_refresh_interval}
        let status_bar_table = self.lua.create_table()?;

        let status_bar_state = self.state.status_bar_requests.clone();
        let set_left_fn = self.lua.create_function(move |_, segments: Table| {
            let segments = parse_status_segments(&segments)?;
            status_bar_state
                .lock()
                .unwrap()
                .push(StatusBarRequest::SetLeft(segments));
            Ok(())
        })?;
        status_bar_table.set("set_left", set_left_fn)?;

        let status_bar_state = self.state.status_bar_requests.clone();
        let set_center_fn = self.lua.create_function(move |_, segments: Table| {
            let segments = parse_status_segments(&segments)?;
            status_bar_state
                .lock()
                .unwrap()
                .push(StatusBarRequest::SetCenter(segments));
            Ok(())
        })?;
        status_bar_table.set("set_center", set_center_fn)?;

        let status_bar_state = self.state.status_bar_requests.clone();
        let set_right_fn = self.lua.create_function(move |_, segments: Table| {
            let segments = parse_status_segments(&segments)?;
            status_bar_state
                .lock()
                .unwrap()
                .push(StatusBarRequest::SetRight(segments));
            Ok(())
        })?;
        status_bar_table.set("set_right", set_right_fn)?;

        let status_bar_state = self.state.status_bar_requests.clone();
        let clear_fn = self.lua.create_function(move |_, ()| {
            status_bar_state
                .lock()
                .unwrap()
                .push(StatusBarRequest::Clear);
            Ok(())
        })?;
        status_bar_table.set("clear", clear_fn)?;

        let status_bar_state = self.state.status_bar_requests.clone();
        let set_interval_fn = self.lua.create_function(move |_, ms: u64| {
            status_bar_state
                .lock()
                .unwrap()
                .push(StatusBarRequest::SetRefreshInterval(ms));
            Ok(())
        })?;
        status_bar_table.set("set_refresh_interval", set_interval_fn)?;
        walk.set("status_bar", status_bar_table)?;

        // walk.set_timeout(ms, callback)
        let timers = self.timers.clone();
        let cancelled_timers = self.cancelled_timers.clone();
        let next_timer_id = self.next_timer_id.clone();
        let set_timeout_fn =
            self.lua
                .create_function(move |lua, (ms, callback): (u64, Function)| {
                    let duration = Duration::from_millis(ms.max(1));
                    let id = {
                        let mut next = next_timer_id.borrow_mut();
                        let id = *next;
                        *next = next.saturating_add(1);
                        id
                    };
                    let key = lua.create_registry_value(callback)?;
                    timers.borrow_mut().push(TimerEntry {
                        id,
                        fire_at: Instant::now() + duration,
                        callback: key,
                        interval: None,
                    });
                    cancelled_timers.borrow_mut().remove(&id);
                    Ok(id)
                })?;
        walk.set("set_timeout", set_timeout_fn)?;

        // walk.set_interval(ms, callback)
        let timers = self.timers.clone();
        let cancelled_timers = self.cancelled_timers.clone();
        let next_timer_id = self.next_timer_id.clone();
        let set_interval_fn =
            self.lua
                .create_function(move |lua, (ms, callback): (u64, Function)| {
                    let duration = Duration::from_millis(ms.max(1));
                    let id = {
                        let mut next = next_timer_id.borrow_mut();
                        let id = *next;
                        *next = next.saturating_add(1);
                        id
                    };
                    let key = lua.create_registry_value(callback)?;
                    timers.borrow_mut().push(TimerEntry {
                        id,
                        fire_at: Instant::now() + duration,
                        callback: key,
                        interval: Some(duration),
                    });
                    cancelled_timers.borrow_mut().remove(&id);
                    Ok(id)
                })?;
        walk.set("set_interval", set_interval_fn)?;

        // walk.clear_timer(id)
        let cancelled_timers = self.cancelled_timers.clone();
        let clear_timer_fn = self.lua.create_function(move |_, id: u64| {
            cancelled_timers.borrow_mut().insert(id);
            Ok(())
        })?;
        walk.set("clear_timer", clear_timer_fn)?;

        // walk.run_action(action) — queue a built-in runtime action
        let action_state = self.state.action_requests.clone();
        let run_action_fn = self.lua.create_function(move |_, action: String| {
            action_state.lock().unwrap().push(action);
            Ok(())
        })?;
        walk.set("run_action", run_action_fn.clone())?;
        walk.set("action", run_action_fn)?;

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

        let snapshot_state = self.state.runtime_snapshot.clone();
        walk.set(
            "app",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let app = snapshot.get("app").cloned().unwrap_or_default();
                lua.to_value(&app)
            })?,
        )?;

        let snapshot_state = self.state.runtime_snapshot.clone();
        walk.set(
            "workspace",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let workspace = snapshot.get("workspace").cloned().unwrap_or_default();
                lua.to_value(&workspace)
            })?,
        )?;

        let snapshot_state = self.state.runtime_snapshot.clone();
        walk.set(
            "pane",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let pane = snapshot.get("pane").cloned().unwrap_or_default();
                lua.to_value(&pane)
            })?,
        )?;

        let snapshot_state = self.state.runtime_snapshot.clone();
        walk.set(
            "session",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let session = snapshot.get("session").cloned().unwrap_or_default();
                lua.to_value(&session)
            })?,
        )?;

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

    /// Return number of listeners registered for a hook name.
    pub fn hook_listener_count(&self, event: &str) -> usize {
        self.hooks.borrow().get(event).map_or(0, std::vec::Vec::len)
    }

    /// Execute due timers, up to `max_fires` callbacks.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if any callback raises an error.
    pub fn run_due_timers(&self, max_fires: usize) -> LuaResult<usize> {
        let mut fired = 0usize;
        let now = Instant::now();

        while fired < max_fires {
            let due = self
                .timers
                .borrow()
                .peek()
                .is_some_and(|entry| entry.fire_at <= now);
            if !due {
                break;
            }

            let Some(mut entry) = self.timers.borrow_mut().pop() else {
                break;
            };

            if self.cancelled_timers.borrow_mut().remove(&entry.id) {
                self.lua.remove_registry_value(entry.callback)?;
                continue;
            }

            let callback: Function = self.lua.registry_value(&entry.callback)?;
            callback.call::<()>(())?;
            fired = fired.saturating_add(1);

            if self.cancelled_timers.borrow_mut().remove(&entry.id) {
                self.lua.remove_registry_value(entry.callback)?;
                continue;
            }

            if let Some(interval) = entry.interval {
                entry.fire_at = Instant::now() + interval;
                self.timers.borrow_mut().push(entry);
            } else {
                self.lua.remove_registry_value(entry.callback)?;
            }
        }

        Ok(fired)
    }

    /// Drain pending shell commands queued from Lua.
    pub fn take_exec_requests(&self) -> Vec<String> {
        std::mem::take(&mut *self.state.exec_requests.lock().unwrap())
    }

    /// Drain pending built-in action requests queued from Lua.
    pub fn take_action_requests(&self) -> Vec<String> {
        std::mem::take(&mut *self.state.action_requests.lock().unwrap())
    }

    /// Drain pending theme requests queued from Lua.
    pub fn take_theme_requests(&self) -> Vec<ThemeRequest> {
        std::mem::take(&mut *self.state.theme_requests.lock().unwrap())
    }

    /// Drain pending trigger requests queued from Lua.
    pub fn take_trigger_requests(&self) -> Vec<TriggerRequest> {
        std::mem::take(&mut *self.state.trigger_requests.lock().unwrap())
    }

    /// Drain pending quick-select pattern requests queued from Lua.
    pub fn take_quick_select_pattern_requests(&self) -> Vec<QuickSelectPatternRequest> {
        std::mem::take(&mut *self.state.quick_select_pattern_requests.lock().unwrap())
    }

    /// Drain pending workflow registration requests queued from Lua.
    pub fn take_workflow_requests(&self) -> Vec<WorkflowRequest> {
        std::mem::take(&mut *self.state.workflow_requests.lock().unwrap())
    }

    /// Drain pending status bar requests queued from Lua.
    pub fn take_status_bar_requests(&self) -> Vec<StatusBarRequest> {
        std::mem::take(&mut *self.state.status_bar_requests.lock().unwrap())
    }

    /// Resolve a named command alias registered from Lua to an action string.
    pub fn resolve_command_action(&self, name: &str) -> Option<String> {
        self.state.commands.lock().unwrap().get(name).cloned()
    }

    /// Return the current command alias table registered from Lua.
    pub fn command_aliases(&self) -> HashMap<String, String> {
        self.state.commands.lock().unwrap().clone()
    }

    /// Drain pending notifications queued from Lua.
    pub fn take_notifications(&self) -> Vec<String> {
        std::mem::take(&mut *self.state.notifications.lock().unwrap())
    }

    /// Push a notification into the pending Lua notification queue.
    pub fn push_notification(&self, message: impl Into<String>) {
        self.state
            .notifications
            .lock()
            .unwrap()
            .push(message.into());
    }

    /// Update the latest runtime snapshot exposed through the `walk.*()` accessors.
    pub fn set_runtime_snapshot(&self, snapshot: JsonValue) {
        *self.state.runtime_snapshot.lock().unwrap() = snapshot;
    }

    /// Update the read-only `walk.config` table with current runtime values.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if the table cannot be updated.
    pub fn set_config_values(&self, values: &JsonValue) -> LuaResult<()> {
        let walk: Table = self.lua.globals().get("walk")?;
        let config: Table = walk.get("config")?;

        config.clear()?;
        let Some(object) = values.as_object() else {
            return Ok(());
        };
        for (key, value) in object {
            config.set(key.as_str(), self.lua.to_value(value)?)?;
        }

        Ok(())
    }
}

fn parse_status_segments(table: &Table) -> LuaResult<Vec<StatusSegment>> {
    table
        .sequence_values::<Table>()
        .map(|item| {
            let item = item?;
            Ok(StatusSegment {
                text: item.get::<String>("text")?,
                fg: item.get::<Option<String>>("fg")?,
                bg: item.get::<Option<String>>("bg")?,
                bold: item.get::<Option<bool>>("bold")?.unwrap_or(false),
            })
        })
        .collect::<LuaResult<Vec<_>>>()
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

    #[test]
    fn test_run_action_queues_request() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(r#"walk.run_action("new_tab")"#)
            .expect("run_action should work");

        assert_eq!(runtime.take_action_requests(), vec!["new_tab".to_string()]);
    }

    #[test]
    fn test_runtime_snapshot_accessors_return_tables() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime.set_runtime_snapshot(serde_json::json!({
            "workspace": { "tab_count": 3 },
            "pane": { "cwd": "/tmp/demo" },
        }));
        runtime
            .exec(
                r#"
                local workspace = walk.workspace()
                local pane = walk.pane()
                walk.notify(tostring(workspace.tab_count) .. ":" .. pane.cwd)
            "#,
            )
            .expect("snapshot accessors should work");

        assert_eq!(
            runtime.take_notifications(),
            vec!["3:/tmp/demo".to_string()]
        );
    }

    #[test]
    fn test_theme_requests_are_queued() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r##"
                walk.theme.set({ background = "#112233", opacity = 0.6 })
                walk.theme.load("paper")
            "##,
            )
            .expect("theme requests should queue");

        let requests = runtime.take_theme_requests();
        assert_eq!(requests.len(), 2);
        assert!(matches!(requests[0], ThemeRequest::Override(_)));
        assert_eq!(requests[1], ThemeRequest::Load("paper".to_string()));
    }

    #[test]
    fn test_config_table_tracks_runtime_values() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .set_config_values(&serde_json::json!({
                "font_size": 17.0,
                "font_family": "Iosevka",
                "shell": "zsh",
            }))
            .expect("config values should update");
        runtime
            .exec(
                r#"
                walk.notify(walk.config.font_family .. ":" .. tostring(walk.config.font_size) .. ":" .. walk.config.shell)
            "#,
            )
            .expect("config table should be readable");

        assert_eq!(
            runtime.take_notifications(),
            vec!["Iosevka:17.0:zsh".to_string()]
        );
    }

    #[test]
    fn test_status_bar_requests_are_queued() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r##"
                walk.status_bar.set_right({{ text = " K8s: prod ", fg = "#00ff00", bold = true }})
                walk.status_bar.set_left({{ text = " left " }})
                walk.status_bar.set_refresh_interval(2500)
                "##,
            )
            .expect("status bar requests should queue");

        let requests = runtime.take_status_bar_requests();
        assert!(matches!(requests[0], StatusBarRequest::SetRight(_)));
        assert!(matches!(requests[1], StatusBarRequest::SetLeft(_)));
        assert_eq!(requests[2], StatusBarRequest::SetRefreshInterval(2500));
    }

    #[test]
    fn test_set_timeout_fires() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                walk.set_timeout(1, function()
                    walk.notify("timeout")
                end)
            "#,
            )
            .expect("timeout should register");
        std::thread::sleep(Duration::from_millis(5));
        runtime.run_due_timers(64).expect("timer should run");
        assert_eq!(runtime.take_notifications(), vec!["timeout".to_string()]);
    }

    #[test]
    fn test_set_interval_and_clear_timer() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                local id = walk.set_interval(1, function()
                    walk.notify("tick")
                end)
                walk.clear_timer(id)
            "#,
            )
            .expect("interval should register");
        std::thread::sleep(Duration::from_millis(5));
        runtime.run_due_timers(64).expect("timer loop should run");
        assert!(runtime.take_notifications().is_empty());
    }

    #[test]
    fn test_timer_execution_cap() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                for i = 1, 100 do
                    walk.set_timeout(1, function()
                        walk.notify("fire")
                    end)
                end
            "#,
            )
            .expect("timers should register");

        std::thread::sleep(Duration::from_millis(5));
        let first = runtime.run_due_timers(64).expect("first timer pass");
        let second = runtime.run_due_timers(64).expect("second timer pass");
        assert_eq!(first, 64);
        assert_eq!(second, 36);
    }
}
