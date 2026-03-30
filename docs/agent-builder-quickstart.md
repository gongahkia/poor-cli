# Agent Builder Quickstart

## Start With Discovery

Use the catalog resources before you build prompt routing logic:

- `sg://apis`: official family coverage, auth, rate limits, and positioning
- `sg://tools`: direct tool inventory and schemas
- `sg://workflows`: bounded workflow entrypoints and examples
- `sg://recipes`: common prompt shapes mapped to the preferred entrypoint and fallback tools
- `sg://runtime`: auth dependencies, credential-source rules, timeout/cache policy, health coverage, and `sg_query` status semantics
- `sg://playbooks`: grouped workflow combinations for relocation, diligence, and social-support style agents
- `sg://benchmarks`: latency, cache-tier, freshness, and credibility expectations for the strongest workflows

If you only read one resource first, read `sg://recipes`.

## When To Use `sg_query`

Use `sg_query` when the caller starts with a goal instead of exact parameters:

- `Walk from 049178 to 048616`
- `Find a community club near 560123`
- `Reverse geocode 1.2840, 103.8510`
- `Convert SVY21 28001 38744 to WGS84`
- `Browse SingStat transport datasets`
- `Browse data.gov collections`
- `Show URA development charge rates for Residential sector A`
- `Architecture firm diligence for DP Architects`
- `Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.`
- `Hotel operator lookup for Marina Bay Sands`

`sg_query` is the preferred interface for covered prompt shapes because it keeps the routing bounded and returns workflow metadata instead of hiding the steps.

## When To Use Direct Tools

Use direct `sg_*` tools when your application already has the required fields and wants a stable low-level contract:

- `sg_onemap_route` when you already have start and end coordinates
- `sg_singstat_table` when you already know the `tableId`
- `sg_singstat_timeseries` when you already know the `tableId`, `indicator`, and year range
- `sg_datagov_rows` when you already know the dataset and need bounded row reads
- `sg_hdb_rental_prices` when you already have `town` and `flatType`

The direct surface is the right choice when you are building your own planner, UI, or cache strategy.

## How To Handle Blocked And Unsupported Results

`sg_query` should not guess.

Expect two important non-success outcomes:

- blocked: the repo recognized the workflow, but a required field is missing
- unsupported: the prompt does not map to a bounded supported workflow
- failed: execution started, but a direct tool or workflow dependency failed

Build your client around those outcomes:

1. If the status is blocked, ask the user for the missing field shown in the blocker message.
2. If the status is unsupported, drop to discovery through `sg://recipes`, `sg://playbooks`, `sg://workflows`, or direct tool selection.
3. If the status is failed, inspect `failedStep`, surface the suggested action, and retry only after fixing the failing direct-tool input.
4. If the workflow is completed, continue from the returned `structuredContent` and underlying direct-tool outputs.

## Recommended Integration Pattern

1. Read `sg://recipes`, `sg://runtime`, `sg://playbooks`, and `sg://benchmarks` at startup and cache them in your planner.
2. Route covered natural-language prompts to `sg_query`.
3. Route exact-parameter tasks to direct `sg_*` tools.
4. Surface blocker messages directly to the caller instead of trying to infer missing data.
5. Treat `blocked` and `unsupported` as non-error control-flow outcomes; only `failed` is an execution error.
6. Keep the direct tool names visible in logs and traces so developers can debug routing decisions.

The runnable reference implementation for this pattern is [`examples/integration/basic-client.ts`](../examples/integration/basic-client.ts). A minimal stdlib-only Python variant lives in [`examples/integration/basic-client.py`](../examples/integration/basic-client.py). For production-oriented patterns, start from [`examples/integration/backend-worker-template.ts`](../examples/integration/backend-worker-template.ts) and [`examples/integration/ui-state-template.ts`](../examples/integration/ui-state-template.ts), which both demonstrate explicit blocked/unsupported/failed handling.

## Operational Defaults For Teams

Before handing the server to an application team:

1. Run `npm run build` and `npm run diagnostics` to validate catalog and resource contracts.
2. Run `npm run verify` as the full gate.
3. Set `SG_APIS_LOG_LEVEL=info` in production and `debug` in staging.
4. Treat `sg_health_check`, `sg_cache_stats`, and `sg_config_get` as first-line operator tools.
5. Use [`docs/troubleshooting.md`](./troubleshooting.md) as the standard incident runbook.

## Live Smoke

- `npm run quick-start` is the credential-gated live quickstart for real OneMap, URA, LTA, data.gov datastore, and official file-download validation.
- `npm run test:smoke:live` runs the same live validation flow without the build wrapper.

## Useful Starter Paths

### Geospatial

```text
sg_query { "query": "Walk from 049178 to 048616", "mode": "execute" }
sg_onemap_route { "startLat": 1.2864, "startLng": 103.8537, "endLat": 1.2840, "endLng": 103.8510, "routeType": "walk" }
sg_onemap_reverse_geocode { "lat": 1.2840, "lng": 103.8510 }
```

### SingStat Drilldown

```text
sg_query { "query": "Browse SingStat transport datasets", "mode": "execute" }
sg_singstat_browse { "category": "Transport" }
sg_singstat_table { "tableId": "M650151" }
sg_singstat_timeseries { "tableId": "M650151", "indicator": "Vehicle population", "startYear": 2022, "endYear": 2025 }
```

### data.gov.sg Drilldown

```text
sg_query { "query": "Browse data.gov collections", "mode": "execute" }
sg_datagov_browse {}
sg_datagov_search { "keyword": "hawker centres" }
sg_datagov_resources { "datasetId": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc" }
sg_datagov_rows { "datasetId": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc", "limit": 5, "sort": "month desc" }
```

### Civic Discovery

```text
sg_query { "query": "Find a family service centre near 560230", "mode": "execute" }
sg_msf_family_services { "postalCode": "560230" }
sg_msf_student_care_services { "postalCode": "750471", "scfaOnly": true }
sg_msf_social_service_offices { "name": "Social Service Office @ Queenstown" }
```

### Business Diligence Expansion

```text
sg_query { "query": "Architecture firm diligence for DP Architects", "mode": "execute" }
sg_business_dossier { "entityName": "DP Architects", "modules": ["acra", "boa", "gebiz"], "sectorHints": ["architecture", "procurement"] }
sg_boa_architecture_firms { "firmName": "DP Architects" }
sg_hsa_health_product_licensees { "companyName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD." }
sg_hlb_hotels { "name": "Marina Bay Sands" }
```

## New Data Families

Eighteen additional families are available as direct tools, all backed by data.gov.sg or the official no-auth file-download path:

- `sg_boa_architects` and `sg_boa_architecture_firms` — architect and architecture-firm registry checks
- `sg_pa_community_outlets` and `sg_pa_resident_network_centres` — community clubs, PAssion WaVe outlets, and residents' network centres
- `sg_sportsg_facilities` — public sport facilities by facility type, postal code, or proximity
- `sg_ecda_childcare_centres` — childcare centres with joined vacancy signals
- `sg_msf_family_services` — family service centres by name, postal code, or proximity
- `sg_msf_student_care_services` — student care services with audit-status and SCFA filters
- `sg_msf_social_service_offices` — social service offices by name, postal code, or proximity
- `sg_gebiz_tenders` — government procurement tenders and awards
- `sg_hawker_centres` — hawker centre directory with coordinates
- `sg_moe_schools` — school directory by level, zone, name
- `sg_moh_facilities` — hospitals, clinics, polyclinics
- `sg_hsa_licensed_pharmacies` and `sg_hsa_health_product_licensees` — pharmacy and health-product licensing evidence
- `sg_sfa_establishments` — licensed food establishments
- `sg_nparks_parks` — parks and nature reserves
- `sg_pub_water_levels` — water level station readings
- `sg_mom_labour_stats` — labour market statistics
- `sg_stb_visitor_stats` — tourism visitor arrivals
- `sg_hlb_hotels` — hotel directory with keeper names and room counts

These complement the property brief with amenity context and the business dossier with architecture, healthcare-supplier, hospitality, and procurement evidence.

## Practical Rule

If your application needs auditability, use the direct tools. If your application needs onboarding speed for supported Singapore public-data prompts, start with `sg_query` plus `sg://recipes`, then use `sg://playbooks` and `sg://benchmarks` to choose the next bounded workflow and the right runtime expectations.
