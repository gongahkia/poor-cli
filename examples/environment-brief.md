# Environment Brief Demo

## Run It

```bash
npm install
npm run build
npm run demo:mcp -- environment
```

## Prompt

```text
Give me an environment snapshot for Singapore right now, with forecast for Tampines, East-region air quality, and rainfall where available.
```

## What It Exercises

- resource: `sg://workflows`
- direct tool: `sg_nea_forecast_2hr`
- brief tool: `sg_environment_brief`
- routed workflow: `sg_query`

## Why The Brief Is Better Than Raw Calls

Raw environment monitoring means calling forecast, air-quality, and rainfall separately, then reconciling area, region, and station coverage differences yourself.

`sg_environment_brief` returns one live artifact with:

- analyst-grade status, coverage, and signal summaries
- threshold bands with a plain-language advisory and reasons
- resolved focus context for area, region, and rainfall station
- follow-up actions and bounded raw supporting rows
- explicit coverage caveats in `limits`

## Sample Output Shape

```json
{
  "title": "Environment Brief",
  "summary": [
    { "label": "Monitoring status", "value": "watch", "source": "NEA" },
    { "label": "Focus", "value": "area Tampines, region East, station S107", "source": "NEA" },
    { "label": "Primary driver", "value": "rainfall", "source": "NEA" }
  ],
  "evidence": [
    { "label": "Forecast rows", "value": 1, "source": "NEA" },
    { "label": "Air-quality rows", "value": 1, "source": "NEA" },
    { "label": "Rainfall rows", "value": 1, "source": "NEA" }
  ],
  "records": {
    "status": { "level": "watch", "headline": "Environmental watch signals detected for area Tampines, region East, station S107." },
    "coverage": {
      "forecast": { "status": "available", "requestedArea": "Tampines", "resolvedArea": "Tampines", "rowCount": 1 },
      "airQuality": { "status": "available", "requestedRegion": "East", "resolvedRegion": "East", "rowCount": 1 },
      "rainfall": { "status": "available", "requestedStationId": "S107", "resolvedStationId": "S107", "resolvedStationName": "Tampines", "rowCount": 1 }
    },
    "thresholds": {
      "forecastRisk": "clear",
      "airQualityBand": "clear",
      "rainfallBand": "watch",
      "advisory": "Carry umbrella, monitor conditions",
      "reasons": ["light rainfall detected"]
    },
    "focus": { "area": "Tampines", "region": "East", "stationId": "S107", "stationName": "Tampines" },
    "followups": [{ "tool": "sg_nea_forecast_2hr", "reason": "Inspect the focused 2-hour forecast directly.", "input": { "area": "Tampines" } }]
  },
  "gaps": [],
  "provenance": [
    { "source": "NEA", "tool": "sg_nea_forecast_2hr", "coverage": "2-hour forecast coverage for the requested area or the first available forecast area.", "authRequired": false, "recordCount": 1 }
  ],
  "freshness": [
    { "source": "NEA forecast", "observedAt": "2026-03-26T03:00:00.000Z", "upstreamTimestamp": "2026-03-26T08:00:00+08:00" }
  ],
  "limits": [
    { "code": "LIVE_SNAPSHOT_ONLY", "message": "This brief summarizes current NEA conditions and does not replace severe-weather alerts or long-range forecasting." }
  ]
}
```
