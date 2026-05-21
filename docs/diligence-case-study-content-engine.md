# SG Diligence Case-Study Content Engine

This page defines the weekly case-study engine for Singapore DPOs, CFOs, and corp-services operators. It is a distribution artifact, not a diligence report and not legal, tax, credit, investment, AML, sanctions, or licensed compliance advice.

Observed at: 2026-05-17 09:42 Asia/Singapore.

## Definition Of Success

| Requirement | Status | Evidence |
| --- | --- | --- |
| Define case-study format with provenance, freshness, gaps, and limits. | Fulfilled | The format below requires an evidence ledger and a source-bound conclusion. |
| Create editorial calendar for the first 8 posts. | Fulfilled | The eight-week calendar below includes audience, workflow, evidence, and CTA. |
| Add review guardrails to avoid defamatory or unsupported claims. | Fulfilled | Review gates block allegations, unsupported scoring, and source-free claims before publication. |
| Publish first case study or create draft-ready examples. | Fulfilled | Three draft-ready examples are included and can be published as fictional scenarios or converted to real cases only after tool evidence is attached. |

## Standard Case-Study Format

Every post should fit this structure:

1. **Scenario**: one bounded diligence question from a DPO, CFO, or corp-services operator.
2. **Public-data workflow**: the exact Dude workflow or `sg_*` tools used.
3. **Evidence ledger**: source name, observed timestamp, returned records, and source URL or provenance field.
4. **What changed the decision**: one operational conclusion tied to the evidence.
5. **Gaps**: missing credentials, unavailable upstreams, incomplete records, stale records, or data families intentionally not queried.
6. **Limits**: what the workflow cannot conclude and when a licensed source, human reviewer, lawyer, accountant, or regulated adviser is needed.
7. **Reusable prompt**: a short prompt or checklist that readers can adapt.
8. **CTA**: ask for a review of their intake/checklist flow, not a risk verdict on a named company.

Minimum evidence language:

```text
Provenance: <tool/source names and URLs>
Freshness: observed <date/time> or source last-updated <date>
Gaps: <missing/failed/not-in-scope checks>
Limits: public-data workflow only; no legal, tax, credit, investment, AML, sanctions, or licensed compliance advice
```

## Editorial Calendar

| Week | Working title | Audience | Workflow | Evidence to attach before real publication | CTA |
| --- | --- | --- | --- | --- | --- |
| 1 | The UEN intake check that prevents stale client files | Corp-secretarial ops | `sg_business_dossier` or `sg_query` with entity name/UEN | ACRA/data.gov evidence, observed timestamp, dossier gaps | Ask readers to compare their onboarding form against the evidence ledger. |
| 2 | Why every vendor dossier needs a gaps section | DPOs | `sg_business_dossier` plus compliance-use clauses | Dossier evidence, `gaps`, `limits`, privacy notice/DPA links | Offer the checklist format, not a vendor verdict. |
| 3 | A public tender screen that stays source-bound | CFOs | `sg_gebiz_tenders` and procurement monitor outcome | GeBIZ records, query terms, no-match behavior | Invite finance teams to test tender-monitor keywords. |
| 4 | Supplemental evidence without overclaiming | Ops leaders | CDD orchestrator with web presence, people discovery, and external diligence enabled | Supplemental source provenance, confidence blockers, freshness, limits | Ask teams to label supplemental evidence as review material, not a clearance signal. |
| 5 | PDPA vendor diligence without pretending to be counsel | DPOs | PDPA readiness pack plus dossier gaps | PDPA checklist, dossier evidence, retained limits | Invite readers to separate data-protection questions from legal advice. |
| 6 | Bulk CDD is a workflow problem before it is an AI problem | Corp-services managers | Bulk diligence flow and export posture | Bulk row count, partial failures, per-row provenance | Ask teams to define acceptable partial-failure handling. |
| 7 | Source freshness is a control, not a footnote | CFOs and auditors | `sg://runtime`, release evidence, brief freshness | Freshness fields, release evidence, stale-source example | Offer a freshness-review checklist for monthly files. |
| 8 | The honest stop sign: when public data is not enough | DPOs, CFOs, partners | Commercial data use review, ACRA licensing track | ACRA and supplemental-source warnings and blockers | Invite readers to document escalation to licensed data or human review. |

## Review Guardrails

Before any real-company case study is published:

- Use a real Dude tool run or export as the evidence source; do not write from memory.
- Keep the exact `provenance`, `freshness`, `gaps`, and `limits` from the tool output or linked readiness document.
- Do not call any entity suspicious, fraudulent, sanctioned, insolvent, non-compliant, unsafe, risky, or untrustworthy unless a cited official source explicitly says so.
- Do not infer beneficial ownership, control, director relationships, shareholder relationships, or sanctions/PEP status from public hints.
- Do not identify a person unless the source is official, public, relevant, and necessary for the workflow.
- Avoid publishing named adverse examples unless counsel or the customer explicitly approves the copy.
- Mark fictional scenarios as fictional in the first paragraph.
- Strip customer personal data, private documents, NRIC/passport/bank details, internal notes, and confidential customer names.
- Keep screenshots free of private emails, account IDs, tokens, addresses that are not already public, and customer-uploaded documents.
- End with an operational takeaway and a source boundary, not a recommendation to buy, reject, report, sue, file taxes, or make a regulated decision.

## Approval Gate

Use this gate for every weekly post:

| Gate | Owner | Pass condition |
| --- | --- | --- |
| Evidence | Author | Every factual claim maps to a source row, tool output, or doc link. |
| Defamation | Reviewer | No unsupported negative characterization of a named entity or person. |
| Privacy | Privacy/security owner | No private personal data or customer-confidential material. |
| Licensed-advice boundary | Maintainer | Copy avoids legal, tax, credit, investment, AML, sanctions, and licensed compliance advice. |
| Freshness | Author | Source observation date is visible and stale source caveats are stated. |

## Draft-Ready Example 1: LinkedIn Post

Fictional scenario.

Most onboarding misses are not dramatic. They are ordinary: a client sends a company name, a partner forwards an old UEN, and the operations team starts a file before anyone has checked what public sources can actually confirm.

The fix is not a bigger memo. It is a small evidence ledger:

- What did we query?
- Which public source returned records?
- When was the source observed?
- What gaps remain?
- What are we not allowed to conclude?

In Dude, a basic UEN intake check should end with four visible fields: provenance, freshness, gaps, and limits. If any of those are missing, the file is not audit-ready yet.

Operational takeaway: make the first client-intake screen prove what it knows before the analyst writes a paragraph.

Provenance: fictional scenario; replace with `sg_business_dossier` output before naming any entity.
Freshness: draft prepared 2026-05-17.
Gaps: no real UEN queried in this draft.
Limits: public-data workflow only; not legal, tax, credit, investment, AML, sanctions, or licensed compliance advice.

## Draft-Ready Example 2: Newsletter Short

Fictional scenario.

**Title:** A vendor dossier should say what it could not check

A DPO reviewing a new software vendor asked for a "quick risk check." That phrase is dangerous because it can hide three different tasks:

1. confirm public identity facts;
2. list source-backed diligence evidence;
3. decide what private contract, security, and data-protection checks remain.

Only the first two belong in a public-data dossier. The third needs a human review workflow.

The useful artifact is a source-bound memo:

| Section | What to include |
| --- | --- |
| Evidence | Public records returned by the tool, with provenance. |
| Freshness | Observation time or source last-updated date. |
| Gaps | Missing licences, auth-gated sources, upstream failures, or no-match results. |
| Limits | No legal advice, no private security assurance, no unsupported compliance verdict. |

The DPO does not need a magic score. They need an artifact that survives a reviewer asking, "where did this claim come from?"

Provenance: fictional scenario; replace with Dude export or tool output before publication as a real case.
Freshness: draft prepared 2026-05-17.
Gaps: no real vendor queried in this draft.
Limits: public-data workflow only; not legal, tax, credit, investment, AML, sanctions, or licensed compliance advice.

## Draft-Ready Example 3: Carousel Script

Fictional scenario.

Slide 1: Your public-data dossier needs a stop sign

Slide 2: Public records can confirm useful facts. They cannot fill every compliance gap.

Slide 3: Keep four fields visible: provenance, freshness, gaps, limits.

Slide 4: Provenance answers: which source produced this record?

Slide 5: Freshness answers: when was it observed or last updated?

Slide 6: Gaps answer: what failed, required credentials, or was out of scope?

Slide 7: Limits answer: what should a human reviewer decide outside the tool?

Slide 8: A better diligence file does not overclaim. It tells the reviewer when to stop.

Caption:

Fictional workflow example. Before publishing a named-company case study, attach the actual Dude evidence ledger and keep the source boundaries visible.

Provenance: fictional scenario.
Freshness: draft prepared 2026-05-17.
Gaps: no real entity queried in this draft.
Limits: public-data workflow only; not legal, tax, credit, investment, AML, sanctions, or licensed compliance advice.

## Operating Cadence

- Monday: choose the scenario and run the tool evidence.
- Tuesday: draft post and evidence ledger.
- Wednesday: complete evidence, defamation, privacy, advice-boundary, and freshness gates.
- Thursday: schedule or publish.
- Friday: record reader questions and convert repeated objections into product/docs issues.

## Limits

- Fictional drafts are publishable only when clearly marked as fictional.
- Real-company drafts require fresh source output attached to the working copy before review.
- Case studies should not publish private customer workflows, uploads, contracts, or personal data.
- Content should create product education and workflow demand, not public allegations about named entities.
