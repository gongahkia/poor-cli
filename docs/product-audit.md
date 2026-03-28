# Product Audit

## Bottom Line

Actual value prop: yes, but narrow.

This repo already has real utility for developers building Singapore-focused agents because it offers one deterministic MCP surface over 29 official public-data families, bounded brief artifacts, transparent blocker behavior, and a verified local build path. That is enough to be useful. It is not yet enough to feel like a broad Singapore developer platform.

## Who Gets Value Today

- agent builders who need explicit `sg_*` contracts instead of wiring multiple Singapore APIs themselves
- diligence and registry workflows that need exact-match evidence instead of vague synthesis
- property, location, transport, and environment use cases where bounded artifacts are more valuable than open-ended chat
- teams that care about provenance, freshness, and hard failure modes

## Why The Repo Is Defensible

- The direct tools are honest wrappers with explicit schemas and stable names.
- The additive briefs create actual product value instead of renaming raw upstream payloads.
- `sg_query` is bounded and inspectable rather than pretending to be a free-form planner.
- The catalog resources make the public surface discoverable without reading the source tree, and `sg://runtime` now exposes the operational trust contract directly.
- `npm run verify` already enforces lint, build, docs parity, tests, and packaging smoke.

## Developer Pain Points Observed

- Discovery was thinner than the tool count suggested. A developer could see 68 tools, but not quickly tell which prompt shapes were supported.
- `sg_query` coverage lagged behind the direct surface for geospatial routing, reverse geocoding, coordinate conversion, SingStat drilldowns, data.gov collection browsing, and URA development charges.
- Install confidence was weaker than it should have been because published tarballs included compiled test and mock artifacts.
- The repo had strong internal structure but weaker newcomer positioning. A new developer still had to infer when to use `sg_query`, when to use direct tools, and how blocked responses should be handled.

## Gain Creators For Actual Users

- Start from `sg://recipes` when the caller has a natural-language goal and wants the right entrypoint quickly.
- Use `sg_query` when the prompt matches a bounded supported workflow and transparent blocker handling matters.
- Use direct `sg_*` tools when the caller already has the exact identifiers, coordinates, table IDs, or dataset IDs.
- Use `sg://workflows`, `sg://tools`, and `sg://runtime` when building your own planner or IDE integration.
- Trust the blocked and unsupported responses. They are a feature because they keep routing deterministic and auditable.

## What This Pass Improves

- runtime-only package contents for published tarballs
- `sg://recipes` as a machine-readable discovery layer
- broader `sg_query` coverage across geospatial, SingStat, data.gov.sg, URA development-charge, and HDB rental prompts
- broader business and compliance diligence coverage across BOA, HSA, HLB, and sector-scoped dossier modules
- no-auth civic discovery across PA community outlets, Sport Singapore facilities, ECDA childcare directories, and MSF civic support directories
- stronger examples, smoke coverage, and onboarding docs for agent builders

## Current Limits

- The repo is still an infrastructure product for developers, not an end-user analytics product.
- The best user stories are bounded and operational. It still does not aim to answer arbitrary Singapore research questions.
- Coverage is strong in a few verticals, but horizontal breadth is still selective.
- The package is credible as a building block, not yet as the single default server for every Singapore civic workflow.

## Breadth Priorities After This Pass

- Civic amenities and directories: deepen from general discovery into family and neighbourhood support services such as student care, family services, and social service offices.
- Education: schools, programmes, and catchment-adjacent discovery would broaden family and relocation use cases.
- Healthcare facilities: clinics, hospitals, and service directories would expand practical consumer and operations workflows.
- Procurement and tender discovery: this is a natural fit for business-facing agents and diligence workflows.

## Recommendation

Keep positioning the repo as the honest Singapore public-data MCP server for developers. Expand breadth through adjacent high-demand public datasets, not by turning `sg_query` into a fake general planner.
