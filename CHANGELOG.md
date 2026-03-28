# Changelog

All notable changes to this repo will be documented in this file.

The format is based on Keep a Changelog, and the project follows semantic versioning once public npm releases begin.

## [Unreleased]

### Added

- Added BOA, HSA, and HLB direct tool families with `sg_boa_architects`, `sg_boa_architecture_firms`, `sg_hsa_licensed_pharmacies`, `sg_hsa_health_product_licensees`, and `sg_hlb_hotels`.
- Added bounded workflows and recipes for Architecture Firm Diligence, Healthcare Supplier Diligence, Hotel Operator Lookup, and Sector Scoped Business Diligence.
- Added explicit `modules` and `sectorHints` support to `sg_business_dossier`.
- Added shared entity-resolution logic with deterministic `matchConfidence`, `matchedOn`, and `unmatchedModules` reporting.
- Added sector-specific walkthroughs and query outcome coverage for architecture, healthcare-supplier, and hotel-operator diligence.
- Expanded brief artifacts now return `title`, `summary`, `evidence`, `records`, `gaps`, `provenance`, `freshness`, and `limits`.
- Brief artifacts now support optional `riskFlags`, `matchConfidence`, and `nextChecks` fields.
- `sg_business_dossier` now returns risk flags (expired licenses, inactive entities), match confidence per source, and next check suggestions.
- `sg_property_brief` now returns transaction rollups (median, min, max, count), market comparison (private vs HDB), and deal checklist flags.
- `sg_macro_brief` now uses named metric extraction (SORA, banking keys) with period-over-period deltas instead of generic first-numeric-field.
- `sg_transport_brief` now returns stop summary (service count, avg wait) and incident summary (count by type).
- `sg_environment_brief` now returns outdoor conditions advisory, area-to-region inference, and rainfall station metadata.
- Added `sg_transport_brief` for LTA bus, train, and traffic operations snapshots.
- Added `sg_environment_brief` for NEA forecast, air-quality, and rainfall snapshots.
- Added 9 new data families: `sg_gebiz_tenders`, `sg_hawker_centres`, `sg_moe_schools`, `sg_moh_facilities`, `sg_sfa_establishments`, `sg_nparks_parks`, `sg_pub_water_levels`, `sg_mom_labour_stats`, `sg_stb_visitor_stats`.
- Added `sg-data` CLI tool for quick lookups without MCP setup.
- Added REST gateway (`npm run rest-gateway`) exposing tools as HTTP POST endpoints.
- Added Dockerfile for zero-config container deployment.
- Added TypeScript integration example at `examples/integration/basic-client.ts`.
- Added internal regression fixtures for brief and query contract coverage.
- Added live quick-start script (`npm run quick-start`).
- Added production notes doc at `docs/production-notes.md`.
- Added 4 new recipes: Demographic Profile, Bus Stop Status, Outdoor Event Check, Business Due Diligence.
- Added `routingExplanation` and `continuationHints` to `sg_query` structured output.
- Added OpenAPI spec generator at `scripts/generate-openapi.mjs`.
- Added credential-gated live smoke validation through `npm run test:smoke:live`.
- Added registry smoke coverage through `npm run test:smoke:registry`.
- Added release documentation and post-publish validation guidance.

### Changed

- Tool count increased from 63 to 68; API family count from 26 to 29; routed families from 17 to 20.
- `sg_business_dossier` now stays backward-compatible by default while supporting explicit BOA, HSA, HLB, and GeBIZ module selection.
- README, skill docs, architecture notes, auth docs, and docs parity checks now track BOA, HSA, HLB, and the new diligence workflows.
- Tool count increased from 47 to 56; API family count from 11 to 20.
- All 9 new tool schemas are exported from `@sg-apis/shared`.
- `sg_query` now routes broad transport snapshot prompts to `sg_transport_brief`.
- `sg_query` now routes broad environment snapshot prompts to `sg_environment_brief`.
- README, examples, auth docs, and skill docs now document the expanded brief contract and truthful install paths.
