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
npm run diagnostics
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

## Live Validation

For a credential-gated live validation pass against the built MCP server:

```bash
npm run quick-start
```

Or run just the smoke flow after building:

```bash
npm run test:smoke:live
```

For credential-free onboarding:

```bash
npm run test:smoke:public
```

## Integration Example

`integration/basic-client.ts` is the recommended app-integration starting point. It connects once, caches `sg://recipes`, `sg://runtime`, `sg://playbooks`, and `sg://benchmarks`, runs one covered `sg_query` prompt, demonstrates blocked, unsupported, and failed outcomes, and then drops to direct `sg_*` tools when the caller has exact parameters. It is the current reference for sg_query completed, blocked, unsupported, and failed outcomes:

```bash
npx tsx examples/integration/basic-client.ts
```

`integration/basic-client.py` is the minimal stdlib-only Python variant for teams evaluating the MCP surface from a non-TypeScript stack:

```bash
python3 examples/integration/basic-client.py
```

Production templates:

- `integration/backend-worker-template.ts` for queue or job-runner style execution with explicit blocked/unsupported/failed branching.
- `integration/ui-state-template.ts` for frontend state adapters around `sg_query` status contracts.
- `integration/scheduled-monitor-template.ts` for periodic transport/environment monitoring with escalation tiers.
- `integration/success-context-ids-template.ts` for validating opt-in `structuredContent.contextIds` on successful tool responses.
- `integration/backend-worker-template.py` for Python job-runner services that need deterministic `sg_query` status handling.
- `integration/queue-consumer-template.py` for Python queue consumers with explicit ack/retry/dead-letter routing.

Python template dry-run checks:

```bash
python3 examples/integration/backend-worker-template.py --dry-run
python3 examples/integration/queue-consumer-template.py --dry-run
```

Template smoke checks (CI and local):

```bash
npm run test:smoke:templates
```

Use the prompts in the example files below once the live smoke path passes. The repo keeps regression fixtures under internal test paths, not in the public examples surface.
