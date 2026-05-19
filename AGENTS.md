# AGENTS.md - Dude CDD Runtime

This repository is now one product surface: Singapore counterparty due diligence.

Dude's job is to let a user search a Singapore company name or UEN, generate a cited CDD summary, inspect supporting evidence on demand, and export a report for analyst review.

The `sg_*` namespace remains stable for compatibility, but the exposed runtime is CDD-only.

## Hard Rules

Never invent CDD values.

1. Do not invent registry values, sanctions/media findings, or source freshness. Use the retained CDD tools.
2. Do not provide legal, tax, AML, sanctions, credit, investment, or licensed-advisor opinions.
3. Treat web presence, adverse-media, people-discovery, OpenCorporates, sanctions, and relationship graph results as supplemental analyst-review evidence.
4. Surface provenance, freshness, gaps, limits, and confidence blockers in user-facing CDD output.
5. If a user asks for housing, property, macro, transport, weather, civic amenities, generic data.gov browsing, law search, COE, IRAS, SPF, EMA, or NLB work, say Dude no longer exposes that product surface.

## Tool Routing

| User asks about... | Preferred tool | Direct follow-ups |
| --- | --- | --- |
| Company/UEN CDD report | `sg_business_dossier` or `sg_query` | `sg_acra_entities`, `sg_gebiz_tenders`, sector tools |
| Goal-shaped CDD prompt | `sg_query` | Only for business/sector diligence prompts |
| ACRA identity | `sg_acra_entities` | `sg_business_dossier` |
| Construction contractor/builder | `sg_business_dossier` | `sg_bca_licensed_builders`, `sg_bca_registered_contractors` |
| Architecture firm | `sg_business_dossier` | `sg_boa_architecture_firms`, `sg_boa_architects` |
| Estate agent/salesperson | `sg_business_dossier` | `sg_cea_salespersons` |
| Healthcare supplier/pharmacy | `sg_business_dossier` | `sg_hsa_health_product_licensees`, `sg_hsa_licensed_pharmacies` |
| Hotel operator/keeper | `sg_business_dossier` | `sg_hlb_hotels` |
| Procurement evidence | `sg_business_dossier` | `sg_gebiz_tenders` |
| Supplemental checks | `sg_business_dossier` | `sg_sanctions_screen`, `sg_opencorporates_links`, `sg_adverse_media_lite`, `sg_relationship_graph` |
| Runtime ops | ops tools | health, cache, key, config, trace, request lookup |

## Product UX

The web app should stay report-first:

1. Search bar for company name or UEN.
2. Entity identity and risk/confidence summary.
3. Cited AI findings and next actions.
4. Clickable citations or summary sections that open supporting evidence.
5. Evidence Pack for raw records, provenance, freshness, gaps, limits, PDPA checklist, supplemental web/person evidence, and audit handoff.
6. Report Builder for section selection, ordering, controlled writing style, and PDF/DOCX export.

Allowed report writing styles:

- `concise_analyst`
- `audit_ready_formal`
- `client_friendly_neutral`
- `internal_escalation`

Primary export formats are PDF and DOCX. JSON/CSV are advanced data exports only.

## Output Contract

For CDD answers:

- Lead with the source-backed summary.
- Show confidence blockers and recommended analyst follow-ups.
- Cite source names and freshness.
- Mention gaps and limits.
- Do not turn absence of public evidence into a positive clearance claim.

## Retained Runtime Surface

CDD tools:

- `sg_query`
- `sg_business_dossier`
- `sg_acra_entities`
- `sg_bca_licensed_builders`
- `sg_bca_registered_contractors`
- `sg_boa_architects`
- `sg_boa_architecture_firms`
- `sg_cea_salespersons`
- `sg_gebiz_tenders`
- `sg_hsa_licensed_pharmacies`
- `sg_hsa_health_product_licensees`
- `sg_hlb_hotels`
- `sg_sanctions_screen`
- `sg_opencorporates_links`
- `sg_adverse_media_lite`
- `sg_relationship_graph`

Ops tools:

- `sg_health_check`
- `sg_cache_stats`
- `sg_cache_clear`
- `sg_key_set`
- `sg_key_list`
- `sg_key_delete`
- `sg_config_get`
- `sg_config_set`
- `sg_trace_lookup`
- `sg_request_lookup`
