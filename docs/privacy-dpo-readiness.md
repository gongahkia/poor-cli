# PDPA Notification And DPO Readiness Pack

This pack is an operational readiness artifact for hosted Dude workflows. It is not legal advice and must be reviewed by counsel before paid hosted use.

## Success Definition

- PDPA notification language exists for website users, workspace customers, and customer end-users whose data may appear in a diligence case.
- The DPO appointment and public contact surface are documented.
- A privacy notice and retention summary are ready for hosted beta review.
- A DPIA checklist exists and must be completed before hosted beta.

## Source Baseline

Observed on 2026-05-17:

- [PDPC Data Protection Obligations](https://www.pdpc.gov.sg/overview-of-pdpa/the-legislation/personal-data-protection-act/data-protection-obligations) states the accountability, notification, protection, retention, transfer, access/correction, and data-breach notification obligations.
- [PDPC Register Your Data Protection Officer](https://www.pdpc.gov.sg/overview-of-pdpa/data-protection/business-owner/data-protection-officers) says organisations must designate at least one DPO and make DPO contact information available to the public.
- [PDPC Guide to Notification](https://www.pdpc.gov.sg/help-and-resources/2019/09/guide-to-notification) describes purpose notification and DPO/contact information that may be included in notices.
- [PDPC Guide to Managing and Notifying Data Breaches](https://www.pdpc.gov.sg/help-and-resources/2021/01/data-breach-management-guide) and the PDPC data-intermediary breach self-assessment page explain breach-assessment and data-intermediary notification expectations.
- [PDPC Guide to Data Protection Impact Assessments](https://www.pdpc.gov.sg/Help-and-Resources/2017/11/Guide-to-Data-Protection-Impact-Assessments) describes DPIA phases for identifying personal data, data flows, risks, action plans, and monitoring.
- [PDPC Advisory on Common Data Protection Lapses and Recommended Measures](https://www.pdpc.gov.sg/help-and-resources/2026/01/advisory-on-common-data-protection-lapses-and-recommended-measures) highlights go-live, monitoring, bulk-download, and migration controls relevant to hosted beta.

## Hosted Beta Data Roles

| Data context | Dude role | Customer role | Handling boundary |
| --- | --- | --- | --- |
| Workspace account profile, billing contact, support ticket, and admin user data | Organisation/controller for Dude account operations. | Supplier/customer contact. | Covered by Dude privacy notice and DPO contact surface. |
| Customer-uploaded diligence inputs, optional notes, saved dossiers, exports, bulk files, and watchlists | Data intermediary/processor when processed only on customer instructions. | Organisation/controller for its client/counterparty file. | Covered by DPA and customer instructions; do not use for unrelated product analytics without a separate approved basis. |
| Public registry data from official sources | Public-data processor and publisher of source-cited derived artifacts. | Reviewer of output limits. | Preserve provenance, freshness, gaps, and limits; do not imply advisory conclusions. |
| Operational telemetry, trace IDs, request IDs, error envelopes, and security logs | Organisation/controller for platform operations. | User/customer may be indirectly referenced if identifiers are configured poorly. | Avoid PII in IDs; use retention controls and redaction. |

## PDPA Notification Language

Use this as draft website and onboarding copy. Replace bracketed fields before launch.

> Dude collects, uses, and discloses personal data to provide workspace accounts, authenticate users, process customer diligence requests, generate and store public-data dossiers, provide support, secure the service, maintain audit records, and meet legal or regulatory requirements. Customer-uploaded diligence inputs and saved outputs are processed for the customer’s authorised workspace purposes. Dude does not require NRIC, passport, bank-account, or special-category personal data for ordinary company/UEN diligence, and users should not upload such data unless their workspace policy and approved use case require it.
>
> Dude may process personal data through subprocessors that provide hosting, storage, logging, email, analytics, support, payment, or security services. Dude will maintain a current subprocessor list for hosted customers and will use contractual and technical controls for authorised processing, retention, deletion, transfer, and breach handling.
>
> For questions, access/correction requests, withdrawal requests, complaints, or data-protection incidents, contact the Dude Data Protection Officer at `[privacy@your-domain.example]` or `[registered business address / support URL]`.

Customer onboarding copy:

> Customer remains responsible for providing any required notices to its own clients, applicants, employees, directors, beneficial owners, counterparties, and other individuals whose personal data it enters into Dude. Customer should not use Dude as the only source for legal, tax, credit, investment, AML, sanctions, or licensed compliance decisions.

Data-intermediary breach language for hosted customers:

> Where Dude has credible grounds to believe that a data breach has occurred in relation to customer personal data processed on behalf of a customer, Dude will notify the relevant customer without undue delay through the security contact or DPO contact configured for the workspace. The customer remains responsible for assessing whether notification to PDPC or affected individuals is required unless otherwise agreed in writing.

## DPO Appointment And Contact Surface

Before hosted beta:

- Designate at least one DPO owner and backup owner.
- Publish a public DPO contact address, preferably a monitored group inbox such as `privacy@...`.
- Add the DPO contact to the website privacy notice, customer onboarding docs, DPA, and incident-response runbook.
- Register or update the DPO contact with PDPC if the operating company is ready to do so.
- Define response owners for access, correction, withdrawal, complaint, deletion, breach, subprocessor, and transfer queries.
- Add an internal weekly check that the DPO inbox is monitored and escalations have an owner.

## Privacy Notice Skeleton

### Personal Data We Collect

- account and workspace administrator details;
- authentication, support, billing, and security-contact details;
- customer-uploaded diligence inputs, notes, and bulk files;
- saved dossiers, analyst memo states, exports, audit events, and watchlist settings;
- operational logs, request IDs, trace IDs, device/session metadata, and security events.

### Purposes

- provide and administer the service;
- authenticate users and enforce workspace access controls;
- generate, save, search, export, and support diligence artifacts;
- preserve provenance, freshness, gaps, limits, audit evidence, and customer instructions;
- detect abuse, secure the service, investigate incidents, and maintain reliability;
- meet contractual, accounting, legal, regulatory, and dispute-resolution requirements.

### Disclosure

- customer-authorised workspace users;
- subprocessors for hosting, storage, logging, support, email, payments, security, and analytics;
- professional advisers, auditors, insurers, regulators, law enforcement, or courts where required;
- public-data upstream sources only when a user makes a live API request that necessarily sends a lookup value to that source.

### Transfer

Hosted beta must record hosting region, backup region, support access countries, and subprocessor locations before launch. If personal data can leave Singapore, document comparable-protection controls in the DPA and subprocessor register.

### Access, Correction, Withdrawal, And Deletion

Provide a DPO/support route for requests. Workspace customers should be able to export and delete their own workspace data through product controls where available; manual support procedures must exist before hosted beta.

## Retention Summary

| Data class | Default beta posture | Deletion trigger | Notes |
| --- | --- | --- | --- |
| Local MCP trace/request audit index | Existing local defaults in [audit-retention-policy.md](./audit-retention-policy.md): `SG_APIS_AUDIT_MAX_ENTRIES=5000` and `SG_APIS_AUDIT_RETENTION_SEC=86400`. | Automatic eviction by count or age. | Local index should not store full upstream payloads. |
| Hosted workspace accounts | Keep while account is active, then delete or anonymise after contractual offboarding and dispute/accounting hold. | Workspace closure or signed customer instruction. | Final period must be set in the customer terms. |
| Saved dossiers, bulk files, exports, watchlists, and analyst notes | Customer-controlled retention by workspace policy. | Customer deletion, offboarding, or retention expiry. | Preserve source provenance until deletion; do not retain hidden copies outside backups/logs. |
| Backups | Time-limited operational recovery only. | Backup expiry. | Document backup retention period before beta. |
| Security and audit logs | Long enough for incident investigation and contractual audit needs. | Policy expiry or legal hold release. | Avoid storing PII in request IDs, trace IDs, and log messages. |
| Support tickets | Keep while needed for support, dispute handling, and service improvement. | Ticket closure plus support retention period. | Redact unnecessary personal data from attachments. |

## DPIA Checklist Before Hosted Beta

Complete this checklist before any hosted beta workspace processes real or customer-approved personal data:

- [ ] Scope: define the hosted beta workflow, workspace roles, customer categories, countries, subprocessors, and data stores.
- [ ] Data inventory: list every personal-data field that may enter account setup, support, diligence inputs, notes, dossiers, exports, telemetry, backups, and logs.
- [ ] Purpose mapping: map each data field to a customer instruction, service purpose, security purpose, or legal/contractual purpose.
- [ ] Flow mapping: draw collection, use, disclosure, transfer, retention, backup, export, deletion, and incident paths.
- [ ] Minimisation: confirm ordinary company/UEN diligence does not require NRIC, passport, bank-account, medical, payroll, or private shareholder/controller personal data.
- [ ] Access control: verify workspace isolation, RBAC, admin impersonation rules, support access approvals, and break-glass logging.
- [ ] Security controls: verify encryption, secrets handling, environment separation, vulnerability checks, go-live migration checks, and monitoring for unusual access or bulk downloads.
- [ ] Subprocessors: approve hosting, logging, support, email, analytics, security, payment, and AI subprocessors before they process customer personal data.
- [ ] Transfer controls: document hosting/support countries and comparable-protection safeguards for overseas transfers.
- [ ] Retention and deletion: confirm product controls, support runbook, backup expiry, and deletion confirmations.
- [ ] Breach response: define customer notification path, severity triage, evidence preservation, PDPC/customer assessment support, and affected-individual communication support.
- [ ] Output limits: verify dossiers, exports, analyst memos, and watchlists preserve `provenance`, `freshness`, `gaps`, and `limits`.
- [ ] Review: DPO, security, product, and counsel sign off or record blockers before beta.

## Gaps

- The DPO email, company legal name, business address, hosting regions, backup retention, and subprocessor list are placeholders until the hosted operating entity is confirmed.
- The privacy notice is draft-ready but not legal-reviewed.
- The DPIA checklist must be completed against the actual hosted architecture before processing real beta data.

## Limits

- This pack does not decide whether a specific deployment complies with the PDPA.
- This pack does not replace a separate DPA template once that template is adopted and reviewed.
- This pack does not authorise collection of unnecessary personal data for diligence.
