# Swee Source Family Live Benchmark

Generated: 2026-05-23T01:30:12.608Z

## Source Checks

| Family | Source tool | Source | State | Records | Freshness | Audit | Gaps |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| weather | sg_nea_forecast_2hr | NEA | stale | 47 | stale | n/a | none |
| weather | sg_nea_air_quality | NEA | ready | 5 | fresh | n/a | none |
| weather | sg_nea_rainfall | NEA | ready | 76 | fresh | n/a | none |
| geospatial | sg_onemap_geocode | OneMap | credential_missing | 0 | unknown | cc1e9ea3-f5a6-430b-8f5b-d63cf8670885 | AUTH_MISSING |
| dataset-discovery | sg_datagov_search | data.gov.sg | error | 0 | unknown | n/a | TOOL_CALL_FAILED |
| statistics-discovery | sg_singstat_search | SingStat | ready | 5 | unknown | 90b689c4-bdb9-4f50-be26-6f84bf1ef7c2 | none |

## Pulse Weather

Pulse audit: 87903e5c-acea-429b-a104-50e611843d39

Signals: 17

Gaps: 0

## Limits

- This artifact is live local evidence, not an SLA or official public-agency service status.
- A ready source check means the adapter returned a bounded response during this run; it does not certify upstream completeness.
- Missing upstream timestamps, empty results, and source gaps are reported directly instead of being filled with synthetic freshness.
- Direct discovery probes use stable sample queries: OneMap 'Raffles Place', data.gov.sg 'weather', and SingStat 'population'.
