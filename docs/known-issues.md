# Known Issues

## Purpose

This registry tracks validated issues and operator-safe workarounds.
Every entry should map to a reproducible signal, not anecdotal behavior.

## Active Issues

| ID | Area | Symptom | Impact | Workaround | Status |
| --- | --- | --- | --- | --- | --- |
| `KI-001` | OneMap auth | `sg_query` geospatial/civic routes return blocked due to missing credentials | Location-first workflows cannot execute | Set `SG_API_ONEMAP_EMAIL` and `SG_API_ONEMAP_PASSWORD` (or keystore entries), then run `sg_health_check` | Open |
| `KI-002` | LTA DataMall | `sg_transport_brief` omits live transport signals when key is absent | Transport context degrades to partial | Set `SG_API_LTA_KEY` and verify with `sg_lta_train_alerts` | Open |
| `KI-003` | URA token exchange | Property planning reads fail when URA key is invalid/expired | `sg_property_brief` loses planning detail | Rotate `SG_API_URA_KEY`; validate with `sg_ura_planning_area` | Open |
| `KI-004` | npm propagation after publish | Registry smoke may fail immediately after release due package CDN delay | False-negative release signal | Re-run `npm run test:smoke:registry` after short delay; do not hotfix blindly | Open |
| `KI-005` | External ecosystem APIs | `ecosystem:snapshot` can partially fail under GitHub/StackOverflow rate limits | Trend artifact may have missing external sections | Provide `GITHUB_TOKEN`; treat missing external blocks as non-release-blocking | Open |

## Triage Rules

1. Add an issue only after reproduction with a command or failing test.
2. Document exact mitigation commands and required env vars.
3. Mark as `Closed` only when regression coverage exists or the upstream risk is removed.
4. Keep links to incidents or PRs in release notes when a known issue changes state.
