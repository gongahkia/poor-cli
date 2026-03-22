# sg-apis-mcp

Agent skill + MCP server for Singapore government data. Provides 21 tools across 5 APIs: SingStat (economics), MAS (finance), OneMap (geospatial), URA (property), and data.gov.sg (general datasets).

## Quickstart

```bash
# Install and run
npx sg-apis-mcp

# Or add to Claude Desktop (claude_desktop_config.json)
{
  "mcpServers": {
    "sg-apis": {
      "command": "npx",
      "args": ["sg-apis-mcp"]
    }
  }
}

# Or add to Claude Code
claude mcp add sg-apis-mcp -- npx sg-apis-mcp
```

## Architecture

```
AI Agent (Claude, Cursor, etc.)
        │
        │ MCP Protocol (stdin/stdout)
        ▼
┌──────────────────┐
│   MCP Server      │ ← 21 tools registered
│   (sg-apis-mcp)   │
│                   │
│   Cache → Dedup   │
│   Rate Limiter    │
│   Circuit Breaker │
└────────┬─────────┘
         │
    ┌────┼────┬────┬────┐
    ▼    ▼    ▼    ▼    ▼
SingStat MAS OneMap URA data.gov.sg
```

## API Coverage

| API | Tools | Auth | Rate Limit | Key Endpoints |
|-----|-------|------|------------|---------------|
| SingStat | 5 (search, table, timeseries, compare, browse) | None | Conservative | Table Builder |
| MAS | 3 (exchange_rates, interest_rates, financial_stats) | None | Conservative | Datastore API |
| OneMap | 5 (geocode, reverse_geocode, route, population, convert_coords) | Email+Password | 250/min | Search, Route, Population |
| URA | 3 (property_transactions, planning_area, dev_charges) | API Key | Slow | Property, Planning |
| data.gov.sg | 3 (search, get, browse) | None | Moderate | Datasets v2 API |
| System | 5 (health_check, key_set/list/delete, cache_stats/clear, config_get/set) | N/A | N/A | Internal |

## Not Covered

These Singapore APIs are handled by other MCP servers:
- **LTA DataMall** (bus arrivals, traffic, parking) → [arjunkmrm/mcp-sg-lta](https://github.com/arjunkmrm/mcp-sg-lta)
- **Weather, Carpark, Dengue** → [prezgamer/Singapore-Data-MCPs](https://github.com/prezgamer/Singapore-Data-MCPs)

## API Key Setup

| API | Required | Setup |
|-----|----------|-------|
| SingStat | No | — |
| MAS | No | — |
| OneMap | Yes | `sg_key_set { "apiName": "onemap_email", "key": "..." }` |
| URA | Yes | `sg_key_set { "apiName": "ura", "key": "..." }` |
| data.gov.sg | No | — |

Or use environment variables: `SG_API_ONEMAP_EMAIL`, `SG_API_ONEMAP_PASSWORD`, `SG_API_URA_KEY`.

## Development

```bash
npm install
npm run build
npm test
npm run dev          # watch mode
npm run mock-server  # local API mock
```

## License

MIT
