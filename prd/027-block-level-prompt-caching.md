# PRD 027: Non-prefix / block-level prompt caching

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** medium (2w)
- **Blocks:** —
- **Blocked by:** 001, 020
- **Files it mutates:**
  - `poor_cli/providers/anthropic_provider.py`
  - `poor_cli/providers/openai_provider.py`
  - `poor_cli/context_assembly.py`
  - `poor_cli/semantic_cache.py` (narrow — integrate with block cache)
- **New files it adds:**
  - `poor_cli/block_cache.py`
  - `tests/test_block_cache.py`

## 1. Problem

Prompt caching today only works on prefix matches. Re-reading a file later in a session pays full prefill cost. LEARNING.md §2.2. PAIN-POINTS.md #15.

## 2. Current state

Anthropic `cache_control` is used only on the system prompt. OpenAI's automatic prefix caching is taken for what it gives.

## 3. Goal & non-goals

**Goal:** block-level caching where each context file (and optionally rules/tool schemas) is a separate cache block with its own `cache_control` marker. Re-reading the same file later re-uses the cache even if position changed.

**Non-goals:**
- Do not implement cross-session caching beyond what providers offer.
- Do not cache agent outputs (PRD 004 covers semantic response cache).

## 4. Design

### 4.1 Block decomposition in `ContextSnapshot`

`ContextSnapshot.files` → each file becomes a cache block in the outgoing message array.

### 4.2 Anthropic

Set `cache_control = {"type": "ephemeral"}` on the content block. Anthropic caches per-block 5-minute TTL. Check `PROMPT_CACHING_BLOCK` capability (PRD 020).

### 4.3 OpenAI

OpenAI auto-caches prefixes of ≥1,024 tokens. Restructure messages so frequently-reused content is near the start. Add telemetry.

### 4.4 Cache hit rate metrics

Expose via `/costSummary` (PRD 016).

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Add `block_cache.py` with utilities to mark cacheable blocks in the provider message format.
2. Anthropic integration first — concrete API.
3. OpenAI reorder heuristic + telemetry.
4. Tests comparing hit rate on a multi-turn fixture.
5. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_anthropic_block_cache_marker_emitted`
- `test_file_reuse_within_session_records_cache_hit`
- `test_unsupported_provider_silently_skips`

**Done criterion**
- [ ] Files cached per block.
- [ ] Hit rate rises measurably on 5-turn rework fixture.

## 8. Rollback / risk

Medium. Anthropic rejects malformed cache_control markers.

## 9. Out-of-scope & boundary

- 🚫 Do not change context selection.
- 🚫 Do not extend KV cache (research module).

## 10. Related PRDs & references

- PRD 001, 020.
- Anthropic caching docs.
- LEARNING.md §2.2. PAIN-POINTS.md #15.
