# Wok Configuration Reference

Wok is configured via a TOML file located at one of:

1. `$WOK_CONFIG`
2. `~/.config/wok/config.toml`
3. `~/.wok.toml`

You can scaffold managed defaults with:

```bash
wok init
```

From inside Wok, open the command palette and run `Reset Settings` to overwrite
`~/.config/wok/config.toml` with the managed default config. This does not
remove sessions, themes, shell integration, workflows, or `init.lua`.

## Full Example

```toml
shell = "zsh"
font_family = "JetBrains Mono"
font_size = 24.0
input_position = "bottom"
command_entry_mode = "shell_native"
scrollback_lines = 10000
cursor_style = "block"
cursor_blink = true
tab_bar_visible = true
tab_bar_orientation = "horizontal"
tab_bar_side = "top"
tab_bar_size = 36.0
status_bar_visible = true
status_bar_side = "bottom"
status_bar_size = 36.0
window_opacity = 1.0
background_image = "~/.config/wok/backgrounds/workspace.png"
background_opacity = 0.85
background_fit = "cover"
background_position = "center"
# background_width = 900.0
# background_height = 600.0
# terminal_background_opacity = 0.72
pane_border_width = 1.0
focused_pane_border_width = 2.0
floating_pane_title_height = 18.0
recent_keys_visible = true
recent_keys_position = "bottom_right"
recent_keys_max_entries = 8
recent_keys_timeout_ms = 2000
recent_keys_opacity = 0.86
typewriter_effect_enabled = false
typewriter_effect_cps = 180.0
copy_on_select = false
confirm_close_with_running_process = true
close_on_shell_exit = true
restore_session = true
debug_overlay = false
command_telemetry = false
theme_path = "~/.config/wok/themes/graph-box-dark.toml"
external_plugin_command = "node ~/.config/wok/plugins/bridge.js"
```

## Options

| Option | Type | Default | Runtime Status | Description |
| --- | --- | --- | --- | --- |
| `shell` | string | auto-detected | Active | Shell to use: `bash`, `zsh`, `fish`, `powershell`, or `wsl:<distro>` |
| `font_family` | string | `"Menlo"` on macOS, `"JetBrains Mono"` elsewhere | Active | Selects the font family used for glyph rasterization and cell metric measurement |
| `font_size` | float | `24.0` | Active | Font size in points |
| `input_position` | string | `"bottom"` | Active | Places the owned input bar above or below the viewport |
| `command_entry_mode` | string | `"shell_native"` | Active | Chooses prompt-time command entry routing: `shell_native` keeps shell-side editing, `owned_primary` routes idle prompt input into Wok's editor with pane-first history recall and `Ctrl+R` command search |
| `scrollback_lines` | integer | `10000` | Active | Number of scrollback lines to retain |
| `cursor_style` | string | `"block"` | Active | Chooses the cursor shape for both the terminal viewport and owned input bar: `block`, `bar`, or `underline` |
| `cursor_blink` | boolean | `true` | Active | Enables the timed cursor blink cadence for the viewport and input bar |
| `tab_bar_visible` | boolean | `true` | Active | Shows or hides the workspace tab bar |
| `tab_bar_orientation` | string | `"horizontal"` | Active | Backward-compatible tab layout option: `"horizontal"` maps to `tab_bar_side = "top"`, `"vertical"` maps to `tab_bar_side = "left"` |
| `tab_bar_side` | string | `"top"` | Active | Places the tab bar on any edge: `top`, `bottom`, `left`, or `right` |
| `tab_bar_size` | float | auto | Active | Optional tab bar thickness in physical pixels; defaults to the active font metrics for horizontal tabs and `180.0` for vertical tabs |
| `status_bar_visible` | boolean | `true` | Active | Shows or hides the status bar |
| `status_bar_side` | string | `"bottom"` | Active | Places the status bar on any edge: `top`, `bottom`, `left`, or `right`; vertical status bars render segments as a stacked list |
| `status_bar_size` | float | auto | Active | Optional status bar thickness in physical pixels; defaults to the active font metrics |
| `window_opacity` | float | `1.0` | Active | Applies window/chrome opacity and blends terminal surfaces against the configured background |
| `background_image` | string | none | Active | Loads a background image from config or theme and renders it behind the workspace chrome and panes |
| `background_opacity` | float | `1.0` | Active | Multiplies background image opacity from `0.0` to `1.0`; combines with `window_opacity` |
| `background_fit` | string | `"stretch"` | Active | Background sizing mode: `stretch`, `cover`, `contain`, or `center` |
| `background_position` | string | `"center"` | Active | Background anchor: `center`, `top_left`, `top_right`, `bottom_left`, or `bottom_right` |
| `background_width` | float | none | Active | Optional rendered background width in physical pixels; preserves source aspect ratio when height is omitted |
| `background_height` | float | none | Active | Optional rendered background height in physical pixels; preserves source aspect ratio when width is omitted |
| `terminal_background_opacity` | float | auto | Active | Optional terminal pane fill opacity from `0.0` to `1.0`; by default panes become slightly translucent only when a background image is loaded |
| `pane_border_width` | float | `1.0` | Active | Split pane border width in physical pixels; use `0.0` to hide inactive borders |
| `focused_pane_border_width` | float | `2.0` | Active | Focused split pane accent border width in physical pixels; use `0.0` to hide it |
| `floating_pane_title_height` | float | `18.0` | Active | Floating pane title strip height in physical pixels |
| `recent_keys_visible` | boolean | `true` | Active | Shows a local in-app recent-key visualizer; keys are not persisted |
| `recent_keys_position` | string | `"bottom_right"` | Active | Places the recent-key visualizer at `top_left`, `top_right`, `bottom_left`, or `bottom_right` |
| `recent_keys_max_entries` | integer | `8` | Active | Maximum number of recent key labels shown, capped at 64 |
| `recent_keys_timeout_ms` | integer | `2000` | Active | Time in milliseconds before a key label expires, clamped to 250..30000 |
| `recent_keys_opacity` | float | `0.86` | Active | Recent-key overlay opacity from `0.0` to `1.0` |
| `typewriter_effect_enabled` | boolean | `false` | Active | Reveals new command-output cells character by character while leaving terminal state, copy, search, and sessions immediate |
| `typewriter_effect_cps` | float | `180.0` | Active | Reveal speed in characters per second, clamped to 20..2000 |
| `copy_on_select` | boolean | `false` | Active | Auto-copy selected text on mouse-up |
| `confirm_close_with_running_process` | boolean | `true` | Active | Requires a second close request within 2 seconds when panes still have running shell processes |
| `close_on_shell_exit` | boolean | `true` | Active | Closes the exited pane, closes an all-exited tab when other tabs remain, or exits Wok when the final shell exits |
| `restore_session` | boolean | `false` | Active | Loads the autosaved workspace session on startup |
| `debug_overlay` | boolean | `false` | Active | Shows a benchmark overlay with FPS, redraw time, phase timings, CPU, memory, disk, GPU adapter/render diagnostics, battery when available, scrollback, and session memory |
| `command_telemetry` | boolean | `false` | Active | Writes opt-in command lifecycle telemetry to `~/.config/wok/command-telemetry.jsonl`; command text is included, so avoid enabling it for secret-bearing workflows |
| `theme_path` | string | none | Active | Path to a custom theme TOML file |
| `external_plugin_command` | string | none | Active | Optional out-of-process plugin bridge command; receives hook/event JSON lines on stdin and can emit typed effects (`notify`, `system_notify`, `exec`, `action`) on stdout |

## Themes

The compiled default is `Graph Box Dark`. Running `wok init` also writes these editable theme files to `~/.config/wok/themes/`:

- `graph-box-dark.toml`
- `tokyo-night.toml`
- `catppuccin.toml`
- `nord.toml`
- `gruvbox-dark.toml`
- `solarized-dark.toml`
- `paper-light.toml`

Load one at startup:

```toml
theme_path = "~/.config/wok/themes/nord.toml"
```

Or switch live from Lua:

```lua
wok.theme.load("gruvbox-dark")
```

## Command And Output Triggers

Triggers are regex rules that run when a command block finishes. They can match command text, command output, or both.

The default generated config ships with a CLI-agent completion trigger:

```toml
[[triggers]]
name = "CLI agent finished"
pattern = '^\s*(claude|codex|gemini|ada|gh\s+copilot)\b'
scope = "command"
actions = ["highlight_cyan", "system_notify:CLI agent command finished"]
```

Useful general command notifications:

```toml
[[triggers]]
name = "Homebrew task finished"
pattern = '^\s*brew\s+(update|upgrade|install|cleanup)\b'
scope = "command"
actions = ["highlight_blue", "system_notify:Homebrew task finished"]

[[triggers]]
name = "sudo task finished"
pattern = '^\s*sudo\b'
scope = "command"
actions = ["highlight_yellow", "system_notify:Privileged command finished"]

[[triggers]]
name = "curl finished"
pattern = '^\s*curl\b'
scope = "command"
actions = ["highlight_green", "system_notify:curl request finished"]
```

Output-driven example:

```toml
[[triggers]]
name = "Build error"
pattern = 'ERROR|FAILED|panic'
scope = "output"
actions = ["highlight_red", "bookmark", "system_notify:Build output matched an error"]
```

Supported trigger scopes:

- `command`: match the command line when the block finishes.
- `output`: match block output when the block finishes.
- `both`: match command and output.

Supported action descriptors:

- `highlight`, `highlight_red`, `highlight_green`, `highlight_yellow`, `highlight_blue`, `highlight_magenta`, `highlight_cyan`
- `notify` or `notify:<message>` for Wok's in-app status message
- `system_notify` or `system_notify:<message>` for native desktop notifications
- `bookmark` / `bookmark_block`
- `open_url`
- `copy_match`
- `lua:<hook_name>` / `lua_hook:<hook_name>`

Native macOS and Linux notifications do not expose per-notification color controls, so color is applied inside Wok through trigger highlights. Use one trigger color per workflow class when you want visual grouping in the block timeline.

## Session Files

- Autosave path: `~/.config/wok/session.json`
- Named snapshots: `~/.config/wok/sessions/<name>.json`

The default manual snapshot keybindings are:

- `Mod+Shift+S` to save `manual`
- `Mod+Shift+R` to load `manual`

Named snapshots can also be bound through Lua with action strings like `save_session:demo` and `load_session:demo`.
