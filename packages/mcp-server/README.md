# Dude MCP

Dude MCP is the backend/runtime for Dude's Singapore counterparty due diligence workflows. It exposes stable `sg_*` tools and `sg://...` resources for company/UEN CDD reports, retained sector registry checks, supplemental analyst-review evidence, and runtime operations.

## Install

After the package is public on npm:

```bash
npx -y @swee-sg/shield
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

Core CDD registry tools run without credentials. These optional CDD providers need keys when enabled:

- `TINYFISH_API_KEY` for web presence and people-discovery hints.
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY` for server-side analyst memo generation.
- `OPENSANCTIONS_API_KEY` and `OPENCORPORATES_API_TOKEN` for supplemental external diligence checks.

Use `sg_key_set` for local credential setup when you do not want to export environment variables.

## Release Readiness

Publishing status and dry-run evidence are tracked in [`docs/npm-publish-readiness.md`](../../docs/npm-publish-readiness.md). A public npm release requires an npm account or automation token with publish access to the `@dude` scope, plus the tag-driven release workflow described in [`docs/release.md`](../../docs/release.md).

## Limits

Dude MCP summarizes public data and source-cited evidence. It does not provide legal, tax, credit, investment, AML, sanctions, or licensed compliance advice.
