# Swee Source Family Live Benchmark

Generated: 2026-05-23T02:42:52.550Z

## Source Checks

| Family | Source tool | Source | State | Records | Freshness | Audit | Gaps |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| weather | sg_nea_forecast_2hr | NEA | ready | 47 | fresh | n/a | none |
| weather | sg_nea_air_quality | NEA | ready | 5 | fresh | n/a | none |
| weather | sg_nea_rainfall | NEA | ready | 76 | fresh | n/a | none |
| geospatial | sg_onemap_geocode | OneMap | credential_missing | 0 | unknown | 07d5e54b-55f7-4162-bee8-de64fdd908ea | AUTH_MISSING |
| dataset-discovery | sg_datagov_search | data.gov.sg | ready | 4 | unknown | a4442bed-dd82-4b53-9f71-99782dcaf78a | none |
| statistics-discovery | sg_singstat_search | SingStat | ready | 5 | unknown | 3f71da2e-56d6-43ad-a581-935aa1044990 | none |
| hawker-operations | sg_hawker_closures | NEA via data.gov.sg | ready | 25 | unknown | f3c6a908-240b-4086-a798-dde549d9333d | none |
| public-amenities | sg_nlb_libraries | NLB via data.gov.sg | ready | 5 | unknown | 6e972e01-33fe-4c6e-aa02-49efb847aa95 | none |
| public-facilities | sg_sportsg_facilities | SportSG via data.gov.sg | ready | 5 | unknown | 5d95ec31-b5cf-491c-ba0c-224215c289b8 | none |
| parks | sg_nparks_parks | NParks via data.gov.sg | ready | 5 | unknown | 6273d8b1-b8ac-4a5f-a7d1-bb137059a39f | none |
| water-levels | sg_pub_water_levels | PUB via data.gov.sg | ready | 5 | unknown | 218f3e3c-a50e-4ac4-9e3b-c977031c2b85 | none |
| community-amenities | sg_pa_community_outlets | People's Association via data.gov.sg | ready | 5 | unknown | 706874e6-6e36-486a-b29c-385762f3026f | none |
| education | sg_moe_schools | MOE via data.gov.sg | ready | 5 | unknown | fffcfbb1-08a0-4020-8367-28e5c9323da2 | none |
| childcare | sg_ecda_childcare_centres | ECDA via data.gov.sg | ready | 5 | unknown | 5b8ee954-7a83-47dd-baf1-89ae28ec39dc | none |
| social-support | sg_msf_family_services | MSF via data.gov.sg | ready | 5 | unknown | d09b041a-ec06-4506-b314-e47dfce11972 | none |
| student-care | sg_msf_student_care_services | MSF via data.gov.sg | ready | 5 | unknown | d5797968-a33f-4e8f-ac69-8e1d263385ae | none |
| social-support | sg_msf_social_service_offices | MSF via data.gov.sg | ready | 5 | unknown | 2c34f6a6-db2b-43a5-af7d-ec25997b49bd | none |
| health-facilities | sg_moh_facilities | MOH via data.gov.sg | ready | 5 | unknown | 56e2621d-b9ed-4c0b-bbb5-925e3611f1cc | none |

## Pulse Weather

Pulse audit: d66f15f8-138f-4b75-818a-6b0a26c4254a

Signals: 20

Gaps: 0

## Limits

- This artifact is live local evidence, not an SLA or official public-agency service status.
- A ready source check means the adapter returned a bounded response during this run; it does not certify upstream completeness.
- Missing upstream timestamps, empty results, and source gaps are reported directly instead of being filled with synthetic freshness.
- Direct discovery probes use stable sample queries: OneMap 'Raffles Place', data.gov.sg 'weather', SingStat 'population', plus bounded directory probes for hawker closures, libraries, sports facilities, parks, water levels, community outlets, education, childcare, social-support, and health-facility directories.
- OneMap geocoding is expected to show credential_missing until SG_API_ONEMAP_EMAIL and SG_API_ONEMAP_PASSWORD, or the onemap_email/onemap_password keystore keys, are configured.
- MOH, MSF, and ECDA probes are directory/source coverage only and must not be read as medical, social-work, safety, or eligibility advice.
