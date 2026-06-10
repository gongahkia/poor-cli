# Swee SG

Swee SG is an open-core, local-first Singapore public-data runtime for civic-hacker demos and agent/app builders. It is not an official public-agency dashboard. The product value is governed source access: every supported Pulse view keeps provenance, freshness, gaps, and Swee Shield audit context visible.

The runtime has two product surfaces:

- **Swee Shield**: policy enforcement, audit persistence, replay metadata, approval queue, policy simulator, runtime output defense, and MCP/tool poisoning scans for every REST and MCP tool call.
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

Splunk Shield proxy tools are local-trial ready without changing the Pulse path. Set `SPLUNK_MCP_URL` to the Splunk MCP Streamable HTTP endpoint and `SPLUNK_MCP_TOKEN` to a bearer token, or store the token with `sg_key_set` using `apiName:"splunk_mcp"`. `SPLUNK_MCP_ALLOWED_INDEXES` optionally restricts `splunk_search` by explicit index. `SWEE_SHIELD_APPROVAL_MODE=queue` makes broad/unbounded SPL create approval records before upstream execution. `NODE_TLS_REJECT_UNAUTHORIZED=0` is only for local self-signed Splunk trials.

`SWEE_SHIELD_RUNTIME_SCAN_MODE=neutralize` redacts/neutralizes risky output and returns the defended result. `SWEE_SHIELD_RUNTIME_SCAN_MODE=block` blocks critical runtime findings and records the blocked audit row.

## Useful Commands

```bash
npm run diagnostics
npm run submission:claims:check
npm run submission:readiness:check
npm run splunk:smoke:live
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
- `swee_shield_approval_list`
- `swee_shield_approval_decide`
- `swee_shield_policy_simulate`
- `swee_shield_splunk_investigation_pack`

Splunk Shield proxy:

- `splunk_search`
- `splunk_list_indexes`
- `splunk_list_saved_searches`

Selected raw source adapters:

- `sg_nea_forecast_2hr`, `sg_nea_air_quality`, `sg_nea_rainfall`
- `sg_lta_traffic_incidents`, `sg_lta_train_alerts`, `sg_lta_road_works`, `sg_lta_traffic_images`
- `sg_datagov_search`, `sg_singstat_search`, `sg_onemap_geocode`
- `sg_hawker_closures`, `sg_nlb_libraries`, `sg_sportsg_facilities`, `sg_nparks_parks`, `sg_pub_water_levels`, `sg_pa_community_outlets`
- `sg_moe_schools`, `sg_ecda_childcare_centres`, `sg_msf_family_services`, `sg_msf_student_care_services`, `sg_msf_social_service_offices`, `sg_moh_facilities`

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
curl http://localhost:3000/api/v1/shield/approvals
curl http://localhost:3000/api/v1/shield/scan
curl -X POST http://localhost:3000/api/v1/shield/policy/simulate \
  -H 'Content-Type: application/json' \
  -d '{"query":"index=security failed login","earliest":"-24h","latest":"now","limit":25}'
curl -X POST http://localhost:3000/api/v1/shield/splunk/investigation-pack \
  -H 'Content-Type: application/json' \
  -d '{"question":"Investigate recent failed login activity","limit":20}'
```

Every generic tool endpoint is also exposed as `POST /api/v1/<tool-name>`.

## Splunk Demo Paths

Mocked local demo, no Splunk token:

```bash
npx vitest run packages/mcp-server/src/shield/__tests__/runtime-demo-fixtures.test.ts
npx vitest run packages/mcp-server/src/tools/__tests__/splunk-tools.test.ts
```

The dashboard route `/api/v1/shield/splunk/investigation-pack` forces mock mode and uses synthetic fixture events embedded in the runtime. They are fake demo events, not Splunk data.

Live Splunk trial, token required:

```bash
export SPLUNK_MCP_URL=https://localhost:8089/services/mcp
export SPLUNK_MCP_TOKEN=<bearer-token>
export SPLUNK_MCP_ALLOWED_INDEXES=main,security
export SWEE_SPLUNK_SMOKE_QUERY='index=security | head 1'
npm run build
npm run splunk:smoke:live
npm run dev:gateway
curl -X POST http://localhost:3000/api/v1/splunk_search \
  -H 'Content-Type: application/json' \
  -d '{"query":"index=security failed login","limit":10}'
```

For self-signed local-trial certs only, set `NODE_TLS_REJECT_UNAUTHORIZED=0`.

Submission prep lives in:

- `docs/submission/significant-update.md`
- `docs/submission/demo-script.md`
- `docs/submission/claims-audit.md`

Run `npm run submission:claims:check` and `npm run submission:readiness:check` before recording the demo. The live Splunk smoke script exits as skipped without `SPLUNK_MCP_URL` and a token; it does not prove live auth unless it actually runs against a configured Splunk MCP endpoint.

## Public Evidence

`npm run benchmarks:snapshot` writes a benchmark JSON artifact with Pulse, Shield, and transport-reliability coverage evidence. `npm run status:public` turns that artifact into `docs/status/public-status.md`.

Those artifacts are release evidence, not an SLA. Transport rows describe source coverage, freshness handling, credentials, and limits; they do not claim official service status or operational safety.

`npm run benchmark:transport:live` runs the local MCP runtime against `swee_pulse_mobility` and writes live proof artifacts to `artifacts/transport/latest.json` and `artifacts/transport/latest.md`. Missing `SG_API_LTA_KEY` is reported as `credential_missing` for credentialed LTA sources rather than treated as a command failure.

`npm run benchmark:sources:live` runs broader source-family probes for NEA weather, OneMap geocoding, data.gov.sg discovery, SingStat discovery, and civic directory families. It writes `artifacts/sources/latest.json` and `artifacts/sources/latest.md` with source states, record counts, gap codes, Shield audit IDs, and limits.

`npm run benchmark:sources:contracts:live`, `npm run benchmark:datagov:discovery:live`, and `npm run benchmark:credentials:live` add live evidence for source-contract drift, data.gov.sg discovery quality, and optional credential readiness. The check-only counterparts validate committed artifacts during `npm run verify`.

## Runtime Contract

Swee Pulse signals are deterministic transformations of source records. Responses surface provenance, observed freshness, gaps, and recommended operator actions. Absence of a public-data signal is not a safety, compliance, or risk clearance claim.

Swee Shield records policy decisions and sanitized replay metadata in a local SQLite audit store. Secrets are redacted in stored payloads and raw payload hashes are retained for reproducibility.
