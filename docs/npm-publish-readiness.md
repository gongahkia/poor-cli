# npm Publish Readiness

This page tracks the `@swee-sg/shield` public npm release path and the exact blocker before the first registry publication.

Observed at: 2026-05-17 09:20 Asia/Singapore.

## Definition Of Success

| Requirement | Status | Evidence |
| --- | --- | --- |
| Rename/package MCP server as `@swee-sg/shield` without breaking existing local names. | Fulfilled | `packages/mcp-server/package.json` uses `name: "@swee-sg/shield"` and keeps `sg-apis-mcp` as a compatibility bin beside `swee-sg`. |
| Add package metadata, files, README, and release checks. | Fulfilled | `package.json` includes description, MIT license, public publish config, Node 20 engine, runtime-only `files`, package-local `README.md`, `prepublishOnly`, and package smoke coverage. |
| Run npm pack and publish dry run. | Fulfilled | `npm run release:dryrun` packs `@swee-sg/shared` and `@swee-sg/shield`, installs both tarballs into a temp project, boots the `swee-sg` bin, and probes the MCP surface. `npm publish --workspace packages/mcp-server --access public --dry-run` remains the npm registry dry-run. |
| Publish initial semver version or document exact blocker. | Blocked outside repo | `npm view @swee-sg/shared version --json` and `npm view @swee-sg/shield version --json` returned npm E404, so no public version exists yet. Real publication requires npm authentication and publish access for the `@swee-sg` scope through `NPM_TOKEN` or an interactive npm account. |

## Current Package Surface

- Package: `@swee-sg/shield`
- Version: `0.1.0`
- Primary executable: `swee-sg`
- Policy/audit executable: `swee-shield`
- Compatibility executable: `sg-apis-mcp`
- CLI helper: `sg-data`
- Runtime files: `dist`, `assets`, and `openapi.json`
- Public release order: `@swee-sg/shared`, then `@swee-sg/shield`, then GHCR image and registry smoke.

## Local Evidence Commands

Run these before tagging or manually dispatching the publish workflow:

```bash
npm install
npm run build
npm run test:smoke:packaging
npm run release:dryrun
npm publish --workspace packages/mcp-server --access public --dry-run
```

The dry-run command does not reserve the package name or publish to npm. It only proves that npm can build the package manifest and tarball for the current workspace.

## Exact Publication Blocker

The repository cannot complete `npm publish` from source alone. The first public release needs:

- an npm organization or scope owner for `@swee-sg`;
- an npm automation token stored as `NPM_TOKEN` in GitHub Actions, or an authenticated maintainer running the publish workflow manually;
- confirmation that `@swee-sg/shared@0.1.0` is published before `@swee-sg/shield@0.1.0`, because `@swee-sg/shield` depends on the published shared package;
- a `v0.1.0` tag or manual `.github/workflows/publish.yml` dispatch after release evidence is green.

## Release Checklist

1. Confirm `npm view @swee-sg/shared version` and `npm view @swee-sg/shield version` still return either E404 for first publish or the expected previous version for patch-forward release.
2. Run `npm run release:preflight`.
3. Confirm `NPM_TOKEN` has public publish rights for both workspaces.
4. Create and push the semver tag matching both package versions.
5. Watch `.github/workflows/publish.yml` until npm publish, GHCR publish, container smoke, and registry smoke pass.
6. Verify `npx -y @swee-sg/shield` and update README install language from readiness to released status only after npm resolves the package publicly.

## Limits

- This page is release-readiness evidence, not proof that npm has accepted the package.
- The dry run does not validate npm scope ownership, package-name availability beyond the observed E404, 2FA policy, provenance signing, or organization billing settings.
- Do not represent `@swee-sg/shield` as published until `npm view @swee-sg/shield version` returns the expected semver version from the public registry.
