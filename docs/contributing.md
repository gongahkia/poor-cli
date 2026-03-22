# Contributing Guide

## Scope First

This pilot currently prioritizes depth and contract honesty across the existing five API families:
- SingStat
- MAS
- OneMap
- URA
- data.gov.sg

Before adding a new API, prefer asking whether the user goal can be served by making an existing tool contract more truthful, more testable, or more complete.

## Adding a New API

1. **Create client**: `packages/mcp-server/src/apis/<api>/client.ts`
   - Set `BASE_URL` with `MOCK_API_BASE_URL` support
   - Implement data fetching functions with caching
   - Use `httpGet` from `@sg-apis/shared`

2. **Create tools**: `packages/mcp-server/src/tools/<api>-tools.ts`
   - Export `register<Api>Tools(server: McpServer)`
   - Use `registerTool` from registry
   - Validate input with Zod schemas

3. **Register tools**: Update `packages/mcp-server/src/tools/registry.ts`
   - Import and call registration function in `registerAllTools`

4. **Add types**: `packages/shared/src/types/<api>.ts`
   - Export from barrel file

5. **Add schemas**: Update `packages/shared/src/schemas/index.ts`
   - Add Zod schemas for tool inputs

6. **Add tests**: `packages/mcp-server/src/apis/<api>/__tests__/`
   - Minimum 5 tests per client
   - Include fixtures in `__tests__/fixtures/`

7. **Update SKILL.md**: Add tool documentation
8. **Update MCP resources and README**: Keep public positioning in sync with the actual surface
9. **Add parity coverage**: Schema, handler, docs, and MCP resource descriptions must agree on supported inputs and behavior

## Tool Naming
Pattern: `sg_<api>_<operation>` (e.g., `sg_singstat_search`)

## Cache TTL
Always include a `// WHY:` comment for TTL values.

## Testing
- Mock `fetch` with `vi.stubGlobal`
- Use `:memory:` for SQLite in tests
- No real HTTP requests in tests
- Add contract-parity tests when you narrow or expand a public tool schema
