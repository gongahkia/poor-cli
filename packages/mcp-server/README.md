# @swee-sg/shield

`@swee-sg/shield` is the MCP and REST runtime for Swee SG. It exposes Swee Pulse city signals, Swee Shield audit/policy tools, retained `sg_*` Singapore public-data adapters, and local ops tools.

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

- `swee-sg`: canonical MCP stdio server.
- `swee-shield`: equivalent policy/audit-oriented alias.
- `sg-apis-mcp`: compatibility alias for older local client configs.
- `sg-data`: command-line helper for quick public-data lookups.

## Product Tools

- `swee_pulse_snapshot`
- `swee_pulse_mobility`
- `swee_pulse_weather`
- `swee_pulse_explain`
- `swee_shield_audit_lookup`
- `swee_shield_scan_tools`

## Credentials

Core Pulse weather, source-health, Shield audit, and no-auth public adapters run without credentials. Some upstreams need keys when enabled:

- `SG_API_LTA_KEY` for credential-gated LTA DataMall sources.
- `SG_API_ONEMAP_EMAIL` and `SG_API_ONEMAP_PASSWORD` for OneMap sources that require authentication.
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or `GOOGLE_API_KEY` for optional explain-only AI.

Use `sg_key_set` for local credential setup when you do not want to export environment variables.

## Release Readiness

Publishing status and dry-run evidence are tracked in [`docs/npm-publish-readiness.md`](../../docs/npm-publish-readiness.md). A public npm release requires npm publish access for the `@swee-sg` scope, plus the tag-driven release workflow described in [`docs/release.md`](../../docs/release.md).

## Limits

Swee SG summarizes public source signals and audit metadata. It does not provide legal, tax, credit, investment, AML, sanctions, safety, medical, or licensed compliance advice.
