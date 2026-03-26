# Civic Discovery Demo

## Run It

```bash
npm install
npm run build
npm run demo:mcp -- civic
```

## Prompt

```text
Find a community club near 048616.
```

## What It Exercises

- resource: `sg://recipes`
- direct tool: `sg_pa_community_outlets`
- supporting direct tool: `sg_ecda_childcare_centres`
- routed workflow: `sg_query`

## Why The Recipe Matters

General civic discovery is useful only if it stays deterministic.

This recipe demonstrates that `sg_query` can:

- detect a bounded civic-discovery prompt
- geocode a Singapore postal code before directory search
- route to the right civic family without introducing new credentials
- return a blocker when the prompt says "near me" without a resolvable location
