# Remote Deployment

This repo ships a single-node Docker VPS deployment bundle for Dude as a web product and for Dude MCP's public Streamable HTTP surface.

## Topology

- `caddy` terminates TLS for `https://<public-hostname>`
- `dude-assets` copies the Vite production build into a shared static asset volume
- `caddy` serves the web app from `/` and falls back to `index.html` for client-side routes
- `dude-gateway` serves the REST gateway under `/api/v1`
- `dude-mcp` serves Dude MCP over `/mcp`
- `/.well-known/oauth-protected-resource*`, `/healthz`, and `/icon.svg` are proxied to the same server
- All persistent state (cache, keys, config, artifacts) lives under `SG_APIS_STATE_DIR` (`/var/lib/sg-apis` in the container) on the `dude_mcp_state` Docker volume

## Files

- [`compose.yaml`](../compose.yaml)
- [`Caddyfile`](../Caddyfile)
- [`.env.deploy.example`](../.env.deploy.example)

## First-Time Setup

1. Copy `.env.deploy.example` to `.env.deploy` on the VPS.
2. Replace `PUBLIC_HOSTNAME` with the real hostname that fronts the web app and `/mcp`.
3. Fill in the OIDC issuer and audience for the authorization server that will issue access tokens for this MCP endpoint.
4. Add upstream credentials only for the Singapore API families you actually need. For analyst memos, set `DUDE_AI_PROVIDER` and exactly the matching server-side provider key (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY`).
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
- the normal web deployment uses same-origin REST calls through Caddy, so browser traffic goes to `https://<public-hostname>/api/v1`
- `DUDE_WEB_ORIGIN_ALLOWLIST` may stay empty for the same-origin Caddy deployment; set it to exact origins only if a separate browser origin calls the REST gateway directly
- analyst memo credentials must be present only on `dude-gateway`; never expose provider keys through `VITE_*` browser variables

## Routes

| Public path | Service | Notes |
| --- | --- | --- |
| `/` and app routes | `caddy` static files | Serves `apps/web/dist` from the Docker image via the `dude_web_assets` volume. |
| `/api/v1/*` | `dude-gateway` | REST gateway for the web app, including `/api/v1/health`, `/api/v1/metrics`, and tool POST routes. |
| `/mcp` | `dude-mcp` | Streamable HTTP MCP endpoint. |
| `/healthz`, `/icon.svg`, `/.well-known/oauth-protected-resource*` | `dude-mcp` | MCP deployment metadata and health. |

## Operations

REST gateway health check:

```bash
curl -fsS https://<public-hostname>/api/v1/health
```

MCP health check:

```bash
curl -fsS https://<public-hostname>/healthz
```

Protected-resource metadata:

```bash
curl -fsS https://<public-hostname>/.well-known/oauth-protected-resource/mcp
```

SQLite artifact inspection:

```bash
docker compose exec dude-mcp sh -lc 'sqlite3 /var/lib/sg-apis/artifacts.db "select kind, tool_name, created_at, expires_at from artifacts order by created_at desc limit 20;"'
```

Manual artifact cleanup:

```bash
docker compose exec dude-mcp sh -lc 'sqlite3 /var/lib/sg-apis/artifacts.db "delete from artifacts where expires_at <= strftime(''%s'',''now'') * 1000;"'
```

The server also performs artifact cleanup on startup and once per hour.

## Validation

Repository verification checks that the Dockerfile builds both the MCP/REST runtime and the Vite web app, and that Caddy/Compose keep the `/api/v1` and `/mcp` routes distinct:

```bash
npm run deployment:web:check
```

Container smoke still validates the default MCP stdio image behavior:

```bash
npm run test:smoke:container
```

## GitHub Actions Deploy Job

The manual deploy job expects these repository secrets:

- `DEPLOY_SSH_HOST`
- `DEPLOY_SSH_PORT` optional, defaults to `22`
- `DEPLOY_SSH_USER`
- `DEPLOY_SSH_KEY`
- `DEPLOY_APP_DIR`

Keep `.env.deploy` on the VPS. The workflow only syncs tracked deployment files, pulls the requested GHCR image tag, and runs `docker compose up -d`.
