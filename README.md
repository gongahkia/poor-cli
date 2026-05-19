# Dude

Dude is a Singapore counterparty due diligence app.

Search a Singapore company or UEN. Get a cited CDD report for analyst review. Open the evidence behind each claim when needed. Export a controlled PDF or DOCX report with provenance, freshness, gaps, limits, citations, and manifest data.

## Product Focus

Dude is no longer a broad Singapore public-data explorer. The retained product job is:

1. Search a company name, UEN, or sector-specific registry identifier.
2. Generate a CDD dossier and cited AI summary.
3. Inspect supporting evidence through citations and the Evidence Pack.
4. Capture next actions, confidence blockers, PDPA checklist prompts, and audit handoff.
5. Export a section-controlled CDD report.

Removed from the product/runtime surface: housing, property, macro, transport, transit ops, weather, civic amenities, generic data.gov drilldowns, visualization, law search, COE, IRAS, SPF, EMA, NLB, and related broad examples.

## Retained Tools

Current runtime surface: 26 `sg_*` tools total across 11 CDD catalog families. `sg_query` is the bounded preferred interface across 2 sg_query-routed CDD families.

CDD tools:

- `sg_query` for business/sector diligence prompts only
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

## Web App

The web app is report-first:

- Home page: one company/UEN search bar.
- Counterparty page: identity, risk/confidence summary, cited findings, next actions, and confidence blockers.
- Citations: click to open the supporting evidence.
- Evidence Pack: raw registry records, provenance, freshness, gaps, limits, supplemental web/person evidence, PDPA checklist, and audit handoff.
- Report Builder: include/exclude sections, reorder sections, choose a controlled writing style, then export PDF or DOCX.
- Workspace: saved dossiers, watchlists, bulk runs, and audit logs remain subordinate CDD workflow tools.

Controlled report styles:

- `concise_analyst`
- `audit_ready_formal`
- `client_friendly_neutral`
- `internal_escalation`

PDF and DOCX are the primary report outputs. JSON and CSV are advanced data exports.

## CDD Workflows

- Company CDD Report
- Architecture Firm Diligence
- Healthcare Supplier Diligence
- Hotel Operator Lookup

## CDD Catalog Families

- CDD Query
- Business Dossier
- ACRA
- BCA
- BOA
- CEA
- GeBIZ
- HSA
- HLB
- External Diligence
- Operations

## Start Here For Builders

- TypeScript integration: `examples/integration/basic-client.ts`
- Python integration: `examples/integration/basic-client.py`
- Runtime profile smoke: `npm run test:smoke:profiles`

## Development

```bash
npm install
npm run build
npm run test
npm run verify
npm run dev
```

Run the web app only:

```bash
npm run dev -w apps/web
```

Run the MCP gateway only:

```bash
npm run dev:gateway
```

## Runtime Discovery

The runtime still exposes catalog resources, now scoped to CDD:

- `sg://apis`
- `sg://tools`
- `sg://workflows`
- `sg://recipes`
- `sg://runtime`
- `sg://playbooks`
- `sg://benchmarks`

`sg_query` rejects non-CDD prompts instead of routing them into removed public-data workflows.

## Safety Boundaries

Dude is an analyst-review system, not an automated compliance decision engine.

- Do not claim a counterparty is cleared, sanctioned-free, PDPA-compliant, financially sound, or legally safe.
- Treat missing public records as a coverage gap, not proof of absence.
- Keep supplemental web presence, people discovery, adverse media, OpenCorporates, sanctions, and relationship graph signals clearly labeled as analyst-review evidence.
- Preserve source attribution, observed freshness, gaps, limits, and report manifest data in exports.

## Key Docs

- [Architecture](./docs/architecture.md)
- [Agent builder quickstart](./docs/agent-builder-quickstart.md)
- [Product health](./docs/product-health.md)
- [CDD product notes](./docs/product/corp-services-cdd.md)
- [Secondary workflows](./docs/product/secondary-workflows.md)
- [PDPA vendor checklist](./docs/pdpa-vendor-diligence-checklist.md)
- [Public data limits](./docs/public-data-limits.md)
