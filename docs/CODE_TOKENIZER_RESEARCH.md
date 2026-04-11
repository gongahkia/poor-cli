# Code-Specific Tokenizer Research

**Agent:** 8C — Code-Specific Tokenizer Research  
**Date:** 2026-04-11  
**Status:** Complete  
**Recommendation:** **Partially pursue** — safe pre-tokenization for context-only files; shelve model-level tokenizer changes

---

## 1. Problem Statement

Standard BPE tokenizers (cl100k_base, o200k_base) impose a constant ~2× token overhead on source code vs English prose. This directly inflates API costs for every turn.

## 2. Baseline Measurement

Measured 195 files from poor-cli (144 Python, 37 Lua, 3 TypeScript, 11 test files) with `cl100k_base` (GPT-4/Claude tokenizer).

| Metric | English Prose | Python | Lua | TypeScript | All Code |
|--------|:---:|:---:|:---:|:---:|:---:|
| Tokens/word | 1.32 | 2.64 | 2.38 | 2.47 | 2.59 |
| Overhead vs English | 1.0× | **2.0×** | **1.8×** | **1.9×** | **1.96×** |

**Total:** 607,651 tokens across 2.88M chars (194 non-trivial files).  
**Indentation:** 18.7% of all characters are leading whitespace.

Worst offenders: test files with repetitive assertions (up to 4.1× tokens/word).

`o200k_base` (GPT-4o) showed nearly identical ratios — code overhead is structural, not tokenizer-version-specific.

## 3. Literature Review

### CodeBPE (arXiv 2308.00683)

Code-aware BPE that respects syntax boundaries during merge operations. Learns merge rules aligned with language syntax instead of raw character frequency.

- **Results:** 10-30% fewer tokens for equivalent code
- **Requires model retraining:** Yes — custom tokenizer must be paired with model embeddings
- **Usable with closed APIs (GPT-4, Claude):** **No**

### AST-T5 (arXiv 2401.03003)

Structure-aware pretraining using AST decomposition. Serializes ASTs and trains T5-style models with structure-aware objectives.

- **Results:** Improved CodeSearchNet/code-gen benchmarks over CodeT5 baselines
- **Requires model retraining:** Yes — entire pretraining strategy change
- **Usable with closed APIs:** **No**

### Other approaches surveyed

| Approach | Requires Retraining | API-Compatible | Notes |
|----------|:---:|:---:|---|
| StarCoder/SantaCoder tokenizers | Yes | No | Code-optimized BPE, model-specific |
| TokenMonster | Yes | No | Alternative to BPE, better compression |
| LLMLingua/LongLLMLingua | No | **Yes** | General prompt compression, 2-5× claimed |
| Minification (Terser, etc.) | No | **Yes** | 20-60% for JS, language-specific |
| Comment/whitespace stripping | No | **Yes** | 10-30%, simple and proven |

**Key finding:** No approach that changes the tokenizer itself can work with closed-API models. Only preprocessing (before sending to the API) is viable for poor-cli's primary use case.

## 4. Prototypes & Benchmarks

### Approach A: Code Pre-tokenization

Pipeline: collapse indentation (4 spaces→tab) + normalize identifiers (camelCase→snake_case) + strip comments + collapse blank lines.

#### Full pre-tokenization (aggressive)

| Language | Baseline | After | Reduction | Parseability |
|----------|:---:|:---:|:---:|:---:|
| Python | 522,075 | 462,398 | **11.4%** | 65.5% |
| Lua | 83,768 | 80,863 | 3.5% | N/A |
| TypeScript | 1,808 | 1,823 | -0.8% | N/A |
| **Total** | **607,651** | **545,084** | **10.3%** | — |

**Problem:** Identifier normalization (camelCase→snake_case) breaks 34.5% of Python files. String literals containing `#` get corrupted by comment stripping. TS files get slightly *worse* because snake_case expands identifiers.

#### Safe pre-tokenization (conservative)

Pipeline: strip full-line comments only + remove docstrings via AST + collapse indentation + collapse blank lines. **No identifier changes, no inline comment removal.**

| Language | Baseline | After | Reduction | Parseability |
|----------|:---:|:---:|:---:|:---:|
| Python | 532,642 | 495,643 | **6.9%** | 99.0% (156/158) |
| Lua | 83,768 | 81,191 | 3.1% | 100% |
| TypeScript | 1,808 | 1,787 | 1.2% | 100% |
| **Total** | **618,218** | **578,621** | **6.4%** | **99.0%** |

**Verdict:** Safe, modest savings. Applicable to context-window files only (not edit targets, since indentation is changed).

### Approach B: Hybrid AST-Token Representation

Python AST → compact serialization. Drops docstrings, normalizes whitespace, collapses control flow.

| Metric | Value |
|--------|:---:|
| Token reduction (Python only) | **48.6%** |
| Function defs preserved | 95.7% |
| Class defs preserved | 76.9% |
| Output parseable as Python | **2.7%** |

Best-case reductions: 85-87% on small utility files, 70-77% on provider modules.

**Problem:** The output is NOT valid Python — it's a compact summary. The model cannot produce valid search-replace edits against it. 76.9% class preservation means ~23% of classes are silently dropped.

**Verdict:** Useful as a **read-only code summary/index** (like the existing AST chunking in Phase 5B), NOT as a code representation for editing.

### Approach A+B Combined

| Total | Baseline | Combined | Reduction |
|-------|:---:|:---:|:---:|
| All files | 607,651 | 351,013 | **42.2%** |

Impressive reduction, but inherits Approach B's edit-accuracy problems.

## 5. Edit Accuracy Analysis

| Approach | Can model produce valid edits? | Safe for context? | Safe for edit target? |
|----------|:---:|:---:|:---:|
| Original code | ✅ | ✅ | ✅ |
| Safe pretok | ❌ (indentation changed) | ✅ | ❌ |
| Full pretok | ❌ (names + indent changed) | ⚠️ (65% parseable) | ❌ |
| AST-compact | ❌ (completely rewritten) | ✅ (as summary) | ❌ |

**No transformation is safe for edit targets.** All approaches change the code text in ways that prevent the model from producing valid search-replace patches against the original file.

## 6. Practical Recommendations

### Pursue: Safe pre-tokenization for context-only files (6.4% savings)

Apply whitespace/comment stripping to files loaded into the context window for understanding (not for editing). This is:
- Low risk (99% parseability)
- Language-agnostic
- Complementary to existing context selection (phases 1-7)
- Easy to implement: only transform files where `is_edit_target = False`

**Integration point:** `poor_cli/context_engine.py` — when building context for a turn, apply `safe_pretokenize()` to non-target files before token counting.

### Consider: AST-compact as context index format

When the context window is tight, represent distant files as AST-compact summaries instead of full source. This is what Phase 5B's AST chunking already does. The 48.6% reduction validates that approach.

### Shelve: Tokenizer-level changes

CodeBPE, AST-T5, vocabulary extension — all require model retraining or open-weights access. Not applicable to closed-API usage (poor-cli's primary use case). If poor-cli adds deep Ollama/vLLM integration with custom fine-tunes, revisit.

### Shelve: Identifier normalization

The camelCase→snake_case transformation saves ~4% additional tokens but breaks 35% of files. The savings-to-risk ratio is unacceptable.

## 7. Summary Table

| Approach | Savings | Risk | Verdict |
|----------|:---:|:---:|---|
| Safe pretok (context-only) | 6.4% | Low | **Pursue** |
| AST-compact (summaries) | 48.6% | Medium | **Already covered by Phase 5B** |
| Full pretok (identifiers) | 10.3% | High | **Shelve** |
| CodeBPE/AST-T5 | 30-50% (theoretical) | N/A | **Shelve** (requires model retraining) |
| Token vocab extension | Unknown | N/A | **Shelve** (requires open-weights) |

## 8. Files Produced

- `poor_cli/code_tokenizer.py` — research prototypes (Approach A, B, A+B)
- `tests/bench_tokenizer.py` — baseline measurement script
- `tests/bench_tokenizer_full.py` — full benchmark (all approaches)
- `tests/bench_safe_pretok.py` — safe-only variant benchmark
- `tests/bench_edit_accuracy.py` — edit accuracy validation
- `tests/tokenizer_bench_results.json` — raw benchmark data
- `tests/edit_accuracy_results.json` — raw accuracy data

## References

- [CodeBPE](https://arxiv.org/abs/2308.00683)
- [AST-T5](https://arxiv.org/abs/2401.03003)
- [tiktoken](https://github.com/openai/tiktoken)
- [LLMLingua](https://arxiv.org/abs/2310.05736)
