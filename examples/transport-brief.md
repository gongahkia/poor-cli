# Transport Brief Example

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

- analyst-grade status, coverage, and signal summaries
- network rollups for train lines and traffic incident types
- optional stop-level detail with next arrival and per-service arrivals
- follow-up actions and bounded raw supporting rows
- explicit no-route-planning and no-prediction limits

## Sample Output Shape

```json
{
  "title": "Transport Brief",
  "summary": [
    { "label": "Transport status", "value": "disrupted", "source": "LTA" },
    { "label": "Focus", "value": "bus stop 83139 service 851", "source": "LTA" },
    { "label": "Primary driver", "value": "train alerts on NSL", "source": "LTA" }
  ],
  "evidence": [
    { "label": "Bus services observed", "value": 1, "source": "LTA" },
    { "label": "Train alerts observed", "value": 1, "source": "LTA" },
    { "label": "Train messages observed", "value": 1, "source": "LTA" },
    { "label": "Traffic incidents", "value": 1, "source": "LTA" }
  ],
  "records": {
    "status": { "level": "disrupted", "headline": "Train disruptions reported on NSL for bus stop 83139 service 851.", "focus": "bus stop 83139 service 851" },
    "coverage": {
      "bus": { "status": "available", "requestedBusStopCode": "83139", "requestedServiceNo": "851", "servicesObserved": 1 },
      "train": { "status": "alerts_active", "alertCount": 1, "messageCount": 1 },
      "traffic": { "status": "incidents_active", "incidentCount": 1 }
    },
    "network": {
      "trainAlertCount": 1,
      "trainMessageCount": 1,
      "trainByLine": { "NSL": 1 },
      "trafficIncidentCount": 1,
      "trafficByType": { "Road Works": 1 }
    },
    "stop": { "busStopCode": "83139", "serviceNo": "851", "serviceCount": 1, "nextArrival": "2026-03-26T08:05:00+08:00" },
    "followups": [{ "tool": "sg_lta_bus_arrivals", "reason": "Inspect stop-level bus arrivals for the current transport focus.", "input": { "busStopCode": "83139", "serviceNo": "851" } }]
  },
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
