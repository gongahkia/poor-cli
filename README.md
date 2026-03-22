# sg-apis-mcp

Tool-first MCP server for agent builders working with Singapore government data.

The canonical surface is the direct `sg_*` tools. Today the repo exposes 28 tools total:
- 19 direct data tools across 5 official API families
- 8 operational helpers for health, keys, cache, and config
- 1 experimental router, `sg_query`

`sg_query` is intentionally narrow. It only routes supported single-step requests to one direct tool. It does not perform hidden fan-out, chaining, or comparison workflows.

## Product Scope

This pilot goes deep on five sources only:
- SingStat for macroeconomic and statistical datasets
- MAS for exchange rates, SORA, and banking statistics
- OneMap for geocoding, routing, demographics, and coordinate conversion
- URA for property transactions, planning-area lookup, and development charges
- data.gov.sg for dataset discovery plus metadata lookup

This phase is not a general Singapore super-connector. It does not add LTA, weather, parliamentary, or other adjacent APIs.

## Stable Surface

| API | Direct tools | Current scope | Auth |
|-----|--------------|---------------|------|
| SingStat | 5 | Search, browse, table reads, time series, explicit compare | None |
| MAS | 3 | Exchange rates by latest or exact date, SORA only, banking stats only | None |
| OneMap | 5 | Geocode, reverse geocode, route, planning-area demographics, coordinate conversion | Email + password |
| URA | 3 | Property transactions, planning-area lookup by name or coordinates, development charges | API key |
| data.gov.sg | 3 | Dataset search, browse, and metadata lookup | None |

Notes:
- `sg_mas_exchange_rates` supports latest or exact-date lookup. It does not expose synthetic date ranges.
- `sg_mas_interest_rates` is SORA-only in this phase.
- `sg_mas_financial_stats` is banking-only in this phase.
- `sg_datagov_get` returns dataset metadata only. It does not page, filter, or read dataset rows.
- `sg_query` is experimental and should not be treated as the product contract.

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

The keystore helpers are still available for local use:
- `sg_key_set { "apiName": "onemap_email", "key": "..." }`
- `sg_key_set { "apiName": "onemap_password", "key": "..." }`
- `sg_key_set { "apiName": "ura", "key": "..." }`

The local keystore is a convenience fallback, not a secret-management system.

## Workflow Recipes

These are the intended product workflows for this phase. Build them explicitly with the direct tools.

### 1. Macro Snapshot
Goal: combine macro indicators from SingStat with MAS rates.

```text
sg_singstat_search { "keyword": "GDP Singapore" }
sg_singstat_search { "keyword": "CPI Singapore" }
sg_mas_exchange_rates { "currency": "USD" }
sg_mas_interest_rates {}
```

### 2. Area Demographics
Goal: inspect the demographic profile of a planning area.

```text
sg_onemap_population { "planningArea": "Tampines", "dataType": "getPopulationAgeGroup" }
sg_onemap_population { "planningArea": "Tampines", "dataType": "getHouseholdMonthlyIncomeWork" }
```

### 3. Property And Location Due Diligence
Goal: pair URA property data with location context from OneMap.

```text
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok" }
sg_ura_planning_area { "planningArea": "Bedok" }
sg_onemap_geocode { "searchVal": "Bedok" }
```

### 4. Dataset Discovery Fallback
Goal: find a relevant Singapore dataset when the domain-specific APIs do not cover the topic.

```text
sg_datagov_search { "keyword": "hawker centres" }
sg_datagov_get { "datasetId": "<dataset-id-from-search>" }
```

## `sg_query`

`sg_query` is an experimental convenience layer for prompts like:
- "What was SORA on 2024-01-31?"
- "Show the master plan zoning for Bedok"
- "Find 168742"

Use the direct tools instead when you need:
- comparisons
- chained workflows
- multi-API synthesis
- predictable contracts for production agents

## Development

```bash
npm install
npm run verify
```

## Related APIs Not Covered Here

- LTA DataMall
- NEA weather and haze
- HDB row-level transactional datasets
- other Singapore public-data surfaces outside the five API families above

## License

MIT
