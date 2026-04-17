# PROPOSAL E — Token Frugality Across the Tool Surface

> **Target:** poor-cli v6.4 / backend-only (Python).
> **Depends on:** Phases A / B / C landed. Does not block PROPOSAL D; they land in parallel.
> **Estimated effort:** 2–3 engineer days.

---

## 1. Philosophical bearings

**"Poor" is the product name.** Every token the harness burns unnecessarily is
a bug, not a feature. The tool system added ~34 new tools in Phase B — some of
them (git.status, fs.browse, review.changes) are pure functions of repo state
that the agent will plausibly call 3+ times in a single session. Caching those
inside a session costs nothing and saves turns.

**Atomic, composable, cheap.** Each tool is a small function. We never hide
tokens by running an LLM under the hood of a tool. We never silently make a
call expensive. Every optimization here is either:

  (a) pure memoization (identical inputs → same output → skip the handler), or
  (b) trimming/truncating context that's about to be sent to the provider.

We do NOT use embeddings, summarization, re-ranking, or any LLM-in-the-loop
trickery as part of this proposal. Those live in PROPOSAL-G-FUTURES.

**Correctness over savings.** A cache that returns a stale result wastes far
more tokens than the cache saves (agent acts on wrong data → retries). Default
TTL is aggressive only for tools we mark as pure. Everything else is opt-in.

**Prompt caching is already live** on Anthropic (see
`poor_cli/providers/anthropic_provider.py`). This proposal makes sure we
don't accidentally bust the cache with variable content shoved in front of
stable content.

## 2. Anti-scope-creep fences

- **No persistent cross-session caches.** In-session only, LRU-bounded.
  Disk caches (SQLite, etc.) require invalidation strategies we don't want
  to own. See PROPOSAL-G.
- **No LLM-based summarization of tool results.** Spends tokens to save
  tokens — net effect unclear and can be worse.
- **No semantic re-ranking** of tools via embeddings. Tool selection is
  the agent's job; we give it `meta.*` discovery (PROPOSAL D) instead.
- **No auto-compaction of user chat messages.** Existing context_optimizer
  handles that; we don't second-guess it here.
- **No prompt-compression libraries** (llmlingua). Tried and rejected in
  v5 — brittle, opaque, often counter-productive.

## 3. End state (definition of success)

Four separable features, all behind feature flags so partial rollout is
possible:

| Feature | Flag | What |
|---|---|---|
| E1 Tool-call memoization | `tools.memoize = true` (default) | In-session cache keyed on `(tool, sha256(args))` with per-tool TTL |
| E2 Result truncation | `tools.max_result_tokens = 8000` (default) | Tool outputs over budget get middle-truncated with metadata.truncated |
| E3 Manifest stability | always on | Tool manifest is sorted deterministically + rendered first in system prompt so cache hits. Measured via provider cache-hit telemetry |
| E4 Lazy tool advertisement | `tools.lazy_manifest = false` (default off) | Opt-in: start prompt with domain summary, require meta.list_tools for full schemas |

**Hard invariants:**

1. E1: Two successive calls to `git.status` with the same args within TTL
   invoke the handler once. Verified by CallRecord count and a handler spy.
2. E1: Tools marked `exclusive` bypass the cache (they mutate state; caching
   is unsafe).
3. E1: Tools raising `TransientError` mid-call never populate the cache.
4. E2: A handler returning 50k tokens of output is truncated to <=8000 tokens
   with `metadata.truncated = true` and `metadata.original_token_estimate` set.
5. E2: A follow-up `tool_blob.get({result_id})` retrieves the full content.
6. E3: The tool manifest rendered for system prompt is byte-identical across
   successive calls with the same tool registry (prompt-cache-stable).
7. E4 (if enabled): System prompt grows by <50% when user switches from
   a git-only session to a debug-only session (proves lazy loading works).

**Test coverage:** ≥ 20 pytest cases. Plus one benchmark showing tokens/turn
before and after for a 3-tool repeat-investigation loop.

## 4. Feature design

### 4.1 E1 — In-session tool-call memoization

**Where:** `poor_cli/tool_cache.py` (new module), wired into
`poor_cli.tool_dispatcher.dispatch_one`.

**Key structure:**

```python
@dataclass
class CacheKey:
    tool: str
    args_hash: str          # sha256 of canonical JSON of args
    session_id: str         # scope to session; never cross-session

@dataclass
class CacheEntry:
    result: ToolResult
    created_at: float
    hits: int = 0

class ToolCache:
    def __init__(self, *, default_ttl_s: float = 60.0, max_entries: int = 512) -> None: ...
    def get(self, key: CacheKey, *, ttl_s: float) -> Optional[CacheEntry]: ...
    def put(self, key: CacheKey, result: ToolResult) -> None: ...
    def invalidate_tool(self, tool: str) -> None: ...  # e.g. after git.commit, wipe git.status cache
    def snapshot(self) -> dict: ...  # for meta.health drill
```

**Per-tool TTL/cacheability:**

Add two fields to `ToolSpec`:
- `cacheable: bool = False` — default OFF; must opt-in
- `cache_ttl_s: float = 60.0`

Mark the safe tools:
- `git.status`, `git.diff`, `git.log`, `git.branch.list` → `cacheable=True, ttl=30s`
- `fs.browse`, `fs.glob` → `cacheable=True, ttl=30s`
- `review.changes` → `cacheable=True, ttl=15s`
- `watch.directives.list` → `cacheable=True, ttl=15s`
- `meta.list_tools`, `meta.describe_tool` → `cacheable=True, ttl=300s`
  (tools don't change mid-session)
- All exclusive tools (commit, push, run, etc.) → `cacheable=False` (forced)

**Invalidation hooks:**

Certain tools invalidate others when they succeed. Declaration:

```python
ToolSpec(..., invalidates=["git.status", "git.diff", "git.log", "hunks.list"])
```

Applied to: `git.commit`, `git.stage`, `git.unstage`, `hunks.stage`, `hunks.reset`.
After a successful dispatch of an `invalidates` tool, purge the cache entries
for the listed tools in this session.

**Args hashing:** `json.dumps(args, sort_keys=True, default=str).encode()` → sha256.
Functions as an arg canonicalizer; `default=str` handles uncommon types gracefully.

**Cache miss emits a normal CallRecord. Cache hit emits a CallRecord with
`metadata.cache_hit = True` and `wall_time_ms ≈ 1` so `meta.call_history`
reflects reality.**

### 4.2 E2 — Result truncation + `tool_blob.get`

**Where:** post-processor inside `tool_dispatcher._dispatch_once`.

**Algorithm:**

1. After handler returns, render the `ToolResult.content` to text for a token
   estimate (use `poor_cli.token_counter` or a fallback 4-chars-per-token
   heuristic).
2. If estimate > `max_result_tokens` (default 8000, per-tool override via
   `ToolSpec.max_result_tokens`):
   a. Compute `keep_head = max_result_tokens // 3`, `keep_tail = max_result_tokens // 3`.
      (Middle-out truncation preserves most useful signal.)
   b. Stash full content under a generated `result_id` in a
      `SessionBlobStore` keyed by session id.
   c. Replace content with `[head] … [TextBlock "tool result truncated
      (X original tokens → Y kept); fetch full with tool_blob.get({result_id}
      = "<id>") "] … [tail]`.
   d. Set `metadata.truncated = True`, `metadata.original_token_estimate`,
      `metadata.result_id`.
3. Ship result to the provider.

**New tool:** `tool_blob.get(result_id: str) -> ToolResult` — reads from the
blob store, returns as-is (no re-truncation; if the agent asked for it, it
accepts the token cost).

**Blob store:**

```python
class SessionBlobStore:
    def __init__(self, *, cap_bytes: int = 4 * 1024 * 1024) -> None: ...  # 4MB session cap
    def put(self, content: List[ContentBlock]) -> str: ...  # returns result_id
    def get(self, result_id: str) -> Optional[List[ContentBlock]]: ...
```

Ring-buffered by total size; oldest blobs evict if cap exceeded. Session-scoped.

### 4.3 E3 — Manifest stability for prompt cache

**Where:** `poor_cli/tool_prompt.py::manifest_markdown` already sorts
deterministically. This proposal adds three enforcement tests:

1. **Stable ordering test:** Call `manifest_markdown()` twice; bytes must match.
2. **Insertion-order independence test:** Register 5 tools in order A,B,C,D,E;
   compute manifest. Clear registry; register in reverse order; compute again.
   Must match.
3. **Prefix stability test:** After registering a new tool, the existing
   portion of the manifest (by domain) is unchanged modulo the new tool's
   insertion point.

**Adjust system-prompt builder** (`core_agent_loop.build_system_prompt` or
equivalent — grep for where the system prompt is assembled):

- Put **tool manifest immediately after the base system instructions**, before
  any user-variable context (repo state, file contents, etc.).
- Put any user-variable context **last**.
- This maximizes Anthropic's ephemeral-cache hit rate (cache_control at the
  boundary between stable-prefix and variable-suffix).

### 4.4 E4 — Lazy tool advertisement (opt-in)

Default OFF. When `tools.lazy_manifest = true`:

**Initial manifest** (what goes into system prompt):
- One short paragraph per domain listing what the domain does.
- A prompt to the agent: "If you need a specific tool, call
  `meta.list_tools({domain: 'git'})` to see schemas."

**Example**:
```
### Tool domains available

- git.* — inspect / modify the repository (9 tools)
- hunks.* — per-file hunk operations (4 tools)
- debug.* — drive nvim-dap (6 tools)
- diagnostics.* — emit/pull LSP-style diagnostics (3 tools)
- fs.* — filesystem browse & glob (2 tools)
- task.* — run repo tasks (5 tools)
- deploy.* — deployment target orchestration (5 tools)
- watch.* — @poor-cli directive inbox (3 tools)
- review.* — review helpers: PR, diff, lint (3 tools)
- meta.* — self-discovery (5 tools)

Use meta.list_tools({domain: "<name>"}) to see schemas.
```

**Token math:** The full manifest is ~3k tokens. The domain summary is ~200
tokens. When enabled, first-turn system prompt shrinks by ~2.8k tokens. After
the agent calls `meta.list_tools({domain: "git"})` once, it has git.* schemas
for the session (cacheable).

**Gotcha:** if the user sets a session as heavy-tool-use (e.g. agent-driven
refactor), `lazy_manifest = false` is better (the full manifest up front
avoids per-turn round-trips to meta.list_tools).

Default remains **off** (full manifest) until real telemetry shows otherwise.

## 5. Files expected to be touched

```
poor_cli/tool_cache.py                 NEW (~180 LOC)
poor_cli/tool_blob_store.py            NEW (~80 LOC)
poor_cli/tool_dispatcher.py            MOD (~60 LOC: cache integration,
                                            truncation pass, invalidation)
poor_cli/tools/_registry.py            MOD (~15 LOC: cacheable, cache_ttl_s,
                                            invalidates, max_result_tokens fields)
poor_cli/tools/git.py                  MOD (~10 LOC: opt-in cacheable + invalidates)
poor_cli/tools/fs.py                   MOD (~5 LOC: cacheable=True)
poor_cli/tools/review.py               MOD (~5 LOC: cacheable=True)
poor_cli/tools/hunks.py                MOD (~10 LOC: invalidates on stage/reset)
poor_cli/tools/meta.py                 MOD (~5 LOC: meta.list_tools cacheable=True)
poor_cli/tool_prompt.py                MOD (~10 LOC: harden sort order)
poor_cli/core_agent_loop.py            MOD (~20 LOC: reorder system prompt sections)
poor_cli/config.py                     MOD (~10 LOC: new feature flags)
tests/test_tool_cache.py               NEW (~200 LOC, ~10 cases)
tests/test_tool_blob_store.py          NEW (~80 LOC, ~5 cases)
tests/test_tool_truncation.py          NEW (~150 LOC, ~5 cases)
tests/test_manifest_stability.py       NEW (~60 LOC, ~3 cases)
tests/bench/tool_frugality.py          NEW (baseline + target numbers)
```

## 6. Test specification

### E1 memoization

```python
def test_cache_hit_skips_handler():
    # Two calls with same args → handler invoked once.
    # CallRecord #2 has metadata.cache_hit = True.

def test_different_args_miss():
    # Same tool, different args → two handler invocations.

def test_exclusive_tool_bypasses_cache():
    # git.commit called twice with same message → two handler invocations.

def test_transient_error_not_cached():
    # Handler raises TransientError on first call; second call tries again.

def test_ttl_expiry():
    # Patch time.monotonic; verify cache miss after ttl_s elapses.

def test_invalidates_clears_dependent_tools():
    # git.status cached → git.commit invokes invalidation → git.status miss.

def test_lru_eviction():
    # Fill cache with max_entries+1 distinct keys; oldest evicts.

def test_cacheable_false_never_caches():
    # Default behavior for new tools.

def test_args_canonicalization():
    # {"a":1,"b":2} and {"b":2,"a":1} hit the same cache key.
```

### E2 truncation + blob

```python
def test_small_result_not_truncated():
    # Handler returns 100 tokens → passes through.

def test_large_result_truncated():
    # Handler returns 20000 tokens → truncated; metadata.truncated=True;
    # metadata.result_id set.

def test_tool_blob_get_returns_full():
    # After truncation, tool_blob.get(result_id) returns the original content.

def test_tool_blob_get_unknown_id():
    # Returns is_error with unknown_blob metadata.

def test_blob_store_ring_evicts_oldest():
    # Fill past cap_bytes; oldest blob no longer retrievable.
```

### E3 manifest stability

```python
def test_manifest_is_byte_stable():
    # Two calls produce identical bytes.

def test_manifest_is_registration_order_independent():
    # Registering tools in different orders produces the same manifest.

def test_new_tool_does_not_shift_earlier_sections():
    # Insert a new domain; git.* section remains byte-identical at the
    # character level up to the git block end.
```

### E4 lazy manifest (opt-in)

```python
def test_lazy_manifest_flag_shrinks_prompt():
    # system_prompt() with lazy_manifest=True has <=500 chars of tool info;
    # lazy_manifest=False has the full block.

def test_lazy_manifest_preserves_domain_names():
    # Agent sees every domain prefix, just not every tool schema.
```

### Benchmark

```python
# tests/bench/tool_frugality.py — not a pytest case, a standalone script.
# Simulates a 5-turn "agent investigates repo" scenario calling:
#   turn 1: git.status, git.diff, review.changes
#   turn 2: git.status (cached), fs.glob
#   turn 3: git.status (cached), fs.browse
#   turn 4: git.commit (invalidates), git.status (miss)
#   turn 5: git.status (cached again)
#
# Records:
#   - handler invocations (expected: 3 git.status executions, NOT 5)
#   - wall time saved
#   - token budget saved (synthetic: assume each handler output ~400 tokens)
```

## 7. Known risks

| Risk | Mitigation |
|---|---|
| Over-aggressive caching returns stale results | Conservative defaults (TTL≤30s for git.*, invalidation hooks on mutations). User can tune `tools.memoize = false` to disable entirely. |
| Blob store memory pressure on long sessions | Hard cap at 4MB; ring-buffer eviction; per-session (not per-process) isolation. |
| Truncation loses critical information | Middle-out keeps head+tail; agent gets clear signal (metadata.truncated=True) so it can fetch full via tool_blob.get if needed. |
| Prompt-cache invalidation from unexpected source | Only ~20 LOC added; tests cover byte-stability invariants. |
| Lazy manifest hurts agents that don't know meta.* exists | Keep lazy_manifest default OFF. The E4 change is optional; we measure before enabling. |

## 8. Done when

- [ ] All 4 features implemented behind the listed flags
- [ ] 23+ new pytest cases green
- [ ] Benchmark script runs; comparison written to
      `docs/perf/v6.4-frugality.md` (before/after token counts)
- [ ] Default config has memoization on, truncation on, manifest stability on,
      lazy manifest off
- [ ] No regression in existing 110+ Phase B/C tests

## 9. Out of scope

- Persistent caches (PROPOSAL-G)
- LLM-based summarization (PROPOSAL-G; flagged as anti-pattern)
- Semantic tool routing via embeddings (PROPOSAL-G; flagged as low-priority)
- Rewriting context_optimizer (separate concern)
- Any changes to provider-specific prompt caching mechanics
  (Anthropic caching is already wired; we just don't break it)
