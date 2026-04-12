# PRD 056: `neogit` integration for commit review

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small-to-medium (3d)
- **Blocked by:** —
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/neogit_bridge.lua`
  - `nvim-poor-cli/tests/neogit_bridge_spec.lua`

## 1. Problem

Agent proposes commits via `/commit` — no integration with neogit. Users want to review staged AI changes in neogit's staging view. LEARNING.md §3.8.

## 2. Current state

`/commit` runs server-side; no UI bridge.

## 3. Goal & non-goals

**Goal:** after `/commit`, if neogit is present and config `neogit.open_on_commit = true`, open neogit's status view, stage only the files touched by the last AI turn, pre-fill the commit message from the agent's proposal.

**Non-goals:**
- Do not hard-depend on neogit.
- Do not modify neogit itself.

## 4. Design

Use neogit's public API to open status + set commit message.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Bridge.
2. Config option.
3. Plenary tests with mocked neogit.

## 7. Testing & acceptance criteria

- `test_opens_neogit_with_prefilled_message`
- `test_noop_when_neogit_absent`

**Done criterion**
- [ ] Flow works end-to-end when neogit present.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not depend on neogit.

## 10. Related PRDs & references

- neogit: https://github.com/NeogitOrg/neogit
- LEARNING.md §3.8.
