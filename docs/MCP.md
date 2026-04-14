# MCP Guide

How to load custom [Model Context Protocol](https://modelcontextprotocol.io) servers into `poor-cli`.

poor-cli is **MCP 2026-compliant**: it supports both `stdio` and `Streamable HTTP` transports, multi-server tool namespacing, registry autodiscovery (opt-in), and per-server allow/deny lists.

## Config File Locations

poor-cli searches these paths in order (first match wins):

1. `./.poor-cli/mcp.json` — repo-local (recommended for project-specific servers)
2. `./.claude/mcp.json` — Claude-compat (same schema; reused for interop)
3. `~/.poor-cli/mcp.json` — user-global (shared across projects)

No `mcp.json` = no MCP tools loaded. The file is pure JSON; no env-var interpolation at the config layer, but you can pass env vars into each server's `env` block (see schema below).

## Minimal Example

```json
{
  "multi": true,
  "registry_autodiscover": false,
  "servers": [
    {
      "name": "github",
      "transport": "stdio",
      "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" },
      "enabled": true
    }
  ]
}
```

- `multi: true` — keep tool namespacing (`<server>:<tool>`). Strongly recommended when you have >1 server.
- `registry_autodiscover: false` — do **not** pull from the official MCP registry by default. Flip to `true` only on demand (see below).
- `servers: [...]` — array of server specs. Can also be a dict keyed by name.

## Server Spec Schema

Every entry under `servers` accepts:

| Field | Type | Required | Description |
|---|---|---|---|
| `name` | string | yes | Unique identifier; used as the prefix in `<server>:<tool>` namespacing. |
| `transport` | `"stdio"` \| `"http"` | no (default `stdio`) | Transport layer. |
| `command` | string[] | stdio only | argv array that launches the server process. |
| `url` | string | http only | Streamable HTTP endpoint (e.g. `http://127.0.0.1:3333/mcp`). |
| `env` | object | no | Environment vars passed to stdio children; values can reference shell env via `${VAR_NAME}`. |
| `headers` | object | http only | HTTP headers sent on every request (use for auth bearer tokens). |
| `enabled` | bool | no (default `true`) | Set `false` to register the server config without activating it. |
| `allow_tools` | string[] | no | Whitelist of tool names the agent can invoke from this server. Overrides `deny_tools`. |
| `deny_tools` | string[] | no | Blacklist. Applied after `allow_tools` if both exist. |

## Common Server Examples

### stdio — GitHub

```json
{
  "name": "github",
  "transport": "stdio",
  "command": ["npx", "-y", "@modelcontextprotocol/server-github"],
  "env": { "GITHUB_TOKEN": "${GITHUB_TOKEN}" },
  "enabled": true
}
```

### stdio — Filesystem (scoped)

```json
{
  "name": "fs",
  "transport": "stdio",
  "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/Users/me/work"],
  "enabled": true,
  "deny_tools": ["write_file", "delete_file"]
}
```

### Streamable HTTP — local docs server

```json
{
  "name": "docs",
  "transport": "http",
  "url": "http://127.0.0.1:3333/mcp",
  "headers": { "Authorization": "Bearer ${DOCS_TOKEN}" },
  "enabled": true
}
```

### Disabled staging server (keeps config, does not connect)

```json
{
  "name": "staging",
  "transport": "http",
  "url": "http://staging.internal/mcp",
  "enabled": false
}
```

## Tool Namespacing

When `multi: true` (default), all tools are registered as `<server>:<tool>`. Example:

- `github:create_issue`
- `fs:read_file`
- `docs:search_corpus`

This prevents name collisions across servers and lets allow/deny lists target specific tools precisely.

## Registry Autodiscovery

Off by default. To enable discovery from `https://registry.modelcontextprotocol.io/`:

**Per-project** (`.poor-cli/mcp.json`):
```json
{ "registry_autodiscover": true, "servers": [] }
```

**Globally** (in `~/.poor-cli/config.yaml`):
```yaml
mcp:
  registry:
    enabled: true
```

Registry autodiscovery adds servers advertised in your organization/account registry automatically. Leave OFF if you want deterministic, reproducible tool availability.

## Verifying Servers

```
:PoorCLIMcp            " full-screen server browser
/mcp-health            " slash command in chat
```

`:PoorCLIMcp` shows: connection status, tool count, last-error, per-server badges, and lets you toggle/edit/remove/health-check/test-tool a server interactively.

## Debugging

- Missing server in `/mcp list`? Check `poor-cli-server` logs (stderr) for `discovered MCP config at <path>` and parse errors.
- `enabled: false` swallows a server silently; confirm with `/mcp list` which shows disabled specs.
- stdio server hung on start → check `env` values are set (remember `${VAR}` is evaluated at shell level before JSON parsing, so pass them via your shell env).
- HTTP server returning 4xx → verify headers and URL; Streamable HTTP expects the `/mcp` endpoint to respond to `initialize` before `tools/list`.

## Security

- Prefer `deny_tools` over `allow_tools` when you want "almost everything, minus these dangerous ones."
- Prefer `allow_tools` when you want a hard allowlist.
- The Trust Center (`:PoorCLITrustCenter`) shows which MCP tools are currently allowed, per server.
- Audit logs capture every MCP tool invocation (see `docs/phase_11_security_hardening.md` for audit retention).

## See Also

- [phase_13_protocol_streaming.md](./phase_13_protocol_streaming.md) — streaming protocol internals
- [phase_15_nvim_navigator_panels.md](./phase_15_nvim_navigator_panels.md) — `:PoorCLIMcp` UX spec
