# ASEAN Country-Pack Skeletons

Status: skeleton fixtures for Malaysia, the Philippines, Indonesia, and Thailand.

Checked on: 2026-05-17.

These packs keep Dude's Singapore contract intact while documenting public-only expansion boundaries. They are not stable production adapters and must not be treated as complete company-registry coverage.

## Malaysia (`my`)

Public-only inventory:

- [data.gov.my](https://data.gov.my/) is Malaysia's official open-data portal and API/documentation entrypoint.
- [SSM e-Info](https://www.ssm.com.my/Pages/Buy_Corporate_Information/e-Info.aspx) and the [SSM e-Info portal](https://prod.ssm-einfo.my/) are official SSM information channels.

Boundary:

- The skeleton can describe open-data discovery and a bounded public-source brief.
- SSM company profiles, business profiles, charges, financial comparisons, company watch, API integration, and bulk/hosted workflows require authorised SSM terms.

Initial tool contract:

- `my_public_registry_brief`: returns a `brief-envelope/v1` public-source inventory and gaps when authoritative SSM data is not available through an approved channel.

## Philippines (`ph`)

Public-only inventory:

- [SEC API Marketplace](https://dev-api.sec.gov.ph/) and SEC API documentation describe API products.
- SEC API Marketplace material describes an SEC Number API with a free daily quota and broader Company Information Lookup packages that are paid.
- [eSECURE](https://esecure.sec.gov.ph/) is the SEC account gateway for authenticated access.

Boundary:

- A public-only skeleton may support a quota-limited SEC-number proof-of-concept after credential and hosted-use terms are reviewed.
- Broad company information, AFS/GIS, certified documents, higher quotas, monitoring, and bulk workflows require SEC subscription terms.

Initial tool contract:

- `ph_sec_number_status`: uses an explicit SEC number and API credential path; returns gaps when the credential or quota is unavailable.

## Indonesia (`id`)

Public-only inventory:

- [data.go.id](https://data.go.id/) is Indonesia's national data portal.
- [OJK](https://www.ojk.go.id/) publishes official financial-sector information and lists.
- AHU company-profile access and OSS/NIB status checks remain term-review items before any live adapter.

Boundary:

- The skeleton can inventory public sources and document manual/fixture paths.
- AHU complete/latest company profiles, paid voucher records, directors, shareholders, capital, deed history, and hosted redistribution require authorised terms.

Initial tool contract:

- `id_public_registry_brief`: returns public-source discovery, known gaps, and partner-boundary notes rather than claiming a complete company lookup.

## Thailand (`th`)

Public-only inventory:

- [DBD DataWarehouse+](https://datawarehouse.dbd.go.th/index) is the Department of Business Development portal for juristic-person information.
- [data.go.th](https://data.go.th/) is Thailand's public open-data portal.

Boundary:

- A public-preview adapter is feasible only after DBD automated-use, rate-limit, CAPTCHA, caching, and hosted-use terms are reviewed.
- Bulk monitoring, enriched ownership/financial packs, or high-volume hosted redistribution require explicit permission or a licensed intermediary.

Initial tool contract:

- `th_dbd_public_brief`: records the DBD public-search path, expected manual lookup gaps, and source limits.

## Shared Success Criteria

Each skeleton fixture must validate against `CountryPackEnvelopeSchema` and include:

- auth, licensing, freshness, and public-data limits
- at least one bounded tool contract
- no-match or blocked-path examples
- contribution notes for tests, source terms, and upstream-failure handling
- explicit limits for paid data, private ownership/control, and advisory use
