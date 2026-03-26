# API Authentication Guide

This repo has 3 authenticated upstreams:

- OneMap
- URA
- LTA DataMall

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

The local keystore is convenient for local development only. It is not a secret-management system.

## Public APIs

These tool families do not require credentials:

- SingStat
- MAS
- NEA
- HDB
- CEA
- BCA
- ACRA
- GeBIZ
- Hawker Centres
- MOE Schools
- MOH Healthcare
- SFA
- NParks
- PUB
- MOM
- STB
- data.gov.sg

HDB, CEA, BCA, ACRA, GeBIZ, Hawker Centres, MOE Schools, MOH Healthcare, SFA, NParks, PUB, MOM, and STB are intentionally covered through the shared data.gov.sg path.

## OneMap

Registration is required at [onemap.gov.sg](https://www.onemap.gov.sg/).

Expected keys:

- `onemap_email`
- `onemap_password`

Operational notes:

- live OneMap requests require valid credentials
- there is no silent unauthenticated fallback outside mock mode
- `sg_health_check` reports OneMap as `configured: true` only when both email and password are present

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

Common failure modes:

- missing key: set `SG_API_LTA_KEY` or `sg_key_set { "apiName": "lta", ... }`
- upstream key rejection: confirm the key is active and not scoped to a different account or environment
- bus-arrival gaps: a valid key can still return empty arrival coverage if the bus stop code or service number is wrong
- train-alert or traffic gaps inside `sg_transport_brief`: treat those as partial upstream coverage unless `sg_health_check` also shows LTA as unreachable or unconfigured

## Workflow Auth Map

| Workflow | Sources | Required auth |
| --- | --- | --- |
| Business Registry Diligence | ACRA, BCA, CEA | None |
| Property And Regulatory Due Diligence | OneMap, URA, HDB, optional NEA, optional LTA | OneMap and URA for full live coverage, LTA only if live transport context is enabled |
| Macro Snapshot | MAS, SingStat | None |
| Transport Status | LTA DataMall | LTA key |
| Environment Snapshot | NEA | None |

## Health Coverage Note

`sg_health_check` probes SingStat, MAS, OneMap, URA, LTA DataMall, data.gov.sg, and NEA directly. HDB, CEA, BCA, and ACRA are intentionally covered through the shared data.gov.sg path rather than separate upstream probes.

