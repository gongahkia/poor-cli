# Swee Source Family Live Benchmark

Generated: 2026-05-23T01:54:23.497Z

## Source Checks

| Family | Source tool | Source | State | Records | Freshness | Audit | Gaps |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| weather | sg_nea_forecast_2hr | NEA | ready | 47 | fresh | n/a | none |
| weather | sg_nea_air_quality | NEA | ready | 5 | fresh | n/a | none |
| weather | sg_nea_rainfall | NEA | ready | 76 | fresh | n/a | none |
| geospatial | sg_onemap_geocode | OneMap | credential_missing | 0 | unknown | af308039-2c35-40cc-b042-f8da3142bf6b | AUTH_MISSING |
| dataset-discovery | sg_datagov_search | data.gov.sg | ready | 4 | unknown | ef3f8eb9-a298-4fd3-934b-31b883171f01 | none |
| statistics-discovery | sg_singstat_search | SingStat | ready | 5 | unknown | 4a6d04c4-fea7-4fec-9a2c-55c76faab1f4 | none |
| hawker-operations | sg_hawker_closures | NEA via data.gov.sg | ready | 25 | unknown | e348a56a-37fb-4d6b-8cc4-9f10b8bb180f | none |
| public-amenities | sg_nlb_libraries | NLB via data.gov.sg | ready | 5 | unknown | 0d1bd766-9c03-4496-9006-e1331ff4732a | none |
| public-facilities | sg_sportsg_facilities | SportSG via data.gov.sg | ready | 5 | unknown | cc7d1128-6d71-4130-9eb8-c743f5d40b22 | none |
| parks | sg_nparks_parks | NParks via data.gov.sg | ready | 5 | unknown | ebed1b66-bd8f-4648-8f45-5410a64e412a | none |
| water-levels | sg_pub_water_levels | PUB via data.gov.sg | gap | 0 | unknown | 2cc7c555-bfaf-4e8f-b93d-a2f3063c7ed1 | UNSUPPORTED_SOURCE_FORMAT |
| community-amenities | sg_pa_community_outlets | People's Association via data.gov.sg | ready | 5 | unknown | 5c58374c-822f-4cd9-b9fa-f50f5a95654e | none |

## Pulse Weather

Pulse audit: 5d5dd9ca-72a9-4574-960a-b8844e1b97a6

Signals: 17

Gaps: 0

## Limits

- This artifact is live local evidence, not an SLA or official public-agency service status.
- A ready source check means the adapter returned a bounded response during this run; it does not certify upstream completeness.
- Missing upstream timestamps, empty results, and source gaps are reported directly instead of being filled with synthetic freshness.
- Direct discovery probes use stable sample queries: OneMap 'Raffles Place', data.gov.sg 'weather', SingStat 'population', plus bounded directory probes for hawker closures, libraries, sports facilities, parks, water levels, and community outlets.
- OneMap geocoding is expected to show credential_missing until SG_API_ONEMAP_EMAIL and SG_API_ONEMAP_PASSWORD, or the onemap_email/onemap_password keystore keys, are configured.
