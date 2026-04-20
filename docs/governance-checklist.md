# Governance Checklist

## Release Gate Checklist

Use this checklist before any tagged release.

1. `npm run release:preflight` passes with no skipped policy checks.
2. `node ./scripts/check-governance.mjs` passes.
3. `docs/ownership-matrix.json` has named owners for every API family and workflow in the built catalog.
4. No unresolved high-severity vulnerability is accepted for release.
5. Brief schema changes include backward-compatibility notes and migration notes where needed.
6. Benchmark, ecosystem, and KPI dashboard evidence snapshots are generated for the release window.
7. Known issues and incident notes are updated for new risk posture.

## Change Admission Rules

1. No new API family without a documented use case, maintainer owner, and test plan.
2. No brief schema expansion without backward-compatibility notes.
3. No release without passing verify, smoke, and policy checks.
4. No unresolved high-severity vulnerability at release time.
5. Every roadmap item must map to at least one KPI.
