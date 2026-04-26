# AGENTS.md — sg-apis-mcp

Conventional agent-instruction file. Read by Codex, Cursor, OpenAI Agents SDK, Aider, and any tool that follows the `AGENTS.md` convention. Claude Code users get the equivalent at `.claude/skills/sg-singapore-data/SKILL.md`.

This repository is **two products in one**:
1. An **MCP server** (`packages/mcp-server`) exposing 105 `sg_*` tools across 38 cataloged Singapore data and advisory families.
2. A **meta-prompt surface** (this file + `.claude/skills/`) that teaches agents how to use those tools deterministically.

If you are an agent reading this file, your job is to use the MCP tools instead of guessing about Singapore data.

---

## Hard rules

1. **Never invent values.** If you would say "I think the HDB grant is...", "SORA is around...", "the bus arrives in roughly...", **stop and call the tool**.
2. **Banks do not issue HDB grants.** Grants come from CPF/HDB. Banks issue home loans only. Correct any user who conflates them.
3. **Cite provenance.** Every tool returns `provenance`, `freshness`, or `rulesVersion` / `rulesLastVerified`. Surface freshness in your final answer.
4. **Use the bounded tool, not your training.** Singapore policy changes at Budget; training data is stale.
5. **No legal / tax / licensed-advisor opinions.** Summarize public data. Do not advise on whether to buy a flat, sue, or file taxes.

---

## Tool routing (cheat sheet)

| User asks about... | Preferred tool | Direct fallbacks |
| --- | --- | --- |
| BTO / resale affordability | `sg_housing_affordability` | `sg_grant_eligibility`, `sg_loan_compare`, `sg_mas_interest_rates`, `sg_hdb_resale_prices` |
| HDB / CPF grants | `sg_grant_eligibility` | (deterministic; no fallback) |
| HDB vs bank loan compare | `sg_loan_compare` | `sg_mas_interest_rates` (live SORA) |
| Resale price benchmark | `sg_resale_price_compare` | `sg_hdb_resale_prices`, `sg_ura_property_transactions` |
| Neighbourhood / postal context | `sg_property_brief` | `sg_onemap_geocode`, `sg_ura_*`, `sg_hdb_*`, `sg_lta_*`, `sg_nea_*` |
| Company / UEN diligence | `sg_business_dossier` | `sg_acra_entities`, `sg_gebiz_tenders`, `sg_bca_*`, `sg_boa_*`, `sg_hsa_*` |
| Macro / FX / SORA / GDP / CPI | `sg_macro_brief` | `sg_mas_*`, `sg_singstat_*`, `sg_mom_labour_stats` |
| Transport / bus / MRT | `sg_transport_brief` | `sg_lta_bus_arrivals`, `sg_lta_train_alerts`, `sg_lta_traffic_incidents` |
| Weather / air quality | `sg_environment_brief` | `sg_nea_forecast_2hr`, `sg_nea_air_quality`, `sg_nea_rainfall` |
| Public services discovery | `sg_civic_brief` | `sg_pa_*`, `sg_sportsg_*`, `sg_ecda_*`, `sg_msf_*`, `sg_moe_schools`, `sg_moh_facilities` |
| Transit ops / reliability | `sg_transit_ops_brief` | `sg_transit_*` (14 ops tools) |
| Dataset discovery | `sg_datagov_search` | `sg_datagov_resources`, `sg_datagov_rows`, `sg_datagov_browse` |
| Anything ambiguous | `sg_query` | (router; plans or executes a bounded workflow) |

---

## Output contract

Every brief tool returns this envelope:

```
title, summary, evidence, records, gaps, provenance, freshness, limits
```

In your final answer to the user:
- Lead with `summary` (3–5 bullets).
- Include `freshness` (when the data was observed).
- Mention `gaps` if any sub-source failed.
- Respect `limits` — don't widen scope into things the brief intentionally excludes.

---

## Housing advisor (BTO / resale flow)

The Housing Advisor tools are deterministic with embedded versioned rules. Walk the user through these steps; ask one cluster of questions per step.

1. **Intent**: BTO or resale? Single or family? First-timer or upgrader?
2. **Profile** (`sg_grant_eligibility`):
   ```jsonc
   {
     "profile": {
       "applicants": [
         { "age": 30, "citizenship": "citizen", "monthlyIncomeSgd": 5000, "employmentMonths": 24, "firstTimer": true }
       ],
       "maritalStatus": "married",      // single | married | joint_singles | fiance_fiancee
       "flatMode": "resale",            // bto | resale
       "flatSize": "4_room",            // 2_room | 3_room | 4_room | 5_room | executive
       "proximityToParents": "near"     // resale only: live_with | near | neither
     }
   }
   ```
   Surface `eligible[]`, `ineligible[]` with reasons, `totalSgd`, `rulesLastVerified`. If `lastVerified` is older than the most recent SG Budget (~Feb annually), warn the user.
3. **Target flat**:
   - BTO: prices set by HDB at launch. Use `sg_property_brief` for area context.
   - Resale: call `sg_resale_price_compare` with `town`, `flatType`, `askingPriceSgd`, `lookbackMonths`. Report `verdict`, `variancePercent`, `stats`. If `insufficient_data`, widen the lookback.
4. **Live SORA**: `sg_mas_interest_rates` with today's date. Read `sora` / `sora_3m`.
5. **Loan compare**: ask user to paste bank packages OR WebFetch from `dbs.com.sg`, `ocbc.com`, `uob.com.sg`, `sc.com/sg`, `hsbc.com.sg`, `maybank2u.com.sg`. Build `bankPackages[]`:
   ```jsonc
   { "bank": "DBS", "packageName": "3M SORA + 0.85%",
     "rateBasis": "sora_3m", "spreadBps": 85, "lockInYears": 2 }
   ```
   Call `sg_loan_compare`. Report HDB vs each bank, `bestByYear1`, `bestByLifetime`.
6. **Affordability** (`sg_housing_affordability`): collect `cashOnHandSgd`, `cpfOaBalanceSgd`, optional `otherMonthlyDebtSgd`. Report `verdict` (`fits` / `tight` / `over_budget`), `recommendedLoanSgd` and binding constraint (MSR 30% / TDSR 55% / LTV 75%), `downpayment.cashRequiredSgd` / `cpfOrCashSgd`, `bsdSgd`, `netCashOutlaySgd`, `monthlyInstalmentEstimateSgd`, `tdsrUtilization`, `msrUtilization`.
7. **Summary**: 3-bullet recommendation, `rulesVersion` + `rulesLastVerified`, source URLs, planning-estimate disclaimer.

---

## Authentication

| Family | Auth | Tool to set |
| --- | --- | --- |
| OneMap | email + password | `sg_key_set` with `apiName: "onemap"` |
| URA | API key | `sg_key_set` with `apiName: "ura"` |
| LTA DataMall | API key | `sg_key_set` with `apiName: "lta"` |
| All others | None | — |

If a tool fails with auth error, run `sg_health_check` first to confirm it's an auth issue and not a transient upstream failure.

---

## Anti-patterns

- Don't compute SG grants / SORA / BSD in your head — call the tool.
- Don't recommend a bank by name without showing the comparison table.
- Don't paraphrase away `provenance` / `freshness` from brief outputs.
- Don't widen `sg_query` scope when the user already named the family — go direct.
- Don't claim "no data" without checking `gaps` and `freshness` first.
- Don't use this skill for legal, tax, or licensed-advisor decisions.

---

## Worked example (Codex / OpenAI Agents SDK style)

User: *"My wife and I (both citizens, 30 and 29, $5k and $4.5k income, 2 years employed) are looking at a $620k 4-room resale in Punggol near my parents. Can we afford it?"*

Tool calls in order:

```jsonc
// 1. Grants
{
  "tool": "sg_grant_eligibility",
  "input": {
    "profile": {
      "applicants": [
        { "age": 30, "citizenship": "citizen", "monthlyIncomeSgd": 5000, "employmentMonths": 24, "firstTimer": true },
        { "age": 29, "citizenship": "citizen", "monthlyIncomeSgd": 4500, "employmentMonths": 36, "firstTimer": true }
      ],
      "maritalStatus": "married",
      "flatMode": "resale",
      "flatSize": "4_room",
      "proximityToParents": "near"
    }
  }
}

// 2. Resale benchmark
{ "tool": "sg_resale_price_compare",
  "input": { "town": "PUNGGOL", "flatType": "4 ROOM", "askingPriceSgd": 620000, "lookbackMonths": 12 } }

// 3. SORA
{ "tool": "sg_mas_interest_rates", "input": {} }

// 4. Loan compare
{ "tool": "sg_loan_compare",
  "input": {
    "priceSgd": 620000, "downpaymentSgd": 155000, "tenureYears": 25,
    "soraValue": 0.031,
    "bankPackages": [
      { "bank": "DBS", "packageName": "3M SORA + 0.85%", "rateBasis": "sora_3m", "spreadBps": 85, "lockInYears": 2 },
      { "bank": "OCBC", "packageName": "1M SORA + 0.80%", "rateBasis": "sora_1m", "spreadBps": 80, "lockInYears": 2 }
    ]
  } }

// 5. Affordability verdict
{ "tool": "sg_housing_affordability",
  "input": {
    "profile": { /* same as 1 */ },
    "targetPriceSgd": 620000, "tenureYears": 25,
    "cashOnHandSgd": 80000, "cpfOaBalanceSgd": 120000,
    "soraValue": 0.031, "loanType": "bank"
  } }
```

Final answer to user: 3-bullet recommendation, citing `rulesLastVerified` from grants, `freshness` from SORA, `verdict` from affordability, and the disclaimer.

---

## Pointers

- Full Claude Code skill: `.claude/skills/sg-singapore-data/SKILL.md` (canonical content; this file is a Codex-side mirror)
- Architecture: `docs/architecture.md`
- Quickstart: `docs/agent-builder-quickstart.md`
- Compatibility & known issues: `docs/compatibility-matrix.md`, `docs/known-issues.md`
- Embedded rules versioning: `packages/mcp-server/src/housing/rules-2026.json`
