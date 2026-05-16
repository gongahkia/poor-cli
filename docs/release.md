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

### Governance Checklist

Before tagging, run the explicit governance policy check (this is also part of `npm run verify`):

```bash
node ./scripts/check-governance.mjs
```

Confirm:

- `docs/ownership-matrix.json` covers every API family and workflow in the built catalog.
- `docs/governance-checklist.md` and `docs/deprecation-policy.md` are current.
- `docs/schema-versioning.md` and `CHANGELOG.md` are current for public schema changes.
- quarterly reporting template and known-issues notes are current for the release window.

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

Do not treat the public smoke pass as release evidence; publish and deploy readiness still requires `npm run test:smoke:live`.

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
