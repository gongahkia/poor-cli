# Transport Brief Demo

## Run It

```bash
npm install
npm run build
npm run demo:mcp -- transport
```

## Prompt

```text
Give me a transport status snapshot for Singapore right now, and include stop-level arrivals for bus stop 83139 service 851.
```

## What It Exercises

- resource: `sg://workflows`
- direct tool: `sg_lta_bus_arrivals`
- brief tool: `sg_transport_brief`
- routed workflow: `sg_query`

## Why The Brief Is Better Than Raw Calls

Raw transport monitoring means checking bus arrivals, train alerts, and traffic incidents independently, then deciding how to present network-wide status versus stop-level optional detail.

`sg_transport_brief` returns one operational artifact with:

- optional stop-level bus timing
- network-wide train alert coverage
- live traffic incident coverage
- explicit no-route-planning and no-prediction limits

## Sample Output Shape

```json
{
  "title": "Transport Brief",
  "summary": [
    { "label": "Bus stop", "value": "83139", "source": "LTA" },
    { "label": "Service number", "value": "851", "source": "LTA" },
    { "label": "Primary train line", "value": "NSL", "source": "LTA" }
  ],
  "evidence": [
    { "label": "Bus services", "value": 1, "source": "LTA" },
    { "label": "Traffic incidents", "value": 1, "source": "LTA" }
  ],
  "gaps": [],
  "provenance": [
    { "source": "LTA", "tool": "sg_lta_train_alerts", "coverage": "Network-wide train service alert coverage and operator messages.", "authRequired": true, "recordCount": 1 }
  ],
  "freshness": [
    { "source": "LTA train alerts", "observedAt": "2026-03-26T03:00:00.000Z", "upstreamTimestamp": "2026-03-26T08:00:00+08:00" }
  ],
  "limits": [
    { "code": "NO_ROUTE_PLANNING", "message": "Use sg_onemap_route for route planning; this brief only summarizes transport operations status." }
  ]
}
```

