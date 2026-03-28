---
name: sg-apis-mcp
description: Official Singapore public data for agent builders through deterministic MCP tools and bounded workflow planning
version: 0.1.0
mcp_server: sg-apis-mcp
---

# sg-apis-mcp Skill

Use this skill when an agent needs official Singapore public data through MCP with explicit contracts.

## Surface Snapshot

The repo currently exposes 68 `sg_*` tools total across 29 official data families.

- 54 direct data tools
- 5 additive brief tools: `sg_business_dossier`, `sg_property_brief`, `sg_macro_brief`, `sg_transport_brief`, `sg_environment_brief`
- 8 operational helpers
- 1 bounded preferred interface, `sg_query`

`sg_query` is the bounded preferred interface across 20 routed families. The direct `sg_*` tools remain the stable low-level contract.

## Positioning

- Best for agent builders who need deterministic Singapore public-data calls
- Optimized for bounded workflows, not free-form analyst chat
- Current depth spans SingStat, MAS, OneMap, URA, LTA DataMall, NEA, HDB, CEA, BCA, BOA, ACRA, PA, Sport Singapore, ECDA, MSF Family Services, MSF Student Care Services, MSF Social Service Offices, GeBIZ, Hawker Centres, MOE Schools, MOH Healthcare, HSA, SFA, NParks, PUB, MOM, STB, HLB, and data.gov.sg
- The core differentiator is explicit contracts plus additive briefs, not hidden orchestration

## Discovery Resources

- `sg://apis`
- `sg://tools`
- `sg://workflows`
- `sg://recipes`
- `sg://runtime`
- `sg://playbooks`
- `sg://benchmarks`

Use `sg://recipes` first when the caller has a goal-shaped prompt and you need the fastest honest entrypoint. Use `sg://runtime` when you need auth, timeout, cache, health, or `sg_query` status-contract details without opening the docs. Use `sg://playbooks` when the task is bigger than one prompt and you need the strongest bounded workflow combination for an agent job. Use `sg://benchmarks` when you need adoption-grade latency, cache-tier, freshness, and credibility expectations for the headline workflows.

## Preferred Entry Points

- `sg_business_dossier`
  Cross-registry business diligence across ACRA, BCA, CEA, and explicit BOA, HSA, HLB, or GeBIZ modules.
- `sg_property_brief`
  Location and property brief across OneMap, URA, HDB, and optional live context.
- `sg_macro_brief`
  Compact Singapore macro starter brief using MAS values and validated SingStat GDP and CPI tables.
- `sg_transport_brief`
  Live transport operations brief over LTA bus arrivals, train alerts, and traffic incidents.
- `sg_environment_brief`
  Live environment brief over NEA forecast, air quality, and rainfall signals.
- `sg_query`
  Preferred bounded workflow planner and executor for covered families.

## Direct Tools Vs `sg_query`

- Use `sg_query` when the user starts from a prompt such as architecture-firm diligence, healthcare supplier diligence, hotel operator lookup, route planning, reverse geocoding, SingStat browsing, data.gov collection browsing, or URA development-charge lookup.
- Use direct `sg_*` tools when your application already has the exact coordinates, table IDs, dataset IDs, UENs, towns, or flat types.
- Treat blocked and unsupported `sg_query` responses as useful contract outcomes, not something to hide.
- Treat only `failed` as an execution error. Use `failedStep` plus the direct tool name to recover.

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

Live OneMap calls require valid credentials. There is no silent unauthenticated fallback.

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

### BOA

- `sg_boa_architects`
- `sg_boa_architecture_firms`

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

### GeBIZ

- `sg_gebiz_tenders`

### Hawker Centres

- `sg_hawker_centres`

### MOE Schools

- `sg_moe_schools`

### MOH Healthcare

- `sg_moh_facilities`

### HSA

- `sg_hsa_licensed_pharmacies`
- `sg_hsa_health_product_licensees`

### SFA

- `sg_sfa_establishments`

### NParks

- `sg_nparks_parks`

### PUB

- `sg_pub_water_levels`

### MOM

- `sg_mom_labour_stats`

### STB

- `sg_stb_visitor_stats`

### HLB

- `sg_hlb_hotels`

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
sg_property_brief { "planningArea": "Bedok", "flatType": "4 ROOM", "format": "json" }
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
sg_business_dossier { "uen": "201912345K", "modules": ["acra", "bca", "cea"], "format": "json" }
sg_acra_entities { "uen": "201912345K", "format": "json" }
sg_bca_licensed_builders { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_bca_registered_contractors { "companyName": "ABC CONSTRUCTION PTE LTD", "format": "json" }
sg_cea_salespersons { "registrationNo": "R123456A", "format": "json" }
```

### Architecture Firm Diligence

```text
sg_query { "query": "Architecture firm diligence for DP Architects", "mode": "execute" }
sg_business_dossier { "entityName": "DP Architects", "modules": ["acra", "boa", "gebiz"], "sectorHints": ["architecture", "procurement"], "format": "json" }
sg_boa_architecture_firms { "firmName": "DP Architects", "format": "json" }
sg_boa_architects { "firmName": "DP Architects", "format": "json" }
sg_gebiz_tenders { "supplierName": "DP Architects", "format": "json" }
```

### Healthcare Supplier Diligence

```text
sg_query { "query": "Healthcare supplier diligence for ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "mode": "execute" }
sg_business_dossier { "entityName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "modules": ["acra", "hsa", "gebiz"], "sectorHints": ["healthcare", "procurement"], "format": "json" }
sg_hsa_health_product_licensees { "companyName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "format": "json" }
sg_hsa_licensed_pharmacies { "pharmacyName": "A.M. Pharmacy Pte Ltd", "format": "json" }
sg_gebiz_tenders { "supplierName": "ZUELLIG PHARMA SPECIALTY SOLUTIONS GROUP PTE. LTD.", "format": "json" }
```

### Hotel Operator Lookup

```text
sg_query { "query": "Hotel operator lookup for Marina Bay Sands", "mode": "execute" }
sg_hlb_hotels { "name": "Marina Bay Sands", "format": "json" }
sg_hlb_hotels { "keeperName": "Marina Bay Sands Pte. Ltd.", "format": "json" }
sg_acra_entities { "entityName": "MARINA BAY SANDS PTE. LTD.", "format": "json" }
```

### Sector Scoped Business Diligence

```text
sg_query { "query": "Sector-scoped business diligence for Marina Bay Sands in hospitality", "mode": "execute" }
sg_business_dossier { "entityName": "MARINA BAY SANDS PTE. LTD.", "modules": ["acra", "hlb"], "sectorHints": ["hospitality"], "format": "json" }
sg_hlb_hotels { "keeperName": "Marina Bay Sands Pte. Ltd.", "format": "json" }
sg_acra_entities { "entityName": "MARINA BAY SANDS PTE. LTD.", "format": "json" }
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

## Additional Bounded Workflow Names

- Macro Snapshot
- Demographic Profile
- Civic Discovery
- Property And Regulatory Due Diligence
- Property Counterparty Diligence
- Business Registry Diligence
- Architecture Firm Diligence
- Healthcare Supplier Diligence
- Hotel Operator Lookup
- Sector Scoped Business Diligence
- Dataset Discovery Fallback
- Route Planning
- SingStat Table Drilldown
- Dataset Collection Browse
- Transport Status
- Environment Snapshot

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

`sg_health_check` probes SingStat, MAS, OneMap, URA, LTA DataMall, data.gov.sg, and NEA directly. OneMap, URA, and LTA are checked through the same authenticated runtime path used by the live tools.

Credential-gated live validation:

- `npm run quick-start`
- `npm run test:smoke:live`

## Examples

The workflow examples live in:

- `examples/business-dossier.md`
- `examples/architecture-firm-diligence.md`
- `examples/healthcare-supplier-diligence.md`
- `examples/hotel-operator-lookup.md`
- `examples/sector-scoped-business-diligence.md`
- `examples/property-brief.md`
- `examples/macro-brief.md`
- `examples/transport-brief.md`
- `examples/environment-brief.md`
- `examples/civic-discovery.md`
- `examples/geospatial-routing.md`
