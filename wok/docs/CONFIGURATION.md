# Wok Configuration Reference

Wok is configured via a TOML file located at one of:

1. `$WOK_CONFIG`
2. `~/.config/wok/config.toml`
3. `~/.wok.toml`

You can scaffold managed defaults with:

```bash
wok init
```

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
recent_keys_visible = true
recent_keys_position = "bottom_right"
recent_keys_max_entries = 8
recent_keys_timeout_ms = 2000
recent_keys_opacity = 0.86
copy_on_select = false
confirm_close_with_running_process = true
close_on_shell_exit = true
restore_session = true
debug_overlay = false
command_telemetry = false
theme_path = "~/.config/wok/themes/catppuccin.toml"
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
| `recent_keys_visible` | boolean | `true` | Active | Shows a local in-app recent-key visualizer; keys are not persisted |
| `recent_keys_position` | string | `"bottom_right"` | Active | Places the recent-key visualizer at `top_left`, `top_right`, `bottom_left`, or `bottom_right` |
| `recent_keys_max_entries` | integer | `8` | Active | Maximum number of recent key labels shown, capped at 64 |
| `recent_keys_timeout_ms` | integer | `2000` | Active | Time in milliseconds before a key label expires, clamped to 250..30000 |
| `recent_keys_opacity` | float | `0.86` | Active | Recent-key overlay opacity from `0.0` to `1.0` |
| `copy_on_select` | boolean | `false` | Active | Auto-copy selected text on mouse-up |
| `confirm_close_with_running_process` | boolean | `true` | Active | Requires a second close request within 2 seconds when panes still have running shell processes |
| `close_on_shell_exit` | boolean | `true` | Active | Closes the exited pane, closes an all-exited tab when other tabs remain, or exits Wok when the final shell exits |
| `restore_session` | boolean | `false` | Active | Loads the autosaved workspace session on startup |
| `debug_overlay` | boolean | `false` | Active | Shows a benchmark overlay with FPS, redraw time, phase timings, CPU, memory, disk, GPU adapter/render diagnostics, battery when available, scrollback, and session memory |
| `command_telemetry` | boolean | `false` | Active | Writes opt-in command lifecycle telemetry to `~/.config/wok/command-telemetry.jsonl`; command text is included, so avoid enabling it for secret-bearing workflows |
| `theme_path` | string | none | Active | Path to a custom theme TOML file |
| `background_image` | string | none | Active | Loads a background image from config or theme and renders it behind the workspace chrome and panes |
| `external_plugin_command` | string | none | Active | Optional out-of-process plugin bridge command; receives hook/event JSON lines on stdin and can emit typed effects (`notify`, `exec`, `action`) on stdout |

## Session Files

- Autosave path: `~/.config/wok/session.json`
- Named snapshots: `~/.config/wok/sessions/<name>.json`

The default manual snapshot keybindings are:

- `Mod+Shift+S` to save `manual`
- `Mod+Shift+R` to load `manual`

Named snapshots can also be bound through Lua with action strings like `save_session:demo` and `load_session:demo`.
