# ACRA Licensing Track

This is the release blocker record for ACRA-derived commercial diligence outputs. It is product/commercial readiness guidance, not legal advice.

## Success Definition

- ACRA API Marketplace and ISP paths are documented with current source URLs.
- Authorised ISP partner candidates are shortlisted.
- Free OSS/self-host and hosted paid data boundaries are explicit.
- Release and onboarding docs carry the legal/commercial blocker status.

## Source Baseline

Observed on 2026-05-17:

- [ACRA data policy statement](https://www.acra.gov.sg/about-us/data-policy-statement/) states that ACRA provides public access to lodged information to support transparency and due diligence; most Bizfile information can be accessed upon payment, and some can be obtained from authorised Information Service Providers.
- [ACRA API Marketplace](https://www.acra.gov.sg/resources/eservice-tools-portals/api-marketplace/) is the current subscription platform for API services. It lists Entity Information Query, Financial Information Query, and trustBar Verification Query. It also notes that new API subscriptions are no longer available on the old API Mall, except for specified legacy cases.
- [ACRA business information products](https://www.acra.gov.sg/resources/buying-business-information/types-of-acra-information-products/) lists paid products such as Business Profile, CCFP, People Profile, Extracts, Certificates, and Registers, and states that residential address access is limited to specified persons including authorised information service providers.
- [ACRA buying from authorised ISPs](https://www.acra.gov.sg/resources/buying-business-information/bizfile-and-other-sources/) lists authorised ISPs for additional business information services.

## Current Product Boundary

| Workflow | Allowed now | Blocked until licence/partner path |
| --- | --- | --- |
| OSS MCP runtime using free public data.gov.sg-style mirrors and official no-auth datasets | Keep source provenance, freshness, gaps, and limits. Do not imply access to paid ACRA products. | Do not redistribute paid Business Profile, People Profile, CCFP, Registers, residential address data, or ISP-enriched products. |
| Self-host customer with its own ACRA subscription/API Marketplace credentials | Customer may configure its own credentials and remain responsible for subscription terms, permitted use, retention, and downstream sharing. | Dude must not bundle, resell, or pool one customer's ACRA subscription for other customers. |
| Hosted paid Dude Cloud | Public no-auth evidence can remain available with limits. | Any paid ACRA-derived commercial diligence output, bulk profile resale, enriched ownership/director/shareholder graph, or residential-address processing requires ACRA API Marketplace terms, ISP status, authorised ISP partner, or written sub-licence path. |
| Analyst memo and exports | May cite only evidence actually returned by current public workflows. | Must not describe restricted ACRA products as available unless the customer/licence path provides them. |

## ACRA API Marketplace Path

Initial track:

1. Confirm operating entity and Corppass access for the future Dude hosted entity.
2. Review Entity Information Query scope, pricing, access criteria, and terms through the ACRA API Marketplace.
3. Confirm whether Business Profile Data API output may be used in hosted customer dossiers, saved reports, bulk workflows, analyst memos, and exports.
4. Confirm whether each customer needs its own subscription or whether Dude may act as a provider under a permitted commercial model.
5. Confirm whether caching, derived summaries, audit logs, and export retention are allowed.
6. Confirm whether any personal data fields require extra notices, masking, retention controls, or customer instructions.
7. Record exact contractual restrictions before enabling any hosted paid ACRA-derived output.

Timeline assumption:

- Week 0: appoint owner and confirm legal entity.
- Week 1: review ACRA Marketplace product terms and request subscription details.
- Weeks 2-4: evaluate pricing, permitted use, caching, redistribution, and data-protection constraints.
- Weeks 4-8: implement only the API scope and customer controls that the signed terms allow.

This timeline is a planning estimate, not a commitment from ACRA.

## Authorised ISP Shortlist

ACRA's public ISP page lists the following authorised ISPs for additional business information services:

| Candidate | Why shortlist | First question |
| --- | --- | --- |
| CRIF BizInsights Pte. Ltd. | Existing authorised ISP and business-information provider. | Can Dude receive a hosted workflow sub-licence or API/data feed for customer diligence outputs? |
| DC Frontiers Pte. Ltd. (Handshakes) | Existing authorised ISP with graph/diligence-adjacent positioning. | Can Handshakes provide partner access for corp-services CDD without overclaiming ownership/control? |
| Experian Credit Services Singapore Pte. Ltd. | Existing authorised ISP with credit/commercial-data distribution experience. | What product scope can be embedded without making Dude a credit-decision tool? |
| Singapore Commercial Credit Bureau Pte. Ltd. | Existing authorised ISP focused on commercial credit/business information. | Is there an API or report-embedding model compatible with Dude's provenance and non-advice boundaries? |

No outreach has been sent from this repo. The track is ready for the owner to contact or compare the shortlist.

## Release Blocker

Hosted paid release must keep this blocker open until one of these is true:

- Dude has its own ACRA API Marketplace terms that expressly allow the intended hosted workflow.
- Dude is an authorised ISP, or has a written partner/sub-licence agreement with an authorised ISP.
- The hosted feature excludes restricted ACRA-derived commercial outputs and uses only public no-auth data with explicit limits.

The blocker covers:

- paid Business Profile, People Profile, CCFP, Extracts, Certificates, Registers, residential-address fields, and ISP-enriched products;
- bulk hosted redistribution or resale of ACRA-derived source records;
- derived director/shareholder/beneficial-owner/control graphs unless explicitly permitted by licensed source data;
- customer exports that include restricted ACRA-derived fields without contractual permission.

## Runtime Warning Surface

The machine-readable `sg://runtime` resource exposes `sourceUseWarnings` for ACRA. Agent and app planners should treat ACRA hosted paid enrichment as blocked until a permitted API Marketplace, authorised ISP, or partner path is recorded.

## Gaps

- No signed ACRA Marketplace subscription, ISP authorisation, or ISP partner terms are recorded.
- No partner outreach owner, date, or response is recorded.
- No paid ACRA-derived output fields are approved for hosted Dude Cloud.

## Limits

- This track does not interpret private ACRA Marketplace or ISP terms.
- This track does not authorise scraping Bizfile or reselling ACRA information products.
- This track does not override PDPA obligations for personal data from ACRA or authorised ISP sources.
