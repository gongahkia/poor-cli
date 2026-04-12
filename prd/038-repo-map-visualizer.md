# PRD 038: Repo Map visualizer

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1–1.5w)
- **Blocked by:** 022
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/repo_map.lua`
  - `nvim-poor-cli/tests/repo_map_spec.lua`

## 1. Problem

`repo_graph.py` produces a dependency graph with PageRank scores. Users can't see it. LEARNING.md §3.4.

## 2. Current state

Graph in SQLite; no UI.

## 3. Goal & non-goals

**Goal:** an ASCII-rendered tree-like visualization of the top-N PageRank files, their import neighborhoods, and tree-sitter-derived top symbols. `<CR>` on a file opens it; `gl` expands its imports; `gs` lists symbols.

**Non-goals:**
- Do not ship a 2D canvas / graph visualizer (terminal-native only).
- Do not show the full graph — top-50 by default.

## 4. Design

Layout:

```
┌──── repo map (top 50 by pagerank) ─────────────────────────┐
│  0.041 poor_cli/core.py                                     │
│         ↓ imports: context, tools_async, provider_factory   │
│         ↑ imported-by: server/runtime, cli/main             │
│  0.027 poor_cli/context.py                                  │
│  ...                                                        │
└─────────────────────────────────────────────────────────────┘
```

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. RPC `poor-cli/repoMapTopK`.
2. Lua render.
3. Expand/collapse via extmarks.
4. Tests.

## 7. Testing & acceptance criteria

- `test_top_k_rendered_sorted`
- `test_expand_shows_imports`

**Done criterion**
- [ ] Map opens and navigable.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not implement graph editing.

## 10. Related PRDs & references

- PRD 022.
- LEARNING.md §3.4.
