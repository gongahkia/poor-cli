---
name: sg-apis
description: Singapore government data for agent builders through direct MCP tools
version: 0.1.0
mcp_server: sg-apis-mcp
---

# Singapore Government Data Skill

Use this skill when an agent needs Singapore government data through MCP.

The product contract is the direct `sg_*` tools. Treat `sg_query` as an experimental shortcut for supported single-step requests only.

## Positioning

- Best for deterministic agent workflows that need official Singapore data
- Optimized for tool calls, not free-form analyst chat
- Current depth is limited to five API families: SingStat, MAS, OneMap, URA, and data.gov.sg
- Multi-step workflows should be composed explicitly by the agent with direct tools

## Stable Scope

### SingStat

Use for dataset discovery and structured statistical retrieval.

- `sg_singstat_search`
  Search SingStat tables by keyword.
  Input: `{ "keyword": "GDP", "limit": 5 }`
- `sg_singstat_table`
  Read a specific table once you know the table ID.
  Input: `{ "tableId": "M015631", "timeFilter": "2020,2024" }`
- `sg_singstat_timeseries`
  Pull a specific indicator over a year range.
  Input: `{ "tableId": "M015631", "indicator": "GDP", "startYear": 2019, "endYear": 2024 }`
- `sg_singstat_compare`
  Compare explicitly specified indicators side by side.
- `sg_singstat_browse`
  Browse categories when search is too broad.

### MAS

Use for official monetary and banking snapshots.

- `sg_mas_exchange_rates`
  Latest or exact-date SGD exchange rates.
  Input: `{ "currency": "USD", "date": "2024-01-31" }`
- `sg_mas_interest_rates`
  SORA only in this phase.
  Input: `{ "date": "2024-01-31" }`
- `sg_mas_financial_stats`
  Banking statistics only in this phase.
  Input: `{ "date": "2024-01-31" }`

Do not assume generic rate categories or date-range semantics are supported.

### OneMap

Use for geography, routing, and planning-area demographics.

- `sg_onemap_geocode`
  Address or postal-code lookup.
  Input: `{ "searchVal": "168742" }`
- `sg_onemap_reverse_geocode`
  Coordinate-to-address lookup.
- `sg_onemap_route`
  Explicit routing from coordinates.
- `sg_onemap_population`
  Demographic data by planning area.
  Input: `{ "planningArea": "Tampines", "dataType": "getPopulationAgeGroup" }`
- `sg_onemap_convert_coords`
  Convert between SVY21 and WGS84.

### URA

Use for property and planning context.

- `sg_ura_property_transactions`
  Private property transaction data by property type, area, or period.
  Input: `{ "propertyType": "residential", "area": "Bedok" }`
- `sg_ura_planning_area`
  URA planning-area lookup by planning area name or coordinates.
  Input: `{ "planningArea": "Bedok" }`
- `sg_ura_dev_charges`
  Development charge lookup.

### data.gov.sg

Use as the general discovery fallback.

- `sg_datagov_search`
  Search datasets by keyword.
  Input: `{ "keyword": "hawker centres" }`
- `sg_datagov_get`
  Metadata lookup only.
  Input: `{ "datasetId": "<dataset-id>" }`
- `sg_datagov_browse`
  Browse collections.

Do not expect `sg_datagov_get` to return paginated dataset rows.

## Operational Tools

- `sg_health_check`
  Reports each API as configured or unconfigured, plus reachable or unreachable.
- `sg_key_set`, `sg_key_list`, `sg_key_delete`
  Local credential helpers.
- `sg_cache_stats`, `sg_cache_clear`
  Cache inspection and maintenance.
- `sg_config_get`, `sg_config_set`
  Runtime config for supported mutable keys only.
- `sg_query`
  Experimental single-step router. Use only when rough routing is acceptable.

## Workflow Recipes

These are the product workflows to build with explicit tool calls.

### Macro Snapshot

```text
sg_singstat_search { "keyword": "GDP Singapore" }
sg_singstat_search { "keyword": "CPI Singapore" }
sg_mas_exchange_rates { "currency": "USD" }
sg_mas_interest_rates {}
```

### Area Demographics

```text
sg_onemap_population { "planningArea": "Tampines", "dataType": "getPopulationAgeGroup" }
sg_onemap_population { "planningArea": "Tampines", "dataType": "getHouseholdMonthlyIncomeWork" }
```

### Property And Location Due Diligence

```text
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok" }
sg_ura_planning_area { "planningArea": "Bedok" }
sg_onemap_geocode { "searchVal": "Bedok" }
```

### Dataset Discovery Fallback

```text
sg_datagov_search { "keyword": "hawker centres" }
sg_datagov_get { "datasetId": "<dataset-id-from-search>" }
```

## `sg_query`

Supported uses:
- quick single-step routing to exchange rates, SORA, banking stats, geocoding, planning-area demographics, URA planning lookup, or dataset search

Unsupported uses:
- comparisons
- fan-out across APIs
- chained steps like geocode-then-population
- production workflows that need stable contracts

When unsupported, call the direct tools yourself.

## Authentication

Recommended production path:
- `SG_API_ONEMAP_EMAIL`
- `SG_API_ONEMAP_PASSWORD`
- `SG_API_URA_KEY`

Local fallback through MCP tools:

```text
sg_key_set { "apiName": "onemap_email", "key": "you@example.com" }
sg_key_set { "apiName": "onemap_password", "key": "your-password" }
sg_key_set { "apiName": "ura", "key": "your-ura-api-key" }
```

The local keystore is convenient for development, but it is not a managed secret store.
