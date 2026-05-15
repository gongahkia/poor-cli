# Naming And Remotes

This repository now presents the web product as **Dude** while preserving the underlying MCP package/runtime identity.

## Stable Names That Should Not Change

- npm package: `sg-apis-mcp`
- MCP server package directory: `packages/mcp-server`
- Tool names and schemas: `sg_*`
- Environment contracts: `SG_API_*`, `SG_APIS_*`
- Resource contracts: `sg://...`
- Container image: `ghcr.io/gongahkia/sg-apis-mcp`

## Product Names

- Dude: the web app, REST gateway, bulk workflow, local shortlist, exports, and analyst memo surface.
- `sg-apis-mcp`: the MCP server and public Singapore data runtime used under the web app.

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

Old local folder names do not break the build, but examples and docs should use `/absolute/path/to/dude/...` unless they intentionally refer to the stable `sg-apis-mcp` package/runtime.
