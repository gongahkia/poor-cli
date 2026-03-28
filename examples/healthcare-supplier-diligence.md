# Healthcare Supplier Diligence

## Runnable Walkthrough

Run the built-in mock-backed profile end to end:

```bash
npm run demo:mcp -- healthcare
```

## Prompt

```text
Run healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD. and include HSA, ACRA, and procurement evidence where available.
```

## What It Exercises

- resource: `sg://workflows`
- direct tools: `sg_hsa_health_product_licensees`, `sg_hsa_licensed_pharmacies`, `sg_gebiz_tenders`
- brief tool: `sg_business_dossier`
- routed workflow: `sg_query`

## Why The Workflow Is Better Than Raw Calls

Raw evidence collection means calling HSA licensee rows, optional pharmacy rows, ACRA, and procurement evidence separately, then deciding how to reconcile exact and fuzzy matches yourself.

The bounded workflow keeps the output honest by:

- keeping HSA licensing evidence as the primary surface
- returning unmatched modules explicitly instead of hiding partial coverage
- surfacing next checks when a supplier needs deeper pharmacy or procurement verification

## Sample Output Shape

```json
{
  "status": "completed",
  "mode": "execute",
  "workflow": "healthcare_supplier_diligence",
  "intent": "business",
  "toolsUsed": ["sg_business_dossier"],
  "resultSummary": {
    "level": "informational",
    "headline": "Healthcare supplier diligence completed with HSA licensing evidence and bounded procurement context."
  },
  "nextActions": [
    {
      "tool": "sg_hsa_licensed_pharmacies",
      "reason": "Check whether the supplier also appears in the licensed pharmacy register.",
      "input": { "pharmacyName": "A.M. Pharmacy Pte Ltd" }
    }
  ]
}
```
