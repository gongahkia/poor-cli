# API Authentication Guide

This repo has 3 authenticated upstreams:

- OneMap requires an email and password
- URA requires an API key
- LTA DataMall requires an API key

The recommended precedence is:

1. environment variables for production and CI
2. the local keystore helpers for development fallback

## Environment Variables

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

The local keystore is convenient for local development only. It is not an encrypted secret-management system.

## Public APIs

These tool families do not require credentials:

- SingStat
- MAS
- NEA
- HDB
- CEA
- BCA
- ACRA
- data.gov.sg

HDB, CEA, BCA, and ACRA are curated tools over official data.gov.sg datasets, so they intentionally do not introduce separate credential flows.

## OneMap

Registration is required at [onemap.gov.sg](https://www.onemap.gov.sg/).

Expected keys:

- `onemap_email`
- `onemap_password`

Health-check behavior:

- `sg_health_check` reports OneMap as `configured: true` only when both email and password are present
- reachability is reported separately from credential presence

Common failures:

- `401 Unauthorized`: the email or password is wrong
- token-related failures: OneMap token issuance or refresh failed upstream

## URA

Registration is required at [ura.gov.sg/maps](https://www.ura.gov.sg/maps/).

Expected key:

- `ura`

Health-check behavior:

- `sg_health_check` reports URA as `configured: true` only when the URA key is present
- reachability is reported separately from credential presence

Common failures:

- missing key: configure `SG_API_URA_KEY` or `sg_key_set`
- invalid token: URA token refresh failed because the upstream key is invalid
- rate limiting: URA is one of the tightest upstreams in this repo, so retry later

## LTA DataMall

Registration is required at [mytransport.sg](https://datamall.lta.gov.sg/).

Expected key:

- `lta`

Health-check behavior:

- `sg_health_check` reports LTA DataMall as `configured: true` only when the LTA key is present
- reachability is reported separately from credential presence

Common failures:

- missing key: configure `SG_API_LTA_KEY` or `sg_key_set`
- `401 Unauthorized`: the key is missing, expired, or invalid
- rate limiting: LTA traffic and arrival data are operational feeds, so retry later instead of fan-out retries

## Health Coverage Note

`sg_health_check` probes SingStat, MAS, OneMap, URA, LTA DataMall, data.gov.sg, and NEA directly. HDB, CEA, BCA, and ACRA are intentionally covered through the shared data.gov.sg path rather than separate upstream probes.
