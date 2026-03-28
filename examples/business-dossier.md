# Business Dossier Example

## Prompt

```text
Run registry diligence for company ABC CONSTRUCTION PTE LTD workhead CW01.
```

## What It Exercises

- resource: `sg://workflows`
- direct tool: `sg_acra_entities`
- brief tool: `sg_business_dossier`
- routed workflow: `sg_query`

## Why The Brief Is Better Than Raw Calls

Raw evidence collection means calling ACRA, BCA licensed builders, BCA registered contractors, and optionally CEA separately, then deciding how to report gaps and exact-match misses yourself.

`sg_business_dossier` returns one bounded artifact with:

- exact-match outcomes
- registry coverage by source
- freshness markers
- explicit scope limits

## Sample Output Shape

```json
{
  "title": "Business Dossier",
  "summary": [
    { "label": "Entity", "value": "ABC CONSTRUCTION PTE LTD", "source": "ACRA" },
    { "label": "UEN", "value": "201912345K", "source": "ACRA" },
    { "label": "Registered contractor", "value": "CW01", "source": "BCA" }
  ],
  "evidence": [
    { "label": "ACRA matches", "value": 1, "source": "ACRA" },
    { "label": "BCA licensed-builder matches", "value": 1, "source": "BCA" }
  ],
  "gaps": [],
  "provenance": [
    { "source": "ACRA", "tool": "sg_acra_entities", "coverage": "Exact-match company and UEN registry evidence.", "authRequired": false, "recordCount": 1 }
  ],
  "freshness": [
    { "source": "ACRA", "observedAt": "2026-03-26T03:00:00.000Z", "upstreamTimestamp": "2026-03-01" }
  ],
  "limits": [
    { "code": "EXACT_MATCH_ONLY", "message": "Registry checks are exact-match oriented for company, UEN, salesperson, and estate-agent identifiers." }
  ]
}
```
