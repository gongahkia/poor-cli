# AGENTS.md - Swee SG Runtime

This repository is now one product surface: policy-governed Singapore public-data signals.

Swee SG's job is to let a user inspect current Singapore city signals, understand source freshness and gaps, and review the Shield audit trail behind every tool or REST call.

The retained `sg_*` namespace remains stable for raw public-data adapters. Product workflows should enter through Swee Pulse and Swee Shield.

## Hard Rules

Never invent public-data values.

1. Do not invent source rows, freshness, provenance, gaps, or recommendations.
2. Treat Pulse output as an operator signal layer, not an official emergency instruction channel.
3. Surface source health, freshness, gaps, limits, and recommended follow-ups in user-facing output.
4. Do not provide legal, tax, AML, sanctions, credit, investment, medical, safety, or licensed-advisor opinions.
5. If a user asks for the retired CDD product path, explain that Swee SG no longer exposes the report-first counterparty workflow and point to direct `sg_*` compatibility adapters only when exact structured parameters are available.

## Tool Routing

| User asks about... | Preferred tool | Direct follow-ups |
| --- | --- | --- |
| Singapore city overview | `swee_pulse_snapshot` | `swee_pulse_mobility`, `swee_pulse_weather` |
| Mobility signals | `swee_pulse_mobility` | `sg_lta_traffic_incidents`, `sg_lta_train_alerts`, `sg_lta_road_works`, `sg_lta_traffic_images` |
| Weather and rainfall | `swee_pulse_weather` | `sg_nea_forecast_2hr`, `sg_nea_air_quality`, `sg_nea_rainfall` |
| Source-backed explanation | `swee_pulse_explain` | Use only after deterministic Pulse signals exist |
| Policy/audit review | `swee_shield_audit_lookup` | `swee_shield_scan_tools`, `sg_trace_lookup`, `sg_request_lookup` |
| Raw public-data lookup | Exact `sg_*` adapter | Prefer Pulse for app-level workflows |
| Runtime ops | ops tools | health, cache, key, config, trace, request lookup |

## Product UX

The web app should stay signal-first:

1. Overview cards for active signals, watch-level signals, source health, and gaps.
2. Mobility and weather sections that explain what changed, why it matters, and what the operator should check next.
3. Source health that shows ready, degraded, and gap states with observed freshness.
4. Shield audit rows that show policy decisions, status, duration, and replay metadata.
5. Optional explain-only AI copy that never changes severity, provenance, or deterministic signal values.

## Output Contract

For Pulse answers:

- Lead with the most important source-backed signal.
- Show gaps, limits, and source freshness.
- Cite source names when summarizing data.
- Keep recommended actions operational and non-advisory.
- Do not turn absence of public evidence into a positive clearance or safety claim.

## Retained Runtime Surface

Product tools:

- `swee_pulse_snapshot`
- `swee_pulse_mobility`
- `swee_pulse_weather`
- `swee_pulse_explain`
- `swee_shield_audit_lookup`
- `swee_shield_scan_tools`

Selected raw adapters:

- `sg_datagov_search`
- `sg_singstat_search`
- `sg_onemap_geocode`
- `sg_nea_forecast_2hr`
- `sg_nea_air_quality`
- `sg_nea_rainfall`
- `sg_lta_traffic_incidents`
- `sg_lta_train_alerts`
- `sg_lta_road_works`
- `sg_lta_road_openings`
- `sg_lta_traffic_images`

Ops tools:

- `sg_health_check`
- `sg_cache_stats`
- `sg_cache_clear`
- `sg_key_set`
- `sg_key_list`
- `sg_key_delete`
- `sg_config_get`
- `sg_config_set`
- `sg_trace_lookup`
- `sg_request_lookup`
