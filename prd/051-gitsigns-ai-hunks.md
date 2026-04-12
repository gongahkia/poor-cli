# PRD 051: `gitsigns.nvim` bridge for AI-authored hunks

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (3d)
- **Blocked by:** 014
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/diff_review.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/gitsigns_bridge.lua`
  - `nvim-poor-cli/tests/gitsigns_bridge_spec.lua`

## 1. Problem

When the user accepts a hunk via Diff Review (PRD 014), it becomes a live unstaged git change. Gitsigns treats it as normal. Users can't distinguish AI-authored vs manual hunks. LEARNING.md §3.8.

## 2. Current state

Gitsigns renders `+`/`~`/`-` gutter signs uniformly.

## 3. Goal & non-goals

**Goal:** a dim gutter icon `✱` (or configurable) on AI-authored hunks after acceptance. Attribution mapping stored per-file for the session. On commit, the AI-authorship map is cleared.

**Non-goals:**
- Do not add git author metadata.
- Do not replace gitsigns.

## 4. Design

Track accepted hunks keyed by `(file, line_range)` in memory. Use a separate gutter sign group. On buffer change, recompute sign positions.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. On `poor-cli/editCommitted`, capture line ranges of applied hunks.
2. Place signs.
3. Clear on `BufWritePost` + git commit.
4. Tests.

## 7. Testing & acceptance criteria

- `test_signs_placed_after_accept`
- `test_signs_cleared_on_commit`

**Done criterion**
- [ ] AI hunks visually distinct.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not replace gitsigns.

## 10. Related PRDs & references

- PRD 014.
- gitsigns: https://github.com/lewis6991/gitsigns.nvim
- LEARNING.md §3.8.
