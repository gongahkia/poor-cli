# PHASE1: Distribution, Trust, and Baseline Reliability (Day 0 to Day 30)

## Context (as of April 20, 2026)

- Repository surface: 69 tools across 29 Singapore data families.
- Preferred interface: `sg_query` routes 20 families with bounded workflows.
- Snapshot signal: `@dude/mcp` package is not currently resolvable on npm.
- Snapshot signal: 17 tools have no direct test-file reference.
- Snapshot signal: dependency audit shows 6 vulnerabilities (3 moderate, 3 high).

This phase is about making the product installable, credible, and safe enough for sustained adoption.

## Objectives

1. Make installation and versioning production-grade.
2. Remove trust blockers in security and testing.
3. Reduce onboarding friction for hackathon and enterprise teams.

## Scope

- Packaging and release automation.
- Security remediation and dependency governance.
- Test coverage expansion on currently weak tool surfaces.
- Quickstart and adoption path tightening.

## Out of Scope

- Large new API family expansion.
- New major feature classes in brief generation.
- Enterprise billing or commercial packaging.

## Workstreams

### 1. Release and Distribution

- Decide final package naming strategy (unscoped vs scoped).
- Publish npm package and verify install path (`npx` and local config blocks).
- Add release workflow with changelog, tags, provenance, and smoke checks.
- Add post-release validation for at least three client environments.

### 2. Security and Dependency Hygiene

- Patch high and moderate vulnerabilities in dependency graph.
- Add scheduled dependency audit job (daily or weekly).
- Define patch SLA:
  - high severity: fix or mitigate within 3 working days
  - moderate severity: fix or mitigate within 10 working days

### 3. Tool-Level Confidence Uplift

- Add direct tests for all tools currently unreferenced in test files.
- Add regression tests for `sg_query` routed workflows with blocked/failed paths.
- Enforce per-release contract diff checks for tool input/output schemas.

### 4. Fast Adoption Path

- Add a single "15-minute install to first value" path in docs.
- Add a "no credentials" starter flow and "credentials ready" live flow.
- Add troubleshooting matrix by client and transport mode (stdio/http).

## Deliverables

- Published npm package with reproducible install instructions.
- CI release pipeline with smoke verification and rollback guidance.
- Security baseline report with vulnerability closure evidence.
- Expanded test suite covering previously unreferenced tools.
- Updated onboarding docs with deterministic first-run workflows.

## Exit Criteria

1. `npm view <final-package-name>` resolves successfully.
2. No open high-severity dependency vulnerabilities.
3. At least 95 percent of tools have direct test-file references.
4. Quickstart runs from clean environment without undocumented steps.
5. One full release completes via automated pipeline and passes smoke checks.

## KPIs

- Installation success rate (first attempt): >= 90 percent in internal trials.
- Mean time to first successful tool call: <= 15 minutes for new developers.
- Vulnerability backlog (high): 0.
- Release rollback events: 0 in this phase.

## Risks and Mitigations

- Risk: npm naming collision or policy delays.
  - Mitigation: reserve scoped fallback package and document migration alias.
- Risk: dependency update breaks transitive runtime behavior.
  - Mitigation: add release-candidate lane with full smoke matrix.
- Risk: test expansion increases CI runtime too much.
  - Mitigation: parallelize suites and split fast vs extended jobs.
