# sg-skills Audit Handoff For Independent Implementation

Date: 2026-04-03
Repository: `/Users/gongahkia/Desktop/coding/projects/sg-skills`
Primary intent of this document: provide a complete audit and implementation-ready handoff so an independent coding agent can execute fixes and enhancements without re-discovery.

## 1. Scope And Method

This audit was performed as a repository-wide engineering + product review with direct code and script validation.

Work done:
- Enumerated repository structure and package boundaries.
- Inspected server runtime, auth, routing, tool registration, docs parity, release/CI scripts.
- Ran key commands to validate runtime and quality gates.
- Traced claims in docs to actual implementation behavior.
- Identified capability strengths, reliability/security gaps, and product expansion opportunities.

Commands executed and outcomes:
- `npm run diagnostics` with `SG_APIS_ARTIFACT_DB_PATH=/tmp/sg-apis-artifacts-audit.db`: passed.
- `npm run verify` with `SG_APIS_ARTIFACT_DB_PATH=/tmp/sg-apis-artifacts-audit.db`: failed in live-surface step due missing `CHANGELOG.md`.
- `npm test`: passed (`40` files, `286` tests).

## 2. Repository Intent, Structure, And Real Capability

### 2.1 Product Intent (What this repo is trying to be)

The repo is a deterministic Singapore public-data MCP platform for agent builders, not a free-form analyst engine.

Core product thesis currently implemented:
- Stable, explicit `sg_*` direct tools.
- Bounded `sg_query` workflow planning/execution layer.
- Additive brief artifacts for high-value workflows.
- Machine-readable catalog resources for discovery and integration.

Evidence:
- [`README.md`](README.md)
- [`docs/architecture.md`](docs/architecture.md)
- [`docs/product-audit.md`](docs/product-audit.md)
- [`packages/mcp-server/src/tools/query-tool.ts`](packages/mcp-server/src/tools/query-tool.ts)

### 2.2 Technical Structure

Top-level monorepo:
- `packages/shared`: runtime primitives (HTTP client, cache, keystore, rate limiting, config, schemas, logger).
- `packages/mcp-server`: MCP server, tool handlers, router/planner/classifier, HTTP server, REST gateway, catalogs/resources.
- `packages/skill`: skill packaging and docs surface.

Core runtime flow:
- Entry: [`packages/mcp-server/src/index.ts`](packages/mcp-server/src/index.ts)
- MCP server factory: [`packages/mcp-server/src/server-factory.ts`](packages/mcp-server/src/server-factory.ts)
- Tool registration and filtering by toolset: [`packages/mcp-server/src/tools/registry.ts`](packages/mcp-server/src/tools/registry.ts), [`packages/mcp-server/src/tools/tool-definition.ts`](packages/mcp-server/src/tools/tool-definition.ts), [`packages/mcp-server/src/tools/tool-metadata.ts`](packages/mcp-server/src/tools/tool-metadata.ts)
- Bounded NL routing: classifier + planner (`router/*`)

### 2.3 Capability Inventory (Validated)

From diagnostics + built catalog:
- Tools: 68
- API families: 29
- Workflows: 16
- Recipes: 22
- Resources: 7

Validated resources:
- `sg://apis`
- `sg://tools`
- `sg://workflows`
- `sg://recipes`
- `sg://runtime`
- `sg://playbooks`
- `sg://benchmarks`

## 3. Key Strengths To Preserve

1. Deterministic contract-first design
- Direct tools and bounded workflows stay explicit and inspectable.
- Good foundation for agent reliability and auditability.

2. High test coverage and packaging rigor
- `286` tests pass.
- Packaging smoke script enforces runtime-only package contents and MCP surface shape.
- Evidence: [`scripts/smoke-packages.mjs`](scripts/smoke-packages.mjs)

3. Strong discovery model
- Catalog/resource surfaces support integrator discovery without source reading.

4. Good separation of concerns
- Shared runtime package keeps common logic centralized.
- Server package isolates routing/tool surfaces.

5. Production-minded auth path exists for MCP HTTP
- OIDC/mixed/all auth modes with protected-resource metadata and session control.
- Evidence: [`packages/mcp-server/src/http-auth.ts`](packages/mcp-server/src/http-auth.ts), [`packages/mcp-server/src/http-server.ts`](packages/mcp-server/src/http-server.ts)

## 4. Critical Findings (Engineering + Product)

Findings are prioritized by severity and implementation urgency.

### F1. Verify/release gate is currently broken by missing changelog file

Severity: Critical
Impact:
- `npm run verify` fails before tests in normal flow.
- CI/release confidence is invalid until fixed.

Observed failure:
- `rg: CHANGELOG.md: No such file or directory` from live-surface script.

Root cause:
- Hardcoded references to `CHANGELOG.md` in scripts that assume it exists.

Evidence:
- [`scripts/check-live-surface.mjs#L11-L13`](scripts/check-live-surface.mjs)
- [`scripts/check-live-surface.mjs#L25-L27`](scripts/check-live-surface.mjs)
- [`scripts/check-docs-parity.mjs#L183-L190`](scripts/check-docs-parity.mjs)

Implementation direction:
- Add file-existence guards before including `CHANGELOG.md` in scan/check lists.
- If changelog is required by policy, fail with explicit actionable message, not raw ENOENT.
- Optionally enforce via a dedicated script step (`check-required-files`) to keep errors intentional.

Acceptance criteria:
- `npm run verify` no longer fails due ENOENT for missing changelog.
- Failure message is policy-driven and explicit when changelog policy is violated.

### F2. CI trigger coverage is insufficient

Severity: Critical
Impact:
- Regressions can merge without automatic verification.

Root cause:
- Workflow only runs on manual `workflow_dispatch`.

Evidence:
- [` .github/workflows/ci.yml#L3-L4`](.github/workflows/ci.yml)

Implementation direction:
- Add `push` and `pull_request` triggers.
- Restrict branches as needed (for example `main`, `develop`) to control CI spend.

Acceptance criteria:
- CI runs automatically for PRs and pushes on selected branches.

### F3. Release documentation drifts from actual automation

Severity: High
Impact:
- Operators follow non-existent workflow docs.

Root cause:
- `docs/release.md` references `.github/workflows/publish.yml`, but that file does not exist.

Evidence:
- [`docs/release.md#L16`](docs/release.md)
- `.github/workflows` currently contains only `ci.yml`.

Implementation direction:
- Either create `publish.yml` matching docs, or revise docs to match current state.
- If publish automation is intended, implement it fully with tag triggers and smoke gates.

Acceptance criteria:
- Release docs and workflow files are consistent and executable.

### F4. REST gateway bypasses auth/toolset controls

Severity: High (Security / deployment risk)
Impact:
- Direct HTTP endpoint can expose all tools without HTTP auth contract used by MCP HTTP.

Root cause:
- `rest-gateway.ts` directly maps `ALL_TOOL_DEFINITIONS` and invokes handlers with no auth/toolset filtering.

Evidence:
- [`packages/mcp-server/src/rest-gateway.ts#L13`](packages/mcp-server/src/rest-gateway.ts)
- [`packages/mcp-server/src/rest-gateway.ts#L45-L59`](packages/mcp-server/src/rest-gateway.ts)

Implementation direction:
- Option A: deprecate/remove REST gateway if unsupported.
- Option B: retrofit gateway with the same toolset + auth policy model as `http-server.ts`.
- At minimum, restrict tool exposure to configured safe toolsets.

Acceptance criteria:
- REST path cannot bypass policy compared to main HTTP server.

### F5. Runtime contract claims circuit breaker, but runtime does not use it

Severity: High (Trust-contract mismatch)
Impact:
- Docs/catalog claim resilience behavior not currently guaranteed.

Root cause:
- `CircuitBreaker` class exists and is exported, but shared HTTP request path does not wrap calls with breaker instances.

Evidence:
- Circuit breaker implementation: [`packages/shared/src/circuit-breaker.ts`](packages/shared/src/circuit-breaker.ts)
- Runtime contract claim: [`packages/mcp-server/src/tools/catalog.ts#L1333-L1338`](packages/mcp-server/src/tools/catalog.ts)
- Production notes claim: [`docs/production-notes.md#L87-L95`](docs/production-notes.md)

Implementation direction:
- Integrate breaker per API family inside `http-client.ts` around `fetch` execution.
- Track breaker metrics/state optionally in logs.
- Ensure breaker behavior aligns with documented thresholds/timeouts.

Acceptance criteria:
- Failing upstream calls open breakers per API family and fail fast when open.
- Runtime docs/catalog claims are true in execution.

### F6. Import-time artifact store side effect creates unnecessary filesystem coupling

Severity: High (operational friction)
Impact:
- Merely importing artifact module touches filesystem/DB by default.
- Scripts importing built catalog can trigger state creation unexpectedly.

Root cause:
- `let artifactStoreSingleton = new ArtifactStore();` at module load time.

Evidence:
- [`packages/mcp-server/src/tools/artifacts.ts#L267`](packages/mcp-server/src/tools/artifacts.ts)

Implementation direction:
- Lazy-init singleton on first use.
- Keep explicit close/reset semantics unchanged.

Acceptance criteria:
- No artifact DB creation on cold import only.
- DB created only when artifact operations actually execute.

### F7. Persistence path strategy is inconsistent for container deployments

Severity: High
Impact:
- State split between container volume and host home paths is confusing and brittle.
- Potential data loss or hidden state in containerized environments.

Root cause:
- Compose sets `SG_APIS_ARTIFACT_DB_PATH`, but cache/keys/config/data.gov index still default to `~/.sg-apis`.

Evidence:
- Compose artifact path: [`compose.yaml#L15`](compose.yaml)
- Cache path default: [`packages/shared/src/cache.ts#L12`](packages/shared/src/cache.ts)
- Keystore path default: [`packages/shared/src/keystore.ts#L11`](packages/shared/src/keystore.ts)
- Config path default: [`packages/shared/src/config/index.ts#L37`](packages/shared/src/config/index.ts)
- data.gov index path default: [`packages/mcp-server/src/apis/datagov/client.ts#L58-L61`](packages/mcp-server/src/apis/datagov/client.ts)
- Config tool hardcoded path language: [`packages/mcp-server/src/tools/config-tools.ts#L37`](packages/mcp-server/src/tools/config-tools.ts)

Implementation direction:
- Introduce one canonical state root env var (for example `SG_APIS_STATE_DIR`).
- Derive default paths for cache/keys/config/index/artifacts from that root.
- Keep current behavior as fallback for backwards compatibility.

Acceptance criteria:
- All persistent state resolves under one configured root in container mode.
- Production docs and compose config describe one coherent strategy.

### F8. Rate limiter can underflow tokens under contention; no direct tests

Severity: Medium-High
Impact:
- Potential negative token behavior and burst inaccuracies under concurrency.

Root cause:
- `acquire()` decrements after sleep without loop/re-check lock semantics.

Evidence:
- [`packages/shared/src/rate-limiter.ts#L16-L26`](packages/shared/src/rate-limiter.ts)
- No direct tests found for limiter behavior under concurrency.

Implementation direction:
- Replace with looped token-bucket acquisition logic that rechecks after wait.
- Add deterministic tests for concurrent `acquire()` calls.

Acceptance criteria:
- Tokens never go negative.
- Concurrent calls honor configured effective rate.

### F9. Query classifier is heavily regex/hardcoded and will be harder to scale safely

Severity: Medium
Impact:
- New workflow additions increase classifier fragility and false route risks.

Root cause:
- Large hardcoded extraction + pattern layer in single classifier module.

Evidence:
- [`packages/mcp-server/src/router/classifier.ts`](packages/mcp-server/src/router/classifier.ts)

Implementation direction:
- Keep deterministic design, but modularize classifier rule groups by domain/workflow.
- Add domain-specific fixtures and decision-table tests for regressions.
- Add observability around unknown/ambiguous prompts.

Acceptance criteria:
- Adding workflows no longer requires brittle edits in one mega-classifier area.
- Classifier behavior remains deterministic and test-covered.

### F10. Macro brief includes low-confidence fallback labels

Severity: Medium (product clarity)
Impact:
- Output quality and trust are reduced when labels degrade to generic text.

Root cause:
- Fallback text uses `"Banking metric"` in key output locations.

Evidence:
- [`packages/mcp-server/src/tools/brief-tools.ts#L1460`](packages/mcp-server/src/tools/brief-tools.ts)
- [`packages/mcp-server/src/tools/brief-tools.ts#L1485`](packages/mcp-server/src/tools/brief-tools.ts)

Implementation direction:
- Improve fallback labeling (for example key-based explicit fallback + source context).
- Ensure summary/evidence semantics stay analyst-readable.

Acceptance criteria:
- No ambiguous generic label in key brief summary fields.

### F11. README policy conflict with current parity tooling

Severity: Medium
Impact:
- User-imposed rule says do not edit `README.md`, but parity scripts currently enforce many README snippets.

Root cause:
- `check-docs-parity.mjs` and `check-live-surface.mjs` hard-target `README.md`.

Evidence:
- [`scripts/check-docs-parity.mjs#L44-L68`](scripts/check-docs-parity.mjs)
- [`scripts/check-docs-parity.mjs#L197-L199`](scripts/check-docs-parity.mjs)
- [`scripts/check-live-surface.mjs#L11`](scripts/check-live-surface.mjs)
- `README2.md` does not exist currently.

Implementation direction:
- Create `README2.md`.
- Update parity scripts to allow `README2.md` as canonical mutable doc while leaving `README.md` untouched.
- Decide whether both files must be in sync automatically.

Acceptance criteria:
- Documentation updates can pass verify without editing `README.md`.

## 5. Product Perspective Summary

Current value proposition is real and defensible:
- Strong for Singapore-focused agent builders needing deterministic contracts.
- Good depth in diligence/property/transport/environment workflows.
- Strong bounded approach avoids fake general planning.

Current limits:
- Operational trust gaps (CI, release docs, circuit-breaker mismatch) weaken enterprise confidence.
- Some runtime/deployment behavior is harder than it needs to be (state path fragmentation, import side effects).
- Breadth can expand further in high-demand workflows while preserving determinism.

High-value product expansion themes (without violating bounded philosophy):
- Deeper procurement and compliance workflows.
- Better healthcare and education operational coverage.
- More recipe/playbook guidance to reduce onboarding cost.
- Better reliability messaging that is actually enforced by runtime behavior.

## 6. Prioritized Implementation Program

## Phase 0: Policy Alignment + Documentation Substrate

Objective:
- Enforce user’s repository workflow requirements before further changes.

Tasks:
- Create `README2.md` as mutable equivalent for future README-intended edits.
- Update docs parity and live-surface scripts to include `README2.md` pathways.
- Preserve `README.md` unchanged.

Files likely touched:
- `README2.md` (new)
- `scripts/check-docs-parity.mjs`
- `scripts/check-live-surface.mjs`
- Optional: docs explaining README2 policy.

## Phase 1: Release Integrity And CI Reliability

Objective:
- Restore trusted engineering gate.

Tasks:
- Fix missing changelog handling in script checks.
- Decide and implement changelog policy behavior.
- Add CI triggers (`push`, `pull_request`) and branch scoping.
- Resolve release doc/workflow mismatch.

Files likely touched:
- `scripts/check-live-surface.mjs`
- `scripts/check-docs-parity.mjs`
- `.github/workflows/ci.yml`
- `docs/release.md`
- Possible new `.github/workflows/publish.yml` if docs intent retained.

## Phase 2: Runtime Security And Reliability Hardening

Objective:
- Remove policy bypasses and make runtime claims true.

Tasks:
- REST gateway auth/toolset parity or deprecation.
- Integrate circuit breaker in HTTP client path.
- Fix rate limiter under concurrency and add tests.
- Lazy-init artifact store.

Files likely touched:
- `packages/mcp-server/src/rest-gateway.ts`
- `packages/shared/src/http-client.ts`
- `packages/shared/src/circuit-breaker.ts` (if API changed)
- `packages/shared/src/rate-limiter.ts`
- `packages/shared/src/__tests__/...` new limiter tests
- `packages/mcp-server/src/tools/artifacts.ts`

## Phase 3: State Path Unification And Ops Clarity

Objective:
- Make persistence behavior explicit and container-safe.

Tasks:
- Add `SG_APIS_STATE_DIR` resolver utility.
- Refactor cache/keystore/config/datagov/artifacts path creation to use shared root.
- Update compose + docs accordingly.
- Ensure `sg_config_set` description/path text is accurate after change.

Files likely touched:
- `packages/shared/src/cache.ts`
- `packages/shared/src/keystore.ts`
- `packages/shared/src/config/index.ts`
- `packages/mcp-server/src/apis/datagov/client.ts`
- `packages/mcp-server/src/tools/artifacts.ts`
- `packages/mcp-server/src/tools/config-tools.ts`
- `compose.yaml`
- `docs/production-notes.md`
- `docs/deployment.md`
- `docs/api-auth-guide.md` if path expectations are referenced

## Phase 4: Product Quality Refinements

Objective:
- Improve user-facing trust and clarity.

Tasks:
- Improve macro brief fallback labels.
- Add classifier modularization scaffold and route-confidence diagnostics.
- Add tests for new classification branches and blocked/unsupported messaging quality.

Files likely touched:
- `packages/mcp-server/src/tools/brief-tools.ts`
- `packages/mcp-server/src/router/classifier.ts`
- `packages/mcp-server/src/router/*` (new helper modules)
- `packages/mcp-server/src/tools/__tests__/...`
- `packages/mcp-server/src/router/__tests__/...`

## 7. Detailed Work Packages (Implementation-Ready)

Each work package includes exact intent, file targets, validation, and done criteria.

### WP-1: Fix verify break from missing changelog

Goal:
- Make verify deterministic and policy-driven for changelog handling.

Implementation:
- In `scripts/check-live-surface.mjs`, build candidate path arrays dynamically by checking file existence first.
- In `scripts/check-docs-parity.mjs`, gate changelog snippet checks behind existence check, or fail with clear policy error.
- Add explicit message like: `CHANGELOG.md required for release checks` if policy is strict.

Validation:
- Run `npm run verify` from clean tree.
- Confirm failure mode is explicit policy error or success, not ENOENT.

Done criteria:
- No raw filesystem ENOENT from changelog checks.

### WP-2: CI auto-trigger coverage

Goal:
- Ensure automated verification on collaboration paths.

Implementation:
- Update `.github/workflows/ci.yml` `on:` block to include:
  - `push`
  - `pull_request`
  - optional `workflow_dispatch` retention.
- Optional path filters if needed.

Validation:
- YAML lint parse check.
- Trigger test via branch push/PR.

Done criteria:
- CI no longer manual-only.

### WP-3: Release workflow/doc alignment

Goal:
- Remove operator ambiguity.

Implementation path A:
- Implement `publish.yml` exactly as release docs claim.

Implementation path B:
- Update `docs/release.md` to current actual workflow model and planned publish path.

Validation:
- All referenced workflow files exist and match docs.

Done criteria:
- No docs references to missing workflow files.

### WP-4: REST gateway policy parity

Goal:
- Prevent bypass of configured auth/toolsets.

Implementation:
- Refactor `rest-gateway.ts` to resolve enabled tool definitions via same selection logic used in server (`isToolEnabled` + configured toolsets).
- Add optional auth middleware or clearly restrict to local/dev mode with explicit warning and safety defaults.
- Consider removing gateway if unsupported to minimize attack surface.

Validation:
- Unit/integration check ensures ops tools are not callable when excluded.
- Unauthorized access returns proper errors in protected mode if auth integrated.

Done criteria:
- REST behavior cannot expose more than configured policy.

### WP-5: Circuit breaker integration in shared HTTP client

Goal:
- Make documented resilience behavior real.

Implementation:
- In `packages/shared/src/http-client.ts`, maintain breaker instances keyed by `apiName`.
- Wrap each outbound fetch attempt path with `breaker.execute(...)` semantics.
- Ensure retry and breaker semantics coexist cleanly (no double-counting failures).
- Add logs for breaker transitions.

Validation:
- Add tests that force repeated failures and verify open -> half-open -> closed behavior.

Done criteria:
- Breaker state transitions observable and effective.

### WP-6: Rate limiter concurrency correctness

Goal:
- Eliminate token underflow and inaccurate throttling under load.

Implementation:
- Replace `acquire()` single wait-decrement pattern with loop:
  - refill
  - if token available decrement and return
  - else wait and retry
- Optional mutex/queue if deterministic ordering is needed.

Validation:
- Add concurrency tests in shared package.
- Confirm no negative token counts and expected wall-time for parallel requests.

Done criteria:
- Stable behavior under concurrent acquisition.

### WP-7: Artifact store lazy initialization

Goal:
- Remove import-time side effects.

Implementation:
- Replace eager singleton with `getArtifactStore()` lazy getter.
- Ensure `close`, `resetArtifactStoreForTests`, and methods handle uninitialized state.

Validation:
- Script imports should not create DB files unless artifact path is actually used.
- Existing artifact tests continue to pass.

Done criteria:
- No DB side effect on module import alone.

### WP-8: Unified state directory model

Goal:
- One coherent persistence story across local and container deployments.

Implementation:
- Add shared resolver utility (for example `resolveStatePath(fileName)`):
  - root from `SG_APIS_STATE_DIR` if set
  - fallback `~/.sg-apis`
- Refactor cache/keystore/config/datagov index/artifact path resolution to use resolver.
- Update compose to set `SG_APIS_STATE_DIR=/var/lib/sg-apis` and simplify per-file overrides.

Validation:
- Start server in container-like env and confirm all state files land under one directory.
- Ensure backward compatibility when env var is absent.

Done criteria:
- No mixed hidden state locations in production mode.

### WP-9: Macro brief output clarity

Goal:
- Improve analyst-facing clarity.

Implementation:
- Replace generic fallback labels with deterministic key-based naming or explicit unavailable labels.
- Ensure summary/evidence fields remain consistent with schema.

Validation:
- Update golden outputs and tests that assert labels.

Done criteria:
- No ambiguous `Banking metric` style label where specific context can be shown.

### WP-10: Classifier maintainability and observability

Goal:
- Keep deterministic behavior while improving extension safety.

Implementation:
- Split extractor/rule groups into domain modules (geospatial, dataset, diligence, civic, macro).
- Preserve public behavior first, then add incremental rule improvements.
- Add test matrix for representative blocked/unsupported/complete prompts.

Validation:
- Existing query tests pass.
- New tests cover ambiguous/edge prompts.

Done criteria:
- Classifier changes are localized and test-driven.

## 8. Test Strategy By Phase

Baseline command set after each phase:
- `npm run lint`
- `npm run build`
- `npm run diagnostics`
- `npm test`
- `npm run verify`

Additional targeted tests to add:
- Rate limiter concurrent acquisition tests.
- Circuit breaker state transition tests.
- REST gateway policy exposure tests.
- Path resolver tests for state dir behavior.
- Query classifier rule unit tests for new modularized rules.

## 9. Risk Register

1. Behavior regressions in routing if classifier refactor is done too broadly.
Mitigation:
- Preserve behavior first with snapshot/fixture tests before logic improvements.

2. Circuit breaker integration could interact poorly with retries.
Mitigation:
- Explicitly test timeout/retry/failure sequences and define breaker failure-count policy.

3. State path migration can strand existing local state.
Mitigation:
- Keep fallback behavior and document migration path.

4. Docs parity may fail if README2 policy not reflected in scripts.
Mitigation:
- Update scripts before broad doc updates.

## 10. Required Workflow Constraints (Must Follow)

These constraints are mandatory for all subsequent implementation passes.

### 10.1 Atomic Git Commit Requirement

For every change set:
- Commits must be atomic and rollback-friendly.
- Prefer one logical change per commit.
- Prefer one file per commit where practical and not harmful.
- Commit messages must be 5 to 10 words.

Recommended operational pattern:
- Edit one file or one tightly-coupled file pair.
- Run the smallest relevant validation.
- Commit immediately with 5-10 word message.
- Repeat.

Message examples (all 5-10 words):
- `Guard changelog checks when file is absent`
- `Enable CI on push and pull requests`
- `Lazy initialize artifact store to avoid side effects`
- `Fix rate limiter token underflow loop`
- `Add concurrent limiter behavior regression tests`

### 10.2 README Edit Constraint

Hard rule:
- Do not modify `README.md`.

Documentation policy for README-intended changes:
- Put all such updates into `README2.md`.
- If scripts require README parity, adapt scripts so `README2.md` can be the mutable tracked doc while preserving `README.md` unchanged.

Required first step before doc-heavy changes:
- Create `README2.md` and establish parity-script behavior for it.

## 11. Suggested First Execution Sequence For Next Agent

Order below minimizes risk and restores trust gates first.

1. Implement README2 + parity script support.
2. Fix changelog existence handling in verify scripts.
3. Enable CI push/PR triggers.
4. Align release documentation/workflow reality.
5. Fix artifact lazy init.
6. Fix rate limiter and add tests.
7. Integrate circuit breaker into shared HTTP path.
8. Harden or retire REST gateway.
9. Implement unified `SG_APIS_STATE_DIR` resolver and update docs/compose.
10. Improve macro brief fallback labels and classifier maintainability.

## 12. Explicit Current Status Snapshot

As of 2026-04-03 audit completion:
- Working tree: clean before this handoff file creation.
- `npm run diagnostics`: pass.
- `npm test`: pass (286/286).
- `npm run verify`: fails due missing `CHANGELOG.md` handling in scripts.
- `README2.md`: does not yet exist.

This document is intentionally verbose and operationally specific so a new coding agent can execute directly without re-auditing.
