# Sector Scoped Business Diligence

## Reference Walkthrough

This walkthrough shows how to keep `sg_business_dossier` deterministic while still selecting a narrower business-compliance slice through explicit `modules` and `sectorHints`.

## Prompt

```text
Run sector-scoped business diligence for Marina Bay Sands in hospitality and keep the workflow bounded to company and hotel evidence.
```

## What It Exercises

- resource: `sg://recipes`
- brief tool: `sg_business_dossier`
- direct tools: `sg_hlb_hotels`, `sg_acra_entities`
- routed workflow: `sg_query`

## Why The Workflow Is Better Than Raw Calls

Raw sector-specific diligence often drifts into arbitrary extra lookups. The bounded workflow keeps the scope explicit by selecting only the needed modules and reporting what was intentionally not searched.

The bounded workflow helps by:

- keeping module selection explicit instead of inferred
- surfacing `selectedModules`, `searchedModules`, and `unsearchedModules`
- preserving the same brief contract as the default business dossier

## Sample Output Shape

```json
{
  "title": "Business Dossier",
  "records": {
    "resolution": {
      "selectedModules": ["acra", "hlb"],
      "searchedModules": ["acra", "hlb"],
      "unsearchedModules": ["bca", "boa", "cea", "gebiz", "hsa"]
    }
  },
  "limits": [
    {
      "code": "MODULE_BOUNDED",
      "message": "This dossier was intentionally scoped to explicit business-diligence modules."
    }
  ]
}
```
