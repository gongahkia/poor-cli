# API Authentication Guide

## SingStat
No authentication required. All endpoints are publicly accessible.

## MAS (Monetary Authority of Singapore)
No authentication required. Subject to fair use rate limits.

## OneMap
**Registration required.** OneMap requires email + password authentication.

1. Register at [onemap.gov.sg](https://www.onemap.gov.sg)
2. Configure credentials:
   ```
   sg_key_set { "apiName": "onemap_email", "key": "your@email.com" }
   sg_key_set { "apiName": "onemap_password", "key": "your-password" }
   ```
   Or via env vars: `SG_API_ONEMAP_EMAIL`, `SG_API_ONEMAP_PASSWORD`

**Troubleshooting:**
- `401 Unauthorized` → Credentials incorrect or expired. Re-register.
- `Token expired` → Token auto-refreshes. If persistent, delete and re-set credentials.

## URA (Urban Redevelopment Authority)
**API key required.**

1. Register at [ura.gov.sg/maps](https://www.ura.gov.sg/maps)
2. Apply for API access key
3. Configure: `sg_key_set { "apiName": "ura", "key": "your-api-key" }`
   Or: `SG_API_URA_KEY=your-api-key`

**Troubleshooting:**
- `Missing API key` → Key not configured. Run `sg_key_set`.
- `Invalid token` → Daily token refresh failed. Check API key validity.
- `Rate limited` → URA has strict limits. Wait and retry.

## data.gov.sg
No authentication required for basic access. Optional API key available for higher rate limits.
