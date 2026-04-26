# Outcome Example: Relocation Assistant

Build a neighbourhood briefing flow that turns a postal code or planning area into a bounded relocation packet.

## User Job

"I am moving near 460123. Show me property context, nearby civic services, transport status, and weather/air-quality signals."

## Recommended Flow

1. Resolve the location and property context:

```text
sg_property_brief {
  "postalCode": "460123",
  "includeTransport": true,
  "includeEnvironment": true,
  "format": "json"
}
```

2. Add family and community services:

```text
sg_civic_brief {
  "postalCode": "460123",
  "modules": ["pa", "sportsg", "ecda", "msf"],
  "format": "json"
}
```

3. If the caller asks for current conditions, refresh live signals:

```text
sg_transport_brief { "format": "json" }
sg_environment_brief { "format": "json" }
```

## Product Shape

- Map or list view: resolved planning area, nearest services, and evidence records.
- Decision panel: freshness, gaps, and limits from every brief.
- Follow-up actions: expose each `nextChecks[]` item as a button that calls the direct tool.

## Boundaries

Do not turn this into a property recommendation engine. The product should say what public data says, what is fresh, what failed, and which direct checks are available next.
