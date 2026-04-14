# docs/archive/

Historical research and migration docs whose conclusions have been folded back into the main codebase. Kept for archaeological reference; not load-bearing for current contributors.

| File | Archived | Why |
|---|---|---|
| `core_pre_slice_placement_map.md` | 2026-04-14 | PRD 017 pre-slice plan. Decomposition (C3) is done; `core.py` now 865 LOC. |
| `CACHE_AUDIT.md` | 2026-04-14 | One-shot investigation doc; recommendations tagged "low priority / pure hygiene". |
| `LATENT_REASONING.md` | 2026-04-14 | Phase 8B research. All three approaches (Coconut, Quiet-STaR, CODI) marked infeasible; practical fallback `thinking_budget.py` shipped. |
| `NEURAL_CODE_EMBEDDINGS.md` | 2026-04-14 | Phase 8D research. Verdict: "Stick with neural retrieval." Fallback shipped via `neural_code_encoder.py`. |
| `CODE_TOKENIZER_RESEARCH.md` | 2026-04-14 | Phase 8C research. Verdict: "Partially pursue / shelve model-level changes." Safe pre-tokenizer shipped via Phase 12F. |

`MULTIPLAYER_DECISION.md` was deleted outright (not archived) because `phase_20/063_outcome.md` supersedes it and two sources of truth invite drift.
