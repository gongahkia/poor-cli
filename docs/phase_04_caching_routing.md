# Phase 4: Caching & Routing — Avoid Redundant Work

**Priority:** Medium-High — 🟡 Moderate solutions targeting cost optimization and duplicate work.
**Estimated agents:** 3 (parallel)
**Dependencies:** Phase 2C (prompt caching) should be done first to avoid conflicting optimizations. Phase 1–3 recommended but not blocking.
**Philosophy:** Don't pay for the same answer twice. Don't use a $15/M-token model when a $0.15/M-token model gives the same answer. These solutions are about routing intelligence — putting the right model on the right task, and caching when possible.

---

## Agent 4A: Semantic Response Caching

**Pain points addressed:** #13 (duplicate query re-inference — full re-cost per duplicate)
**Solution reference:** Solution #6 from SOLUTIONS.md
**Expected savings:** Up to 68.8% reduction in API calls (GPT Semantic Cache benchmark)

### What to build

A local semantic cache that intercepts agent queries, computes embedding similarity against past queries, and returns cached responses for near-duplicate queries without making an API call.

### Implementation details

1. **Audit existing caching** — read `poor_cli/file_cache.py` and `poor_cli/embeddings.py`:
   - Does any response-level caching exist?
   - What embedding model/infra is available?

2. **Cache architecture**:
   ```
   Query → Embed → Search cache (cosine similarity) → Hit? Return cached → Miss? Call API → Store response + embedding
   ```

3. **Embedding model** — use a small, fast, local embedding model:
   - Option A: `sentence-transformers/all-MiniLM-L6-v2` (~80MB, runs locally)
   - Option B: Use the existing embeddings infrastructure in `poor_cli/embeddings.py`
   - Option C: If Ollama is available, use `nomic-embed-text` or `mxbai-embed-large`
   - Requirement: must work offline, no API calls for caching itself

4. **Cache storage** — SQLite-based local cache:
   ```python
   class SemanticCache:
       def __init__(self, db_path: Path, similarity_threshold: float = 0.92):
           self.db = sqlite3.connect(db_path)
           self.threshold = similarity_threshold
       
       async def get(self, query: str, context_hash: str) -> CacheResult | None:
           embedding = await self.embed(query)
           # search for similar queries with matching context hash
           results = self.search(embedding, context_hash)
           if results and results[0].similarity >= self.threshold:
               return results[0]
           return None
       
       async def put(self, query: str, context_hash: str, response: str, embedding: list[float]):
           self.store(query, context_hash, response, embedding)
   ```

5. **Context-aware cache keys** — a query's cache validity depends on context:
   - Same question about different files → different cache entry
   - Hash the active file set + pinned context as part of the cache key
   - This prevents stale cache hits after file changes

6. **Cache invalidation**:
   - Invalidate entries when referenced files change (git status check)
   - TTL-based expiry (default: 24 hours)
   - Manual invalidation via command

7. **Integration point** — intercept at the provider layer, before the API call:
   ```python
   async def complete(self, messages, tools):
       cache_result = await self.cache.get(last_user_message, context_hash)
       if cache_result:
           self.log_cache_hit(cache_result)
           return cache_result.response
       response = await self._api_call(messages, tools)
       await self.cache.put(last_user_message, context_hash, response, embedding)
       return response
   ```

8. **Cache dashboard** — show cache hit rates and savings in `/cost` and `/savings`.

### Files to create/modify
- `poor_cli/semantic_cache.py` (new, ~300 lines)
- `poor_cli/embeddings.py` (enhance if needed for local embeddings)
- `poor_cli/providers/base.py` (add cache check before API call)
- Provider implementations (integrate cache)
- `poor_cli/cost.py` (track cache savings)

### Acceptance criteria
- [ ] Semantic similarity search works with configurable threshold
- [ ] Context-aware cache keys prevent stale hits
- [ ] Cache hit avoids API call entirely
- [ ] Cache invalidated on file changes
- [ ] Works offline (local embedding model)
- [ ] Cache stats visible in `/cost` and `/savings`
- [ ] Test: ask same question twice, second call returns cached response
- [ ] Test: ask same question after file change, cache miss occurs

### References
- [GPTCache](https://github.com/zilliztech/GPTCache) — production-ready, 6K+ stars
- [GPT Semantic Cache paper](https://arxiv.org/abs/2411.05276)
- [MeanCache paper](https://arxiv.org/abs/2403.02694) — federated per-user caches

---

## Agent 4B: LLM Cascading / Model Routing

**Pain points addressed:** Wrong-sized model for task, overall cost
**Solution reference:** Solution #9 from SOLUTIONS.md
**Expected savings:** Up to 98% cost reduction (FrugalGPT), 2× savings (RouteLLM) without quality loss

### What to build

A routing engine that sends each query to the cheapest model capable of answering it correctly, cascading to more expensive models only when needed. poor-cli already has multi-provider support — this leverages that.

### Implementation details

1. **Audit existing architect mode** — read `poor_cli/architect_mode.py`:
   - Does it already route between models?
   - How does it decide which model to use?

2. **Task complexity classifier** — classify each user prompt:
   ```python
   class TaskComplexity(Enum):
       TRIVIAL = "trivial"    # typo fix, simple rename, "what does X do"
       SIMPLE = "simple"      # single-file edit, straightforward bug fix
       MODERATE = "moderate"  # multi-file change, needs reasoning
       COMPLEX = "complex"    # architectural decision, multi-step agent loop
   
   def classify_complexity(prompt: str, context: SessionContext) -> TaskComplexity:
       # heuristic features:
       # - prompt length
       # - number of files referenced
       # - presence of planning keywords ("redesign", "refactor", "architect")
       # - tool calls likely needed (more tools = more complex)
       # - conversation depth (follow-ups in deep sessions = more complex)
       ...
   ```

3. **Model routing table** — map complexity to model:
   ```python
   ROUTING_TABLE = {
       "gemini": {
           TaskComplexity.TRIVIAL: "gemini-2.5-flash-lite",
           TaskComplexity.SIMPLE: "gemini-2.5-flash",
           TaskComplexity.MODERATE: "gemini-2.5-flash",
           TaskComplexity.COMPLEX: "gemini-2.5-pro",
       },
       "anthropic": {
           TaskComplexity.TRIVIAL: "claude-3-5-haiku-20241022",
           TaskComplexity.SIMPLE: "claude-3-5-haiku-20241022",
           TaskComplexity.MODERATE: "claude-sonnet-4-20250514",
           TaskComplexity.COMPLEX: "claude-sonnet-4-20250514",
       },
       # ... etc for openai, openrouter, ollama
   }
   ```

4. **Cascade with confidence check** — for ambiguous complexity:
   - Start with the cheaper model
   - If the response includes low-confidence markers (hedging, "I'm not sure", incomplete tool calls), escalate to the next tier
   - Log the escalation for cost tracking

5. **Integration with economy modes**:
   - `/broke` (frugal): aggressive routing to cheapest models, cascade only on failure
   - `balanced`: standard routing table
   - `/my-treat` (quality): always use top-tier model, no cascading

6. **User override** — if the user explicitly set a model via `/switch`, respect that. Routing only applies when model is set to "auto" or not explicitly set.

7. **Routing analytics** — track which model answered each query and whether escalation occurred. Surface in `/cost`.

### Files to create/modify
- `poor_cli/model_router.py` (new, ~250 lines)
- `poor_cli/architect_mode.py` (integrate routing if overlap)
- `poor_cli/profiles.py` (tie routing to economy presets)
- `poor_cli/providers/provider_factory.py` (routing-aware model selection)
- `poor_cli/cost.py` (track routing savings)

### Acceptance criteria
- [ ] Task complexity classifier works on heuristic features
- [ ] Routing table maps complexity to models per provider
- [ ] Cascade on low-confidence response works
- [ ] Economy mode influences routing aggressiveness
- [ ] User explicit model choice overrides routing
- [ ] Routing decisions logged and visible in `/cost`
- [ ] Test: "fix typo" routes to cheapest model, "redesign auth system" routes to expensive model

### References
- [FrugalGPT paper](https://arxiv.org/abs/2305.05176)
- [RouteLLM paper](https://arxiv.org/abs/2406.18665)
- [RouteLLM GitHub](https://github.com/lm-sys/RouteLLM)

---

## Agent 4C: Grammar-Constrained Output Integration

**Pain points addressed:** #14 (CoT verbosity), #18 (markdown formatting overhead), malformed output retry loops
**Solution reference:** Solution #7 from SOLUTIONS.md
**Expected savings:** 30–50% shorter outputs, eliminates malformed-output retries

### What to build

For structured outputs (tool call arguments, JSON responses, edit specifications), use grammar constraints to ensure the model can only emit valid tokens. This eliminates retry loops from malformed output and produces more compact responses.

### Implementation details

1. **Identify structured output points** — where does poor-cli expect structured output from the model?
   - Tool call argument JSON
   - Edit format blocks (search/replace, diff)
   - Plan mode structured output
   - JSON/YAML editing

2. **Provider-specific integration**:
   - **Anthropic**: use `response_format` with JSON schema, or tool definitions with strict schemas
   - **OpenAI**: use `response_format: { type: "json_schema", ... }` for structured outputs
   - **Gemini**: use `response_schema` parameter
   - **Ollama** (local models): use grammar-constrained decoding if model supports it (via `format: "json"`)

3. **Structured response schemas** — define JSON schemas for common structured outputs:
   ```python
   EDIT_RESPONSE_SCHEMA = {
       "type": "object",
       "properties": {
           "edits": {
               "type": "array",
               "items": {
                   "type": "object",
                   "properties": {
                       "file": {"type": "string"},
                       "search": {"type": "string"},
                       "replace": {"type": "string"}
                   },
                   "required": ["file", "search", "replace"]
               }
           }
       }
   }
   ```

4. **Conditional application** — only apply grammar constraints for responses that should be structured. Free-form explanations should not be constrained.

5. **Fallback** — if constrained decoding fails or the provider doesn't support it, fall back to normal generation + post-hoc validation.

### Files to create/modify
- `poor_cli/structured_output.py` (new, ~150 lines — schema definitions + provider adapters)
- `poor_cli/providers/base.py` (add structured output support to provider interface)
- Provider implementations (add response_format support)
- `poor_cli/edit_formats.py` (use structured output for edit responses)

### Acceptance criteria
- [ ] JSON schema defined for tool call responses and edit blocks
- [ ] Anthropic, OpenAI, Gemini providers use native structured output
- [ ] Ollama uses `format: "json"` where supported
- [ ] Retry loops eliminated for malformed structured output
- [ ] Free-form responses not constrained
- [ ] Fallback to unstructured generation on provider error
- [ ] Test: 10 edit requests produce valid structured output without retries

### References
- [Outlines](https://github.com/dottxt-ai/outlines)
- [XGrammar](https://github.com/mlc-ai/xgrammar)
- [OpenAI structured outputs](https://platform.openai.com/docs/guides/structured-outputs)
- [Anthropic tool use](https://docs.anthropic.com/en/docs/build-with-claude/tool-use)
