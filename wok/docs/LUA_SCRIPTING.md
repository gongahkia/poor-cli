# Wok Lua Scripting Guide

Wok loads `~/.config/wok/init.lua` on startup and exposes a local-only plugin surface for keybindings, command aliases, lifecycle hooks, shell execution, built-in actions, runtime state inspection, and theme changes.

This API is still intentionally scoped. Lua extends the action bus and runtime state model; it does not replace the renderer or bypass core workspace routing.

## Getting Started

Create `~/.config/wok/init.lua`:

```lua
wok.bind_key("terminal", "ctrl+shift+t", "new_tab")
wok.register_command("save_demo", "save_session:demo")
wok.bind_key("terminal", "ctrl+shift+s", "save_demo")

wok.on("app_start", function()
    wok.notify("Wok started")
end)
```

The `wok.keymap(...)` name is kept as an alias for `wok.bind_key(...)`.

## API Reference

### `wok.config`

Read-only table of current runtime config values.

```lua
local font_size = wok.config.font_size
```

### `wok.bind_key(mode, key, action)`

Define a custom keybinding.

- `mode`: `"terminal"`, `"normal"`, `"input"`, `"block"`, or `"search"`
- `key`: key combo string like `"ctrl+t"` or `"cmd+shift+d"`
- `action`: built-in action string or a command alias registered through `wok.register_command(...)`

```lua
wok.bind_key("terminal", "ctrl+shift+t", "new_tab")
wok.bind_key("terminal", "ctrl+shift+s", "save_session:demo")
```

### `wok.register_command(name, action)`

Register an action alias that can be reused from `wok.bind_key(...)`.

```lua
wok.register_command("restore_demo", "load_session:demo")
wok.bind_key("terminal", "ctrl+shift+r", "restore_demo")
```

### Built-in Action Strings

- Tabs: `new_tab`, `close_tab`, `next_tab`, `prev_tab`
- Pane layout: `split_vertical`, `split_horizontal`, `close_split`
- Pane focus/resize: `focus_left`, `focus_right`, `focus_up`, `focus_down`, `resize_split_left`, `resize_split_right`, `resize_split_up`, `resize_split_down`
- Search and palette: `search_global`, `toggle_search`, `command_palette`, `palette`, `command_search`
- Block navigation/actions: `block_prev`, `block_next`, `block_copy`, `block_copy_command`, `block_copy_output`, `block_collapse`, `block_toggle_bookmark`, `block_prev_bookmark`, `block_next_bookmark`, `block_prev_failed`, `block_next_failed`, `block_find`, `block_filter`, `block_diff`, `block_rerun`, `block_rerun_in_split`, `block_save_workflow`, `block_export_markdown`, `block_export_json`
- Runtime tools: `quick_select`, `quick_select_block`, `toggle_failure_trends_panel`, `toggle_workspace_insights_panel`, `toggle_broadcast`
- Floating panes/layout: `new_floating_pane`, `toggle_floating_pane`, `close_floating_pane`, `next_layout`, `prev_layout`
- Input and terminal: `toggle_input_position`, `zoom_in`, `zoom_out`, `zoom_reset`, `clear_screen`, `send_eof`
- Session snapshots: `save_session:<name>`, `load_session:<name>`

Aliases also accepted:

- `close_pane`
- `search`
- `copy_block`
- `collapse_block`
- `diff_block`
- `failure_trends`
- `prev_failed_block`
- `next_failed_block`
- `rerun_block_split`
- `save_block_workflow`
- `export_block_markdown`
- `export_block_json`
- `workspace_insights`
- `history_search`

### `wok.on(event, callback)`

Register a lifecycle hook.

Available hooks:

- `app_start`
- `app_exit`
- `tab_opened`
- `pane_opened`
- `command_submitted`
- `block_finished`
- `cwd_changed`

```lua
wok.on("block_finished", function()
    wok.notify("Command block finished")
end)
```

Hook payloads are structured tables. Common fields include:

- `pane_id`
- `tab_id`
- `tab_index`
- `tab_title`
- `shell`
- `title`
- `cwd`

Event-specific fields include:

- `command_submitted`: `command`
- `block_finished`: `block_id`, `command`, `exit_code`, `duration_ms`, `output_start_row`, `output_end_row`
- `cwd_changed`: `path`

Example:

```lua
wok.on("block_finished", function(event)
    if event.exit_code ~= 0 then
        wok.notify("Failed command: " .. event.command)
    end
end)
```

### `wok.run_action(action)`

Queue a built-in Wok action through the same runtime path used by core keybindings.

```lua
wok.run_action("new_tab")
wok.run_action("command_palette")
```

### `wok.app()`, `wok.workspace()`, `wok.pane()`, `wok.session()`

Return structured tables describing the current runtime state visible to plugins.

```lua
local pane = wok.pane()
local workspace = wok.workspace()
wok.notify("Pane " .. tostring(pane.pane_id) .. " of " .. tostring(workspace.pane_count))
```

### `wok.exec(command)`

Queue a shell command to run in the focused pane.

```lua
wok.exec("echo hello from lua")
```

### `wok.notify(message)`

Publish a status message. Wok logs it and mirrors the latest message into the status bar when the bar is visible.

```lua
wok.notify("Snapshot restored")
```

### `wok.setup.*(...)`

Queue local setup lifecycle operations from Lua. These APIs are synchronous in intent (same behavior as CLI setup commands) but are executed through the runtime setup queue.

```lua
wok.setup.init({ overwrite = true })
wok.setup.doctor({ json = true })
wok.setup.reset({ scope = "managed", yes = true })
wok.setup.shell_install({ shell = "zsh", overwrite = false })
wok.setup.shell_rollback({ shell = "zsh", yes = true })
```

Supported methods and options:

- `wok.setup.init({ overwrite = <bool> })`
- `wok.setup.doctor({ json = <bool> })`
- `wok.setup.reset({ scope = "managed"|"state"|"all", yes = <bool> })`
- `wok.setup.shell_install({ shell = "auto"|"bash"|"zsh"|"fish", overwrite = <bool> })`
- `wok.setup.shell_rollback({ shell = "bash"|"zsh"|"fish", yes = <bool> })`

### `wok.theme.set(table)`

Apply live theme overrides to the active runtime theme. Overrides are also re-applied after watched theme file reloads.

```lua
wok.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor = "#f5e0dc",
})
```

### `wok.theme.load(name)`

Load a theme either by explicit path or by name from `~/.config/wok/themes/<name>.toml`.

```lua
wok.theme.load("catppuccin")
wok.theme.load("/absolute/path/to/theme.toml")
```

## Examples

- [docs/examples/minimal.lua](examples/minimal.lua)
- [docs/examples/full.lua](examples/full.lua)
