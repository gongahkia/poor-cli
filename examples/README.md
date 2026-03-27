# Examples

This folder contains seven runnable walkthroughs: five additive brief outcomes plus two recipe-driven discovery flows.

- `business-dossier.md`
- `property-brief.md`
- `macro-brief.md`
- `transport-brief.md`
- `environment-brief.md`
- `civic-discovery.md`
- `geospatial-routing.md`

## Local Client Snippets

Build the server first:

```bash
npm install
npm run build
```

Claude Desktop or Codex-style clients:

```json
{
  "mcpServers": {
    "sg-apis-mcp": {
      "command": "node",
      "args": ["/absolute/path/to/sg-skills/packages/mcp-server/dist/index.js"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add sg-apis-mcp -- node /absolute/path/to/sg-skills/packages/mcp-server/dist/index.js
```

Published-package snippet after the first npm release:

```json
{
  "mcpServers": {
    "sg-apis-mcp": {
      "command": "npx",
      "args": ["-y", "sg-apis-mcp"]
    }
  }
}
```

## Runnable Demo Profiles

Each example file maps to one built-in profile:

- `npm run demo:mcp -- business`
- `npm run demo:mcp -- property`
- `npm run demo:mcp -- macro`
- `npm run demo:mcp -- transport`
- `npm run demo:mcp -- environment`
- `npm run demo:mcp -- civic`
- `npm run demo:mcp -- geospatial`

Every profile reads one resource, calls one direct tool, calls one supporting tool, and then runs the equivalent `sg_query` workflow against the mock upstream server.

## Integration Example

`integration/basic-client.ts` is the recommended app-integration starting point. It connects once, caches `sg://recipes`, runs one covered `sg_query` prompt, demonstrates both blocked and unsupported outcomes, and then drops to direct `sg_*` tools when the caller has exact parameters:

```bash
npx tsx examples/integration/basic-client.ts
```

## Golden Outputs

`golden-outputs/` contains realistic JSON fixtures for each brief tool, useful as reference for expected output shapes and field values.

## Quick Start

Run one brief workflow end-to-end in under 5 minutes:

```bash
node scripts/quick-start.mjs property
```
