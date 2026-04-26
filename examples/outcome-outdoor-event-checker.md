# Outcome Example: Outdoor Event Checker

Build a lightweight operations check for outdoor events in Singapore.

## User Job

"We have an outdoor event this afternoon. Check rain, air quality, nearby transport disruptions, and relevant public notices."

## Recommended Flow

1. Start with weather and air quality:

```text
sg_environment_brief {
  "area": "Marina Bay",
  "format": "json"
}
```

2. Add transport status:

```text
sg_transport_brief { "format": "json" }
```

3. Add official feed discovery for alerts or advisories:

```text
sg_gov_feed_items {
  "stream": "weather",
  "limit": 10
}
```

## Product Shape

- Status strip: forecast risk, PSI/PM2.5, rainfall signal, train alerts, traffic incidents.
- Operations checklist: `nextChecks[]` from the brief plus manual escalation states.
- Evidence drawer: provenance and freshness per source.

## Boundaries

This is a public-signal monitor, not a severe-weather forecast or safety authority. Show stale or missing upstream signals plainly.
