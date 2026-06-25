# MCP Registry Copy

## Short Description

Haus is a local floor-plan planning workbench with MCP tools for real layout objects, scenario validation, furniture fit checks, accessibility reviews, renovation concept packs, and client-ready exports.

## Long Description

Haus turns an uploaded or manually traced apartment plan into editable layout geometry. MCP clients can inspect rooms and objects, add or move furniture, score doorway and walkway access, draft renovation/accessibility/furniture-fit/designer workflows, duplicate scenarios, and export reports. The emphasis is practical floor-plan work: validate dimensions, compare options, preserve assumptions, and keep homeowner or designer reports local-first.

## Suggested Tags

floor-plan, interior-design, accessibility, furniture-fit, renovation, local-first, reports, threejs

## Setup

```console
uvx --from git+https://github.com/gongahkia/haus haus view
uvx --from git+https://github.com/gongahkia/haus haus mcp --layout ~/.haus/viewer/mcp-layout.json
```

## Safety Copy

Haus provides planning guidance and spatial validation. It is not BIM authoring, code certification, medical advice, contractor-ready documentation, or a substitute for professional site verification.
