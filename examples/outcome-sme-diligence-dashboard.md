# Outcome Example: SME Diligence Dashboard

Build a registry-first diligence dashboard for a Singapore company or UEN.

## User Job

"Check whether this counterparty is a live company and show any sector-specific public evidence."

## Recommended Flow

1. Start with the bounded dossier:

```text
sg_business_dossier {
  "entityName": "DP Architects",
  "modules": ["acra", "boa", "gebiz"],
  "sectorHints": ["architecture", "procurement"],
  "format": "json"
}
```

2. For healthcare suppliers, swap the sector modules:

```text
sg_business_dossier {
  "entityName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.",
  "modules": ["acra", "hsa", "gebiz"],
  "sectorHints": ["healthcare", "procurement"],
  "format": "json"
}
```

3. If the user needs raw evidence, expose continuation tools:

```text
sg_acra_entities { "entityName": "DP Architects" }
sg_boa_architecture_firms { "firmName": "DP Architects" }
sg_gebiz_tenders { "supplierName": "DP Architects" }
```

## Product Shape

- Entity header: status, UEN, match confidence, and source freshness.
- Evidence tabs: ACRA, sector registry, procurement.
- Risk panel: `riskFlags[]`, `gaps[]`, and intentionally unsupported claims.

## Boundaries

This is public-data diligence, not legal, credit, compliance, tax, or investment advice. Keep unmatched modules visible instead of filling gaps with inference.
