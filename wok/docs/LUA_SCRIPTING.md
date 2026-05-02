# Wok Lua Scripting Guide

Wok loads `~/.config/wok/init.lua` on startup and exposes a local-only plugin surface across **18 namespaces** spanning ~50 functions. Plugins can:

- register keybindings and command aliases,
- listen to lifecycle hooks (block finished, cwd changed, app start/exit, …),
- run shell commands and queue built-in actions,
- read live runtime state (history, blocks, panes, themes, sessions),
- write to the system clipboard and inject PTY input,
- manipulate tabs, panes, and the OS window (title, fullscreen, opacity),
- persist plugin state to a sandboxed filesystem area,
- register workflows, triggers, and quick-select patterns,
- schedule timers,
- drive `wok` setup operations from inside the running app.

All APIs are local-only — no network access, no telemetry, no cloud sync.

**Stability promise**: this surface is versioned independently of the wok binary. See [`LUA_API_STABILITY.md`](LUA_API_STABILITY.md) for the deprecation policy, the meaning of `wok.api_version`, and the contributor checklist for adding/removing APIs.

```lua
-- Pin a minimum API version in your init.lua
assert(wok.api_version >= "1.0.0", "wok 1.0+ required")
```

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

Two example files ship in this repo:

- [`docs/examples/minimal.lua`](examples/minimal.lua) — the smallest useful config
- [`docs/examples/powerful.lua`](examples/powerful.lua) — exercises the full API

The `wok.keymap(...)` name is an alias for `wok.bind_key(...)`.

## Quick Reference

| Namespace | Functions |
|---|---|
| top-level | `bind_key`/`keymap`, `register_command`, `register_workflow`, `workflows`, `add_trigger`, `remove_trigger`, `on`, `run_action`/`action`, `exec`, `notify`, `system_notify`, `set_timeout`, `set_interval`, `clear_timer`, `app`, `workspace`, `pane`, `session` |
| `wok.config` | read-only config snapshot |
| `wok.theme` | `set`, `load` |
| `wok.status_bar` | `set_left`, `set_center`, `set_right`, `clear`, `set_refresh_interval` |
| `wok.quick_select` | `add_pattern`, `remove_pattern` |
| `wok.setup` | `init`, `doctor`, `reset`, `shell_install`, `shell_rollback` |
| `wok.clipboard` | `copy`, `paste` |
| `wok.pane_api` | `send_input`, `info` |
| `wok.tabs` | `new`, `close`, `next`, `prev`, `switch(N)` |
| `wok.panes` | `split_vertical`, `split_horizontal`, `close`, `focus_left/right/up/down`, `new_floating`, `toggle_floating` |
| `wok.window` | `set_title`, `toggle_fullscreen`, `set_opacity` |
| `wok.history` | `entries`, `search` |
| `wok.blocks` | `list` |
| `wok.git` | `status`, `diff`, `stage`, `unstage`, `discard` |
| `wok.fs` | `read`, `write`, `exists`, `list` (sandboxed) |

---

## Configuration

### `wok.config`

Read-only table of current runtime config values.

```lua
local font_size = wok.config.font_size
local shell     = wok.config.shell  -- "bash", "zsh", "fish", "powershell", "wsl:Ubuntu"
```

---

## Keybindings

### `wok.bind_key(mode, key, action)`

Define a custom keybinding from Lua.

- `mode`: `"terminal"`, `"normal"`, `"input"`, `"block"`, or `"search"`
- `key`: combo string like `"ctrl+t"` or `"cmd+shift+d"`
- `action`: a built-in action id, a `command_alias` registered via `wok.register_command`, or a parameterised id like `"save_session:work"` / `"switch_to_tab:3"`

```lua
wok.bind_key("terminal", "ctrl+shift+t", "new_tab")
wok.bind_key("terminal", "ctrl+shift+s", "save_session:work")
wok.bind_key("terminal", "alt+1",        "switch_to_tab:1")
```

> **Bindings can also live in `~/.config/wok/keybindings.toml`** (no Lua required — see *TOML keybindings* below). Lua bindings layer on top.

### `wok.register_command(name, action)`

Register an alias usable from `wok.bind_key` and the command palette.

```lua
wok.register_command("restore_demo", "load_session:demo")
wok.bind_key("terminal", "ctrl+shift+r", "restore_demo")
```

### Built-in Action IDs

Tabs: `new_tab`, `close_tab`, `next_tab`, `prev_tab`, `switch_to_tab:N` (1..=9)

Pane layout: `split_vertical`, `split_horizontal`, `close_split`/`close_pane`

Pane focus/resize: `focus_left`, `focus_right`, `focus_up`, `focus_down`, `resize_split_left`, `resize_split_right`, `resize_split_up`, `resize_split_down`

Floating panes: `new_floating_pane`, `toggle_floating_pane`, `close_floating_pane`

Search & palette: `search_global`, `command_palette`, `command_search`, `quick_select`, `quick_select_block`, `keybinding_discovery`, `theme_picker`, `settings_discovery`, `git_changes`, `git_worktrees`

Block navigation: `block_prev`, `block_next`, `block_copy`, `block_copy_command`, `block_copy_output`, `block_collapse`, `block_toggle_bookmark`, `block_prev_bookmark`, `block_next_bookmark`, `block_prev_failed`, `block_next_failed`, `block_find`, `block_filter`, `block_diff`, `block_rerun`, `block_rerun_in_split`, `block_save_workflow`, `block_export_markdown`, `block_export_json`

Layout / panels: `next_layout`, `prev_layout`, `toggle_failure_trends_panel`, `toggle_workspace_insights_panel`, `toggle_broadcast`

Input & terminal: `toggle_input_position`, `zoom_in`, `zoom_out`, `zoom_reset`, `clear_screen`, `send_eof`

Sessions: `save_session:<name>`, `load_session:<name>`

Settings: `open_settings`, `settings_discovery`

Aliases (also accepted): `close_pane`, `search`, `copy_block`, `collapse_block`, `diff_block`, `failure_trends`, `prev_failed_block`, `next_failed_block`, `rerun_block_split`, `save_block_workflow`, `export_block_markdown`, `export_block_json`, `workspace_insights`, `history_search`, `git_status`, `changed_files`, `git_worktree`, `worktree_switcher`.

### TOML keybindings (`~/.config/wok/keybindings.toml`)

Lua isn't required for simple rebinding. Drop a TOML file:

```toml
[[binding]]
keys   = "cmd+shift+t"
action = "new_tab"

[[binding]]
keys   = "alt+f4"
action = "close_tab"

[[binding]]
keys   = "cmd+shift+p"
action = "command_palette"
```

`keys` syntax: `+`-separated tokens, case-insensitive. Modifiers: `cmd`/`super`/`meta`/`win`, `ctrl`/`control`, `alt`/`opt`/`option`, `shift`. Final token is the key (single char, named like `enter`, `escape`, `pgup`, `f1`..`f12`, `up`/`down`/`left`/`right`).

`action` matches a canonical action id from the list above. Unknown actions log warnings; other entries keep loading.

The file is hot-reloaded — saving applies immediately. Removed bindings persist in-memory until you restart wok (known limitation).

---

## Lifecycle hooks

### `wok.on(event, callback)`

Register a structured hook. Callbacks receive a payload table.

| Event | Payload fields |
|---|---|
| `app_start` | `active_tab_index`, `active_tab_id?`, `tab_count`, `pane_count`, `active_pane_id?` |
| `app_exit` | same as `app_start` |
| `tab_opened` | `pane_id`, `tab_index`, `tab_id?`, `tab_title?`, `shell?`, `title?`, `cwd`, `is_active_pane` |
| `pane_opened` | same as `tab_opened` plus `direction` (`"vertical"` / `"horizontal"` / `"floating"`) |
| `pane_exited` | `pane_id`, `exit_code` |
| `tab_done` | `tab_id`, `pane_ids`, `pane_count` |
| `command_submitted` | `pane_id`, `command`, `cwd?` |
| `block_finished` | `pane_id`, `block_id`, `command`, `exit_code`, `duration_ms`, `output_start_row`, `output_end_row` |
| `cwd_changed` | `pane_id`, `path` |

```lua
wok.on("block_finished", function(event)
    if event.exit_code ~= 0 then
        wok.system_notify({title = "Failed", message = event.command})
    end
end)
```

---

## Actions, exec, and notifications

### `wok.run_action(action)` / `wok.action(action)`

Queue a built-in action through the same path as keybindings.

```lua
wok.run_action("new_tab")
wok.run_action("command_palette")
wok.run_action("switch_to_tab:3")
```

### `wok.exec(command)`

Queue a shell command in the focused pane.

```lua
wok.exec("git status")
```

### `wok.notify(message)`

In-app status bar message (also logged).

```lua
wok.notify("Snapshot restored")
```

### `wok.system_notify(message | table)`

Native desktop notification. macOS uses Notification Center via `osascript`; Linux uses `notify-send` if installed.

```lua
wok.system_notify("Long command finished")

wok.system_notify({
    title    = "Agent finished",
    subtitle = "review tab",
    message  = "codex completed with exit code 0",
})
```

---

## Reading runtime state

### `wok.app()`, `wok.workspace()`, `wok.pane()`, `wok.session()`

Read-only snapshots refreshed each event tick.

```lua
local pane      = wok.pane()
local workspace = wok.workspace()
wok.notify(string.format("pane %s of %d", tostring(pane.pane_id), workspace.pane_count))
```

Snapshot fields:

```
app: { status_message, cursor_visible, uptime_ms, history }
workspace: { active_tab_index, active_pane_id, tab_count, pane_count }
pane: { pane_id, title, shell, cwd, cols, rows, follow_output, display_offset,
        search_query, selected_block_id, blocks }
session: { restore_enabled, autosave_path, window_size, window_position }
theme: { name, font_family, font_size, background_image }
```

`pane.blocks` and `app.history` carry the last 100 blocks and last 200 history entries respectively.

### `wok.history.entries()` / `wok.history.search(query)`

```lua
local recent = wok.history.entries()  -- last 200
for _, e in ipairs(recent) do
    print(e.command, e.exit_code, e.duration_ms)
end

local git_runs = wok.history.search("git ")  -- case-insensitive substring
```

Each entry: `{ command, cwd, started_at_ms, completed_at_ms, exit_code, duration_ms }`.

### `wok.blocks.list()`

Last 100 blocks of the active pane.

```lua
for _, b in ipairs(wok.blocks.list()) do
    if b.exit_code ~= nil and b.exit_code ~= 0 then
        print("failed:", b.command)
    end
end
```

Each block: `{ id, command, cwd, exit_code, duration_ms, is_bookmarked, git_branch }`.

### `wok.git.status([options])`

Read the changed-file snapshot for the Git repository containing the active pane's `cwd`. Pass `{ cwd = "/path" }` to inspect a specific directory.

```lua
local status = wok.git.status()
if status.is_git_repo and not status.clean then
    for _, file in ipairs(status.files) do
        print(file.status_text, file.path, file.additions, file.deletions)
    end
end
```

Returns `{ is_git_repo, repo_root, branch, clean, files }`. Outside a repository it returns `{ is_git_repo = false, clean = true, files = {} }`.

Each file: `{ path, old_path, index_status, worktree_status, status_text, staged_status_text, unstaged_status_text, is_staged, is_unstaged, additions, deletions, is_binary }`.

### `wok.git.diff(path | options)`

Read parsed staged plus unstaged diff rows for one repository-relative file path. Pass a string path or `{ cwd = "/repo", path = "src/lib.rs" }`.

```lua
local diff = wok.git.diff("src/lib.rs")
for _, row in ipairs(diff.rows) do
    print(row.kind, row.old_line_number, row.new_line_number, row.text)
end
```

Returns `{ is_git_repo, repo_root, branch, path, additions, deletions, rows }`. Outside a repository it returns `{ is_git_repo = false, path = path, additions = 0, deletions = 0, rows = {} }`.

Each row: `{ kind, old_line_number, new_line_number, old_text, new_text, text }`, where `kind` is `hunk`, `context`, `addition`, `deletion`, or `collapsed`.

The same changed-file list is available in the app via the **Git Changes** palette action (`git_changes`). The palette can preview a diff, stage unstaged changes, unstage indexed changes, or discard local edits for a path. Use **Git Worktrees** (`git_worktrees`) to switch the active pane into another worktree for the same repository.

### `wok.git.stage(path | options)`

Stages one repository-relative path and returns `{ ok, action, path, status }`, where `status` is the refreshed `wok.git.status()` snapshot.

```lua
wok.git.stage("src/lib.rs")
wok.git.unstage({ path = "src/lib.rs", cwd = "/repo" })
```

### `wok.git.discard(options)`

Discards local edits for one repository-relative path and returns `{ ok, action, path, status }`. This is destructive, so `confirm = true` is required.

```lua
wok.git.discard({ path = "scratch.txt", confirm = true })
```

### `wok.pane_api.info()`

Read the active pane snapshot directly (same data as `wok.pane()`; the alternate name was kept to avoid colliding with pane-manipulation surfaces).

---

## Pane and tab manipulation

### `wok.tabs.{new, close, next, prev, switch}`

```lua
wok.tabs.new()
wok.tabs.switch(2)
wok.tabs.next()
wok.tabs.close()
```

`switch(N)` accepts `1..=9`.

### `wok.panes.{split_vertical, split_horizontal, close, focus_*, *_floating}`

```lua
wok.panes.split_vertical()
wok.panes.split_horizontal()
wok.panes.focus_right()
wok.panes.close()
wok.panes.new_floating()
wok.panes.toggle_floating()
```

### `wok.pane_api.send_input(s | array)`

Inject input into the active pane's PTY (same path as user keystrokes).

```lua
wok.pane_api.send_input("ls\r")            -- string
wok.pane_api.send_input({0x1b, 0x5b, 0x42}) -- array of bytes (ESC [ B = down arrow)
```

---

## Window control

### `wok.window.{set_title, toggle_fullscreen, set_opacity}`

```lua
wok.window.set_title("focus mode")
wok.window.toggle_fullscreen()
wok.window.set_opacity(0.85)  -- clamped to [0.0, 1.0]
```

---

## Clipboard

### `wok.clipboard.{copy, paste}`

```lua
wok.clipboard.copy("hello from lua")
local text = wok.clipboard.paste()
```

`paste()` reads the latest clipboard snapshot surfaced by the runtime; refresh cadence matches snapshot ticks.

---

## Sandboxed filesystem

### `wok.fs.{read, write, exists, list}`

For plugin state, log files, caches. Sandbox roots:

- `~/.config/wok/data/` (default for relative paths)
- `~/.local/share/wok/`

Paths outside the sandbox raise an error. `exists()` returns `false` for paths outside the sandbox (matches POSIX semantics).

```lua
if not wok.fs.exists("counter.txt") then
    wok.fs.write("counter.txt", "0")
end
local n = tonumber(wok.fs.read("counter.txt")) or 0
wok.fs.write("counter.txt", tostring(n + 1))

for _, name in ipairs(wok.fs.list(".")) do
    print(name)
end
```

`write()` creates parent directories as needed.

---

## Triggers, workflows, quick-select

### `wok.add_trigger(name, pattern, actions)` / `wok.remove_trigger(name)`

Regex triggers fire when a block finishes. Lua-added triggers default to `output` scope.

```lua
wok.add_trigger("test failure", "FAILED|panic", {
    "highlight_red",
    "system_notify:Output matched a failure",
})

wok.remove_trigger("test failure")
```

Trigger actions: `highlight_<color>`, `notify:<message>`, `system_notify:<message>`, `bookmark`, `open_url`, `copy_match`, `lua:<hook_name>`.

### `wok.register_workflow(table)` / `wok.workflows()`

```lua
wok.register_workflow({
    name = "git: commit message",
    description = "Run git commit -m '<message>'",
    parameters = {
        { name = "message", description = "Commit message", required = true },
    },
    command = "git commit -m \"{message}\"",
})

for _, wf in ipairs(wok.workflows()) do
    print(wf.name)
end
```

### `wok.quick_select.add_pattern(name, regex)` / `remove_pattern(name)`

Add custom regexes for the quick-select label overlay (e.g. URLs, file paths).

```lua
wok.quick_select.add_pattern("ipv4", "(?:\\d{1,3}\\.){3}\\d{1,3}")
```

---

## Status bar

### `wok.status_bar.{set_left, set_center, set_right, clear, set_refresh_interval}`

Each `set_*` takes an array of segments:

```lua
wok.status_bar.set_left({
    { text = "wok", color = "#89b4fa" },
})
wok.status_bar.set_right({
    { text = os.date("%H:%M") },
})
wok.status_bar.set_refresh_interval(2000) -- ms
wok.status_bar.clear()
```

---

## Themes

### `wok.theme.set(table)`

Apply live theme overrides. Reapplied after watched theme file reloads.

```lua
wok.theme.set({
    background = "#1e1e2e",
    foreground = "#cdd6f4",
    cursor     = "#f5e0dc",
})
```

### `wok.theme.load(name_or_path)`

Load a theme by name from `~/.config/wok/themes/<name>.toml` or by absolute path.

```lua
wok.theme.load("catppuccin")
wok.theme.load("/abs/path/to/theme.toml")
```

The same selection is also available via the **Theme Picker** palette: open the command palette and search for `theme_picker`.

---

## Setup operations

### `wok.setup.{init, doctor, reset, shell_install, shell_rollback}`

Drive the same operations as `wok init`, `wok doctor`, etc., from inside the running app.

```lua
wok.setup.init({ overwrite = true })
wok.setup.doctor({ json = true })
wok.setup.reset({ scope = "managed", yes = true })
wok.setup.shell_install({ shell = "zsh", overwrite = false })
wok.setup.shell_rollback({ shell = "zsh", yes = true })
```

`scope` accepts `"managed"`, `"state"`, or `"all"`. Destructive ops require `yes = true`.

---

## Timers

### `wok.set_timeout(ms, fn)` → id

Fires once after `ms` milliseconds. Returns an id usable with `wok.clear_timer`.

### `wok.set_interval(ms, fn)` → id

Fires every `ms` milliseconds until cleared.

### `wok.clear_timer(id)`

```lua
local id = wok.set_interval(5000, function()
    wok.notify("tick at " .. os.date("%H:%M:%S"))
end)
-- later:
wok.clear_timer(id)
```

Timers run on the main thread between event ticks; long callbacks block rendering.

---

## Patterns

### Reactive status bar from history

```lua
wok.set_interval(3000, function()
    local h = wok.history.entries()
    wok.status_bar.set_right({
        { text = "#" .. #h, color = "#a6e3a1" },
    })
end)
```

### Backup history nightly via `wok.fs`

```lua
wok.set_interval(24 * 60 * 60 * 1000, function()
    local entries = wok.history.entries()
    local lines = {}
    for _, e in ipairs(entries) do table.insert(lines, e.command) end
    wok.fs.write("history-" .. os.date("%Y%m%d") .. ".txt",
                 table.concat(lines, "\n"))
end)
```

### Auto-respond to interactive prompts

```lua
wok.on("block_finished", function(event)
    if event.command:match("^npm install") and event.exit_code == 0 then
        wok.pane_api.send_input("npm test\r")
    end
end)
```

### Zen mode: collapse to one pane + dim window

```lua
wok.register_command("zen", function()
    wok.window.set_opacity(0.95)
    while wok.workspace().pane_count > 1 do wok.panes.close() end
end)
wok.bind_key("terminal", "cmd+shift+z", "zen")
```

---

## Examples

- [`docs/examples/minimal.lua`](examples/minimal.lua) — bare minimum
- [`docs/examples/full.lua`](examples/full.lua) — keybindings + theme + a few hooks
- [`docs/examples/powerful.lua`](examples/powerful.lua) — every namespace exercised

## Editor autocomplete

[`docs/wok.d.lua`](wok.d.lua) ships LuaCATS type annotations for the entire `wok.*` API. With `lua-language-server` installed (most editors via the Lua extension), drop the file into your workspace library to get autocomplete, hover docs, and type checking for every function, namespace, hook payload, and snapshot field.

Drop-in setup:

```bash
mkdir -p ~/.config/wok/types
cp /path/to/wok/docs/wok.d.lua ~/.config/wok/types/
cat > ~/.config/wok/.luarc.json <<'EOF'
{
  "workspace": { "library": ["~/.config/wok/types"] },
  "runtime":   { "version": "Lua 5.4" }
}
EOF
```

After that, opening `~/.config/wok/init.lua` in any LSP-capable editor will auto-complete `wok.<TAB>` with proper type signatures and inline documentation.
