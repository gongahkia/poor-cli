# Release Guide

## What This Covers

This repo publishes two npm packages:

- `@sg-apis/shared`
- `sg-apis-mcp`

The publish workflow is tag-driven and runs from `.github/workflows/publish.yml`.

## Before You Tag

1. Update `CHANGELOG.md`.
2. Bump versions in:
   - `packages/shared/package.json`
   - `packages/mcp-server/package.json`
3. Keep the dependency edge aligned:
   - `packages/mcp-server/package.json` should depend on the same published `@sg-apis/shared` version.
4. Run:

```bash
npm install
npm run verify
```

5. Run the live validation pass:

```bash
npm run quick-start
```

If the build already exists and you only want the smoke flow:

```bash
npm run test:smoke:live
```

## Publish Order

The workflow publishes in this order:

1. `@sg-apis/shared`
2. `sg-apis-mcp`
3. registry smoke against the public npm registry

That order matters because `sg-apis-mcp` installs `@sg-apis/shared` from npm.

## Tag And Push

Create a semver tag that matches the package version:

```bash
git tag v0.1.0
git push origin v0.1.0
```

The publish workflow only runs on pushed tags matching `v*`.

## What The Publish Workflow Verifies

The workflow runs:

- `npm ci`
- `npm run verify`
- `npm publish` for `@sg-apis/shared`
- `npm publish` for `sg-apis-mcp`
- `npm run test:smoke:registry`

The registry smoke step waits for npm propagation, installs both published packages into a temporary directory, performs an MCP handshake, reads the public workflow and recipe resources, and calls representative live no-auth direct tools and routed workflows. It does not validate credential-gated upstreams; use `npm run test:smoke:live` separately when you need that proof.

## Post-Release Checks

After the workflow is green, verify:

```bash
npm view @sg-apis/shared version
npm view sg-apis-mcp version
```

You should also sanity-check:

- `npx -y sg-apis-mcp`
- one MCP client configuration using the published package
- the README install instructions if this is the first public release

## Rollback Notes

Assume npm rollback is patch-forward, not history erasure.

- If the package is already public, prefer a quick follow-up release over relying on unpublish.
- If only one workspace package published successfully, publish the missing dependent fix rather than forcing consumers onto mismatched versions.
- If the registry smoke job fails after publish, treat the release as suspect and ship a new tagged fix as soon as the root cause is known.
