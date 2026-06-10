# MCP Registry Listings

Public listing metadata for Haus.

Canonical files: `mcp-manifest.json`, `server.json`.

## Shared Listing Copy

**Name:** Haus

**Short description:** MCP-native AI floor-plan workbench for uploaded apartment layouts.

**Long description:** Haus is an open-source floor-plan editor and local AI planning workbench. Users can upload floor-plan images, calibrate scale, vectorize walls into editable 3D geometry, ask agents to furnish rooms, run spatial checks, and export JSON, SVG, or GLB layouts.

**Category:** Design tools

**Tags:** `mcp`, `floor-plan`, `interior-design`, `apartment`, `threejs`, `layout`, `space-planning`

**Install and launch:**

```console
uvx --from git+https://github.com/gongahkia/haus haus view
uvx --from git+https://github.com/gongahkia/haus haus mcp --layout ~/.haus/viewer/mcp-layout.json
```

**Client config:**

```json
{
  "mcpServers": {
    "haus": {
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/gongahkia/haus",
        "haus",
        "mcp",
        "--layout",
        "/Users/YOUR_USER/.haus/viewer/mcp-layout.json"
      ]
    }
  }
}
```

## Status

| Target | Status | Submit action |
|---|---|---|
| mcp.so | Ready | Submit GitHub URL and client config. |
| PulseMCP | Ready | Submit `https://github.com/gongahkia/haus`. |
| Official MCP Registry | Blocked | Publish PyPI package, then run registry publish flow. |
