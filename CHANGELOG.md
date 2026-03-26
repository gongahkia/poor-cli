# Changelog

All notable changes to this repo will be documented in this file.

The format is based on Keep a Changelog, and the project follows semantic versioning once public npm releases begin.

## [Unreleased]

### Added

- Expanded brief artifacts now return `title`, `summary`, `evidence`, `records`, `gaps`, `provenance`, `freshness`, and `limits`.
- Added `sg_transport_brief` for LTA bus, train, and traffic operations snapshots.
- Added `sg_environment_brief` for NEA forecast, air-quality, and rainfall snapshots.
- Added runnable MCP demo profiles through `npm run demo:mcp -- <profile>`.
- Added registry smoke coverage through `npm run test:smoke:registry`.
- Added release documentation and post-publish validation guidance.

### Changed

- `sg_query` now routes broad transport snapshot prompts to `sg_transport_brief`.
- `sg_query` now routes broad environment snapshot prompts to `sg_environment_brief`.
- README, examples, auth docs, and skill docs now document the expanded brief contract and truthful install paths.

