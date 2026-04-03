# Remote Deployment

This repo now ships a single-node Docker VPS deployment bundle for the public Streamable HTTP MCP surface.

## Topology

- `caddy` terminates TLS for `https://<public-hostname>`
- `sg-apis-mcp` serves MCP over `/mcp`
- `/.well-known/oauth-protected-resource*`, `/healthz`, and `/icon.svg` are proxied to the same server
- All persistent state (cache, keys, config, artifacts) lives under `SG_APIS_STATE_DIR` (`/var/lib/sg-apis` in the container) on the `sg_apis_state` Docker volume

## Files

- [`compose.yaml`](/Users/gongahkia/Desktop/coding/projects/sg-skills/compose.yaml)
- [`Caddyfile`](/Users/gongahkia/Desktop/coding/projects/sg-skills/Caddyfile)
- [`.env.deploy.example`](/Users/gongahkia/Desktop/coding/projects/sg-skills/.env.deploy.example)

## First-Time Setup

1. Copy `.env.deploy.example` to `.env.deploy` on the VPS.
2. Replace `PUBLIC_HOSTNAME` with the real hostname that fronts `/mcp`.
3. Fill in the OIDC issuer and audience for the authorization server that will issue access tokens for this MCP endpoint.
4. Add upstream credentials only for the Singapore API families you actually need.
5. Start the stack:

```bash
docker compose --env-file .env.deploy up -d
```

## Required Runtime Invariants

- `SG_APIS_STATE_DIR` must point to a persistent, writable directory (defaults to `~/.sg-apis` locally, `/var/lib/sg-apis` in compose)
- `SG_APIS_REMOTE_BASE_URL` must resolve to `https://<public-hostname>/mcp`
- `server.json.remotes[0].url` must match that same public `/mcp` URL before a real release
- the protected-resource metadata `resource` value must match the same `/mcp` URL
- `SG_APIS_HTTP_AUTH_MODE` should stay `mixed` for a public deployment unless the server is intentionally private

## Operations

Health check:

```bash
curl -fsS https://<public-hostname>/healthz
```

Protected-resource metadata:

```bash
curl -fsS https://<public-hostname>/.well-known/oauth-protected-resource/mcp
```

SQLite artifact inspection:

```bash
docker compose exec sg-apis-mcp sh -lc 'sqlite3 /var/lib/sg-apis/artifacts.db "select kind, tool_name, created_at, expires_at from artifacts order by created_at desc limit 20;"'
```

Manual artifact cleanup:

```bash
docker compose exec sg-apis-mcp sh -lc 'sqlite3 /var/lib/sg-apis/artifacts.db "delete from artifacts where expires_at <= strftime(''%s'',''now'') * 1000;"'
```

The server also performs artifact cleanup on startup and once per hour.

## GitHub Actions Deploy Job

The manual deploy job expects these repository secrets:

- `DEPLOY_SSH_HOST`
- `DEPLOY_SSH_PORT` optional, defaults to `22`
- `DEPLOY_SSH_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_APP_DIR`

Keep `.env.deploy` on the VPS. The workflow only syncs tracked deployment files, pulls the requested GHCR image tag, and runs `docker compose up -d`.
