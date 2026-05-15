# WORKON-PIVOT-ASAP

Direction document for Dude. Open-core, SG SMEs + corp-services first, ASEAN expansion via country-pack framework. Honest, non-sycophantic.

Date: 2026-05-15.

---

## 0. Commercial reality check (carry-over from review)

Strong codebase, weak commercial proposition as-is. The author's own [docs/product-audit.md](./docs/product-audit.md) and [docs/developer-adoption-audit.md](./docs/developer-adoption-audit.md) already concede: infrastructure, not outcomes. Retention concentrated in ~10 of 105 tools. First-run macro brief still mis-resolves CPI to a GDP dataset.

Structural blockers to a standalone paid product today:

1. **Regulatory positioning.** ACRA has only 4 authorised ISPs (Handshakes, CRIF BizInsights, Experian QuestNet, SCCB). Dude is not one. Commercial redistribution of ACRA-derived diligence outputs is at minimum ToS-fragile without an ISP partnership or sub-licence. [Inference] OneMap and URA also have commercial-use clauses that need explicit review before paid shipping.
2. **No moat.** Data is 100% public. Defensibility = engineering hygiene, which is copyable. By early 2026 there are 10k+ MCP servers indexed publicly; "MCP for SG" is one weekend away from being cloned.
3. **Buyer mismatch.** Compliance/KYC buyers want sanctions, PEP, adverse media, UBO, SOC 2, SLAs, indemnity. Dude has none. SME/founder buyers can buy BizFile profiles at S$5.50 each. Agent builders expect free/OSS.
4. **Product gaps.** No accounts, saved searches, watchlists, alerts, bulk lookup, audit logs, team features, API keys, billing. None of the SaaS hooks.
5. **Solo maintainer.** Procurement-blocker for any enterprise > 10 people.
6. **SG-only TAM.** A premium diligence niche tops out at a few thousand seats.

Strengths worth preserving:

- Bounded-envelope design (`evidence`/`gaps`/`provenance`/`freshness`/`limits`) is genuinely above-average.
- `sg_query` as deterministic bounded router is a credible answer to "fake planner" MCP servers.
- Operational discipline (verify gate, smoke tests, structured logging, parity checks) is above what most MCP repos ship.
- 38-family catalog breadth would take a competitor 2–4 months to replicate honestly.

Decision: **open-source it harder**, optimize for SG SMEs + corporate-services firms, expand ASEAN via plug-in country packs.

---

## 1. Reframe the product around a job, not a tool

Today Dude is "30-second SG due diligence." That is a feature, not a job. SMEs and corp-services buy outcomes.

Three candidate jobs to be done that fit the existing tech:

- **A. Vendor onboarding + PDPA-grade third-party risk.** "I'm an SME hiring a new supplier/contractor. Did I check enough to satisfy PDPA s.24 data-intermediary diligence + procurement governance?"
- **B. Client/counterparty CDD for corp-secretarial + accounting firms.** "Every new client onboarding takes me 40 min of BizFile lookups, sanctions screens, manual filing — make it a 3-minute audit-logged workflow."
- **C. SME tender/procurement intelligence.** "Show me everyone bidding on a GeBIZ tender vs. their ACRA + BCA/BOA/CEA status + adverse signals."

**Pick one and make it un-fuckable. Primary = B.** Corp-services firms have recurring spend, well-defined budgets (S$50–500/seat/mo is normal), and pain that BizFile alone doesn't solve. Existing code already covers ~60% of B.

---

## 2. Product depth — features that flip "evaluable" into "adoptable"

### 2a. Non-negotiables for any SME buyer (currently missing)

- **Accounts + multi-seat** with workspace isolation and RBAC (admin / analyst / viewer).
- **Persistent dossiers.** Every lookup auto-saves to a workspace folder. Export to PDF / CSV / JSON with signed manifest.
- **Audit log.** Who ran what, when, against which dataset version, with hash. This is what makes diligence defensible in front of MAS / PDPC / an auditor.
- **Watchlists + alerts.** Pin entities; notify on ACRA status change, GeBIZ tender, COE/MOH/HSA licence change, adverse RSS feed. Reuse existing `sg_gov_feed_items`.
- **Bulk CSV upload.** Paste 200 UENs, get 200 dossiers + a summary risk grid. This single feature converts more corp-services buyers than the next 10 combined.
- **2FA + SSO** (Google / Microsoft). Corp-services firms expect this.

### 2b. Real differentiation features

- **OpenSanctions integration.** Free + permissive licence. Brings PEP + 200+ sanction lists + UBO links. Closes the biggest credibility gap vs. Handshakes/Refinitiv at zero data cost.
- **OpenCorporates cross-link.** They're already linked to OpenSanctions; gives global subsidiary/branch context for SG entities.
- **Adverse-media lite.** RSS + State Courts cause list + bankruptcy/wind-up gazette feeds. Bounded, source-cited, no opaque NLP.
- **UBO graph.** Even shallow (director/shareholder edges from ACRA + sibling-entity rollups by shared address/director). Use the deferred Graphviz scaffold already in the repo.
- **PDPA s.24 / s.26 vendor-diligence template.** Pre-built checklist + report template aligned to PDPC guidance. SME-DPO buyers will pay for this alone.
- **SG risk rules pack.** Open YAML rules: shell-co heuristic = paid-up capital < S$1, registered office matches known nominee address, struck-off-then-restored within 24 mo, etc. Ship rules as OSS so the community audits them.

### 2c. Distribution format

- **Embeddable widget.** Iframe / web-component any corp-services firm drops into their own client portal. White-label.
- **Browser extension.** Overlays a Dude dossier when the user hovers a UEN on BizFile+, a tender PDF, a contract draft.
- **Google Sheets / Excel add-in.** Resolves a column of UENs into dossier columns. SME accountants live in Sheets.

---

## 3. Open-source hygiene that "harder" actually requires

"Open-source it harder" is mostly distribution + governance, not code.

- **Publish to npm** as `@dude/mcp`, `@dude/sdk`. The current `private: true` + unpublished state blocks every funnel.
- **List on every MCP registry that matters.** modelcontextprotocol.io reference list, Smithery (already have `smithery.yaml`), Glama (already have `glama.json`), MCP-Hive, Awesome-MCP, mcp.so. Each is a backlink + discovery.
- **Governance out of solo control.** CONTRIBUTING.md with explicit "we accept country packs" pattern, CODE_OF_CONDUCT.md, 2–3 person maintainer team (seed with friends if needed), CLA or DCO, monthly office-hours call.
- **Donate to a neutral home.** Propose `sg-apis-mcp` as community package under Agentic AI Foundation (AAIF), an Asia-Pacific MCP working group, or Open Government Products. Fastest credibility unlock vs. "solo Singaporean repo."
- **Licence revisit.** MIT is fine; consider Apache-2.0 for the patent grant if any enterprise asks. Or BSL → Apache (Sentry / Cal.com pattern) if a hosted tier needs protection.
- **Public roadmap on GitHub Projects.** Surface `docs/roadmap` as Issues with `good-first-issue` labels.
- **Reference deployments.** Three named users (a corp-secretarial firm, an SME, a journalist) publicly saying they use it. Logos on README convert more than any feature.
- **Versioned schemas + CHANGELOG** following semver + ecosystem deprecation rules. Signals "depend on us in production."
- **Public benchmark / uptime page.** Hosted Grafana or static status.json. `sg://benchmarks` already exists; expose as public URL.

---

## 4. ASEAN expansion — realistic sequencing

SG openness is unusual. ASEAN access drops fast.

| Country | Registry | Accessibility | Strategy |
| --- | --- | --- | --- |
| MY | SSM e-Info | Paid per-search; some open via MAMPU | `my-apis-mcp` skeleton on MAMPU + court datasets; SSM behind licensed-partner adapter |
| ID | AHU + OJK | AHU semi-public, OJK requires login | OJK published lists + data.go.id mirrors |
| TH | DBD DataWarehouse | Subscription, partial open | Public-only OSS adapter; partner TH ISP for paid |
| VN | National Business Registration Portal | HTML-only | Lowest priority; community-contributed if at all |
| PH | SEC Express + DTI + data.gov.ph | Partial open | Mid-priority; PH SME services market is large |

**Mechanism: country-pack architecture.** Refactor `packages/mcp-server` so each pack exposes the same envelope shape. ASEAN expansion becomes a community-contribution surface; you maintain the contract.

This turns "ASEAN" from a 5-country build into a framework + 1 pack you maintain (SG) + N community packs. Cal.com / Strapi pattern.

**Recommended order:** SG (done) → framework refactor → MY skeleton → PH → ID → TH → VN.

---

## 5. Business model — open-core that won't cannibalize itself

| Layer | Audience | Price | Contents |
| --- | --- | --- | --- |
| **OSS core** (`@dude/mcp`, `@dude/sdk`, country packs) | Devs, agent builders, researchers, journalists, civic | Free, MIT/Apache | All data wrappers, brief envelopes, CLI, MCP server, rules packs |
| **Self-host Dude Web** | SMEs with engineering capacity | Free (open-core) | Web app + REST gateway, self-hostable via Docker compose |
| **Dude Cloud** | Corp-services firms, SMEs without engineering | S$29/seat/mo analyst, S$99/seat/mo firm | Hosted, SLA, SOC 2 path, ISP-licensed data adapters, support, training, audit log, SSO, bulk, watchlists |

**Critical rule: never put a data source behind the paywall that's free upstream.** Paywall the workflow — multi-seat, audit, bulk, alerts, SLA, support, ISP-licensed feeds. WorkOS / PostHog / Cal.com pattern; doesn't generate the OSS resentment that "open-core but the good parts are paid" does.

Optional fourth lane: **certified consulting partners.** Train and certify corp-services firms to deliver "Dude-powered diligence" downstream, take 10–20% rev-share. Odoo / HubSpot scaling pattern in SEA.

---

## 6. Distribution — how SG corp-services firms actually find you

Corp-services firms do NOT discover tools via Hacker News.

- **ACCA, ISCA, SCCA, SAL events.** Speak once a quarter at each. ISCA tech-adoption track = highest leverage.
- **PSG (Productivity Solutions Grant).** Subsidises up to 50% of pre-approved SME software. If Dude Cloud gets PSG-listed, every SG SME effectively gets it half-price. Highest-ROI commercial move available. Budget 2–4 months to apply.
- **GeBIZ / SGTech / AGIL accreditation.** Government SMEs and stat boards can procure once approved.
- **LinkedIn long-form + newsletter** targeted at SG DPOs and CFOs of 10–200-person firms. Weekly diligence-case-study ("we ran X firm through Dude — here's what we found in 30 sec").
- **Affiliate with secretarial-software incumbents** — Sleek, Osome, Lanturn, BoardRoom. They handle compliance for 50k+ SG SMEs and currently bolt diligence onto manual workflows. Embedded API deal > direct competition.
- **One Big-4 audit firm's innovation lab.** Even a free MOU gives credibility logos.

---

## 7. Compliance + regulatory must-do's (cannot ship paid without)

- **ACRA ISP application** or formal sub-licence via Handshakes/CRIF/Experian/SCCB. Until resolved, Dude Cloud cannot legally re-distribute Bizfile profiles even though public-dataset shards are okay.
- **PDPA notification + DPO appointment.** Required for any service holding personal data on SG residents. Trivial cost, mandatory signal.
- **MAS Outsourcing Notice 658** considerations if selling to MAS-regulated firms. They will ask for BCP, sub-contractor list, data-residency.
- **SOC 2 Type I roadmap.** Drata / Vanta automates most of it for ~S$15k/yr. Required for any FI-adjacent buyer.
- **Data Processing Agreement template.** Needed before any corp-services firm can hand you their client data.
- **Explicit "not legal/financial advice"** disclaimer with a separate "compliance use" clause referencing which laws each rules-pack maps to.

---

## 8. Concrete 90-day shape

| Wk | Theme | Output |
| --- | --- | --- |
| 1–2 | Repo packaging | Publish `@dude/mcp`, `@dude/sdk` to npm; list on Smithery / Glama / MCP-Hive; add CONTRIBUTING + maintainer team |
| 3–4 | OpenSanctions + adverse-media integration | `sg_sanctions_screen` tool + RSS adverse feeds; bench against 50 known shell companies |
| 5–6 | Accounts + bulk CSV + audit log MVP | Self-host Docker compose ready; private beta with 2 corp-secretarial firms |
| 7–8 | PDPA s.24 vendor-diligence template + PDF export polish | Sellable artifact, used in 1 case study |
| 9–10 | Country-pack refactor + MY skeleton | Framework PR; first community contributor invited |
| 11–12 | PSG application + ACRA ISP enquiry | Regulatory track open; SOC 2 gap analysis started |

End-state at 90 days: public OSS project, 3 named pilot users, MY pack skeleton, PSG application in flight. Credible path to a sellable thing.

---

## 9. Brutally honest risks to plan around

- **GovTech ships their own SG MCP.** Possible. Mitigation: be already-installed, already-trusted, already-PSG-listed before that happens.
- **Solo-maintainer collapse.** Biggest risk. Recruit ≥1 co-maintainer in the first 60 days even if unpaid. OSS-momentum claim is not credible with one Git author.
- **ASEAN data licensing surprises.** Set expectation in docs that some packs ship "official public data only" and partnerships required for paid coverage.
- **Free OSS depresses paid uptake.** Only if the paid tier paywalls data. Don't. Paywall workflow.
- **PDPC enforcement on data-intermediary status.** The moment Dude processes a customer's personal data, you ARE a data intermediary. Handle with DPA + DPIA up front, not after onboarding.

---

## 10. Sources

- OpenSanctions: https://www.opensanctions.org/ , https://github.com/opensanctions/opensanctions , https://www.opensanctions.org/docs/enrichment/
- OpenCorporates ↔ OpenSanctions linkage: https://blog.opencorporates.com/2022/07/19/opencorporates-identifiers-now-in-opensanctions-a-win-for-the-open-data-ecosystem/
- OSS KYC prior art: https://github.com/vyayasan/kyc-analyst
- ACRA Authorised ISPs: https://www.acra.gov.sg/how-to-guides/buying-information/our-partners
- ACRA Buying Business Information: https://www.acra.gov.sg/resources/buying-business-information/bizfile-and-other-sources/
- Handshakes (ACRA ISP): https://www.handshakes.ai/
- Kyckr SG Corporate Register Guide 2026: https://www.kyckr.com/blog/singapore-corporate-register-acra-guide
- PDPA SME guide (HeySara): https://heysara.sg/singapore-pdpa-compliance-2026-sme-guide/
- PDPA third-party risk (Atlas Systems): https://www.atlassystems.com/complyscore/compliance/pdpa-singapore
- SG Government Developer Portal: https://www.developer.tech.gov.sg/products
- Open Government Products: https://www.open.gov.sg/
- GovTech SGTS: https://www.tech.gov.sg/products-and-services/for-government-agencies/software-development/sg-tech-stack/
- MCP 2026 adoption + monetization: https://medium.com/mcp-server/the-rise-of-mcp-protocol-adoption-in-2026-and-emerging-monetization-models-cb03438e985c
- MCP donated to Agentic AI Foundation: https://www.anthropic.com/news/donating-the-model-context-protocol-and-establishing-of-the-agentic-ai-foundation
- Top vendor due-diligence platforms (Procurement Magazine): https://procurementmag.com/top10/top-10-vendor-due-diligence-platforms
- WorkOS — MCP in 2026: https://workos.com/blog/everything-your-team-needs-to-know-about-mcp-in-2026
