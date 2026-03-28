# Examples

This folder contains eleven walkthroughs: five additive brief outcomes, two recipe-driven discovery flows, and four sector-specific diligence workflows.

- `business-dossier.md`
- `architecture-firm-diligence.md`
- `healthcare-supplier-diligence.md`
- `hotel-operator-lookup.md`
- `sector-scoped-business-diligence.md`
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

Eleven walkthroughs map to built-in demo profiles:

- `npm run demo:mcp -- business`
- `npm run demo:mcp -- property`
- `npm run demo:mcp -- macro`
- `npm run demo:mcp -- transport`
- `npm run demo:mcp -- environment`
- `npm run demo:mcp -- civic`
- `npm run demo:mcp -- geospatial`
- `npm run demo:mcp -- architecture`
- `npm run demo:mcp -- healthcare`
- `npm run demo:mcp -- hotel`
- `npm run demo:mcp -- sector-business`

Every profile reads one resource, calls one direct tool, calls one supporting tool, and then runs the equivalent `sg_query` workflow against the mock upstream server.

## Integration Example

`integration/basic-client.ts` is the recommended app-integration starting point. It connects once, caches `sg://recipes`, `sg://runtime`, `sg://playbooks`, and `sg://benchmarks`, runs one covered `sg_query` prompt, demonstrates blocked, unsupported, and failed outcomes, and then drops to direct `sg_*` tools when the caller has exact parameters:

```bash
npx tsx examples/integration/basic-client.ts
```

`integration/basic-client.py` is the minimal stdlib-only Python variant for teams evaluating the MCP surface from a non-TypeScript stack:

```bash
python3 examples/integration/basic-client.py
```

## Golden Outputs

`golden-outputs/` contains realistic JSON fixtures for each brief tool plus sg_query completed, blocked, unsupported, and failed outcomes, along with sector-specific diligence outcomes, useful as reference for expected output shapes, believable headline fields, and contract semantics.

## Quick Start

Run one brief workflow end-to-end in under 5 minutes:

```bash
node scripts/quick-start.mjs property
```
