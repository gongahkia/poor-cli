# Packaging Smoke Confirmation - 2026-03-30

## Local Verification Evidence

- Command: `npm run verify`
- Result: `passed`
- Packaging smoke stage executed (not skipped):
  - `==> packaging smoke`
  - `npm run test:smoke:packaging`
  - `packaging smoke test passed`

## CI / Release Runner Wiring

- Workflow: `.github/workflows/ci.yml`
- Trigger mode: `workflow_dispatch` (manual), so release operators can run the same gate when runner billing is available
- `Verify repository` step runs `npm run verify` without `SG_APIS_SKIP_PACKAGING_SMOKE=1`.
- This ensures packaging smoke executes inside the CI runner context where npm cache and child-process permissions are available.

## Expected Release Context Behavior

Packaging smoke remains part of the default verify gate in CI and should block merges or releases whenever package contents regress.
