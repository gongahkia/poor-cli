# SDK Publish Readiness

This document tracks the publish decision for `@swee-sg/sdk`.

## Success Definition

- SDK API scope and types are documented.
- The package exists as a workspace package with a TypeScript build.
- `npm pack --dry-run` can be run through a root script.
- Publish blockers are explicit rather than implicit.

## API Scope

The first SDK version is a thin typed REST client for Dude Cloud and self-hosted Dude gateways:

- `DudeClient` and `createDudeClient`;
- `health()` and `listTools()` for gateway discovery;
- `callTool<T>()` for stable `sg_*` tool contracts;
- `businessDossier()` and `query()` convenience methods with shared-schema validation;
- exported types for brief artifacts, query outcomes, gateway health, and typed API errors.

The SDK deliberately does not duplicate runtime logic, source adapters, risk rules, or country-pack behavior. Those remain in Dude MCP and `@swee-sg/shared`.

## Dry-Run Command

```bash
npm run build
npm run sdk:pack:dryrun
```

Observed on 2026-05-17: `npm run sdk:pack:dryrun` completed successfully for `@swee-sg/sdk@0.1.0`. The dry-run tarball was `dude-sdk-0.1.0.tgz`, approximately 6.2 kB packed and 21.1 kB unpacked.

The dry-run includes only:

- `dist/**`;
- `README.md`;
- package metadata.

## Publish Blockers

| Blocker | Status |
| --- | --- |
| npm scope | Confirm that the maintainer account controls or can create the public `@dude` scope before publishing. |
| hosted auth contract | Finalize bearer-token issuance, rate limits, and workspace scoping before documenting hosted SDK production use. |
| semantic version policy | Align SDK semver with `@swee-sg/shield` and shared schema versions before the first public release. |
| public examples | Add a hosted/self-host integration example once the auth contract is stable. |

## Publish Decision

Do not publish yet. The package is ready for local workspace use and npm pack verification, but public npm publication should wait for npm-scope confirmation and hosted auth finalization.
