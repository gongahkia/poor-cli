# KPI Threshold Policy

The KPI dashboard supports policy-driven status and alerting from a threshold config.

## Default Behavior

If no threshold file is provided, `npm run kpis:dashboard` uses built-in defaults.

## Configure a Policy File

1. Copy [config/kpi-thresholds.example.json](../config/kpi-thresholds.example.json) to `config/kpi-thresholds.json`.
2. Adjust thresholds for your deployment lane.
3. Regenerate the dashboard:

```bash
npm run kpis:dashboard
```

Override path options:

- CLI: `npm run kpis:dashboard -- --thresholds /absolute/path/to/policy.json`
- Env: `SG_APIS_KPI_THRESHOLDS_PATH=/absolute/path/to/policy.json`

## Policy Fields

- `installability.requireVerifyPassed`
- `installability.allowedRegistrySmokeStatuses`
- `installability.minInstallSuccessRatePct`
- `slo.maxBreachCount`
- `slo.maxWarningCount`
- `docs.maxDriftDefects`
- `onboarding.maxMeanTimeToFirstWorkflowMinutes`
- `ecosystem.minSingaporeMcpRepoCount`
- `ecosystem.minStackoverflowQuestionCount`

## Output Contract

`kpi-dashboard/v1` now includes:

- `policy` (source and effective thresholds)
- `alerts` (warning and breach entries)
- `overallPolicyStatus` (`within_threshold`, `warning`, or `breach`)

`npm run release:evidence` fails by default if `overallPolicyStatus` is `breach`.

Emergency override:

```bash
npm run release:evidence -- --allow-kpi-breach
```
