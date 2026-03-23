# sg-apis-mcp

Tool-first MCP server for Singapore government data.

## Surface Snapshot

The repo currently exposes 40 `sg_*` tools total across 11 official data families.

- 31 direct data tools
- 8 operational helpers for health, keys, cache, and config
- 1 bounded preferred interface, `sg_query`

`sg_query` is the preferred natural-language entrypoint across 11 routed families. It plans or executes bounded deterministic workflows and transparent single-step direct calls. The direct `sg_*` tools remain the stable low-level contract.

## Product Scope

This repo is not a general Singapore analyst copilot. It goes deep on 11 official data families:

- SingStat
- MAS
- OneMap
- URA
- LTA DataMall
- NEA
- HDB
- CEA
- BCA
- ACRA
- data.gov.sg

Architecture and tradeoff notes live in [docs/architecture.md](./docs/architecture.md).

## Stable Surface

| API family | Direct tools | Current scope | Auth |
| --- | --- | --- | --- |
| SingStat | 5 | Search, browse, table reads, time series, explicit compare | None |
| MAS | 3 | Exchange rates by latest or exact date, SORA only, banking stats only | None |
| OneMap | 5 | Geocode, reverse geocode, route, planning-area demographics, coordinate conversion | Email + password |
| URA | 3 | Property transactions, planning-area lookup by name or coordinates, development charges | API key |
| LTA DataMall | 3 | Bus arrivals, train alerts, traffic incidents | API key |
| NEA | 3 | 2-hour forecast, air quality, rainfall | None |
| HDB | 2 | Curated resale and rental market records over official data.gov.sg datasets | None |
| CEA | 1 | Curated salesperson registry lookup | None |
| BCA | 2 | Curated builder and contractor registry lookup | None |
| ACRA | 1 | Curated corporate-entity lookup by exact entity name or UEN over the official sharded registry | None |
| data.gov.sg | 3 | Dataset search, browse, and metadata lookup | None |

Notes:

- `sg_mas_exchange_rates` supports latest or exact-date lookup. It does not expose synthetic date ranges.
- `sg_mas_interest_rates` is SORA-only in this phase.
- `sg_mas_financial_stats` is banking-only in this phase.
- `sg_datagov_get` returns dataset metadata only. It does not page, filter, or read dataset rows.
- `sg_onemap_route` only supports `startLat`, `startLng`, `endLat`, `endLng`, and `routeType`.
- HDB, CEA, BCA, and ACRA are curated tools over official data.gov.sg datasets. They do not require separate credentials.

## Quickstart

Node 20.x is the supported runtime.

```bash
npx sg-apis-mcp
```

Claude Desktop:

```json
{
  "mcpServers": {
    "sg-apis": {
      "command": "npx",
      "args": ["sg-apis-mcp"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add sg-apis-mcp -- npx sg-apis-mcp
```

## Authentication

Environment variables are the recommended production path:

- `SG_API_ONEMAP_EMAIL`
- `SG_API_ONEMAP_PASSWORD`
- `SG_API_URA_KEY`
- `SG_API_LTA_KEY`

The keystore helpers are still available for local use:

- `sg_key_set { "apiName": "onemap_email", "key": "..." }`
- `sg_key_set { "apiName": "onemap_password", "key": "..." }`
- `sg_key_set { "apiName": "ura", "key": "..." }`
- `sg_key_set { "apiName": "lta", "key": "..." }`

The local keystore is a convenience fallback, not a secret-management system.

`sg_health_check` probes SingStat, MAS, OneMap, URA, LTA DataMall, data.gov.sg, and NEA directly. HDB, CEA, BCA, and ACRA are intentionally covered operationally through the shared data.gov.sg path rather than separate health probes.

## Workflow Recipes

These are the intended product workflows for this phase.

### 1. Macro Snapshot

Goal: combine macro indicators from SingStat with MAS rates.

```text
sg_query { "query": "Macro snapshot of Singapore", "mode": "execute" }
sg_singstat_search { "keyword": "GDP Singapore" }
sg_singstat_search { "keyword": "CPI Singapore" }
sg_mas_exchange_rates { "currency": "USD" }
sg_mas_interest_rates {}
```

### 2. Demographic Profile

Goal: inspect the demographic profile of a planning area, optionally starting from a postal code.

```text
sg_query { "query": "Demographic profile for postal code 168742", "mode": "execute" }
sg_onemap_population { "planningArea": "Tampines", "dataType": "getPopulationAgeGroup" }
sg_onemap_population { "planningArea": "Tampines", "dataType": "getHouseholdMonthlyIncomeWork" }
```

### 3. Property And Regulatory Due Diligence

Goal: pair URA planning and transaction data with optional HDB market context.

```text
sg_query { "query": "Property due diligence for Bedok HDB resale", "mode": "execute" }
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok" }
sg_ura_planning_area { "planningArea": "Bedok" }
sg_hdb_resale_prices { "town": "Bedok" }
```

### 4. Property Counterparty Diligence

Goal: combine market context with ACRA, CEA, and BCA registry checks.

```text
sg_query { "query": "Run registry check for company ABC CONSTRUCTION PTE LTD", "mode": "execute" }
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok" }
sg_hdb_resale_prices { "town": "Bedok", "flatType": "4 ROOM" }
sg_cea_salespersons { "estateAgentName": "ERA REALTY NETWORK PTE LTD" }
sg_acra_entities { "entityName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD" }
```

### 5. Business Registry Diligence

Goal: cross-check a company, contractor, builder, or estate-agent counterparty across official registries.

```text
sg_query { "query": "Run registry check for company ABC CONSTRUCTION PTE LTD", "mode": "execute" }
sg_acra_entities { "entityName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD" }
sg_cea_salespersons { "registrationNo": "R123456A" }
```

### 6. Dataset Discovery Fallback

Goal: find a relevant Singapore dataset when the domain-specific APIs do not cover the topic.

```text
sg_query { "query": "Find datasets about hawker centres", "mode": "execute" }
sg_datagov_search { "keyword": "hawker centres" }
sg_datagov_get { "datasetId": "<dataset-id-from-search>" }
```

## `sg_query`

`sg_query` is the bounded preferred interface across 11 routed families.

Supported uses:

- transparent plan or execute mode for bounded workflows
- single-step routing to covered direct tools
- macro, demographic, property, business-registry, dataset-discovery, transport, and environment workflows

Unsupported uses:

- general planning across arbitrary user goals
- automatic comparison workflows
- hidden fan-out beyond the bounded workflow catalog
- hidden row-level data.gov.sg extraction beyond the explicit direct tools

When you need deterministic contracts, use the direct `sg_*` tools.

## Development

```bash
npm install
npm run verify
```

## Current Limits

The public entity surface is now live through `sg_acra_entities`, but it is still exact-match and registry-focused. This repo does not yet expose broader corporate graph or officer-level diligence beyond the fields published in the official public ACRA collection.

## License

MIT
