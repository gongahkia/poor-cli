# SOC 2 Type I Readiness Roadmap

This roadmap is a buyer-readiness plan for hosted Dude Cloud. It is not an audit report, attestation, certification, or legal advice.

## Success Definition

- Hosted Dude Cloud has a SOC 2 readiness gap analysis.
- The build-vs-tool evidence path is selected.
- A control backlog has owners and timelines.
- Estimated cost and buyer trigger threshold are documented.

## Source Baseline

Observed on 2026-05-17:

- [AICPA SOC 2 overview](https://www.aicpa-cima.com/topic/audit-assurance/audit-and-assurance-greater-than-soc-2) says SOC 2 reports serve users that need assurance about controls relevant to security, availability, processing integrity, confidentiality, and privacy.
- [AICPA Trust Services Criteria](https://us.aicpa.org/content/dam/aicpa/interestareas/frc/assuranceadvisoryservices/downloadabledocuments/trust-services-criteria-redlined.pdf) remains the primary criteria reference for SOC 2 control design.
- 2026 market pricing references for startup SOC 2 audits vary widely. Public 2026 pricing guides commonly put Type I audit fees in a broad low-five-figure range, with compliance platforms, readiness work, penetration testing, and engineering time adding materially to first-year cost. Treat all numbers below as planning estimates pending auditor quotes.

## Intended First Scope

| Scope choice | Roadmap decision | Reason |
| --- | --- | --- |
| Report type | SOC 2 Type I first, then Type II when evidence collection is stable. | Type I tests control design at a point in time and is the fastest buyer-unblocker before a monitored observation period. |
| Trust Services Criteria | Security required; add Availability only if hosted SLAs are sold before the audit. Defer Confidentiality and Privacy until customer contracts require them. | Keeps first audit scoped to current buyer pressure and hosted maturity. |
| System boundary | Hosted Dude Cloud web app, REST gateway, MCP endpoint, production infrastructure, support access, logging, backups, and administrative processes. | Self-host OSS runtime stays out of audit scope unless a customer contract requires it. |
| Data boundary | Customer workspace data, saved dossiers, exports, audit events, support tickets, production logs, secrets, and subprocessor-managed data. | Aligns with the DPA and PDPA/DPO readiness pack. |
| Exclusions | Local-only MCP installs, customer-managed self-host deployments, external public-data sources, customer-controlled browser/client environments. | These are not controlled by hosted Dude Cloud. |

## Readiness Gap Analysis

| Domain | Current evidence | Gap | Required before Type I |
| --- | --- | --- | --- |
| Governance | Maintainer governance, release guide, ownership matrix, security reporting, DPA, PDPA/DPO pack. | No hosted operating entity, control owner register, formal risk committee, or policy approval cadence. | Assign executive owner, security owner, DPO/privacy owner, change owner, vendor owner, and incident owner. |
| Risk assessment | Product risk docs, public-data limits, commercial data-use blockers, source warnings. | No formal hosted risk register or recurring review evidence. | Create risk register with quarterly review and risk acceptance records. |
| Asset inventory | Repo has deployment topology and API family ownership. | No hosted asset inventory for cloud resources, domains, databases, queues, logs, backups, and admin consoles. | Create asset inventory with owner, environment, data class, region, backup, and monitoring fields. |
| Access control | Workspace/RBAC implementation contract, SSO/2FA policy docs, deployment docs, server-side secrets guidance. | Hosted admin access reviews, support access approvals, break-glass evidence, and production IdP configuration are not yet evidenced. | Configure production identity controls, enforce MFA for production/admin access, and retain access-review and break-glass audit evidence. |
| Change management | Release guide, verify pipeline, release preflight, changelog discipline. | No formal change tickets, approval evidence, emergency-change policy, or production deployment audit trail. | Use GitHub issues/PRs as change records; document approval and rollback evidence. |
| Availability/BCP | Deployment guide, health checks, smoke tests, incident playbook. | No RTO/RPO, backup restore evidence, failover test, uptime page, or customer SLA definition. | Define RTO/RPO, run backup restore test, document uptime/incident metrics. |
| Incident response | Incident playbook and security reporting route. | No hosted customer notification runbook, tabletop evidence, severity matrix, or contact tree. | Run tabletop and record actions; align breach notices with DPA and PDPA/DPO pack. |
| Vendor/subprocessor management | DPA and hosted onboarding require subprocessor register. | No approved subprocessor list, vendor risk ratings, or annual review. | Build subprocessor register and minimum vendor review procedure. |
| Data protection | PDPA/DPO readiness pack, DPA, audit-retention policy, commercial source-use warnings. | No hosted deletion proof, backup retention proof, encryption evidence, data classification, or production redaction checks. | Document data classification, retention/deletion process, encryption settings, and log redaction checks. |
| Monitoring/logging | Local trace/request audit index and health checks. | No hosted SIEM/log retention, privileged access alerts, bulk-download monitoring, or log review evidence. | Define logging sources, retention, alert owners, and review cadence. |
| Secure development | TypeScript build/test, lint, verify, dependency workflow. | No formal secure SDLC policy, dependency SLA, vulnerability triage, or pen-test record. | Add secure SDLC policy and perform external or scoped internal security test before audit. |

## Build-Vs-Tool Path

Decision: start with repository-native evidence for the first readiness pass, then buy a GRC platform only when a paying hosted buyer requires a report date.

Rationale:

- The current risk is premature platform spend before workspace/RBAC/hosted architecture is implemented.
- The repo already has strong evidence primitives: `npm run verify`, release preflight, governance checks, docs, ownership matrix, and smoke tests.
- A GRC platform becomes useful when there is a real hosted system, subprocessors, production access, and recurring evidence to collect.

Trigger to buy a tool:

- one signed or near-signed FI-adjacent customer requires a SOC 2 report date;
- hosted workspace/RBAC, production deployment, backups, and incident process exist;
- at least three months of evidence must be collected for a likely Type II follow-up.

Candidate tool categories:

- lightweight repository-native evidence folder plus GitHub Issues/Projects;
- startup GRC platforms for automated evidence collection;
- auditor-provided readiness portal if bundled with the audit engagement.

## Control Backlog

| Priority | Control / artifact | Owner | Target |
| --- | --- | --- | --- |
| P0 | Hosted control owner register and risk register | Project owner | Before hosted beta |
| P0 | Workspace accounts, RBAC, admin/viewer roles, and cross-workspace isolation | Platform owner | Before real customer data |
| P0 | Production MFA, privileged access review, and break-glass logging | Security owner | Before hosted beta |
| P0 | Subprocessor register and vendor-risk review | Operations owner | Before hosted beta |
| P0 | Backup retention, restore test, RTO/RPO, and deletion procedure | Operations owner | Before hosted beta |
| P0 | Incident tabletop, severity matrix, breach/customer notification path | Security + DPO | Before hosted beta |
| P0 | Secure SDLC policy, dependency triage SLA, and vulnerability response evidence | Maintainer | Before SOC 2 readiness review |
| P1 | Uptime/SLO evidence and public status or benchmark page | Operations owner | Before FI-adjacent sales |
| P1 | External penetration test or scoped security review | Security owner | Before Type I audit fieldwork |
| P1 | Formal change approval and emergency-change evidence | Maintainer | Before Type I audit fieldwork |
| P1 | Data classification, log redaction, encryption evidence | Security + DPO | Before Type I audit fieldwork |
| P2 | GRC platform rollout and automated evidence collection | Operations owner | When buyer trigger is met |
| P2 | Type II observation-window plan | Project owner | After Type I or buyer letter |

## Cost And Buyer Trigger

Planning estimate for a lean hosted SaaS scope:

- Audit fee for a narrow Type I: USD 7,500-25,000.
- Readiness support, policy cleanup, and gap remediation: USD 5,000-25,000 if outsourced; otherwise mostly internal time.
- GRC platform: USD 10,000-30,000/year if selected.
- Penetration test or targeted security review: USD 5,000-20,000 depending on scope.
- Internal engineering/compliance time: 100-300 hours for first readiness pass, higher if workspace/RBAC and hosted controls are unfinished.

Buyer trigger threshold:

- Do not start a paid audit solely for speculative credibility.
- Start readiness work now.
- Get auditor quotes when a hosted buyer says SOC 2 Type I is a procurement blocker or when two FI-adjacent prospects request formal assurance evidence.
- Start Type I audit only after hosted workspace isolation, production access controls, backup restore evidence, incident process, subprocessor register, and DPA are in place.

## Evidence Folder Plan

Use `artifacts/compliance/soc2/` or a private equivalent for sensitive material. Do not commit secrets, customer data, raw logs, or private audit evidence.

Suggested index:

- `scope.md`
- `system-description.md`
- `risk-register.csv`
- `control-matrix.csv`
- `asset-inventory.csv`
- `subprocessor-register.csv`
- `access-review/YYYY-MM.md`
- `change-evidence/`
- `backup-restore/YYYY-MM.md`
- `incident-tabletop/YYYY-MM.md`
- `vendor-review/`
- `security-test/`

## Gaps

- No hosted production system boundary is final.
- Workspace/RBAC, persistence, audit logs, SSO/2FA policy, signed manifests, and watchlist primitives exist in the repo, but hosted production evidence is still missing.
- No auditor has been selected and no Type I audit is scheduled.
- Costs are estimates and require current quotes.

## Limits

- This roadmap does not claim SOC 2 readiness or compliance.
- SOC 2 reports must be issued by an independent CPA firm under applicable AICPA standards.
- Buyer-specific assurance requests may require ISO 27001, CSA CAIQ, MAS outsourcing mappings, or contractual controls beyond SOC 2.
