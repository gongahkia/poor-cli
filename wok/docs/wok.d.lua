---@meta
--
-- LuaCATS type definitions for the Wok plugin API.
--
-- Drop this file into your editor's Lua-language-server workspace (or place
-- it at `~/.config/wok/types/wok.d.lua` and add a `.luarc.json` with
-- `{"workspace": {"library": ["~/.config/wok/types"]}}`) and you'll get
-- autocomplete, type checking, and hover docs over the entire wok.* API.
--
-- See docs/LUA_SCRIPTING.md for prose docs and docs/examples/powerful.lua
-- for a working init.lua that uses every namespace.

---@class wok.Config
---@field shell string                       Shell name ("bash"/"zsh"/"fish"/"powershell"/"wsl:<distro>")
---@field font_family string
---@field font_size number
---@field scrollback_lines integer
---@field input_position "top" | "bottom"
---@field theme_path string?
---@field window_opacity number              0.0–1.0
---@field tab_bar_orientation "horizontal" | "vertical"
---@field tab_bar_side "top" | "bottom" | "left" | "right"
---@field status_bar_side "top" | "bottom" | "left" | "right"
---@field recent_keys_visible boolean
---@field recent_keys_position string
---@field close_on_shell_exit boolean
---@field restore_session boolean
---@field debug_overlay boolean
---@field trigger_count integer
---@field workflow_count integer

---@class wok.AppSnapshot
---@field status_message string?
---@field cursor_visible boolean
---@field uptime_ms integer
---@field history wok.HistoryEntry[]         Last 200 entries

---@class wok.WorkspaceSnapshot
---@field active_tab_index integer
---@field active_pane_id integer?
---@field tab_count integer
---@field pane_count integer

---@class wok.PaneSnapshot
---@field pane_id integer?
---@field title string?
---@field shell string?
---@field cwd string
---@field cols integer?
---@field rows integer?
---@field follow_output boolean?
---@field display_offset integer?
---@field search_query string?
---@field selected_block_id integer?
---@field blocks wok.Block[]                 Last 100 blocks of this pane

---@class wok.SessionSnapshot
---@field restore_enabled boolean
---@field autosave_path string
---@field window_size integer[]              [width, height]
---@field window_position integer[]          [x, y]

---@class wok.HistoryEntry
---@field command string
---@field cwd string?
---@field started_at_ms integer
---@field completed_at_ms integer?
---@field exit_code integer?
---@field duration_ms integer?

---@class wok.Block
---@field id integer
---@field command string
---@field cwd string
---@field exit_code integer?
---@field duration_ms integer?
---@field is_bookmarked boolean
---@field git_branch string?

---@class wok.PanePayload                    Common base of pane-related hook payloads
---@field pane_id integer
---@field tab_index integer
---@field tab_id integer?
---@field tab_title string?
---@field shell string?
---@field title string?
---@field cwd string
---@field is_active_pane boolean

---@class wok.AppEventPayload
---@field active_tab_index integer
---@field active_tab_id integer?
---@field tab_count integer
---@field pane_count integer
---@field active_pane_id integer?

---@class wok.BlockFinishedPayload : wok.PanePayload
---@field block_id integer
---@field command string
---@field exit_code integer?
---@field duration_ms integer?
---@field output_start_row integer
---@field output_end_row integer

---@class wok.CwdChangedPayload : wok.PanePayload
---@field path string

---@class wok.CommandSubmittedPayload : wok.PanePayload
---@field command string

---@class wok.PaneExitedPayload : wok.PanePayload
---@field exit_code integer?

---@class wok.TabDonePayload
---@field tab_index integer
---@field tab_id integer?
---@field tab_title string?
---@field pane_ids integer[]
---@field pane_count integer
---@field is_active_tab boolean

-- `tab_opened` and `pane_opened` extend the standard pane payload. Floating
-- panes report `direction = "floating"`.
---@class wok.TabOpenedPayload : wok.PanePayload

---@class wok.PaneOpenedPayload : wok.PanePayload
---@field direction "vertical" | "horizontal" | "floating"

---@class wok.SystemNotification
---@field title string?
---@field subtitle string?
---@field message string

---@class wok.StatusSegment
---@field text string
---@field color string?                      Hex like "#89b4fa"
---@field background string?
---@field bold boolean?
---@field italic boolean?

---@class wok.WorkflowParam
---@field name string
---@field description string?
---@field required boolean?
---@field default string?

---@class wok.Workflow
---@field name string
---@field description string?
---@field parameters wok.WorkflowParam[]?
---@field command string

---@class wok.SetupOptions
---@field overwrite boolean?
---@field json boolean?
---@field scope "managed" | "state" | "all" | nil
---@field shell "auto" | "bash" | "zsh" | "fish" | nil
---@field yes boolean?

---@class wok.Theme
---@field name string?
---@field font_family string?
---@field font_size number?
---@field background_image string?

---@class wok.ThemeSet
---@field background string?
---@field foreground string?
---@field cursor string?
---@field selection string?
---@field bell string?
---@field [string] string?                   Other named theme colors

-- Lifecycle event names accepted by `wok.on`. Keep in sync with
-- docs/LUA_SCRIPTING.md and tests/lua_hook_payloads.rs.
---@alias wok.HookName
---| "app_start"
---| "app_exit"
---| "tab_opened"
---| "pane_opened"
---| "command_submitted"
---| "block_finished"
---| "pane_exited"
---| "tab_done"
---| "cwd_changed"

-- Modes accepted by `wok.bind_key`.
---@alias wok.KeyMode
---| "terminal"
---| "normal"
---| "input"
---| "block"
---| "search"

---@class wok                                Top-level table; injected as the `wok` global
---@field config wok.Config
local wok = {}

-- =====================================================================
--  Keybindings + commands
-- =====================================================================

---Register a Lua-side keybinding.
---@param mode wok.KeyMode
---@param key string                         e.g. "ctrl+t" or "cmd+shift+d"
---@param action string                      Built-in action id, alias, or "switch_to_tab:N" / "save_session:NAME"
function wok.bind_key(mode, key, action) end

---Alias for `wok.bind_key`.
---@param mode wok.KeyMode
---@param key string
---@param action string
function wok.keymap(mode, key, action) end

---Register an action alias usable from `wok.bind_key` and the command palette.
---@param name string
---@param action string|function             Built-in action id or a Lua function
function wok.register_command(name, action) end

-- =====================================================================
--  Lifecycle hooks
-- =====================================================================

---Register a hook for a lifecycle event.
---@param event "app_start"          @callback receives wok.AppEventPayload
---@param fn fun(event: wok.AppEventPayload)
---@overload fun(event: "app_exit", fn: fun(event: wok.AppEventPayload))
---@overload fun(event: "block_finished", fn: fun(event: wok.BlockFinishedPayload))
---@overload fun(event: "cwd_changed", fn: fun(event: wok.CwdChangedPayload))
---@overload fun(event: "command_submitted", fn: fun(event: wok.CommandSubmittedPayload))
---@overload fun(event: "pane_exited", fn: fun(event: wok.PaneExitedPayload))
---@overload fun(event: "tab_done", fn: fun(event: wok.TabDonePayload))
---@overload fun(event: "tab_opened", fn: fun(event: wok.TabOpenedPayload))
---@overload fun(event: "pane_opened", fn: fun(event: wok.PaneOpenedPayload))
function wok.on(event, fn) end

-- =====================================================================
--  Actions, exec, notifications
-- =====================================================================

---Queue a built-in action through the runtime action bus.
---@param action string
function wok.run_action(action) end

---Alias for `wok.run_action`.
---@param action string
function wok.action(action) end

---Queue a shell command in the focused pane.
---@param command string
function wok.exec(command) end

---Show an in-app status bar message.
---@param message string
function wok.notify(message) end

---Show a native desktop notification.
---@param notification string|wok.SystemNotification
function wok.system_notify(notification) end

-- =====================================================================
--  Runtime state snapshots
-- =====================================================================

---Return the current `app` snapshot.
---@return wok.AppSnapshot
function wok.app() end

---Return the current `workspace` snapshot.
---@return wok.WorkspaceSnapshot
function wok.workspace() end

---Return the active pane snapshot.
---@return wok.PaneSnapshot
function wok.pane() end

---Return the current `session` snapshot.
---@return wok.SessionSnapshot
function wok.session() end

-- =====================================================================
--  History
-- =====================================================================

wok.history = {}

---Return up to the last 200 global history entries.
---@return wok.HistoryEntry[]
function wok.history.entries() end

---Case-insensitive substring search over history commands.
---@param query string
---@return wok.HistoryEntry[]
function wok.history.search(query) end

-- =====================================================================
--  Blocks
-- =====================================================================

wok.blocks = {}

---Last 100 blocks of the active pane.
---@return wok.Block[]
function wok.blocks.list() end

-- =====================================================================
--  Tabs
-- =====================================================================

wok.tabs = {}

---Open a new tab.
function wok.tabs.new() end

---Close the current tab.
function wok.tabs.close() end

---Switch to the next tab.
function wok.tabs.next() end

---Switch to the previous tab.
function wok.tabs.prev() end

---Switch to tab `index` (1..=9).
---@param index integer
function wok.tabs.switch(index) end

-- =====================================================================
--  Panes
-- =====================================================================

wok.panes = {}

---Split the focused pane vertically.
function wok.panes.split_vertical() end

---Split the focused pane horizontally.
function wok.panes.split_horizontal() end

---Close the focused split pane.
function wok.panes.close() end

function wok.panes.focus_left() end
function wok.panes.focus_right() end
function wok.panes.focus_up() end
function wok.panes.focus_down() end

---Open a new floating pane.
function wok.panes.new_floating() end

---Show or hide all floating panes.
function wok.panes.toggle_floating() end

-- =====================================================================
--  Pane I/O (separate namespace to avoid clashing with `wok.pane()`)
-- =====================================================================

wok.pane_api = {}

---Inject input into the active pane's PTY.
---@param data string|integer[]              UTF-8 string or array of bytes
function wok.pane_api.send_input(data) end

---Read the active pane snapshot (same data as `wok.pane()`).
---@return wok.PaneSnapshot
function wok.pane_api.info() end

-- =====================================================================
--  Window
-- =====================================================================

wok.window = {}

---Set the OS window title.
---@param title string
function wok.window.set_title(title) end

---Toggle borderless fullscreen.
function wok.window.toggle_fullscreen() end

---Set the window opacity (clamped to 0.0–1.0).
---@param value number
function wok.window.set_opacity(value) end

-- =====================================================================
--  Clipboard
-- =====================================================================

wok.clipboard = {}

---Copy `text` to the system clipboard.
---@param text string
function wok.clipboard.copy(text) end

---Read the latest clipboard snapshot.
---@return string
function wok.clipboard.paste() end

-- =====================================================================
--  Sandboxed filesystem
-- =====================================================================

-- All paths must descend from one of the sandbox roots:
--   ~/.config/wok/data/      (relative paths land here)
--   ~/.local/share/wok/

wok.fs = {}

---Read the contents of a file inside the sandbox.
---@param path string
---@return string
function wok.fs.read(path) end

---Write `contents` to a file inside the sandbox. Creates parents as needed.
---@param path string
---@param contents string
function wok.fs.write(path, contents) end

---Whether `path` exists (returns false for paths outside the sandbox).
---@param path string
---@return boolean
function wok.fs.exists(path) end

---List the immediate children of a directory inside the sandbox.
---@param path string
---@return string[]
function wok.fs.list(path) end

-- =====================================================================
--  Triggers, workflows, quick-select
-- =====================================================================

---Register a regex trigger that runs when a block finishes.
---@param name string
---@param pattern string
---@param actions string[]                   e.g. {"highlight_red", "system_notify:msg"}
function wok.add_trigger(name, pattern, actions) end

---Remove a trigger by name.
---@param name string
function wok.remove_trigger(name) end

---Register a parameterised workflow.
---@param workflow wok.Workflow
function wok.register_workflow(workflow) end

---Return the current set of registered workflows.
---@return wok.Workflow[]
function wok.workflows() end

wok.quick_select = {}

---Add a custom regex pattern for the quick-select label overlay.
---@param name string
---@param pattern string
function wok.quick_select.add_pattern(name, pattern) end

---Remove a custom quick-select pattern by name.
---@param name string
function wok.quick_select.remove_pattern(name) end

-- =====================================================================
--  Status bar
-- =====================================================================

wok.status_bar = {}

---Replace the left segment list.
---@param segments wok.StatusSegment[]
function wok.status_bar.set_left(segments) end

---Replace the center segment list.
---@param segments wok.StatusSegment[]
function wok.status_bar.set_center(segments) end

---Replace the right segment list.
---@param segments wok.StatusSegment[]
function wok.status_bar.set_right(segments) end

---Clear all custom status-bar segments.
function wok.status_bar.clear() end

---Set the status-bar refresh interval in milliseconds.
---@param ms integer
function wok.status_bar.set_refresh_interval(ms) end

-- =====================================================================
--  Themes
-- =====================================================================

wok.theme = {}

---Apply a live theme override map.
---@param overrides wok.ThemeSet
function wok.theme.set(overrides) end

---Load a theme by name (resolved under ~/.config/wok/themes) or absolute path.
---@param name_or_path string
function wok.theme.load(name_or_path) end

-- =====================================================================
--  Setup operations (programmatic equivalents of `wok` CLI subcommands)
-- =====================================================================

wok.setup = {}

---Run `wok init` from inside the running app.
---@param opts wok.SetupOptions?
function wok.setup.init(opts) end

---Run `wok doctor`.
---@param opts wok.SetupOptions?
function wok.setup.doctor(opts) end

---Run `wok reset`. Requires `yes = true`.
---@param opts wok.SetupOptions
function wok.setup.reset(opts) end

---Install shell integration. `shell` defaults to `"auto"`.
---@param opts wok.SetupOptions?
function wok.setup.shell_install(opts) end

---Roll back shell integration. Requires `yes = true`.
---@param opts wok.SetupOptions
function wok.setup.shell_rollback(opts) end

-- =====================================================================
--  Timers
-- =====================================================================

---Schedule `fn` to run once after `ms` milliseconds. Returns a timer id.
---@param ms integer
---@param fn fun()
---@return integer
function wok.set_timeout(ms, fn) end

---Schedule `fn` to run every `ms` milliseconds. Returns a timer id.
---@param ms integer
---@param fn fun()
---@return integer
function wok.set_interval(ms, fn) end

---Cancel a previously scheduled timer.
---@param id integer
function wok.clear_timer(id) end

return wok
