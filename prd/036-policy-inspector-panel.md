# PRD 036: Policy Inspector panel

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small (3d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/policy_panel.lua`
  - `nvim-poor-cli/tests/policy_panel_spec.lua`

## 1. Problem

Permission rules and policy hooks are opaque. `/policy` lists them as text. LEARNING.md §3.4.

## 2. Current state

Command returns text snapshot.

## 3. Goal & non-goals

**Goal:** right-split panel showing: rule name, scope, outcome (allow/deny/prompt), source (user / repo / default). Click-to-edit opens the rule file. Keymap to reload rules after edit.

## 4. Design

Backed by `poor-cli/policy/list`, `policy/reload`, `policy/edit` RPCs.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Render rules.
2. Edit-in-place path.
3. Tests.

## 7. Testing & acceptance criteria

- `test_rules_list_renders`
- `test_reload_picks_up_disk_change`

**Done criterion**
- [ ] Inspector usable.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not change policy engine semantics.

## 10. Related PRDs & references

- LEARNING.md §3.4.
