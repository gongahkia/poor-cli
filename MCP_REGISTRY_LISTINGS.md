# MCP Registry Listings

This tracks the public listing metadata for Haus and the submission state for MCP directories.

## Shared Listing Copy

**Name:** Haus

**Short description:** MCP-native HDB BTO floor-plan editor that lets agents furnish Singapore flats.

**Long description:** Haus is an open-source SVG/GLB floor-plan editor for Singapore HDB BTO layouts. Its stdio MCP server lets assistants load real BTO flat layouts, place and edit furniture, tag rooms, check sightlines and walkways, and write the result back to the browser editor.

**Category:** Design tools

**Tags:** `mcp`, `floor-plan`, `interior-design`, `hdb`, `bto`, `singapore`, `threejs`, `layout`

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

## Metadata Files

- `mcp-manifest.json`: cross-registry metadata, listing copy, client config, tool list, and submission status.
- `server.json`: official MCP Registry draft using the current `server.json` schema. It is ready as metadata, but publication is blocked until the PyPI package is released and the package ownership marker in `README.md` is present in the published package README.

## Registry Checklist

| Target | Public path checked | Required metadata | Haus status | Submit action |
|---|---|---|---|---|
| mcp.so | https://mcp.so/submit | Type, name, URL, server config. | Ready for manual submission. | Select MCP Server, use the shared listing copy, paste the GitHub URL, and paste the client config above. |
| mcp.pizza | https://www.mcp.pizza/mcp-servers | Directory page exposes GitHub-backed server listings, README content, specs, language, license, and stars. No public submit form was found during this pass. | Pending submission path. | Keep the shared copy ready; submit when a public form/contact route is exposed, or contact the site operator if needed. |
| PulseMCP | https://www.pulsemcp.com/submit | Submit server/client route accepts a project URL; the directory enriches listing metadata from the project. | Ready for manual submission. | Submit `https://github.com/gongahkia/haus` and use the shared copy if asked for text fields. |
| Smithery | https://smithery.ai/docs/build/publish | URL publishing needs a public Streamable HTTP server; local stdio publishing needs an MCPB bundle. Smithery can scan public servers or use a static server card. | Blocked until Haus ships either a public remote MCP endpoint or an MCPB bundle. | Package an MCPB or add a remote Streamable HTTP deployment, then publish with `smithery mcp publish`. |
| Anthropic Connectors Directory | https://claude.com/docs/connectors/building/submission | Directory accepts remote MCP servers, desktop extensions packaged as MCPB, and MCP Apps. Submission requires server basics, connection details, data handling, tools/prompts/resources, docs/support, tests, branding, and policy checks. | Blocked until Haus ships an MCPB bundle or remote connector and adds the required privacy/policy material. | Build/test the MCPB or remote connector, add privacy policy documentation, then use the appropriate Anthropic submission form. |
| Official MCP Registry | https://modelcontextprotocol.io/registry | `server.json`, authenticated namespace, package ownership verification, and a published package. PyPI packages must use `https://pypi.org` as the registry base URL. | Blocked until the PyPI release exists and package verification passes. | Publish the package, run `mcp-publisher login github`, then `mcp-publisher publish`. |

## Submission Status

- `mcp.so`: not submitted, ready.
- `mcp.pizza`: not submitted, waiting on a public submission path.
- `PulseMCP`: not submitted, ready.
- `Smithery`: not submitted, blocked by missing MCPB or remote endpoint.
- `Anthropic Connectors Directory`: not submitted, blocked by missing MCPB or remote connector and privacy/policy docs.
- `Official MCP Registry`: not submitted, blocked by PyPI release and ownership verification.

## Source Notes

- Official MCP Registry docs describe `server.json`, the preview publishing flow, namespace authentication, package verification, and registry base URL restrictions.
- mcp.so exposes a submit route with Type, Name, URL, and Server Config fields.
- PulseMCP exposes a Submit server/client route from its directory navigation.
- Smithery publish docs distinguish URL-based Streamable HTTP publishing from local stdio MCPB publishing.
- Anthropic Connectors Directory docs distinguish remote MCPs, MCPB desktop extensions, and MCP Apps, and list the required submission metadata and policy checks.
