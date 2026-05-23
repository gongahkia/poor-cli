# Swee Credential Readiness Benchmark

Generated: 2026-05-23T02:38:50.983Z

| Tool | Source | Auth required | State | Records | Audit | Gaps |
| --- | --- | --- | --- | ---: | --- | --- |
| sg_onemap_geocode | OneMap | yes | credential_missing | 0 | 2fd31318-19c1-4a8c-acb6-59d006e4ca79 | AUTH_MISSING |
| sg_datagov_search | data.gov.sg | no | ready | 3 | 01553ad9-8124-41e1-8763-fe0d17b224b0 | none |

## Limits

- This artifact records local credential readiness only; credential_missing is an actionable setup state, not a runtime failure.
- OneMap may use SG_API_ONEMAP_EMAIL and SG_API_ONEMAP_PASSWORD or the onemap_email/onemap_password keystore keys.
- data.gov.sg discovery currently uses the public no-key path and remains subject to upstream public rate limits.
