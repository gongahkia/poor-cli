# Singapore Accreditation And Market-Access Track

This track evaluates GeBIZ, SGTech, and IMDA accreditation/readiness paths for Dude. It is a go-to-market readiness document, not a claim that Dude is registered, accredited, approved, or endorsed.

## Success Definition

- GeBIZ, SGTech, and IMDA/AGIL-adjacent requirements are inventoried from current public sources.
- Each path is assessed for relevance to Dude's stage.
- A recommended readiness order is documented.
- Follow-up tasks are scoped before any application or public claim.

## Source Baseline

Observed on 2026-05-17:

- [GeBIZ FAQ](https://www.gebiz.gov.sg/faq.html) says suppliers who want to respond to electronic tenders/quotations/qualifications need to register as GeBIZ Trading Partners, business entities need Corppass, and GeBIZ Trading Partner/Government Registered Supplier registration is not a licence to conduct business in Singapore.
- [GeBIZ GTP registration](https://www.gebiz.gov.sg/ptn/gtpregistration/signup.xhtml?faces-redirect=true) says suppliers must register as GeBIZ Trading Partners to do business with Government Agencies, and registration requires company information and nominated Authorised Representatives.
- [GovTech procurement guidance](https://www.developer.tech.gov.sg/guidelines/procurement/gebiz) describes GeBIZ as Singapore Government's one-stop e-procurement portal where public-sector ICT ITQs and tenders are posted.
- [SGTech about page](https://www.sgtech.org.sg/aboutUs) describes SGTech as Singapore's leading tech trade association with more than 1,400 member companies.
- [SGTech membership page](https://www.sgtech.org.sg/membership/CategoriesAndFees) is the membership entrypoint, but current browser capture surfaced login/change-password chrome instead of complete fee/category detail. Manual validation is required before application.
- [SMEs Go Digital vendor page](https://www.sgd.org.sg/) lists SGTech-operated vendor briefing/checklist submission materials for SMEs Go Digital pre-approved solutions and points enquiries to `SGD@sgtech.org.sg`.
- [IMDA Accreditation](https://www.imda.gov.sg/How-We-Can-Help/IMDA-Accreditation) says the programme accredits promising Singapore-based high-growth ICM product companies, evaluates Technical, Financial, and Operations aspects, and lists `accreditation@imda.gov.sg` for enquiries.
- The same IMDA page says the SecureTech track requires Common Criteria certification for the product to be accredited.

## AGIL Naming Note

I could not verify a current official Singapore programme literally named "AGIL accreditation" from public sources during this pass. The closest relevant official path appears to be IMDA Accreditation@SG Digital, including its SecureTech track, Tech Acceleration Lab, and related "Green Lane" market-access language.

Action: confirm whether "AGIL" in the issue refers to an internal acronym, a partner programme, IMDA Accreditation/Green Lane, or a separate body before making any external claim.

## Path Inventory

| Path | What it unlocks | Current requirements / signals | Dude relevance | Stage fit |
| --- | --- | --- | --- | --- |
| GeBIZ Trading Partner | Ability to log in and respond to government electronic tenders/quotations/qualifications. | Company information, Corppass, nominated Authorised Representatives, GeBIZ registration. Government Supplier Registration for supply heads has separate documentation and financial/accounting evidence. | Useful for public-sector procurement discovery and response, not a product-quality accreditation. | Later, after legal entity and sales owner exist. |
| SGTech membership | Trade association credibility, committees/advisory groups, networking, government procurement and digital-trust channels. | Membership application/category validation; current public page needs manual fee/category confirmation. | Useful for partner pipeline, event access, digital-trust/procurement advisory channels. | Good near-term once operating entity is clear. |
| SMEs Go Digital / SGTech vendor pre-approval | Potential route for SME grant-assisted sales if Dude becomes an eligible solution. | Vendor briefing, self-assessment checklist, solution brochure/screenshots, latest financial statements, invoices to current SME customers, customer satisfaction survey. | Relevant only after Dude has paying SME customers, support, invoicing, and a repeatable solution package. | Not ready; revisit after hosted beta evidence. |
| IMDA Accreditation@SG Digital | Credibility and market access for high-growth Singapore-based ICM product companies, including government/enterprise buyers. | IMDA evaluates technical, financial, and operations aspects; programme targets Singapore-based high-growth product companies. | High credibility, but requires mature product, customers, operations, financials, and local company posture. | Later, after reference deployments and hosted controls. |
| IMDA SecureTech track | Accreditation path for cybersecurity products; requires Common Criteria certification. | SecureTech track under IMDA/CSA; CC certification required for product accreditation. | Dude is not currently a cybersecurity product with CC certification scope. | Not a fit unless product scope changes materially. |
| IMDA Tech Acceleration Lab / Green Lane | PoC-to-production support and shorter enterprise/public-sector procurement cycle. | Tied to IMDA Accreditation ecosystem and enterprise/government PoCs. | Useful after a real public-sector/enterprise PoC sponsor exists. | Later. |

## Readiness Checklist

| Readiness area | Needed evidence |
| --- | --- |
| Legal entity | Singapore operating entity, ACRA registration, registered address, authorised representatives, Corppass access. |
| Product package | Stable hosted URL, product deck, pricing/entitlements, terms, privacy/DPA packet, support contact. |
| Security/compliance | PDPA/DPO readiness, DPA, subprocessor register, source-licensing gates, audit logs, retention/deletion, incident process. |
| Financial/ops | Latest financial statements, invoices, support process, customer success owner, uptime/status evidence. |
| Technical proof | Architecture, security controls, data-flow diagram, API docs, benchmark/status page, reference deployment evidence. |
| Customer evidence | Case studies, customer satisfaction survey, testimonials, renewal/usage metrics, production references. |
| Procurement readiness | GeBIZ account, supplier profile, sales owner, bid/no-bid criteria, template responses, non-advice and source-limit clauses. |

## Recommended Order

1. Finish hosted control prerequisites: workspace/RBAC, persisted dossiers, immutable audit log, SSO/2FA posture, source licensing, DPA/PDPA, subprocessor register.
2. Create legal-entity and Corppass readiness checklist before any GeBIZ/SGTech application.
3. Join SGTech or engage membership only after the operating entity, website, product packet, and owner are ready.
4. Register GeBIZ Trading Partner when there is an authorised representative and a concrete public-sector opportunity owner.
5. Revisit SMEs Go Digital pre-approval after repeatable SME paid deployments, invoices, customer satisfaction evidence, and support process exist.
6. Revisit IMDA Accreditation after at least three credible reference deployments, financial/ops evidence, and a product sponsor that benefits from the accreditation path.
7. Treat SecureTech/Common Criteria as out of scope unless Dude becomes a certifiable cybersecurity product.

## Follow-Up Tasks

- Confirm the intended meaning of "AGIL" and update this document with the exact programme/body if different from IMDA Accreditation/Green Lane.
- Create a legal-entity/Corppass readiness checklist for GeBIZ and SGTech applications.
- Draft a supplier one-pager: product description, buyer segment, non-advice boundary, source-licensing posture, support contact, hosted architecture.
- Prepare a procurement response template for public-sector CDD/public-data diligence opportunities.
- Build a customer-evidence folder with case studies, invoices, satisfaction survey, and screenshots before SMEs Go Digital or IMDA Accreditation.
- Assign one owner for all government/trade-association applications so claims remain consistent.

## Claims Policy

Until an application is approved:

- do not say Dude is GeBIZ registered, SGTech accredited, IMDA accredited, AGIL accredited, PSG pre-approved, or government endorsed;
- do not use official logos or lockups;
- do not imply registration is a licence or compliance certification;
- do not offer grant-assisted sales unless the exact programme approval exists for the exact solution and customer workflow.

## Decision

Near-term: prepare entity/procurement materials and validate SGTech membership manually.

Not ready: GeBIZ bidding, SMEs Go Digital pre-approval, IMDA Accreditation, SecureTech, or any AGIL/Green Lane claim.
