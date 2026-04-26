# Outcome Example: Procurement Monitor

Build a watchlist for Singapore public procurement and supplier diligence.

## User Job

"Monitor tender awards for a supplier and show whether the entity matches public registry records."

## Recommended Flow

1. Check registry identity first:

```text
sg_business_dossier {
  "entityName": "Example Supplier Pte Ltd",
  "modules": ["acra", "gebiz"],
  "sectorHints": ["procurement"],
  "format": "json"
}
```

2. Pull procurement records directly for scheduled jobs:

```text
sg_gebiz_tenders {
  "supplierName": "Example Supplier Pte Ltd",
  "limit": 25
}
```

3. Store only bounded evidence:

```text
sg_datagov_resources {
  "datasetId": "<dataset-id-from-discovery>"
}
```

## Product Shape

- Supplier watchlist: entity name, UEN, match confidence, latest tender evidence.
- Alert conditions: new awards, unmatched supplier names, stale registry data, source gaps.
- Audit trail: tool name, input, freshness, and provenance for each record.

## Boundaries

This is tender discovery and public registry evidence. Do not infer vendor risk, financial quality, or compliance status without licensed review.
