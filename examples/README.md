# Examples

This folder contains Swee SG integration examples for Pulse signals, Shield audit review, and lightweight embeddable surfaces.

## Demo Integrations

- `browser-extension/`: page overlay that detects Singapore area names and opens a Swee Pulse preview.
- `spreadsheet-addins/`: Google Sheets and Excel custom functions for Pulse snapshots, signals, and source health.
- `embeddable-widget/`: `<swee-pulse-widget>` web component for dashboards, internal portals, and static pages.

Each demo calls the REST gateway at `http://localhost:3000` by default and uses `/api/v1/pulse/snapshot` for app-level signal data.

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
    "swee-sg": {
      "command": "node",
      "args": ["/absolute/path/to/swee-sg/packages/mcp-server/dist/index.js"]
    }
  }
}
```

Published-package snippet after the first npm release:

```json
{
  "mcpServers": {
    "swee-sg": {
      "command": "npx",
      "args": ["-y", "@swee-sg/shield"]
    }
  }
}
```

## Live Validation

For credential-free onboarding:

```bash
npm run test:smoke:profiles
```

For package and demo checks:

```bash
npm run test:smoke:packaging
npm run browser-extension:check
npm run spreadsheet-addins:check
npm run widget:check
```

## Integration Templates

The integration templates are intentionally small:

- `integration/success-context-ids-template.ts` validates optional success `contextIds`.
- `integration/ui-state-template.ts` maps Pulse and Shield states into frontend banners.
- `integration/backend-worker-template.py` demonstrates dry-run job decisions for Pulse snapshots and Shield failures.
- `integration/queue-consumer-template.py` demonstrates ack/retry/dead-letter handling for source-backed jobs.

Run the template smoke checks with:

```bash
npm run test:smoke:templates
```

Legacy report walkthroughs may remain in this directory until final pruning, but they are not the current product path.
