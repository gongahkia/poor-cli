# Naming And Remotes

This repository presents **Dude** as the product and **Dude MCP** as its backend/runtime.

## Stable Names That Should Not Change

- npm package: `@dude/mcp`
- executable: `dude-mcp`
- MCP server package directory: `packages/mcp-server`
- Tool names and schemas: `sg_*`
- Environment contracts: `SG_API_*`, `SG_APIS_*`
- Resource contracts: `sg://...`
- Container image: `ghcr.io/gongahkia/dude-mcp`

## Product Names

- Dude: the web app, REST gateway, bulk workflow, browser-local workspace tools, exports, and analyst memo surface.
- Dude MCP: the MCP server and public Singapore data runtime that backs the web app and direct agent integrations.

## Namespace Note

`sg_*`, `sg://...`, and `SG_API_*` / `SG_APIS_*` remain stable Singapore-data contract namespaces. They describe the tool/resource/env contract, not the product brand.

## Legacy Compatibility

The `sg-apis-mcp` executable is retained as a compatibility alias inside `@dude/mcp` for older local MCP client configs. New documentation, releases, and registry metadata should use `@dude/mcp`, `dude-mcp`, and `ghcr.io/gongahkia/dude-mcp`.

## Local Clone And Remote Expectations

After the GitHub rename, contributors should prefer a local folder named `dude`:

```bash
git clone https://github.com/gongahkia/dude.git
cd dude
git remote -v
```

If an existing checkout still points at the old `sg-skills` remote, update it instead of recloning:

```bash
git remote set-url origin https://github.com/gongahkia/dude.git
```

Old local folder names do not break the build, but examples and docs should use `/absolute/path/to/dude/...` unless they intentionally document the legacy compatibility alias.
