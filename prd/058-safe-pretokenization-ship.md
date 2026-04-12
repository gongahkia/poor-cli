# PRD 058: Ship safe pre-tokenization end-to-end

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/code_tokenizer.py`
  - `poor_cli/context_assembly.py` (opt-in hook)
  - `poor_cli/economy.py` (track savings)
- **New files it adds:**
  - `tests/test_safe_pretokenization.py`

## 1. Problem

`docs/CODE_TOKENIZER_RESEARCH.md` and the `bench_safe_pretok.py` benchmark show safe pre-tokenization yields ~6.4% token savings with 99% parseability. Not shipped. LEARNING.md §2.2, §1.5.

## 2. Current state

Module exists; tests exist (`bench_safe_pretok.py`). Not integrated into context assembly.

## 3. Goal & non-goals

**Goal:** a config option `context.safe_pretokenization = true` (default off v1, on v2 after real-world data) that runs code files through the safe pre-tokenizer before adding to context. Savings tracked in economy.

**Non-goals:**
- Do not ship aggressive pre-tokenization.
- Do not re-benchmark (existing benchmark is the evidence).

## 4. Design

`code_tokenizer.safe_pretokenize(text, language_hint) -> str`. Call from `context_assembly` when writing file content into the snapshot. Record `original_tokens, compressed_tokens` on each `ContextFile`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Expose `safe_pretokenize`.
2. Add config option; feature-flag default off.
3. Integrate into assembly.
4. Economy tracking.
5. Tests verifying parseability and savings on fixture.

## 7. Testing & acceptance criteria

- `test_pretokenize_preserves_parseability`
- `test_pretokenize_reduces_tokens_by_at_least_5pct`

**Done criterion**
- [ ] Feature works end-to-end.
- [ ] Opt-in config flag.

## 8. Rollback / risk

Low. Opt-in; failure path returns original content.

## 9. Out-of-scope & boundary

- 🚫 Do not ship aggressive mode.
- 🚫 Do not relocate to research/.

## 10. Related PRDs & references

- LEARNING.md §2.2, §1.5.
- `docs/CODE_TOKENIZER_RESEARCH.md`.
