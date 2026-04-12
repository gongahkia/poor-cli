# PRD 029: Context Explainer panel upgrade

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Blocks:** —
- **Blocked by:** 018
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `nvim-poor-cli/lua/poor-cli/context_mgr.lua`
  - `poor_cli/server/handlers/context.py` (PRD 019 moves here)
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/context_panel.lua`
  - `nvim-poor-cli/tests/context_panel_spec.lua`

## 1. Problem

`:PoorCliContext` today opens a scratch buffer with a text summary. Users can't see *why* a file is in context, its token cost, or whether it was compressed. LEARNING.md §3.4: panel that shows file-by-file inclusion reasoning.

## 2. Current state

Scratch buffer, static text, RPC backs it but output is minimal.

## 3. Goal & non-goals

**Goal:** right-split panel listing every file in the `ContextSnapshot` (PRD 018) with columns: path, tokens, reason (pagerank-hub / recent-open / imported-by-target / pinned), compressed?, pinned?. Actions: `p` pin/unpin, `d` drop from context, `r` refresh, `/` filter, `o` jump to file.

**Non-goals:**
- Do not mutate context selection heuristics.
- Do not show token-count history (PRD 041 covers savings).

## 4. Design

### 4.1 RPC

`poor-cli/explainContext` returns the full `ContextSnapshot` serialized (paths, tokens, reasons, budget, compression metadata).

### 4.2 Panel layout

```
┌──── poor-cli context (turn 42)  [budget: 100,000 tok, used: 78,340] ─┐
│ path                                        tokens  reason         │
├──────────────────────────────────────────────────────────────────── │
│ 📌 AGENTS.md                                   820  rules           │
│    poor_cli/core.py                          4,320  pagerank-hub    │
│    poor_cli/context.py                       2,140  imported-by     │
│ ✂  README.md                                 1,120  pinned (comp.)  │
│    tests/test_core_pre_slice.py                540  recent          │
│ ...                                                                 │
└──────────────────────────────────────────────────────────────────── │
```

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Server: `explainContext` method built on `ContextSnapshot`.
2. Lua: panel with columns; use extmarks for pin/compressed icons.
3. Wire pin/drop to RPCs (reuse `/add` `/drop` commands internally).
4. Tests.
5. `make lint && make test` + `:PlenaryBustedDirectory`.

## 7. Testing & acceptance criteria

- `test_explain_context_serializes_snapshot`
- `pin unpin persists across turn`
- `filter narrows visible rows`

**Done criterion**
- [ ] Panel renders with real data.
- [ ] Pin/drop works.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not edit `ContextSnapshot` schema.
- 🚫 Do not touch assembly logic.

## 10. Related PRDs & references

- PRD 018, 055.
- LEARNING.md §3.4.
