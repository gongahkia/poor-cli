# Certified Consulting Partner Program

This document defines a future partner program for corp-services, compliance, and diligence consultants who help customers adopt Dude. It is not yet launched and should not be marketed as an active certification.

## Success Definition

- Partner profile, training, certification criteria, rev-share model, and onboarding docs are defined.
- First three candidate partner targets are identified.
- The decision gate for piloting is tied to hosted workflow readiness.
- Claims and customer-safety boundaries are explicit.

## Program Goal

Enable qualified partners to implement Dude for Singapore client and counterparty CDD workflows without turning Dude outputs into legal, tax, AML, sanctions, credit, investment, or licensed compliance advice.

The partner should sell implementation, workflow design, training, and evidence handling. Dude should remain the public-data diligence system with provenance, freshness, gaps, limits, auditability, and non-advice boundaries.

## Source Baseline

Observed on 2026-05-17:

- [Sleek Singapore](https://sleek.com/sg/) describes expert accounting and corporate-secretarial services for startups and small businesses.
- [Osome Singapore FAQ](https://osome.com/sg/faq/company-formation/osome-incorporation-compliance/) describes end-to-end incorporation, corporate secretarial, accounting, payroll, GST, registered-office, nominee-director, and work-pass support.
- [InCorp/Rikvin ACE partnership press release](https://www.incorp.asia/press-releases/incorp-group-with-rikvin-as-key-subsidiary-appointed-as-official-corporate-services-partner-of-ace/) describes InCorp Global with Rikvin as a key subsidiary and positions it as a corporate solutions provider.

These sources identify candidate fit only. They are not endorsements, commitments, or proof of partner interest.

## Ideal Partner Profile

| Dimension | Requirement |
| --- | --- |
| Firm type | Corporate services provider, accounting/bookkeeping firm, compliance advisory, company-secretarial practice, boutique legal-ops vendor, or digital transformation consultant serving Singapore SMEs/funds/founders. |
| Customer base | At least 25 active Singapore entities or recurring client-onboarding workflows. |
| Operational maturity | Named engagement lead, support contact, client onboarding checklist, documented escalation process. |
| Compliance posture | Understands ACRA/CSP obligations, PDPA basics, source provenance, and non-advice limits. |
| Implementation capability | Can configure workflows, train analysts, manage exports, and handle customer-specific DPA/retention questions. |
| Disqualifiers | Wants to resell public data as proprietary, provide unsupported pass/fail compliance opinions, bypass source licences, or hide gaps/limits from customers. |

## Training Path

| Module | Content | Evidence |
| --- | --- | --- |
| Product fundamentals | Dude MCP, web dossier workflow, `sg_business_dossier`, provenance/freshness/gaps/limits, non-advice boundaries. | 45-minute recorded training and quiz. |
| Corp-services CDD workflow | New-client intake, UEN/name search, sector module reruns, PDF/CSV/JSON exports, signed manifest, analyst handoff. | Demo dossier and export pack. |
| PDPA and DPA basics | PDPA vendor checklist, DPO/privacy packet, DPA boundaries, retention/deletion, subprocessor questions. | Completed sample PDPA checklist. |
| Source licensing and public-data limits | ACRA, OneMap, URA, LTA, commercial data-use gates, no unsupported enrichment claims. | Source-limit acknowledgement. |
| Hosted operations | Workspace roles, audit logs, debug logs, support escalation, incident routing, uptime/status limitations. | Support simulation. |
| Sales ethics | No legal/tax/AML/sanctions advice, no government endorsement claims, no hidden source gaps. | Partner code of conduct sign-off. |

## Certification Criteria

Initial certification should be firm-level with named practitioners.

| Level | Criteria | Renewal |
| --- | --- | --- |
| Registered Partner | Completed onboarding, signed partner terms, understands non-advice/source limits. | Annual acknowledgement. |
| Certified Implementation Partner | Two named practitioners pass training; completes one supervised customer or sample implementation; support process verified. | Annual refresher and one evidence pack review. |
| Certified Delivery Partner | Three successful customer rollouts, no unresolved serious support/compliance incidents, can train customer admins. | Annual review, customer references, incident review. |

Certification evidence should be stored privately. Public partner listings must show scope and expiry date.

## Rev-Share Draft

Do not implement rev-share until hosted billing, entitlements, audit logs, support ownership, and partner attribution exist.

Draft model:

- 20% first-year revenue share for partner-sourced paid hosted workspaces;
- 10% second-year share if the partner remains active on support/training;
- no share on OSS/self-host installs unless a paid support contract exists;
- no commission for grant-funded or public-sector deals unless the grant/programme permits it;
- clawback for refunds, non-payment, sanctions/source-licensing violations, or material misrepresentation;
- partner-attributed usage must be visible in the billing ledger.

Alternative for early pilots: fixed implementation fee paid by the customer to the partner, with no Dude rev-share until billing is mature.

## Onboarding Docs Required

| Document | Status |
| --- | --- |
| Partner overview one-pager | Draft needed. |
| Partner code of conduct and claims policy | Draft from this document and compliance-use clauses. |
| Training deck and quiz | Draft needed after hosted workflow stabilizes. |
| Demo script and sample dossiers | Use existing examples; add partner-specific script. |
| Customer handoff checklist | Draft from corp-services CDD and hosted onboarding docs. |
| Support escalation guide | Draft after support owner and SLA tiers exist. |
| Rev-share agreement | Legal review required; do not draft from scratch as final contract. |
| Public listing criteria | Draft after certification evidence model exists. |

## First Candidate Targets

These are outreach hypotheses, not endorsements or commitments.

| Candidate | Rationale | First ask |
| --- | --- | --- |
| Sleek | Singapore-facing tech-enabled incorporation, accounting, and corporate-secretarial services for startups/SMEs. | Validate whether dossier checks reduce onboarding/manual review time for entity clients. |
| Osome | Singapore-headquartered business-management/corporate-services platform with incorporation, accounting, payroll, GST, registered-office, nominee director, and work-pass support. | Explore workflow integration or internal analyst pilot for public-source CDD evidence packs. |
| InCorp / Rikvin | Established corporate-services provider with Singapore presence and history serving founders and SMEs. | Test whether partner-delivered onboarding packs can improve high-touch CDD and client handoff. |

Candidate outreach should wait until the hosted private-beta workflow is stable enough to demo without manual engineering support.

## Pilot Gate

Do not launch the partner pilot until:

- hosted workspace/RBAC is implemented;
- persisted dossiers/folders and retention/deletion controls exist;
- immutable audit logs and signed exports are available;
- PDPA/DPA/customer onboarding packet is current;
- source-licensing gates are enforced;
- partner attribution and support owner are defined;
- three sample customer workflows are documented end to end;
- the partner claims policy is reviewed.

## Pilot Shape

Recommended first pilot:

- two partners maximum;
- one named implementation lead per partner;
- three customer workflows per partner, using sample or consenting beta data;
- no public certification badge until completion;
- no rev-share until billing ledger exists;
- weekly support review and one final retrospective;
- exit criteria: repeatable setup, no unsupported claims, measurable analyst time savings or evidence-quality improvement.

## Claims Policy

Partners may say:

- they are participating in a Dude partner pilot, if approved in writing;
- Dude produces public-data diligence artifacts with provenance, freshness, gaps, and limits;
- Dude outputs support analyst review.

Partners may not say:

- Dude or the partner provides legal, tax, AML, sanctions, credit, investment, or licensed compliance advice;
- Dude is government endorsed, IMDA accredited, SGTech accredited, GeBIZ registered, or grant pre-approved unless that exact approval exists;
- a dossier is a pass/fail compliance decision;
- public sources are complete when gaps/limits are present.

## Decision

Do not pilot yet. Build the hosted workflow and partner attribution/support foundations first.

Next step: draft the partner one-pager and claims policy after workspace/RBAC, persistence, audit log, and signed export work are production-ready.
