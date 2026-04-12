# PRD 039: Conversation Branch Tree

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Blocked by:** 043
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `poor_cli/history.py`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/branch_tree.lua`
  - `nvim-poor-cli/tests/branch_tree_spec.lua`

## 1. Problem

Conversations are linear today. Regenerate discards the previous reply. Users want tree history so they can keep both branches. LEARNING.md §3.4.

## 2. Current state

`history.py` stores a flat list of turns.

## 3. Goal & non-goals

**Goal:** history becomes a DAG where regenerate creates a sibling branch. UI: right-split tree view with `[[`/`]]` to navigate siblings, `<CR>` to switch to a branch. Server persists tree structure.

**Non-goals:**
- Do not merge branches.
- Do not serialize trees older than N turns (configurable).

## 4. Design

Schema change to history:

```json
{
  "turns": [
    {"id": "t1", "parent_id": null, "role": "user", ...},
    {"id": "t2", "parent_id": "t1", "role": "assistant", ...},
    {"id": "t3", "parent_id": "t1", "role": "assistant", "branch_of": "t2", ...}
  ],
  "active_leaf": "t2"
}
```

Schema migration via PRD 003.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Migrate history schema.
2. Update `regenerate` (from PRD 043) to produce a sibling.
3. Tree view in Lua.
4. Tests.

## 7. Testing & acceptance criteria

- `test_regenerate_creates_sibling`
- `test_active_leaf_drives_context`
- `test_tree_view_navigates`

**Done criterion**
- [ ] Branching works; visualization works.

## 8. Rollback / risk

Medium (schema change). Migration path via PRD 003.

## 9. Out-of-scope & boundary

- 🚫 Do not rewrite history persistence.

## 10. Related PRDs & references

- PRD 003, 043.
- LEARNING.md §3.4.
