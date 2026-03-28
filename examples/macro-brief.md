# Macro Brief Example

## Prompt

```text
Give me a Singapore macro snapshot with USD/SGD, SORA, GDP, and CPI.
```

## What It Exercises

- resource: `sg://workflows`
- direct tool: `sg_mas_exchange_rates`
- brief tool: `sg_macro_brief`
- routed workflow: `sg_query`

## Why The Brief Is Better Than Raw Calls

Raw macro setup means querying multiple MAS series and then separately reading the right SingStat GDP and CPI tables for the next step.

`sg_macro_brief` returns one starter artifact with:

- latest currency and rate context
- validated SingStat table IDs and current periods
- freshness markers
- explicit limits around what the brief does not infer

## Sample Output Shape

```json
{
  "title": "Macro Brief",
  "summary": [
    { "label": "USD/SGD", "value": 1.35, "source": "MAS" },
    { "label": "SORA metric", "value": 3.2, "source": "MAS" },
    { "label": "GDP table ID", "value": "M015631", "source": "SingStat" },
    { "label": "CPI YoY table ID", "value": "M213781", "source": "SingStat" }
  ],
  "evidence": [
    { "label": "FX rows", "value": 1, "source": "MAS" },
    { "label": "GDP rows", "value": 1, "source": "SingStat" }
  ],
  "gaps": [],
  "provenance": [
    { "source": "MAS", "tool": "sg_mas_exchange_rates", "coverage": "Exchange-rate coverage for the requested currency and date range.", "authRequired": false, "recordCount": 1 }
  ],
  "freshness": [
    { "source": "MAS exchange rates", "observedAt": "2026-03-26T03:00:00.000Z", "upstreamTimestamp": "2026-03-26" }
  ],
  "limits": [
    { "code": "STARTER_SNAPSHOT", "message": "This brief is a compact macro starter, not a full economic research note or narrative analysis." }
  ]
}
```
