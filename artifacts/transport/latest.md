# Swee Transport Live Benchmark

Generated: 2026-05-23T01:16:55.967Z

Pulse audit: 21930226-4fc7-4d3e-9194-a090a228b784

Shield decision: allow / medium

## Source Checks

| Source tool | Source | Auth | State | Records | Freshness | Upstream | Gaps |
| --- | --- | --- | --- | ---: | --- | --- | --- |
| sg_lta_traffic_incidents | LTA DataMall | required | credential_missing | 0 | unknown | n/a | SG_LTA_TRAFFIC_INCIDENTS_FAILED |
| sg_lta_train_alerts | LTA DataMall | required | credential_missing | 0 | unknown | n/a | SG_LTA_TRAIN_ALERTS_FAILED |
| sg_lta_road_works | LTA DataMall | required | credential_missing | 0 | unknown | n/a | SG_LTA_ROAD_WORKS_FAILED |
| sg_lta_road_openings | LTA DataMall | required | credential_missing | 0 | unknown | n/a | SG_LTA_ROAD_OPENINGS_FAILED |
| sg_lta_traffic_images | data.gov.sg transport feed | not required | ready | 90 | fresh | 2026-05-23T09:16:16+08:00 | none |

## Pulse Summary

Signals: 0

Watch-or-higher signals: 0

Gaps: 4

## Limits

- This artifact is live local evidence, not an SLA or official public-agency service status.
- Credentialed LTA DataMall checks require SG_API_LTA_KEY or a local Swee SG keystore entry.
- Missing upstream timestamps and source gaps are preserved instead of being filled with synthetic freshness.
- Stop-level bus arrivals, carparks, and taxis remain direct-adapter follow-ups; this proof covers the default Pulse mobility runtime path.
