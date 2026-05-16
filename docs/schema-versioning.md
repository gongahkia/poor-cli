# Schema Versioning

This repo treats public payload shapes as contracts. Schema changes are allowed, but breaking changes must be intentional, documented, and released with migration notes.

## Current Contract IDs

| Surface | Contract ID | Scope |
| --- | --- | --- |
| Brief envelope | `brief-envelope/v1` | Shared `title`, `summary`, `evidence`, `records`, `gaps`, `provenance`, `freshness`, and `limits` structure returned by brief-style tools. |
| Business dossier | `business-dossier/v1` | Counterparty dossier records, evidence, confidence, risk flags, next checks, web presence, and module gap semantics. |
| Country pack | `country-pack/v1` | Country-pack adapter envelope, auth metadata, licensing assumptions, source freshness, public-data limits, and contribution fixtures. |

The code-level registry lives in `packages/shared/src/schema-version.ts` and is exported by `@dude/shared`.

## Compatibility Rules

- Adding an optional field is a minor-compatible change when existing consumers can ignore it safely.
- Adding a required field, renaming a field, changing a field type, removing a field, or changing enum semantics is a breaking change.
- Tightening validation is a breaking change when previously valid caller input or output records become invalid.
- Relaxing validation is minor-compatible only when downstream semantics remain clear.
- New country packs must use the country-pack envelope from the start; they should not define one-off payload shapes.

## Required Release Notes

Every public schema change must update `CHANGELOG.md` under one of these headings:

- `Schema Changes` for additive or compatible changes
- `Breaking Changes` for required migration work
- `Deprecations` when a field, enum value, tool, resource, or workflow is still available but scheduled for removal

Breaking changes must include:

- affected contract ID
- old behavior
- new behavior
- migration path
- verification command or fixture

Deprecations must follow [deprecation-policy.md](./deprecation-policy.md), including target removal version or date and release-note entries until removal completes.

## Intentional-Break Check

`npm run schema:check` verifies that the schema version registry, this document, and `CHANGELOG.md` mention the current contract IDs and release-note sections. `npm run verify` runs that check so schema-governance drift fails before release.

When a breaking schema change is intentional, update the relevant contract ID, changelog entry, migration notes, and tests in the same pull request.
