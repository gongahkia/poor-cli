---
name: sg-apis
description: Singapore government data — economics, demographics, geospatial, property, finance
version: 0.1.0
mcp_server: sg-apis-mcp
---

# Singapore Government Data Skill

Access Singapore's official government data through 21 MCP tools spanning 5 APIs: SingStat (economics), MAS (finance), OneMap (geospatial), URA (property), and data.gov.sg (general).

## Tools

### SingStat (Economy & Statistics)

#### `sg_singstat_search`
Search SingStat Table Builder for datasets matching a keyword. Returns dataset IDs, titles, and update frequency.

**Input:**
- `keyword` (string, required) — Search keyword (e.g., "GDP", "population", "CPI")
- `limit` (number, optional) — Max results (default: 20)

**Example:**
```json
{ "keyword": "GDP", "limit": 5 }
```

#### `sg_singstat_table`
Retrieve data from a specific SingStat table. Use `sg_singstat_search` first to find table IDs.

**Input:**
- `tableId` (string, required) — Table ID from search results (e.g., "M015631")
- `timeFilter` (string, optional) — Year range (e.g., "2020,2025")
- `variables` (string[], optional) — Variable codes to filter
- `format` (string, optional) — "json" | "markdown" | "csv" | "geojson"

**Example:**
```json
{ "tableId": "M015631", "timeFilter": "2020,2025" }
```

#### `sg_singstat_timeseries`
Get time series data for a specific indicator from a SingStat table.

**Input:**
- `tableId` (string, required) — Table ID
- `indicator` (string, required) — Indicator name to match
- `startYear` (number, required) — Start year
- `endYear` (number, required) — End year
- `format` (string, optional) — Output format

**Example:**
```json
{ "tableId": "M015631", "indicator": "GDP", "startYear": 2019, "endYear": 2024 }
```

#### `sg_singstat_compare`
Compare multiple SingStat indicators side by side.

**Input:**
- `queries` (array, required) — Array of `{ tableId, indicator, label }`
- `startYear` (number, optional) — Start year
- `endYear` (number, optional) — End year
- `format` (string, optional) — Output format

**Example:**
```json
{
  "queries": [
    { "tableId": "M015631", "indicator": "GDP", "label": "GDP Growth" },
    { "tableId": "M213171", "indicator": "CPI", "label": "CPI" }
  ],
  "startYear": 2019,
  "endYear": 2024
}
```

#### `sg_singstat_browse`
Browse SingStat dataset categories.

**Input:**
- `category` (string, optional) — Category to browse (e.g., "Economy", "Population")

### MAS (Finance & Monetary)

#### `sg_mas_exchange_rates`
Get MAS exchange rates for SGD against foreign currencies. Supports latest data or an exact date lookup.

**Input:**
- `currency` (string, optional) — 3-letter currency code (e.g., "USD", "EUR")
- `date` (string, optional) — Exact date (YYYY-MM-DD)
- `format` (string, optional) — Output format

**Example:**
```json
{ "currency": "USD", "date": "2024-01-01" }
```

#### `sg_mas_interest_rates`
Get MAS interest rates. This phase supports SORA only.

**Input:**
- `date` (string, optional) — Exact date (YYYY-MM-DD)
- `format` (string, optional) — Output format

#### `sg_mas_financial_stats`
Get MAS financial sector statistics. This phase supports banking data only.

**Input:**
- `date` (string, optional) — Exact date (YYYY-MM-DD)
- `format` (string, optional) — Output format

### OneMap (Geospatial & Demographics)

#### `sg_onemap_geocode`
Convert a Singapore address, building name, or postal code to coordinates.

**Input:**
- `searchVal` (string, required) — Address, building name, or 6-digit postal code
- `limit` (number, optional) — Max results

**Example:**
```json
{ "searchVal": "Raffles Place" }
```

#### `sg_onemap_reverse_geocode`
Convert coordinates to a Singapore address.

**Input:**
- `lat` (number, required) — Latitude
- `lng` (number, required) — Longitude
- `buffer` (number, optional) — Search radius in meters (default: 50)

#### `sg_onemap_route`
Get routing directions between two Singapore locations.

**Input:**
- `startLat` / `startLng` (number, required) — Start coordinates
- `endLat` / `endLng` (number, required) — End coordinates
- `routeType` (string, required) — "walk" | "drive" | "pt" | "cycle"
- `date` / `time` (string, optional) — For public transport scheduling

**Example:**
```json
{ "startLat": 1.3521, "startLng": 103.8198, "endLat": 1.2830, "endLng": 103.8513, "routeType": "pt" }
```

#### `sg_onemap_population`
Get demographic data for a Singapore planning area.

**Input:**
- `planningArea` (string, required) — e.g., "Tampines", "Bedok", "Jurong East"
- `year` (string, optional) — Census year (default: "2020")
- `dataType` (string, optional) — "getPopulationAgeGroup" | "getEthnicGroup" | "getHouseholdMonthlyIncomeWork" | "getEconomicStatus" | "getTypeOfDwellingHousehold"
- `format` (string, optional) — Output format

#### `sg_onemap_convert_coords`
Convert between SVY21 (Singapore) and WGS84 (GPS) coordinate systems.

**Input:**
- `from` (string, required) — "SVY21" or "WGS84"
- `x` (number, required) — Easting (SVY21) or Latitude (WGS84)
- `y` (number, required) — Northing (SVY21) or Longitude (WGS84)

### URA (Property & Urban Planning)

#### `sg_ura_property_transactions`
Get property transaction data from URA.

**Input:**
- `propertyType` (string, optional) — "residential" | "commercial" | "industrial"
- `area` (string, optional) — Area/project name filter
- `period` (string, optional) — Period in MMYY format (e.g., "0125" for Jan 2025)
- `format` (string, optional) — Output format

**Example:**
```json
{ "propertyType": "residential", "area": "Orchard" }
```

#### `sg_ura_planning_area`
Get URA master plan data for a location or planning area.

**Input:**
- `lat` / `lng` (number, optional) — Coordinates to look up
- `planningArea` (string, optional) — Planning area name

#### `sg_ura_dev_charges`
Get URA development charge rates by use group and sector.

**Input:**
- `useGroup` (string, optional) — e.g., "A" (landed residential), "B1" (non-landed), "C" (commercial)
- `sector` (string, optional) — Sector code

### data.gov.sg (General Datasets)

#### `sg_datagov_search`
Search data.gov.sg for datasets matching a keyword. Covers 2,000+ Singapore government datasets.

**Input:**
- `keyword` (string, required) — Search keyword
- `limit` (number, optional) — Max results (default: 10)

**Example:**
```json
{ "keyword": "hawker centres" }
```

#### `sg_datagov_get`
Get metadata for a specific data.gov.sg dataset.

**Input:**
- `datasetId` (string, required) — Dataset ID from search results
- `format` (string, optional) — Output format

#### `sg_datagov_browse`
Browse data.gov.sg collections by agency.

**Input:**
- `collection` (string, optional) — Collection/agency name

### System Tools

#### `sg_health_check`
Check connectivity and API key status for all APIs. No input required.

#### `sg_key_set`
Store an API key. Input: `{ "apiName": "ura", "key": "your-api-key" }`

#### `sg_key_list`
List all stored API keys (values masked). No input required.

#### `sg_key_delete`
Delete a stored API key. Input: `{ "apiName": "ura" }`

#### `sg_cache_stats`
Show cache statistics. No input required.

#### `sg_cache_clear`
Clear cached data. Input: `{ "api": "singstat" }` or omit to clear all.

#### `sg_config_get`
Show current configuration. No input required.

#### `sg_config_set`
Update configuration. Input: `{ "key": "defaultFormat", "value": "csv" }`

## Workflows

### 1. Current Exchange Rate
**Query:** "What's the current SGD to USD exchange rate?"

```
→ sg_mas_exchange_rates { "currency": "USD" }
← Returns latest SGD/USD rate
```

### 2. HDB Resale Prices
**Query:** "Show me HDB resale prices in Tampines for 2024"

```
→ sg_datagov_search { "keyword": "HDB resale" }
← Get dataset ID
→ sg_datagov_get { "datasetId": "<id from above>" }
← Returns HDB resale data
```

### 3. Nearest MRT
**Query:** "Find the nearest MRT station to postal code 168742"

```
→ sg_onemap_geocode { "searchVal": "168742" }
← Get coordinates (lat: 1.2825, lng: 103.8447)
→ sg_onemap_geocode { "searchVal": "MRT" }
← Search nearby MRT stations
```

### 4. GDP Growth
**Query:** "What's Singapore's GDP growth rate for the last 5 years?"

```
→ sg_singstat_search { "keyword": "GDP growth" }
← Find table ID (e.g., M015631)
→ sg_singstat_timeseries { "tableId": "M015631", "indicator": "GDP", "startYear": 2019, "endYear": 2024 }
← Returns annual GDP growth values
```

### 5. Property Comparison
**Query:** "Compare property prices between Orchard and Tampines"

```
→ sg_ura_property_transactions { "area": "Orchard" }
→ sg_ura_property_transactions { "area": "Tampines" }
← Present both results side by side
```

### 6. Population Density
**Query:** "What's the population in Bishan?"

```
→ sg_onemap_population { "planningArea": "Bishan", "dataType": "getPopulationAgeGroup" }
← Returns population breakdown
```

## Advanced: Multi-API Queries

### Fan-Out Rules

- **Geographic + Data**: If query mentions a location AND a dataset, geocode first (OneMap), then query the dataset API with location context.
- **Comparison**: If query asks to compare across areas, make parallel calls to the same API with different area filters.
- **Cross-domain**: If query spans domains (e.g., "property prices and population"), fan out to multiple APIs concurrently.

### Multi-API Examples

**Example 1: "Property prices and demographics in Tampines"**
```
→ sg_ura_property_transactions { "area": "Tampines" }     [parallel]
→ sg_onemap_population { "planningArea": "Tampines" }      [parallel]
← Combine: property data + population data for Tampines
```

**Example 2: "Compare GDP growth with exchange rate trends"**
```
→ sg_singstat_timeseries { "tableId": "M015631", "indicator": "GDP", "startYear": 2019, "endYear": 2024 }  [parallel]
→ sg_mas_exchange_rates { "currency": "USD" }                                                                [parallel]
← Align by date, present as comparison table
```

**Example 3: "What housing types are near 168742?"**
```
→ sg_onemap_geocode { "searchVal": "168742" }              [step 1]
← Get planning area from coordinates
→ sg_onemap_population { "planningArea": "<area>", "dataType": "getTypeOfDwellingHousehold" }  [step 2]
← Returns housing type breakdown for that area
```

### Source Attribution
Always attribute data sources in multi-API responses:
- "Sources: SingStat, MAS" or "Source: URA Property Transactions"
- Note partial failures: "Note: MAS query failed: API under maintenance"

## Context

### Singapore Terminology

- **HDB** — Housing & Development Board. Singapore's public housing authority. ~80% of residents live in HDB flats. Types: 1-room, 2-room, 3-room, 4-room, 5-room, Executive, DBSS.
- **MRT** — Mass Rapid Transit. Lines: North-South (NS), East-West (EW), North-East (NE), Circle (CC), Downtown (DT), Thomson-East Coast (TE), Jurong Region (JR, under construction), Cross Island (CR, under construction).
- **Planning Areas** — Singapore is divided into 55 planning areas (e.g., Tampines, Bedok, Jurong East). These are the geographic units used by URA, SingStat, and OneMap.
- **Postal Codes** — 6-digit format (e.g., 168742). Unique to each building or block. Used for geocoding.
- **SVY21** — Singapore's national coordinate system. Easting (X) and Northing (Y) in meters. Different from WGS84 (GPS lat/lng). Use `sg_onemap_convert_coords` to convert.
- **GRC/SMC** — Group Representation Constituency / Single Member Constituency — electoral boundaries (different from planning areas).
- **District Codes** — URA property districts 01-28. Used in property transactions.
- **CCR/RCR/OCR** — Core Central Region / Rest of Central Region / Outside Central Region — URA market segments for property analysis.

### Planning Area → Region Mapping

| Region | Planning Areas |
|--------|---------------|
| Central | Bishan, Bukit Merah, Bukit Timah, Downtown Core, Geylang, Kallang, Marine Parade, Museum, Newton, Novena, Orchard, Outram, Queenstown, River Valley, Rochor, Singapore River, Southern Islands, Tanglin, Toa Payoh |
| East | Bedok, Changi, Changi Bay, Pasir Ris, Paya Lebar, Tampines |
| North | Central Water Catchment, Lim Chu Kang, Mandai, Sembawang, Simpang, Sungei Kadut, Woodlands, Yishun |
| North-East | Ang Mo Kio, Hougang, North-Eastern Islands, Punggol, Seletar, Sengkang, Serangoon |
| West | Boon Lay, Bukit Batok, Bukit Panjang, Choa Chu Kang, Clementi, Jurong East, Jurong West, Pioneer, Tengah, Tuas, Western Islands, Western Water Catchment |

## Setup

### Installation

**One-time use:**
```bash
npx sg-apis-mcp
```

**Permanent installation:**
```bash
npm install -g sg-apis-mcp
```

**Claude Desktop** — add to `claude_desktop_config.json`:
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

**Claude Code:**
```bash
claude mcp add sg-apis-mcp -- npx sg-apis-mcp
```

**Cursor** — add to MCP settings:
```json
{
  "sg-apis": {
    "command": "npx",
    "args": ["sg-apis-mcp"]
  }
}
```

### API Key Setup

| API | Auth Required | How to Get |
|-----|--------------|------------|
| SingStat | No | No key needed |
| MAS | No | No key needed |
| OneMap | Yes (email + password) | Register at [onemap.gov.sg](https://www.onemap.gov.sg) |
| URA | Yes (API key) | Register at [ura.gov.sg/maps](https://www.ura.gov.sg/maps) |
| data.gov.sg | No | No key needed (optional key for higher rate limits) |

**Configure via MCP tools:**
```
sg_key_set { "apiName": "onemap_email", "key": "your@email.com" }
sg_key_set { "apiName": "onemap_password", "key": "your-password" }
sg_key_set { "apiName": "ura", "key": "your-ura-api-key" }
```

**Or via environment variables:**
```bash
export SG_API_ONEMAP_EMAIL=your@email.com
export SG_API_ONEMAP_PASSWORD=your-password
export SG_API_URA_KEY=your-ura-api-key
```

### Quick Test

After setup, verify the MCP server is working with a query that needs no API key:

> "What's the current SGD to USD exchange rate?"

This uses the MAS API (no key needed). If you get exchange rate data back, the server is working correctly.
