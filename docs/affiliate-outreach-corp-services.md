# Corp-Services Affiliate Outreach Plan

This plan turns the partner-program research into an actionable outreach packet for corporate-services incumbents. It is not a launched partner program.

## Success Definition

- Embedded API/widget partner pitch is ready.
- Target firms and current workflow hypotheses are documented.
- Pilot terms, data constraints, and support boundaries are defined.
- Outreach tracking is ready, with actual external contact moved to follow-up.

## Partner Pitch

Dude gives corp-services teams a source-backed client and counterparty CDD evidence layer:

- company or UEN search defaults to ACRA identity evidence;
- sector modules such as BCA, CEA, BOA, HSA, HLB, and GeBIZ run when selected or supported by sector context;
- exports preserve provenance, freshness, gaps, limits, and a signed manifest;
- the workflow is non-advisory and designed for analyst review.

Integration options:

| Option | Shape | Best fit |
| --- | --- | --- |
| Embedded web link | Partner portal links to a Dude dossier/search flow with a prefilled query. | First pilot with minimal engineering. |
| Backend API | Partner system calls the REST gateway or MCP runtime and stores returned evidence packs. | Mature portal with audit and retention controls. |
| Widget | Partner embeds a controlled search/check panel once hosted auth and tenant boundaries are ready. | Later-stage product integration. |
| Partner-delivered onboarding pack | Partner runs Dude as part of onboarding and exports the evidence pack to the client record. | Consulting or managed-service rollout. |

## Target Firms And Workflow Hypotheses

These are outreach hypotheses, not endorsements or commitments.

| Target | Workflow hypothesis | First ask |
| --- | --- | --- |
| Sleek | Tech-enabled startup/SME incorporation, accounting, and secretary workflows can benefit from faster public-registry evidence packs. | Validate whether Dude reduces manual client-onboarding checks for Singapore entities. |
| Osome | Digital business-management workflows can use source-backed dossiers during incorporation, accounting, payroll, and compliance handoff. | Explore an internal analyst pilot or integration review. |
| InCorp / Rikvin | High-touch corporate-services work can use repeatable evidence packs and analyst handoff exports. | Test a partner-delivered onboarding pack with approved sample data. |
| BoardRoom or similar CSP | Larger corporate-services providers may need auditability, retention, and workflow controls before integration. | Ask for product-fit feedback and hosted-control requirements. |

## Pilot Terms

| Term | Default |
| --- | --- |
| Duration | Four weeks after onboarding. |
| Scope | Up to three approved workflows per partner. |
| Data | Public-only, synthetic, or customer-approved test cases. No private client records without hosted beta controls and DPA review. |
| Support | One named Dude maintainer and one named partner lead. |
| Output | Dossier/export evidence, issue list, go/no-go recommendation. |
| Commercials | No rev-share until billing ledger, partner attribution, and support ownership exist. |
| Claims | No legal, tax, AML, sanctions, credit, investment, or licensed compliance advice claims. |

## Outreach Tracker

| Target | Contact path | Status | Next step | External blocker |
| --- | --- | --- | --- | --- |
| Sleek | Warm intro, website contact, or founder/operator network. | Not contacted. | Identify named owner. | Requires external outreach. |
| Osome | Warm intro, partnerships contact, or product lead. | Not contacted. | Identify named owner. | Requires external outreach. |
| InCorp / Rikvin | Partnerships or corporate-services operations lead. | Not contacted. | Identify named owner. | Requires external outreach. |
| BoardRoom or similar CSP | Enterprise partnerships or innovation lead. | Not contacted. | Decide whether to include in first wave. | Requires external outreach. |

## Follow-Up Criteria

Open an implementation issue only after a target confirms:

- the workflow to test;
- the data approval boundary;
- a named pilot owner;
- the required export/audit artifact;
- whether the pilot is internal, customer-facing, or partner-delivered.
