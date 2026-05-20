# Secondary Workflows

Corp-services CDD onboarding remains the first-run product workflow. Vendor onboarding and procurement intelligence are adjacent lanes because they reuse the same public-data discipline, but they should not dilute the primary client-file path or create unsupported risk scoring.

## Lane 1: Vendor Onboarding

Vendor onboarding helps an operations, finance, or DPO team decide what public evidence needs analyst review before a supplier is added to an approved-vendor file.

### Workflow

1. Capture the vendor company name or UEN and intended service category.
2. Resolve the entity through ACRA before running any sector module.
3. Run sector modules only when justified by the service category or official registry evidence.
4. Produce a vendor review packet with evidence, freshness, gaps, limits, and next checks.
5. Attach the packet to the procurement or vendor-management record, or save it to the workspace dossier folder when that workflow is enabled.

### Required Tools And Data Sources

| Need | Current surface |
| --- | --- |
| Corporate identity | CDD orchestrator with `sg_acra_entities` source evidence |
| Public procurement history | `sg_gebiz_tenders` |
| Contractor or builder licensing | `sg_bca_*` tools |
| Architect or architecture-firm registration | `sg_boa_*` tools |
| Real-estate salesperson or agency evidence | `sg_cea_salespersons` |
| Healthcare, pharmacy, import, wholesale, or manufacturing licences | `sg_hsa_*` tools |
| PDPA vendor checklist | Public-data vendor checklist and report template in [pdpa-vendor-diligence-checklist.md](../pdpa-vendor-diligence-checklist.md) |
| Adverse-media lite | `sg_adverse_media_lite` bounded to official public feeds |
| Watchlists and change alerts | Workspace watchlists and manual alert checks documented in [watchlist-alerts.md](../watchlist-alerts.md) |

### Non-Goals

- Do not produce a pass/fail vendor approval.
- Do not infer directors, shareholders, beneficial owners, related parties, or control relationships from missing public data.
- Do not claim a vendor is PDPA-compliant, sanctioned-free, financially sound, or conflict-free.
- Do not replace internal procurement policy, DPO review, legal review, or licensed advisory checks.

## Lane 2: Procurement Intelligence

Procurement intelligence helps a team monitor public tender and award signals around counterparties, sectors, and public buyers. It is an evidence-discovery lane, not a bidding strategy engine.

### Workflow

1. Define a bounded procurement question, such as a UEN, entity name, buyer agency, tender category, or award period.
2. Search GeBIZ and relevant official public feeds.
3. Normalize matches into records with source URL, publication date, award value where available, and freshness.
4. Mark unmatched or ambiguous entity names as review gaps.
5. Export or hand off records to the team's CRM, procurement tracker, or workspace dossier folder.

### Required Tools And Data Sources

| Need | Current surface |
| --- | --- |
| Tender and award discovery | `sg_gebiz_tenders` |
| Entity identity checks | CDD orchestrator with ACRA source evidence |
| Sector classification | SSIC evidence from ACRA-backed records plus analyst-selected sector hints |
| Bulk monitoring | Workspace-backed 200-row bulk flow with partial-failure and retry metadata |
| Shallow relationship graph | `sg_relationship_graph` for supplied dossier records without ownership or control claims |
| Public benchmark data | 50-case diligence benchmark set documented in [diligence-benchmarks.md](../diligence-benchmarks.md) |

### Non-Goals

- Do not recommend whether to bid, price, or partner.
- Do not predict tender outcomes or buyer intent.
- Do not imply procurement relationships where only name similarity exists.
- Do not scrape paid, private, or restricted procurement systems.

## Roadmap Links

These lanes should stay downstream of the CDD and workspace foundation work:

- Primary CDD workflow: [docs/product/corp-services-cdd.md](./corp-services-cdd.md)
- Workspace accounts and RBAC: [#43](https://github.com/gongahkia/dude/issues/43)
- Persisted dossier folders: [#45](https://github.com/gongahkia/dude/issues/45)
- Signed export manifests: [#46](https://github.com/gongahkia/dude/issues/46)
- Audit log: [#47](https://github.com/gongahkia/dude/issues/47)
- Watchlists and alert rules: [#48](https://github.com/gongahkia/dude/issues/48)
- Bulk diligence workflows: [#49](https://github.com/gongahkia/dude/issues/49)
- PDPA vendor checklist/report: [#56](https://github.com/gongahkia/dude/issues/56)

Any new feature in either lane must preserve evidence, records, gaps, provenance, freshness, and limits, and must add source-licensing notes before shipping.
