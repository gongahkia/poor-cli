# Corp-Services CDD Onboarding Workflow

Dude's primary product workflow is client and counterparty customer due diligence for Singapore corp-secretarial, accounting, and compliance operations teams. The first-run job is not broad research; it is a bounded public-data dossier that can be saved into a client file, reviewed by an analyst, and exported with provenance, freshness, gaps, and limits intact.

Vendor onboarding and procurement intelligence are documented as secondary lanes in [secondary-workflows.md](./secondary-workflows.md). They reuse the same evidence discipline but should not displace the CDD first-run flow.

## Target Workflow

1. **New-client intake**
   - Collect the Singapore company name or UEN from the onboarding form, email, or existing client register.
   - Record the requesting workspace, analyst, client file, and intended use.
   - Do not collect NRIC, passport, bank-account, or shareholder/controller personal data unless a workspace policy and lawful basis have already been approved.

2. **Identity resolution**
   - Run the ACRA-backed entity search first.
   - Treat exact UEN matches as the strongest public identifier.
   - Treat name-only matches as analyst-review items when multiple ACRA candidates are returned.
   - Preserve unmatched, ambiguous, or stale source states as `gaps` instead of silently dropping them.

3. **Bounded module enrichment**
   - Enrich only with modules justified by the counterparty profile or analyst selection.
   - Architecture firms: BOA plus ACRA, with optional GeBIZ procurement evidence.
   - Healthcare suppliers: HSA plus ACRA, with optional GeBIZ procurement evidence.
   - Hotel operators: HLB plus ACRA where a corporate operator can be resolved.
   - Construction or real-estate services: BCA, CEA, or BOA where identifiers and sector evidence support the lookup.

4. **Analyst review**
   - Review evidence, confidence, gaps, freshness, and limits before relying on the dossier.
   - Escalate ambiguous name matches, missing licence evidence, stale source timestamps, and unsupported ownership/control questions.
   - Record the review state and any next checks needed outside Dude.

5. **Audit-ready export**
   - Export the dossier as JSON, CSV, or PDF with the source envelope intact.
   - Include generated-at time, source provenance, source freshness, unresolved gaps, and non-advice limitations.
   - Store the dossier and export manifest in the workspace client folder when workspace storage is enabled.

## Current Modules That Support The Workflow

| Workflow need | Current support | Notes |
| --- | --- | --- |
| Company or UEN identity resolution | `sg_acra_entities`, `sg_business_dossier`, web search suggestions | ACRA is the first module for client onboarding because UEN is the durable public identifier. |
| Cross-registry dossier | `sg_business_dossier` | Returns evidence, records, confidence, gaps, provenance, freshness, and limits. |
| Sector-scoped checks | BCA, BOA, CEA, HSA, HLB, GeBIZ tools plus sector hints | Modules should be selected from official registry or analyst context, not guessed from marketing copy. |
| Analyst memo | REST gateway analyst memo endpoint | Memo generation is secondary to the bounded dossier and must retain source gaps and limits. |
| Exports | Web JSON, CSV, and PDF export helpers | Exports keep dossier fields but still need signed manifests before regulated buyer workflows. |
| Bulk intake | Web bulk diligence flow | Useful for corp-services backlogs, but workspace-backed persistence and audit logs remain roadmap work. |

## Gaps To Close Before Hosted CDD Operations

- Workspace accounts, RBAC, and cross-workspace isolation.
- Persisted dossier folders for client files.
- Immutable audit events with actor, source version, and content hash.
- Signed export manifests for downstream verification.
- Watchlists and alert rules for status changes after onboarding.
- Hosted privacy, DPA, retention, and incident-response documents.
- Hosted PDPA notification, DPO, privacy, retention, and DPIA readiness controls in [privacy-dpo-readiness.md](../privacy-dpo-readiness.md).
- Licensed or authorised-partner path for any paid redistribution of ACRA-derived commercial diligence outputs.
- OneMap and URA commercial-use controls in [commercial-data-use.md](../commercial-data-use.md) must remain satisfied before hosted paid workflows rely on those sources.

## In Scope

- Singapore public-registry-backed entity and sector checks.
- Bounded CDD onboarding support for corp-secretarial and accounting workflows.
- Evidence-first dossiers with provenance, freshness, gaps, and limits.
- Analyst-review handoff that states what the public sources did and did not show.
- Self-host and local workflows that do not imply proprietary data access.

## Out Of Scope

- Legal, tax, accounting, credit, investment, or licensed compliance advice.
- Beneficial-ownership, shareholder, director, subsidiary, or control-graph inference from missing public data.
- Claims that a counterparty is safe, approved, sanctioned-free, conflict-free, or risk-free.
- Paid redistribution of restricted upstream data unless the relevant licence, authorised partner, or sub-licence path is in place.
- General market research, reputation scoring, or open-ended web investigation.

## First-Run Product Copy

Use this positioning consistently in the web app and docs:

> Client CDD onboarding for Singapore corp-services teams.

Supporting copy should say that Dude turns a Singapore company name or UEN into a bounded public-data dossier for analyst review. It should not imply that Dude completes all KYC, AML, tax, legal, or licensed advisory obligations.
