# PRD 001: Unify token counting through a single `TokenCounter` service

- **Wave:** 1
- **Status:** ready
- **Owner (human):** @gongahkia
- **Assignee (agent):** _unassigned_
- **Estimated effort:** medium (2–3d)
- **Blocks:** 017, 018, 027
- **Blocked by:** —
- **Files it mutates:**
  - `poor_cli/context.py`
  - `poor_cli/context_optimizer.py`
  - `poor_cli/token_budget_controller.py`
  - `poor_cli/core.py` (limited — only at token-counting call sites)
  - `poor_cli/history_pruning.py`
  - `poor_cli/prompt_compressor.py`
  - `poor_cli/providers/base.py`
- **New files it adds:**
  - `poor_cli/token_counter.py`
  - `tests/test_token_counter.py`
  - `tests/test_token_counter_integration.py`

---

## 1. Problem

The repository today estimates token counts in at least four different places, each with its own `chars_per_token` ratio and heuristic:

- `poor_cli/context.py` — uses a ratio near 4 chars/token for English and has its own code-heavier override.
- `poor_cli/context_optimizer.py` — independent estimator for its tiered compaction policy (defer → prune → compress).
- `poor_cli/token_budget_controller.py` — rule-based allocator with its own ratio for thinking-token and output-token reserves.
- `poor_cli/core.py` — inline estimates for budget warnings and overflow detection.

These estimators **silently diverge**. When the budget controller says "2 KB left" and the compressor says "0.5 KB left", the agent loop truncates prompts mid-flight or — worse — Anthropic rejects the request for exceeding `max_tokens` while the logs show headroom. This is flagged in [`LEARNING.md` §2.1](../LEARNING.md) as "the highest-leverage single bug fix in the repo."

The downstream symptom for users: unpredictable truncation, unexplained rate-limit errors on long turns, and poor cache hit rates because the cached prefix length disagrees with the current-turn length. PAIN-POINTS.md #1 (context accumulation) compounds because every turn's estimate can wander.

## 2. Current state

Run `grep -n "chars_per_token\|estimate_tokens\|count_tokens\|num_tokens" poor_cli/*.py | head -60` to see the scatter. Representative signatures today:

- `ContextManager.estimate_tokens(text: str) -> int` in `context.py`
- `ContextOptimizer._estimate_tokens(text) -> int` in `context_optimizer.py`
- `TokenBudgetController._approx_tokens(...)` in `token_budget_controller.py`
- inline `len(text) // 4` expressions in `core.py` and `history_pruning.py`

None of these import each other. Each has comments along the lines of "approximate — good enough for budgeting" but none agree on the approximation.

Providers do expose provider-native counts when available:

- Anthropic SDK: `client.messages.count_tokens(model=..., messages=...)`
- OpenAI SDK: `tiktoken.encoding_for_model(model).encode(...)`
- Gemini: `model.count_tokens(...)` async
- Ollama / OpenRouter: no native count; fall back to tiktoken (`cl100k_base`) or `o200k_base` for GPT-5.

These are not used consistently — `base.py` has `count_tokens` abstract method on the provider interface, but most callers estimate locally instead of routing through the provider.

## 3. Goal & non-goals

**Goal:** every token count anywhere in the codebase routes through a single `TokenCounter` service with per-provider calibration, a test that asserts `sum(parts) == whole` across a realistic session, and no `chars_per_token`-style magic numbers outside this one module.

**Non-goals:**
- Do NOT change how budgets are allocated (that is `token_budget_controller` logic — keep its policy, just switch its counter).
- Do NOT change how context is assembled or pruned (PRD 018 owns that).
- Do NOT add tokenizer-based re-ranking or compression (that's PRD 058).
- Do NOT attempt exact billable-token accuracy for Gemini / Ollama (approximations are fine if provider-exact unavailable; just document the approximation).

## 4. Design

### 4.1 Module shape

```python
# poor_cli/token_counter.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Literal

ProviderId = Literal["anthropic", "openai", "gemini", "ollama", "openrouter"]

@dataclass(frozen=True)
class TokenCount:
    """A token count plus the calibration source that produced it."""
    count: int
    source: Literal["native", "tiktoken", "heuristic"]
    provider: ProviderId | None
    model: str | None

class CountBackend(Protocol):
    def count(self, text: str, *, model: str | None = None) -> int: ...

class TokenCounter:
    """
    Single source of truth for token counts.

    Resolution order per (provider, model):
      1. Provider-native counter if the SDK exposes one and we have a client.
      2. tiktoken with the right encoding if provider is OpenAI-compatible.
      3. Calibrated heuristic fallback keyed by (provider, model) — never a magic number.

    Thread-safe, async-safe. Caches encodings.
    """
    def __init__(self, *, native_backends: dict[ProviderId, CountBackend] | None = None) -> None: ...

    def count(
        self,
        text: str,
        *,
        provider: ProviderId | None = None,
        model: str | None = None,
    ) -> TokenCount: ...

    async def acount(
        self,
        text: str,
        *,
        provider: ProviderId | None = None,
        model: str | None = None,
    ) -> TokenCount: ...

    def count_messages(
        self,
        messages: list[dict],
        *,
        provider: ProviderId | None = None,
        model: str | None = None,
    ) -> TokenCount: ...

    def reserve(self, *, budget: int, for_parts: dict[str, str]) -> dict[str, int]:
        """
        Given a budget and a dict of named parts (prompt, system, history, tools),
        return an allocation dict where sum(values) <= budget.
        Used by token_budget_controller — replaces its local estimator.
        """

# module-level singleton accessor
def get_token_counter() -> TokenCounter: ...
def set_token_counter(tc: TokenCounter) -> None: ...  # for tests
```

### 4.2 Calibration table

The heuristic fallback is a simple table, kept in this file (not config — this is a measurement, not a preference):

```python
# chars per token, calibrated against empirical samples (code-heavy + English-heavy)
HEURISTIC_CHARS_PER_TOKEN = {
    ("anthropic", "*"):            3.5,
    ("openai",    "gpt-5.1"):      3.7,
    ("openai",    "gpt-5-mini"):   3.7,
    ("openai",    "*"):            3.8,
    ("gemini",    "*"):            3.6,
    ("openrouter","*"):            3.7,  # routes to underlying provider; fallback avg
    ("ollama",    "*"):            3.9,  # local, varies by model
    (None,        None):           3.8,  # last-resort
}
```

Calibration numbers come from measuring representative code+prose samples against each provider's native count during test setup — see Testing below.

### 4.3 Integration points

Every existing estimator migrates to call this counter:

| Old call site | New call |
|---|---|
| `ContextManager.estimate_tokens(text)` in `context.py` | `get_token_counter().count(text, provider=self.provider_id, model=self.model_id).count` |
| `ContextOptimizer._estimate_tokens(text)` | same |
| `TokenBudgetController._approx_tokens(text)` | same |
| inline `len(text) // 4` in `core.py:NNN` | same |
| inline in `history_pruning.py` | same |
| inline in `prompt_compressor.py` | same |

The **Provider base class** gains a concrete default implementation that routes through `TokenCounter` so subclasses don't need to override unless they have a native backend to register.

```python
# poor_cli/providers/base.py
class BaseProvider(ABC):
    ...
    def count_tokens(self, text: str, *, model: str | None = None) -> int:
        return get_token_counter().count(
            text, provider=self.provider_id, model=model or self.default_model
        ).count
```

### 4.4 Invariant we will test

For any provider / model / message list:

```
sum(counter.count(part).count for part in parts)
    ≤ counter.count(joined).count + len(parts) * 2
```

(small slack for BPE merges across boundaries). Test proves this holds for every provider's backend.

## 5. Files to create / modify / delete

**Create**

- `poor_cli/token_counter.py` — the service, calibration table, singleton accessor.
- `tests/test_token_counter.py` — unit tests for the counter itself.
- `tests/test_token_counter_integration.py` — proves the invariant across a realistic session payload for each provider.

**Modify**

- `poor_cli/context.py` — delete `estimate_tokens`, replace every call site with `get_token_counter().count(...).count`.
- `poor_cli/context_optimizer.py` — same.
- `poor_cli/token_budget_controller.py` — same; also route the `.reserve()` allocation through the counter.
- `poor_cli/core.py` — only the token-counting call sites. Do **not** refactor anything else (that's PRD 017).
- `poor_cli/history_pruning.py` — same.
- `poor_cli/prompt_compressor.py` — same.
- `poor_cli/providers/base.py` — concrete `count_tokens` default.
- Each provider adapter in `poor_cli/providers/*_provider.py` — register a `CountBackend` implementation with the counter at init time if the SDK exposes native counting.

**Delete** — nothing. (Remove private estimator methods in the modified modules.)

## 6. Implementation plan

1. Create `poor_cli/token_counter.py` with the `TokenCounter` class, calibration table, singleton accessor, and no integration yet.
2. Write `tests/test_token_counter.py` covering: heuristic fallback, unknown-provider path, cache behavior, thread-safety (simultaneous `count` from two threads).
3. Add a `CountBackend` protocol implementation in each provider adapter. Each registers with the counter at `__init__` via `set_token_counter(...)` or a register call.
4. 🟠 Run the native counters against a fixed 4-sample corpus (`tests/fixtures/token_corpus/{code.py,prose.md,mixed.json,large.lua}`) and measure actual chars-per-token. Update `HEURISTIC_CHARS_PER_TOKEN` to match.
5. Migrate `context.py` first — it has the most call sites. Prove tests still pass.
6. Migrate `context_optimizer.py`, `token_budget_controller.py`, `history_pruning.py`, `prompt_compressor.py`.
7. 🟠 Migrate `core.py` **only the token-counting call sites**. Use `grep -n "len(\w\+) // 4\|_estimate_tokens\|estimate_tokens"` to find them. Touch nothing else in `core.py` — PRD 017 owns the broader decomposition.
8. Write the integration test in `tests/test_token_counter_integration.py` asserting the `sum(parts) ≤ whole + slack` invariant for a canned session across Anthropic / OpenAI / Gemini / Ollama (using mock backends — real SDK calls gated behind env vars and skipped in CI if absent).
9. Add a budget-warning smoke test: simulate a 90% full budget and assert the counter agrees within 2% of the provider-native count.
10. Run `make lint && make test`. All green.

## 7. Testing & acceptance criteria

**New tests**

- `tests/test_token_counter.py::test_heuristic_fallback_uses_calibration_table`
- `tests/test_token_counter.py::test_native_backend_preferred_over_heuristic`
- `tests/test_token_counter.py::test_unknown_provider_falls_back_cleanly`
- `tests/test_token_counter.py::test_counter_is_thread_safe`
- `tests/test_token_counter.py::test_count_messages_sums_across_messages_within_slack`
- `tests/test_token_counter_integration.py::test_sum_of_parts_within_slack_anthropic`
- `tests/test_token_counter_integration.py::test_sum_of_parts_within_slack_openai`
- `tests/test_token_counter_integration.py::test_context_manager_uses_global_counter`
- `tests/test_token_counter_integration.py::test_budget_controller_reservations_sum_to_budget`

**Commands to pass**

- `make lint`
- `make test`

**Manual verification**

- Run a realistic session: `.venv/bin/poor-cli exec --prompt "Summarize docs/MULTIPLAYER.md"` and confirm the logged token count for the assembled prompt agrees within 2% of the provider-reported usage for the response turn. (Use `/cost` after.)

**Done criterion**

- [ ] No `chars_per_token` literal exists outside `poor_cli/token_counter.py` (grep-verified).
- [ ] Every previously-existing token-estimation function is gone or delegates to `TokenCounter`.
- [ ] Integration test proves sum-of-parts invariant.
- [ ] `make test` passes on Python 3.12 and 3.14.

## 8. Rollback / risk

Risk is low — behavior-preserving refactor. If a calibration number is wrong, worst case is that budgets are 5–10% more or less conservative than before (which is the current state anyway). Rollback = revert the PR.

No persisted-state migration.

If a native counter is slow (Anthropic's `count_tokens` is a network call), the counter must degrade to the heuristic for interactive use and retain the native count only for accounting / logging. The `source` field in `TokenCount` makes this observable.

## 9. Out-of-scope & boundary

- 🚫 Do not touch `core.py` except the token-counting call sites. Do not extract, rename, or move functions in `core.py`. PRD 017 owns that.
- 🚫 Do not change budget *policy* (how many tokens get reserved for thinking vs output). Only change the *counter* that policy uses.
- 🚫 Do not change prompt caching logic. PRD 027 owns that.
- 🚫 Do not change the provider abstraction surface (no new abstract methods on `BaseProvider` beyond `count_tokens`, which already exists).
- 🚫 Do not alter the code tokenizer or embeddings code.

## 10. Related PRDs & references

- Downstream blockers that need this: PRD 017 (core pre-slice — needs a clean counter to extract around), PRD 018 (ContextAssemblyOrchestrator), PRD 027 (block-level caching).
- LEARNING.md §2.1 "Four distinct token counters silently disagree".
- PAIN-POINTS.md #1 (context accumulation) and #12 (code tokenization inefficiency).
- Anthropic token-counting API: https://docs.anthropic.com/en/api/messages-count-tokens
- tiktoken: https://github.com/openai/tiktoken
