# Commercial Data Use Review

This review is a product and release-readiness control, not legal advice. It records the terms posture for the OneMap and URA sources that block paid hosted shipping if left ambiguous.

## Review Status

| Source | Observed | Upstream terms | OSS/self-host posture | Hosted-paid posture | Release decision |
| --- | --- | --- | --- | --- | --- |
| OneMap | 2026-05-17 | [OneMap Terms of Use](https://www.onemap.gov.sg/legal/termsofuse.html) | Allowed only for registered-developer use under the OneMap Terms of Use and Developer Agreement. | Do not market hosted paid workflows as redistributing OneMap data until counsel or SLA confirms the exact Developer Agreement rights. | Review before paid hosted launch. |
| URA APIs | 2026-05-17 | [URA API Terms of Service](https://www.ura.gov.sg/ms/eservices/Maps/API-terms-of-service) and [Singapore Open Data Licence](https://data.gov.sg/open-data-licence) | API use may be commercial or non-commercial, subject to API terms, dataset-page terms, credentials, attribution, and licence limits. | Hosted paid use can proceed only if each URA-backed feature keeps attribution, avoids endorsement claims, and checks individual API pages for extra limits. | Allowed with controls. |

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

- block paid hosted OneMap-backed redistribution unless the blocker is cleared;
- keep URA attribution text in UI and exports that include URA data;
- keep OneMap and URA credentials server-side only;
- show source freshness and data limits anywhere derived outputs are saved or exported.

## Provenance And Freshness

- OneMap Terms of Use observed on 2026-05-17 from `https://www.onemap.gov.sg/legal/termsofuse.html`.
- URA API Terms of Service observed on 2026-05-17 from `https://www.ura.gov.sg/ms/eservices/Maps/API-terms-of-service`; page footer showed `Last Updated : 13 May 2026`.
- Singapore Open Data Licence observed on 2026-05-17 from `https://data.gov.sg/open-data-licence`.

## Limits

- This document does not interpret the private OneMap Developer Agreement beyond the public terms page.
- This document does not decide whether a specific hosted contract is legally compliant.
- If upstream terms change, update this review, `sg://runtime` source-use warnings, and any affected onboarding or export copy before paid release.
