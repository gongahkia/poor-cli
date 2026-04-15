# Configuration

This page documents `gocli-poor` TUI config. Backend config for `poor-cli-server` is separate and lives at `~/.poor-cli/config.yaml`.

## Load Order

First file found wins:

1. `$XDG_CONFIG_HOME/gocli-poor/config.yaml`
2. `~/.config/gocli-poor/config.yaml`
3. `~/.gocli-poor.yaml`

Then env vars override file values.

## Example

```yaml
theme:
  name: dark
server_path: /opt/bin/poor-cli-server
default_provider: anthropic
default_model: claude-4-6-sonnet
context_budget_tokens: 180000
max_response_tokens: 8192
auto_accept_safe_edits: true
history_file: ~/.local/share/gocli-poor/history
log_level: info
keybindings:
  submit: ctrl+enter
  cancel: ctrl+c,esc
  palette: /
  mention: "@"
  focus.chat: ctrl+j
  focus.input: ctrl+i
  scroll.up: pgup
  scroll.down: pgdn
  scroll.top: home
  scroll.bottom: end
  accept.edit: ctrl+y
  reject.edit: ctrl+n
  regen.edit: ctrl+r
  quit: ctrl+q
```

## Fields

| Field | Type | Default | Env | Description |
|---|---|---|---|---|
| `theme` | string or map | `dark` | `GOCLI_POOR_THEME` | Theme name or inline theme map. |
| `theme.name` | string | `dark` | `GOCLI_POOR_THEME` | Theme name when `theme` is a map. |
| `theme.<style>` | string | none | none | Inline theme style token override. |
| `server_path` | string | empty | `GOCLI_POOR_SERVER_PATH`, `POOR_CLI_SERVER_PATH` | Explicit backend executable path. Empty searches `poor-cli-server`, then `poor-cli`. |
| `default_provider` | string | `anthropic` | `GOCLI_POOR_DEFAULT_PROVIDER` | Provider sent during startup/default state. |
| `default_model` | string | `claude-4-6-sonnet` | `GOCLI_POOR_DEFAULT_MODEL` | Model sent during startup/default state. |
| `context_budget_tokens` | int | `180000` | `GOCLI_POOR_CONTEXT_BUDGET_TOKENS` | Context budget displayed and sent with chat requests. Must be positive. |
| `max_response_tokens` | int | `8192` | `GOCLI_POOR_MAX_RESPONSE_TOKENS` | Response cap for chat requests. Must be positive. |
| `auto_accept_safe_edits` | bool | `true` | `GOCLI_POOR_AUTO_ACCEPT_SAFE_EDITS` | Auto-accept edits marked safe by the backend. |
| `history_file` | string | `~/.local/share/gocli-poor/history` | `GOCLI_POOR_HISTORY_FILE` | Prompt history path. |
| `log_level` | enum | `info` | `GOCLI_POOR_LOG_LEVEL` | One of `debug`, `info`, `warn`, `error`. |
| `keybindings` | map | see below | per-action env vars | Action-to-key mapping. |

## Keybinding Fields

| Field | Default | Env |
|---|---|---|
| `keybindings.submit` | `ctrl+enter` | `GOCLI_POOR_KEYBINDINGS_SUBMIT` |
| `keybindings.cancel` | `ctrl+c,esc` | `GOCLI_POOR_KEYBINDINGS_CANCEL` |
| `keybindings.palette` | `/` | `GOCLI_POOR_KEYBINDINGS_PALETTE` |
| `keybindings.mention` | `@` | `GOCLI_POOR_KEYBINDINGS_MENTION` |
| `keybindings.focus.chat` | `ctrl+j` | `GOCLI_POOR_KEYBINDINGS_FOCUS_CHAT` |
| `keybindings.focus.input` | `ctrl+i` | `GOCLI_POOR_KEYBINDINGS_FOCUS_INPUT` |
| `keybindings.scroll.up` | `pgup` | `GOCLI_POOR_KEYBINDINGS_SCROLL_UP` |
| `keybindings.scroll.down` | `pgdn` | `GOCLI_POOR_KEYBINDINGS_SCROLL_DOWN` |
| `keybindings.scroll.top` | `home` | `GOCLI_POOR_KEYBINDINGS_SCROLL_TOP` |
| `keybindings.scroll.bottom` | `end` | `GOCLI_POOR_KEYBINDINGS_SCROLL_BOTTOM` |
| `keybindings.accept.edit` | `ctrl+y` | `GOCLI_POOR_KEYBINDINGS_ACCEPT_EDIT` |
| `keybindings.reject.edit` | `ctrl+n` | `GOCLI_POOR_KEYBINDINGS_REJECT_EDIT` |
| `keybindings.regen.edit` | `ctrl+r` | `GOCLI_POOR_KEYBINDINGS_REGEN_EDIT` |
| `keybindings.quit` | `ctrl+q` | `GOCLI_POOR_KEYBINDINGS_QUIT` |

Full key syntax: [keybindings.md](./keybindings.md).

## Env-Only Runtime Controls

| Env | Description |
|---|---|
| `POOR_CLI_SERVER_PATH` | Backend executable path. Same effect as `server_path`, with env precedence. |
| `POOR_CLI_SERVER_LOG_FILE` | File where backend stderr is appended. |
| `NO_COLOR` | Force monochrome output. |
| `COLORTERM=truecolor` or `COLORTERM=24bit` | Enable truecolor theme capability. |
| `TERM=xterm-256color` | Enable 256-color fallback. |

## Validation

- Unknown keybinding actions fail startup.
- Unknown key names fail startup.
- `context_budget_tokens` and `max_response_tokens` must be positive integers.
- `log_level` must be `debug`, `info`, `warn`, or `error`.
- Env var validation errors do not include file line numbers.
- YAML file validation errors include source line numbers when available.

## Backend Config

Backend config is managed by `poor-cli-server`:

```sh
poor-cli config
poor-cli config list
poor-cli config get model.provider
poor-cli config set model.provider anthropic
```

Backend docs:

- [Providers](./PROVIDERS.md)
- [Economy](./ECONOMY.md)
- [MCP](./MCP.md)
- [Sandbox](./SANDBOX.md)
- [Multiplayer](./MULTIPLAYER.md)
