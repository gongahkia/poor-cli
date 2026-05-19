# Agent Builder Quickstart

Dude MCP is now CDD-only.

Use it when your agent needs to search a Singapore company/UEN, generate a cited CDD dossier, inspect evidence, and export an analyst-review report.

## Start With Discovery

Read the CDD-scoped catalog resources at startup:

- `sg://apis`
- `sg://tools`
- `sg://workflows`
- `sg://recipes`
- `sg://runtime`
- `sg://playbooks`
- `sg://benchmarks`

`sg://recipes` is the best first resource for natural-language prompt routing.

## Use `sg_query` For Goal-Shaped CDD Prompts

Examples:

```text
sg_query { "query": "Business dossier for DP Architects", "mode": "execute" }
sg_query { "query": "Architecture firm diligence for DP Architects", "mode": "execute" }
sg_query { "query": "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "mode": "execute" }
sg_query { "query": "Hotel operator lookup for Marina Bay Sands", "mode": "execute" }
```

Non-CDD prompts return `unsupported`. Do not retry them against removed public-data tools.

## Use Direct Tools For Exact Inputs

```text
sg_business_dossier { "uen": "201912345K" }
sg_business_dossier { "entityName": "DP Architects", "modules": ["acra", "boa", "gebiz"], "sectorHints": ["architecture", "procurement"] }
sg_acra_entities { "entityName": "DP Architects" }
sg_boa_architecture_firms { "firmName": "DP Architects" }
sg_hsa_health_product_licensees { "companyName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD." }
sg_hlb_hotels { "name": "Marina Bay Sands" }
sg_gebiz_tenders { "supplierName": "ABC CONSTRUCTION PTE LTD" }
```

## Handle Outcomes

- `completed`: render the cited summary and evidence pack.
- `planned`: show the planned CDD steps or execute after user confirmation.
- `blocked`: ask for the missing company/UEN/registration identifier.
- `unsupported`: tell the caller Dude only supports CDD entity and sector diligence.
- `failed`: surface the failed step and suggested action.

## Evidence Rules

Your agent should preserve:

- citations
- provenance
- freshness
- gaps
- limits
- confidence blockers
- next actions

Do not infer that a company is safe, sanctioned-free, PDPA-compliant, or financially sound from missing public evidence.

## Local Verification

```bash
npm run build
npm run test
npm run verify
```

For web UX changes, also run:

```bash
npm run build -w apps/web
npm run test -w apps/web
```
