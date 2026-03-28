# Production Notes

Operational guidance for teams deploying sg-apis-mcp in production.

The same runtime contract is also exposed as the machine-readable `sg://runtime` resource for MCP clients that want to cache operational assumptions instead of scraping docs. Adoption-oriented latency, cache-tier, and credibility expectations for the headline workflows are also exposed through `sg://benchmarks`.

## Latency Expectations

| API Family | Timeout (ms) | Typical Latency | Notes |
|---|---|---|---|
| SingStat | 15000 | 2-8s | Large table queries can be slow |
| MAS | 10000 | 1-3s | CKAN datastore queries |
| OneMap | 10000 | 0.5-2s | Auth token refresh adds ~1s on first call |
| URA | 20000 | 3-10s | Token endpoint can be slow; bulk transaction queries are heavy |
| LTA DataMall | 10000 | 0.5-2s | Real-time endpoints are fast |
| NEA | 10000 | 0.5-2s | Weather API is responsive |
| data.gov.sg | 10000 | 1-5s | Depends on dataset size and CKAN load |

Hard cap timeout: **30000ms**. No single upstream call will block longer than this.

## Cache TTL by Tier

| Tier | TTL (seconds) | Used By | Rationale |
|---|---|---|---|
| REALTIME | 30 | LTA bus arrivals, NEA forecast/rainfall | Live data, stale after 30s |
| NEAR_REALTIME | 300 (5m) | MAS exchange rates | Updates every few minutes |
| DAILY | 3600 (1h) | SingStat, URA transactions, HDB resale | At most daily updates |
| STATIC | 86400 (1d) | OneMap geocodes, planning areas, CEA/BCA/ACRA registries | Changes quarterly at most |
| ARCHIVAL | 604800 (7d) | Historical time series | Never changes |

Cache storage: SQLite at `~/.sg-apis/cache.db` (WAL mode). Typical size: 10-100 MB.

## Rate Limits by Family

| API Family | Max Tokens | Refill/sec | Effective Rate |
|---|---|---|---|
| SingStat | 10 | 2 | ~2 req/s sustained |
| MAS | 10 | 2 | ~2 req/s sustained |
| OneMap | 50 | 4 | ~4 req/s sustained |
| URA | 5 | 1 | ~1 req/s sustained (most restrictive) |
| LTA DataMall | 20 | 2 | ~2 req/s sustained |
| NEA | 20 | 2 | ~2 req/s sustained |
| data.gov.sg | 20 | 3 | ~3 req/s sustained |

Token-bucket algorithm: requests acquire tokens, blocked if empty until refill.

## Retry Strategy

- **Retryable**: HTTP 429 (rate limit), 5xx (server errors)
- **Non-retryable**: 401/403 (auth), 404 (not found), other 4xx
- **Backoff**: Exponential with jitter — 1s, 2s, 4s, 8s (max 15s)
- **Max retries**: 3 by default
- **Retry-After**: Respected when present in response headers

## Circuit Breaker

Each API family has an independent circuit breaker:

- **Threshold**: 3 consecutive failures to open
- **Reset timeout**: 60 seconds
- **States**: closed (normal) → open (failing, fast-reject) → half-open (probe one request)

When open, calls fail immediately with a descriptive error instead of hitting the upstream.

## Partial Failure Semantics

Brief tools use `safeRead()` to catch per-source errors without failing the whole brief:

- If one source fails (e.g., URA timeout), the brief still returns with the remaining sources
- Failed sources appear in the `gaps` array with error code and message
- The `provenance` array shows `recordCount: 0` for failed sources
- The `freshness` array still reports the observation timestamp

This means a brief artifact is always returned even under partial failure. Consumers should check `gaps` to understand missing context.

## Credential Behavior

| API | Auth Type | Env Var | Fallback |
|---|---|---|---|
| OneMap | Email + Password → token | `SG_API_ONEMAP_EMAIL`, `SG_API_ONEMAP_PASSWORD` | Keystore |
| URA | API key → access token | `SG_API_URA_KEY` | Keystore |
| LTA DataMall | API key (header) | `SG_API_LTA_KEY` | Keystore |
| All others | None | — | — |

Token refresh: OneMap and URA tokens are refreshed automatically on 401. The keystore (`~/.sg-apis/keys.db`) provides a persistent fallback for credentials not set via environment.

## Upstream Schema Stability

| API | Stability | Notes |
|---|---|---|
| SingStat TableBuilder | Stable | JSON API, versioned endpoints |
| MAS | Stable | CKAN datastore, rarely changes |
| OneMap | Moderate | Endpoints stable, response shapes occasionally adjusted |
| URA | Moderate | Token endpoint can change; transaction fields are stable |
| LTA DataMall | Stable | OData-style, well-documented |
| NEA | Moderate | Weather endpoints are public and stable; air quality schema updates quarterly |
| data.gov.sg | Stable | CKAN standard; v2 API is the current surface |

## Configuration

Runtime config file: `~/.sg-apis/config.json`

Override any default via environment variables:
- `SG_APIS_LOG_LEVEL` — debug, info, warn, error
- `SG_APIS_CACHE_TTL_DAILY` — override daily TTL in seconds

## Monitoring

Use `sg_health_check` to probe all API families. OneMap, URA, and LTA are checked through the same authenticated runtime path used by the live tools. Returns per-family: reachable status, latency, auth status, dependency coverage, and errors.

Use `npm run test:smoke:live` when you want one credential-gated smoke flow over the live MCP server plus representative data.gov datastore and file-download families.

Use `sg_cache_stats` to inspect cache hit/miss rates and storage size.
