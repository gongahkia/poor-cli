# TODO - 30 March 2026

## Remaining Verification Work

- [x] Run full `npm run verify` with packaging smoke enabled in an unrestricted environment (no `SG_APIS_SKIP_PACKAGING_SMOKE=1`), since this sandbox blocks nested `npm` spawning (`spawnSync npm EPERM`).
- [x] Run `npm run test:smoke:registry` after the latest reliability/docs changes and record baseline output.
- [ ] Confirm packaging smoke behavior in CI/release runner where npm cache and child-process permissions are fully available.

## Remaining Implementation Candidates

- [x] Add optional trace/request IDs to selected structured tool outputs (not just logs) for easier cross-system correlation.
- [x] Publish a small machine-readable operations taxonomy (error codes, retryability, severity) via resource catalog.
- [x] Add profile-based toolset subsets (for example `diligence`, `property`, `ops`) to support least-privilege agent setups.
- [x] Add one backend-worker and one UI-oriented integration template demonstrating blocked/unsupported/failed handling.
- [x] Wire `sg://benchmarks` to CI-generated evidence snapshots for stronger adoption credibility.

## Broken Flows / Stubs Status

- No explicit code stubs/placeholders were found in core runtime paths during this pass.
- One constrained-environment flow remains: packaging smoke cannot run in this sandbox without skip flag.
