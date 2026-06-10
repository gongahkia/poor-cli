# Commercial Data Use Review

This review is a product and release-readiness control, not legal advice. It records the terms posture for the OneMap and URA sources that block paid hosted shipping if left ambiguous.

## Review Status

| Source | Observed | Upstream terms | OSS/self-host posture | Hosted-paid posture | Release decision |
| --- | --- | --- | --- | --- | --- |
| ACRA | 2026-05-17 | [ACRA data policy statement](https://www.acra.gov.sg/about-us/data-policy-statement/), [ACRA API Marketplace](https://www.acra.gov.sg/resources/eservice-tools-portals/api-marketplace/), and [authorised ISP list](https://www.acra.gov.sg/resources/buying-business-information/bizfile-and-other-sources/) | Current public/no-auth evidence may be used with provenance, freshness, gaps, and limits; customer-owned subscriptions remain customer's responsibility. | Do not ship paid hosted ACRA-derived commercial diligence outputs until API Marketplace terms, ISP status, authorised ISP partnership, or sub-licence rights are recorded. | Blocked for hosted paid enrichment. |
| OneMap | 2026-05-17 | [OneMap Terms of Use](https://www.onemap.gov.sg/legal/termsofuse.html) | Allowed only for registered-developer use under the OneMap Terms of Use and Developer Agreement. | Do not market hosted paid workflows as redistributing OneMap data until counsel or SLA confirms the exact Developer Agreement rights. | Review before paid hosted launch. |
| URA APIs | 2026-05-17 | [URA API Terms of Service](https://www.ura.gov.sg/ms/eservices/Maps/API-terms-of-service) and [Singapore Open Data Licence](https://data.gov.sg/open-data-licence) | API use may be commercial or non-commercial, subject to API terms, dataset-page terms, credentials, attribution, and licence limits. | Hosted paid use can proceed only if each URA-backed feature keeps attribution, avoids endorsement claims, and checks individual API pages for extra limits. | Allowed with controls. |

## ACRA Controls

ACRA is the strongest commercial blocker for paid hosted diligence enrichment.

- Paid ACRA information products and API Marketplace outputs must not be bundled, resold, pooled across customers, or exported from hosted Dude unless the relevant ACRA or partner terms allow the exact use.
- Current OSS/self-host output may cite only public/no-auth ACRA-derived evidence actually returned by the running workflow.
- Hosted paid workflows must not claim access to Business Profiles, People Profiles, CCFP, Registers, residential-address data, director/shareholder details, or beneficial-owner/control graphs unless a licensed source path is in place.
- Customer-owned ACRA subscriptions must remain scoped to that customer and cannot become a shared Dude Cloud data source without permission.
- The active track and partner shortlist live in [acra-licensing-track.md](./acra-licensing-track.md).

## OneMap Controls

OneMap is the restrictive source for paid hosted use.

- Registration and acceptance of the Developer Agreement are required before using the API and data in an application.
- The public terms grant a revocable, non-exclusive, royalty-free licence subject to the OneMap terms.
- The terms restrict storing, downloading, archiving, distributing, publicly displaying, reproducing, publishing, copying, modifying, adapting, transmitting, or integrating SLA Data except as expressly permitted.
- Hosted workflows must not sell OneMap data, raw geocoding rows, map tiles, route geometry, or cached lookups as a standalone dataset.
- Product copy must frame OneMap-backed outputs as bounded location resolution inside a customer workflow, with source provenance and limits.
- Cache TTLs for OneMap should remain operational and bounded. Do not introduce long-lived customer-visible OneMap data stores without a signed terms review.

## URA Controls

URA API terms are more permissive, but still require release controls.

- URA API use may be commercial or non-commercial, subject to its API Terms of Service.
- URA datasets are governed by the Singapore Open Data Licence unless an individual API or dataset page adds further terms.
- Products using URA datasets need conspicuous source attribution and a link to the Open Data Licence.
- API credentials must remain confidential and must not be exposed to browser clients, customer exports, logs, or public examples.
- URA terms do not grant rights over personal data, third-party rights, patents, trademarks, or design rights.
- Do not imply official URA or Singapore Government endorsement.
- Generated reports should preserve `provenance`, `freshness`, `gaps`, and `limits`; derived analyses must not hide upstream uncertainty.

## Runtime Warning Surface

The machine-readable `sg://runtime` resource exposes `sourceUseWarnings` for OneMap and URA. Agent and app planners should read that field before enabling hosted commercial workflows.

Minimum handling:

- block paid hosted ACRA-derived enrichment and OneMap-backed redistribution unless the relevant blocker is cleared;
- keep URA attribution text in UI and exports that include URA data;
- keep ACRA, OneMap, and URA credentials server-side only;
- show source freshness and data limits anywhere derived outputs are saved or exported.

## Provenance And Freshness

- ACRA data policy, API Marketplace, information products, and authorised ISP pages observed on 2026-05-17. ACRA pages showed last-updated dates between 2026-01-29 and 2026-03-25, and site footer date 2026-05-16.
- OneMap Terms of Use observed on 2026-05-17 from `https://www.onemap.gov.sg/legal/termsofuse.html`.
- URA API Terms of Service observed on 2026-05-17 from `https://www.ura.gov.sg/ms/eservices/Maps/API-terms-of-service`; page footer showed `Last Updated : 13 May 2026`.
- Singapore Open Data Licence observed on 2026-05-17 from `https://data.gov.sg/open-data-licence`.

## Limits

- This document does not interpret the private OneMap Developer Agreement beyond the public terms page.
- This document does not interpret private ACRA API Marketplace, ISP, or partner terms.
- This document does not decide whether a specific hosted contract is legally compliant.
- If upstream terms change, update this review, `sg://runtime` source-use warnings, and any affected onboarding or export copy before paid release.
