# Public Benchmark And Source Status

Generated: 2026-05-23T01:07:16.797Z

Source: local

Commit: 9c9124a8deeeb518edccc0ba819e9b57c9e3b2a1

## Release Evidence

Measurement window: rolling-7d

Average availability-style gate: 98.9%

| Workflow | Availability-style gate | p50 | p95 | Status |
| --- | ---: | ---: | ---: | --- |
| Swee Pulse Snapshot | 99% | 500 ms | 2500 ms | within_slo |
| Swee Pulse Weather | 99% | 420 ms | 1800 ms | within_slo |
| Swee Pulse Mobility | 98.5% | 680 ms | 2600 ms | within_slo |
| Transport Reliability Benchmark | 98.5% | 700 ms | 2800 ms | within_slo |
| Swee Shield Audit Review | 99.5% | 40 ms | 200 ms | within_slo |

## Freshness

Average freshness metadata completeness: 91%

| Workflow | Freshness completeness | Window | Notes |
| --- | ---: | --- | --- |
| Swee Pulse Snapshot | 90% | rolling-7d | Pulse summarizes source-backed city signals and surfaces freshness gaps explicitly. |
| Swee Pulse Weather | 95% | rolling-7d | Weather signals remain deterministic and retain NEA provenance. |
| Swee Pulse Mobility | 85% | rolling-7d | Credential-gated LTA sources are tracked as explicit gaps when unavailable. |
| Transport Reliability Benchmark | 85% | rolling-7d | Transport reliability proof covers incidents, train alerts, road events, and traffic camera freshness before broader civic expansion. |
| Swee Shield Audit Review | 100% | rolling-7d | Shield writes sanitized replay metadata for every governed call. |

## Failures

No warning or breach statuses in the latest snapshot.

## Transport Reliability

LTA transport reliability source coverage for civic-hacker demos.

| Source tool | Surface | Auth | Coverage | Freshness evidence |
| --- | --- | --- | --- | --- |
| sg_lta_traffic_incidents | Swee Pulse mobility signal + source health | required | Network-wide traffic incident rows. | LTA does not provide a row timestamp; Swee Pulse reports observedAt and preserves the missing upstream timestamp as a confidence limit. |
| sg_lta_train_alerts | Swee Pulse mobility signal + source health | required | Network-wide train service alerts and operator messages. | Operator message createdDate is used when present; otherwise freshness is surfaced as unknown. |
| sg_lta_road_works | Swee Pulse mobility signal + source health | required | Network-wide road-work events with start/end timing. | Event start/end timing is retained as upstream timing context; unknown timing remains visible in source health. |
| sg_lta_road_openings | Swee Pulse mobility signal + source health | required | Network-wide road-opening events with start/end timing. | Event start/end timing is retained as upstream timing context; unknown timing remains visible in source health. |
| sg_lta_traffic_images | Swee Pulse source health | not required | Traffic camera image references and camera timestamps. | Camera timestamps drive freshness where data.gov.sg returns them. |
| sg_lta_bus_arrivals | Credentialed direct adapter | required | Stop-level bus arrival timings when exact bus stop inputs are supplied. | Arrival estimates remain direct-adapter evidence and are not collapsed into the default network-wide Pulse snapshot. |
| sg_lta_carpark_availability | Credentialed direct adapter | required | Live carpark lot availability for filtered or capped queries. | Adapter responses expose observedAt metadata; Swee Pulse does not currently score carpark availability as a city disruption signal. |
| sg_lta_taxi_availability | Credentialed direct adapter | required | Available taxi coordinates for bounded queries. | Adapter responses expose observedAt metadata; Swee Pulse does not currently infer transport safety or availability claims from taxi positions. |

- This benchmark reports source coverage and evidence handling, not official service status.
- Credentialed LTA checks require SG_API_LTA_KEY or a local keystore entry.
- Missing upstream timestamps are reported as limits instead of being filled with synthetic freshness.

## Benchmarks

| Set | Fixtures | Schema | Source |
| --- | ---: | --- | --- |
| Swee Pulse and Shield release baseline | 5 | swee-benchmarks/v1 | scripts/generate-benchmark-snapshot.mjs |

## Limits

- This page is generated from local or CI benchmark evidence; it is not an SLA.
- Skipped smoke checks are reported separately and do not count as failures.
- Freshness completeness measures whether outputs expose freshness metadata, not whether upstream data is intrinsically complete.
