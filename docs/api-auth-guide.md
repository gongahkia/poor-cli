# API Authentication Guide

This repo has 4 authenticated upstreams:

- OneMap
- URA
- LTA DataMall
- Transit Intelligence

The recommended precedence is:

1. environment variables for production and CI
2. the local keystore helpers for development fallback

## Environment Variables

Copy `.env.example` and fill only the credentials you need:

```bash
export SG_API_ONEMAP_EMAIL="you@example.com"
export SG_API_ONEMAP_PASSWORD="your-password"
export SG_API_URA_KEY="your-ura-api-key"
export SG_API_LTA_KEY="your-lta-api-key"
```

## Local MCP Keystore Fallback

```text
sg_key_set { "apiName": "onemap_email", "key": "you@example.com" }
sg_key_set { "apiName": "onemap_password", "key": "your-password" }
sg_key_set { "apiName": "ura", "key": "your-ura-api-key" }
sg_key_set { "apiName": "lta", "key": "your-lta-api-key" }
```

The local keystore is convenient for local development only. It is not a secret-management system. Keystore data is stored at `$SG_APIS_STATE_DIR/keys.db` (default `~/.sg-apis/keys.db`).

## Public APIs

These tool families do not require credentials:

- SingStat
- MAS
- NEA
- HDB
- CEA
- BCA
- BOA
- ACRA
- PA
- Sport Singapore
- ECDA
- MSF Family Services
- MSF Student Care Services
- MSF Social Service Offices
- GeBIZ
- Hawker Centres
- MOE Schools
- MOH Healthcare
- HSA
- SFA
- NParks
- PUB
- MOM
- STB
- HLB
- data.gov.sg

HDB, CEA, BCA, BOA, HSA, HLB, and ACRA are intentionally covered through the shared data.gov.sg path or official file-download path.
PA, Sport Singapore, ECDA, MSF Family Services, MSF Student Care Services, MSF Social Service Offices, GeBIZ, Hawker Centres, MOE Schools, MOH Healthcare, SFA, NParks, PUB, MOM, and STB use the same no-auth data.gov.sg access layer or official file-download path.

## OneMap

Registration is required at [onemap.gov.sg](https://www.onemap.gov.sg/).

Expected keys:

- `onemap_email`
- `onemap_password`

Operational notes:

- live OneMap requests require valid credentials
- there is no silent unauthenticated fallback
- `sg_health_check` reports OneMap as `configured: true` only when both email and password are present
- `sg_health_check` uses the same authenticated runtime path as the live OneMap tools

Common failure modes:

- missing email or password: set both `SG_API_ONEMAP_EMAIL` and `SG_API_ONEMAP_PASSWORD`, or the matching keystore keys
- upstream auth failure: verify the OneMap account credentials directly, then refresh the local values
- geocode returns no result: this is usually an input-resolution issue, not an auth issue; try a Singapore postal code or a more exact address
- route or reverse-geocode instability: retry once before assuming a bad credential, because OneMap availability and auth are surfaced separately in `sg_health_check`

## URA

Registration is required at [ura.gov.sg/maps](https://www.ura.gov.sg/maps/).

Expected key:

- `ura`

Operational notes:

- `sg_health_check` reports URA as `configured: true` only when the URA key is present
- live planning-area and transaction lookups should be treated as key-backed production paths
- `sg_health_check` uses the same authenticated runtime path as the live URA tools

Common failure modes:

- missing key: set `SG_API_URA_KEY` or `sg_key_set { "apiName": "ura", ... }`
- upstream key rejection: confirm that the URA key is active and copied without whitespace
- property brief gaps such as `URA_PLANNING_FAILED` or `URA_TRANSACTIONS_FAILED`: check the key first, then retry with a simpler planning area input like `Bedok`
- empty transaction responses: this can be a legitimate coverage outcome for the selected area or property type rather than an auth problem

## LTA DataMall

Registration is required at [datamall.lta.gov.sg](https://datamall.lta.gov.sg/).

Expected key:

- `lta`

Operational notes:

- `sg_health_check` reports LTA DataMall as `configured: true` only when the LTA key is present
- `sg_transport_brief` depends on the same live LTA credential surface used by the direct transport tools
- `sg_health_check` uses the same authenticated runtime path as the live LTA tools

Common failure modes:

- missing key: set `SG_API_LTA_KEY` or `sg_key_set { "apiName": "lta", ... }`
- upstream key rejection: confirm the key is active and not scoped to a different account or environment
- bus-arrival gaps: a valid key can still return empty arrival coverage if the bus stop code or service number is wrong
- train-alert or traffic gaps inside `sg_transport_brief`: treat those as partial upstream coverage unless `sg_health_check` also shows LTA as unreachable or unconfigured

## Transit Intelligence

Transit Intelligence uses the same LTA credential surface for live-dependent reads.

Expected key:

- `lta`

Operational notes:

- transit planning, reliability, transfer-risk, and ops decisions consume the same authenticated LTA runtime path
- policy-audit and replay tools can still run on historical traces without new upstream credentials
- `sg_health_check` relies on LTA DataMall checks as the shared live dependency signal

Common failure modes:

- missing key: set `SG_API_LTA_KEY` or `sg_key_set { "apiName": "lta", ... }`
- live-dependent transit outputs degrade to bounded gaps when LTA is unavailable or rate-limited
- policy replay works but cannot validate live plan deltas without current LTA feed health

## Workflow Auth Map

| Workflow | Sources | Required auth |
| --- | --- | --- |
| Business Registry Diligence | ACRA, BCA, CEA, optional BOA, HSA, HLB, GeBIZ | None |
| Architecture Firm Diligence | BOA, ACRA, optional GeBIZ | None |
| Healthcare Supplier Diligence | HSA, ACRA, optional GeBIZ | None |
| Hotel Operator Lookup | HLB, optional ACRA | None |
| Sector Scoped Business Diligence | ACRA plus explicit BOA, HSA, HLB, GeBIZ, BCA, or CEA modules | None |
| Property And Regulatory Due Diligence | OneMap, URA, HDB, optional NEA, optional LTA | OneMap and URA for full live coverage, LTA only if live transport context is enabled |
| Macro Snapshot | MAS, SingStat | None |
| Transport Status | LTA DataMall | LTA key |
| Environment Snapshot | NEA | None |

## Health Coverage Note

`sg_health_check` probes SingStat, MAS, OneMap, URA, LTA DataMall, data.gov.sg datastore, data.gov.sg file downloads, and NEA directly. OneMap, URA, and LTA are checked through the same authenticated runtime path used by the live tools. HDB, CEA, BCA, ACRA, GeBIZ, Hawker Centres, MOE Schools, MOH Healthcare, SFA, NParks, PUB, MOM, and STB are intentionally covered through the shared data.gov.sg datastore path. BOA, HSA, HLB, PA, Sport Singapore, ECDA, and the MSF civic directories are intentionally covered through the shared official file-download path.
