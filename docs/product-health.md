# Product Health

This page is the public entrypoint for product-health, governance, and adoption evidence. It separates current working evidence from credentialed, unpublished, and hosted/commercial readiness tracks so planning docs are not mistaken for completed production claims.

## Readiness Status

- `Works today`: implemented in the local/self-hosted Swee Pulse and Swee Shield product path and covered by smoke or repository tests.
- `Requires credentials`: implemented, but only fully useful when the named provider key, licence, or source approval is configured.
- `Unpublished`: prepared in the repo but not available through the public registry or marketplace yet.
- `Hosted/commercial blocked`: planning or governance evidence only; do not treat as a production attestation, public listing, or customer-ready hosted control.

## Evaluation

- `Works today` Swee Pulse and Shield local smoke — no-auth dashboard, Pulse snapshot, and Shield audit paths are covered by repository smoke checks; live upstreams still depend on source availability.
- `Works today` [Public benchmark/status](./status/public-status.md) — generated Pulse, Shield, and transport-reliability evidence; this is release evidence, not an SLA or official public-agency status page.
- `Works today` `npm run benchmark:transport:live` — live local MCP proof for `swee_pulse_mobility`, source states, Shield audit replay metadata, and credential gaps.
- `Works today` [Market conventions audit](./market-conventions-audit.md) — MCP ecosystem expectations and positioning.
- `Works today` [Ecosystem snapshot](./ecosystem-snapshot.md) — generated ecosystem evidence and comparison context.

## Distribution

- `Hosted/commercial blocked` [SG diligence case-study content engine](./diligence-case-study-content-engine.md) — planning material for distribution content, not evidence of a live campaign.

## Operations

- `Works today` [Compatibility matrix](./compatibility-matrix.md) — supported clients, transports, and smoke checks.
- `Hosted/commercial blocked` [Incident playbook](./incident-playbook.md) — response flow template; production evidence still depends on hosted operations.
- `Works today` [Troubleshooting](./troubleshooting.md) — common local/self-host failure modes and diagnostics.

## Retired Material

Older CDD, dossier, and counterparty artifacts may remain for compatibility and migration history. They are not the active product entrypoint. New demos, docs, status evidence, and UI surfaces should route through Swee Pulse and Swee Shield.

## Governance

- `Works today` [Governance checklist](./governance-checklist.md) — release and ownership gates.
- `Works today` [Audit retention policy](./audit-retention-policy.md) — local trace and request-retention policy.
- `Requires credentials` [ACRA licensing track](./acra-licensing-track.md) — API Marketplace, authorised ISP, and hosted paid enrichment blocker status.
- `Hosted/commercial blocked` [Commercial data use review](./commercial-data-use.md) — OneMap, URA, and other source-use posture plus source-limit history.
- `Hosted/commercial blocked` [PDPA notification and DPO readiness](./privacy-dpo-readiness.md) — hosted beta privacy notice, DPO contact, retention, and DPIA checklist.
- `Hosted/commercial blocked` [Data Processing Agreement template](./data-processing-agreement-template.md) — draft hosted customer DPA requiring legal review.
- `Hosted/commercial blocked` [SOC 2 Type I readiness roadmap](./soc2-type1-roadmap.md) — hosted assurance gap analysis, control backlog, cost estimate, and buyer trigger; not an attestation.
- `Hosted/commercial blocked` [MAS outsourcing readiness pack](./mas-outsourcing-readiness.md) — BCP, incident response, subprocessors, data residency, and FI-adjacent control gaps.
- `Unpublished` [npm publish readiness](./npm-publish-readiness.md) — `@swee-sg/shield` package metadata, dry-run evidence, and first-publish blocker.
- `Hosted/commercial blocked` [PSG application track](./psg-application-track.md) — vendor pre-approval requirements, materials, timeline, and first-application blocker.
- `Hosted/commercial blocked` [KPI thresholds](./kpi-thresholds.md) — dashboard policy and breach handling for future hosted operations.
- `Works today` [Quarterly product health template](./quarterly-product-health-template.md) — recurring review format.
- `Works today` [Deprecation policy](./deprecation-policy.md) — migration and removal rules.
- `Works today` [Release guide](./release.md) — release-window commands and evidence.
