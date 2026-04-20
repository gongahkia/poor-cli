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
wok rpc wok.get_failure_trends --params '[0, 3600000, 24]' --socket /tmp/wok.sock
wok rpc wok.setup.init --params '{"overwrite":true}' --socket /tmp/wok.sock
```

Flags:

- `--params`: JSON array/object payload (`null` by default)
- `--socket`: explicit socket path (falls back to `$WOK_SOCKET`)
- `--id`: explicit JSON-RPC id value (defaults to `1`)
- `--notify`: send as notification (no id, no response expected)

See [REMOTE_RPC.md](REMOTE_RPC.md) for supported method contracts.
