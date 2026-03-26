# Geospatial Routing Demo

## Run It

```bash
npm install
npm run build
npm run demo:mcp -- geospatial
```

## Prompt

```text
Walk from 049178 to 048616.
```

## What It Exercises

- resource: `sg://recipes`
- direct tool: `sg_onemap_route`
- supporting direct tool: `sg_onemap_reverse_geocode`
- routed workflow: `sg_query`

## Why The Recipe Matters

Agent builders often know they want directions, but they do not want to manually wire geocoding, routing, and fallback messaging on every prompt shape.

This recipe demonstrates that `sg_query` can:

- detect a bounded route-planning prompt
- geocode both endpoints from Singapore postal codes
- call `sg_onemap_route` with explicit route type
- return a blocker when one endpoint is missing instead of guessing
