# Reference Deployment Program

This program defines how Dude should collect named reference deployments without overstating adoption or leaking customer data. It is a readiness packet; no named reference is public until permission is recorded.

## Success Definition

- One corp-secretarial firm target, one SME target, and one journalist/civic user target are identified for outreach.
- Each reference path has a permission request and anonymized fallback.
- README or website copy is prepared without pretending references exist.
- Adoption caveats are explicit.
- Actual permission collection is tracked as an external follow-up.

## Target Segments

| Segment | Initial target profile | Why this target | First ask |
| --- | --- | --- | --- |
| Corp-secretarial firm | Singapore firm doing recurring incorporation, secretary, accounting, and client-onboarding checks. Candidate examples include Sleek, Osome, and InCorp/Rikvin from the partner-program research. | This segment directly matches the CDD workflow and can validate analyst time saved, evidence quality, and export usefulness. | Run two approved sample or consenting-client dossiers and review the evidence pack for onboarding fit. |
| SME | Singapore SME with recurring vendor/customer onboarding and no dedicated compliance tooling. | Validates whether Dude is useful outside corp-services specialists and whether the web-first search/export path is simple enough. | Use a public or approved vendor list and compare current manual checks against Dude exports. |
| Journalist or civic user | Data journalist, civic-tech maintainer, or public-interest researcher covering Singapore company/public-data workflows. | Validates the public-data, provenance, and limits story without turning the product into licensed advice. | Review a non-sensitive public-interest scenario and confirm whether provenance/freshness/gaps are understandable. |

These are target profiles, not endorsements or commitments.

## Permission Request

Use this email or message skeleton:

```text
Subject: Permission request for a Dude MCP reference or anonymized case study

Hi [name],

We are collecting early references for Dude, a Singapore public-data CDD workflow that produces source-backed dossiers with provenance, freshness, gaps, and limits.

Could we use your organization as:

1. a named public reference;
2. an anonymized case study; or
3. private reviewer-only evidence?

We will not publish client names, UENs, screenshots, logos, metrics, or quotes without written approval. We will also keep the caveat that Dude is public-data evidence for analyst review and is not legal, tax, AML, sanctions, credit, investment, or licensed compliance advice.

Proposed evidence:

- workflow tested:
- date tested:
- approved quote or summary:
- allowed logo/name usage:
- caveats:

Thanks,
[maintainer]
```

## Case Study Template

| Field | Requirement |
| --- | --- |
| Reference type | `named`, `anonymized`, or `private reviewer-only`. |
| Segment | Corp-secretarial firm, SME, journalist, civic user, or other. |
| Workflow | Exact workflow tested, such as new-client UEN search, sector-module rerun, bulk list, export pack, or analyst memo. |
| Data approval | Public-only, synthetic, customer-approved, or redacted. |
| Evidence | Dossier export, signed manifest, screenshot, timing note, or quote. |
| Outcome | Concrete observed value, not broad marketing claims. |
| Caveats | Source gaps, missing hosted controls, beta status, or non-advice boundaries. |
| Permission | Name, approver, date, allowed assets, expiry/review date. |

## README Copy Block

Do not add logos or customer names until permission is recorded. Use this placeholder until then:

```markdown
## Reference Deployments

Reference deployments are being collected from corp-services, SME, and civic/public-data users. Public names, logos, quotes, and case-study links will be added only after written permission. Until then, Dude should be evaluated through the reproducible quickstart, public-data limits, and exported dossier evidence.
```

## Adoption Caveats

- A public reference means the workflow was useful for a bounded use case; it is not proof that all diligence needs are covered.
- An anonymized case study can support workflow credibility but should not be counted as a public named deployment.
- Private reviewer-only evidence should not be shown in README, registry listings, or marketing copy.
- Any reference involving real customer data must respect the PDPA readiness and DPA boundaries before hosted beta.
