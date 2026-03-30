# Troubleshooting Runbook

Use this when `sg_query` or direct `sg_*` tools fail, block, or return unexpected results.

## Fast Triage (Under Five Minutes)

1. Build + static diagnostics

```bash
npm run build
npm run diagnostics
```

2. Runtime health sweep

Call:

```text
sg_health_check {}
```

3. Cache and config sanity

```text
sg_cache_stats {}
sg_config_get {}
```

4. Re-run the failing call with logs enabled

```bash
SG_APIS_LOG_LEVEL=debug node packages/mcp-server/dist/index.js
```

## `sg_query` Status Semantics

- `completed`: execution succeeded
- `blocked`: workflow recognized; required field missing
- `unsupported`: prompt outside bounded workflow catalog
- `failed`: workflow started but at least one step failed

Operational rule:

- Treat `blocked` and `unsupported` as control flow, not runtime exceptions.
- Treat `failed` as execution failure requiring source-level triage.

## Source-Level Debugging Checklist

When a call fails:

1. Inspect `error.code`, `error.source`, and `error.suggestedAction` from structured output.
2. Check server logs for matching `tool`, `workflow`, or `stepId`.
3. Confirm auth presence (`SG_API_ONEMAP_*`, `SG_API_URA_KEY`, `SG_API_LTA_KEY`) when source is authenticated.
4. Re-run the direct tool with exact parameters to isolate planner vs source behavior.
5. Clear stale cache if needed:

```text
sg_cache_clear {}
```

## Logging Conventions Added

This repo now logs structured JSON entries across:

- shared HTTP client request lifecycle (request, retries, latency, terminal failure)
- `sg_query` plan selection and step execution
- additive brief source failures (no silent partial failure)
- middleware-handled tool failures
- REST gateway request lifecycle
- CLI command lifecycle and argument validation failures

Common log fields:

- `module`, `level`, `msg`, `ts`, `pid`
- context fields such as `traceId`, `requestId`, `workflow`, `tool`, `stepId`

Sensitive key-like fields are redacted in logger output.

## Verify Pipeline Notes

`npm run verify` no longer shells through `npm exec -- node` for internal scripts, reducing avoidable network dependency in restricted environments.

If verification still fails:

1. run `npm install`
2. run `npm run build`
3. run `npm run diagnostics`
4. run `npm run verify`

Stop on first failing stage and fix forward rather than skipping checks.

If your environment blocks nested process spawning (for example hardened sandboxes), run:

```bash
SG_APIS_SKIP_PACKAGING_SMOKE=1 npm run verify
```

Use this only for constrained local environments; keep packaging smoke enabled in CI or release workflows.
