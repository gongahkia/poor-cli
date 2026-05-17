# Dude MCP

Dude MCP is the backend/runtime for Dude's bounded Singapore public-data and due-diligence workflows. It exposes stable `sg_*` tools and `sg://...` resources for official public datasets, registry checks, maps, live signals, and agent-ready brief workflows.

## Install

After the package is public on npm:

```bash
npx -y @dude/mcp
```

Local development from the repo:

```bash
npm install
npm run build
node packages/mcp-server/dist/index.js
```

## Executables

- `dude-mcp`: canonical MCP stdio server.
- `sg-apis-mcp`: compatibility alias for older local client configs.
- `sg-data`: command-line helper for quick public-data lookups.

## Credentials

Most public-data families run without credentials. These optional upstreams need keys:

- `SG_API_ONEMAP_EMAIL` and `SG_API_ONEMAP_PASSWORD` for OneMap.
- `SG_API_URA_KEY` for URA.
- `SG_API_LTA_KEY` for LTA DataMall.

Use `sg_key_set` or `sg-data init` for local credential setup when you do not want to export environment variables.

## Release Readiness

Publishing status and dry-run evidence are tracked in [`docs/npm-publish-readiness.md`](../../docs/npm-publish-readiness.md). A public npm release requires an npm account or automation token with publish access to the `@dude` scope, plus the tag-driven release workflow described in [`docs/release.md`](../../docs/release.md).

## Limits

Dude MCP summarizes public data and source-cited evidence. It does not provide legal, tax, credit, investment, AML, sanctions, or licensed compliance advice.
