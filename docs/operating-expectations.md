# Operating Expectations

Single-page adoption-grade view of what to expect from this server in production. Use this when integrating; the source-of-truth runtime contract still lives in `sg://runtime` and `sg://benchmarks` (and the deeper details in [production-notes.md](./production-notes.md)).

## Per-Family Quick Reference

| Family | Auth | Typical p50 | Cache Tier | Default TTL | Schema Stability |
|---|---|---|---|---|---|
| SingStat | None | 1-3s | DAILY | 1h | Stable |
| MAS | None | 0.5-2s | NEAR_REALTIME | 5m | Moderate |
| OneMap | Email+Password | 0.5-2s (cold token slower) | STATIC | 1d | Moderate |
| URA | API key | 3-10s | DAILY | 1h | Moderate |
| LTA DataMall | API key | 0.5-2s | REALTIME | 30s | Stable |
| NEA | None | 0.5-2s | REALTIME | 30s | Moderate |
| HDB | None | 1-3s | DAILY | 1h | Stable |
| ACRA / BCA / CEA / BOA / HSA / HLB | None | 1-3s | STATIC | 1d | Stable |
| GeBIZ | None | 1-3s | DAILY | 1h | Stable |
| MOE / MOH / ECDA / MSF / PA / SportSG / Hawker | None | 1-3s | STATIC | 1d | Stable |
| Government RSS Feeds | None | 1-3s | NEAR_REALTIME | 5m | Moderate |
| data.gov.sg | None | 1-5s | DAILY | 1h | Stable |
| Hard cap | — | 30s | — | — | — |

Token-bucket rate limits per family (URA most restrictive at ~1 req/s; OneMap most permissive at ~4 req/s). See [production-notes.md](./production-notes.md#rate-limits-by-family) for the full table.

## SLO Posture by Headline Workflow

Targets are framed for agent developers, not consumer chat products. Recalibrate after sustained production traffic.

| Workflow | Availability | p50 | p95 | Freshness completeness |
|---|---|---|---|---|
| Business Registry Diligence | 99.0% | 1.2s | 3.0s | 100% |
| Property And Regulatory Due Diligence | 97.0% | 3.2s | 9.0s | 95% |
| Macro Snapshot | 98.0% | 2.2s | 7.0s | 98% |
| Transport And Environment Snapshots | 99.0% | 0.9s | 2.5s | 98% |

These match `BASELINE_SLO_TARGETS` in `packages/mcp-server/src/tools/catalog.ts` and the `sg://benchmarks` resource. Latest evidence snapshot is published in `BENCHMARK_EVIDENCE_SNAPSHOT` and refreshed by `npm run benchmarks:snapshot`.

## What Each Cache Tier Means For You

- **REALTIME (30s):** transport ETAs and weather signals. Treat artifacts older than 30s as stale.
- **NEAR_REALTIME (5m):** MAS exchange rates, gov RSS feeds. Safe to reuse within a single request batch.
- **DAILY (1h):** SingStat tables, URA transactions, HDB resale prices, GeBIZ. Cache results across an agent session.
- **STATIC (1d):** geocodes, planning areas, no-auth registries. Can be persisted across process restarts.
- **ARCHIVAL (7d):** historical time series. Effectively immutable.

Cache storage: SQLite at `~/.sg-apis/cache.db` (WAL mode). Typical size: 10-100 MB.

## Partial-Failure Semantics

Brief tools use `safeRead()` so a single upstream failure does not collapse the artifact:

- the brief still returns with the remaining sources
- failed sources appear in `gaps[]` with `code` and `message`
- failed sources show `recordCount: 0` in `provenance[]`
- `freshness[]` still reports the observation timestamp
- top-level `riskFlags[]` and `nextChecks[]` (where present) call out which direct tool to escalate to

Always inspect `gaps` before trusting `summary`. If you ship the brief into a UI, render `gaps` and `freshness` alongside `summary` to keep partial-failure visibility intact.

## Retry, Circuit, And Backoff

- Retryable: 429, 5xx
- Non-retryable: 401/403/404 and other 4xx
- Backoff: exponential with jitter (1s, 2s, 4s, 8s; max 15s)
- Max retries: 3
- Circuit breaker: opens after 3 consecutive failures, 60s reset, half-open probe

When a circuit is open, calls fail fast with a descriptive error instead of hitting the upstream. This is intentional and surfaces in `gaps` so brief artifacts remain interpretable.

## Credential Bootstrap

- OneMap: `SG_API_ONEMAP_EMAIL`, `SG_API_ONEMAP_PASSWORD` (or `sg_key_set` with `apiName: "onemap"`)
- URA: `SG_API_URA_KEY` (or `sg_key_set` with `apiName: "ura"`)
- LTA DataMall: `SG_API_LTA_KEY` (or `sg_key_set` with `apiName: "lta"`)
- All other families: no auth required

Token refresh: OneMap and URA tokens are refreshed automatically on 401. The keystore at `~/.sg-apis/keys.db` provides a persistent fallback. Verify with `sg_health_check` before assuming an issue is upstream rather than configuration.

## Adoption Checkpoints

| Checkpoint | What it proves | How to verify |
|---|---|---|
| Five-minute success | A new developer can boot and reach a no-auth tool on a clean machine. | `npm install && npm run try`; CI shows the same public path as `Run public no-credential smoke`. |
| Bounded routing trust | Blocked, unsupported, and failed `sg_query` outcomes are obvious in app code. | Run examples under `examples/integration/` and inspect blocked-state responses. |
| Artifact credibility | Public workflows return real live data, not placeholders. | `npm run test:smoke:public`; for credentialed flows, `npm run test:smoke:live`. |
| Release-grade evidence | SLO snapshots and packaging smoke pass per release window. | `npm run release:preflight` plus `npm run benchmarks:snapshot`. |

## When To Treat An Artifact As Stale

- `freshness[i].upstreamTimestamp` is null and `cache tier` is REALTIME or NEAR_REALTIME
- `gaps[]` contains entries scoped to your headline summary source
- `provenance[i].recordCount` is 0 for the source that backs your headline
- For Housing Advisor flows: `rulesLastVerified` is older than the most recent SG Budget date (annual, ~Feb)

If any of these are true, prefer routing to the underlying direct tool rather than the brief. The brief surfaces these signals deliberately so the caller can escalate.

## Cross-References

- Full per-family detail: [production-notes.md](./production-notes.md)
- Compatibility and known issues: [compatibility-matrix.md](./compatibility-matrix.md), [known-issues.md](./known-issues.md)
- Incident response: [incident-playbook.md](./incident-playbook.md)
- KPI policy: [kpi-thresholds.md](./kpi-thresholds.md)
