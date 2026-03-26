# Examples

This folder contains runnable walkthroughs for the five primary outcome workflows:

- `business-dossier.md`
- `property-brief.md`
- `macro-brief.md`
- `transport-brief.md`
- `environment-brief.md`

## Local Client Snippets

Build the server first:

```bash
npm install
npm run build
```

Claude Desktop or Codex-style clients:

```json
{
  "mcpServers": {
    "sg-apis-mcp": {
      "command": "node",
      "args": ["/absolute/path/to/sg-skills/packages/mcp-server/dist/index.js"]
    }
  }
}
```

Claude Code:

```bash
claude mcp add sg-apis-mcp -- node /absolute/path/to/sg-skills/packages/mcp-server/dist/index.js
```

Published-package snippet after the first npm release:

```json
{
  "mcpServers": {
    "sg-apis-mcp": {
      "command": "npx",
      "args": ["-y", "sg-apis-mcp"]
    }
  }
}
```

## Runnable Demo Profiles

Each example file maps to one built-in profile:

- `npm run demo:mcp -- business`
- `npm run demo:mcp -- property`
- `npm run demo:mcp -- macro`
- `npm run demo:mcp -- transport`
- `npm run demo:mcp -- environment`

Every profile reads one resource, calls one direct tool, calls one brief tool, and then runs the equivalent `sg_query` workflow against the mock upstream server.

