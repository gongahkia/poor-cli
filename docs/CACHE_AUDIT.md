# Cache Fragmentation Audit

Investigation of cache-related modules in `poor_cli/` to identify
redundancy, lifetime overlap, and consolidation opportunities.

Source: original pain-point analysis (optimization #5 of 13).

## Inventory

| Module | Purpose | Backend | TTL/eviction | Scope |
| --- | --- | --- | --- | --- |
| `semantic_cache.py` | cache LLM responses keyed by query+context; cosine-sim lookup over embeddings | SQLite + embeddings table | `DEFAULT_TTL_SECONDS=86400` (24h), `DEFAULT_MAX_ENTRIES=2048` | cross-session (persistent) |
| `kv_cache_store.py` | KV cache precompute/reuse for self-hosted inference (vLLM/LMCache) | local files + HTTP to LMCache | manual invalidation on content_hash mismatch | cross-session |
| `file_cache.py` | LRU cache for file reads | in-memory OrderedDict + optional SQLite persistence | `ttl_seconds` opt-in; `max_size=128` LRU | cross-session |
| `failure_amnesia.py` | compress failed tool traces into short "lessons" kept in chat history | in-memory (part of turn state) | turn-scoped; no TTL | within-session |
| `working_memory.py` | short-term scratchpad across turns | in-memory | session-scoped | within-session |
| `context_compressor.py` | llmlingua-based prompt compression | in-memory | turn-scoped | within-session |

## Findings

### 1. Same verb, different semantics
"cache" in this codebase spans four distinct ideas:
- **Response cache** (`semantic_cache`): LLM output memoization
- **Model-side KV** (`kv_cache_store`): inference-time attention state
- **Filesystem memoization** (`file_cache`): disk read memoization
- **Lossy context pruning** (`failure_amnesia`, `context_compressor`): dropping/rewriting chat history

[Inference] Each is legitimate on its own; grouping them under "cache" makes
the mental model worse. Rename or namespace is a low-risk cleanup.

### 2. No shared eviction policy or coordination
Each module owns its own SQLite DB (or in-mem store), TTL, max-size knob.
[Inference] There is no global disk-budget enforcement; if a user hits
heavy use, the three on-disk caches (`semantic_cache.db`,
`file_cache.db`, KV artifacts) can grow independently without either
module knowing.

### 3. Lifetime overlap that isn't actually redundancy
- `semantic_cache` + `file_cache`: don't overlap — one caches model
  *output*, the other caches file *input*.
- `failure_amnesia` + `context_compressor`: overlap in intent (shrink
  history) but distinct triggers (failures vs token pressure). Keeping
  them separate is correct.
- `kv_cache_store`: separate universe — only relevant with vLLM/LMCache
  backends, dead code for closed-API users.

### 4. Configuration knobs aren't centralized
[Verified] TTLs, max-sizes, and enable flags are per-module constants
or per-instance args. No single `config.cache.*` section.

## Recommendations (no code change in this commit)

1. **Rename for clarity**
   - `semantic_cache` → `response_cache` (it's not a generic semantic store)
   - Keep `kv_cache_store` as-is (industry term)
   - Keep `file_cache` as-is
   - Consider re-homing `failure_amnesia` + `context_compressor` under
     `context_pruning/` since they aren't caches.

2. **Unified config section** — add `config.cache.{response,file,kv}` with
   enable/ttl/max_entries; deprecate the per-module constants.

3. **Shared disk-budget monitor** — single service that tallies SQLite
   file sizes across the caches and enforces a total budget with LRU-by-mtime
   eviction.

4. **Surface stats in `:PoorCliStats`** — currently each cache reports its
   own stats via ad-hoc paths. Publish one unified view.

## Non-findings (things we checked that are fine)

- **`semantic_cache` vs `file_cache` overlap** — they cache different
  things and do not duplicate work.
- **`failure_amnesia` token savings** — directly aligned with the
  product's core token-saving mission.
- **In-memory vs persistent split** — the in-memory modules are all
  turn-scoped or session-scoped, which is correct.

## Priority

- **Low** — nothing here is a correctness or latency bug. Pure hygiene.
- If tackled, take items in order: (1) rename, (2) config consolidation,
  (3) shared budget. (4) is a UI polish dependent on (2).
