//! Lua scripting runtime for user configuration and extensions.

/// Version of the Lua plugin API surface, exposed to plugins as
/// `wok.api_version`. Bumped per `docs/LUA_API_STABILITY.md`.
pub const LUA_API_VERSION: &str = "1.1.0";

use std::cell::RefCell;
use std::collections::{BinaryHeap, HashMap, HashSet};
use std::path::{Path, PathBuf};
use std::rc::Rc;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use mlua::{Function, Integer, Lua, LuaSerdeExt, RegistryKey, Result as LuaResult, Table, Value};
use serde::Serialize;
use serde_json::Value as JsonValue;
use tracing::{info, warn};
use wok_input::workflows::{Workflow, WorkflowParam};
use wok_ui::status_bar::StatusSegment;

/// Allowed sandbox roots for `wok.fs.*`. Resolves `$HOME` lazily so the test
/// suite can override it via env.
fn sandbox_roots() -> Vec<PathBuf> {
    let mut roots = Vec::new();
    if let Some(home) = std::env::var_os("HOME").map(PathBuf::from) {
        roots.push(home.join(".config").join("wok").join("data"));
        roots.push(home.join(".local").join("share").join("wok"));
    }
    roots
}

/// Resolve a user-supplied path against the wok.fs sandbox. The input may be
/// relative (resolved under `~/.config/wok/data/`) or absolute. After symlink
/// resolution it must descend from at least one [`sandbox_roots`] entry, else
/// returns an error.
pub(crate) fn resolve_sandboxed_path(path: &str) -> Result<PathBuf, String> {
    if path.is_empty() {
        return Err("wok.fs: path is empty".to_string());
    }
    let mut candidate = PathBuf::from(path);
    if candidate.is_relative() {
        let roots = sandbox_roots();
        let primary = roots
            .first()
            .ok_or_else(|| "wok.fs: HOME not set; sandbox unavailable".to_string())?;
        candidate = primary.join(candidate);
    }
    // ensure parent exists so canonicalize succeeds for files we're about to
    // write; parent must itself canonicalise to inside the sandbox.
    let canon = if candidate.exists() {
        candidate
            .canonicalize()
            .map_err(|e| format!("wok.fs: canonicalize failed: {e}"))?
    } else {
        let parent = candidate
            .parent()
            .ok_or_else(|| "wok.fs: path has no parent".to_string())?;
        let parent_canon = if parent.exists() {
            parent
                .canonicalize()
                .map_err(|e| format!("wok.fs: parent canonicalize failed: {e}"))?
        } else {
            // parent is in the sandbox root; allow if any root is a prefix.
            parent.to_path_buf()
        };
        parent_canon.join(candidate.file_name().unwrap_or_default())
    };
    let roots = sandbox_roots();
    if roots.iter().any(|root| canon.starts_with(root)) {
        Ok(canon)
    } else {
        Err(format!(
            "wok.fs: path {} is outside the allowed sandbox roots",
            canon.display()
        ))
    }
}

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

/// Window-level operations requested by Lua.
#[derive(Debug, Clone, PartialEq)]
pub enum WindowRequest {
    /// Set the OS window title.
    SetTitle(String),
    /// Toggle fullscreen state.
    ToggleFullscreen,
    /// Set the window opacity in `[0.0, 1.0]`.
    SetOpacity(f32),
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

/// Local setup lifecycle work requested by Lua.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SetupRequest {
    /// Run `wok init`.
    Init {
        /// Overwrite existing managed files.
        overwrite: bool,
    },
    /// Run `wok doctor`.
    Doctor {
        /// Whether to request JSON output mode.
        json: bool,
    },
    /// Run `wok reset`.
    Reset {
        /// Reset scope string: managed, state, or all.
        scope: String,
        /// Destructive confirmation.
        yes: bool,
    },
    /// Run `wok shell install`.
    ShellInstall {
        /// Optional shell target.
        shell: Option<String>,
        /// Overwrite managed integration files first.
        overwrite: bool,
    },
    /// Run `wok shell rollback`.
    ShellRollback {
        /// Optional shell target.
        shell: Option<String>,
        /// Destructive confirmation.
        yes: bool,
    },
}

/// Native desktop notification requested by Lua.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SystemNotificationRequest {
    /// Notification title.
    pub title: String,
    /// Notification body text.
    pub message: String,
    /// Optional secondary title/subtitle text.
    pub subtitle: Option<String>,
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
    /// Native desktop notifications from Lua.
    pub system_notifications: Arc<Mutex<Vec<SystemNotificationRequest>>>,
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
    /// Lua-registered workflow cache for `wok.workflows()`.
    pub workflows: Arc<Mutex<Vec<Workflow>>>,
    /// Pending status bar customization requests requested by Lua.
    pub status_bar_requests: Arc<Mutex<Vec<StatusBarRequest>>>,
    /// Pending setup lifecycle requests requested by Lua.
    pub setup_requests: Arc<Mutex<Vec<SetupRequest>>>,
    /// Named commands registered from Lua as action aliases.
    pub commands: Arc<Mutex<HashMap<String, String>>>,
    /// Latest runtime snapshot exposed to plugin callbacks.
    pub runtime_snapshot: Arc<Mutex<JsonValue>>,
    /// Clipboard copy requests (UTF-8 strings).
    pub clipboard_copy_requests: Arc<Mutex<Vec<String>>>,
    /// Raw PTY bytes to inject into the active pane.
    pub pty_input_requests: Arc<Mutex<Vec<Vec<u8>>>>,
    /// Window-level requests (title, fullscreen, opacity).
    pub window_requests: Arc<Mutex<Vec<WindowRequest>>>,
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

fn warn_deprecated_lua_api_once(
    warnings: &Rc<RefCell<HashSet<String>>>,
    symbol: &str,
    replacement: &str,
) {
    let key = symbol.to_string();
    if warnings.borrow_mut().insert(key) {
        warn!("deprecated Lua API '{symbol}' used; use '{replacement}' instead");
    }
}

/// Lua scripting runtime for Wok.
pub struct LuaRuntime {
    lua: Lua,
    init_path: Option<PathBuf>,
    /// Shared state accessible from Lua callbacks.
    pub state: LuaState,
    hooks: Rc<RefCell<HashMap<String, Vec<RegistryKey>>>>,
    timers: Rc<RefCell<BinaryHeap<TimerEntry>>>,
    cancelled_timers: Rc<RefCell<HashSet<u64>>>,
    next_timer_id: Rc<RefCell<u64>>,
    deprecated_warnings: Rc<RefCell<HashSet<String>>>,
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
            deprecated_warnings: Rc::new(RefCell::new(HashSet::new())),
        })
    }

    /// Initialize the runtime and load init.lua if present.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if init.lua has syntax or runtime errors.
    pub fn init(&mut self, config_dir: &Path) -> LuaResult<()> {
        self.register_wok_api()?;

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

    /// Register the `wok` global API table.
    fn register_wok_api(&self) -> LuaResult<()> {
        let wok = self.lua.create_table()?;

        // wok.config table (read-only config values)
        let config = self.lua.create_table()?;
        wok.set("config", config)?;

        // wok.bind_key(mode, key, action) — register keybinding
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
        wok.set("bind_key", bind_key_fn.clone())?;
        let keymap_warnings = self.deprecated_warnings.clone();
        let keymap_fn =
            self.lua
                .create_function(move |_, (mode, key, action): (String, String, Value)| {
                    warn_deprecated_lua_api_once(&keymap_warnings, "wok.keymap", "wok.bind_key");
                    bind_key_fn.call::<()>((mode, key, action))
                })?;
        wok.set("keymap", keymap_fn)?;

        // wok.theme table with set() and load()
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
        wok.set("theme", theme_table)?;

        // wok.on(event, callback) — register event hook
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
        wok.set("on", on_fn)?;

        // wok.register_command(name, action) — register named action aliases
        let command_state = self.state.commands.clone();
        let register_command_fn =
            self.lua
                .create_function(move |_, (name, action): (String, String)| {
                    command_state.lock().unwrap().insert(name, action);
                    Ok(())
                })?;
        wok.set("register_command", register_command_fn)?;

        // wok.register_workflow(table)
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
        wok.set("register_workflow", register_workflow_fn)?;

        // wok.workflows()
        let workflow_state = self.state.workflows.clone();
        let workflows_fn = self.lua.create_function(move |lua, ()| {
            let workflows = workflow_state.lock().unwrap().clone();
            lua.to_value(&workflows)
        })?;
        wok.set("workflows", workflows_fn)?;

        // wok.add_trigger(name, pattern, actions)
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
        wok.set("add_trigger", add_trigger_fn)?;

        // wok.remove_trigger(name)
        let trigger_request_state = self.state.trigger_requests.clone();
        let remove_trigger_fn = self.lua.create_function(move |_, name: String| {
            trigger_request_state
                .lock()
                .unwrap()
                .push(TriggerRequest::Remove { name });
            Ok(())
        })?;
        wok.set("remove_trigger", remove_trigger_fn)?;

        // wok.quick_select.add_pattern(name, regex)
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

        // wok.quick_select.remove_pattern(name)
        let quick_select_state = self.state.quick_select_pattern_requests.clone();
        let remove_quick_pattern_fn = self.lua.create_function(move |_, name: String| {
            quick_select_state
                .lock()
                .unwrap()
                .push(QuickSelectPatternRequest::Remove { name });
            Ok(())
        })?;
        quick_select_table.set("remove_pattern", remove_quick_pattern_fn)?;
        wok.set("quick_select", quick_select_table)?;

        // wok.status_bar.{set_left,set_center,set_right,clear,set_refresh_interval}
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
        wok.set("status_bar", status_bar_table)?;

        // wok.setup.{init,doctor,reset,shell_install,shell_rollback}
        let setup_table = self.lua.create_table()?;

        let setup_state = self.state.setup_requests.clone();
        let setup_init_fn = self.lua.create_function(move |_, options: Option<Table>| {
            let overwrite = options
                .as_ref()
                .and_then(|table| table.get::<Option<bool>>("overwrite").ok())
                .flatten()
                .unwrap_or(false);
            setup_state
                .lock()
                .unwrap()
                .push(SetupRequest::Init { overwrite });
            Ok(())
        })?;
        setup_table.set("init", setup_init_fn)?;

        let setup_state = self.state.setup_requests.clone();
        let setup_doctor_fn = self.lua.create_function(move |_, options: Option<Table>| {
            let json = options
                .as_ref()
                .and_then(|table| table.get::<Option<bool>>("json").ok())
                .flatten()
                .unwrap_or(true);
            setup_state
                .lock()
                .unwrap()
                .push(SetupRequest::Doctor { json });
            Ok(())
        })?;
        setup_table.set("doctor", setup_doctor_fn)?;

        let setup_state = self.state.setup_requests.clone();
        let setup_reset_fn = self.lua.create_function(move |_, options: Option<Table>| {
            let scope = options
                .as_ref()
                .and_then(|table| table.get::<Option<String>>("scope").ok())
                .flatten()
                .unwrap_or_else(|| "managed".to_string());
            let yes = options
                .as_ref()
                .and_then(|table| table.get::<Option<bool>>("yes").ok())
                .flatten()
                .unwrap_or(false);
            setup_state
                .lock()
                .unwrap()
                .push(SetupRequest::Reset { scope, yes });
            Ok(())
        })?;
        setup_table.set("reset", setup_reset_fn)?;

        let setup_state = self.state.setup_requests.clone();
        let setup_shell_install_fn =
            self.lua.create_function(move |_, options: Option<Table>| {
                let shell = options
                    .as_ref()
                    .and_then(|table| table.get::<Option<String>>("shell").ok())
                    .flatten();
                let overwrite = options
                    .as_ref()
                    .and_then(|table| table.get::<Option<bool>>("overwrite").ok())
                    .flatten()
                    .unwrap_or(false);
                setup_state
                    .lock()
                    .unwrap()
                    .push(SetupRequest::ShellInstall { shell, overwrite });
                Ok(())
            })?;
        setup_table.set("shell_install", setup_shell_install_fn)?;

        let setup_state = self.state.setup_requests.clone();
        let setup_shell_rollback_fn =
            self.lua.create_function(move |_, options: Option<Table>| {
                let shell = options
                    .as_ref()
                    .and_then(|table| table.get::<Option<String>>("shell").ok())
                    .flatten();
                let yes = options
                    .as_ref()
                    .and_then(|table| table.get::<Option<bool>>("yes").ok())
                    .flatten()
                    .unwrap_or(false);
                setup_state
                    .lock()
                    .unwrap()
                    .push(SetupRequest::ShellRollback { shell, yes });
                Ok(())
            })?;
        setup_table.set("shell_rollback", setup_shell_rollback_fn)?;
        wok.set("setup", setup_table)?;

        // wok.set_timeout(ms, callback)
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
        wok.set("set_timeout", set_timeout_fn)?;

        // wok.set_interval(ms, callback)
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
        wok.set("set_interval", set_interval_fn)?;

        // wok.clear_timer(id)
        let cancelled_timers = self.cancelled_timers.clone();
        let clear_timer_fn = self.lua.create_function(move |_, id: u64| {
            cancelled_timers.borrow_mut().insert(id);
            Ok(())
        })?;
        wok.set("clear_timer", clear_timer_fn)?;

        // wok.run_action(action) — queue a built-in runtime action
        let action_state = self.state.action_requests.clone();
        let run_action_fn = self.lua.create_function(move |_, action: String| {
            action_state.lock().unwrap().push(action);
            Ok(())
        })?;
        wok.set("run_action", run_action_fn.clone())?;
        let action_warnings = self.deprecated_warnings.clone();
        let action_alias_fn = self.lua.create_function(move |_, action: String| {
            warn_deprecated_lua_api_once(&action_warnings, "wok.action", "wok.run_action");
            run_action_fn.call::<()>(action)
        })?;
        wok.set("action", action_alias_fn)?;

        // wok.exec(command) — queue a shell command for the active pane
        let exec_state = self.state.exec_requests.clone();
        let exec_fn = self.lua.create_function(move |_, command: String| {
            exec_state.lock().unwrap().push(command);
            Ok(())
        })?;
        wok.set("exec", exec_fn)?;

        // wok.notify(message) — show status message
        let notify_state = self.state.notifications.clone();
        let notify_fn = self.lua.create_function(move |_, message: String| {
            notify_state.lock().unwrap().push(message);
            Ok(())
        })?;
        wok.set("notify", notify_fn)?;

        // wok.system_notify(message | table) — queue a native desktop notification
        let system_notify_state = self.state.system_notifications.clone();
        let system_notify_fn = self.lua.create_function(move |_, value: Value| {
            let request = parse_system_notification(value)?;
            system_notify_state.lock().unwrap().push(request);
            Ok(())
        })?;
        wok.set("system_notify", system_notify_fn)?;

        // wok.clipboard.copy(text) — push text to system clipboard
        let clipboard_state = self.state.clipboard_copy_requests.clone();
        let clipboard_copy_fn = self.lua.create_function(move |_, text: String| {
            clipboard_state.lock().unwrap().push(text);
            Ok(())
        })?;
        // wok.clipboard.paste() — read from snapshot (caller refreshes each tick)
        let snapshot_state_clip = self.state.runtime_snapshot.clone();
        let clipboard_paste_fn = self.lua.create_function(move |_, ()| {
            let snap = snapshot_state_clip.lock().unwrap();
            let text = snap
                .get("clipboard")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            Ok(text)
        })?;
        let clipboard_table = self.lua.create_table()?;
        clipboard_table.set("copy", clipboard_copy_fn)?;
        clipboard_table.set("paste", clipboard_paste_fn)?;
        wok.set("clipboard", clipboard_table)?;

        // wok.pane.send_input(bytes_or_string) — inject input into the active pane.
        let pty_state = self.state.pty_input_requests.clone();
        let send_input_fn = self.lua.create_function(move |_, value: Value| {
            let bytes: Vec<u8> = match value {
                Value::String(s) => s.as_bytes().to_vec(),
                Value::Table(t) => {
                    let mut buf = Vec::new();
                    for pair in t.pairs::<Integer, Integer>() {
                        let (_, b) = pair?;
                        buf.push(b as u8);
                    }
                    buf
                }
                _ => {
                    return Err(mlua::Error::external(
                        "wok.pane.send_input expects a string or array of integers",
                    ));
                }
            };
            if !bytes.is_empty() {
                pty_state.lock().unwrap().push(bytes);
            }
            Ok(())
        })?;
        // wok.pane.info() — read current pane snapshot
        let snapshot_state_pane = self.state.runtime_snapshot.clone();
        let pane_info_fn = self.lua.create_function(move |lua, ()| {
            let snap = snapshot_state_pane.lock().unwrap().clone();
            let pane = snap.get("pane").cloned().unwrap_or_default();
            lua.to_value(&pane)
        })?;
        let pane_table = self.lua.create_table()?;
        pane_table.set("send_input", send_input_fn)?;
        pane_table.set("info", pane_info_fn)?;
        wok.set("pane_api", pane_table)?;

        // wok.api_version — string constant, baseline for plugin compatibility
        // checks. Bumped per docs/LUA_API_STABILITY.md.
        wok.set("api_version", LUA_API_VERSION)?;

        // wok.fs — sandboxed filesystem ops. Allowed roots: ~/.config/wok/data
        // and ~/.local/share/wok. Paths must canonicalise to a descendant of
        // an allowed root after symlink resolution; everything else errors.
        let fs_table = self.lua.create_table()?;
        let fs_read_fn = self.lua.create_function(move |_, path: String| {
            let abs = match resolve_sandboxed_path(&path) {
                Ok(p) => p,
                Err(error) => return Err(mlua::Error::external(error)),
            };
            std::fs::read_to_string(&abs).map_err(mlua::Error::external)
        })?;
        fs_table.set("read", fs_read_fn)?;
        let fs_write_fn =
            self.lua
                .create_function(move |_, (path, contents): (String, String)| {
                    let abs = match resolve_sandboxed_path(&path) {
                        Ok(p) => p,
                        Err(error) => return Err(mlua::Error::external(error)),
                    };
                    if let Some(parent) = abs.parent() {
                        std::fs::create_dir_all(parent).map_err(mlua::Error::external)?;
                    }
                    std::fs::write(&abs, contents).map_err(mlua::Error::external)?;
                    Ok(())
                })?;
        fs_table.set("write", fs_write_fn)?;
        let fs_exists_fn = self.lua.create_function(move |_, path: String| {
            match resolve_sandboxed_path(&path) {
                Ok(p) => Ok(p.exists()),
                Err(_) => Ok(false), // outside sandbox → caller treats as missing
            }
        })?;
        fs_table.set("exists", fs_exists_fn)?;
        let fs_list_fn = self.lua.create_function(move |lua, path: String| {
            let abs = match resolve_sandboxed_path(&path) {
                Ok(p) => p,
                Err(error) => return Err(mlua::Error::external(error)),
            };
            let mut names: Vec<String> = std::fs::read_dir(&abs)
                .map_err(mlua::Error::external)?
                .filter_map(|e| e.ok())
                .filter_map(|e| e.file_name().into_string().ok())
                .collect();
            names.sort();
            lua.to_value(&names)
        })?;
        fs_table.set("list", fs_list_fn)?;
        wok.set("fs", fs_table)?;

        // wok.window — title, fullscreen, opacity.
        let window_table = self.lua.create_table()?;
        let win_state = self.state.window_requests.clone();
        let window_set_title_fn = {
            let queue = win_state.clone();
            self.lua.create_function(move |_, title: String| {
                queue.lock().unwrap().push(WindowRequest::SetTitle(title));
                Ok(())
            })?
        };
        window_table.set("set_title", window_set_title_fn)?;
        let window_toggle_fs_fn = {
            let queue = win_state.clone();
            self.lua.create_function(move |_, ()| {
                queue.lock().unwrap().push(WindowRequest::ToggleFullscreen);
                Ok(())
            })?
        };
        window_table.set("toggle_fullscreen", window_toggle_fs_fn)?;
        let window_set_opacity_fn = {
            let queue = win_state.clone();
            self.lua.create_function(move |_, value: f32| {
                let clamped = value.clamp(0.0, 1.0);
                queue
                    .lock()
                    .unwrap()
                    .push(WindowRequest::SetOpacity(clamped));
                Ok(())
            })?
        };
        window_table.set("set_opacity", window_set_opacity_fn)?;
        wok.set("window", window_table)?;

        // wok.history — read-only history accessor.
        let history_table = self.lua.create_table()?;
        let snap_for_history = self.state.runtime_snapshot.clone();
        let history_entries_fn = self.lua.create_function(move |lua, ()| {
            let snap = snap_for_history.lock().unwrap().clone();
            let entries = snap
                .get("app")
                .and_then(|a| a.get("history"))
                .cloned()
                .unwrap_or_default();
            lua.to_value(&entries)
        })?;
        history_table.set("entries", history_entries_fn)?;
        let snap_for_search = self.state.runtime_snapshot.clone();
        let history_search_fn = self.lua.create_function(move |lua, query: String| {
            let snap = snap_for_search.lock().unwrap().clone();
            let entries = snap
                .get("app")
                .and_then(|a| a.get("history"))
                .and_then(|h| h.as_array())
                .cloned()
                .unwrap_or_default();
            let needle = query.to_lowercase();
            let filtered: Vec<_> = entries
                .into_iter()
                .filter(|entry| {
                    entry
                        .get("command")
                        .and_then(|c| c.as_str())
                        .is_some_and(|c| c.to_lowercase().contains(&needle))
                })
                .collect();
            lua.to_value(&filtered)
        })?;
        history_table.set("search", history_search_fn)?;
        wok.set("history", history_table)?;

        // wok.tabs — tab manipulation, all routed through action_requests.
        let tabs_table = self.lua.create_table()?;
        let action_state = self.state.action_requests.clone();
        let tabs_new_fn = {
            let queue = action_state.clone();
            self.lua.create_function(move |_, ()| {
                queue.lock().unwrap().push("new_tab".into());
                Ok(())
            })?
        };
        tabs_table.set("new", tabs_new_fn)?;
        let tabs_close_fn = {
            let queue = action_state.clone();
            self.lua.create_function(move |_, ()| {
                queue.lock().unwrap().push("close_tab".into());
                Ok(())
            })?
        };
        tabs_table.set("close", tabs_close_fn)?;
        let tabs_next_fn = {
            let queue = action_state.clone();
            self.lua.create_function(move |_, ()| {
                queue.lock().unwrap().push("next_tab".into());
                Ok(())
            })?
        };
        tabs_table.set("next", tabs_next_fn)?;
        let tabs_prev_fn = {
            let queue = action_state.clone();
            self.lua.create_function(move |_, ()| {
                queue.lock().unwrap().push("prev_tab".into());
                Ok(())
            })?
        };
        tabs_table.set("prev", tabs_prev_fn)?;
        let tabs_switch_fn = {
            let queue = action_state.clone();
            self.lua.create_function(move |_, index: u8| {
                if !(1..=9).contains(&index) {
                    return Err(mlua::Error::external(
                        "wok.tabs.switch expects an index in 1..=9",
                    ));
                }
                queue.lock().unwrap().push(format!("switch_to_tab:{index}"));
                Ok(())
            })?
        };
        tabs_table.set("switch", tabs_switch_fn)?;
        wok.set("tabs", tabs_table)?;

        // wok.panes — split / close / focus, all routed through actions.
        let panes_table = self.lua.create_table()?;
        let push_action = |name: &'static str, queue: Arc<Mutex<Vec<String>>>| {
            self.lua.create_function(move |_, ()| {
                queue.lock().unwrap().push(name.into());
                Ok(())
            })
        };
        let action_state = self.state.action_requests.clone();
        panes_table.set(
            "split_vertical",
            push_action("split_vertical", action_state.clone())?,
        )?;
        panes_table.set(
            "split_horizontal",
            push_action("split_horizontal", action_state.clone())?,
        )?;
        panes_table.set("close", push_action("close_split", action_state.clone())?)?;
        panes_table.set(
            "focus_left",
            push_action("focus_left", action_state.clone())?,
        )?;
        panes_table.set(
            "focus_right",
            push_action("focus_right", action_state.clone())?,
        )?;
        panes_table.set("focus_up", push_action("focus_up", action_state.clone())?)?;
        panes_table.set(
            "focus_down",
            push_action("focus_down", action_state.clone())?,
        )?;
        panes_table.set(
            "new_floating",
            push_action("new_floating_pane", action_state.clone())?,
        )?;
        panes_table.set(
            "toggle_floating",
            push_action("toggle_floating_pane", action_state.clone())?,
        )?;
        wok.set("panes", panes_table)?;

        // wok.blocks.list() — read blocks from snapshot for the active pane.
        let snapshot_state_blocks = self.state.runtime_snapshot.clone();
        let blocks_list_fn = self.lua.create_function(move |lua, ()| {
            let snap = snapshot_state_blocks.lock().unwrap().clone();
            let blocks = snap
                .get("pane")
                .and_then(|p| p.get("blocks"))
                .cloned()
                .unwrap_or_default();
            lua.to_value(&blocks)
        })?;
        let blocks_table = self.lua.create_table()?;
        blocks_table.set("list", blocks_list_fn)?;
        wok.set("blocks", blocks_table)?;

        // wok.git.status({ cwd = optional }) - changed-file snapshot for the
        // active pane repository, backed by the shared git service.
        let git_table = self.lua.create_table()?;
        let snapshot_state_git = self.state.runtime_snapshot.clone();
        let git_status_fn = self.lua.create_function(move |lua, options: Value| {
            let cwd = match options {
                Value::Nil => None,
                Value::Table(table) => table.get::<Option<String>>("cwd")?,
                _ => {
                    return Err(mlua::Error::runtime(
                        "wok.git.status expects nil or an options table",
                    ));
                }
            }
            .or_else(|| {
                snapshot_state_git
                    .lock()
                    .unwrap()
                    .get("pane")
                    .and_then(|pane| pane.get("cwd"))
                    .and_then(|cwd| cwd.as_str())
                    .filter(|cwd| !cwd.is_empty())
                    .map(ToOwned::to_owned)
            });

            let Some(cwd) = cwd else {
                return empty_git_status_table(lua);
            };

            match wok_git::service::load_status(Path::new(&cwd)) {
                Ok(snapshot) => git_status_table(lua, snapshot),
                Err(wok_git::service::GitServiceError::NotGitRepository(_)) => {
                    empty_git_status_table(lua)
                }
                Err(error) => Err(mlua::Error::external(format!(
                    "wok.git.status failed: {error}"
                ))),
            }
        })?;
        git_table.set("status", git_status_fn)?;
        let snapshot_state_git_diff = self.state.runtime_snapshot.clone();
        let git_diff_fn = self.lua.create_function(move |lua, options: Value| {
            let (path, cwd) = match options {
                Value::String(path) => (path.to_string_lossy().to_string(), None),
                Value::Table(table) => {
                    let path = table
                        .get::<Option<String>>("path")?
                        .ok_or_else(|| mlua::Error::runtime("wok.git.diff table requires path"))?;
                    let cwd = table.get::<Option<String>>("cwd")?;
                    (path, cwd)
                }
                _ => {
                    return Err(mlua::Error::runtime(
                        "wok.git.diff expects a path string or options table",
                    ));
                }
            };
            if path.trim().is_empty() {
                return Err(mlua::Error::runtime("wok.git.diff path is empty"));
            }

            let cwd = cwd.or_else(|| {
                snapshot_state_git_diff
                    .lock()
                    .unwrap()
                    .get("pane")
                    .and_then(|pane| pane.get("cwd"))
                    .and_then(|cwd| cwd.as_str())
                    .filter(|cwd| !cwd.is_empty())
                    .map(ToOwned::to_owned)
            });

            let Some(cwd) = cwd else {
                return empty_git_diff_table(lua, path);
            };

            match wok_git::service::load_file_diff(Path::new(&cwd), &path) {
                Ok(diff) => git_diff_table(lua, diff),
                Err(wok_git::service::GitServiceError::NotGitRepository(_)) => {
                    empty_git_diff_table(lua, path)
                }
                Err(error) => Err(mlua::Error::external(format!(
                    "wok.git.diff failed: {error}"
                ))),
            }
        })?;
        git_table.set("diff", git_diff_fn)?;
        let snapshot_state_git_stage = self.state.runtime_snapshot.clone();
        let git_stage_fn = self.lua.create_function(move |lua, options: Value| {
            run_lua_git_mutation(
                lua,
                "stage",
                options,
                false,
                &snapshot_state_git_stage,
                wok_git::service::stage_path,
            )
        })?;
        git_table.set("stage", git_stage_fn)?;
        let snapshot_state_git_unstage = self.state.runtime_snapshot.clone();
        let git_unstage_fn = self.lua.create_function(move |lua, options: Value| {
            run_lua_git_mutation(
                lua,
                "unstage",
                options,
                false,
                &snapshot_state_git_unstage,
                wok_git::service::unstage_path,
            )
        })?;
        git_table.set("unstage", git_unstage_fn)?;
        let snapshot_state_git_discard = self.state.runtime_snapshot.clone();
        let git_discard_fn = self.lua.create_function(move |lua, options: Value| {
            run_lua_git_mutation(
                lua,
                "discard",
                options,
                true,
                &snapshot_state_git_discard,
                wok_git::service::discard_path,
            )
        })?;
        git_table.set("discard", git_discard_fn)?;
        wok.set("git", git_table)?;

        let snapshot_state = self.state.runtime_snapshot.clone();
        wok.set(
            "app",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let app = snapshot.get("app").cloned().unwrap_or_default();
                lua.to_value(&app)
            })?,
        )?;

        let snapshot_state = self.state.runtime_snapshot.clone();
        wok.set(
            "workspace",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let workspace = snapshot.get("workspace").cloned().unwrap_or_default();
                lua.to_value(&workspace)
            })?,
        )?;

        let snapshot_state = self.state.runtime_snapshot.clone();
        wok.set(
            "pane",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let pane = snapshot.get("pane").cloned().unwrap_or_default();
                lua.to_value(&pane)
            })?,
        )?;

        let snapshot_state = self.state.runtime_snapshot.clone();
        wok.set(
            "session",
            self.lua.create_function(move |lua, ()| {
                let snapshot = snapshot_state.lock().unwrap().clone();
                let session = snapshot.get("session").cloned().unwrap_or_default();
                lua.to_value(&session)
            })?,
        )?;

        self.lua.globals().set("wok", wok)?;
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

    /// Drain pending setup lifecycle requests queued from Lua.
    pub fn take_setup_requests(&self) -> Vec<SetupRequest> {
        std::mem::take(&mut *self.state.setup_requests.lock().unwrap())
    }

    /// Drain pending native desktop notification requests queued from Lua.
    pub fn take_system_notifications(&self) -> Vec<SystemNotificationRequest> {
        std::mem::take(&mut *self.state.system_notifications.lock().unwrap())
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

    /// Update the latest runtime snapshot exposed through the `wok.*()` accessors.
    pub fn set_runtime_snapshot(&self, snapshot: JsonValue) {
        *self.state.runtime_snapshot.lock().unwrap() = snapshot;
    }

    /// Drain queued clipboard.copy requests.
    pub fn take_clipboard_copy_requests(&self) -> Vec<String> {
        std::mem::take(&mut *self.state.clipboard_copy_requests.lock().unwrap())
    }

    /// Drain queued PTY input injection requests.
    pub fn take_pty_input_requests(&self) -> Vec<Vec<u8>> {
        std::mem::take(&mut *self.state.pty_input_requests.lock().unwrap())
    }

    /// Drain queued window-level requests.
    pub fn take_window_requests(&self) -> Vec<WindowRequest> {
        std::mem::take(&mut *self.state.window_requests.lock().unwrap())
    }

    /// Update the read-only `wok.config` table with current runtime values.
    ///
    /// # Errors
    ///
    /// Returns a Lua error if the table cannot be updated.
    pub fn set_config_values(&self, values: &JsonValue) -> LuaResult<()> {
        let wok: Table = self.lua.globals().get("wok")?;
        let config: Table = wok.get("config")?;

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

fn active_snapshot_cwd(snapshot_state: &Arc<Mutex<JsonValue>>) -> Option<String> {
    snapshot_state
        .lock()
        .unwrap()
        .get("pane")
        .and_then(|pane| pane.get("cwd"))
        .and_then(|cwd| cwd.as_str())
        .filter(|cwd| !cwd.is_empty())
        .map(ToOwned::to_owned)
}

fn lua_git_path_options(
    options: Value,
    api_name: &str,
) -> LuaResult<(String, Option<String>, bool)> {
    match options {
        Value::String(path) => Ok((path.to_string_lossy().to_string(), None, false)),
        Value::Table(table) => {
            let path = table.get::<Option<String>>("path")?.ok_or_else(|| {
                mlua::Error::runtime(format!("wok.git.{api_name} table requires path"))
            })?;
            let cwd = table.get::<Option<String>>("cwd")?;
            let confirm = table.get::<Option<bool>>("confirm")?.unwrap_or(false);
            Ok((path, cwd, confirm))
        }
        _ => Err(mlua::Error::runtime(format!(
            "wok.git.{api_name} expects a path string or options table"
        ))),
    }
}

fn run_lua_git_mutation(
    lua: &Lua,
    action: &'static str,
    options: Value,
    require_confirm: bool,
    snapshot_state: &Arc<Mutex<JsonValue>>,
    apply: fn(&Path, &str) -> Result<(), wok_git::service::GitServiceError>,
) -> LuaResult<Table> {
    let (path, cwd, confirm) = lua_git_path_options(options, action)?;
    if path.trim().is_empty() {
        return Err(mlua::Error::runtime(format!(
            "wok.git.{action} path is empty"
        )));
    }
    if require_confirm && !confirm {
        return Err(mlua::Error::runtime(format!(
            "wok.git.{action} requires confirm = true"
        )));
    }
    let cwd = cwd
        .or_else(|| active_snapshot_cwd(snapshot_state))
        .ok_or_else(|| mlua::Error::runtime(format!("wok.git.{action} requires cwd")))?;

    apply(Path::new(&cwd), &path).map_err(|error| {
        mlua::Error::external(format!("wok.git.{action} failed for {path}: {error}"))
    })?;
    let snapshot = wok_git::service::load_status(Path::new(&cwd)).map_err(|error| {
        mlua::Error::external(format!(
            "wok.git.{action} changed {path} but refresh failed: {error}"
        ))
    })?;
    git_mutation_result_table(lua, action, path, snapshot)
}

fn empty_git_status_table(lua: &Lua) -> LuaResult<Table> {
    let table = lua.create_table()?;
    table.set("is_git_repo", false)?;
    table.set("clean", true)?;
    table.set("files", lua.create_table()?)?;
    Ok(table)
}

fn git_status_table(lua: &Lua, snapshot: wok_git::service::GitStatusSnapshot) -> LuaResult<Table> {
    let clean = snapshot.is_clean();
    let table = lua.create_table()?;
    table.set("is_git_repo", true)?;
    table.set("repo_root", snapshot.worktree_root.display().to_string())?;
    table.set("branch", snapshot.branch)?;
    table.set("clean", clean)?;

    let files = lua.create_table()?;
    for (index, file) in snapshot.files.into_iter().enumerate() {
        let status_text = file.status_text().to_string();
        let staged_status_text = file.staged_status_text().to_string();
        let unstaged_status_text = file.unstaged_status_text().to_string();
        let is_staged = file.is_staged();
        let is_unstaged = file.is_unstaged();

        let row = lua.create_table()?;
        row.set("path", file.path)?;
        row.set("old_path", file.old_path)?;
        row.set("index_status", file.index_status.to_string())?;
        row.set("worktree_status", file.worktree_status.to_string())?;
        row.set("status_text", status_text)?;
        row.set("staged_status_text", staged_status_text)?;
        row.set("unstaged_status_text", unstaged_status_text)?;
        row.set("is_staged", is_staged)?;
        row.set("is_unstaged", is_unstaged)?;
        row.set("additions", file.additions)?;
        row.set("deletions", file.deletions)?;
        row.set("is_binary", file.is_binary)?;
        files.set(index + 1, row)?;
    }
    table.set("files", files)?;

    Ok(table)
}

fn git_mutation_result_table(
    lua: &Lua,
    action: &str,
    path: String,
    snapshot: wok_git::service::GitStatusSnapshot,
) -> LuaResult<Table> {
    let table = lua.create_table()?;
    table.set("ok", true)?;
    table.set("action", action)?;
    table.set("path", path)?;
    table.set("status", git_status_table(lua, snapshot)?)?;
    Ok(table)
}

fn empty_git_diff_table(lua: &Lua, path: String) -> LuaResult<Table> {
    let table = lua.create_table()?;
    table.set("is_git_repo", false)?;
    table.set("path", path)?;
    table.set("additions", 0)?;
    table.set("deletions", 0)?;
    table.set("rows", lua.create_table()?)?;
    Ok(table)
}

fn git_diff_table(lua: &Lua, diff: wok_git::service::GitFileDiff) -> LuaResult<Table> {
    let table = lua.create_table()?;
    table.set("is_git_repo", true)?;
    table.set("repo_root", diff.worktree_root.display().to_string())?;
    table.set("branch", diff.branch)?;
    table.set("path", diff.path)?;
    table.set("additions", diff.additions)?;
    table.set("deletions", diff.deletions)?;

    let rows = lua.create_table()?;
    for (index, row) in diff.rows.into_iter().enumerate() {
        let item = lua.create_table()?;
        item.set("kind", git_diff_kind_name(row.kind))?;
        item.set("old_line_number", row.old_line_number)?;
        item.set("new_line_number", row.new_line_number)?;
        item.set("old_text", row.old_text)?;
        item.set("new_text", row.new_text)?;
        item.set("text", row.text)?;
        rows.set(index + 1, item)?;
    }
    table.set("rows", rows)?;

    Ok(table)
}

fn git_diff_kind_name(kind: wok_git::diff::DiffRowKind) -> &'static str {
    match kind {
        wok_git::diff::DiffRowKind::Hunk => "hunk",
        wok_git::diff::DiffRowKind::Context => "context",
        wok_git::diff::DiffRowKind::Addition => "addition",
        wok_git::diff::DiffRowKind::Deletion => "deletion",
        wok_git::diff::DiffRowKind::Collapsed => "collapsed",
    }
}

fn parse_system_notification(value: Value) -> LuaResult<SystemNotificationRequest> {
    match value {
        Value::String(message) => Ok(SystemNotificationRequest {
            title: "Wok".to_string(),
            message: message.to_string_lossy().to_string(),
            subtitle: None,
        }),
        Value::Table(table) => {
            let title = table
                .get::<Option<String>>("title")?
                .filter(|title| !title.trim().is_empty())
                .unwrap_or_else(|| "Wok".to_string());
            let message = table
                .get::<Option<String>>("message")?
                .or(table.get::<Option<String>>("body")?)
                .ok_or_else(|| mlua::Error::runtime("system_notify table requires message"))?;
            let subtitle = table.get::<Option<String>>("subtitle")?;
            Ok(SystemNotificationRequest {
                title,
                message,
                subtitle,
            })
        }
        _ => Err(mlua::Error::runtime(
            "system_notify expects a string or table",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn unique_temp_dir(name: &str) -> PathBuf {
        let stamp = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock should be after unix epoch")
            .as_nanos();
        std::env::temp_dir().join(format!("wok-lua-{name}-{stamp}"))
    }

    fn run_git(cwd: &Path, args: &[&str]) {
        let output = Command::new("git")
            .args(args)
            .current_dir(cwd)
            .output()
            .expect("git should run");
        assert!(
            output.status.success(),
            "git {:?} failed: {}",
            args,
            String::from_utf8_lossy(&output.stderr)
        );
    }

    #[test]
    fn api_version_is_exposed_to_lua() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec("wok.notify(wok.api_version)")
            .expect("exec should succeed");
        let messages = runtime.take_notifications();
        assert_eq!(messages, vec![LUA_API_VERSION.to_string()]);
    }

    #[test]
    fn sandbox_rejects_paths_outside_roots() {
        // /tmp is never inside the sandbox roots.
        let err = resolve_sandboxed_path("/tmp/does/not/matter").unwrap_err();
        assert!(err.contains("outside"), "got: {err}");
    }

    #[test]
    fn sandbox_resolves_relative_under_data_root() {
        // Relative path lands under ~/.config/wok/data/ — accepted even if the
        // file does not yet exist (write path).
        if std::env::var_os("HOME").is_none() {
            return; // skip on environments without HOME
        }
        let result = resolve_sandboxed_path("plugin-state.json");
        assert!(result.is_ok(), "got: {result:?}");
        let path = result.unwrap();
        assert!(path.ends_with("plugin-state.json"));
    }

    #[test]
    fn sandbox_rejects_empty_path() {
        let err = resolve_sandboxed_path("").unwrap_err();
        assert!(err.contains("empty"), "got: {err}");
    }

    #[test]
    fn test_trigger_hook_passes_structured_payload() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                wok.on("demo", function(event)
                    wok.notify(event.message .. ":" .. tostring(event.code))
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
            .exec(r#"wok.run_action("new_tab")"#)
            .expect("run_action should work");

        assert_eq!(runtime.take_action_requests(), vec!["new_tab".to_string()]);
    }

    #[test]
    fn deprecated_aliases_warn_once_and_still_work() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                wok.action("new_tab")
                wok.action("close_tab")
                wok.keymap("terminal", "ctrl+t", "new_tab")
                wok.keymap("terminal", "ctrl+w", "close_tab")
                "#,
            )
            .expect("deprecated aliases should still work");

        assert_eq!(
            runtime.take_action_requests(),
            vec!["new_tab".to_string(), "close_tab".to_string()]
        );
        assert_eq!(runtime.state.keybindings.lock().unwrap().len(), 2);
        let warnings = runtime.deprecated_warnings.borrow();
        assert!(warnings.contains("wok.action"));
        assert!(warnings.contains("wok.keymap"));
        assert_eq!(warnings.len(), 2);
    }

    #[test]
    fn test_system_notify_queues_request() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                wok.system_notify({
                    title = "Agent done",
                    subtitle = "tab 1",
                    message = "codex finished"
                })
                "#,
            )
            .expect("system_notify should work");

        assert_eq!(
            runtime.take_system_notifications(),
            vec![SystemNotificationRequest {
                title: "Agent done".to_string(),
                message: "codex finished".to_string(),
                subtitle: Some("tab 1".to_string()),
            }]
        );
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
                local workspace = wok.workspace()
                local pane = wok.pane()
                wok.notify(tostring(workspace.tab_count) .. ":" .. pane.cwd)
            "#,
            )
            .expect("snapshot accessors should work");

        assert_eq!(
            runtime.take_notifications(),
            vec!["3:/tmp/demo".to_string()]
        );
    }

    #[test]
    fn test_git_status_uses_active_pane_cwd() {
        let repo = unique_temp_dir("git-status");
        fs::create_dir_all(&repo).expect("repo dir should be created");
        run_git(&repo, &["init"]);
        fs::write(repo.join("new.txt"), "hello\n").expect("file should be written");

        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime.set_runtime_snapshot(serde_json::json!({
            "pane": { "cwd": repo },
        }));
        runtime
            .exec(
                r#"
                local status = wok.git.status()
                wok.notify(
                    tostring(status.is_git_repo) .. ":" ..
                    tostring(status.clean) .. ":" ..
                    tostring(#status.files) .. ":" ..
                    status.files[1].path .. ":" ..
                    status.files[1].unstaged_status_text
                )
            "#,
            )
            .expect("git status should be readable from lua");

        assert_eq!(
            runtime.take_notifications(),
            vec!["true:false:1:new.txt:U".to_string()]
        );
        fs::remove_dir_all(repo).ok();
    }

    #[test]
    fn test_git_status_returns_empty_snapshot_outside_repo() {
        let dir = unique_temp_dir("non-repo");
        fs::create_dir_all(&dir).expect("temp dir should be created");

        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(&format!(
                r#"
                local status = wok.git.status({{ cwd = "{}" }})
                wok.notify(tostring(status.is_git_repo) .. ":" .. tostring(status.clean) .. ":" .. tostring(#status.files))
                "#,
                dir.display()
            ))
            .expect("non-repo status should not error");

        assert_eq!(
            runtime.take_notifications(),
            vec!["false:true:0".to_string()]
        );
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn test_git_diff_uses_active_pane_cwd() {
        let repo = unique_temp_dir("git-diff");
        fs::create_dir_all(&repo).expect("repo dir should be created");
        run_git(&repo, &["init"]);
        run_git(&repo, &["config", "user.email", "wok@example.test"]);
        run_git(&repo, &["config", "user.name", "Wok Test"]);
        fs::write(repo.join("tracked.txt"), "old\nsame\n").expect("file should be written");
        run_git(&repo, &["add", "tracked.txt"]);
        run_git(&repo, &["commit", "-m", "initial"]);
        fs::write(repo.join("tracked.txt"), "new\nsame\n").expect("file should be modified");

        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime.set_runtime_snapshot(serde_json::json!({
            "pane": { "cwd": repo },
        }));
        runtime
            .exec(
                r#"
                local diff = wok.git.diff("tracked.txt")
                wok.notify(
                    tostring(diff.is_git_repo) .. ":" ..
                    diff.path .. ":" ..
                    tostring(diff.additions) .. ":" ..
                    tostring(diff.deletions) .. ":" ..
                    diff.rows[2].kind .. ":" ..
                    diff.rows[3].kind
                )
            "#,
            )
            .expect("git diff should be readable from lua");

        assert_eq!(
            runtime.take_notifications(),
            vec!["true:tracked.txt:1:1:deletion:addition".to_string()]
        );
        fs::remove_dir_all(repo).ok();
    }

    #[test]
    fn test_git_diff_returns_empty_snapshot_outside_repo() {
        let dir = unique_temp_dir("diff-non-repo");
        fs::create_dir_all(&dir).expect("temp dir should be created");

        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(&format!(
                r#"
                local diff = wok.git.diff({{ cwd = "{}", path = "x.txt" }})
                wok.notify(tostring(diff.is_git_repo) .. ":" .. diff.path .. ":" .. tostring(#diff.rows))
                "#,
                dir.display()
            ))
            .expect("non-repo diff should not error");

        assert_eq!(
            runtime.take_notifications(),
            vec!["false:x.txt:0".to_string()]
        );
        fs::remove_dir_all(dir).ok();
    }

    #[test]
    fn test_git_stage_and_unstage_mutations_return_refreshed_status() {
        let repo = unique_temp_dir("git-stage-unstage");
        fs::create_dir_all(&repo).expect("repo dir should be created");
        run_git(&repo, &["init"]);
        run_git(&repo, &["config", "user.email", "wok@example.test"]);
        run_git(&repo, &["config", "user.name", "Wok Test"]);
        fs::write(repo.join("tracked.txt"), "old\n").expect("file should be written");
        run_git(&repo, &["add", "tracked.txt"]);
        run_git(&repo, &["commit", "-m", "initial"]);
        fs::write(repo.join("tracked.txt"), "new\n").expect("file should be modified");

        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime.set_runtime_snapshot(serde_json::json!({
            "pane": { "cwd": repo },
        }));
        runtime
            .exec(
                r#"
                local staged = wok.git.stage("tracked.txt")
                local unstaged = wok.git.unstage("tracked.txt")
                wok.notify(
                    staged.action .. ":" ..
                    tostring(staged.status.files[1].is_staged) .. ":" ..
                    unstaged.action .. ":" ..
                    tostring(unstaged.status.files[1].is_unstaged)
                )
            "#,
            )
            .expect("git mutations should be callable from lua");

        assert_eq!(
            runtime.take_notifications(),
            vec!["stage:true:unstage:true".to_string()]
        );
        fs::remove_dir_all(repo).ok();
    }

    #[test]
    fn test_git_discard_requires_confirm_true() {
        let repo = unique_temp_dir("git-discard-confirm");
        fs::create_dir_all(&repo).expect("repo dir should be created");
        run_git(&repo, &["init"]);
        fs::write(repo.join("scratch.txt"), "scratch\n").expect("file should be written");

        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(&format!(
                r#"
                local ok, err = pcall(function()
                    wok.git.discard({{ cwd = "{}", path = "scratch.txt" }})
                end)
                wok.notify(tostring(ok) .. ":" .. tostring(err):match("confirm = true"))
                local discarded = wok.git.discard({{ cwd = "{}", path = "scratch.txt", confirm = true }})
                wok.notify(discarded.action .. ":" .. tostring(discarded.status.clean))
                "#,
                repo.display(),
                repo.display()
            ))
            .expect("discard confirmation should be enforced");

        assert!(!repo.join("scratch.txt").exists());
        assert_eq!(
            runtime.take_notifications(),
            vec![
                "false:confirm = true".to_string(),
                "discard:true".to_string(),
            ]
        );
        fs::remove_dir_all(repo).ok();
    }

    #[test]
    fn test_theme_requests_are_queued() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r##"
                wok.theme.set({ background = "#112233", opacity = 0.6 })
                wok.theme.load("paper")
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
                wok.notify(wok.config.font_family .. ":" .. tostring(wok.config.font_size) .. ":" .. wok.config.shell)
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
                wok.status_bar.set_right({{ text = " K8s: prod ", fg = "#00ff00", bold = true }})
                wok.status_bar.set_left({{ text = " left " }})
                wok.status_bar.set_refresh_interval(2500)
                "##,
            )
            .expect("status bar requests should queue");

        let requests = runtime.take_status_bar_requests();
        assert!(matches!(requests[0], StatusBarRequest::SetRight(_)));
        assert!(matches!(requests[1], StatusBarRequest::SetLeft(_)));
        assert_eq!(requests[2], StatusBarRequest::SetRefreshInterval(2500));
    }

    #[test]
    fn test_setup_requests_are_queued() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                wok.setup.init({ overwrite = true })
                wok.setup.doctor({ json = true })
                wok.setup.reset({ scope = "all", yes = true })
                wok.setup.shell_install({ shell = "zsh", overwrite = true })
                wok.setup.shell_rollback({ shell = "zsh", yes = true })
            "#,
            )
            .expect("setup requests should queue");

        let requests = runtime.take_setup_requests();
        assert_eq!(requests.len(), 5);
        assert_eq!(requests[0], SetupRequest::Init { overwrite: true });
        assert_eq!(requests[1], SetupRequest::Doctor { json: true });
        assert_eq!(
            requests[2],
            SetupRequest::Reset {
                scope: "all".to_string(),
                yes: true,
            }
        );
        assert_eq!(
            requests[3],
            SetupRequest::ShellInstall {
                shell: Some("zsh".to_string()),
                overwrite: true,
            }
        );
        assert_eq!(
            requests[4],
            SetupRequest::ShellRollback {
                shell: Some("zsh".to_string()),
                yes: true,
            }
        );
    }

    #[test]
    fn test_set_timeout_fires() {
        let mut runtime = LuaRuntime::new().expect("lua runtime");
        runtime.init(&std::env::temp_dir()).expect("lua init");
        runtime
            .exec(
                r#"
                wok.set_timeout(1, function()
                    wok.notify("timeout")
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
                local id = wok.set_interval(1, function()
                    wok.notify("tick")
                end)
                wok.clear_timer(id)
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
                    wok.set_timeout(1, function()
                        wok.notify("fire")
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
