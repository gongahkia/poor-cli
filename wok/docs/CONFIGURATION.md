# Walk Configuration Reference

Walk is configured via a TOML file located at one of:

1. `$WALK_CONFIG` (environment variable)
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
restore_session = false
theme_path = "~/.config/walk/themes/catppuccin.toml"
```

## Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `shell` | string | auto-detected | Shell to use: `bash`, `zsh`, `fish`, `powershell` |
| `font_family` | string | `"JetBrains Mono"` | Font family name |
| `font_size` | float | `14.0` | Font size in points |
| `input_position` | string | `"bottom"` | Input editor position: `top` or `bottom` |
| `scrollback_lines` | integer | `10000` | Number of scrollback lines to retain |
| `cursor_style` | string | `"block"` | Cursor shape: `block`, `bar`, `underline` |
| `cursor_blink` | boolean | `true` | Whether the cursor blinks |
| `tab_bar_visible` | boolean | `true` | Show the tab bar |
| `status_bar_visible` | boolean | `true` | Show the status bar |
| `window_opacity` | float | `1.0` | Window opacity (0.0-1.0) |
| `copy_on_select` | boolean | `false` | Auto-copy selected text |
| `confirm_close_with_running_process` | boolean | `true` | Confirm before closing with active processes |
| `restore_session` | boolean | `false` | Auto-restore previous session on launch |
| `theme_path` | string | none | Path to a custom theme TOML file |
| `background_image` | string | none | Path to a background image |
