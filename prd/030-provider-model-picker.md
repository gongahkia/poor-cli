# PRD 030: Provider / Model Picker modal

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (4–5d)
- **Blocked by:** 020
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/providers.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
  - `nvim-poor-cli/lua/poor-cli/keymaps.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/provider_picker.lua`
  - `nvim-poor-cli/tests/provider_picker_spec.lua`

## 1. Problem

`:PoorCliSwitchProvider` takes a text arg. Discoverability is poor. Users don't know which models are available, their capabilities (cache? thinking?), or estimated cost per 1K tokens. LEARNING.md §3.4.

## 2. Current state

Command-line arg parsing. No UI.

## 3. Goal & non-goals

**Goal:** modal picker (via PRD 055 adapter) listing providers → models with capability icons (🔁 streaming, 🧠 thinking, 📦 caching, 👁 vision) and $$/1K-token indicators. Selecting switches provider+model.

**Non-goals:**
- Do not implement capability discovery (PRD 020 handles).
- Do not change economy logic.

## 4. Design

Uses `picker_adapter.pick(items, opts)` from PRD 055. Each item is formatted:

```
anthropic / claude-sonnet-4        🔁 🧠 📦 👁   $3.00/$15.00  (current)
anthropic / claude-3-5-haiku       🔁             $0.80/$4.00
openai / gpt-5.1                   🔁 🧠    👁   $2.50/$10.00
gemini / gemini-2.5-flash          🔁        👁   $0.075/$0.30
ollama / llama3.1                  🔁             local (free)
```

Preview pane (right side): expanded capability list, model description, last-used.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Build the item list from `provider_catalog.py` + capabilities.
2. Use picker adapter.
3. On pick: `poor-cli/switchProvider` RPC.
4. Cache last-used; surface at the top.
5. Tests.

## 7. Testing & acceptance criteria

- `test_items_include_capability_icons`
- `test_selecting_item_calls_switch_rpc`
- `test_current_model_marked`

**Done criterion**
- [ ] Modal opens, picks, switches.
- [ ] Capabilities visible.

## 8. Rollback / risk

Low. Command-line variant still works.

## 9. Out-of-scope & boundary

- 🚫 Do not implement per-model pricing discovery.
- 🚫 Do not fetch from a remote catalog.

## 10. Related PRDs & references

- PRD 020, 055.
- LEARNING.md §3.4.
