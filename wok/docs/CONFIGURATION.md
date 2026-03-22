# Walk Configuration Reference

> Status note: the config schema is ahead of the active runtime in a few places. Today the binary actively uses `shell`, `theme_path`, `font_family`, `font_size`, `scrollback_lines`, and `copy_on_select`. Other keys are parsed and retained for planned UI/runtime surfaces, but are not all visible in the current single-terminal v1.

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

| Option | Type | Default | Runtime Status | Description |
|--------|------|---------|----------------|-------------|
| `shell` | string | auto-detected | Active | Shell to use: `bash`, `zsh`, `fish`, `powershell` |
| `font_family` | string | `"JetBrains Mono"` | Active | Font family name |
| `font_size` | float | `14.0` | Active | Font size in points |
| `input_position` | string | `"bottom"` | Partial | Stored in app state, but the separate input bar is not fully rendered yet |
| `scrollback_lines` | integer | `10000` | Active | Number of scrollback lines to retain |
| `cursor_style` | string | `"block"` | Deferred | Parsed, but the renderer still uses a fixed block-style cursor overlay |
| `cursor_blink` | boolean | `true` | Deferred | Parsed, but blink behavior is not yet surfaced in the active runtime |
| `tab_bar_visible` | boolean | `true` | Deferred | Parsed for planned tab UI |
| `status_bar_visible` | boolean | `true` | Deferred | Parsed for planned status bar UI |
| `window_opacity` | float | `1.0` | Deferred | Parsed, but not yet wired into the live compositor path |
| `copy_on_select` | boolean | `false` | Active | Auto-copy selected text on mouse-up |
| `confirm_close_with_running_process` | boolean | `true` | Deferred | Parsed, but close confirmation is not yet implemented |
| `restore_session` | boolean | `false` | Deferred | Parsed, but session restore is not active in the current runtime |
| `theme_path` | string | none | Active | Path to a custom theme TOML file |
| `background_image` | string | none | Deferred | Parsed by theme/config loaders, not yet in the active runtime surface |
