# Architecture Decision Record

## Title

Official Singapore public data for agents with deterministic contracts

## Status

Accepted for the current product shape.

## Context

This repo is not a general Singapore analyst copilot. It is a tool-first MCP server for agent builders who need reliable, explicit interfaces over 11 official data families.

The product boundary is:

- stable direct `sg_*` tools first
- additive briefs where composition creates clear user value
- a bounded preferred interface across 11 routed families

That boundary keeps the repo useful without pretending to solve arbitrary analyst workflows.

## Decisions

### 1. Direct `sg_*` tools stay the stable low-level contract

Why:

- explicit schemas are easier to test, document, and defend
- direct tools let callers compose intentionally
- deterministic contracts matter more than hidden convenience

Consequence:

- new scope is added with honest direct tools first
- additive briefs are allowed only when they return a bounded artifact, not hidden orchestration

### 2. The repo goes deep on 11 official data families

The current families are:

- SingStat
- MAS
- OneMap
- URA
- LTA DataMall
- NEA
- HDB
- CEA
- BCA
- ACRA
- data.gov.sg

Why:

- together they cover macro, finance, location, property, transport, environment, housing, dataset discovery, and business diligence
- HDB, CEA, BCA, and ACRA deepen the diligence story without adding more credential surfaces
- every new upstream multiplies auth, rate-limit, schema, and support cost

Consequence:

- family growth is driven by user stories, not agency count
- data.gov.sg remains the broad fallback and row-access substrate

### 3. `sg_query` is a bounded usability layer, not a planner

`sg_query` is the bounded preferred interface across 11 routed families.

Why:

- open-source users benefit from a natural-language entrypoint
- transparent step metadata keeps the routing layer honest
- keeping the workflow set bounded avoids fake coverage

Consequence:

- business-registry workflows can route to ACRA, CEA, and BCA
- macro workflows can collapse to `sg_macro_brief`
- property workflows can collapse to `sg_property_brief`
- transport workflows can collapse to `sg_transport_brief`
- environment workflows can collapse to `sg_environment_brief`
- dataset discovery can continue into `sg_datagov_resources` and `sg_datagov_rows`
- comparisons and arbitrary multi-step synthesis remain out of scope

### 4. Additive brief tools must return bounded artifacts

The allowed additive shape is a deterministic brief with:

- `title`
- `summary`
- `evidence`
- `records`
- `gaps`
- `provenance`
- `freshness`
- `limits`

Why:

- this is where the repo creates user-facing value beyond raw wrappers
- the brief remains inspectable and source-linked through the underlying records
- provenance, freshness, and limits make the product useful for real developer-facing workflows instead of demo-only synthesis

Consequence:

- `sg_business_dossier`, `sg_property_brief`, `sg_macro_brief`, `sg_transport_brief`, and `sg_environment_brief` are additive
- they do not replace the direct `sg_*` tools
- they are acceptable because they produce bounded artifacts instead of hidden planning behavior

### 5. Runtime behavior is centralized and explicit

The runtime combines:

- config-driven timeouts
- config-driven TTLs
- upstream-specific rate limiting
- cache and dedup layers
- structured error handling

Why:

- Singapore public APIs differ widely in auth, latency, and rate limits
- production callers need consistent behavior across families

Consequence:

- the server favors explicit failure over silent fallback
- OneMap credential behavior now matches the documented contract
- the data.gov.sg warm-cache path is explicit and non-blocking

## Runtime Model

At a high level:

- MCP requests enter the server over stdio
- input schemas validate at the tool boundary
- tool handlers call family clients or bounded brief handlers
- clients apply auth, cache, dedup, timeout, and rate-limit behavior
- results are returned as text plus structured content when available

The warm-cache path is intentionally best-effort and non-blocking. Startup should not wait on prefetch work.

## Interview Defense

The shortest defensible answer is:

"I kept the direct contracts explicit, then added a small number of bounded artifacts on top. The result is useful for agents without pretending to be a general planner."

Key tradeoffs:

- chose explicit direct tools over hidden orchestration
- chose bounded briefs over vague multi-API synthesis
- chose a bounded preferred interface over a free-form planner
- chose curated user stories over low-signal surface expansion
- chose truthful docs and parity checks over aspirational claims

## Known Intentional Limits

- `sg_query` is not a general planner
- `sg_macro_brief` is a starter snapshot, not full analysis
- `sg_business_dossier` is registry-focused and exact-match oriented
- `sg_property_brief` is bounded diligence context, not a recommendation engine
- `sg_transport_brief` is an operations snapshot, not route planning or predictive dispatch
- `sg_environment_brief` is a live monitoring brief, not severe-weather forecasting
- data.gov.sg support is bounded to explicit metadata, resource inspection, and row reads rather than arbitrary data prep

