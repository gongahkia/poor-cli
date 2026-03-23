# Walk Configuration Reference

Walk is configured via a TOML file located at one of:

1. `$WALK_CONFIG`
2. `~/.config/walk/config.toml`
3. `~/.walk.toml`

## Full Example

```toml
shell = "zsh"
font_family = "JetBrains Mono"
font_size = 14.0
input_position = "bottom"
scrollback_lines = 10000
cursor_style = "block"
cursor_blink = true
tab_bar_visible = true
status_bar_visible = true
window_opacity = 1.0
copy_on_select = false
confirm_close_with_running_process = true
restore_session = true
theme_path = "~/.config/walk/themes/catppuccin.toml"
```

## Options

| Option | Type | Default | Runtime Status | Description |
| --- | --- | --- | --- | --- |
| `shell` | string | auto-detected | Active | Shell to use: `bash`, `zsh`, `fish`, `powershell`, or `wsl:<distro>` |
| `font_family` | string | `"JetBrains Mono"` | Active | Selects the font family used for glyph rasterization and cell metric measurement |
| `font_size` | float | `14.0` | Active | Font size in points |
| `input_position` | string | `"bottom"` | Active | Places the owned input bar above or below the viewport |
| `scrollback_lines` | integer | `10000` | Active | Number of scrollback lines to retain |
| `cursor_style` | string | `"block"` | Active | Chooses the cursor shape for both the terminal viewport and owned input bar: `block`, `bar`, or `underline` |
| `cursor_blink` | boolean | `true` | Active | Enables the timed cursor blink cadence for the viewport and input bar |
| `tab_bar_visible` | boolean | `true` | Active | Shows or hides the workspace tab bar |
| `status_bar_visible` | boolean | `true` | Active | Shows or hides the status bar |
| `window_opacity` | float | `1.0` | Active | Applies window/chrome opacity and blends terminal surfaces against the configured background |
| `copy_on_select` | boolean | `false` | Active | Auto-copy selected text on mouse-up |
| `confirm_close_with_running_process` | boolean | `true` | Active | Requires a second close request within 2 seconds when panes still have running shell processes |
| `restore_session` | boolean | `false` | Active | Loads the autosaved workspace session on startup |
| `debug_overlay` | boolean | `false` | Active | Shows a small internal overlay with redraw timing, atlas occupancy, scrollback depth, and approximate session memory |
| `theme_path` | string | none | Active | Path to a custom theme TOML file |
| `background_image` | string | none | Active | Loads a background image from config or theme and renders it behind the workspace chrome and panes |

## Session Files

- Autosave path: `~/.config/walk/session.json`
- Named snapshots: `~/.config/walk/sessions/<name>.json`

The default manual snapshot keybindings are:

- `Mod+Shift+S` to save `manual`
- `Mod+Shift+R` to load `manual`

Named snapshots can also be bound through Lua with action strings like `save_session:demo` and `load_session:demo`.
