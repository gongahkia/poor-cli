# Wok Remote RPC Contract

Wok exposes a JSON-RPC 2.0 surface over the remote-control socket (`$WOK_SOCKET` or `wok rpc --socket ...`).

Methods accept either array params (`[value0, value1, ...]`) or object params (`{"key": value}`) where documented.

When `WOK_RPC_TOKEN` is set in the Wok server process environment, all methods except `wok.get_rpc_info` require `auth_token` in the JSON-RPC envelope (or `--token` / `$WOK_RPC_TOKEN` via `wok rpc`).

## RPC Introspection

### `wok.get_rpc_info`

- Params: none
- Response:
  - `schema_version` (string)
  - `methods` (string array)
  - `auth_required` (bool)

## Setup Lifecycle Methods

### `wok.setup.init`

- Params:
  - `overwrite` (`bool`, default `false`)
- Example:

```json
{"method":"wok.setup.init","params":{"overwrite":true}}
```

### `wok.setup.doctor`

- Params:
  - `json` (`bool`, default `true`)
- Example:

```json
{"method":"wok.setup.doctor","params":{"json":true}}
```

### `wok.setup.reset`

- Params:
  - `scope` (`"managed" | "state" | "all"`, default `"managed"`)
  - `yes` (`bool`, default `false`)
- Example:

```json
{"method":"wok.setup.reset","params":{"scope":"state","yes":true}}
```

### `wok.setup.shell_install`

- Params:
  - `shell` (`"auto" | "bash" | "zsh" | "fish"`, optional)
  - `overwrite` (`bool`, default `false`)
- Example:

```json
{"method":"wok.setup.shell_install","params":{"shell":"zsh","overwrite":false}}
```

### `wok.setup.shell_rollback`

- Params:
  - `shell` (`"bash" | "zsh" | "fish"`, optional)
  - `yes` (`bool`, default `false`)
- Example:

```json
{"method":"wok.setup.shell_rollback","params":{"shell":"zsh","yes":true}}
```

## Failure Analytics Methods

### `wok.get_failure_summary`

- Params:
  - `pane_id` (`u64`, required)
- Response:
  - array of `{command, count, last_exit_code, last_completed_at_ms}`

### `wok.get_failure_trends`

- Params:
  - `pane_id` (`u64`, required)
  - `bucket_ms` (`u64`, optional, default `3600000`, min clamp `60000`)
  - `limit` (`u64`, optional, default `24`, clamp `1..=250`)
- Response:
  - array of `{command, cwd, branch, bucket_start_ms, count, last_exit_code, last_completed_at_ms}`

## Lua Contract Mapping

Lua setup APIs map directly to the setup RPC behavior:

- `wok.setup.init({ overwrite = ... })`
- `wok.setup.doctor({ json = ... })`
- `wok.setup.reset({ scope = ..., yes = ... })`
- `wok.setup.shell_install({ shell = ..., overwrite = ... })`
- `wok.setup.shell_rollback({ shell = ..., yes = ... })`

Failure trends in Lua action routing:

- `wok.run_action("toggle_failure_trends_panel")`
- Alias: `wok.run_action("failure_trends")`

## Machine-Readable Schema

- [REMOTE_RPC_SCHEMA_V1.json](REMOTE_RPC_SCHEMA_V1.json)
