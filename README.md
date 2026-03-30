# sg-apis-mcp

Give your Agents context on Singapore.

Official Singapore public data for agents with deterministic contracts.

## Surface Snapshot

The repo currently exposes 68 `sg_*` tools total across 29 official data families.

- 54 direct data tools
- 5 additive brief tools: `sg_business_dossier`, `sg_property_brief`, `sg_macro_brief`, `sg_transport_brief`, `sg_environment_brief`
- 8 operational helpers for health, keys, cache, and config
- 1 bounded preferred interface, `sg_query`

`sg_query` is the bounded preferred interface across 20 routed families. It plans or executes bounded deterministic workflows with transparent step metadata. The direct `sg_*` tools remain the stable low-level contract.

## Why This Exists

This repo is for agent builders who want one honest MCP server for Singapore public data instead of stitching together SingStat, MAS, OneMap, URA, LTA DataMall, NEA, HDB, CEA, BCA, BOA, ACRA, PA, Sport Singapore, ECDA, MSF Family Services, MSF Student Care Services, MSF Social Service Offices, GeBIZ, Hawker Centres, MOE Schools, MOH Healthcare, HSA, SFA, NParks, PUB, MOM, STB, HLB, and data.gov.sg manually.

The value is not hidden magic. The value is:

- official Singapore public data in one server
- explicit schemas and stable `sg_*` tool names
- bounded workflows instead of vague planning claims
- provenance, freshness, and limits surfaced directly in brief artifacts
- caching, rate limiting, auth handling, packaging, and parity checks already done

If you are evaluating whether the repo is actually useful for developers, start with [docs/product-audit.md](./docs/product-audit.md), [docs/developer-adoption-audit.md](./docs/developer-adoption-audit.md), [docs/agent-builder-quickstart.md](./docs/agent-builder-quickstart.md), and [docs/market-conventions-audit.md](./docs/market-conventions-audit.md).

## Capability Matrix

| Need | Best entrypoint | Better than raw API calls because | Auth | Freshness surface | Intentionally unsupported |
| --- | --- | --- | --- | --- | --- |
| Business Registry Diligence | `sg_business_dossier` or `sg_query` | ACRA, BCA, and CEA are combined into one brief and can extend explicitly into GeBIZ, BOA, HSA, and HLB with `modules` and `sectorHints` | None | observed-at and upstream registry timestamps are returned per source | broad corporate graph analysis |
| Architecture Firm Diligence | `sg_business_dossier` or `sg_query` | BOA, ACRA, and optional GeBIZ evidence stay bounded to architecture-firm diligence with match confidence and unmatched-module reporting | None | observed-at and upstream registry timestamps are returned per source | generic architecture-market analysis |
| Healthcare Supplier Diligence | `sg_business_dossier` or `sg_query` | HSA, ACRA, and optional GeBIZ evidence stay bounded to healthcare supplier diligence with licensing-focused continuation hints | None | observed-at and upstream licence timestamps are returned per source | open-ended healthcare research |
| Hotel Operator Lookup | `sg_hlb_hotels` or `sg_query` | HLB hotel and keeper facts stay bounded to hospitality diligence without widening into travel planning | None | observed-at plus HLB dataset timestamps are returned when available | hotel ranking or recommendation |
| Property And Regulatory Due Diligence | `sg_property_brief` or `sg_query` | OneMap, URA, HDB, and optional NEA/LTA context are combined with explicit location resolution and workflow limits | OneMap optional, URA key for live planning data, LTA optional | observed-at plus first available market or live-signal timestamps | hidden property scoring or recommendations |
| Macro Snapshot | `sg_macro_brief` or `sg_query` | MAS values and SingStat dataset entrypoints are returned as one starter brief with dataset IDs and scope notes | None | observed-at plus returned MAS dates | open-ended macro commentary |
| Transport Status | `sg_transport_brief` or `sg_query` | bus arrivals, train alerts, and traffic incidents are normalized into one operational snapshot | LTA key for live data | observed-at plus next ETA or alert timestamps when available | route planning or delay prediction |
| Environment Snapshot | `sg_environment_brief` or `sg_query` | forecast, air quality, and rainfall are normalized into one live monitoring snapshot | None | observed-at plus forecast, air-quality, and rainfall timestamps when available | long-range forecasting or severe-weather alerting |
| Dataset Discovery Fallback | `sg_datagov_search` -> `sg_datagov_resources` -> `sg_datagov_rows` | dataset discovery continues into resource inspection and bounded row reads | None | data.gov.sg metadata timestamps are returned directly by the direct tools | unbounded scraping or arbitrary joins |

## Stable Surface

| API family | Direct tools | Current scope | Auth |
| --- | --- | --- | --- |
| SingStat | 5 | Search, browse, table reads, time series, explicit compare | None |
| MAS | 3 | Exchange rates, SORA, banking stats, exact dates, bounded date ranges | None |
| OneMap | 5 | Geocode, reverse geocode, route, planning-area demographics, coordinate conversion | Email + password |
| URA | 3 | Property transactions, planning-area lookup, development charges | API key |
| LTA DataMall | 3 | Bus arrivals, train alerts, traffic incidents | API key |
| NEA | 3 | 2-hour forecast, air quality, rainfall | None |
| HDB | 2 | Curated resale and rental market reads over official data.gov.sg datasets | None |
| CEA | 1 | Curated salesperson and estate-agent registry lookup | None |
| BCA | 2 | Curated licensed-builder and contractor registry lookup | None |
| BOA | 2 | Curated architect and architecture-firm registry lookup | None |
| ACRA | 1 | Curated exact-match company and UEN lookup over the official sharded registry | None |
| PA | 2 | Community clubs, PAssion WaVe outlets, and residents' network centres | None |
| Sport Singapore | 1 | Public sports facility discovery across swimming complexes, sports halls, stadiums, and sport centres | None |
| ECDA | 1 | Childcare discovery with joined location and vacancy signals | None |
| MSF Family Services | 1 | Family service centre discovery by name, postal code, or proximity | None |
| MSF Student Care Services | 1 | Student care discovery with audit-status and SCFA filters | None |
| MSF Social Service Offices | 1 | Social service office discovery by name, postal code, or proximity | None |
| GeBIZ | 1 | Government procurement tender awards and contract data | None |
| Hawker Centres | 1 | Hawker centre directory with locations and stall counts | None |
| MOE Schools | 1 | School directory filtered by level, zone, and name | None |
| MOH Healthcare | 1 | Healthcare facility directory (hospitals, clinics) | None |
| HSA | 2 | Licensed pharmacies plus health-product import, wholesale, and manufacturing licensees | None |
| SFA | 1 | Licensed food establishment directory | None |
| NParks | 1 | Parks and nature reserves directory | None |
| PUB | 1 | Water level monitoring station readings | None |
| MOM | 1 | Labour market statistics | None |
| STB | 1 | Visitor arrival statistics | None |
| HLB | 1 | Hotel directory with keeper names, room counts, and geospatial location context | None |
| data.gov.sg | 5 | Dataset search, metadata, resource inspection, bounded row reads, collection browse | None |

Additive brief tools:

- `sg_business_dossier`
- `sg_property_brief`
- `sg_macro_brief`
- `sg_transport_brief`
- `sg_environment_brief`

All brief tools return the same bounded envelope:

- `title`
- `summary`
- `evidence`
- `records`
- `gaps`
- `provenance`
- `freshness`
- `limits`

Transport and environment brief records expose analyst-oriented subshapes:

- `sg_transport_brief.records`: `status`, `coverage`, `signals`, `network`, optional `stop`, `followups`, and `raw`
- `sg_environment_brief.records`: `status`, `coverage`, `signals`, `thresholds`, `focus`, `followups`, and `raw`

Notes:

- `sg_mas_exchange_rates`, `sg_mas_interest_rates`, and `sg_mas_financial_stats` support latest, exact-date, and bounded date-range reads.
- `sg_datagov_get` is metadata only.
- `sg_datagov_resources` exposes the current machine-readable resource shape and columns for a dataset.
- `sg_datagov_rows` performs bounded datastore reads with explicit `filters`, `limit`, `offset`, and `sort`.
- OneMap now requires valid credentials for live requests. There is no silent unauthenticated fallback outside mock mode.
- HDB, CEA, BCA, BOA, HSA, HLB, and `sg_acra_entities` are curated tools over official public datasets and do not introduce separate credentials.
- PA, Sport Singapore, ECDA, and the MSF civic directories stay no-auth by using the same official data.gov.sg download path.

## Quickstart

Node 20.x is the supported runtime.

### Local Repo Install

This is the truthful default until the first public npm release exists.

```bash
npm install
npm run build
node packages/mcp-server/dist/index.js
```

Local Claude Desktop or Codex-style MCP config:

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

Local Claude Code:

```bash
claude mcp add sg-apis-mcp -- node /absolute/path/to/sg-skills/packages/mcp-server/dist/index.js
```

### Published npm Install

Use this only after the first successful public npm release:

```bash
npx -y sg-apis-mcp
```

Published-package client config:

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

### Quick Demo

After building locally, run one of the bundled end-to-end demos:

```bash
npm run demo:mcp -- business
npm run demo:mcp -- property
npm run demo:mcp -- macro
npm run demo:mcp -- transport
npm run demo:mcp -- environment
npm run demo:mcp -- civic
npm run demo:mcp -- geospatial
npm run demo:mcp -- architecture
npm run demo:mcp -- healthcare
npm run demo:mcp -- hotel
npm run demo:mcp -- sector-business
```

Those demos start the mock upstream server, connect to the built MCP server, read a catalog resource, and call one direct tool, one supporting tool, and `sg_query`.

### Discovery Resources

Read the built-in catalogs before wiring your own client logic:

- `sg://apis`
- `sg://tools`
- `sg://workflows`
- `sg://recipes`
- `sg://runtime`
- `sg://playbooks`
- `sg://benchmarks`

`sg://recipes` is the fastest way to see which natural-language prompt shapes already map cleanly to `sg_query` versus direct fallback tools. `sg://runtime` exposes the machine-readable trust layer for auth dependencies, credential-source rules, timeouts, cache tiers, retry policy, health coverage, and the `planned | completed | blocked | unsupported | failed` query contract. `sg://playbooks` groups the strongest workflow combinations by agent job, and `sg://benchmarks` exposes adoption-grade latency, cache-tier, freshness, and credibility expectations for the headline workflows.

For application wiring, start with [`examples/integration/basic-client.ts`](./examples/integration/basic-client.ts) for the TypeScript planner pattern and [`examples/integration/basic-client.py`](./examples/integration/basic-client.py) for a minimal stdlib-only Python client. The TypeScript example caches `sg://recipes`, `sg://runtime`, `sg://playbooks`, and `sg://benchmarks`, uses `sg_query` for covered prompts, surfaces blocked or unsupported outcomes directly, demonstrates a failed execution, and falls back to direct `sg_*` tools when the caller already has exact parameters.

## Authentication

Copy [`.env.example`](./.env.example) and set the credentials you actually need:

- `SG_API_ONEMAP_EMAIL`
- `SG_API_ONEMAP_PASSWORD`
- `SG_API_URA_KEY`
- `SG_API_LTA_KEY`

The keystore helpers are still available for local use:

- `sg_key_set { "apiName": "onemap_email", "key": "..." }`
- `sg_key_set { "apiName": "onemap_password", "key": "..." }`
- `sg_key_set { "apiName": "ura", "key": "..." }`
- `sg_key_set { "apiName": "lta", "key": "..." }`

`sg_health_check` probes SingStat, MAS, OneMap, URA, LTA DataMall, data.gov.sg, and NEA directly. It now returns structured records with `configured`, `credentialSource`, `reachable`, `latencyMs`, and dependency notes. HDB, CEA, BCA, BOA, HSA, HLB, and ACRA are intentionally covered operationally through the shared data.gov.sg path or official file-download path.

Auth troubleshooting and failure modes live in [docs/api-auth-guide.md](./docs/api-auth-guide.md).

Operational failure triage lives in [docs/troubleshooting.md](./docs/troubleshooting.md).

## Workflow Demos

The primary walkthroughs for this tranche are:

- [Business Registry Diligence](./examples/business-dossier.md)
- [Architecture Firm Diligence](./examples/architecture-firm-diligence.md)
- [Healthcare Supplier Diligence](./examples/healthcare-supplier-diligence.md)
- [Hotel Operator Lookup](./examples/hotel-operator-lookup.md)
- [Sector Scoped Business Diligence](./examples/sector-scoped-business-diligence.md)
- [Property And Regulatory Due Diligence](./examples/property-brief.md)
- [Macro Snapshot](./examples/macro-brief.md)
- [Transport Status](./examples/transport-brief.md)
- [Environment Snapshot](./examples/environment-brief.md)
- [Civic Discovery](./examples/civic-discovery.md)
- [Geospatial Routing](./examples/geospatial-routing.md)

Additional bounded workflow names exposed in the catalog:

- Demographic Profile
- Civic Discovery
- Property Counterparty Diligence
- Architecture Firm Diligence
- Healthcare Supplier Diligence
- Hotel Operator Lookup
- Sector Scoped Business Diligence
- Dataset Discovery Fallback
- Route Planning
- SingStat Table Drilldown
- Dataset Collection Browse

### Business Registry Diligence

```text
sg_query { "query": "Registry diligence for UEN 201912345K", "mode": "execute" }
sg_business_dossier { "uen": "201912345K", "modules": ["acra", "bca", "cea"], "format": "json" }
sg_acra_entities { "uen": "201912345K", "format": "json" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_cea_salespersons { "registrationNo": "R123456A", "format": "json" }
```

### Architecture Firm Diligence

```text
sg_query { "query": "Architecture firm diligence for DP Architects", "mode": "execute" }
sg_business_dossier { "entityName": "DP Architects", "modules": ["acra", "boa", "gebiz"], "sectorHints": ["architecture", "procurement"], "format": "json" }
sg_boa_architecture_firms { "firmName": "DP Architects", "format": "json" }
sg_boa_architects { "firmName": "DP Architects", "format": "json" }
sg_gebiz_tenders { "supplierName": "DP Architects", "format": "json" }
```

### Healthcare Supplier Diligence

```text
sg_query { "query": "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "mode": "execute" }
sg_business_dossier { "entityName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "modules": ["acra", "hsa", "gebiz"], "sectorHints": ["healthcare", "procurement"], "format": "json" }
sg_hsa_health_product_licensees { "companyName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "format": "json" }
sg_hsa_licensed_pharmacies { "pharmacyName": "A.M. Pharmacy Pte Ltd", "format": "json" }
sg_gebiz_tenders { "supplierName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "format": "json" }
```

### Hotel Operator Lookup

```text
sg_query { "query": "Hotel operator lookup for Marina Bay Sands", "mode": "execute" }
sg_hlb_hotels { "name": "Marina Bay Sands", "format": "json" }
sg_hlb_hotels { "keeperName": "Marina Bay Sands Pte. Ltd.", "format": "json" }
sg_acra_entities { "entityName": "MARINA BAY SANDS PTE. LTD.", "format": "json" }
```

### Sector Scoped Business Diligence

```text
sg_query { "query": "Sector-scoped business diligence for Marina Bay Sands in hospitality", "mode": "execute" }
sg_business_dossier { "entityName": "MARINA BAY SANDS PTE. LTD.", "modules": ["acra", "hlb"], "sectorHints": ["hospitality"], "format": "json" }
sg_hlb_hotels { "keeperName": "Marina Bay Sands Pte. Ltd.", "format": "json" }
sg_acra_entities { "entityName": "MARINA BAY SANDS PTE. LTD.", "format": "json" }
```

### Property And Regulatory Due Diligence

```text
sg_query { "query": "Property due diligence for Bedok HDB resale", "mode": "execute" }
sg_property_brief { "planningArea": "Bedok", "flatType": "4 ROOM", "format": "json" }
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok", "format": "json" }
sg_hdb_resale_prices { "town": "Bedok", "flatType": "4 ROOM", "format": "json" }
```

### Property Counterparty Diligence

```text
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok", "format": "json" }
sg_hdb_resale_prices { "town": "Bedok", "flatType": "4 ROOM", "format": "json" }
sg_cea_salespersons { "estateAgentName": "ERA REALTY NETWORK PTE LTD", "format": "json" }
sg_acra_entities { "entityName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
```

### Macro Snapshot

```text
sg_query { "query": "Macro snapshot of Singapore", "mode": "execute" }
sg_macro_brief { "currency": "USD", "format": "json" }
sg_mas_exchange_rates { "currency": "USD", "startDate": "2026-03-01", "endDate": "2026-03-26", "format": "json" }
sg_singstat_search { "keyword": "Singapore GDP", "format": "json" }
```

### Transport Status

```text
sg_query { "query": "Transport status in Singapore right now", "mode": "execute" }
sg_transport_brief { "busStopCode": "83139", "serviceNo": "851", "format": "json" }
sg_lta_bus_arrivals { "busStopCode": "83139", "serviceNo": "851", "format": "json" }
sg_lta_train_alerts { "format": "json" }
sg_lta_traffic_incidents { "format": "json" }
```

### Environment Snapshot

```text
sg_query { "query": "Environment snapshot of Singapore right now", "mode": "execute" }
sg_environment_brief { "area": "Tampines", "region": "East", "stationId": "S107", "format": "json" }
sg_nea_forecast_2hr { "area": "Tampines", "format": "json" }
sg_nea_air_quality { "region": "East", "format": "json" }
sg_nea_rainfall { "stationId": "S107", "format": "json" }
```

### Civic Discovery

```text
sg_query { "query": "Find a community club near 560123", "mode": "execute" }
sg_pa_community_outlets { "type": "community_club", "postalCode": "560123", "format": "json" }
sg_pa_resident_network_centres { "postalCode": "560123", "format": "json" }
sg_sportsg_facilities { "facilityType": "swimming_complex", "postalCode": "560123", "format": "json" }
sg_ecda_childcare_centres { "postalCode": "560123", "hasVacancy": true, "format": "json" }
```

### Geospatial Routing

```text
sg_query { "query": "Walk from 049178 to 048616", "mode": "execute" }
sg_onemap_route { "startLat": 1.2864, "startLng": 103.8537, "endLat": 1.284, "endLng": 103.851, "routeType": "walk", "format": "json" }
sg_onemap_reverse_geocode { "lat": 1.284, "lng": 103.851, "format": "json" }
sg_onemap_convert_coords { "from": "SVY21", "x": 28001, "y": 38744, "format": "json" }
```

## Why This Beats Raw APIs

| Workflow | Raw upstream path | MCP path | What the repo adds |
| --- | --- | --- | --- |
| Business Registry Diligence | call `sg_acra_entities`, `sg_bca_licensed_builders`, `sg_bca_registered_contractors`, and `sg_cea_salespersons`, then normalize exact-match misses and module selection yourself | `sg_business_dossier` or `sg_query` | one envelope, explicit coverage, sector-aware module selection, exact-match gaps, freshness markers, and scope limits |
| Architecture Firm Diligence | call BOA architect and firm registries, then decide whether to add ACRA and GeBIZ evidence | `sg_business_dossier` or `sg_query` | one bounded architecture-focused artifact with BOA-first evidence, match confidence, and procurement-only continuation |
| Healthcare Supplier Diligence | call HSA licensee rows, optional pharmacy rows, ACRA, and GeBIZ separately, then reconcile exact and fuzzy matches yourself | `sg_business_dossier` or `sg_query` | one bounded healthcare supplier artifact with licensing emphasis, unmatched-module reporting, and next checks |
| Hotel Operator Lookup | call `sg_hlb_hotels`, then optionally widen into company evidence yourself | `sg_hlb_hotels` or `sg_query` | one bounded hotel-operator lookup path with keeper facts, room counts, and explicit hospitality scope |
| Property And Regulatory Due Diligence | geocode, resolve planning area, fetch URA transactions, fetch HDB market reads, then optionally stitch NEA and LTA signals | `sg_property_brief` or `sg_query` | resolved location, bounded live context, provenance per source, and clear non-recommendation boundaries |
| Macro Snapshot | call 3 MAS series plus separate SingStat dataset search calls, then decide which dataset IDs to keep | `sg_macro_brief` or `sg_query` | one starter artifact with dataset entrypoints, freshness, and explicit limits |
| Transport Status | call bus arrivals, train alerts, and traffic incidents separately, then decide what counts as a useful operations snapshot | `sg_transport_brief` or `sg_query` | one snapshot contract with stop-level optionality, provenance, and no hidden route-planning claims |
| Environment Snapshot | call forecast, air quality, and rainfall separately, then reconcile area, region, and station coverage | `sg_environment_brief` or `sg_query` | one live snapshot contract with area and region caveats surfaced directly in `limits` |

## `sg_query`

Supported intents:

- macro snapshot
- demographic profile
- property or regulatory due diligence
- business registry diligence
- architecture firm diligence
- healthcare supplier diligence
- hotel operator lookup
- sector-scoped business diligence
- dataset discovery fallback
- route planning between Singapore postal codes or coordinate pairs
- civic discovery for community clubs, residents' network centres, SportSG facilities, and childcare centres
- reverse geocode from one coordinate pair
- coordinate conversion between SVY21 and WGS84
- SingStat browse, table drilldown, and time-series reads
- data.gov collection browsing before dataset drilldown
- HDB resale or rental checks with town and flat-type extraction
- URA development-charge lookups with use-group and sector extraction
- transport status or transport snapshot
- environment snapshot
- direct-tool routing for precise stop-level, area-level, region-level, station-level, company, UEN, dataset, and table prompts already covered by a direct `sg_*` tool

Common rejection or block cases:

- unsupported comparisons return an explicit unsupported-workflow response instead of hidden multi-step synthesis
- missing identifiers return a blocked plan with the exact field needed next, such as `busStopCode`, `planningArea`, `datasetId`, `entityName`, or `UEN`
- unsupported multi-step formats return a direct format error instead of silently flattening the workflow
- broad prompts outside the bounded catalog return an explicit "could not build a supported workflow" response

When you need deterministic contracts, use the direct `sg_*` tools.

## Development

```bash
npm install
npm run verify
```

Useful follow-up commands:

- `npm run diagnostics`
- `npm run demo:mcp -- transport`
- `npm run test:smoke:packaging`
- `npm run test:smoke:registry`

Release workflow notes live in [docs/release.md](./docs/release.md).

### Debugging Notes

- set `SG_APIS_LOG_LEVEL=debug` for request and workflow execution traces
- `sg_query` now logs plan routing plus step-level execution metadata with trace IDs
- additive brief source failures are logged and surfaced as gaps (no silent source drops)
- run [docs/troubleshooting.md](./docs/troubleshooting.md) for the five-minute triage flow

## Current Limits

- The repo is still a tool-first infrastructure product for agents, not a broad end-user analytics assistant.
- `sg_business_dossier` is registry-focused, module-bounded, and entity-match oriented.
- `sg_property_brief` is a bounded diligence brief, not an automated investment recommendation.
- `sg_macro_brief` is a compact starter snapshot, not a full macro research product.
- `sg_transport_brief` is an operational snapshot, not a route planner or prediction engine.
- `sg_environment_brief` is a live monitoring brief, not a severe-weather or forecasting system.

## License

MIT
