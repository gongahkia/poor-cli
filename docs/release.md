# Release Guide

## What This Covers

This repo publishes two npm packages:

- `@dude/shared`
- `@dude/mcp`

It also publishes:

- `server.json` registry metadata at the repo root
- `ghcr.io/gongahkia/dude-mcp` as the container image
- `packages/mcp-server/openapi.json` as the checked-in REST artifact

The publish workflow is tag-driven from `.github/workflows/publish.yml`. It runs on `v*` tags and supports `workflow_dispatch` for controlled manual execution.

## Before You Tag

Repository secrets required by `.github/workflows/publish.yml`:

- `NPM_TOKEN` with publish access for `@dude/shared` and `@dude/mcp`

1. Update `CHANGELOG.md`, including `Schema Changes`, `Breaking Changes`, or `Deprecations` when public contracts change.
2. Bump versions in:
   - `packages/shared/package.json`
   - `packages/mcp-server/package.json`
3. Keep the dependency edge aligned:
   - `packages/mcp-server/package.json` should depend on the same published `@dude/shared` version.
4. Keep metadata in sync:
   - `server.json.version` should match `packages/mcp-server/package.json`
   - `packages/mcp-server/package.json#mcpName` should match `server.json.name`
   - `packages/mcp-server/openapi.json` should match `scripts/generate-openapi.mjs`
   - `server.json.remotes[0].url` must match the real canonical public `/mcp` URL before release
5. Run:

```bash
npm install
npm run release:preflight
```

`release:preflight` executes verify, fresh benchmark/ecosystem/KPI artifact generation, and release evidence checks in one pass.

The release preflight and CI both run the production dependency audit gate:

```bash
npm run security:audit:prod
```

The gate runs `npm audit --omit=dev`. High and critical production findings fail unless they are fixed or explicitly allowlisted with a rationale. Moderate findings also require a tracking or allowlist entry so they do not disappear into release noise. Allowlist entries live in `config/npm-audit-allowlist.json` and must include the package, severity, advisory ID or title, rationale, and tracking reference.

### Governance Checklist

Before tagging, run the explicit governance policy check (this is also part of `npm run verify`):

```bash
node ./scripts/check-governance.mjs
```

Confirm:

- `docs/ownership-matrix.json` covers every API family and workflow in the built catalog.
- `docs/governance-checklist.md` and `docs/deprecation-policy.md` are current.
- `docs/schema-versioning.md` and `CHANGELOG.md` are current for public schema changes.
- quarterly reporting template and troubleshooting notes are current for the release window.
- hosted paid releases do not enable ACRA-derived commercial enrichment unless [docs/acra-licensing-track.md](./acra-licensing-track.md) records an approved API Marketplace, authorised ISP, partner, or sub-licence path.

Generate release-window evidence artifacts manually (if not using `release:preflight`):

```bash
npm run benchmarks:snapshot
npm run ecosystem:snapshot
npm run kpis:dashboard
npm run release:evidence
```

If your release lane uses custom KPI thresholds, set `SG_APIS_KPI_THRESHOLDS_PATH` before generating KPI and evidence artifacts.

For quarterly governance updates, generate a report draft from the latest artifacts:

```bash
npm run quarterly:report
```

### npm Publish Readiness

Before the first public npm release, review [npm-publish-readiness.md](./npm-publish-readiness.md). It records the `@dude/mcp` definition of success, local dry-run evidence, and the current external blocker.

For package-level proof without touching the registry:

```bash
npm run test:smoke:packaging
npm run release:dryrun
npm publish --workspace packages/mcp-server --access public --dry-run
```

6. Run the live validation pass:

```bash
npm run quick-start
```

If the build already exists and you only want the smoke flow:

```bash
npm run test:smoke:live
```

For local onboarding without credentials, run:

```bash
npm run test:smoke:public
```

The CI workflow runs the same no-credential path as `Run public no-credential smoke` so first-run public upstream failures are visible without reading the broader verify log.

Do not treat the public smoke pass as release evidence; publish and deploy readiness still requires `npm run test:smoke:live`.

## Hosted Commercial Data Gates

Before a hosted paid release or beta:

- ACRA-derived paid enrichment is blocked unless [ACRA licensing track](./acra-licensing-track.md) records an approved ACRA API Marketplace, authorised ISP, partner, or sub-licence path.
- OneMap-backed redistribution is blocked until Developer Agreement rights are reviewed.
- URA-backed workflows must preserve attribution, source freshness, and any API-page-specific limits.
- FI-adjacent sales require the [MAS outsourcing readiness pack](./mas-outsourcing-readiness.md) and cannot proceed until hosted BCP, incident, subprocessor, data residency, and audit-log gaps are accepted or remediated.
- Sales/onboarding packets must include [hosted-onboarding.md](./product/hosted-onboarding.md), the DPA, PDPA/DPO readiness pack, and commercial data use review.

## Publish Order

The publish workflow runs in this order:

1. `@dude/shared`
2. `@dude/mcp`
3. `ghcr.io/gongahkia/dude-mcp`
4. registry smoke against the public npm registry

That order matters because `@dude/mcp` installs `@dude/shared` from npm.

## Tag And Push

Create a semver tag that matches the package version:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The publish workflow runs automatically on pushed tags matching `v*`. It also supports `workflow_dispatch` for manual release control.

## What The Publish Workflow Verifies

The workflow runs:

- `npm ci`
- `npm run verify`
- `npm publish` for `@dude/shared`
- `npm publish` for `@dude/mcp`
- GHCR container build and push
- `npm run test:smoke:container` against the published GHCR image
- `npm run test:smoke:registry`

Before treating a remote deployment as release-ready, also run:

```bash
SG_APIS_REMOTE_URL=https://<public-hostname>/mcp npm run test:smoke:remote
```

The registry smoke step waits for npm propagation, installs both published packages into a temporary directory, performs an MCP handshake, reads the public workflow and recipe resources, and calls representative live no-auth direct tools and routed workflows. It does not validate credential-gated upstreams; use `npm run test:smoke:live` separately when you need that proof.

CI also publishes benchmark evidence as:

- `artifacts/benchmarks/latest.json`
- `artifacts/benchmarks/history/<timestamp>.json`

Use these to track SLO trends across releases.

CI also publishes KPI dashboard evidence as:

- `artifacts/operations/latest.json`
- `artifacts/operations/history/<timestamp>.json`

`release:evidence` treats `overallPolicyStatus=breach` as release-blocking by default. Use `--allow-kpi-breach` only for an explicit emergency override.

## Post-Release Checks

After the workflow is green, verify:

```bash
npm view @dude/shared version
npm view @dude/mcp version
```

You should also sanity-check:

- `npx -y @dude/mcp`
- `docker run --rm -i ghcr.io/gongahkia/dude-mcp:latest`
- `SG_APIS_CONTAINER_IMAGE=ghcr.io/gongahkia/dude-mcp:latest npm run test:smoke:container`
- one MCP client configuration using the published package
- the README install instructions if this is the first public release

## Rollback Notes

Assume npm rollback is patch-forward, not history erasure.

- If the package is already public, prefer a quick follow-up release over relying on unpublish.
- If only one workspace package published successfully, publish the missing dependent fix rather than forcing consumers onto mismatched versions.
- If the registry smoke job fails after publish, treat the release as suspect and ship a new tagged fix as soon as the root cause is known.
