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
--
-- Every function, class, and event below is annotated with `---@since X.Y.Z`
-- per docs/LUA_API_STABILITY.md. Editors using lua-language-server surface
-- this on hover so plugin authors can pin a minimum API version.

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
---@since 1.0.0

---@class wok.AppSnapshot
---@field status_message string?
---@field cursor_visible boolean
---@field uptime_ms integer
---@field history wok.HistoryEntry[]         Last 200 entries
---@since 1.0.0

---@class wok.WorkspaceSnapshot
---@field active_tab_index integer
---@field active_pane_id integer?
---@field tab_count integer
---@field pane_count integer
---@since 1.0.0

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
---@since 1.0.0

---@class wok.SessionSnapshot
---@field restore_enabled boolean
---@field autosave_path string
---@field window_size integer[]              [width, height]
---@field window_position integer[]          [x, y]
---@since 1.0.0

---@class wok.HistoryEntry
---@field command string
---@field cwd string?
---@field started_at_ms integer
---@field completed_at_ms integer?
---@field exit_code integer?
---@field duration_ms integer?
---@since 1.0.0

---@class wok.Block
---@field id integer
---@field command string
---@field cwd string
---@field exit_code integer?
---@field duration_ms integer?
---@field is_bookmarked boolean
---@field git_branch string?
---@since 1.0.0

---@class wok.PanePayload                    Common base of pane-related hook payloads
---@field pane_id integer
---@field tab_index integer
---@field tab_id integer?
---@field tab_title string?
---@field shell string?
---@field title string?
---@field cwd string
---@field is_active_pane boolean
---@since 1.0.0

---@class wok.AppEventPayload
---@field active_tab_index integer
---@field active_tab_id integer?
---@field tab_count integer
---@field pane_count integer
---@field active_pane_id integer?
---@since 1.0.0

---@class wok.BlockFinishedPayload : wok.PanePayload
---@field block_id integer
---@field command string
---@field exit_code integer?
---@field duration_ms integer?
---@field output_start_row integer
---@field output_end_row integer
---@since 1.0.0

---@class wok.CwdChangedPayload : wok.PanePayload
---@field path string
---@since 1.0.0

---@class wok.CommandSubmittedPayload : wok.PanePayload
---@field command string
---@since 1.0.0

---@class wok.PaneExitedPayload : wok.PanePayload
---@field exit_code integer?
---@since 1.0.0

---@class wok.TabDonePayload
---@field tab_index integer
---@field tab_id integer?
---@field tab_title string?
---@field pane_ids integer[]
---@field pane_count integer
---@field is_active_tab boolean
---@since 1.0.0

-- `tab_opened` and `pane_opened` extend the standard pane payload. Floating
-- panes report `direction = "floating"`.
---@class wok.TabOpenedPayload : wok.PanePayload
---@since 1.0.0

---@class wok.PaneOpenedPayload : wok.PanePayload
---@field direction "vertical" | "horizontal" | "floating"
---@since 1.0.0

---@class wok.SystemNotification
---@field title string?
---@field subtitle string?
---@field message string
---@since 1.0.0

---@class wok.StatusSegment
---@field text string
---@field color string?                      Hex like "#89b4fa"
---@field background string?
---@field bold boolean?
---@field italic boolean?
---@since 1.0.0

---@class wok.WorkflowParam
---@field name string
---@field description string?
---@field required boolean?
---@field default string?
---@since 1.0.0

---@class wok.Workflow
---@field name string
---@field description string?
---@field parameters wok.WorkflowParam[]?
---@field command string
---@since 1.0.0

---@class wok.SetupOptions
---@field overwrite boolean?
---@field json boolean?
---@field scope "managed" | "state" | "all" | nil
---@field shell "auto" | "bash" | "zsh" | "fish" | nil
---@field yes boolean?
---@since 1.0.0

---@class wok.Theme
---@field name string?
---@field font_family string?
---@field font_size number?
---@field background_image string?
---@since 1.0.0

---@class wok.ThemeSet
---@field background string?
---@field foreground string?
---@field cursor string?
---@field selection string?
---@field bell string?
---@field [string] string?                   Other named theme colors
---@since 1.0.0

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
---@field api_version string                  Semantic-version string of the Lua API ("MAJOR.MINOR.PATCH"). See docs/LUA_API_STABILITY.md.
---@since 1.0.0
local wok = {}

-- =====================================================================
--  Keybindings + commands
-- =====================================================================

---Register a Lua-side keybinding.
---@param mode wok.KeyMode
---@param key string                         e.g. "ctrl+t" or "cmd+shift+d"
---@param action string                      Built-in action id, alias, or "switch_to_tab:N" / "save_session:NAME"
---@since 1.0.0
function wok.bind_key(mode, key, action) end

---Alias for `wok.bind_key`.
---@param mode wok.KeyMode
---@param key string
---@param action string
---@since 1.0.0
function wok.keymap(mode, key, action) end

---Register an action alias usable from `wok.bind_key` and the command palette.
---@param name string
---@param action string|function             Built-in action id or a Lua function
---@since 1.0.0
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
---@since 1.0.0
function wok.on(event, fn) end

-- =====================================================================
--  Actions, exec, notifications
-- =====================================================================

---Queue a built-in action through the runtime action bus.
---@param action string
---@since 1.0.0
function wok.run_action(action) end

---Alias for `wok.run_action`.
---@param action string
---@since 1.0.0
function wok.action(action) end

---Queue a shell command in the focused pane.
---@param command string
---@since 1.0.0
function wok.exec(command) end

---Show an in-app status bar message.
---@param message string
---@since 1.0.0
function wok.notify(message) end

---Show a native desktop notification.
---@param notification string|wok.SystemNotification
---@since 1.0.0
function wok.system_notify(notification) end

-- =====================================================================
--  Runtime state snapshots
-- =====================================================================

---Return the current `app` snapshot.
---@return wok.AppSnapshot
---@since 1.0.0
function wok.app() end

---Return the current `workspace` snapshot.
---@return wok.WorkspaceSnapshot
---@since 1.0.0
function wok.workspace() end

---Return the active pane snapshot.
---@return wok.PaneSnapshot
---@since 1.0.0
function wok.pane() end

---Return the current `session` snapshot.
---@return wok.SessionSnapshot
---@since 1.0.0
function wok.session() end

-- =====================================================================
--  History
-- =====================================================================

wok.history = {}

---Return up to the last 200 global history entries.
---@return wok.HistoryEntry[]
---@since 1.0.0
function wok.history.entries() end

---Case-insensitive substring search over history commands.
---@param query string
---@return wok.HistoryEntry[]
---@since 1.0.0
function wok.history.search(query) end

-- =====================================================================
--  Blocks
-- =====================================================================

wok.blocks = {}

---Last 100 blocks of the active pane.
---@return wok.Block[]
---@since 1.0.0
function wok.blocks.list() end

-- =====================================================================
--  Tabs
-- =====================================================================

wok.tabs = {}

---Open a new tab.
---@since 1.0.0
function wok.tabs.new() end

---Close the current tab.
---@since 1.0.0
function wok.tabs.close() end

---Switch to the next tab.
---@since 1.0.0
function wok.tabs.next() end

---Switch to the previous tab.
---@since 1.0.0
function wok.tabs.prev() end

---Switch to tab `index` (1..=9).
---@param index integer
---@since 1.0.0
function wok.tabs.switch(index) end

-- =====================================================================
--  Panes
-- =====================================================================

wok.panes = {}

---Split the focused pane vertically.
---@since 1.0.0
function wok.panes.split_vertical() end

---Split the focused pane horizontally.
---@since 1.0.0
function wok.panes.split_horizontal() end

---Close the focused split pane.
---@since 1.0.0
function wok.panes.close() end

---@since 1.0.0
function wok.panes.focus_left() end
---@since 1.0.0
function wok.panes.focus_right() end
---@since 1.0.0
function wok.panes.focus_up() end
---@since 1.0.0
function wok.panes.focus_down() end

---Open a new floating pane.
---@since 1.0.0
function wok.panes.new_floating() end

---Show or hide all floating panes.
---@since 1.0.0
function wok.panes.toggle_floating() end

-- =====================================================================
--  Pane I/O (separate namespace to avoid clashing with `wok.pane()`)
-- =====================================================================

wok.pane_api = {}

---Inject input into the active pane's PTY.
---@param data string|integer[]              UTF-8 string or array of bytes
---@since 1.0.0
function wok.pane_api.send_input(data) end

---Read the active pane snapshot (same data as `wok.pane()`).
---@return wok.PaneSnapshot
---@since 1.0.0
function wok.pane_api.info() end

-- =====================================================================
--  Window
-- =====================================================================

wok.window = {}

---Set the OS window title.
---@param title string
---@since 1.0.0
function wok.window.set_title(title) end

---Toggle borderless fullscreen.
---@since 1.0.0
function wok.window.toggle_fullscreen() end

---Set the window opacity (clamped to 0.0–1.0).
---@param value number
---@since 1.0.0
function wok.window.set_opacity(value) end

-- =====================================================================
--  Clipboard
-- =====================================================================

wok.clipboard = {}

---Copy `text` to the system clipboard.
---@param text string
---@since 1.0.0
function wok.clipboard.copy(text) end

---Read the latest clipboard snapshot.
---@return string
---@since 1.0.0
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
---@since 1.0.0
function wok.fs.read(path) end

---Write `contents` to a file inside the sandbox. Creates parents as needed.
---@param path string
---@param contents string
---@since 1.0.0
function wok.fs.write(path, contents) end

---Whether `path` exists (returns false for paths outside the sandbox).
---@param path string
---@return boolean
---@since 1.0.0
function wok.fs.exists(path) end

---List the immediate children of a directory inside the sandbox.
---@param path string
---@return string[]
---@since 1.0.0
function wok.fs.list(path) end

-- =====================================================================
--  Triggers, workflows, quick-select
-- =====================================================================

---Register a regex trigger that runs when a block finishes.
---@param name string
---@param pattern string
---@param actions string[]                   e.g. {"highlight_red", "system_notify:msg"}
---@since 1.0.0
function wok.add_trigger(name, pattern, actions) end

---Remove a trigger by name.
---@param name string
---@since 1.0.0
function wok.remove_trigger(name) end

---Register a parameterised workflow.
---@param workflow wok.Workflow
---@since 1.0.0
function wok.register_workflow(workflow) end

---Return the current set of registered workflows.
---@return wok.Workflow[]
---@since 1.0.0
function wok.workflows() end

wok.quick_select = {}

---Add a custom regex pattern for the quick-select label overlay.
---@param name string
---@param pattern string
---@since 1.0.0
function wok.quick_select.add_pattern(name, pattern) end

---Remove a custom quick-select pattern by name.
---@param name string
---@since 1.0.0
function wok.quick_select.remove_pattern(name) end

-- =====================================================================
--  Status bar
-- =====================================================================

wok.status_bar = {}

---Replace the left segment list.
---@param segments wok.StatusSegment[]
---@since 1.0.0
function wok.status_bar.set_left(segments) end

---Replace the center segment list.
---@param segments wok.StatusSegment[]
---@since 1.0.0
function wok.status_bar.set_center(segments) end

---Replace the right segment list.
---@param segments wok.StatusSegment[]
---@since 1.0.0
function wok.status_bar.set_right(segments) end

---Clear all custom status-bar segments.
---@since 1.0.0
function wok.status_bar.clear() end

---Set the status-bar refresh interval in milliseconds.
---@param ms integer
---@since 1.0.0
function wok.status_bar.set_refresh_interval(ms) end

-- =====================================================================
--  Themes
-- =====================================================================

wok.theme = {}

---Apply a live theme override map.
---@param overrides wok.ThemeSet
---@since 1.0.0
function wok.theme.set(overrides) end

---Load a theme by name (resolved under ~/.config/wok/themes) or absolute path.
---@param name_or_path string
---@since 1.0.0
function wok.theme.load(name_or_path) end

-- =====================================================================
--  Setup operations (programmatic equivalents of `wok` CLI subcommands)
-- =====================================================================

wok.setup = {}

---Run `wok init` from inside the running app.
---@param opts wok.SetupOptions?
---@since 1.0.0
function wok.setup.init(opts) end

---Run `wok doctor`.
---@param opts wok.SetupOptions?
---@since 1.0.0
function wok.setup.doctor(opts) end

---Run `wok reset`. Requires `yes = true`.
---@param opts wok.SetupOptions
---@since 1.0.0
function wok.setup.reset(opts) end

---Install shell integration. `shell` defaults to `"auto"`.
---@param opts wok.SetupOptions?
---@since 1.0.0
function wok.setup.shell_install(opts) end

---Roll back shell integration. Requires `yes = true`.
---@param opts wok.SetupOptions
---@since 1.0.0
function wok.setup.shell_rollback(opts) end

-- =====================================================================
--  Timers
-- =====================================================================

---Schedule `fn` to run once after `ms` milliseconds. Returns a timer id.
---@param ms integer
---@param fn fun()
---@return integer
---@since 1.0.0
function wok.set_timeout(ms, fn) end

---Schedule `fn` to run every `ms` milliseconds. Returns a timer id.
---@param ms integer
---@param fn fun()
---@return integer
---@since 1.0.0
function wok.set_interval(ms, fn) end

---Cancel a previously scheduled timer.
---@param id integer
---@since 1.0.0
function wok.clear_timer(id) end

return wok
