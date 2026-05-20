# Contributing Guide

## Scope First

The repo currently prioritizes depth and contract honesty across 39 catalog families, with `sg_query` acting as a bounded preferred interface and seven additive brief tools creating the main user-facing artifacts.

## Package Manager

Use npm for local development and CI parity. `package-lock.json` is the canonical lockfile, and the supported install path is:

```bash
npm install
```

Do not add pnpm-only workflows, lockfiles, or workspace metadata unless the repo also adds a maintained pnpm CI/test path in the same change.

Before adding a new family, ask whether the user goal is better served by:

- improving an existing direct contract
- adding a bounded brief over existing direct tools
- unlocking a reusable data.gov.sg row-access path

## Current Public Shape

- 90 direct data tools, including diligence tools, across 39 catalog families
- 7 additive brief tools
- 11 runtime and operational tools, including health checks
- 1 bounded preferred interface, `sg_query`

The direct tools are the stable low-level contract. Additive briefs are allowed only when they remain deterministic and inspectable.

## Adding Or Expanding A Data Family

1. Add shared types in `packages/shared/src/types/<family>.ts`.
2. Add shared schemas in `packages/shared/src/schemas/index.ts`.
3. Create the upstream client in `packages/mcp-server/src/apis/<family>/client.ts`.
4. Create direct tool definitions in `packages/mcp-server/src/tools/<family>-tools.ts` as a `RegisteredToolDefinition[]`.
5. Register the definitions through the owning country pack in `packages/mcp-server/src/country-packs/`; `packages/mcp-server/src/tools/tool-set.ts` hydrates definitions from country packs.
6. Update public catalogs in `packages/mcp-server/src/tools/catalog.ts`.
7. Keep `sg://apis`, `sg://tools`, `sg://workflows`, `sg://recipes`, `sg://runtime`, `sg://playbooks`, and `sg://benchmarks` truthful.
8. Add tests for schemas, clients, tools, routing, and catalog parity.
9. Update docs and marketplace metadata in the same change.
10. Keep `scripts/check-docs-parity.mjs` green.

If the change introduces a new guided prompt shape, update `RECIPE_CATALOG` in the same patch and reflect the onboarding impact in `docs/agent-builder-quickstart.md`.

## Adding An Additive Brief Tool

Use the brief pattern only when the output is a bounded artifact with:

- `title`
- `summary`
- `evidence`
- `records`
- `gaps`
- `provenance`
- `freshness`
- `limits`

The brief must improve one of the core product stories:

- business diligence
- sector-scoped business and compliance diligence
- property or location diligence
- macro snapshot
- transport operations
- environment monitoring

## Tool Naming

Pattern: `sg_<family>_<operation>`

Examples:

- `sg_datagov_rows`
- `sg_business_dossier`
- `sg_transport_brief`

## Testing

- Run `npm run diagnostics` after `npm run build` for fast catalog/resource sanity checks.
- Run `npm run verify` before shipping changes.
- Mock `fetch` with `vi.stubGlobal`.
- Avoid real HTTP requests in tests.
- Add parity coverage when public tools are added or removed.
- Add schema and handler coverage when new brief envelopes or workflow types are introduced.
- Update packaging smoke and registry smoke expectations when the public surface changes.
- Update docs parity markers in the same patch when counts, workflow names, or install instructions change.
- When recovering from partial failures, log structured context; do not silently drop source errors.
