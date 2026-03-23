# Contributing Guide

## Scope First

The repo currently prioritizes depth and contract honesty across 11 official data families, with `sg_query` acting as a bounded preferred interface across the routed subset.

Before adding a new family, prefer asking whether the user goal can be served by making an existing tool contract more truthful, more testable, or more complete.

## Current Public Shape

- 31 direct data tools across 11 data families
- 8 operational helpers
- 1 bounded preferred interface, `sg_query`

The direct tools are the stable low-level contract. `sg_query` should only grow when the bounded workflow stays transparent and deterministic.

## Adding Or Expanding A Data Family

1. **Add shared types** in `packages/shared/src/types/<family>.ts`
   - export normalized output types for the direct tools
   - export them from `packages/shared/src/index.ts`

2. **Add shared schemas** in `packages/shared/src/schemas/index.ts`
   - keep public inputs explicit
   - use `.strict()` when extra fields should be rejected
   - update schema tests in `packages/shared/src/__tests__/`

3. **Create the upstream client** in `packages/mcp-server/src/apis/<family>/client.ts`
   - support `MOCK_API_BASE_URL` when the family performs HTTP calls
   - use cache, rate-limit, and error helpers consistently
   - keep normalization inside the client or adjacent normalizers

4. **Create direct tool definitions** in `packages/mcp-server/src/tools/<family>-tools.ts`
   - export a `readonly RegisteredToolDefinition[]`
   - validate input with the shared schema
   - return both formatted text and structured content when practical

5. **Register the definitions** in `packages/mcp-server/src/tools/tool-set.ts`
   - import the new `RegisteredToolDefinition[]`
   - add the definitions to `ALL_TOOL_DEFINITIONS`

6. **Update public catalogs** in `packages/mcp-server/src/tools/catalog.ts`
   - add or update the API family entry
   - update workflow recipes if the new tools materially change the public story
   - keep `preferredInterface` honest; do not claim `sg_query` coverage that does not exist

7. **Keep resources truthful**
   - `sg://apis`, `sg://tools`, and `sg://workflows` are generated from the catalog layer
   - if the public story changes, the catalog must change in the same patch

8. **Add tests**
   - client tests in `packages/mcp-server/src/apis/<family>/__tests__/`
   - handler tests in `packages/mcp-server/src/tools/__tests__/`
   - schema tests in `packages/shared/src/__tests__/`
   - catalog/resource parity tests when you add or remove public tools

9. **Update docs and metadata in the same change**
   - `README.md`
   - `packages/skill/SKILL.md`
   - `docs/architecture.md`
   - `docs/api-auth-guide.md`
   - marketplace metadata such as `smithery.yaml` and `glama.json`

10. **Keep docs parity green**
   - `scripts/check-docs-parity.mjs` is the verify-time guardrail for counts, auth surfaces, and `sg_query` positioning
   - if the public surface changes, update the docs markers in the same patch

## Tool Naming

Pattern: `sg_<family>_<operation>` (for example `sg_singstat_search`)

## Cache TTL

Always include a `// WHY:` comment for TTL values.

## Testing

- Run `npm run verify` before shipping changes. It is the canonical local and CI verification entrypoint.
- Mock `fetch` with `vi.stubGlobal`
- Avoid real HTTP requests in tests
- Add contract-parity tests when you narrow or expand a public tool schema
- Update packaging smoke expectations when the public tool list changes
