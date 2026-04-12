# PRD 045: Chat — slash command autocomplete

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** small-to-medium (3–4d)
- **Blocked by:** 044
- **Conflicts with:** 046, 047
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/chat.lua`

## 1. Problem

90+ slash commands; discoverability is painful. LEARNING.md §3.5 #6.

## 2. Current state

User types `/` then remembers the command.

## 3. Goal & non-goals

**Goal:** typing `/` in the chat input triggers a picker / popup listing slash commands with 1-line descriptions. Fuzzy-match as user types.

**Non-goals:**
- Do not replace the command list; reflect it.

## 4. Design

Use picker adapter (PRD 055). Trigger on `/` at column 1 of the input. Fuzzy-filter. Preview description + examples.

## 5. Files to create / modify / delete

Modify `chat.lua`.

## 6. Implementation plan

1. Hook InsertCharPre for `/` at col 1.
2. Open picker.
3. On pick, insert the command + cursor in argument position.
4. Tests.

## 7. Testing & acceptance criteria

- `test_slash_triggers_picker`
- `test_fuzzy_filter_narrows`
- `test_pick_inserts_command`

**Done criterion**
- [ ] Autocomplete usable.

## 8. Rollback / risk

Low.

## 9. Out-of-scope & boundary

- 🚫 Do not introduce new slash commands.

## 10. Related PRDs & references

- PRD 055. LEARNING.md §3.5.
