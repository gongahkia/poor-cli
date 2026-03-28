# Property Brief Example

## Prompt

```text
Build a property brief for Bedok resale flats with environment and transport context.
```

## What It Exercises

- resource: `sg://workflows`
- direct tool: `sg_hdb_resale_prices`
- brief tool: `sg_property_brief`
- routed workflow: `sg_query`

## Why The Brief Is Better Than Raw Calls

Raw property diligence means resolving the location first, then manually stitching together URA planning context, URA transactions, HDB market reads, and optional NEA or LTA signals.

`sg_property_brief` returns one bounded artifact with:

- resolved planning area and region
- market context from URA and HDB
- optional live environment and transport context
- explicit non-recommendation boundaries

## Sample Output Shape

```json
{
  "title": "Property Brief",
  "summary": [
    { "label": "Resolved planning area", "value": "Bedok", "source": "URA" },
    { "label": "Region", "value": "East", "source": "URA" },
    { "label": "HDB resale average", "value": 560000, "source": "HDB" }
  ],
  "evidence": [
    { "label": "URA transactions", "value": 1, "source": "URA" },
    { "label": "HDB resale records", "value": 1, "source": "HDB" }
  ],
  "gaps": [],
  "provenance": [
    { "source": "URA", "tool": "sg_ura_property_transactions", "coverage": "Private market transaction context for the resolved planning area.", "authRequired": true, "recordCount": 1 }
  ],
  "freshness": [
    { "source": "HDB resale", "observedAt": "2026-03-26T03:00:00.000Z", "upstreamTimestamp": "2026-03" }
  ],
  "limits": [
    { "code": "NOT_A_RECOMMENDATION", "message": "This brief is bounded diligence context, not a valuation, investment score, or purchase recommendation." }
  ]
}
```
