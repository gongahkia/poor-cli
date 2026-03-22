# Walk Lua Scripting Guide

> Status note: Lua support is currently scaffolding, not an active runtime feature in the shipped binary. The scripting module and API surface exist in the workspace, but `walk` does not yet wire Lua into the live event loop or product claims. Treat this document as the planned API direction, not current day-one behavior.

Walk supports Lua 5.4 scripting for custom keybindings, themes, and event hooks.

## Getting Started

Place your configuration in `~/.config/walk/init.lua`. Walk loads this file on startup.

## API Reference

### `walk.config`

Read-only table of current configuration values.

```lua
local font_size = walk.config.font_size
```

### `walk.keymap(mode, key, action)`

Define a custom keybinding.

- `mode`: `"normal"`, `"input"`, `"search"`
- `key`: Key combo string like `"ctrl+t"`, `"ctrl+shift+d"`
- `action`: Built-in action name or Lua function

```lua
walk.keymap("normal", "ctrl+shift+t", "new_tab")
walk.keymap("normal", "ctrl+shift+e", function()
    walk.exec("echo hello")
end)
```

#### Built-in Actions

- `"new_tab"`, `"close_tab"`, `"next_tab"`, `"prev_tab"`
- `"split_horizontal"`, `"split_vertical"`, `"close_pane"`
- `"toggle_search"`, `"copy_block"`
- `"scroll_up"`, `"scroll_down"`
- `"zoom_in"`, `"zoom_out"`, `"zoom_reset"`

### `walk.theme.set(table)`

Apply theme colors immediately.

```lua
walk.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor = "#f5e0dc",
})
```

### `walk.theme.load(name)`

Load a named theme from `~/.config/walk/themes/`.

```lua
walk.theme.load("catppuccin")
```

### `walk.on(event, callback)`

Register an event hook.

#### Events

| Event | Context Fields | Description |
|-------|---------------|-------------|
| `"tab_created"` | `{id}` | New tab opened |
| `"tab_closed"` | `{id}` | Tab closed |
| `"command_finished"` | `{exit_code, duration_ms}` | Command completed |
| `"directory_changed"` | `{path}` | CWD changed |
| `"block_created"` | `{id, command}` | New block created |

```lua
walk.on("command_finished", function(e)
    if e.exit_code ~= 0 then
        walk.notify("Command failed!")
    end
end)
```

### `walk.exec(command)`

Execute a shell command in the active terminal.

### `walk.notify(message)`

Display a message in the status bar.

## Examples

See `docs/examples/minimal.lua` and `docs/examples/full.lua` for complete examples.
