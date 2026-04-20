# MASTER ROADMAP

## Purpose

This document is the single execution map for the repository roadmap.
It consolidates:

- [PHASE1.md](./PHASE1.md)
- [PHASE2.md](./PHASE2.md)
- [PHASE3.md](./PHASE3.md)
- [PHASE4.md](./PHASE4.md)
- [PHASE5.md](./PHASE5.md)

Primary goal: move from credible infrastructure to default Singapore MCP dependency for hackathon and enterprise developer workflows.

## Current Baseline (April 20, 2026)

- 69 tools across 29 data families.
- `sg_query` routes 20 families.
- Snapshot indicates package distribution and enterprise trust gaps remain key blockers.
- Phase sequencing prioritizes reliability before breadth.

## Phase Timeline

| Phase | Window | Primary Outcome |
| --- | --- | --- |
| Phase 1 | Day 0 to Day 30 | Installability, security baseline, direct test coverage uplift |
| Phase 2 | Day 31 to Day 60 | Enterprise observability, auth/toolset governance, SLO baseline |
| Phase 3 | Day 61 to Day 90 | Workflow depth in high-value SG use cases |
| Phase 4 | Day 91 to Day 120 | DX accelerators, compatibility matrix, adoption scaling |
| Phase 5 | Ongoing | Governance, deprecation, long-term product discipline |

## Dependency Graph

Phase order is intentionally strict because each stage de-risks the next.

```text
P1 -> P2 -> P3 -> P4 -> P5
```

Critical dependencies:

1. `P2` depends on `P1` release/distribution and security closure.
2. `P3` depends on `P2` operations schema and stable observability.
3. `P4` depends on `P3` stable workflow quality and schema confidence.
4. `P5` codifies all prior phase controls as ongoing guardrails.

## Milestone Gates

### Gate A (end of Phase 1)

- Package is resolvable and installable.
- No high-severity dependency vulnerabilities.
- Test reference coverage target met for tool surface.

### Gate B (end of Phase 2)

- Request traceability and error taxonomy are active and documented.
- Auth and toolset profile tests pass consistently.
- Initial SLO baseline published from CI artifacts.

### Gate C (end of Phase 3)

- Brief artifacts include deterministic confidence and risk signals.
- Backward compatibility maintained for existing consumers.
- Expanded workflows reflected in recipes/playbooks.

### Gate D (end of Phase 4)

- Integration templates are production-usable and CI-validated.
- Compatibility matrix and known-issues registry are active.
- Ecosystem trend reporting is automated and versioned.

### Gate E (Phase 5 steady state)

- Governance checklist enforced in release workflow.
- Quarterly health reporting cadence is stable.
- Ownerless surfaces reduced to zero.

## Owner Matrix (Role-Based)

| Work Area | Primary Owner | Secondary Owner | Notes |
| --- | --- | --- | --- |
| Release engineering and npm distribution | Platform Engineering | Core Maintainer | Includes publish, changelog, rollback readiness |
| Security and dependency governance | Security Engineering | Platform Engineering | Includes SLA tracking and audit automation |
| Tool contract tests and workflow regressions | QA/Quality Engineering | Domain Maintainers | Includes blocked/failed path verification |
| Runtime observability and ops taxonomy | Platform Engineering | SRE/Operations | Includes trace IDs and failure classification |
| Auth/toolset policy and profile governance | Security Engineering | Platform Engineering | Includes least-privilege profile controls |
| Brief/workflow product quality | Domain Maintainers | Product Engineering | Includes risk/confidence semantics |
| DX templates and compatibility docs | Developer Experience | Platform Engineering | Includes client matrix and migration guides |
| Ecosystem intelligence and quarterly reporting | Product/Strategy | Developer Experience | Uses scheduled snapshot artifacts |

## KPI Rollup

Track these cross-phase indicators in one dashboard:

1. Install success rate on clean environment.
2. Mean time to first successful workflow.
3. High/moderate vulnerability backlog.
4. Workflow success rate for supported prompts.
5. SLO compliance for top workflows (availability, latency, freshness completeness).
6. Documentation-drift defects per release.
7. Monthly package installation trend.
8. Mean time to diagnose failed workflow.

## 30/60/90/120-Day Deliverable Map

### Day 30

- Published package and validated install path.
- Security remediation baseline complete.
- Coverage uplift for currently weak tool references.

### Day 60

- Versioned operations schema.
- Trace-enabled runtime diagnostics.
- Auth and toolset profile hardening.

### Day 90

- Upgraded brief depth for business/property/ops workflows.
- Deterministic confidence/risk signals across core artifacts.
- Additional high-value SG workflow surfaces shipped with test coverage.

### Day 120

- SDK/template accelerators and compatibility matrix.
- Automated ecosystem trend reporting with historical snapshots.
- Segment-specific adoption lanes for hackathon and enterprise users.

## Risk Register (Top Program Risks)

| Risk | Probability | Impact | Mitigation |
| --- | --- | --- | --- |
| Package naming or publish friction | Medium | High | Reserve scoped fallback, pre-flight publish checks |
| Dependency patch breaks runtime behavior | Medium | High | Release-candidate lane with full smoke matrix |
| Observability overhead affects latency | Medium | Medium | Configurable verbosity and selective sampling |
| Workflow depth drifts into unverifiable synthesis | Medium | High | Rule-based deterministic signals tied to evidence |
| Template/compatibility maintenance burden | High | Medium | Keep minimal templates and strict support tiers |
| Governance overhead slows shipping | Medium | Medium | Automate checklist enforcement and keep controls concise |

## Change Control

Roadmap changes require:

1. Trigger reason (metric miss, ecosystem shift, security event, upstream API change).
2. Impacted phase and milestone gate.
3. New acceptance criteria and KPI changes.
4. Explicit owner and due date.

Changes should be logged in release notes and reflected in phase documents.

## Weekly Operating Cadence

1. Monday: security + dependency triage.
2. Tuesday: quality and regression review.
3. Wednesday: roadmap delivery checkpoint by phase.
4. Thursday: docs/runtime drift review.
5. Friday: ecosystem signal review and next-week commit plan.

## Immediate Next Actions

1. Execute Phase 1 release/distribution workstream first.
2. Stand up a single KPI dashboard artifact source in CI.
3. Assign named owners to each role-based row in the owner matrix.
4. Define gate-review meeting cadence (Gate A to Gate E).

