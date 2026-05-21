# Public Benchmark And Uptime Status

Generated: 2026-05-21T06:51:27.832Z

Source: local

Commit: 1d8e163d501dc936bfd79542a1ff85400364f108

## Uptime

Measurement window: rolling-7d

Average availability: 99.13%

| Workflow | Availability | p50 | p95 | Status |
| --- | ---: | ---: | ---: | --- |
| Company CDD Report | 99.4% | 870 ms | 1820 ms | within_slo |
| Architecture Firm Diligence | 99.1% | 980 ms | 2400 ms | within_slo |
| Healthcare Supplier Diligence | 99% | 1040 ms | 2600 ms | within_slo |
| Hotel Operator Lookup | 99% | 940 ms | 2300 ms | within_slo |

## Freshness

Average freshness metadata completeness: 100%

| Workflow | Freshness completeness | Window | Notes |
| --- | ---: | --- | --- |
| Company CDD Report | 100% | rolling-7d | Primary company/UEN CDD workflow baseline remained inside all target bands. |
| Architecture Firm Diligence | 100% | rolling-7d | Architecture-sector enrichment preserved provenance, gaps, limits, and freshness metadata. |
| Healthcare Supplier Diligence | 100% | rolling-7d | Healthcare-sector enrichment preserved evidence-bound gaps and limits. |
| Hotel Operator Lookup | 100% | rolling-7d | Hospitality-sector enrichment preserved source attribution and review limits. |

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
