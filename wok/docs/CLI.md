# Wok CLI Reference

## `wok init`

Initialize managed files in `~/.config/wok`:

- `config.toml`
- `init.lua`
- `shell/bash.sh`
- `shell/zsh.zsh`
- `shell/fish.fish`

```bash
wok init
wok init --overwrite
```

## `wok doctor`

Run local diagnostics for config and shell integration state.

```bash
wok doctor
wok doctor --json
```

The doctor checks:

- config directory presence
- `config.toml` presence and TOML parseability
- `init.lua` presence
- managed shell script presence
- first-run marker presence

## `wok reset`

Reset managed files created by init/first-run bootstrap.

```bash
wok reset --scope managed --yes
```

State-only cleanup:

```bash
wok reset --scope state --yes
```

Full cleanup:

```bash
wok reset --scope all --yes
```

`state` and `all` remove:

- `session.json`
- `sessions/`
- `themes/`
- `workflows/`

## `wok shell install`

Wire shell startup files to source Wok-managed integration scripts.

```bash
wok shell install --shell zsh
wok shell install --shell fish
wok shell install --shell bash
wok shell install --shell auto
```

`install` creates a backup of the target startup file (`*.wok.bak`) and stores rollback metadata under `~/.config/wok/shell/install_state.json`.

## `wok shell rollback`

Restore shell startup files from the most recent `wok shell install`.

```bash
wok shell rollback --yes
```

## `wok rpc`

Send a single JSON-RPC request to a running Wok remote-control socket.

```bash
wok rpc wok.get_panes --socket /tmp/wok.sock
wok rpc wok.get_rpc_info --socket /tmp/wok.sock
wok rpc wok.get_failure_trends --params '[0, 3600000, 24]' --socket /tmp/wok.sock
wok rpc wok.setup.init --params '{"overwrite":true}' --socket /tmp/wok.sock
```

Flags:

- `--params`: JSON array/object payload (`null` by default)
- `--socket`: explicit socket path (falls back to `$WOK_SOCKET`)
- `--token`: optional RPC auth token (falls back to `$WOK_RPC_TOKEN`)
- `--id`: explicit JSON-RPC id value (defaults to `1`)
- `--notify`: send as notification (no id, no response expected)

See [REMOTE_RPC.md](REMOTE_RPC.md) for supported method contracts.

## `wok git-status`

Print the active pane's Git status snapshot by calling `wok.get_git_status` on a running Wok instance.

```bash
wok git-status --socket /tmp/wok.sock
wok git-status --pane-id 3 --socket /tmp/wok.sock
```

Flags:

- `--pane-id`: optional pane id (defaults to the active pane)
- `--socket`: explicit socket path (falls back to `$WOK_SOCKET`)
- `--token`: optional RPC auth token (falls back to `$WOK_RPC_TOKEN`)

## `wok workspace`

Manage named workspace snapshots from a shell connected to a running Wok instance.

```bash
wok workspace save backend
wok workspace load backend
wok workspace list
```

`save` and `load` call the running app through `wok.run_action`, so they use `--socket` or `$WOK_SOCKET` and optional `--token` or `$WOK_RPC_TOKEN`. Session JSON now includes lightweight metadata (`schema_version`, `saved_at_unix_ms`, `wok_version`, `workspace_description`, and `workspace_tags`) so saved workspaces are easier to inspect outside Wok and in the command-palette workspace browser.

Wok also supports Kitty graphics, Sixel, and iTerm image escape sequences for inline terminal image output, plus built-in file previews for images, GIFs, MP4/M4V, and bounded text/code previews. GIF and MP4 previews can be paused/resumed from the command palette or default keybinding; MP4 previews also expose seek, speed, frame-step, and mute actions.
