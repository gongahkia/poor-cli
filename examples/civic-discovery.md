# Civic Discovery Example

## Prompt

```text
Find a family service centre near 560230.
```

## What It Exercises

- resource: `sg://recipes`
- direct tool: `sg_msf_family_services`
- supporting direct tool: `sg_msf_student_care_services`
- routed workflow: `sg_query`

## Why The Recipe Matters

General civic discovery is useful only if it stays deterministic.

This recipe demonstrates that `sg_query` can:

- detect a bounded civic-discovery prompt
- geocode a Singapore postal code before directory search
- route to the right civic family without introducing new credentials
- return a blocker when the prompt says "near me" without a resolvable location
