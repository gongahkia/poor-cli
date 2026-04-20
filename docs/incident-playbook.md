# Incident Playbook

Use this runbook when workflow failures cross normal retry bounds or SLO indicators move into warning or breach states.

## Trigger Conditions

Start incident handling when any of these occur:

- `sg://benchmarks.latestEvidenceSnapshot.sloMeasurements[*].status` is `warning` or `breach`.
- unknown or uncategorized failures exceed 2 percent of total failed calls in one day.
- release-blocking workflow smoke checks fail in CI for two consecutive runs.
- authenticated upstreams (OneMap, URA, LTA) fail health checks despite valid credentials.

## Immediate Response (First 15 Minutes)

1. Record incident start time, failing workflow(s), and latest commit SHA.
2. Pull current benchmark and runtime evidence:
   - `sg://benchmarks`
   - `sg://runtime`
   - `sg://ops-taxonomy`
3. Capture correlated trace/request IDs from failing calls.
4. Run:

```bash
npm run diagnostics
SG_APIS_LOG_LEVEL=debug node packages/mcp-server/dist/index.js
```

5. Confirm whether failures are scoped to one source family or cross-family.

## Failure Class Matrix

| Class | Primary signals | First action | Escalation owner |
| --- | --- | --- | --- |
| `client_input` (`VALIDATION_ERROR`, `RESOURCE_ID_REQUIRED`) | 4xx failure envelopes, caller-side parameter defects | Return structured fix hints; no retry storm | Support / app integrator |
| `workflow_dependency` (`WORKFLOW_DEPENDENCY_ERROR`) | `sg_query` step dependency failures | Re-run prerequisite step directly and verify planner extraction | Platform + workflow maintainer |
| `workflow_execution` (`TOOL_RESULT_ERROR`) | Routed step failed after plan execution started | Use `failedStep` context, replay direct tool call, isolate upstream vs planner | Platform on-call |
| `credential_configuration` (`AUTH_MISSING`) | Auth probe failed, missing keystore/env credentials | Restore credential source, rerun `sg_health_check` | Security / platform |
| `upstream_timeout`, `network_path`, `upstream_reliability` | timeout/retry-exhausted/network errors | Validate upstream status, apply bounded retries, inspect circuit-breaker state | SRE / operations |
| `server_fault` (`INTERNAL_ERROR`) | 500 failures with trace IDs | Correlate trace logs, roll forward fix or rollback by commit | Core maintainer |

## Containment Actions

1. If only one toolset is affected, temporarily narrow deployment using `SG_APIS_TOOL_PROFILE` or explicit `SG_APIS_TOOLSETS`.
2. If auth-backed families are unstable, isolate public profile traffic while resolving credentials or upstream access.
3. If the failure is release-blocking, stop release promotion until:
   - `npm run verify` passes
   - release-blocking smoke checks recover
   - benchmark snapshot returns to non-breach state

## Recovery Exit Criteria

Mark incident resolved only when all are true:

1. Failing workflow reproductions now pass with fresh trace IDs.
2. The next benchmark snapshot reports no `breach` statuses.
3. Health probes for impacted families return `reachable: true`.
4. A short post-incident note is added to release notes or governance logs.

## Post-Incident Review Template

- Incident ID:
- Start / end time (UTC):
- Trigger condition:
- Affected workflows:
- Root cause category:
- Corrective change commit:
- Preventive follow-up task:
- KPI impact (availability, latency, freshness completeness):
