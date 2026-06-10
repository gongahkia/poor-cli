# Singapore risk rules pack

The Singapore business-dossier risk rules live in `rules/sg-risk-rules.yml`.

The current pack is `sg-risk-rules/v1`, version `2026.05`, reviewed on `2026-05-17`. It covers deterministic public-data signals only:

- inactive ACRA entity status
- no ACRA match after an ACRA lookup
- expired BCA builder licence
- expired BCA contractor registration
- expired HSA health-product licence
- cross-source name divergence
- partial module coverage
- no module matches after searched modules run
- selected modules that could not run because required identifiers were missing

Each `sg_business_dossier` response exposes the active rule pack under `records.quality.riskRules` so downstream exports and analyst memos can cite the rule version that produced `riskFlags`.

## Limits

Risk flags are review signals, not findings of wrongdoing. The pack intentionally avoids adverse-media inference, beneficial-ownership inference, legal conclusions, credit decisions, and tax advice. Analysts must evaluate flags alongside dossier `provenance`, `freshness`, `gaps`, and `limits`.

## Updating rules

When a rule changes, update:

- `rules/sg-risk-rules.yml`
- `packages/mcp-server/src/diligence/risk-rules.ts`
- `packages/mcp-server/src/diligence/__tests__/risk-rules.test.ts`

Then run `npm test -- packages/mcp-server/src/diligence/__tests__/risk-rules.test.ts` and the affected business-dossier tests.
