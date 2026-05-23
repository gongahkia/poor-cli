# Naming And Remotes

This repository presents **Swee SG** as the product and `@swee-sg/shield` as the package/runtime.

## Stable Names

- npm package: `@swee-sg/shield`
- primary executable: `swee-sg`
- policy/audit executable alias: `swee-shield`
- MCP server package directory: `packages/mcp-server`
- canonical server name: `io.github.gongahkia/swee-sg`
- Tool names and schemas: `swee_*` for product tools, `sg_*` for raw source adapters and ops compatibility
- Environment contracts: `SG_API_*`, `SG_APIS_*`, `SWEE_WEB_ORIGIN_ALLOWLIST`
- Resource contracts: `sg://...`
- Container image: `ghcr.io/gongahkia/swee-sg`

## Product Names

- Swee SG: the web app, REST gateway, MCP runtime, Pulse signal surface, and Shield audit layer.
- Swee Pulse: city signal aggregation for mobility, weather, source health, freshness, and gaps.
- Swee Shield: local policy enforcement, audit persistence, replay metadata, and scanner findings.

## Namespace Note

`sg_*`, `sg://...`, and `SG_API_*` / `SG_APIS_*` remain stable Singapore-data contract namespaces. They describe the source-adapter/resource/env contract, not the product brand.

## Legacy Compatibility

The `sg-apis-mcp` executable is retained as a compatibility alias inside `@swee-sg/shield` for older local MCP client configs. New documentation, releases, and registry metadata should use `@swee-sg/shield`, `swee-sg`, and `ghcr.io/gongahkia/swee-sg`.

## Local Clone And Remote Expectations

Contributors should prefer the renamed repository:

```bash
git clone https://github.com/gongahkia/swee-sg.git
cd swee-sg
git remote -v
```

If an existing checkout still points at an old remote, update it instead of recloning:

```bash
git remote set-url origin https://github.com/gongahkia/swee-sg.git
```
