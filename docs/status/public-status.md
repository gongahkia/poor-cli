# Public Benchmark And Uptime Status

Generated: 2026-05-17T02:50:21.497Z

Source: local

Commit: 5fda9e9b66e46d41956c343277f6996eefa5ebd6

## Uptime

Measurement window: rolling-7d

Average availability: 98.75%

| Workflow | Availability | p50 | p95 | Status |
| --- | ---: | ---: | ---: | --- |
| Business Registry Diligence | 99.4% | 870 ms | 1820 ms | within_slo |
| Property And Regulatory Due Diligence | 97.8% | 2890 ms | 8420 ms | within_slo |
| Macro Snapshot | 98.6% | 2110 ms | 6530 ms | within_slo |
| Transport And Environment Snapshots | 99.2% | 760 ms | 2240 ms | within_slo |

## Freshness

Average freshness metadata completeness: 98.42%

| Workflow | Freshness completeness | Window | Notes |
| --- | ---: | --- | --- |
| Business Registry Diligence | 100% | rolling-7d | Primary diligence workflow baseline remained inside all target bands. |
| Property And Regulatory Due Diligence | 96.2% | rolling-7d | URA latency remains the p95 driver; freshness metadata was complete in baseline runs. |
| Macro Snapshot | 99.1% | rolling-7d | Live SingStat table reads remained within baseline latency budget. |
| Transport And Environment Snapshots | 98.4% | rolling-7d | Realtime probes and workflow responses remained inside baseline SLO windows. |

## Failures

No warning or breach statuses in the latest snapshot.

## Benchmarks

| Set | Fixtures | Schema | Source |
| --- | ---: | --- | --- |
| Singapore business-dossier diligence edge cases | 50 | diligence-edge-cases/v1 | benchmarks/diligence-edge-cases.json |

## Limits

- This page is generated from local or CI benchmark evidence; it is not an SLA.
- Skipped smoke checks are reported separately and do not count as failures.
- Freshness completeness measures whether outputs expose freshness metadata, not whether upstream data is intrinsically complete.
