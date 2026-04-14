# Phase 6: Memory Architecture — Fundamental Context Redesign

**Priority:** Medium — 🟠 Hard solutions requiring architectural changes to how poor-cli manages state across turns.
**Estimated agents:** 2 (parallel)
**Dependencies:** Phase 3 (smart loading/pruning) should be complete — these solutions build on the pruning and skill-loading infrastructure. Phase 5C (failure amnesia) is a prerequisite for differential updates.
**Philosophy:** Stop re-reading the world every turn. The agent should maintain working memory and receive only deltas. This is the hardest category that doesn't require open-weights models — pure engineering with no ML training.

---

## Agent 6A: Differential Context Updates (MemGPT-Style)

**Pain points addressed:** #1 (context window accumulation — the fundamental problem), #3 (codebase reading inefficiency)
**Solution reference:** Solution #18 from SOLUTIONS.md
**Expected savings:** Potentially 60-80% reduction in per-turn input tokens for long sessions

### What to build

Instead of re-sending the full conversation history + full file contents every turn, send only what changed since the last turn. The agent maintains a "working memory" snapshot, and each turn receives a diff against that snapshot.

### Implementation details

1. **Working memory model** — define what the agent "knows" at any point:
   ```python
   @dataclass
   class WorkingMemory:
       session_summary: str           # compressed summary of session so far
       active_files: dict[str, str]   # filepath → content (files currently in context)
       active_file_versions: dict[str, str]  # filepath → git hash / content hash
       key_decisions: list[str]       # important decisions made this session
       pending_tasks: list[str]       # what the agent is working on
       tool_state: dict               # state from recent tool calls
       last_turn_id: int              # for delta computation
   ```

2. **Delta computation** — between turns, compute what changed:
   ```python
   @dataclass
   class ContextDelta:
       new_user_message: str
       files_changed: dict[str, str]      # filepath → unified diff
       files_added: dict[str, str]        # filepath → content
       files_removed: list[str]           # filepaths no longer relevant
       new_tool_results: list[ToolResult] # results from last turn's tool calls
       memory_updates: list[str]          # any working memory updates
   
   def compute_delta(prev_memory: WorkingMemory, current_state: SessionState) -> ContextDelta:
       delta = ContextDelta()
       # diff active files
       for path, content in current_state.active_files.items():
           if path not in prev_memory.active_files:
               delta.files_added[path] = content
           elif content != prev_memory.active_files[path]:
               delta.files_changed[path] = unified_diff(prev_memory.active_files[path], content)
       for path in prev_memory.active_files:
           if path not in current_state.active_files:
               delta.files_removed.append(path)
       return delta
   ```

3. **Prompt construction with deltas** — instead of full history, send:
   ```
   [Working Memory Summary]
   You are mid-session. Here's what you know:
   - Session goal: {session_summary}
   - Key decisions: {key_decisions}
   - Active files: {file list with sizes}
   
   [Since Last Turn]
   - User said: {new_user_message}
   - Files changed: {diffs}
   - Tool results: {new_tool_results}
   
   [Current File Contents]
   {only files referenced in current turn or recently changed}
   ```

4. **Memory persistence** — working memory survives across turns but gets compacted periodically:
   - After every N turns (configurable, default 10), re-summarize the session
   - Working memory stored in `poor-cli/session_store.py`

5. **Hybrid mode** — for the first few turns (before enough context accumulates), use traditional full-history mode. Switch to delta mode once conversation exceeds a threshold (e.g., 5 turns or 50% of context window used).

6. **Recovery from confusion** — if the model produces a response indicating it lost context ("I don't have access to that file", "what file are you referring to?"), fall back to full-history mode for one turn to re-anchor, then resume deltas.

7. **Integration with existing compaction** — delta mode and `/compact` work together:
   - `/compact` resets the working memory to a fresh summary
   - Delta computation restarts from the compacted state

### Files to create/modify
- `poor-cli/working_memory.py` (new, ~300 lines — memory model + delta computation)
- `poor-cli/context_providers.py` (major refactor — delta-based prompt construction)
- `poor-cli/session_store.py` (persist working memory)
- `poor-cli/context_optimizer.py` (integrate delta mode with compaction)

### Acceptance criteria
- [ ] Working memory model tracks files, decisions, and session state
- [ ] Delta computation produces minimal diffs between turns
- [ ] Prompt constructed from working memory + delta (not full history)
- [ ] Hybrid mode: full history for first N turns, then switch to deltas
- [ ] Recovery mechanism when model indicates lost context
- [ ] Working memory persists across turns, compacted periodically
- [ ] Measured: 50%+ reduction in per-turn input tokens for 20+ turn sessions
- [ ] Test: simulate 20-turn session, compare token usage with and without delta mode

### References
- [Letta (MemGPT)](https://github.com/letta-ai/letta) — OS-style memory for agents
- [MemGPT paper](https://arxiv.org/abs/2310.08560)

---

## Agent 6B: Position-Independent KV Cache Reuse

**Pain points addressed:** #15 (non-prefix cache misses — full re-prefill when same file appears at different position)
**Solution reference:** Solution #15 from SOLUTIONS.md
**Expected savings:** 2.2–3.3× TTFT reduction; enables true codebase-level caching

### What to build

This is an **infrastructure-level optimization** that only applies when poor-cli is used with self-hosted inference (Ollama, vLLM, SGLang). It pre-computes KV caches for repository files and reuses them regardless of position in the prompt.

### Important caveat

This solution **only works with local/self-hosted inference**. It cannot be used with closed API providers (Anthropic, OpenAI, Gemini). Implementation should be gated behind Ollama/local provider detection.

### Implementation details

1. **Pre-compute file KV caches** — for each file in the repo, compute and store its KV cache:
   ```python
   class KVCacheStore:
       def __init__(self, cache_dir: Path):
           self.cache_dir = cache_dir
       
       async def precompute(self, filepath: Path, model: str):
           """Pre-compute KV cache for a file using the local model."""
           content = filepath.read_text()
           # use vLLM/SGLang API to compute KV cache
           kv_cache = await self.inference_engine.compute_kv(content, model)
           cache_key = self._cache_key(filepath, content)
           self.store(cache_key, kv_cache)
       
       def _cache_key(self, filepath: Path, content: str) -> str:
           return hashlib.sha256(f"{filepath}:{content}".encode()).hexdigest()
   ```

2. **Cache invalidation** — re-compute when files change:
   - Watch for git changes (same mechanism as repo map cache)
   - Content-hash-based: if hash matches, cache is valid regardless of path

3. **Cache assembly** — when constructing a prompt, assemble pre-computed KV caches:
   ```python
   async def assemble_cached_prompt(files: list[Path], query: str):
       cached_segments = []
       for f in files:
           kv = cache_store.get(f)
           if kv:
               cached_segments.append(kv)
           else:
               # fall back to text for uncached files
               cached_segments.append(f.read_text())
       # append query (always fresh)
       return combine_kv_caches(cached_segments, query)
   ```

4. **LMCache integration** — [LMCache](https://github.com/LMCache/LMCache) is the most mature open-source implementation of this pattern. Integrate with it rather than building from scratch:
   - LMCache works with vLLM
   - Supports prefix-independent cache reuse
   - Handles cache combination automatically

5. **Ollama integration** — investigate whether Ollama exposes KV cache APIs:
   - Current Ollama API may not support this directly
   - May require running vLLM with the same models as an alternative backend
   - Document the infrastructure requirements clearly

6. **Gating** — this feature should be:
   - Off by default
   - Only available when using local inference (Ollama, vLLM)
   - Configurable via `.poor-cli/config.yaml`:
     ```yaml
     kv_cache:
       enabled: true
       backend: "lmcache"  # or "vllm"
       cache_dir: ".poor-cli/kv_cache/"
       precompute_on_startup: true
     ```

### Files to create/modify
- `poor-cli/kv_cache_store.py` (new, ~250 lines)
- `poor-cli/providers/ollama_provider.py` (integrate KV cache for local inference)
- `.poor-cli/config.yaml` (add kv_cache config section)

### Acceptance criteria
- [ ] KV cache pre-computation works with vLLM/LMCache
- [ ] Cache stored on disk, keyed by content hash
- [ ] Cache invalidated on file changes
- [ ] Cache assembly combines pre-computed segments + fresh query
- [ ] Feature gated behind local inference detection
- [ ] Documentation: clear infra requirements (vLLM, LMCache, disk space)
- [ ] Test: pre-compute cache for 10 files, verify reuse on second query
- [ ] Measured: TTFT reduction on cache-hit vs cold start

### References
- [CacheBlend paper (EuroSys 2025)](https://arxiv.org/abs/2405.16444)
- [LMCache GitHub](https://github.com/LMCache/LMCache)
- [EPIC paper](https://arxiv.org/abs/2410.15332)
- [Prompt Cache paper](https://arxiv.org/abs/2311.04934)

### Research tasks (if implementing from scratch)
- [ ] Benchmark LMCache with vLLM on poor-cli's typical workloads
- [ ] Measure cache storage requirements per file (estimate: 10-100MB per file depending on model)
- [ ] Test cache validity across model versions
- [ ] Investigate Ollama's internal KV cache management for potential API contributions
