# TODO — Caregiver and Eldercare Extension

Scoping doc for extending `sg-apis-mcp` to support two problem statements:

> **PS1 — Empowering Caregivers.** How might we enable and empower caregivers who are caring for seniors or PWDs so that they can alleviate caregiver fatigue and burnout?
>
> **PS2 — Streamlining Eldercare.** How might we reduce manual and time-consuming tasks within the eldercare ecosystem so that more seniors are well-supported?

Use this file as the planning surface. Each item maps to a concrete code change that should ship as its own commit, following the existing patterns (bounded briefs, deterministic versioned rules, drift alarms, runnable outcome examples).

---

## Why this fits the repo

The repo's core thesis is *agents should not guess about Singapore data*. PS1 and PS2 are fragmented-public-data problems — exactly the wedge:

- Caregivers must today consult **6–8 separate agencies** (AIC, MOH, MSF, HDB, CPF, IRAS, PA, NCSS) to assemble one care plan.
- Subsidy eligibility involves **deterministic rules with means-test thresholds** that drift each Budget — the same shape as the housing advisor.
- The "next-action checklist" pattern already shipped in `sg_property_brief` and `sg_business_dossier` is the right shape for caregiver hand-off artifacts.

Reuse, not invent.

---

## Current coverage assessment (~40–50%)

These existing tools/briefs are already directly usable by a caregiver agent:

| Existing surface | Caregiver use case |
|---|---|
| `sg_moh_facilities` | Hospitals + polyclinics around senior's address |
| `sg_msf_family_services` | Family Service Centres (FSC) for caregiver counselling |
| `sg_msf_social_service_offices` | SSO for ComCare, financial assistance |
| `sg_msf_student_care_services` | Sandwich-generation caregivers with school-age kids |
| `sg_pa_community_outlets` | Senior activity centres, befriending programmes |
| `sg_sportsg_facilities` | Active-ageing programmes |
| Housing advisor (Proximity Housing Grant) | Already a caregiver-incentive scheme; reframe summary copy |
| `sg_onemap_route` + `sg_transport_brief` | Travel-time burden calc to/from senior's home |
| `sg_environment_brief` | Outdoor advisory for elderly (heat, PSI > 100) |
| `sg_civic_brief` modules filter | Already extensible — add an `eldercare` module |
| `sg_govfeeds_articles` | MOH/AIC/MSF subsidy announcement filter |

The remaining 50–60% is what we need to build.

---

## Build plan — PS1: Empowering Caregivers

### A. `sg_aic_services` — direct tool (highest leverage single addition)

**What:** Wrap the Agency for Integrated Care service directory: day care centres, home care, nursing homes, dementia day care, community befrienders, respite care, hospice care.

**Why:** AIC is the single most important agency for caregivers and the repo currently has zero AIC coverage. Without this, every other caregiver workflow has a hole at the centre.

**Inputs:**
- `serviceType: "day_care" | "home_care" | "nursing_home" | "dementia_day_care" | "respite" | "hospice" | "community_befriender"`
- `lat`, `lng`, `radiusKm` — coordinate-based discovery, same shape as `sg_msf_*`
- `postalCode`, `address` — convenience that geocodes via OneMap
- `name` — exact-match filter

**Output:** standard direct-tool record envelope (`records[]` + provenance + freshness).

**Dependencies / unknowns:**
- `[Unverified]` AIC publishes some directories via data.gov.sg (e.g. `d_eldercare_services`); confirm coverage and licensing before building.
- If only HTML scraping is available, build the client around the same html-fetch + parse pattern used for `sg_law_search` and accept the staleness trade-off.

**Acceptance criteria:**
- Returns ≥ 1 record per service type within Singapore.
- `sg_health_check` probe added.
- `examples/integration/outcomes/eldercare-finder.ts` runnable end-to-end without auth.

**Commit shape:** `feat(aic): add sg_aic_services direct tool`.

---

### B. `sg_caregiver_brief` — bounded brief

**What:** A `BriefArtifact` aggregating respite + day care + financial schemes + family services + transport context for one senior's address.

**Why:** Today a caregiver must call AIC + MSF + HDB + CPF + the local FSC just to plan one week. One brief, one envelope.

**Envelope:** standard `{title, summary, evidence, records, gaps, provenance, freshness, limits, riskFlags, nextChecks, matchConfidence}`.

**Required `summary[]` fields:**
- Resolved postal code / planning area (with `address confidence` carried over from property brief pattern).
- Nearest day care + distance (km).
- Nearest respite care + distance.
- Nearest FSC + distance.
- Estimated subsidy eligibility (true / false / insufficient_input) per scheme — pulled from `sg_caregiver_advisor` (see C).
- "Sandwich generation" boolean if `sg_ecda_childcare_centres` is also relevant for the household.

**Required `riskFlags`:**
- `LONG_DAY_CARE_WAITLIST` — `[Inference]` AIC publishes wait-time hints; if not, surface as a `[Unverified]` advisory limit.
- `INCOME_OVER_HCG_CEILING` — caregiver/senior household income exceeds Home Caregiving Grant means test.
- `NO_PROXIMITY_TO_PARENTS_KNOWN` — when caller has not declared whether they live ≤4 km from the senior (relevant for HDB Proximity Grant + caregiver burden).

**Required `nextChecks`:**
- `sg_aic_services` for deeper day-care drilldown.
- `sg_caregiver_advisor` for full eligibility computation if not already run.
- `sg_msf_family_services` for caregiver counselling.
- `sg_govfeeds_articles` filtered to caregiver topics.

**Routing:** add to `sg_query` via the civic_discovery family — keyword hints: `caregiver`, `day care`, `respite`, `dementia`, `nursing home`, `senior`, `eldercare`. Fallbacks listed in `RECIPE_FALLBACK_TOOLS`.

**Commit shape:** `feat(brief): add sg_caregiver_brief bounded artifact`.

---

### C. `sg_caregiver_advisor` — deterministic versioned rules (same pattern as housing advisor)

**What:** Eligibility + entitlement compute over caregiver financial schemes. Pure rules, no upstream calls. Versioned.

**File:** `packages/mcp-server/src/caregiver/rules-2026.json` — mirror of `housing/rules-2026.json` shape.

**Top schemes to cover (priority order):**
1. **Home Caregiving Grant (HCG)** — $400/month means-tested. PCHI ceiling, requires ADL assessment, etc. `[Unverified]` confirm latest amount each Budget.
2. **Caregiver Training Grant (CTG)** — $200 grant for accredited courses.
3. **Seniors' Mobility & Enabling Fund (SMF)** — subsidies for mobility devices.
4. **ElderFund** — for severely disabled seniors not covered by CareShield.
5. **CareShield Life premiums** — auto-enrol deferred classes; surface premium estimate by birth year.
6. **Pioneer Generation / Merdeka Generation** subsidies — birth-year-based, deterministic.
7. **CHAS Blue / Orange / Green** — outpatient subsidies; means-tested by PCHI.

**Inputs:**
- `senior`: { age, citizenship, conditionsAdl, monthlyIncomeSgd, householdMembers }
- `caregiver`: { age, citizenship, employmentStatus, residesWithSenior }
- Optional: `pchi` (per-capita household income).

**Outputs (mirroring `sg_grant_eligibility`):** `eligible[]`, `ineligible[]`, `totalEstimatedSgd`, `rulesVersion`, `rulesLastVerified`, `assumptions[]`, `nextDocuments[]` (the document checklist — see PS2).

**Drift alarm:** `scripts/check-caregiver-rules-freshness.mjs` (clone of `check-housing-rules-freshness.mjs`); wire into `npm run verify` and a monthly GitHub Action mirroring `housing-rules-freshness.yml`.

**Commit shape (split):**
- `feat(caregiver): add caregiver-rules-2026 with HCG, CTG, SMF, ElderFund` (one commit per cluster of schemes).
- `feat(caregiver): add sg_caregiver_advisor compute tool`.
- `chore(caregiver): wire caregiver rules freshness check into verify`.
- `ci: add monthly caregiver rules freshness workflow`.

---

### D. `sg_caregiver_training` — direct tool

**What:** Search SkillsFuture / AIC accredited caregiver courses by topic.

**Inputs:** `topic: "dementia" | "mobility" | "end_of_life" | "wound_care" | "general"`, `mode: "in_person" | "online" | "hybrid"`, optional date range.

**Why:** Course discovery is currently a manual MySkillsFuture search. Direct-tool wrap keeps it bounded.

**Dependencies:** `[Unverified]` MySkillsFuture has a public courses API; confirm before scoping.

**Commit shape:** `feat(caregiver): add sg_caregiver_training course directory`.

---

## Build plan — PS2: Streamlining Eldercare

### E. `sg_eldercare_journey` — router workflow (the headline integration)

**What:** One call replaces ~6 phone calls. Take a senior + caregiver profile, return a ranked care plan.

**Inputs:** `senior` (age, conditions, mobility, postalCode, monthlyIncomeSgd), `caregiver` (residesWithSenior, weeklyHoursAvailable, employmentStatus), preferences (`preferDayCare | preferHomeCare | preferRespite`).

**Steps (sg_query workflow):**
1. `sg_onemap_geocode` — resolve senior's postal code.
2. `sg_aic_services` — fetch nearest 5 facilities of preferred service type.
3. `sg_msf_family_services` — nearest 3 FSCs.
4. `sg_caregiver_advisor` — full subsidy eligibility.
5. `sg_transport_brief` (auto-include) — travel time from caregiver's address (if supplied) to each facility.
6. `sg_environment_brief` (auto-include) — outdoor heat/air-quality flag.
7. Composite ranking: facility distance + transport time + subsidised cost (after eligibility) + capacity (if AIC publishes).

**Output:** `BriefArtifact` with `summary[]` ranked-options table, `riskFlags` (`HIGH_BURDEN_FORECAST`, `INCOME_TOO_HIGH_FOR_HCG_BUT_LOW_FOR_CHAS_GREEN`, `NO_TRANSPORT_FALLBACK`), `nextChecks` (apply for X scheme, contact Y FSC, book trial day at Z facility).

**Commit shape:** `feat(query): add sg_eldercare_journey workflow`.

---

### F. Document checklist rules (extends advisor)

**What:** For each scheme in `caregiver-rules-2026.json`, encode required documents + processing time + application URL.

**Why:** Manual chase of "what do I need to apply" is a recurring caregiver complaint and pure deterministic logic.

**Shape:**
```json
"homeCaregiveGrant": {
  "documents": [
    "NRIC of senior and caregiver",
    "Functional assessment by polyclinic / GP",
    "Income proof (last 3 months payslip or NOA)"
  ],
  "applicationUrl": "https://www.aic.sg/...",
  "processingDaysMin": 10,
  "processingDaysMax": 30,
  "appliesVia": "AIC online / SSO walk-in"
}
```

Surfaces in advisor output as `nextDocuments[]` and in `sg_caregiver_brief` as `records.documentChecklist`.

**Commit shape:** `feat(caregiver): add document checklist rules + nextDocuments output`.

---

### G. `sg_caregiver_burden_brief` — pure-compute brief

**What:** Given a recurring task list (medication times, appointments, meal prep, transport runs), return weekly hour count, peak-load day, batching opportunities.

**Why:** Caregiver fatigue is quantifiable. The pattern matches `sg_housing_affordability` — pure inputs, pure compute, deterministic verdict.

**Inputs:** `tasks: [{ name, frequencyPerWeek, durationMinutes, requiresPhysicalPresence }]`, `caregiverWeeklyHoursAvailable`.

**Outputs:**
- `weeklyHoursTotal`
- `weeklyHoursDelegatable` (tasks not requiring physical presence)
- `peakLoadDayEstimate` (heuristic)
- `verdict: "sustainable" | "tight" | "burnout_risk"` (mirroring affordability's `fits | tight | over_budget`)
- `batchingSuggestions[]` (e.g., consolidate transport runs, use telemedicine for non-physical follow-ups).

**Commit shape:** `feat(caregiver): add sg_caregiver_burden_brief compute tool`.

---

### H. Caregiver-scoped gov-feed monitor

**What:** Pre-set filter on `sg_govfeeds_articles` that returns only caregiver/eldercare-relevant announcements (MOH, AIC, MSF, HDB Proximity Grant changes, Pioneer/Merdeka updates).

**Why:** Subsidies and means-test thresholds change mid-year; without a filter the caregiver misses them.

**Implementation:** add `topic: "caregiver"` enum to existing `sg_govfeeds_articles` schema OR ship as a runnable outcome example under `examples/integration/outcomes/caregiver-monitor.ts` that hard-codes the source/topic filter.

**Commit shape:** `feat(govfeeds): add caregiver topic filter` OR `docs(examples): add caregiver-monitor outcome script`.

---

### I. Outcome examples

Mirror the existing `examples/integration/outcomes/*.ts` pattern. Each script must be runnable end-to-end against the local server.

| Script | Outcome |
|---|---|
| `eldercare-finder.ts` | Senior postal code → nearest day care + respite + nursing home options. |
| `caregiver-subsidy-check.ts` | Profile → ranked subsidy entitlements + total $/month + document checklist. |
| `caregiver-burden-audit.ts` | Task list → weekly burden + batching suggestions. |
| `eldercare-journey.ts` | Full senior + caregiver profile → ranked care plan with subsidies + transport. |
| `caregiver_journey.py` | Python job-runner equivalent (mirrors `sme_diligence_dashboard.py` pattern). |

**Commit shape:** one commit per script (`docs(examples): add <name> outcome script`).

---

## Data licensing and trust caveats — must verify before building

- `[Unverified]` AIC service directory licensing: confirm via aic.sg / data.gov.sg whether facility data is API-accessible. Without this, items A and E drop from "high-leverage" to "blocked".
- `[Unverified]` MySkillsFuture courses API: confirm public access and rate limits.
- `[Unverified]` Subsidy means-test thresholds and quantums update at most Budgets and at unannounced interim updates. The drift-alarm (item C) is genuinely load-bearing — plan a manual re-verification each Feb mirroring the housing rules cadence.
- **No medical advice.** Same trust boundary as `sg_law_search`. Briefs surface scheme + facility data only; never recommend treatments, prognosis, or care arrangements.
- **PWD coverage** in PS1 is broader than seniors. SG Enable directory + assistive-tech listings would need their own family (`sg_sgenable_*`). Out of scope for the first pass; flag in roadmap as a sibling track.

---

## Suggested execution order (sharpest first build)

The minimum-viable wedge is **A + B + C (HCG only) + I (eldercare-finder)**. One weekend of work, four commits, immediately useful.

1. Verify AIC + MySkillsFuture data licensing (1 hour, blocks everything else).
2. `feat(aic): add sg_aic_services` (item A).
3. `feat(caregiver): add caregiver-rules-2026 with HCG` — start with one scheme to validate the rules file shape (item C, partial).
4. `feat(caregiver): add sg_caregiver_advisor compute tool` (item C).
5. `feat(brief): add sg_caregiver_brief` (item B).
6. `docs(examples): add eldercare-finder outcome script` (item I, partial).
7. Drift alarm + CI workflow for caregiver rules (item C, finishing).
8. Layer in additional schemes (CTG, SMF, ElderFund, PG, MG, CHAS) one commit each.
9. `feat(query): add sg_eldercare_journey workflow` (item E).
10. Burden brief + remaining outcome examples (items G + I).

Each step is independently shippable. The bounded-brief and rules-versioned patterns are already proven in this repo, so the cost of adding each is small.

---

## Acceptance for "this extension shipped"

- `sg://recipes` includes ≥ 4 caregiver/eldercare recipes with prompt metadata.
- `sg://playbooks` includes a "Caregiver journey" persona playbook.
- `npm run verify` includes the caregiver rules freshness check.
- `examples/integration/outcomes/` contains ≥ 3 runnable caregiver scripts; all pass `npm run test:smoke:outcomes`.
- `docs/operating-expectations.md` lists AIC + caregiver rules tier as a new family row with cache TTL + freshness rule.
- `docs/ship-in-2-days.md` is updated with a caregiver-flow worked example.
- A `caregiver-rules-freshness.yml` GitHub Action exists and runs monthly.
- Housing advisor's existing Proximity Housing Grant copy is updated to reference the new caregiver advisor as a cross-link.

When all of the above is true, this TODO can be archived under `docs/roadmap/`.
