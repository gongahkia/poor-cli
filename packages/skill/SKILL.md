---
name: sg-apis
description: Singapore government data for agent builders through direct MCP tools and bounded workflow planning
version: 0.1.0
mcp_server: sg-apis-mcp
---

# Singapore Government Data Skill

Use this skill when an agent needs official Singapore public data through MCP.

## Surface Snapshot

The repo currently exposes 40 `sg_*` tools total across 11 official data families.

- 31 direct data tools
- 8 operational helpers
- 1 bounded preferred interface, `sg_query`

`sg_query` is the bounded preferred interface across 11 routed families. The direct `sg_*` tools remain the stable low-level contract.

## Positioning

- Best for deterministic agent workflows that need official Singapore data
- Optimized for tool calls, not free-form analyst chat
- Current depth spans 11 data families: SingStat, MAS, OneMap, URA, LTA DataMall, NEA, HDB, CEA, BCA, ACRA, and data.gov.sg
- Multi-step workflows are intentionally bounded and transparent

## Stable Scope

### SingStat

Use for dataset discovery and structured statistical retrieval.

- `sg_singstat_search`
  Search SingStat tables by keyword.
  Input: `{ "keyword": "GDP", "limit": 5 }`
- `sg_singstat_table`
  Read a specific table once you know the table ID.
  Input: `{ "tableId": "M015631", "timeFilter": "2020,2024", "variables": ["GDP Growth Rate"] }`
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
  Input: `{ "startLat": 1.3, "startLng": 103.8, "endLat": 1.31, "endLng": 103.81, "routeType": "drive" }`
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

### LTA DataMall

Use for live transport operations.

- `sg_lta_bus_arrivals`
  Bus-arrival predictions for a stop and optional service number.
- `sg_lta_train_alerts`
  Train service disruption and line-status alerts.
- `sg_lta_traffic_incidents`
  Live traffic incidents.

### NEA

Use for live environment conditions.

- `sg_nea_forecast_2hr`
  2-hour weather forecast by area.
- `sg_nea_air_quality`
  PSI and PM2.5 by region.
- `sg_nea_rainfall`
  Rainfall readings by station.

### HDB

Use for curated public-housing market checks over official data.gov.sg datasets.

- `sg_hdb_resale_prices`
  Resale records filtered by town, flat type, and month range.
- `sg_hdb_rental_prices`
  Rental records filtered by town, flat type, and month range.

### CEA

Use for curated estate-agent diligence.

- `sg_cea_salespersons`
  Exact-match salesperson lookup by salesperson, registration number, estate agent, or estate-agent licence number.

### BCA

Use for curated builder and contractor diligence.

- `sg_bca_licensed_builders`
  Exact-match lookup by company, UEN, builder class, or class code.
- `sg_bca_registered_contractors`
  Exact-match lookup by company, UEN, workhead, or grade.

### ACRA

Use for curated company-registry diligence over the official sharded public entity collection.

- `sg_acra_entities`
  Exact-match entity lookup by company name or UEN.

### data.gov.sg

Use as the general discovery fallback.

- `sg_datagov_search`
  Search datasets by keyword across the full paginated index.
- `sg_datagov_get`
  Metadata lookup only.
  Input: `{ "datasetId": "<dataset-id>" }`
- `sg_datagov_browse`
  Browse collections across the full paginated index.

Do not expect `sg_datagov_get` to return paginated dataset rows.

## Operational Tools

- `sg_health_check`
  Reports each core upstream as configured or unconfigured, plus reachable or unreachable.
- `sg_key_set`, `sg_key_list`, `sg_key_delete`
  Local credential helpers.
- `sg_cache_stats`, `sg_cache_clear`
  Cache inspection and maintenance.
- `sg_config_get`, `sg_config_set`
  Runtime config for supported mutable keys only.
- `sg_query`
  Preferred bounded workflow planner and executor for covered routed families.

## Workflow Recipes

### Macro Snapshot

```text
sg_query { "query": "Macro snapshot of Singapore", "mode": "execute" }
sg_singstat_search { "keyword": "GDP Singapore" }
sg_singstat_search { "keyword": "CPI Singapore" }
sg_mas_exchange_rates { "currency": "USD" }
sg_mas_interest_rates {}
```

### Demographic Profile

```text
sg_query { "query": "Demographic profile for postal code 168742", "mode": "execute" }
sg_onemap_population { "planningArea": "Tampines", "dataType": "getPopulationAgeGroup" }
sg_onemap_population { "planningArea": "Tampines", "dataType": "getHouseholdMonthlyIncomeWork" }
```

### Property And Regulatory Due Diligence

```text
sg_query { "query": "Property due diligence for Bedok HDB resale", "mode": "execute" }
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok" }
sg_ura_planning_area { "planningArea": "Bedok" }
sg_hdb_resale_prices { "town": "Bedok" }
```

### Property Counterparty Diligence

```text
sg_query { "query": "Run registry check for company ABC CONSTRUCTION PTE LTD", "mode": "execute" }
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok" }
sg_hdb_resale_prices { "town": "Bedok", "flatType": "4 ROOM" }
sg_cea_salespersons { "estateAgentName": "ERA REALTY NETWORK PTE LTD" }
sg_acra_entities { "entityName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD" }
```

### Business Registry Diligence

```text
sg_query { "query": "Run registry check for company ABC CONSTRUCTION PTE LTD", "mode": "execute" }
sg_acra_entities { "entityName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD" }
sg_cea_salespersons { "registrationNo": "R123456A" }
```

### Dataset Discovery Fallback

```text
sg_query { "query": "Find datasets about hawker centres", "mode": "execute" }
sg_datagov_search { "keyword": "hawker centres" }
sg_datagov_get { "datasetId": "<dataset-id-from-search>" }
```

## `sg_query`

Supported uses:

- plan or execute bounded workflows
- single-step routing to covered direct tools
- macro, demographic, property, business-registry, dataset, transport, and environment workflows

Unsupported uses:

- general planning across arbitrary goals
- automatic comparison workflows
- hidden fan-out beyond the bounded workflow catalog
- hidden row-level data.gov.sg extraction beyond the explicit direct tools

When unsupported, call the direct tools yourself.

## Authentication

Recommended production path:

- `SG_API_ONEMAP_EMAIL`
- `SG_API_ONEMAP_PASSWORD`
- `SG_API_URA_KEY`
- `SG_API_LTA_KEY`

Local fallback through MCP tools:

```text
sg_key_set { "apiName": "onemap_email", "key": "you@example.com" }
sg_key_set { "apiName": "onemap_password", "key": "your-password" }
sg_key_set { "apiName": "ura", "key": "your-ura-api-key" }
sg_key_set { "apiName": "lta", "key": "your-lta-api-key" }
```

HDB, CEA, BCA, and ACRA use official data.gov.sg datasets and do not need separate credentials.

The local keystore is convenient for development, but it is not a managed secret store.
