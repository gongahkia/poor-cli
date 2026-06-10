# Registry Smoke Baseline - 2026-03-30

## Command

`npm run test:smoke:registry`

## Environment

- Date: 2026-03-30
- Runtime: local repository workspace
- Registry target: npm public registry

## Outcome

- Exit code: `1`
- Status: `expected pre-publish failure`

## Key Output Signals

- `npm error 404 Not Found - GET https://registry.npmjs.org/@sg-apis%2fshared - Not found`
- `Timed out waiting for @sg-apis/shared@0.1.0 to become visible in npm.`

## Interpretation

The registry smoke flow currently assumes release-published package versions are visible on npm.
This baseline confirms the script behavior after the latest reliability/docs updates and documents the expected failure mode before publication.
