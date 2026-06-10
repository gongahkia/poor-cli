# Architecture Firm Diligence

## Prompt

```text
Run architecture firm diligence for DP Architects and include BOA, ACRA, and procurement evidence where available.
```

## What It Exercises

- resource: `sg://workflows`
- direct tools: `sg_boa_architecture_firms`, `sg_boa_architects`, `sg_gebiz_tenders`
- brief tool: `sg_business_dossier`
- routed workflow: `sg_query`

## Why The Workflow Is Better Than Raw Calls

Raw evidence collection means calling BOA firm rows, BOA architect rows, ACRA, and optional procurement evidence separately, then deciding how to explain missing modules and confidence yourself.

The bounded workflow keeps the output honest by:

- selecting only architecture-relevant modules
- surfacing `matchConfidence`, `matchedOn`, and `unmatchedModules`
- keeping procurement evidence optional instead of silently widening the brief

## Sample Output Shape

```json
{
  "status": "completed",
  "mode": "execute",
  "workflow": "architecture_firm_diligence",
  "intent": "business",
  "toolsUsed": ["sg_business_dossier"],
  "resultSummary": {
    "level": "informational",
    "headline": "Architecture-firm diligence completed with BOA, ACRA, and procurement-scoped evidence."
  },
  "nextActions": [
    {
      "tool": "sg_boa_architects",
      "reason": "Inspect the registered architects linked to the matched firm.",
      "input": { "firmName": "DP Architects" }
    }
  ]
}
```
