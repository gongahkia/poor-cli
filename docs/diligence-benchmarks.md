# Diligence edge-case benchmarks

`benchmarks/diligence-edge-cases.json` catalogs 50 Singapore business-dossier edge cases for product regression testing. The set covers exact UEN lookups, missing identifiers, sector-module selection, source outages, partial coverage, risk-rule metadata, exports, bulk summaries, skipped-module follow-ups, country-pack boundaries, and public-status reporting.

The benchmark is intentionally public-data only. It uses synthetic entities unless a case is describing a source boundary or artifact behavior. The fixtures must not accuse any real company or person of wrongdoing.

## Verification

Run:

```sh
node ./scripts/check-diligence-benchmarks.mjs
```

`npm run verify` also runs the benchmark fixture check. `npm run benchmarks:snapshot` includes the fixture count and limitations in `artifacts/benchmarks/latest.json` so scheduled status evidence can show whether the benchmark set is present.

## False-positive limits

Name similarity can over-match common company names when no UEN is supplied. Sector hints can select irrelevant modules for diversified entities. Expiry-date fixtures can also become stale if upstream formats change.

## False-negative limits

Public-only datasets can omit paid, private, authentication-gated, or recently changed records. A passing benchmark verifies product behavior and evidence handling; it does not certify upstream completeness, legal status, or compliance risk.
