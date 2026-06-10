# Data Processing Agreement Template

This is a Singapore PDPA-oriented starting template for hosted Dude customers. It is not legal advice, is not a final contract, and must receive legal review before any paid hosted use.

## Source Baseline

Observed on 2026-05-17:

- [PDPC Guide on Data Protection Clauses for Agreements Relating to the Processing of Personal Data](https://www.pdpc.gov.sg/-/media/Files/PDPC/PDF-Files/Resource-for-Organisation/Guide-on-Data-Protection-Clauses-for-Agreements-Relating-to-the-Processing-of-Personal-Data-1-Feb-2021.pdf) provides sample clauses for customer/contractor processing arrangements, data-intermediary obligations, protection, retention, breach notification, return/deletion, and legal-review cautions.
- [PDPC Data Protection Obligations](https://www.pdpc.gov.sg/overview-of-pdpa/the-legislation/personal-data-protection-act/data-protection-obligations) describes notification, protection, retention, transfer, access/correction, and data-breach notification obligations.
- [PDPC data-intermediary breach guidance](https://www.pdpc.gov.sg/report-data-breach/before-you-report-a-data-breach-2/info) states that a data intermediary should notify the relevant organisation or public agency without undue delay when it has credible grounds to believe a breach occurred.

## Template Status

- Owner: `[legal / operations owner]`
- Version: `draft-2026-05-17`
- Legal review status: `required before paid hosted use`
- Intended customers: Singapore corp-secretarial, accounting, and compliance teams using hosted Dude workspaces.
- Intended role split: customer as organisation/controller for customer-entered personal data; Dude as data intermediary/processor when processing that data on customer instructions.

## Agreement Template

### 1. Parties And Order Of Precedence

This Data Processing Agreement ("DPA") forms part of the agreement between `[Customer legal name]` ("Customer") and `[Dude operating entity]` ("Dude") for hosted Dude services.

If this DPA conflicts with the main services agreement on personal-data processing, this DPA controls only for the conflicting personal-data processing term unless the parties expressly agree otherwise in writing.

### 2. Definitions

- "Customer Personal Data" means personal data that Customer provides to Dude, or that Dude processes on behalf of Customer, through the hosted Dude service.
- "PDPA" means Singapore's Personal Data Protection Act 2012 and its applicable regulations.
- "Personal data", "data intermediary", "organisation", and "processing" should be interpreted consistently with the PDPA unless the main services agreement defines a stricter standard.
- "Subprocessor" means a third party engaged by Dude to process Customer Personal Data for hosted Dude services.
- "Security Incident" means unauthorised or accidental access, collection, use, disclosure, copying, modification, disposal, loss, or similar risk involving Customer Personal Data.

### 3. Processing Scope And Instructions

Dude will process Customer Personal Data only:

- to provide, secure, support, monitor, and improve the hosted Dude service;
- to generate, store, search, export, and support customer-authorised diligence artifacts;
- to comply with Customer's documented instructions, including workspace configuration and support requests;
- as required by law, court order, regulator, or public authority, after notifying Customer where lawful and practicable.

Dude will not sell Customer Personal Data, use it for unrelated advertising, or use it to train public models unless Customer separately and expressly agrees in writing.

### 4. Customer Responsibilities

Customer remains responsible for:

- deciding whether Customer has a lawful basis and required notices for the personal data it enters into Dude;
- configuring workspace access, users, roles, retention, exports, and support contacts;
- avoiding unnecessary NRIC, passport, bank-account, medical, payroll, or private shareholder/controller personal data unless Customer has an approved workspace policy and lawful basis;
- reviewing Dude outputs as public-data evidence artifacts, not legal, tax, credit, investment, AML, sanctions, or licensed compliance advice.

### 5. Dude Data-Intermediary Obligations

For Customer Personal Data processed on behalf of Customer, Dude will:

- process only under Customer instructions and this DPA;
- maintain reasonable administrative, physical, procedural, and technical safeguards;
- restrict personnel access to authorised personnel with a need to know;
- require personnel and subprocessors to maintain confidentiality;
- support Customer's reasonable access, correction, deletion, export, audit, and breach-assessment requests;
- preserve `provenance`, `freshness`, `gaps`, and `limits` in saved diligence artifacts where those fields exist.

### 6. Security Measures

Dude will maintain a written security baseline for hosted production covering:

- server-side secret handling and no browser exposure of upstream API keys or AI provider keys;
- workspace isolation and role-based access controls;
- encryption in transit and, where supported by the storage layer, encryption at rest;
- least-privilege production access and support-access approval;
- audit logging for administrative access, exports, deletion, and support actions;
- monitoring for unusual access, bulk downloads, credential exposure, and migration/go-live mistakes;
- backup, restore, vulnerability-management, dependency-update, and incident-response procedures.

The initial control list is in Schedule B and may be updated if controls remain materially equivalent or stronger.

### 7. Subprocessors

Dude may use subprocessors for hosting, storage, logging, email, support, payments, analytics, security, and AI-assisted memo generation only where necessary for the hosted service.

Dude will:

- maintain a current subprocessor register in Schedule C or a linked customer-facing page;
- require subprocessors to process Customer Personal Data only for the authorised service purpose;
- impose confidentiality, security, retention, deletion, transfer, and breach-support obligations appropriate to the processing;
- notify Customer of new subprocessors through `[notice channel and notice period]` before production use where commercially reasonable;
- provide an objection path for material subprocessor changes.

### 8. Transfers Outside Singapore

Dude will document hosting regions, backup regions, support-access countries, and subprocessor locations. Where Customer Personal Data is transferred outside Singapore, Dude will use contractual or other legally enforceable safeguards intended to provide a standard of protection comparable to the PDPA.

### 9. Retention, Return, And Deletion

Dude will retain Customer Personal Data only for as long as needed to provide the hosted service, comply with Customer instructions, meet contractual/legal obligations, or resolve disputes.

Upon Customer's written request or account termination, Dude will:

- export or return Customer Personal Data in an available supported format where technically feasible;
- delete Customer Personal Data from active production systems after Customer confirmation or expiry of the agreed offboarding period;
- delete backup copies according to backup expiry schedules unless a legal hold applies;
- provide reasonable written confirmation of deletion when complete;
- instruct relevant subprocessors to return or delete Customer Personal Data where required and feasible.

Retention defaults and placeholders are listed in Schedule D and must be completed before hosted beta.

### 10. Security Incident And Breach Notification

Where Dude has credible grounds to believe that a Security Incident has occurred in relation to Customer Personal Data processed on Customer's behalf, Dude will notify Customer without undue delay through the configured security or DPO contact.

The notification should include, where known and lawful to disclose:

- incident summary and discovery time;
- affected systems, workspaces, records, or data categories;
- likely impact and containment steps;
- information needed for Customer's PDPA assessment;
- next update cadence and customer action requests.

Customer remains responsible for assessing whether notification to PDPC or affected individuals is required unless the parties expressly agree otherwise in writing.

### 11. Assistance And Cooperation

Dude will reasonably assist Customer with:

- access, correction, export, deletion, and retention requests;
- data-flow, subprocessor, transfer, and DPIA questions;
- breach assessment, containment, evidence preservation, and post-incident review;
- regulator, auditor, or customer questionnaire responses that relate to Dude's hosted service controls.

Dude may charge reasonable fees for extraordinary assistance outside standard support if the main services agreement allows it.

### 12. Audit Cooperation

Upon reasonable written request, Dude will provide audit cooperation appropriate to the risk and service tier, such as:

- current security overview and architecture summary;
- subprocessor list and hosting-region summary;
- relevant policy summaries for access control, backup, logging, retention, incident response, and vulnerability management;
- exportable audit events or signed export manifests where the product supports them;
- management responses to material findings.

Customer audit access must be scoped, scheduled, confidentiality-protected, and limited to Customer's own workspace and Dude's relevant control evidence. Customer may not access other customers' data, production secrets, unrelated logs, source code not otherwise licensed, or systems in a way that weakens security.

### 13. Public-Data And Non-Advice Boundary

Dude's public-registry outputs are evidence artifacts for analyst review. Customer must not use this DPA to infer that Dude:

- provides legal, tax, credit, investment, AML, sanctions, or licensed compliance advice;
- guarantees a counterparty is safe, approved, risk-free, sanctioned-free, conflict-free, or compliant;
- has access to restricted ACRA, private beneficial-ownership, banking, credit, or internal procurement data unless separately contracted.

### 14. Legal Review Gate

Before paid hosted use, counsel must review at least:

- party names, governing agreement, liability, indemnity, and insurance alignment;
- whether Dude is acting as data intermediary, independent organisation, or both for each data context;
- breach notification timing and content commitments;
- subprocessor notice and objection mechanics;
- overseas transfer safeguards;
- retention/deletion periods and backup commitments;
- audit rights, security schedule, and customer questionnaire process.

## Schedule A: Processing Details

| Field | Draft value |
| --- | --- |
| Processing purpose | Hosted workspace accounts, public-data diligence case processing, saved dossiers, exports, audit evidence, support, security, and service operations. |
| Data subjects | Customer workspace users; customer contacts; individuals included by Customer in diligence inputs, notes, files, or support requests. |
| Data categories | Account identifiers, business contact details, customer-entered case notes, optional personal data in uploaded files, operational telemetry, trace/request IDs, support content. |
| Sensitive data | Not required for ordinary company/UEN diligence; prohibited unless Customer has a documented policy and approved use case. |
| Processing duration | Term of the customer agreement plus offboarding, backup, legal hold, or dispute period. |
| Customer instructions | Workspace configuration, user actions, support tickets, API calls, and written instructions accepted by Dude. |

## Schedule B: Security Measures

- Identity and access management with role-based workspace access.
- Server-side secret management for upstream API and AI provider credentials.
- Transport encryption for customer-facing and admin endpoints.
- Production data access approval and logging.
- Backup and restore procedure with retention expiry.
- Vulnerability and dependency update process.
- Incident-response runbook and security contact route.
- Audit log or trace evidence for material admin, export, deletion, and support actions as product support matures.

## Schedule C: Subprocessor Register

Complete before hosted beta.

| Subprocessor | Purpose | Data categories | Location/region | Transfer safeguard | Notice status |
| --- | --- | --- | --- | --- | --- |
| `[cloud provider]` | Hosting, storage, network | Workspace and service data | `[region]` | `[contract / DPA / SCC-style safeguard / other]` | `[approved]` |
| `[email provider]` | Account, security, support email | Business contact details | `[region]` | `[safeguard]` | `[approved]` |
| `[logging/security provider]` | Security monitoring and diagnostics | Logs, event metadata | `[region]` | `[safeguard]` | `[approved]` |
| `[AI provider if enabled]` | Analyst memo generation if customer enables it | Dossier text sent for memo generation | `[region]` | `[safeguard and no-training setting]` | `[optional]` |

## Schedule D: Retention And Deletion

| Data class | Draft retention | Deletion method | Confirmation |
| --- | --- | --- | --- |
| Account and workspace records | Active term plus `[offboarding period]` | Production deletion/anonymisation | Support confirmation |
| Saved dossiers, notes, exports, bulk files | Customer workspace policy | Product deletion or support-run deletion | Export/deletion ticket |
| Audit/security logs | `[period]` for security, contractual, and dispute needs | Expiry or legal-hold release | Policy evidence |
| Backups | `[backup period]` | Backup expiry | Backup policy evidence |
| Support tickets | `[support retention period]` | Ticket deletion/redaction | Support confirmation |

## Schedule E: Audit Request Packet

For customer onboarding and renewals, prepare:

- this DPA;
- [PDPA notification and DPO readiness pack](./privacy-dpo-readiness.md);
- [commercial data use review](./commercial-data-use.md);
- security overview and hosting-region summary;
- subprocessor register;
- retention/deletion summary;
- incident-response and breach-notification contact path;
- latest release evidence or verification summary where available.

## Fulfilment Checklist

- [ ] DPA template covers data-intermediary/processor obligations.
- [ ] Subprocessors, retention, deletion, breach notification, and audit cooperation are explicit.
- [ ] Legal review gate is stated before paid hosted use.
- [ ] Hosted onboarding docs link to this template.
- [ ] Provenance, freshness, gaps, and limits remain visible for public-data outputs.

## Limits

- This template does not determine whether a particular customer contract complies with PDPA.
- This template does not cover regulated financial-institution outsourcing terms, MAS Notice 658, SOC 2 controls, or sector-specific terms except by later schedule.
- This template must be adapted to the actual hosted architecture, subprocessors, customer terms, and legal entity before use.
