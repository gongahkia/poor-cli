---
name: sg-apis-mcp
description: Official Singapore public data for agent builders through deterministic MCP tools and bounded workflow planning
version: 0.1.0
mcp_server: sg-apis-mcp
---

# sg-apis-mcp Skill

Use this skill when an agent needs official Singapore public data through MCP with explicit contracts.

## Surface Snapshot

The repo currently exposes 63 `sg_*` tools total across 26 official data families.

- 49 direct data tools
- 5 additive brief tools: `sg_business_dossier`, `sg_property_brief`, `sg_macro_brief`, `sg_transport_brief`, `sg_environment_brief`
- 8 operational helpers
- 1 bounded preferred interface, `sg_query`

`sg_query` is the bounded preferred interface across 17 routed families. The direct `sg_*` tools remain the stable low-level contract.

## Positioning

- Best for agent builders who need deterministic Singapore public-data calls
- Optimized for bounded workflows, not free-form analyst chat
- Current depth spans SingStat, MAS, OneMap, URA, LTA DataMall, NEA, HDB, CEA, BCA, ACRA, PA, Sport Singapore, ECDA, MSF Family Services, MSF Student Care Services, MSF Social Service Offices, GeBIZ, Hawker Centres, MOE Schools, MOH Healthcare, SFA, NParks, PUB, MOM, STB, and data.gov.sg
- The core differentiator is explicit contracts plus additive briefs, not hidden orchestration

## Discovery Resources

- `sg://apis`
- `sg://tools`
- `sg://workflows`
- `sg://recipes`

Use `sg://recipes` first when the caller has a goal-shaped prompt and you need the fastest honest entrypoint.

## Preferred Entry Points

- `sg_business_dossier`
  Cross-registry business diligence across ACRA, BCA, and CEA.
- `sg_property_brief`
  Location and property brief across OneMap, URA, HDB, and optional live context.
- `sg_macro_brief`
  Compact Singapore macro starter brief using MAS values and SingStat entrypoints.
- `sg_transport_brief`
  Live transport operations brief over LTA bus arrivals, train alerts, and traffic incidents.
- `sg_environment_brief`
  Live environment brief over NEA forecast, air quality, and rainfall signals.
- `sg_query`
  Preferred bounded workflow planner and executor for covered families.

## Direct Tools Vs `sg_query`

- Use `sg_query` when the user starts from a prompt such as route planning, reverse geocoding, SingStat browsing, data.gov collection browsing, or URA development-charge lookup.
- Use direct `sg_*` tools when your application already has the exact coordinates, table IDs, dataset IDs, UENs, towns, or flat types.
- Treat blocked and unsupported `sg_query` responses as useful contract outcomes, not something to hide.

## Stable Scope

### SingStat

- `sg_singstat_search`
- `sg_singstat_table`
- `sg_singstat_timeseries`
- `sg_singstat_compare`
- `sg_singstat_browse`

### MAS

- `sg_mas_exchange_rates`
  Latest, exact-date, or bounded date-range FX reads.
- `sg_mas_interest_rates`
  SORA only, with latest, exact-date, or bounded date-range reads.
- `sg_mas_financial_stats`
  Banking only, with latest, exact-date, or bounded date-range reads.

### OneMap

- `sg_onemap_geocode`
- `sg_onemap_reverse_geocode`
- `sg_onemap_route`
- `sg_onemap_population`
- `sg_onemap_convert_coords`

Live OneMap calls require valid credentials. There is no silent unauthenticated fallback outside mock mode.

### URA

- `sg_ura_property_transactions`
- `sg_ura_planning_area`
- `sg_ura_dev_charges`

### LTA DataMall

- `sg_lta_bus_arrivals`
- `sg_lta_train_alerts`
- `sg_lta_traffic_incidents`

### NEA

- `sg_nea_forecast_2hr`
- `sg_nea_air_quality`
- `sg_nea_rainfall`

### HDB

- `sg_hdb_resale_prices`
- `sg_hdb_rental_prices`

### CEA

- `sg_cea_salespersons`

### BCA

- `sg_bca_licensed_builders`
- `sg_bca_registered_contractors`

### ACRA

- `sg_acra_entities`

### PA

- `sg_pa_community_outlets`
- `sg_pa_resident_network_centres`

### Sport Singapore

- `sg_sportsg_facilities`

### ECDA

- `sg_ecda_childcare_centres`

### MSF Family Services

- `sg_msf_family_services`

### MSF Student Care Services

- `sg_msf_student_care_services`

### MSF Social Service Offices

- `sg_msf_social_service_offices`

### data.gov.sg

- `sg_datagov_search`
- `sg_datagov_get`
- `sg_datagov_resources`
- `sg_datagov_rows`
- `sg_datagov_browse`

`sg_datagov_get` is metadata only. Use `sg_datagov_resources` to inspect the current machine-readable resource shape, then `sg_datagov_rows` for bounded datastore reads.

## Brief Contract

All additive brief tools return:

- `title`
- `summary`
- `evidence`
- `records`
- `gaps`
- `provenance`
- `freshness`
- `limits`

## Workflow Recipes

### Macro Snapshot

```text
sg_query { "query": "Macro snapshot of Singapore", "mode": "execute" }
sg_macro_brief { "currency": "USD", "format": "json" }
sg_mas_exchange_rates { "currency": "USD", "startDate": "2026-03-01", "endDate": "2026-03-26", "format": "json" }
sg_singstat_search { "keyword": "Singapore GDP", "format": "json" }
```

### Property And Regulatory Due Diligence

```text
sg_query { "query": "Property due diligence for Bedok HDB resale", "mode": "execute" }
sg_property_brief { "planningArea": "Bedok", "flatType": "4 ROOM", "includeEnvironment": true, "includeTransport": true, "format": "json" }
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok", "format": "json" }
sg_hdb_resale_prices { "town": "Bedok", "flatType": "4 ROOM", "format": "json" }
```

### Property Counterparty Diligence

```text
sg_ura_property_transactions { "propertyType": "residential", "area": "Bedok", "format": "json" }
sg_hdb_resale_prices { "town": "Bedok", "flatType": "4 ROOM", "format": "json" }
sg_cea_salespersons { "estateAgentName": "ERA REALTY NETWORK PTE LTD", "format": "json" }
sg_acra_entities { "entityName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
```

### Business Registry Diligence

```text
sg_query { "query": "Registry diligence for UEN 201912345K", "mode": "execute" }
sg_business_dossier { "uen": "201912345K", "format": "json" }
sg_acra_entities { "uen": "201912345K", "format": "json" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_cea_salespersons { "registrationNo": "R123456A", "format": "json" }
```

### Transport Status

```text
sg_query { "query": "Transport status in Singapore right now", "mode": "execute" }
sg_transport_brief { "busStopCode": "83139", "serviceNo": "851", "format": "json" }
sg_lta_bus_arrivals { "busStopCode": "83139", "serviceNo": "851", "format": "json" }
sg_lta_train_alerts { "format": "json" }
sg_lta_traffic_incidents { "format": "json" }
```

### Environment Snapshot

```text
sg_query { "query": "Environment snapshot of Singapore right now", "mode": "execute" }
sg_environment_brief { "area": "Tampines", "region": "East", "stationId": "S107", "format": "json" }
sg_nea_forecast_2hr { "area": "Tampines", "format": "json" }
sg_nea_air_quality { "region": "East", "format": "json" }
sg_nea_rainfall { "stationId": "S107", "format": "json" }
```

### Civic Discovery

```text
sg_query { "query": "Find a family service centre near 560230", "mode": "execute" }
sg_msf_family_services { "postalCode": "560230", "format": "json" }
sg_msf_student_care_services { "postalCode": "750471", "scfaOnly": true, "format": "json" }
sg_msf_social_service_offices { "name": "Social Service Office @ Queenstown", "format": "json" }
sg_pa_community_outlets { "type": "community_club", "postalCode": "560123", "format": "json" }
sg_ecda_childcare_centres { "postalCode": "560123", "hasVacancy": true, "format": "json" }
```

### Dataset Discovery Fallback

```text
sg_query { "query": "Find datasets about hawker centres", "mode": "execute" }
sg_datagov_search { "keyword": "hawker centres" }
sg_datagov_resources { "datasetId": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc" }
sg_datagov_rows { "datasetId": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc", "limit": 5, "sort": "month desc" }
```

### Route Planning

```text
sg_query { "query": "Walk from 049178 to 048616", "mode": "execute" }
sg_onemap_route { "startLat": 1.2864, "startLng": 103.8537, "endLat": 1.284, "endLng": 103.851, "routeType": "walk" }
sg_onemap_reverse_geocode { "lat": 1.284, "lng": 103.851 }
```

### SingStat Table Drilldown

```text
sg_query { "query": "Browse SingStat transport datasets", "mode": "execute" }
sg_singstat_browse { "category": "Transport" }
sg_singstat_table { "tableId": "M650151" }
sg_singstat_timeseries { "tableId": "M650151", "indicator": "Vehicle population", "startYear": 2022, "endYear": 2025 }
```

### Dataset Collection Browse

```text
sg_query { "query": "Browse data.gov collections", "mode": "execute" }
sg_datagov_browse {}
sg_datagov_search { "keyword": "hawker centres" }
sg_datagov_resources { "datasetId": "d_8b84c4ee58e3cfc0ece0d773c8ca6abc" }
```

## Authentication

Authenticated upstreams:

- OneMap
- URA
- LTA DataMall

Recommended production path:

- `SG_API_ONEMAP_EMAIL`
- `SG_API_ONEMAP_PASSWORD`
- `SG_API_URA_KEY`
- `SG_API_LTA_KEY`

Public families:

- SingStat
- MAS
- NEA
- HDB
- CEA
- BCA
- ACRA
- PA
- Sport Singapore
- ECDA
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

HDB, CEA, BCA, and ACRA are intentionally covered through the shared data.gov.sg path.

## Examples

The workflow demos live in:

- `examples/business-dossier.md`
- `examples/property-brief.md`
- `examples/macro-brief.md`
- `examples/transport-brief.md`
- `examples/environment-brief.md`
- `examples/civic-discovery.md`
- `examples/geospatial-routing.md`
