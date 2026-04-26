# PHASE2: Enterprise Hardening and Operational Transparency (Day 31 to Day 60)

## Intent

Phase 1 makes the repository installable and trustworthy.
Phase 2 makes it operable in enterprise environments with explicit observability, policy controls, and failure semantics.

## Objectives

1. Make runtime behavior diagnosable at scale.
2. Make policy boundaries explicit for least-privilege operation.
3. Provide production confidence signals beyond correctness tests.

## Scope

- Structured observability and operations schema.
- Auth and toolset policy hardening.
- Benchmarks, SLOs, and incident operations.

## Out of Scope

- Major domain expansion into many new data families.
- Opinionated UI product development.

## Workstreams

### 1. Request Tracing and Structured Error Taxonomy

- Add request/trace identifiers for tool invocations and workflow steps.
- Version the error/ops taxonomy in machine-readable form.
- Include retryability and operator-action hints in failure envelopes.

### 2. Toolset Governance and Access Profiles

- Introduce profile presets (for example: `public`, `diligence`, `property`, `ops`).
- Define profile-to-tool mappings in one canonical source.
- Add profile-focused smoke tests to ensure no accidental permission drift.

### 3. Auth Hardening

- Add auth regression tests for `none`, `mixed`, and `all` modes.
- Add OIDC integration test coverage for token validation edge cases.
- Add documentation for secure default deployment patterns.

### 4. Operational Evidence

- Promote benchmark snapshots to CI artifacts with trend retention.
- Publish baseline SLOs for core workflows:
  - availability
  - p50/p95 latency
  - freshness response completeness
- Add incident playbook for common failure classes.

## Deliverables

- Versioned operations schema and error taxonomy.
- Trace-enabled logs and request-correlated diagnostics.
- Toolset profile framework with tests and docs.
- CI-generated benchmark history and baseline SLO dashboard artifact.
- Incident playbook linked from runtime docs.

## Exit Criteria

1. Every failure category maps to a documented error code and operator action.
2. Core workflows expose request/trace IDs in logs and diagnostics artifacts.
3. Toolset profiles can be enabled without manual allowlist edits.
4. Auth mode tests pass for all supported transport/auth combinations.
5. Two consecutive weekly benchmark runs remain within defined SLO bands.

## KPIs

- Mean time to diagnose failed workflow: reduced by >= 40 percent.
- Unknown/unclassified errors in logs: <= 2 percent of total failures.
- Unauthorized tool access incidents: 0 in profile-constrained environments.
- SLO compliance for top workflows: >= 95 percent.

## Risks and Mitigations

- Risk: richer telemetry increases payload or logging overhead.
  - Mitigation: support configurable verbosity and sampling controls.
- Risk: profile segmentation breaks existing user assumptions.
  - Mitigation: ship migration guide with explicit old-to-new mapping.
- Risk: SLO targets are set before real traffic profile is known.
  - Mitigation: mark as provisional for one cycle, then recalibrate.

