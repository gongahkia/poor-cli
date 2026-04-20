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
wok reset --yes
```

Optional full state cleanup:

```bash
wok reset --all --yes
```

`--all` also removes:

- `session.json`
- `sessions/`
- `themes/`
- `workflows/`

