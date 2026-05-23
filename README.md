# Swee SG

Swee SG is an open-core, local-first Singapore public-data runtime for civic-hacker demos and agent/app builders. It is not an official public-agency dashboard. The product value is governed source access: every supported Pulse view keeps provenance, freshness, gaps, and Swee Shield audit context visible.

The runtime has two product surfaces:

- **Swee Shield**: policy enforcement, audit persistence, replay metadata, and MCP/tool poisoning scans for every REST and MCP tool call.
- **Swee Pulse**: source-backed Singapore city signals for mobility, weather, source health, freshness, gaps, and deterministic explanations.

The app no longer exposes the old counterparty due-diligence workflow. The retained `sg_*` tools are reusable Singapore source adapters; app-level workflows should enter through `swee_pulse_*` and Shield audit tools.

The first benchmark focus is **transport reliability**: LTA incidents, rail alerts, road works/openings, traffic camera freshness, and credentialed direct adapters where exact structured inputs are supplied.

## Run It

```bash
npm install
npm run build
npm run dev
```

The REST gateway starts on `http://localhost:3000` and the web dashboard starts on the Vite URL printed by `npm run dev`, usually `http://localhost:5173`.

No AI key is required for the main dashboard. Live LTA routes require `SG_API_LTA_KEY` where upstream DataMall credentials are needed.

For split-origin local development, set `SWEE_WEB_ORIGIN_ALLOWLIST` on the REST gateway to the exact web origin, for example `http://localhost:5173`.

## Useful Commands

```bash
npm run diagnostics
npm run test:smoke:profiles
npm run test:smoke:web
npm run benchmarks:snapshot
npm run benchmark:transport:live
npm run benchmark:sources:live
npm run status:public
npm test -w apps/web
npx vitest run packages/mcp-server/src/pulse/__tests__ packages/mcp-server/src/shield/__tests__
```

## Main Tools

Pulse:

- `swee_pulse_snapshot`
- `swee_pulse_mobility`
- `swee_pulse_weather`
- `swee_pulse_explain`

Shield:

- `swee_shield_audit_lookup`
- `swee_shield_scan_tools`

Selected raw source adapters:

- `sg_nea_forecast_2hr`, `sg_nea_air_quality`, `sg_nea_rainfall`
- `sg_lta_traffic_incidents`, `sg_lta_train_alerts`, `sg_lta_road_works`, `sg_lta_traffic_images`
- `sg_datagov_search`, `sg_singstat_search`, `sg_onemap_geocode`

Ops:

- `sg_health_check`
- `sg_cache_stats`, `sg_cache_clear`
- `sg_key_set`, `sg_key_list`, `sg_key_delete`
- `sg_config_get`, `sg_config_set`
- `sg_trace_lookup`, `sg_request_lookup`

## REST Shortcuts

```bash
curl http://localhost:3000/api/v1/pulse/snapshot
curl http://localhost:3000/api/v1/pulse/weather
curl http://localhost:3000/api/v1/pulse/mobility
curl http://localhost:3000/api/v1/shield/audits
curl http://localhost:3000/api/v1/shield/scan
```

Every generic tool endpoint is also exposed as `POST /api/v1/<tool-name>`.

## Public Evidence

`npm run benchmarks:snapshot` writes a benchmark JSON artifact with Pulse, Shield, and transport-reliability coverage evidence. `npm run status:public` turns that artifact into `docs/status/public-status.md`.

Those artifacts are release evidence, not an SLA. Transport rows describe source coverage, freshness handling, credentials, and limits; they do not claim official service status or operational safety.

`npm run benchmark:transport:live` runs the local MCP runtime against `swee_pulse_mobility` and writes live proof artifacts to `artifacts/transport/latest.json` and `artifacts/transport/latest.md`. Missing `SG_API_LTA_KEY` is reported as `credential_missing` for credentialed LTA sources rather than treated as a command failure.

`npm run benchmark:sources:live` runs broader no-auth source-family probes for NEA weather, OneMap geocoding, data.gov.sg discovery, and SingStat discovery. It writes `artifacts/sources/latest.json` and `artifacts/sources/latest.md` with source states, record counts, gap codes, Shield audit IDs, and limits.

## Runtime Contract

Swee Pulse signals are deterministic transformations of source records. Responses surface provenance, observed freshness, gaps, and recommended operator actions. Absence of a public-data signal is not a safety, compliance, or risk clearance claim.

Swee Shield records policy decisions and sanitized replay metadata in a local SQLite audit store. Secrets are redacted in stored payloads and raw payload hashes are retained for reproducibility.
