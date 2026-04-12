# PRD 035: MCP Registry browser

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Blocked by:** 024
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/mcp_registry.lua`
  - `nvim-poor-cli/tests/mcp_registry_spec.lua`

## 1. Problem

No UI for MCP server management. Users need a way to browse the official registry, toggle servers, view tool lists, and test health. mcphub.nvim does this in its ecosystem. LEARNING.md §3.4, §4.

## 2. Current state

`.poor-cli/mcp.json` edited by hand.

## 3. Goal & non-goals

**Goal:** full-screen buffer listing configured servers (status, tool count, last error) + a `[Browse registry]` action that paginates the official registry. Actions: toggle enable, edit spec, remove, health-check, test-tool-call.

**Non-goals:**
- Do not ship `mcphub.nvim` integration (it would be a thin wrapper; keep ours native).
- Do not auto-install servers.

## 4. Design

Uses RPCs from PRD 024: `listMcpServers`, `healthMcp`, `registrySearch`.

Layout:

```
┌─── poor-cli mcp ─────────────────────────────────────────┐
│ CONFIGURED                                                │
│  ● github (stdio)   healthy   24 tools                    │
│    [toggle] [edit] [remove] [test-tool]                   │
│  ○ fs (stdio)       error: command not found              │
│                                                           │
│ REGISTRY                                                  │
│  [Search:             ]                                   │
│  ● @modelcontextprotocol/server-linear                    │
│    [install]                                              │
└───────────────────────────────────────────────────────────┘
```

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Server RPCs (list, health, registry).
2. Lua buffer with sections.
3. Keymaps.
4. Tests.

## 7. Testing & acceptance criteria

- `test_configured_servers_render`
- `test_registry_search_filters`
- `test_install_prompt_writes_mcp_json`

**Done criterion**
- [ ] Registry browser functional.
- [ ] Config writes via UI round-trip correctly.

## 8. Rollback / risk

Low. Manual edit of mcp.json remains supported.

## 9. Out-of-scope & boundary

- 🚫 Do not auto-execute registry commands.

## 10. Related PRDs & references

- PRD 024.
- https://registry.modelcontextprotocol.io/
- LEARNING.md §3.4.
