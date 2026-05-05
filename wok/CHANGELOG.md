# Changelog

All notable user-visible changes to Wok and its Lua API are recorded here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the **Lua API** follows independent semantic versioning per [`docs/LUA_API_STABILITY.md`](docs/LUA_API_STABILITY.md). Wok-the-binary still tracks its own version in `Cargo.toml`; this file documents both the binary and the API surface it ships.

## [Unreleased]

### Added
- _Track here as features land before the next release._

### Changed
- `wok.api_version` is now `"1.1.0"`.

### Deprecated
- `wok.keymap(...)` is deprecated; use `wok.bind_key(...)`.
- `wok.action(id)` is deprecated; use `wok.run_action(id)`.

### Removed
- _Track removals here._

### Fixed
- _Track fixes here._

### Security
- _Track security-relevant changes here._

---

## [1.0.0] — Lua API baseline

This is the v1.0 commitment for the Lua plugin surface. Everything below is covered by the stability policy in `docs/LUA_API_STABILITY.md` and pinned by `wok-app/tests/lua_hook_payloads.rs` + `wok-app/src/scripting.rs::tests`.

The wok binary ships at version `0.1.0` (per `Cargo.toml`); the API version (`wok.api_version`) ships at `1.0.0`. The two are intentionally decoupled so the Lua surface can stabilise faster than the application.

### Added — Lua namespaces

- `wok.config` — read-only runtime config snapshot.
- `wok.api_version` — string `"1.0.0"`. Plugins should pin a minimum.
- `wok.bind_key(mode, key, action)` / `wok.keymap(...)` — register a hotkey.
- `wok.register_command(name, action_or_fn)` — alias bound to a built-in or Lua callback.
- `wok.on(event, fn)` — lifecycle hook listener. Events covered: `app_start`, `app_exit`, `tab_opened`, `pane_opened`, `command_submitted`, `block_finished`, `pane_exited`, `tab_done`, `cwd_changed`.
- `wok.run_action(id)` / `wok.action(id)` — queue a built-in action.
- `wok.exec(command)` — run a shell command in the focused pane.
- `wok.notify(message)` — in-app status bar message.
- `wok.system_notify(string|table)` — native desktop notification.
- `wok.app()` / `wok.workspace()` / `wok.pane()` / `wok.session()` — runtime state snapshots.
- `wok.history.entries()` / `wok.history.search(query)` — last 200 global history entries with substring search.
- `wok.blocks.list()` — last 100 blocks of the active pane.
- `wok.tabs.{new, close, next, prev, switch}` — tab manipulation.
- `wok.panes.{split_vertical, split_horizontal, close, focus_left, focus_right, focus_up, focus_down, new_floating, toggle_floating}` — pane manipulation.
- `wok.pane_api.{send_input, info}` — PTY input injection + pane snapshot.
- `wok.window.{set_title, toggle_fullscreen, set_opacity}` — window control.
- `wok.clipboard.{copy, paste}` — system clipboard.
- `wok.fs.{read, write, exists, list}` — sandboxed filesystem ops scoped to `~/.config/wok/data/` and `~/.local/share/wok/`.
- `wok.add_trigger(name, pattern, actions)` / `wok.remove_trigger(name)` — regex triggers.
- `wok.register_workflow(spec)` / `wok.workflows()` — parameterised workflows.
- `wok.quick_select.{add_pattern, remove_pattern}` — custom quick-select regexes.
- `wok.status_bar.{set_left, set_center, set_right, clear, set_refresh_interval}` — status bar customisation.
- `wok.theme.{set, load}` — theme overrides + load by name/path.
- `wok.setup.{init, doctor, reset, shell_install, shell_rollback}` — programmatic CLI equivalents.
- `wok.set_timeout(ms, fn)` / `wok.set_interval(ms, fn)` / `wok.clear_timer(id)` — timers.

### Added — Plugin SDK assets

- `docs/LUA_SCRIPTING.md` — prose API reference with quick-reference table, per-namespace docs, four reusable patterns, hook payload table.
- `docs/wok.d.lua` — LuaCATS type definitions covering every function, namespace, hook payload, and snapshot field. Every declaration carries `---@since 1.0.0`.
- `docs/LUA_API_STABILITY.md` — versioning model, deprecation policy, contributor checklist.
- `docs/examples/minimal.lua`, `docs/examples/full.lua`, `docs/examples/powerful.lua` — copy-paste starting points.
- `wok-app/tests/lua_hook_payloads.rs` — 12 integration tests pinning every documented hook event payload schema.

### Added — Wok binary features (in scope of the 1.0 SDK baseline)

- TOML keybindings at `~/.config/wok/keybindings.toml` with hot-reload.
- Theme picker palette (`Action::ThemePicker`).
- Keybinding discovery palette (`Action::KeybindingDiscovery`).
- Settings field discovery palette (`Action::SettingsDiscovery`).
- `wok onboard` 4-step guided setup CLI.
- `wok bug-report` diagnostics bundler CLI.
- `wok replay` wokcast playback CLI.
- iTerm2 OSC 1337 inline image protocol support.
- Live `config.toml` reload via filesystem watcher.
- `wok doctor` reports per-shell capability matrix.

### Notes

- The wok binary version is independent of the Lua API version. Future binaries may ship newer API minors without bumping the binary major.
- The pre-1.0 deltas in `tab_opened` / `pane_opened` payload documentation (see commit `f266c6b`) are grandfathered as a documentation bug — the implementation always emitted the full pane payload.

---

[Unreleased]: https://github.com/gongahkia/wok/compare/lua-api-1.0.0...HEAD
[1.0.0]: https://github.com/gongahkia/wok/releases/tag/lua-api-1.0.0
