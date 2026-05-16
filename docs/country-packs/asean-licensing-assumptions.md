# ASEAN Paid-Data Licensing Assumptions

Status: planning assumptions, not legal advice.

Checked on: 2026-05-16.

These assumptions guide country-pack planning for Malaysia, Indonesia, Thailand, Vietnam, and the Philippines. They do not grant permission to scrape, redistribute, resell, or host upstream data. Before shipping a live adapter, maintainers must review the source terms, rate limits, caching rules, attribution requirements, and commercial-use restrictions.

## Summary Matrix

| Country | Public-only candidate surfaces | Partner/subscription-required surfaces | Current adapter posture |
| --- | --- | --- | --- |
| Malaysia | Basic lookup/navigation through SSM public services where allowed. | SSM e-Info / MyData company profiles, business profiles, documents, charges, financial comparisons, company watch, API or bulk access. | Public-only skeleton until authorised SSM channel, Corporate Integration Data, MyData-SSM, or e-Info commercial terms are approved. |
| Indonesia | Narrow AHU/OSS status or NIB checks only if terms allow automated access. | AHU complete/latest company profiles, paid voucher/PNBP profile downloads, director/shareholder/capital/deed history, bulk or hosted redistribution. | Feasibility/skeleton only; paid AHU profile access and OSS automation rules need review. |
| Thailand | DBD DataWarehouse manual public search and records where the official portal allows free access. | Bulk automation, API access if not public, enriched ownership/financial packs, paid registry intermediaries, high-volume hosted monitoring. | Public-preview candidate after DBD terms/rate-limit review; hosted bulk requires permission or partner path. |
| Vietnam | Free public fields on the National Business Registration Portal if access is manual or permitted. | Automated HTML scraping, bulk search, paid registry extracts, hosted redistribution, any non-public enterprise data. | Feasibility only; lowest priority until stable permitted access path exists. |
| Philippines | SEC Number API within free quota, public SEC status/search pages where terms allow use. | SEC Company Information Lookup subscriptions, AFS/GIS/document retrieval, higher API quotas, certified or paid documents. | Public-only SEC-number proof-of-concept possible; production/bulk requires SEC API subscription and terms review. |

## Malaysia

Source references:

- [SSM e-Info product page](https://www.ssm.com.my/Pages/Buy_Corporate_Information/e-Info.aspx)
- [SSM e-Info official service portal](https://prod.ssm-einfo.my/)

Assumptions:

- SSM e-Info lists official products such as company profiles, business profiles, company charges, financial comparisons, images, company watch, and good-standing attestations.
- Company profile data includes fields that go beyond a lightweight public status check, including directors, shareholders, charges, and financial summaries.
- Corporate Integration Data/API-style access is a commercial or authorised-channel question, not a free OSS assumption.

Public-only boundary:

- A Malaysia pack may document source discovery and possibly support user-supplied document parsing.
- Do not redistribute SSM profile data, directors, shareholders, charges, or financial extracts through hosted Dude without an authorised path.

Partner-required boundary:

- Any paid hosted workflow, API integration, batch lookup, company-profile resale, or watchlist over SSM-derived data requires approved e-Info, MyData-SSM, Corporate Integration Data, or equivalent authorised-channel terms.

## Indonesia

Source references:

- [AHU Online company-profile guide](https://panduan.ahu.go.id/doku.php?id=perseroan)
- [OSS NIB public search guide surfaced through Data Rakyat research](https://datarakyat.id/docs/oss_nib/)

Assumptions:

- AHU Online is the official company-profile route for Indonesian limited-company profiles.
- AHU profile downloads are fee-bearing in the public guide, with different prices for complete and latest profiles.
- OSS NIB search may expose public business-licensing status, but the surface is a web application and automation terms need review.

Public-only boundary:

- A pack may start with fixtures and manual-source documentation.
- A live NIB/status check is acceptable only after confirming that automated access, caching, and hosted use are permitted.

Partner-required boundary:

- Full AHU profiles, paid voucher downloads, director/shareholder/capital fields, deed history, and KYC-grade dossiers require paid access or an authorised provider path.

## Thailand

Source references:

- [DBD DataWarehouse link and description through Thailand OSMEP](https://en.sme.go.th/en/page.php?modulekey=430)
- [DBD DataWarehouse](https://datawarehouse.dbd.go.th/index)

Assumptions:

- DBD DataWarehouse is the official Department of Business Development source for juristic-person information and financial statement information.
- Public web access appears available, but direct automated access was not confirmed because the portal blocked automated fetch during this review.
- Thai and English UI availability does not imply permission for bulk or hosted redistribution.

Public-only boundary:

- A Thailand pack can begin with manual examples, source links, and fixture-backed parsing.
- Public-preview live lookup requires documented DBD terms, rate-limit behavior, and no bypass of CAPTCHA or bot controls.

Partner-required boundary:

- Bulk monitoring, hosted watchlists, high-volume search, director/shareholder enrichment, paid reports, or resale of DBD-derived records requires explicit permission or a licensed intermediary.

## Vietnam

Source references:

- [Vietnam feasibility note](./vietnam-feasibility.md)
- [National Business Registration Portal](https://dangkykinhdoanh.gov.vn/en/pages/default.aspx)
- [Decree 01/2021/ND-CP official record](https://vanban.chinhphu.vn/default.aspx?docid=202344&pageid=27160)

Assumptions:

- Article 36 supports a narrow set of free public enterprise-registration fields.
- The portal is HTML-first and no stable public API was identified during the feasibility pass.
- Automated scraping and hosted redistribution remain unapproved until terms and technical controls are reviewed.

Public-only boundary:

- Keep Vietnam as a feasibility note, fixture parser, or community proposal only.

Partner-required boundary:

- Any live automation, bulk lookup, paid hosted workflow, or source-derived redistribution requires permission, terms review, or an authorised data partner.

## Philippines

Source references:

- [SEC API Marketplace](https://dev-api.sec.gov.ph/)
- [SEC API documentation PDF](https://portal.sec.gov.ph/home/guides/API_DOCUMENTATION.pdf)
- [eSECURE gateway](https://esecure.sec.gov.ph/)

Assumptions:

- The SEC API Marketplace advertises both free and paid API categories.
- The SEC Number API is described as free with a limited quota.
- Company Information Lookup includes broader company data such as official address, SEC number, registration status, secondary licences, AFS, and GIS, but is subscription-based.

Public-only boundary:

- A Philippines pack may start with a quota-limited SEC-number status proof-of-concept if API terms allow OSS and hosted use.

Partner-required boundary:

- Broad company information lookup, AFS/GIS access, certified documents, higher quotas, production hosted monitoring, and bulk workflows require SEC subscription terms and credential handling.

## Licensed Adapter Contribution Guidance

Licensed adapters are allowed only when they keep source obligations explicit:

1. Add a `country-pack/v1` envelope with `licensing.redistribution`, `licensing.commercialUse`, and `auth` set to the actual source terms.
2. Use country-specific environment variables such as `MY_API_*`, `ID_API_*`, `TH_API_*`, `VN_API_*`, or `PH_API_*`; do not reuse `SG_API_*` names for ASEAN packs.
3. Keep partner credentials server-side only. Never expose them through Vite `VITE_*` variables, browser bundles, examples, or logs.
4. Add tests for no-credential behavior, expired credentials, quota exhaustion, no-match, ambiguous-match, and upstream failure.
5. Preserve evidence, records, gaps, provenance, freshness, and limits.
6. Add a source-specific "no resale/no redistribution" limit when terms restrict downstream use.
7. Document whether hosted Dude may store raw source records, derived summaries only, or neither.
8. Do not merge adapters that rely on scraping controls being bypassed.

## Roadmap Implication

Malaysia and the Philippines are the clearest partner/subscription candidates. Thailand is the clearest public-preview candidate if DBD automation terms are acceptable. Indonesia and Vietnam should remain skeleton/feasibility work until paid-profile and automated-access constraints are resolved.
