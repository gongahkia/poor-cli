# Ecosystem Snapshot

## Why this exists

Repository-local audits are useful but insufficient in a fast-moving MCP market.
This repo now includes a machine-readable ecosystem snapshot so maintainers can compare
local surface quality with live external signals from GitHub, npm, and Stack Overflow.

## Command

Run after build:

```bash
npm run build
npm run ecosystem:snapshot
```

Optional output path:

```bash
npm run ecosystem:snapshot -- --output artifacts/ecosystem/custom.json
```

Optional history directory:

```bash
npm run ecosystem:snapshot -- --history-dir artifacts/ecosystem/history
```

Default output:

`artifacts/ecosystem/latest.json`

Default history directory:

`artifacts/ecosystem/history/<timestamp>.json`

## What gets captured

- local surface shape from built catalog:
  - tool, family, workflow, and recipe counts
  - routed-family count for `sg_query`
  - additive brief inventory
  - test-file reference coverage per tool
- GitHub repository telemetry:
  - MCP ecosystem baselines
  - selected Singapore-focused MCP servers
- npm distribution telemetry:
  - package existence
  - latest version
  - creation and modified dates
  - last-30-day downloads
- Stack Overflow MCP telemetry:
  - `model-context-protocol` tag question count
  - latest and top-voted tagged questions
- GitHub search snapshot for Singapore MCP repositories

## Notes

- The script uses unauthenticated public APIs by default.
- Set `GITHUB_TOKEN` to avoid stricter GitHub API limits.
- The snapshot is intended as directional product evidence, not a benchmark SLA.
- `trendComparedToPrevious` compares core local-surface counts with the previous `latest.json`.
