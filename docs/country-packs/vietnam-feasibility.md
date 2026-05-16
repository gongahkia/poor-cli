# Vietnam Country-Pack Feasibility

Status: feasibility-only, lowest priority.

Checked on: 2026-05-16.

ASEAN-wide licensing assumptions are tracked in [asean-licensing-assumptions.md](./asean-licensing-assumptions.md).

## Sources Reviewed

- [National Business Registration Portal](https://dangkykinhdoanh.gov.vn/en/pages/default.aspx), operated by Vietnam's business registration authorities.
- [Search engine overview on the National Business Registration Portal](https://demo.dangkykinhdoanh.gov.vn/en/News/615/4415/search-engine-on-the-national-business-registration-portal.aspx), describing instant and advanced search surfaces.
- [Decree 01/2021/ND-CP official record](https://vanban.chinhphu.vn/default.aspx?docid=202344&pageid=27160), with Article 36 coverage also visible through the national legal-document system.

## Available Public Surfaces

The portal appears to expose these public or semi-public surfaces:

| Surface | Feasibility note |
| --- | --- |
| Homepage and statistics | Public HTML pages with business-registration statistics and support links. Useful for market context, not entity diligence. |
| Search status of business registration | Public portal entrypoint for entity lookup. The visible surface is web UI, not a documented API. |
| Instant search | Portal guidance says users can search by enterprise name, short name, foreign-language name, enterprise code, or NBRS internal code. |
| Advanced search | Portal guidance describes filters for name, enterprise code, type, legal status, representative, head-office address, province/city, district, and ward/commune. |
| E-gazette / enterprise announcements | Public UI surface for enterprise announcements. Adapter feasibility depends on terms, pagination stability, and whether detail pages are reliably addressable. |
| Business-line search | Public search page exists, but should be treated as HTML-only until a stable machine interface is documented. |

Decree 01/2021/ND-CP Article 36 indicates that free public enterprise-registration information includes enterprise name, enterprise identification number, head-office address, business lines, legal representative full name, and legal status. That is enough for a narrow registry lookup if the access method is allowed and technically stable.

## Scraping And Automation Constraints

- No stable public API was identified during this pass.
- The official portal is HTML-first and may rely on scripts, sessions, localized pages, or dynamic search behavior.
- The portal exposes Terms of Use and Privacy Statement links, but automated-use permissions were not confirmed in this pass.
- Do not ship automated scraping, crawling, or hosted paid redistribution until terms, robots posture, rate limits, and caching rules are reviewed.
- Do not bypass CAPTCHA, session controls, paywalls, login flows, or technical anti-automation measures.
- Do not infer shareholder, director, beneficial-owner, subsidiary, or control-graph facts unless an official public field explicitly returns them.

## Why Vietnam Is Lowest Priority

- The current product pivot is Singapore corp-services CDD first; Vietnam support is not needed for that first-run workflow.
- Compared with Malaysia, Philippines, Indonesia, and Thailand skeletons, Vietnam currently looks more HTML-only and less adapter-ready.
- Licensing and automated-use permission are not clear enough for hosted or commercial workflows.
- A rushed adapter would likely create maintenance risk, false coverage expectations, and possible source-term risk.

## Community Contribution Path

A community-contributed Vietnam pack must prove the following before adapter code is accepted:

1. A completed `country-pack/v1` envelope with `packId: "vn"`.
2. Source terms review covering public-only use, attribution, caching, rate limits, automated access, and commercial hosted use.
3. A recorded-source parser for manually saved official pages before any live network adapter.
4. Tests for exact match, no match, ambiguous match, stale source, and upstream failure.
5. Output envelope with evidence, records, gaps, provenance, freshness, and limits.
6. Explicit public-data limits for ownership/control, advisory use, paid data, and legal status interpretation.
7. A maintainer review that confirms the pack does not widen into legal advice, tax advice, investment advice, or unsupported risk scoring.

## Proposed Initial Scope

If a contributor can satisfy the constraints above, the first Vietnam pack should be limited to:

- exact enterprise-code lookup where a stable detail page or permitted query path is available
- name search with ambiguity preserved as `gaps`
- legal-status and head-office-address fields when returned by the official public source
- no ownership, representative-liability, credit, sanctions, or adverse-media claims

Until those conditions are met, Vietnam should remain a documented feasibility item rather than an implementation task.
