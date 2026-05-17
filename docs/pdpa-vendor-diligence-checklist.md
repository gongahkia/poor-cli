# PDPA Vendor Diligence Checklist

This checklist maps Dude business dossiers to Singapore PDPA vendor-review questions. It is an analyst aid, not legal advice, not a PDPA compliance opinion, and not a replacement for DPO, counsel, or contract review.

## Success Definition

- PDPA section 24 and section 26 review points are represented in the dossier UI.
- Checklist items cite PDPC public guidance.
- Checklist evidence is tied to dossier provenance, freshness, gaps, and limits.
- Analysts can mark items reviewed and export a PDF report with provenance/non-advice language.
- Tests cover checklist generation and rendering.

## Source Baseline

Observed on 2026-05-17:

- [PDPC Data Protection Obligations](https://www.pdpc.gov.sg/overview-of-pdpa/the-legislation/personal-data-protection-act/data-protection-obligations) summarises obligations including Accuracy, Protection, Retention Limitation, Transfer Limitation, Access and Correction, Data Breach Notification, and Accountability.
- [PDPC Advisory Guidelines on Key Concepts in the PDPA](https://www.pdpc.gov.sg/guidelines-and-consultation/2020/03/advisory-guidelines-on-key-concepts-in-the-personal-data-protection-act) lists chapters for Accuracy, Protection, Retention Limitation, Transfer Limitation, Data Breach Notification, and Accountability.
- [PDPC distinction between organisations and data intermediaries](https://www.pdpc.gov.sg/the-distinction-between-organisations-and-data-intermediaries-and-why-it-matters) explains the controller/intermediary distinction and notes data intermediaries have Protection and Retention Limitation obligations, plus breach notification to the organisation for which they process personal data.
- [PDPC Advisory on Common Data Protection Lapses and Recommended Measures](https://www.pdpc.gov.sg/help-and-resources/2026/01/advisory-on-common-data-protection-lapses-and-recommended-measures) highlights section 24 protection lapses and recommended measures.

## Product Behavior

The dossier page now includes a PDPA vendor diligence checklist with six items:

| Item | PDPA / PDPC mapping | Dossier evidence used | Expected analyst action |
| --- | --- | --- | --- |
| Vendor identity and data accuracy | Accuracy Obligation | ACRA identity, UEN/entity summary, match confidence, provenance. | Confirm contracting party against official name/UEN. |
| Security arrangements for personal data | Section 24 / Protection Obligation | Matched modules and official provenance. | Request security controls, data-flow diagram, access controls, incident process, and recent evidence. |
| Retention and deletion controls | Retention Limitation Obligation | Dossier freshness and export provenance. | Collect retention schedule, deletion procedure, backup expiry, and exit/return process. |
| Cross-border transfer and subprocessors | Section 26 / Transfer Limitation Obligation | Public registry provenance only. | Ask for processing locations, subprocessors, overseas support access, safeguards, and notice process. |
| Controller / data-intermediary boundary | Data intermediary guidance | Dossier identity and module matches. | Document processing role and contract/DPA responsibility split. |
| Breach notification and escalation path | Data Breach Notification Obligation | Dossier gaps, limits, and freshness. | Record DPO/security contact, breach SLA, and escalation route. |

## Status Meanings

| Status | Meaning |
| --- | --- |
| Evidence available | The dossier has official evidence that supports the checklist item, but the analyst must still review it. |
| Analyst action | The item cannot be resolved from public registry evidence alone. |
| Blocked by dossier gap | A relevant upstream failure, timeout, or rate-limit gap makes the evidence incomplete. |

No status means the vendor is PDPA compliant.

## Export

The `Export PDPA report` action creates a standalone PDF with:

- entity/UEN summary;
- reviewed checkbox state;
- evidence, gaps, and analyst action for each checklist item;
- PDPC source citations;
- non-advice language.

The ordinary dossier PDF remains unchanged except for the main dossier page now offering this separate report.

## Limits

- Public registry evidence does not prove the vendor's security controls, retention behavior, hosting countries, subprocessors, or breach notification readiness.
- Section 24 and section 26 handling depends on the customer's actual workflow, personal-data categories, contract terms, and transfer chain.
- Counsel/DPO review is required before relying on the checklist for regulated, high-risk, or sensitive personal-data processing.
