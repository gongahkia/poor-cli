# Walk Lua Scripting Guide

Walk loads `~/.config/walk/init.lua` on startup and exposes a small action-oriented Lua surface for keybindings, command aliases, lifecycle hooks, shell execution, and notifications.

This API is intentionally constrained. Lua extends the existing action bus; it does not replace the renderer or bypass core runtime state.

## Getting Started

Create `~/.config/walk/init.lua`:

```lua
walk.bind_key("terminal", "ctrl+shift+t", "new_tab")
walk.register_command("save_demo", "save_session:demo")
walk.bind_key("terminal", "ctrl+shift+s", "save_demo")

walk.on("app_start", function()
    walk.notify("Walk started")
end)
```

The `walk.keymap(...)` name is kept as an alias for `walk.bind_key(...)`.

## API Reference

### `walk.config`

Read-only table of a few startup config values.

```lua
local font_size = walk.config.font_size
```

### `walk.bind_key(mode, key, action)`

Define a custom keybinding.

- `mode`: `"terminal"`, `"normal"`, `"input"`, `"block"`, or `"search"`
- `key`: key combo string like `"ctrl+t"` or `"cmd+shift+d"`
- `action`: built-in action string or a command alias registered through `walk.register_command(...)`

```lua
walk.bind_key("terminal", "ctrl+shift+t", "new_tab")
walk.bind_key("terminal", "ctrl+shift+s", "save_session:demo")
```

### `walk.register_command(name, action)`

Register an action alias that can be reused from `walk.bind_key(...)`.

```lua
walk.register_command("restore_demo", "load_session:demo")
walk.bind_key("terminal", "ctrl+shift+r", "restore_demo")
```

### Built-in Action Strings

- `new_tab`, `close_tab`, `next_tab`, `prev_tab`
- `split_vertical`, `split_horizontal`, `close_split`
- `focus_left`, `focus_right`, `focus_up`, `focus_down`
- `search_global`, `toggle_search`
- `block_prev`, `block_next`, `block_copy`, `block_collapse`
- `zoom_in`, `zoom_out`, `zoom_reset`
- `clear_screen`, `send_eof`
- `save_session:<name>`, `load_session:<name>`

Aliases also accepted:

- `close_pane`
- `search`
- `copy_block`
- `collapse_block`

### `walk.on(event, callback)`

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
walk.on("block_finished", function()
    walk.notify("Command block finished")
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
walk.on("block_finished", function(event)
    if event.exit_code ~= 0 then
        walk.notify("Failed command: " .. event.command)
    end
end)
```

### `walk.exec(command)`

Queue a shell command to run in the focused pane.

```lua
walk.exec("echo hello from lua")
```

### `walk.notify(message)`

Publish a status message. Walk logs it and mirrors the latest message into the status bar when the bar is visible.

```lua
walk.notify("Snapshot restored")
```

### `walk.theme.set(table)`

Store theme overrides for future theme-aware surfaces.

```lua
walk.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor = "#f5e0dc",
})
```

### `walk.theme.load(name)`

Placeholder hook for named theme loading.

## Examples

- [docs/examples/minimal.lua](examples/minimal.lua)
- [docs/examples/full.lua](examples/full.lua)
