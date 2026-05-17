# MAS Notice 658 Outsourcing Readiness Pack

This pack is for early FI-adjacent buyer diligence. It is not legal advice, does not claim MAS compliance, and must be validated against the current MAS Notice 658 text and customer counsel before selling into regulated financial-institution workflows.

## Success Definition

- Buyer-facing pack covers BCP, incident response, subprocessors, and data residency.
- Current gaps are mapped honestly.
- Required controls before FI-adjacent sales are defined.
- The pack links to the SOC 2 roadmap and DPA.

## Source Baseline

Observed on 2026-05-17:

- Official MAS URLs for [Notice 658](https://www.mas.gov.sg/regulation/notices/notice-658), [Guidelines on Outsourcing for Banks](https://www.mas.gov.sg/regulation/guidelines/guidelines-on-outsourcing-banks), [Business Continuity Management Guidelines](https://www.mas.gov.sg/regulation/guidelines/guidelines-on-business-continuity-management), and [Technology Risk Management Guidelines](https://www.mas.gov.sg/regulation/guidelines/technology-risk-management-guidelines) are the intended primary sources.
- Automated browser access to the MAS notice/guideline pages returned a MAS maintenance page on 2026-05-17. Manual validation against the current MAS source text is therefore a release gate before FI-adjacent sales.
- Public market summaries consistently describe MAS Notice 658 as applying to banks, with focus on outsourced relevant services, material ongoing outsourced relevant services, services involving disclosure of customer information, due diligence, agreements, audit/inspection rights, subcontractor controls, customer-information protection, termination, and outsourcing registers. Treat this as orientation only until confirmed from MAS primary text.

## Applicability Boundary

Dude is not itself a MAS-regulated financial institution. MAS Notice 658 obligations fall on banks, but FI-adjacent buyers will ask Dude to provide evidence that helps them complete outsourcing due diligence.

Use this pack only for:

- responding to bank or FI-adjacent vendor-risk questionnaires;
- explaining hosted Dude Cloud control posture;
- identifying controls required before selling hosted workflows to regulated buyers;
- routing contract clauses into the [Data Processing Agreement template](./data-processing-agreement-template.md) and later customer-specific terms.

Do not use this pack to claim Dude complies with MAS Notice 658 or that any customer can outsource regulated obligations without its own assessment.

## Buyer-Facing Summary

| Area | Current answer | Evidence / next artifact |
| --- | --- | --- |
| Service description | Hosted Dude Cloud provides public-data client/counterparty diligence artifacts for analyst review, with provenance, freshness, gaps, and limits. | [corp-services-cdd.md](./product/corp-services-cdd.md) |
| Data handled | Workspace user data, customer-entered company/UEN diligence inputs, saved dossiers, exports, operational logs, support data, and optional analyst memo content. | [privacy-dpo-readiness.md](./privacy-dpo-readiness.md), [data-processing-agreement-template.md](./data-processing-agreement-template.md) |
| Customer information | Hosted workflows may process customer personal data if users enter it; ordinary company/UEN diligence should not require NRIC, passport, bank-account, payroll, or private shareholder/controller data. | PDPA pack and DPA |
| Subprocessors | Must be listed before hosted beta. Categories include hosting, storage, logging/security, email, support, payments, analytics, and optional AI provider. | DPA Schedule C |
| Data residency | Not final. Hosted beta must define primary region, backup region, support-access countries, and subprocessor locations. | This pack and hosted onboarding gaps |
| BCP/DR | Not production-ready for FI-adjacent buyers until RTO/RPO, backup restore tests, incident runbooks, and availability monitoring are evidenced. | SOC 2 roadmap and incident playbook |
| Audit rights | DPA includes audit cooperation but not unrestricted customer system access. Customer-specific audit clauses need legal review. | DPA Section 12 |
| Exit and deletion | DPA includes return/deletion template; hosted implementation must prove product deletion, support-run deletion, and backup expiry. | DPA Schedule D |

## Business Continuity And Operational Resilience

Minimum before FI-adjacent sales:

- define service tiers and whether any hosted workflow is business-critical for the customer;
- define RTO and RPO for web app, REST gateway, MCP endpoint, database, artifact store, logs, and backups;
- document primary region, backup region, restore owner, and recovery runbook;
- run and record at least one backup restore test;
- define status page or customer notification channel for material incidents;
- define dependency inventory for cloud provider, DNS, email, AI provider, upstream Singapore public-data sources, and monitoring/logging providers;
- document degradation behavior when ACRA, OneMap, URA, LTA, or AI providers are unavailable;
- preserve `gaps`, `freshness`, and `limits` when upstream sources fail instead of producing silent pass/fail outcomes.

Current gap: deployment docs describe the single-node Docker topology, but no hosted production RTO/RPO, failover, restore evidence, or customer-facing SLA exists.

## Incident Response

Minimum before FI-adjacent sales:

- maintain severity levels for security, privacy, availability, data-integrity, and source-data incidents;
- assign incident commander, technical lead, communications owner, DPO/privacy owner, and legal/commercial owner;
- define customer notification thresholds and contact paths;
- align security-incident handling with the DPA and PDPA/DPO readiness pack;
- record incident timeline, affected workspaces, affected data classes, containment, root cause, customer actions, and post-incident remediation;
- run a tabletop exercise before hosted beta and at least annually after launch;
- define evidence retention for incident records without storing unnecessary customer data.

Current gap: the repo has an incident playbook and security reporting route, but no hosted customer notification tabletop evidence, severity matrix, or FI-specific reporting pack.

## Subprocessors And Subcontracting

Minimum before FI-adjacent sales:

- complete DPA Schedule C with each subprocessor, purpose, data categories, region, and transfer safeguard;
- classify subprocessors by criticality and whether they can access customer information;
- define prior notice and objection mechanics for material new subprocessors;
- require subprocessors to support security, confidentiality, retention, deletion, breach cooperation, audit evidence, and transfer controls;
- maintain annual review evidence and contract owner for each material subprocessor;
- document optional AI provider behavior, data submission boundaries, and no-training settings where applicable.

Current gap: the DPA has a subprocessor register template, but no actual hosted subprocessor list is approved.

## Data Residency And Customer Information

Minimum before FI-adjacent sales:

- identify primary processing region and backup region;
- identify countries where support or operations personnel may access production systems;
- identify countries where subprocessors process or store customer data;
- document encryption in transit and at rest for customer data, backups, logs, and exports;
- document customer-data classification and prohibit unnecessary sensitive personal data for ordinary company/UEN diligence;
- document deletion and backup expiry behavior;
- document how public-data source terms affect retention and redistribution.

Current gap: no final hosting region, backup region, support-access country list, or subprocessor location list is recorded.

## Required Controls Before FI-Adjacent Sales

| Priority | Required control | Blocking issue / artifact |
| --- | --- | --- |
| P0 | Workspace accounts, RBAC, and cross-workspace isolation | #43 |
| P0 | SSO/2FA or equivalent enterprise identity controls for hosted customers | #44 |
| P0 | Persisted dossier folders with retention/deletion controls | #45 |
| P0 | Signed export manifests for downstream verification | #46 |
| P0 | Immutable audit log with actor, dataset/source version, and content hash | #47 |
| P0 | Approved subprocessor register, DPA, and hosted privacy pack | DPA + PDPA/DPO pack |
| P0 | ACRA, OneMap, URA commercial-source gates cleared for the exact customer workflow | ACRA licensing track + commercial data use review |
| P0 | Backup restore test, RTO/RPO, and customer incident notification path | This pack + SOC 2 roadmap |
| P1 | SOC 2 Type I readiness review or signed auditor engagement letter if buyer requires it | [soc2-type1-roadmap.md](./soc2-type1-roadmap.md) |
| P1 | External security test or scoped penetration test | SOC 2 roadmap |
| P1 | Vendor-risk questionnaire packet with current architecture, regions, subprocessors, BCP, and incident evidence | Hosted onboarding packet |

## Contract Clause Mapping

Use the [Data Processing Agreement template](./data-processing-agreement-template.md) as the starting point for:

- customer instructions;
- confidentiality and security safeguards;
- subprocessors and transfer controls;
- breach notification and cooperation;
- return/deletion and retention;
- audit cooperation;
- public-data and non-advice boundaries.

FI-adjacent customers may require additional clauses for:

- MAS and customer audit/inspection access;
- subcontractor prior approval or notice;
- termination and exit assistance;
- business continuity testing and notification;
- data localisation or support-access restrictions;
- customer-information protection and regulator cooperation.

Do not accept these clauses without legal review and confirmation that the hosted architecture can evidence them.

## Gaps

- MAS Notice 658 source text needs manual primary-source validation because automated access returned maintenance.
- Dude does not yet have hosted workspace/RBAC, immutable audit logs, signed export manifests, or approved subprocessor evidence.
- No final data residency, backup, RTO/RPO, or SLA commitment exists.
- No SOC 2 readiness review or audit engagement exists.
- No FI-adjacent customer contract has been reviewed against these controls.

## Limits

- This pack is not a MAS compliance opinion.
- It does not decide whether a customer's use of Dude is an outsourced relevant service, material ongoing outsourced relevant service, or customer-information arrangement.
- It does not replace bank, counsel, auditor, or regulator review.
