# Implementation Waves — Token Optimization for poor-cli

Master orchestration document for parallel agent execution across 8 phases.
Total agents across all phases: **24**. Maximum parallel agents in a single phase: **4**.

Each phase contains copy-paste-ready prompts per agent. Prompts reference the corresponding `phase_XX_*.md` document for full implementation details.

---

## Reading Guide

- **Phases are sequential** — complete Phase N before starting Phase N+1 (soft dependency; some phases can overlap)
- **Agents within a phase are parallel** — spin up all agents in a phase simultaneously
- **Prompts are customizable** — sections marked `[CUSTOMIZE]` should be adjusted to your environment
- **Each prompt references a phase doc** — the agent should read that doc first for full context

---

## Phase Overview

| Phase | Name | Agents | Pain Points Targeted | Feasibility | Expected Total Savings |
|-------|------|--------|---------------------|-------------|----------------------|
| 1 | Quick Wins | 4 | #1, #2, #3, #9, #10, #14, #18 | 🟢 Easy | 30-50% on targeted areas |
| 2 | Context Intelligence | 3 | #2, #3, #4, #16 | 🟢 Easy | 50-90% on input tokens |
| 3 | Smart Loading & Pruning | 3 | #1, #4, #6 | 🟡 Moderate | 50-80% on system prompt + history |
| 4 | Caching & Routing | 3 | #13, #14, #18, cost | 🟡 Moderate | 50-98% on duplicates + routing |
| 5 | Advanced Compression | 3 | #3, #5, #7 | 🟡–🟠 Moderate-Hard | 30-80% on compression targets |
| 6 | Memory Architecture | 2 | #1, #3, #15 | 🟠 Hard | 60-80% on long sessions |
| 7 | Adaptive Optimization | 2 | Cost, #8, inference speed | 🟠 Hard | 30-50% adaptive improvement |
| 8 | Research Frontier | 4 | #11, #12, #14, #3 | 🔴 Research | Potentially transformative |

---

## Phase 1: Quick Wins — Drop-in Integrations

**Agents: 4 (all parallel)**
**Reference document:** `docs/phase_01_quick_wins.md`
**Estimated time per agent:** 1-3 days
**Prerequisites:** None

### Agent 1A: RTK CLI Output Proxy Integration

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing RTK (Rust Token Killer) integration for poor-cli, a Neovim-focused
coding agent. Your task is to add a thin middleware that wraps shell tool calls with the
`rtk` binary for token-compact output.

FIRST: Read docs/phase_01_quick_wins.md, specifically the "Agent 1A" section. It contains
exact implementation details, files to modify, and acceptance criteria.

CONTEXT:
- poor-cli is a Python backend + Lua Neovim plugin communicating via JSON-RPC
- Shell tool execution lives in poor-cli/enhanced_tools.py
- Config system is in poor-cli/repo_config.py and nvim-poor-cli/lua/poor-cli/config.lua
- RTK is an external Rust binary (brew install rtk) that filters shell output

YOUR DELIVERABLES:
1. Create poor-cli/rtk_integration.py — RTK detection, command wrapping, tee-mode fallback
2. Modify poor-cli/enhanced_tools.py — integrate RTK wrapper in bash tool execution
3. Add rtk config fields to poor-cli/repo_config.py
4. Add rtk_enabled default to nvim-poor-cli/lua/poor-cli/config.lua
5. Write unit tests in tests/test_rtk_integration.py

CONSTRAINTS:
- Do NOT refactor outside scope. Touch only the files listed above.
- RTK is optional — everything must work identically when rtk is not installed
- Follow existing code style: inline comments only, lowercase, minimize whitespace
- [CUSTOMIZE: add any repo-specific constraints here]

Read the phase doc first, then implement.
```

### Agent 1B: Enhanced Diff-Based Editing

```
[AGENT PROMPT — copy/paste to your coding agent]

You are enhancing poor-cli's edit format system to minimize token usage on file edits.
The current implementation may use full-file rewrites where a compact diff would suffice.

FIRST: Read docs/phase_01_quick_wins.md, specifically the "Agent 1B" section for full
implementation details and acceptance criteria.

CONTEXT:
- poor-cli's edit format logic lives in poor-cli/edit_formats.py
- Provider base class is poor-cli/providers/base.py
- The tool that applies edits is in poor-cli/enhanced_tools.py (edit_file tool)
- Multiple providers (Gemini, OpenAI, Anthropic, OpenRouter, Ollama) need format support

YOUR DELIVERABLES:
1. Audit poor-cli/edit_formats.py — document current format and identify waste
2. Implement search/replace block format (Aider-style)
3. Implement unified diff format as alternative
4. Add format selection heuristic based on edit size
5. Add preferred_edit_format to provider interface
6. Write tests in tests/test_edit_formats.py

CONSTRAINTS:
- Stick to edit_formats.py and provider files only
- Must work across all 5 providers
- Validation: edited files must be syntactically valid after applying diffs
- [CUSTOMIZE: specify which providers you primarily use]

Read the phase doc first, then implement.
```

### Agent 1C: Enhanced Context Compaction

```
[AGENT PROMPT — copy/paste to your coding agent]

You are enhancing poor-cli's /compact command and auto-compaction system to be smarter
about what gets preserved vs summarized vs dropped when context grows too large.

FIRST: Read docs/phase_01_quick_wins.md, specifically the "Agent 1C" section for full
implementation details and acceptance criteria.

CONTEXT:
- Context optimization lives in poor-cli/context_optimizer.py
- Context contracts in poor-cli/context_contract.py
- Context providers in poor-cli/context_providers.py
- Economy modes (/broke, /my-treat) defined in poor-cli/profiles.py
- Neovim lualine integration in nvim-poor-cli/lua/poor-cli/lualine.lua

YOUR DELIVERABLES:
1. Audit context_optimizer.py — document current compaction strategy
2. Implement tiered compaction (Tier 1: preserve, Tier 2: summarize, Tier 3: drop)
3. Add auto-compaction trigger at configurable threshold (default 70%)
4. Tie compaction aggressiveness to economy mode
5. Add compaction status to lualine
6. Write tests in tests/test_context_compaction.py

CONSTRAINTS:
- Current /compact must still work — enhance, don't replace
- Economy mode integration must respect existing mode system
- Auto-compaction must be non-blocking (async)
- [CUSTOMIZE: set your preferred auto-compact threshold]

Read the phase doc first, then implement.
```

### Agent 1D: Terse Output Mode

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding a terse output directive to poor-cli's /broke (frugal) economy mode
so the model produces maximally compressed responses when cost savings are prioritized.

FIRST: Read docs/phase_01_quick_wins.md, specifically the "Agent 1D" section for full
implementation details and acceptance criteria.

CONTEXT:
- Economy modes defined in poor-cli/profiles.py
- System prompt construction happens in the core engine (likely core.py or similar)
- /broke and /my-treat commands already exist and toggle economy modes

YOUR DELIVERABLES:
1. Find where the system prompt is assembled (trace from provider call backwards)
2. Add terse output directive injected when economy mode is frugal/broke
3. Map economy presets to output verbosity (frugal=caveman, balanced=normal, quality=comprehensive)
4. Ensure code blocks, error messages, git prose are preserved even in terse mode
5. Spot-check: test 5 different prompts in broke mode, verify shorter output

CONSTRAINTS:
- Smallest-scope change in Phase 1. Should be < 50 lines of code changed.
- Do NOT modify /my-treat or balanced mode behavior
- Do NOT install external skills or dependencies
- [CUSTOMIZE: adjust the terse directive wording to your preferences]

Read the phase doc first, then implement.
```

---

## Phase 2: Context Intelligence — Smarter Input

**Agents: 3 (all parallel)**
**Reference document:** `docs/phase_02_context_intelligence.md`
**Estimated time per agent:** 3-7 days
**Prerequisites:** None (can run in parallel with Phase 1)

### Agent 2A: Tree-Sitter Repo Map

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building an Aider-style repository map for poor-cli using tree-sitter for AST
parsing and PageRank for importance scoring. This gives the model a concise, ranked
overview of the entire codebase without reading full files.

FIRST: Read docs/phase_02_context_intelligence.md, specifically the "Agent 2A" section
for full implementation details and acceptance criteria.

CONTEXT:
- poor-cli already has poor-cli/repo_graph.py — audit it first
- The /workspace-map command should use this enhanced map
- poor-cli/indexer.py handles code indexing — coordinate with this module
- poor-cli/context_providers.py injects context into prompts
- tree-sitter Python bindings: pip install tree-sitter tree-sitter-python tree-sitter-lua etc.

YOUR DELIVERABLES:
1. Audit poor-cli/repo_graph.py — document current capabilities
2. Add tree-sitter parsing for Python, Lua, JS/TS, Rust
3. Build dependency graph from imports/calls
4. Implement PageRank scoring with recency boost
5. Generate token-budgeted map output (default 2000 tokens)
6. Cache map with git-based invalidation
7. Integrate with /workspace-map and context injection
8. Write tests in tests/test_repo_graph.py

CONSTRAINTS:
- tree-sitter is a new dependency — add to pyproject.toml optional dependencies
- Map must respect token budget — truncate from lowest rank upward
- Cache must invalidate on file changes
- [CUSTOMIZE: list the languages most important for your codebase]

Read the phase doc first, then implement.
```

### Agent 2B: Schema-Aware Tool Output Filtering

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building a tool output filtering middleware for poor-cli that reduces bloated
tool/MCP responses to only the fields the agent needs. This is a greenfield implementation
— no standard exists in the ecosystem.

FIRST: Read docs/phase_02_context_intelligence.md, specifically the "Agent 2B" section
for full implementation details and acceptance criteria.

CONTEXT:
- Tool execution lives in poor-cli/enhanced_tools.py
- MCP client in poor-cli/mcp_scaffold.py
- GitHub tools in poor-cli/github_tools.py
- Cost tracking in poor-cli/cost.py

YOUR DELIVERABLES:
1. Create poor-cli/tool_output_filter.py — projection-based filtering + size-based auto-filter
2. Define default projections for built-in tools (gh, git, list_directory)
3. Integrate filter middleware into tool execution pipeline (enhanced_tools.py)
4. Add MCP response filtering in mcp_scaffold.py
5. Support user-configurable projections via .poor-cli/tool_projections.yaml
6. Track tokens saved in cost dashboard
7. Write tests in tests/test_tool_output_filter.py

CONSTRAINTS:
- Filtering is middleware — must not break any existing tool behavior
- Use jmespath or similar for JSONPath field selection
- Size-based auto-filtering: threshold configurable, default 5000 tokens
- Filtered output must include a note about what was trimmed
- [CUSTOMIZE: list the MCP servers you use most]

Read the phase doc first, then implement.
```

### Agent 2C: Prompt Caching Optimization

```
[AGENT PROMPT — copy/paste to your coding agent]

You are optimizing poor-cli's prompt construction to maximize provider-level cache hit
rates. This means ensuring the static prefix (system prompt, tool schemas, repo map) is
deterministic and stable across turns.

FIRST: Read docs/phase_02_context_intelligence.md, specifically the "Agent 2C" section
for full implementation details and acceptance criteria.

CONTEXT:
- Provider implementations in poor-cli/providers/
- Provider base class: poor-cli/providers/base.py
- Context assembly in poor-cli/context_providers.py
- Cost tracking in poor-cli/cost.py / nvim-poor-cli/lua/poor-cli/cost.lua
- Anthropic supports explicit cache_control; OpenAI caches on prefix match automatically

YOUR DELIVERABLES:
1. Trace prompt construction end-to-end (user message → API call)
2. Document current component ordering — identify cache-busting patterns
3. Stabilize prefix ordering: system → tools → repo map → instructions → history → user
4. Add Anthropic cache_control on static prefix components
5. Remove timestamps/random content from cacheable prefix
6. Log cache hit/miss rates from provider response headers
7. Display cache savings in /cost

CONSTRAINTS:
- Must not change the semantic content of prompts — only ordering and cache metadata
- Each provider needs provider-specific cache optimization
- Test by sending 5 identical prompts and verifying cache hits on 2-5
- [CUSTOMIZE: specify your primary provider for testing priority]

Read the phase doc first, then implement.
```

---

## Phase 3: Smart Loading & Pruning

**Agents: 3 (all parallel)**
**Reference document:** `docs/phase_03_smart_loading.md`
**Estimated time per agent:** 5-10 days
**Prerequisites:** Phase 2 recommended (repo map helps skill routing), but not blocking

### Agent 3A: Progressive Skill/Instruction Loading

```
[AGENT PROMPT — copy/paste to your coding agent]

You are refactoring poor-cli's instruction system from a monolithic system prompt into
a progressive skill-loading architecture where only task-relevant instructions are loaded
per request.

FIRST: Read docs/phase_03_smart_loading.md, specifically the "Agent 3A" section for full
implementation details and acceptance criteria.

CONTEXT:
- Instructions currently in poor-cli/instructions.py
- Skills system in poor-cli/skills.py
- System prompt assembled in the core engine
- /instructions command shows active instructions

YOUR DELIVERABLES:
1. Audit poor-cli/instructions.py — measure total instruction payload size
2. Break instructions into ≥8 discrete skill files in poor-cli/skills/ directory
3. Build task classifier (keyword-based + context-based)
4. Implement SkillRegistry for on-demand loading
5. Replace monolithic prompt injection with dynamic skill loading
6. Support user-defined skills in .poor-cli/skills/
7. Update /instructions to show which skills are loaded
8. Write tests in tests/test_skill_loading.py

CONSTRAINTS:
- Core safety/behavior instructions must ALWAYS load (never skip)
- Skill classification can be heuristic — no ML model needed
- Must be backwards-compatible: if classification fails, load all (fallback)
- [CUSTOMIZE: list your most-used task types for classifier tuning]

Read the phase doc first, then implement.
```

### Agent 3B: Lazy Tool Schema Loading

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing lazy/on-demand tool schema loading for poor-cli so that only
relevant tool schemas are injected into each request, instead of the full tool catalog.

FIRST: Read docs/phase_03_smart_loading.md, specifically the "Agent 3B" section for full
implementation details and acceptance criteria.

CONTEXT:
- Tool definitions in poor-cli/command_manifest.py and poor-cli/enhanced_tools.py
- MCP tool schemas loaded in poor-cli/mcp_scaffold.py
- Tools injected into provider requests in the prompt assembly pipeline
- poor-cli has ~30+ built-in tools plus MCP tools

YOUR DELIVERABLES:
1. Audit: count total tool schemas, measure token size of full catalog
2. Classify tools into groups (core, search, git, github, quality, network, etc.)
3. Build task-to-tools classifier (keyword + context heuristic)
4. Modify prompt assembly to only inject relevant tool groups
5. Add dynamic tool loading: if model requests missing tool, add group + retry
6. Implement lazy MCP schema loading (defer until first use)
7. Write tests in tests/test_lazy_tools.py

CONSTRAINTS:
- Core tools (read_file, write_file, edit_file, bash) always loaded
- Dynamic loading on missing tool must be seamless — no user-visible error
- MCP lazy loading must not break MCP health checks
- [CUSTOMIZE: list your MCP servers for testing]

Read the phase doc first, then implement.
```

### Agent 3C: Importance-Weighted History Pruning

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building a smart history pruning system that scores each conversation turn for
importance and selectively removes low-value turns, instead of blanket summarization.

FIRST: Read docs/phase_03_smart_loading.md, specifically the "Agent 3C" section for full
implementation details and acceptance criteria.

CONTEXT:
- Conversation history in poor-cli/history.py
- Context optimization in poor-cli/context_optimizer.py
- Session management in poor-cli/session_manager.py

YOUR DELIVERABLES:
1. Implement turn scoring: recency, tool success, file relevance, role, decision content
2. Build pruning engine: sort by score, remove lowest until under budget
3. Add supersession detection (failed → retried → mark old as superseded)
4. Integrate with context_optimizer.py compaction pipeline
5. Add pruning notifications to user
6. Write tests in tests/test_history_pruning.py

CONSTRAINTS:
- Never prune: current turn, last user message, pinned context
- Pruning must be reversible — keep pruned turns in a sidecar log for recovery
- Integrate with (don't replace) existing /compact
- [CUSTOMIZE: set your preferred pruning aggressiveness threshold]

Read the phase doc first, then implement.
```

---

## Phase 4: Caching & Routing

**Agents: 3 (all parallel)**
**Reference document:** `docs/phase_04_caching_routing.md`
**Estimated time per agent:** 7-14 days
**Prerequisites:** Phase 2C (prompt caching) recommended. Phase 1-3 helpful but not blocking.

### Agent 4A: Semantic Response Caching

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building a local semantic cache for poor-cli that avoids redundant API calls by
detecting semantically similar queries and returning cached responses.

FIRST: Read docs/phase_04_caching_routing.md, specifically the "Agent 4A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Existing file cache: poor-cli/file_cache.py
- Embeddings: poor-cli/embeddings.py
- Provider base: poor-cli/providers/base.py
- Cost tracking: poor-cli/cost.py

YOUR DELIVERABLES:
1. Audit poor-cli/embeddings.py — determine available embedding infrastructure
2. Create poor-cli/semantic_cache.py — SQLite-backed cache with cosine similarity search
3. Implement context-aware cache keys (file set + pinned context hash)
4. Add cache check before API call in provider base class
5. Cache invalidation: file changes, TTL, manual command
6. Display cache hit rates and savings in /cost and /savings
7. Write tests in tests/test_semantic_cache.py

CONSTRAINTS:
- Embedding model must work offline (no API calls for caching)
- Cache threshold configurable (default: 0.92 similarity)
- Must not cache tool-call-heavy responses (only pure Q&A)
- [CUSTOMIZE: specify your preferred local embedding model]

Read the phase doc first, then implement.
```

### Agent 4B: LLM Cascading / Model Routing

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building an intelligent model routing engine for poor-cli that sends each query
to the cheapest model capable of answering it, cascading to more expensive models only
when needed.

FIRST: Read docs/phase_04_caching_routing.md, specifically the "Agent 4B" section for
full implementation details and acceptance criteria.

CONTEXT:
- poor-cli supports 5 providers (Gemini, OpenAI, Anthropic, OpenRouter, Ollama)
- Architect mode: poor-cli/architect_mode.py
- Profiles/economy: poor-cli/profiles.py
- Provider factory: poor-cli/providers/provider_factory.py
- Cost tracking: poor-cli/cost.py

YOUR DELIVERABLES:
1. Audit poor-cli/architect_mode.py — check for existing routing logic
2. Create poor-cli/model_router.py — complexity classifier + routing table
3. Implement task complexity classification (trivial/simple/moderate/complex)
4. Define routing tables per provider (map complexity → model)
5. Add cascade logic: retry with more expensive model on low confidence
6. Tie routing to economy modes (frugal=aggressive routing, quality=no routing)
7. Log routing decisions in /cost
8. Write tests in tests/test_model_router.py

CONSTRAINTS:
- User explicit /switch overrides routing
- Routing tables must be configurable (not just hardcoded)
- Cascade must have a max-retry limit (default: 1 escalation)
- [CUSTOMIZE: define your per-provider model tiers and cost preferences]

Read the phase doc first, then implement.
```

### Agent 4C: Grammar-Constrained Output Integration

```
[AGENT PROMPT — copy/paste to your coding agent]

You are integrating structured/grammar-constrained output into poor-cli's provider layer
to eliminate malformed output retries and produce more compact structured responses.

FIRST: Read docs/phase_04_caching_routing.md, specifically the "Agent 4C" section for
full implementation details and acceptance criteria.

CONTEXT:
- Provider base: poor-cli/providers/base.py
- Edit formats: poor-cli/edit_formats.py
- Tool definitions: poor-cli/enhanced_tools.py
- Each provider has its own structured output API

YOUR DELIVERABLES:
1. Identify all structured output points (tool calls, edits, plan mode, JSON ops)
2. Create poor-cli/structured_output.py — JSON schemas for structured responses
3. Add response_format support to each provider adapter
4. Use structured output for tool call arguments and edit blocks
5. Implement fallback: if structured output fails, retry with unconstrained generation
6. Measure: track retry rate before/after structured output
7. Write tests in tests/test_structured_output.py

CONSTRAINTS:
- Only constrain responses that SHOULD be structured (not free-form explanations)
- Each provider has different structured output APIs — handle per-provider
- Ollama may not support structured output for all models — graceful fallback
- [CUSTOMIZE: list which providers you want structured output on first]

Read the phase doc first, then implement.
```

---

## Phase 5: Advanced Compression

**Agents: 3 (all parallel)**
**Reference document:** `docs/phase_05_advanced_compression.md`
**Estimated time per agent:** 7-14 days
**Prerequisites:** Phase 2A (tree-sitter) for Agent 5B. Phase 3 recommended.

### Agent 5A: LLMLingua Prompt Compression

```
[AGENT PROMPT — copy/paste to your coding agent]

You are integrating prompt compression into poor-cli using LLMLingua-2 (or a custom
heuristic alternative) to remove redundant tokens from prompts before sending to the
main model.

FIRST: Read docs/phase_05_advanced_compression.md, specifically the "Agent 5A" section
for full implementation details and acceptance criteria.

CONTEXT:
- Context optimization: poor-cli/context_optimizer.py
- Profiles/economy: poor-cli/profiles.py
- pyproject.toml for dependencies

YOUR DELIVERABLES:
1. Create poor-cli/prompt_compressor.py — compression middleware
2. Implement LLMLingua-2 integration OR custom heuristic compression
3. Define content-type-specific compression ratios
4. Add preserve-patterns for code blocks, errors, file paths
5. Tie compression to economy modes
6. Lazy-load compression model (don't slow startup)
7. Measure compression speed — must be < 100ms per request
8. Write tests in tests/test_prompt_compressor.py

CONSTRAINTS:
- LLMLingua-2 is optional dependency — must work without it (heuristic fallback)
- Never compress current user message or code the model needs to edit
- Compression must not introduce latency > 100ms
- [CUSTOMIZE: choose LLMLingua-2 vs heuristic based on your GPU/CPU resources]

Read the phase doc first, then implement.
```

### Agent 5B: AST-Aware Code Chunking

```
[AGENT PROMPT — copy/paste to your coding agent]

You are replacing poor-cli's code chunking in the indexer with AST-aware chunking that
preserves syntactic boundaries, producing chunks that are always complete functions/classes.

FIRST: Read docs/phase_05_advanced_compression.md, specifically the "Agent 5B" section
for full implementation details and acceptance criteria.

CONTEXT:
- Current indexer: poor-cli/indexer.py
- Embeddings: poor-cli/embeddings.py
- tree-sitter infrastructure from Phase 2A (may or may not be done yet)

YOUR DELIVERABLES:
1. Audit poor-cli/indexer.py — document current chunking strategy
2. Implement AST-aware chunking for Python, Lua, JS/TS, Rust
3. Define chunk types per language (functions, classes, methods, etc.)
4. Add natural language descriptions per chunk
5. Implement dual embedding (code + description)
6. Add incremental re-indexing (only changed files)
7. Write tests in tests/test_ast_chunking.py

CONSTRAINTS:
- tree-sitter is required — if Phase 2A added it, use it; otherwise add dependency
- Chunks must be syntactically complete (never mid-function)
- Large chunks (>500 lines) must split at method boundaries
- [CUSTOMIZE: list your primary codebase languages for priority]

Read the phase doc first, then implement.
```

### Agent 5C: Selective Failure Amnesia

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building a failure amnesia system for poor-cli that extracts lessons from failed
tool calls and prunes the full failure traces from conversation history. This is a
greenfield implementation — no standard exists.

FIRST: Read docs/phase_05_advanced_compression.md, specifically the "Agent 5C" section
for full implementation details and acceptance criteria.

CONTEXT:
- Error recovery: poor-cli/error_recovery.py
- Context optimization: poor-cli/context_optimizer.py
- History management: poor-cli/history.py

YOUR DELIVERABLES:
1. Create poor-cli/failure_amnesia.py — failure detection + lesson extraction + trace pruning
2. Implement failure detection for tool calls (exit codes, error responses)
3. Build lesson extraction: use current model to summarize failure into 1-2 sentences
4. Replace full traces with lessons in conversation history
5. Safety: never prune unresolved or most-recent failures
6. Integrate with context optimizer (failures pruned first during compaction)
7. Track tokens saved in cost dashboard
8. Write tests in tests/test_failure_amnesia.py

CONSTRAINTS:
- Lesson extraction costs a small API call — must be cheaper than keeping full trace
- Extraction prompt must be minimal (< 100 tokens including the failure summary)
- Never prune failures the user explicitly referenced
- [CUSTOMIZE: set your threshold for when failure traces are large enough to amnesia]

Read the phase doc first, then implement.
```

---

## Phase 6: Memory Architecture

**Agents: 2 (parallel)**
**Reference document:** `docs/phase_06_memory_architecture.md`
**Estimated time per agent:** 14-21 days
**Prerequisites:** Phase 3 (smart loading/pruning) should be complete. Phase 5C (failure amnesia) recommended.

### Agent 6A: Differential Context Updates

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing a MemGPT-style working memory system for poor-cli where the agent
receives diffs between turns instead of full conversation history re-sends. This is the
most architecturally significant change in the optimization roadmap.

FIRST: Read docs/phase_06_memory_architecture.md, specifically the "Agent 6A" section
for full implementation details and acceptance criteria.

CONTEXT:
- Context providers: poor-cli/context_providers.py
- Session store: poor-cli/session_store.py
- Context optimizer: poor-cli/context_optimizer.py
- Memory: poor-cli/memory.py

YOUR DELIVERABLES:
1. Create poor-cli/working_memory.py — WorkingMemory model + delta computation
2. Implement delta-based prompt construction (working memory + changes since last turn)
3. Build hybrid mode: full history for first N turns, then switch to deltas
4. Add confusion recovery: detect lost context → fall back to full history for 1 turn
5. Persist working memory across turns with periodic re-summarization
6. Integrate with /compact (compact resets working memory)
7. Measure: compare per-turn token usage with/without delta mode
8. Write tests in tests/test_working_memory.py

CONSTRAINTS:
- This is a major refactor of context_providers.py — proceed carefully
- Hybrid mode default: switch to deltas after 5 turns or 50% context used
- Working memory must survive server restarts (persist to disk)
- [CUSTOMIZE: set your context window size and hybrid mode thresholds]

Read the phase doc first, then implement.
```

### Agent 6B: Position-Independent KV Cache Reuse

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing position-independent KV cache reuse for poor-cli's local inference
path (Ollama/vLLM). This pre-computes KV caches for repo files and reuses them regardless
of prompt position.

FIRST: Read docs/phase_06_memory_architecture.md, specifically the "Agent 6B" section
for full implementation details and acceptance criteria.

IMPORTANT: This feature ONLY works with self-hosted inference (Ollama, vLLM, SGLang).
It cannot work with closed API providers.

CONTEXT:
- Ollama provider: poor-cli/providers/ollama_provider.py
- LMCache (https://github.com/LMCache/LMCache) is the reference implementation

YOUR DELIVERABLES:
1. Research: confirm LMCache works with vLLM for position-independent caching
2. Research: check if Ollama exposes KV cache APIs
3. Create poor-cli/kv_cache_store.py — pre-compute, store, invalidate, assemble KV caches
4. Integrate with Ollama provider (if API supports it) or document vLLM requirement
5. Gate behind feature flag + local inference detection
6. Measure TTFT with/without cache
7. Write docs: infrastructure requirements, setup guide
8. Write tests in tests/test_kv_cache.py

CONSTRAINTS:
- Feature must be OFF by default
- Only enable when local inference detected
- Document disk space requirements (KV caches can be large)
- [CUSTOMIZE: specify your local inference setup — Ollama vs vLLM]

Read the phase doc first, then implement.
```

---

## Phase 7: Adaptive Optimization

**Agents: 2 (parallel)**
**Reference document:** `docs/phase_07_adaptive_optimization.md`
**Estimated time per agent:** 14-28 days
**Prerequisites:** Phase 4B (model routing) — RL controller extends routing concept.

### Agent 7A: RL Token Budget Allocation

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building a meta-controller for poor-cli that learns to allocate token budgets
(thinking tokens, model choice, compression level) optimally based on task characteristics
and session state. Start with a rule-based decision tree, not neural RL.

FIRST: Read docs/phase_07_adaptive_optimization.md, specifically the "Agent 7A" section
for full implementation details and acceptance criteria.

CONTEXT:
- Economy/profiles: poor-cli/profiles.py
- Cost tracking: poor-cli/cost.py
- Phase 4B's model router (if built) provides the task complexity classifier

YOUR DELIVERABLES:
1. Create poor-cli/token_budget_controller.py — state observation + action selection
2. Create poor-cli/budget_logger.py — log (state, action, outcome) tuples
3. Implement rule-based decision tree as baseline controller
4. Integrate into per-turn decision loop (before each API call)
5. Log session data to .poor-cli/budget_logs.jsonl for offline analysis
6. Safety: economy mode overrides, minimum token floors
7. Measure: tokens per successful task with/without controller
8. Write tests in tests/test_budget_controller.py

CONSTRAINTS:
- Start with decision tree, NOT neural network
- Safety constraints are hard limits — controller cannot violate them
- Controller is advisory in quality mode
- [CUSTOMIZE: define your cost-quality preference curve]

Read the phase doc first, then implement.
```

### Agent 7B: Speculative Decoding Integration

```
Archived by Phase 9B. Do not create `poor-cli/speculative_decoding.py` unless a new end-to-end vLLM provider PRD is accepted first.
```

---

## Phase 8: Research Frontier

**Agents: 4 (all parallel)**
**Reference document:** `docs/phase_08_research_frontier.md`
**Estimated time per agent:** 21-60 days (research timelines are uncertain)
**Prerequisites:** Phases 1-7 substantially complete. These are R&D bets.

### Agent 8A: Latent-Space Inter-Agent Communication

```
[AGENT PROMPT — copy/paste to your coding agent]

You are researching and prototyping latent-space communication between poor-cli's agents,
replacing text-based multi-agent communication with direct hidden-state passing.

FIRST: Read docs/phase_08_research_frontier.md, specifically the "Agent 8A" section for
full research plan and acceptance criteria.

This is a RESEARCH task. Your primary deliverable is a feasibility report with a working
prototype if feasible, or a documented assessment of why not.

YOUR DELIVERABLES:
1. Literature review: LatentMAS, Interlat — detailed notes on requirements
2. Feasibility assessment: which models, which frameworks, what infrastructure
3. Prototype (if feasible): LatentAgent class with hidden-state communication
4. Benchmark: compare text vs latent communication on multi-agent tasks
5. Write docs/LATENT_COMMUNICATION.md — findings, setup guide, limitations
6. If infeasible: document WHY and what would need to change

CONSTRAINTS:
- This requires open-weights models and GPU access
- Do not build production code — prototype quality is sufficient
- Focus on answering: "can this work?" before "how well does it work?"
- [CUSTOMIZE: specify your GPU resources and available open-weights models]

Read the phase doc first, then research.
```

### Agent 8B: Latent Reasoning

```
[AGENT PROMPT — copy/paste to your coding agent]

You are researching latent reasoning techniques (Coconut, Quiet-STaR, CODI) to reduce
chain-of-thought token overhead. Your primary deliverable is a feasibility report plus
a practical thinking-token-budget optimizer.

FIRST: Read docs/phase_08_research_frontier.md, specifically the "Agent 8B" section for
full research plan and acceptance criteria.

This is a RESEARCH task with a practical fallback deliverable.

YOUR DELIVERABLES:
1. Literature review: Coconut, Quiet-STaR, CODI — feasibility ranking
2. Prototype (if any approach is feasible with available models)
3. PRACTICAL FALLBACK (implement regardless): thinking_budget.py — per-task-type
   thinking token limits based on historical data analysis
4. Write docs/LATENT_REASONING.md — findings
5. Benchmark thinking budget optimizer: tokens saved vs task success rate

CONSTRAINTS:
- The practical fallback (thinking budgets) MUST be delivered even if latent reasoning is infeasible
- Thinking budget should integrate with Phase 7A's budget controller
- [CUSTOMIZE: specify your model access and compute resources]

Read the phase doc first, then research.
```

### Agent 8C: Code-Specific Tokenizer Research

```
[AGENT PROMPT — copy/paste to your coding agent]

You are researching code-specific tokenization to reduce the 1.5-2× token overhead that
standard BPE tokenizers impose on source code.

FIRST: Read docs/phase_08_research_frontier.md, specifically the "Agent 8C" section for
full research plan and acceptance criteria.

This is a RESEARCH task. Your primary deliverable is a benchmark report with
recommendations.

YOUR DELIVERABLES:
1. Quantify: measure tokenization overhead on poor-cli's codebase with tiktoken
2. Literature review: CodeBPE, AST-T5
3. Prototype approach A: code pre-tokenization (normalize identifiers, collapse whitespace)
4. Prototype approach B: hybrid AST-token representation
5. Benchmark all approaches: token count reduction vs task success rate
6. Write docs/CODE_TOKENIZER_RESEARCH.md — findings + recommendation
7. Recommendation: pursue or shelve, with evidence

CONSTRAINTS:
- Pre-tokenization must not break edit accuracy (model must still produce valid edits)
- Benchmark on at least 50 files across Python, Lua, JS/TS
- [CUSTOMIZE: specify your primary codebase languages for benchmarking]

Read the phase doc first, then research.
```

### Agent 8D: Neural Code Embeddings as Context Substitute

```
[AGENT PROMPT — copy/paste to your coding agent]

You are researching whether a codebase can be represented as a fixed-size neural embedding
(analogous to images in multimodal models) instead of raw text tokens, and prototyping
the most feasible approach.

FIRST: Read docs/phase_08_research_frontier.md, specifically the "Agent 8D" section for
full research plan and acceptance criteria.

This is a RESEARCH task — the most speculative in the entire roadmap. Your primary
deliverable is an architectural study with a practical neural-retrieval fallback.

YOUR DELIVERABLES:
1. Architecture study: LLaVA/CLIP → code analogy assessment
2. CodeBERT baseline: codebase → embedding → retrieval pipeline
3. PRACTICAL FALLBACK: neural retrieval — embed files, retrieve top-K by similarity,
   include only relevant files in context (enhancement of Phase 5B)
4. Benchmark: text-in-context vs neural retrieval on code Q&A tasks
5. Write docs/NEURAL_CODE_EMBEDDINGS.md — findings
6. Recommendation: pursue full neural embeddings or stick with retrieval?

CONSTRAINTS:
- The practical fallback (neural retrieval) MUST be delivered
- Full neural embeddings likely require training — document requirements
- Benchmark on poor-cli's own codebase for relevance
- [CUSTOMIZE: specify your GPU resources and training data availability]

Read the phase doc first, then research.
```

---

## Execution Checklist

### Before starting any phase:
- [ ] Read the phase document thoroughly
- [ ] Ensure prerequisites are met
- [ ] Customize all `[CUSTOMIZE]` sections in agent prompts
- [ ] Set up agent environments (venv, dependencies, etc.)

### Per-agent workflow:
1. Copy prompt to agent
2. Agent reads phase doc
3. Agent audits existing code
4. Agent implements
5. Agent writes tests
6. Review agent output
7. Run tests: `make test`
8. Merge to main

### After each phase:
- [ ] Run full test suite
- [ ] Measure token savings (use /cost before/after)
- [ ] Update LONGTERM-TODO.md with completed items
- [ ] Document any architectural decisions for future phases

---

## Pain Point Coverage Matrix

Every pain point from PAIN-POINTS.md is addressed by at least one phase:

| Pain Point | Phase(s) | Agent(s) |
|---|---|---|
| #1 Context accumulation | 1C, 3C, 6A | 1C, 3C, 6A |
| #2 Tool output bloat | 1A, 2B | 1A, 2B |
| #3 Codebase reading | 1A, 2A, 5B, 6B, 8D | 1A, 2A, 5B, 6B, 8D |
| #4 System prompt bloat | 2C, 3A, 5A | 2C, 3A, 5A |
| #5 Retry/failure tax | 5C | 5C |
| #6 Tool schema bloat | 3B | 3B |
| #7 Lost-in-the-middle | 5B | 5B |
| #8 Thinking overhead | 8B | 8B |
| #9 Ambient noise | 1A | 1A |
| #10 Edit format tax | 1B | 1B |
| #11 Multi-agent overhead | 8A | 8A |
| #12 Code tokenization | 8C | 8C |
| #13 Duplicate queries | 4A | 4A |
| #14 CoT verbosity | 1D, 4C, 8B | 1D, 4C, 8B |
| #15 Non-prefix cache | 6B | 6B |
| #16 Static prompt redundancy | 2C | 2C |
| #17 Tokenizer special chars | (low priority, not addressed) | — |
| #18 Markdown overhead | 1D, 4C | 1D, 4C |
| #19 Cache invalidation | 2C | 2C |

**Pain Point #17** (tokenizer special-char issues) is 🟢 Low severity and not directly addressed. It is partially mitigated by Phase 8C (code tokenizer research) if pursued.

---

## Phase 9: Repo Cleanup & Dead Code Purge

**Agents: 6 (two sub-waves)**
**Reference document:** `docs/phase_09_repo_cleanup.md`
**Estimated time per agent:** 1-3 days
**Prerequisites:** PRDs 001-004 complete.

**Sub-wave 9.i (parallel):** 9A, 9B, 9E.
**Sub-wave 9.ii (parallel, after 9.i):** 9C, 9F, 9D.

### Agent 9A: Remove Retired Front-Ends (PRD 006)

```
[AGENT PROMPT — copy/paste to your coding agent]

PRD 006 is complete. Retired front-end sources were removed from the repository; git history remains the recovery path.

Do not re-home retired client code. Do not restore the old tree outside an explicit rollback.
```

### Agent 9B: Stub Module Decision + Execution (PRD 007)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the decision outcome on stub modules (`docker_sandbox`,
`speculative_decoding`, `rtk_integration`, plus any other "concept car" stubs) for poor-cli.

FIRST: Read docs/phase_09_repo_cleanup.md, specifically the "Agent 9B" section for the
chosen decision and acceptance criteria.

CONTEXT:
- Each stub is either (a) shipped end-to-end elsewhere, or (b) removed here
- `rtk_integration.py` is covered by PRD 026 (RTK-lite ships) — leave intact if PRD 026 is in-flight
- `docker_sandbox.py` and `speculative_decoding.py` default to archive-unless-shown-shipped
- Docs and `LONGTERM-TODO.md` must reflect the outcome

YOUR DELIVERABLES:
1. Record the per-stub decision matrix in `docs/phase_09_repo_cleanup.md`
2. For "archive" decisions: delete file, remove imports, prune docs
3. For "ship" decisions: confirm follow-up PRD exists and leave file as-is
4. Update README / architecture docs to drop any mention of archived stubs
5. Add a CI check (or test) asserting no imports of removed modules

CONSTRAINTS:
- Do NOT silently alter behavior of stubs we are keeping
- Prefer delete over comment-out — we have git history
- [CUSTOMIZE: list any stubs added locally that need the same treatment]

Read the phase doc and PRD first, then implement.
```

### Agent 9C: Research Module Relocation (PRD 008)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are relocating research-grade modules into `poor-cli/research/` gated by feature flags
so contributors reading the main package see only production code.

FIRST: Read docs/phase_09_repo_cleanup.md, specifically the "Agent 9C" section for full
implementation details and acceptance criteria.

CONTEXT:
- Several research-only modules currently live at `poor-cli/*.py` top level
- Cold-start imports pull them in unnecessarily
- Feature flags live in `poor-cli/repo_config.py` and per-user config
- Do NOT delete — this PRD is purely a move + gate

YOUR DELIVERABLES:
1. Inventory research modules (latent_communication, neural_code_encoder, etc.; `speculative_decoding.py` was archived by 9B)
2. Move each into `poor-cli/research/<name>.py`; add `poor-cli/research/__init__.py`
3. Add `research.<name>.enabled = false` config defaults
4. Update every importer to go through the gated loader
5. Measure cold-start import time before/after; document the delta

CONSTRAINTS:
- Do NOT change module public APIs; only imports move
- Do NOT delete anything here (PRD 007 is the deleter)
- Feature flag must default OFF so normal users skip the import
- [CUSTOMIZE: note any research modules you want kept hot-loaded]

Read the phase doc and PRD first, then implement.
```

### Agent 9D: README Rewrite + Screenshot Purge (PRD 009)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are rewriting `README.md` so it reads as a Neovim-plugin README with a Python server
backend, and purging stale TUI screenshots from `asset/`.

FIRST: Read docs/phase_09_repo_cleanup.md, specifically the "Agent 9D" section for full
implementation details and acceptance criteria.

CONTEXT:
- Current README references the retired TUI (dead since PRD 006)
- Above-the-fold must be: value prop + one screenshot + install snippet
- `asset/` contains stale TUI screenshots that misrepresent the product
- `nvim-poor-cli/README.md` gets alignment edits only, no rewrite

YOUR DELIVERABLES:
1. Audit README for any references to retired surfaces; remove
2. Rewrite above-the-fold: Neovim-first value prop, single current screenshot, install
3. Capture 3-5 current-UX screenshots; replace stale TUI shots in `asset/`
4. Add a short "how it works" diagram (ASCII or single image)
5. Align `nvim-poor-cli/README.md` cross-references (edits only)

CONSTRAINTS:
- Do NOT build a full docs site (LONGTERM-TODO H4 handles that)
- Do NOT ship an asciinema recording in this PRD
- Keep the README under ~400 lines
- [CUSTOMIZE: your preferred screenshot colorscheme]

Read the phase doc and PRD first, then implement.
```

### Agent 9E: `core.py` Pre-Slice (PRD 017)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are pre-slicing `poor-cli/core.py` into empty section modules so follow-up PRDs
(018, 021) can migrate code in small, reviewable chunks without behavior change.

FIRST: Read docs/phase_09_repo_cleanup.md, specifically the "Agent 9E" section for full
implementation details and acceptance criteria.

CONTEXT:
- `core.py` is oversized and multi-responsibility; three targets are agent-loop,
  tool-dispatch, and turn-lifecycle
- This PRD creates the empty scaffolding only — no logic moves yet
- PRD 018 will later fill `ContextAssemblyOrchestrator`; PRD 021 pins the ceiling at 1000

YOUR DELIVERABLES:
1. Create `poor-cli/core_agent_loop.py`, `core_tool_dispatch.py`, `core_turn_lifecycle.py`
2. Each file exports a stub class with the expected public surface only
3. Add re-exports from `core.py` so nothing breaks at import time
4. Write a "placement map" doc listing which core.py regions will migrate where
5. Confirm `make lint && make test` pass with zero behavioral change

CONSTRAINTS:
- Do NOT move any logic yet — scaffolding only
- Do NOT change any `PoorCLICore` public API
- Every test must pass unchanged
- [CUSTOMIZE: if your fork added core.py sections, include them in the placement map]

Read the phase doc and PRD first, then implement.
```

### Agent 9F: Line-Count CI Gate (PRD 021)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are wiring a CI gate that fails when key files exceed their line budgets, protecting
the refactor gains from regression.

FIRST: Read docs/phase_09_repo_cleanup.md, specifically the "Agent 9F" section for full
implementation details and acceptance criteria.

CONTEXT:
- Budgets: `core.py` ≤1000, `config.py` ≤1500, any other py ≤2000, with explicit temporary caps for pre-existing monoliths (`server/runtime.py`, `tools_async.py`, `multiplayer.py`, `core_turn_lifecycle.py`)
- CI lives in `.github/workflows/` (or the repo's CI surface)
- Must produce a clear error message with the delta (e.g. "core.py 1124/1000 (+124)")
- Must not gate test files

YOUR DELIVERABLES:
1. Add `scripts/check_line_budgets.py` (or similar) with per-file caps
2. Wire it into CI as a required check
3. Add a pre-commit hook mirroring the same check
4. Document the budgets in `docs/phase_09_repo_cleanup.md` and CONTRIBUTING
5. Verify locally by artificially bloating a file; confirm CI fails

CONSTRAINTS:
- Exclude `tests/**`, generated files, and vendored code
- Make budget values data-driven (one constants dict); no magic numbers
- [CUSTOMIZE: any repo-specific files needing custom caps]

Read the phase doc and PRD first, then implement.
```

---

## Phase 10: Core Refactor & Partition

**Agents: 4 (two sub-waves)**
**Reference document:** `docs/phase_10_core_refactor.md`
**Estimated time per agent:** 3-7 days
**Prerequisites:** Phase 9E (core pre-slice) complete.

**Sub-wave 10.1 (parallel):** 10A, 10B.
**Sub-wave 10.2 (parallel, after 10.1):** 10C, 10D.

### Agent 10A: Context Assembly Orchestrator (PRD 018)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are extracting `ContextAssemblyOrchestrator` — a single entry point with
`.assemble(turn_input) -> ContextSnapshot` — out of `core.py`.

FIRST: Read docs/phase_10_core_refactor.md, specifically the "Agent 10A" section for full
implementation details and acceptance criteria.

CONTEXT:
- Today, context assembly is scattered across core.py, context_providers.py, history.py
- The orchestrator calls existing modules; it does not re-implement selection logic
- Output is a typed `ContextSnapshot` dataclass
- Enables PRD 022 (PageRank selection) and PRD 027 (block caching) downstream

YOUR DELIVERABLES:
1. Define `ContextSnapshot` dataclass (files, messages, rules, tool schemas)
2. Create `poor-cli/context_assembly.py` housing `ContextAssemblyOrchestrator`
3. Migrate existing assembly code paths into `.assemble()` without logic changes
4. Update `core.py` to call the orchestrator and drop direct calls to sub-modules
5. Write `tests/test_context_assembly.py` covering the snapshot shape and parity

CONSTRAINTS:
- Do NOT change what content enters context — only how it is assembled
- Do NOT rewrite the selection or compression heuristics
- Preserve every public API on `PoorCLICore`
- [CUSTOMIZE: any repo-specific context sources to route through the orchestrator]

Read the phase doc and PRD first, then implement.
```

### Agent 10B: Server Handlers Partition (PRD 019)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are partitioning `poor-cli/server/runtime.py` into a `handlers/` package where each
handler self-registers via a decorator.

FIRST: Read docs/phase_10_core_refactor.md, specifically the "Agent 10B" section for full
implementation details and acceptance criteria.

CONTEXT:
- `runtime.py` currently mixes dispatch, transport, and every RPC handler
- Target: `runtime.py` ≤800 lines; each `handlers/*.py` ≤500 lines
- Multiplayer state machine needs its own module (`handlers/multiplayer.py`)
- A decorator like `@register("method.name")` populates the dispatch table

YOUR DELIVERABLES:
1. Create `poor-cli/server/handlers/` with `__init__.py` and a `register` decorator
2. Move each handler family (chat, context, cost, multiplayer, etc.) to its own file
3. Slim `runtime.py` down to dispatch + transport + handler import bootstrapping
4. Confirm no method signatures changed (RPC wire shape identical)
5. Write targeted tests exercising dispatch across at least 3 handler families

CONSTRAINTS:
- Do NOT change any method signature or wire format
- Do NOT add OpenAPI / JSON Schema docs (future PRD)
- Respect the line-budget CI gate from PRD 021
- [CUSTOMIZE: note any downstream handlers in your fork that need migration]

Read the phase doc and PRD first, then implement.
```

### Agent 10C: ProviderCapability Enum (PRD 020)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are introducing a `ProviderCapability` enum that every provider declares, replacing
`isinstance` checks scattered through the core.

FIRST: Read docs/phase_10_core_refactor.md, specifically the "Agent 10C" section for full
implementation details and acceptance criteria.

CONTEXT:
- Five providers live under `poor-cli/providers/` with divergent feature sets
- Capability examples: streaming, vision, thinking, block caching, latent communication
- PRD 030 (model picker) will render capability icons from this enum
- This PRD only types capabilities — it does not implement any new ones

YOUR DELIVERABLES:
1. Define `ProviderCapability` enum + `capabilities: frozenset[ProviderCapability]` on base
2. Declare the correct capability set on each provider adapter
3. Replace provider `isinstance` branches with `if cap in provider.capabilities`
4. Expose `capabilities` through the RPC `getStatus` (or equivalent) payload
5. Add tests asserting each provider's declared capabilities match reality

CONSTRAINTS:
- Do NOT implement any new capability here (e.g., keep latent comm gated elsewhere)
- Do NOT change the underlying SDK calls
- [CUSTOMIZE: custom providers in your fork need a capability set declared]

Read the phase doc and PRD first, then implement.
```

### Agent 10D: Extension Model Consolidation (PRD 064)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are executing the consolidation DECISION on poor-cli's extension model
(AutomationRule + skills).

FIRST: Read docs/phase_10_core_refactor.md, specifically the "Agent 10D" section for the
chosen decision and migration plan.

CONTEXT:
- Today: PRD 064 resolves the legacy extension overlap into AutomationRule + skills
- Decision options: (a) merge to AutomationRule+Skills (2 concepts), (b) keep 4, (c) partial merge
- Phase doc records the final decision; implement that option
- Skills are likely preserved (distinct "instruction library" concept)

YOUR DELIVERABLES:
1. Implement the chosen consolidation per the phase doc decision
2. Provide a migration script that converts existing user configs into the new shape
3. Update every doc page / slash command help mentioning the old concepts
4. Preserve backward-compat aliases for one release cycle
5. Add tests for cron/event/slash-command triggers against the unified model

CONSTRAINTS:
- Must not break existing user `.poor-cli/` configs without migration
- Keep migration idempotent and reversible (dry-run flag)
- [CUSTOMIZE: the chosen option — (a/b/c) — records the decision]

Read the phase doc and PRD first, then implement.
```

---

## Phase 11: Security & Policy Hardening

**Agents: 6 (mostly parallel; 11E before 11F)**
**Reference document:** `docs/phase_11_security_policy.md`
**Estimated time per agent:** 2-5 days
**Prerequisites:** None blocking; benefits from Phase 10B landed.

### Agent 11A: RPC Rate Limiting (PRD 010)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing configurable rate-limiting on the inbound JSON-RPC surface of the
poor-cli server.

FIRST: Read docs/phase_11_security_policy.md, specifically the "Agent 11A" section for full
implementation details and acceptance criteria.

CONTEXT:
- Every inbound RPC call must traverse a limiter before handler dispatch
- Hot methods (chatStreaming, completions) have tighter caps than cold ones (getStatus)
- Exceeding the cap returns a structured JSON-RPC 429-equivalent error; no blocking
- Single local user — global limits are enough; skip per-user buckets

YOUR DELIVERABLES:
1. Add `poor-cli/server/rate_limit.py` with a token-bucket implementation
2. Hook into dispatch (handlers package from PRD 019 if landed)
3. Define per-method defaults in config; allow user overrides in `.poor-cli/config.yaml`
4. Emit an audit-log event on 429 (ties into PRD 011)
5. Write tests covering normal traffic, bursts, and exceed scenarios

CONSTRAINTS:
- Do NOT queue dropped requests — return the error, let the client retry
- Do NOT add token-count-aware limits (economy already covers that for LLM calls)
- [CUSTOMIZE: any repo-specific RPC methods needing custom buckets]

Read the phase doc and PRD first, then implement.
```

### Agent 11B: Audit Log Rotation (PRD 011)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding size-capped rotation, archival, and export to poor-cli's audit log DB.

FIRST: Read docs/phase_11_security_policy.md, specifically the "Agent 11B" section for full
implementation details and acceptance criteria.

CONTEXT:
- Audit DB is SQLite at `.poor-cli/audit.db`; schema is frozen by this PRD
- Archive format: gzipped JSONL at `.poor-cli/audit/archive/YYYY-MM.jsonl.gz`
- A scheduled archival job trims the live DB after exporting old rows
- User-facing command: `/audit-export [--since ...] [--to FILE]`

YOUR DELIVERABLES:
1. Add size-cap config (default 100 MB) and row-count fallback
2. Implement `audit_export(since, to)` producing JSONL
3. Implement monthly archival into gz JSONL + post-archive DB trim
4. Expose `/audit-export` slash command and corresponding RPC method
5. Write tests for rotation boundary, export round-trip, archive replay

CONSTRAINTS:
- Do NOT alter the audit table schema (state it in the PRD)
- Do NOT ship a remote sink integration here
- Archive writes must be atomic (temp-file + rename)
- [CUSTOMIZE: your preferred archive directory if not the default]

Read the phase doc and PRD first, then implement.
```

### Agent 11C: Keyring Credential Storage (PRD 012)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are integrating the OS keyring as the preferred credential store for poor-cli
(Keychain / Secret Service / Credential Manager), with env+plaintext fallback.

FIRST: Read docs/phase_11_security_policy.md, specifically the "Agent 11C" section for full
implementation details and acceptance criteria.

CONTEXT:
- Lookup order must be: keyring → env var → plaintext config
- Use `keyring` from PyPI (cross-platform); add as a soft dependency
- Setup wizard offers to migrate existing env/plaintext keys into the keyring
- Dev ergonomics: env + plaintext fallback stays permanently

YOUR DELIVERABLES:
1. Add `poor-cli/credentials.py` wrapping `keyring` with graceful fallback
2. Update every provider credential read path to use the new helper
3. Add a migration wizard step: detect existing creds, offer to move into keyring
4. Surface keyring status in `/status` and setup wizard
5. Write tests with a fake keyring backend covering all three fallback tiers

CONSTRAINTS:
- Do NOT remove env/plaintext fallback — breaks CI and devs
- Do NOT ship encryption of the plaintext config in this PRD
- Handle keyring-unavailable hosts silently (log once, continue)
- [CUSTOMIZE: note your OS keyring backends for QA priorities]

Read the phase doc and PRD first, then implement.
```

### Agent 11D: Browser Tool JS Sandbox (PRD 013)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are hardening the `browser_evaluate` tool so arbitrary JS cannot exfiltrate or
destructively mutate state.

FIRST: Read docs/phase_11_security_policy.md, specifically the "Agent 11D" section for full
implementation details and acceptance criteria.

CONTEXT:
- Tool lives alongside the Playwright integration in `poor-cli/enhanced_tools.py`
- Use Playwright's built-in isolation; do NOT roll a full JS sandbox
- Denylist: `localStorage.clear`, `document.cookie` writes, `navigator.sendBeacon`,
  third-party origin `fetch`
- Output size + exec timeout are mandatory

YOUR DELIVERABLES:
1. Add size + timeout caps (configurable) to `browser_evaluate`
2. Static scan JS for denylist patterns; refuse or warn per policy
3. Wrap evaluation so return values must be JSON-serializable
4. Emit audit-log events on every evaluation (command hash + outcome)
5. Write tests with a locally-served HTML fixture covering allow/deny cases

CONSTRAINTS:
- Do NOT block all `fetch` — some legitimate flows need same-origin network
- Do NOT implement a full JS sandbox — lean on Playwright isolation
- Respect same-origin by default; third-party fetch requires policy opt-in
- [CUSTOMIZE: domain allowlist for your usage]

Read the phase doc and PRD first, then implement.
```

### Agent 11E: Trust Center Interactive (PRD 034)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the interactive Trust Center — a single scratch buffer with inline
actions for sandbox toggles, permission rule viewing, audit rotation, and audit export.

FIRST: Read docs/phase_11_security_policy.md, specifically the "Agent 11E" section for full
implementation details and acceptance criteria.

CONTEXT:
- New buffer type in `nvim-poor-cli/lua/poor-cli/trust_center.lua`
- Inline actions rendered as virtual text: `[Toggle sandbox]`, `[Rotate audit log]`, etc.
- Cursor-on-action + `<CR>` invokes the handler; no separate config UI here
- Must pair with PRD 011 (rotation) and PRD 036 (policy inspector); 11E ships first

YOUR DELIVERABLES:
1. Implement `:PoorCLITrustCenter` opening a section-ful scratch buffer
2. Render virtual-text actions with keymaps; dispatch to the correct RPC method
3. Surface policy summary (allow/deny/prompt counts) at the top
4. Show last N audit-log events with a jump action to the event detail
5. Write Lua tests (plenary.busted; from PRD 065) for keymap + dispatch paths

CONSTRAINTS:
- Do NOT re-implement the full settings UI — that is a future PRD
- Do NOT duplicate policy rendering logic with PRD 036 — share a helper
- [CUSTOMIZE: user-defined action sections]

Read the phase doc and PRD first, then implement.
```

### Agent 11F: Policy Inspector Panel (PRD 036)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the Policy Inspector panel — a right-split buffer that enumerates every
permission rule in effect with scope, outcome, and source.

FIRST: Read docs/phase_11_security_policy.md, specifically the "Agent 11F" section for full
implementation details and acceptance criteria.

CONTEXT:
- Rules originate from user config, repo config, and defaults; show each source
- Must share the policy-render helper introduced by PRD 034 (11E must land first)
- Click-to-edit opens the rule file at the correct line
- Reload-on-save keymap refreshes the panel

YOUR DELIVERABLES:
1. Add `:PoorCLIPolicy` panel with columns: name / scope / outcome / source
2. Fetch rules via an RPC (`policy.list`); reuse server-side aggregator from 11E
3. Implement `gf`-style jump from rule row to rule source file
4. Reload keymap (`R`) re-fetches without closing the buffer
5. Write Lua tests covering render, jump, and reload paths

CONSTRAINTS:
- Do NOT mutate rules from this panel (view + jump only)
- Do NOT duplicate the aggregator logic — call into the shared helper
- [CUSTOMIZE: preferred column widths / ordering]

Read the phase doc and PRD first, then implement.
```

---

## Phase 12: Context Intelligence v2

**Agents: 6 (two sub-waves)**
**Reference document:** `docs/phase_12_context_intel_v2.md`
**Estimated time per agent:** 3-10 days
**Prerequisites:** Phase 10A (ContextAssemblyOrchestrator) for 12B, 12D, 12F.

**Sub-wave 12.1 (parallel):** 12A, 12C, 12E.
**Sub-wave 12.2 (serialized):** 12B → 12D → 12F.

### Agent 12A: File Watcher Consolidation (PRD 005)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are consolidating `poor-cli/watch.py` and `poor-cli/ide_watch.py` into a single
`poor-cli/file_watcher.py` serving both async-generator and callback consumers.

FIRST: Read docs/phase_12_context_intel_v2.md, specifically the "Agent 12A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Pick `ide_watch.py` as the survivor (richer, newer)
- Rename to `FileWatcher` in `poor-cli/file_watcher.py`
- Add `async def __aiter__` for old-style consumers; keep `on_change(cb)` for new style
- Both call patterns must share one event queue underneath

YOUR DELIVERABLES:
1. Create `poor-cli/file_watcher.py` consolidating both implementations
2. Migrate every importer; both consumption patterns must still work
3. Delete `poor-cli/watch.py` and `poor-cli/ide_watch.py`
4. Write `tests/test_file_watcher.py` covering both patterns
5. Run `make lint && make test`; zero behavior change expected

CONSTRAINTS:
- Keep existing public function/class names where feasible
- Do NOT add new watcher features — unify only
- [CUSTOMIZE: any downstream consumers in your fork to migrate]

Read the phase doc and PRD first, then implement.
```

### Agent 12B: PageRank File Selection (PRD 022)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are wiring the existing repo-graph PageRank score into poor-cli's file selection so
context picks the most-linked, most-recent, import-adjacent candidates.

FIRST: Read docs/phase_12_context_intel_v2.md, specifically the "Agent 12B" section for
full implementation details and acceptance criteria.

CONTEXT:
- Selection score: `alpha*recency + beta*pagerank + gamma*import_distance`
- Repo graph already exists from Phase 2A; we only consume it here
- Must flow through the ContextAssemblyOrchestrator from Phase 10A
- Defaults must be tuned so the change is a net quality improvement on a small benchmark

YOUR DELIVERABLES:
1. Add `poor-cli/context/file_selector.py` that emits ranked candidates
2. Thread the selector through `ContextAssemblyOrchestrator.assemble`
3. Expose `alpha/beta/gamma` in repo_config with sensible defaults
4. Add a tiny benchmark: N canned prompts → file-selection accuracy vs baseline
5. Write tests covering ranking determinism and weighted-tie handling

CONSTRAINTS:
- Do NOT re-implement PageRank — reuse `repo_graph.py`
- Defaults must win on the benchmark before you ship
- Never drop pinned files from selection
- [CUSTOMIZE: benchmark prompt set specific to your repo]

Read the phase doc and PRD first, then implement.
```

### Agent 12C: AGENTS.md Support (PRD 023)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding `AGENTS.md` support (hierarchical, closest-wins) with `CLAUDE.md` fallback,
so repo-level instructions can live in a standard filename.

FIRST: Read docs/phase_12_context_intel_v2.md, specifically the "Agent 12C" section for
full implementation details and acceptance criteria.

CONTEXT:
- Precedence (high to low): AGENTS.md in cwd, ancestor AGENTS.md, CLAUDE.md legacy
- Rules layer lives in `poor-cli/rules.py` (or similar)
- Found files should stack (append) rather than overwrite
- `/rules` slash command should list active files with paths

YOUR DELIVERABLES:
1. Update the rules loader to walk upward and collect AGENTS.md files
2. Keep CLAUDE.md as a fallback source with lower precedence
3. Extend `/rules` output to show each file's path and order
4. Add cache invalidation on any AGENTS.md change (via file watcher)
5. Write tests with nested fixtures verifying precedence and stacking

CONSTRAINTS:
- Do NOT silently ignore CLAUDE.md — fall back, don't break existing users
- Deduplicate when both AGENTS.md and CLAUDE.md live in the same directory
- [CUSTOMIZE: any additional rule filenames you want supported]

Read the phase doc and PRD first, then implement.
```

### Agent 12D: Block-Level Prompt Caching (PRD 027)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are extending prompt caching beyond the static prefix to per-block caching — each
context file (and optional rules / tool schemas) gets its own `cache_control` marker.

FIRST: Read docs/phase_12_context_intel_v2.md, specifically the "Agent 12D" section for
full implementation details and acceptance criteria.

CONTEXT:
- Builds on Phase 2C (prefix caching) and Phase 10A (orchestrator)
- Anthropic supports multiple `cache_control` blocks; OpenAI caches automatically
- Re-reading the same file later must reuse the cache even at a different position
- Must preserve cache hit metrics in `/cost` and `/savings`

YOUR DELIVERABLES:
1. Emit context files as individually cache-marked blocks in the provider payload
2. Stabilize per-file block ordering within a session
3. Add telemetry: per-block hit/miss counters, rolling hit rate
4. Update `/cost` display to show block-level cache stats
5. Write tests asserting block structure for each provider adapter

CONSTRAINTS:
- Do NOT cache agent outputs here — that is PRD 004
- Do NOT change semantic content of prompts
- Respect provider-specific cache-block count limits
- [CUSTOMIZE: preferred provider to optimize first]

Read the phase doc and PRD first, then implement.
```

### Agent 12E: Tool Output Schema Filter (PRD 028)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding per-tool output-shape filters declared in each tool's schema — JSONPath
for JSON tools, regex/keep-lines for text tools — applied post-execution, pre-context.

FIRST: Read docs/phase_12_context_intel_v2.md, specifically the "Agent 12E" section for
full implementation details and acceptance criteria.

CONTEXT:
- Every built-in tool declares a `output_filter` in its schema
- Dispatcher applies the filter after execution; agent timeline shows "X KB → Y KB"
- Full output remains accessible via timeline expand (user-facing UX)
- MCP tools are OUT of scope here (server owns their schemas — PRD 024 follow-up)

YOUR DELIVERABLES:
1. Extend the tool schema dataclass with `output_filter` (JSONPath | regex | keeplines)
2. Implement the filter middleware in the tool dispatcher
3. Backfill filters for at least 8 chatty tools (list_directory, gh, git_log, etc.)
4. Show filtered/raw sizes in the Agent Timeline (PRD 015)
5. Write tests covering each filter flavor and the fallthrough when absent

CONSTRAINTS:
- Do NOT filter user-facing output (timeline expansion shows raw)
- Do NOT touch MCP tool outputs here
- [CUSTOMIZE: your top-5 noisiest tools for priority]

Read the phase doc and PRD first, then implement.
```

### Agent 12F: Safe Pre-Tokenization Ship (PRD 058)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are shipping safe pre-tokenization end-to-end — gated behind
`context.safe_pretokenization` (default off v1, on v2 after real-world data).

FIRST: Read docs/phase_12_context_intel_v2.md, specifically the "Agent 12F" section for
full implementation details and acceptance criteria.

CONTEXT:
- Module + benchmark already exist (`bench_safe_pretok.py`); not wired in yet
- Wire into ContextAssemblyOrchestrator so code files can be pre-tokenized on ingest
- Savings must surface in the economy counters and Savings dashboard (PRD 041)
- Must be reversible per file — any failure falls back to raw content silently

YOUR DELIVERABLES:
1. Wire `safe_pretokenize()` into the file-ingest path inside the orchestrator
2. Add `context.safe_pretokenization` config (default false)
3. Track per-file tokens-saved in economy; roll up in `/cost` and `/savings`
4. Run the bench on a representative sample; document the delta
5. Add tests proving edit accuracy is unaffected (edited files round-trip correctly)

CONSTRAINTS:
- Do NOT ship aggressive pre-tokenization — only the safe variant
- If pre-tokenization breaks edits on any file, fall back to raw for that file
- [CUSTOMIZE: default v2 flip date contingent on your telemetry]

Read the phase doc and PRD first, then implement.
```

---

## Phase 13: Protocol & Streaming

**Agents: 3**
**Reference document:** `docs/phase_13_protocol_streaming.md`
**Estimated time per agent:** 4-10 days
**Prerequisites:** Phase 10B (handlers partition) recommended. 13B before 13C.

### Agent 13A: MCP 2026 Compliance (PRD 024)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are upgrading poor-cli's MCP integration to the 2026 spec — Streamable HTTP plus
stdio, multi-server support, and optional registry pull.

FIRST: Read docs/phase_13_protocol_streaming.md, specifically the "Agent 13A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Relocate to a `poor-cli/mcp/` package; stdio and Streamable HTTP transports
- Multi-server with tool namespacing: `<server>:<tool>`
- Discovery from `.poor-cli/mcp.json` (array of server specs)
- Optional pull from `https://registry.modelcontextprotocol.io/`, behind a config flag

YOUR DELIVERABLES:
1. Create `poor-cli/mcp/{stdio,http,registry}.py` replacing `mcp_scaffold.py`
2. Implement multi-server orchestration with `<server>:<tool>` namespacing
3. Wire discovery from `.poor-cli/mcp.json`
4. Add registry pull behind `mcp.registry.enabled = false` default
5. Write tests with a mock HTTP server and a mock stdio server

CONSTRAINTS:
- Do NOT break existing stdio users silently — migrate configs cleanly
- Registry pull is OFF by default; document how to enable
- [CUSTOMIZE: your required MCP servers for QA]

Read the phase doc and PRD first, then implement.
```

### Agent 13B: Streaming Tool Output (PRD 025)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are streaming long-running tool output chunks to the server pubsub, forwarding to
the Lua client, and rendering progressively in the Agent Timeline.

FIRST: Read docs/phase_13_protocol_streaming.md, specifically the "Agent 13B" section for
full implementation details and acceptance criteria.

CONTEXT:
- Targets: bash, run_tests, process_logs — the tools that produce large/slow output
- Model still sees completed output (or a summarized head if over size budget)
- Client is the Agent Timeline buffer (PRD 015) — append-as-you-go rendering
- Backpressure: client acknowledges chunks; server pauses producers on pressure

YOUR DELIVERABLES:
1. Add `poor-cli/server/tool_stream.py` with chunked pub/sub + backpressure
2. Hook supported tools to emit streaming chunks
3. Extend the RPC protocol with `tool.chunk` notifications
4. Update `nvim-poor-cli/lua/poor-cli/timeline.lua` to render chunks in order
5. Write tests for flow control, drop-on-disconnect, and final-output correctness

CONSTRAINTS:
- Do NOT stream to the LLM mid-call — model sees the final output only
- Do NOT stream every tool — gate by a schema flag
- [CUSTOMIZE: extra tools in your fork that should stream]

Read the phase doc and PRD first, then implement.
```

### Agent 13C: RTK-Lite Shell Filter (PRD 026)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding a Python-only post-processing filter for a handful of high-signal shell
commands (`git status`, `git diff --stat`, `ls -la` first; stretch: npm/cargo).

FIRST: Read docs/phase_13_protocol_streaming.md, specifically the "Agent 13C" section for
full implementation details and acceptance criteria.

CONTEXT:
- This is NOT RTK the Rust binary — Python-only, no Rust dependency
- Recognize the command by its argv; dispatch a purpose-built filter
- Composes with streaming (PRD 025) — filter after completion, not mid-stream
- Savings must flow into the economy + Savings dashboard

YOUR DELIVERABLES:
1. Add `poor-cli/shell_filters/` with one module per supported command
2. Plug the filter into the bash tool post-execution
3. Preserve a "full" view path in the timeline for auditing
4. Ship `git status`, `git diff --stat`, `ls -la` filters with tests
5. Stretch: implement `npm install` and `cargo build` filters

CONSTRAINTS:
- Python only — no Rust binary in this PRD
- Do NOT hook shell aliases
- Filter must be a no-op when output is already tiny
- [CUSTOMIZE: extra commands you want filtered]

Read the phase doc and PRD first, then implement.
```

---

## Phase 14: Nvim Observability Panels

**Agents: 6 (serialize dispatch-touching agents, parallel bodies)**
**Reference document:** `docs/phase_14_nvim_observability.md`
**Estimated time per agent:** 2-6 days
**Prerequisites:** Phase 10A (orchestrator) for 14D. PRD 065 (Lua test infra) alongside.

Because multiple agents touch `nvim-poor-cli/lua/poor-cli/commands.lua` and
`chat.lua`, serialize the command-dispatch edits (14A → 14B → 14C → 14D → 14E → 14F)
while the per-panel Lua bodies can be developed in parallel branches.

### Agent 14A: Diff Review Panel (PRD 014)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Diff Review panel — proposed edits are staged, surfaced hunk by
hunk, and the user accepts/rejects/regenerates per hunk.

FIRST: Read docs/phase_14_nvim_observability.md, specifically the "Agent 14A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Today edits auto-apply; this PRD stages them behind a review UI
- One checkpoint per accepted batch, labeled with the triggering prompt
- A config switch keeps legacy auto-apply behavior for power users
- Do NOT replace the checkpoint system — integrate

YOUR DELIVERABLES:
1. Add `nvim-poor-cli/lua/poor-cli/diff_review.lua` with hunk-level keymaps
2. Server-side: stage edits in a proposal store; expose `diff.list/accept/reject/regen`
3. Register `:PoorCLIDiffReview` and dispatch from commands.lua (serial edit)
4. Wire checkpoint creation on accept-batch
5. Write Lua tests for keymaps; Python tests for the proposal store

CONSTRAINTS:
- Single-source diff (agent proposal vs current file); no three-way merge
- Do NOT replace existing checkpoints
- Legacy auto-apply stays available via config toggle
- [CUSTOMIZE: your preferred accept/reject keymaps]

Read the phase doc and PRD first, then implement.
```

### Agent 14B: Agent Timeline Panel (PRD 015)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the live Agent Timeline panel showing every tool call in the current
and previous turns — with cancel, retry, and dismiss actions.

FIRST: Read docs/phase_14_nvim_observability.md, specifically the "Agent 14B" section for
full implementation details and acceptance criteria.

CONTEXT:
- Columns/fields: tool name, first-line args, status, duration, expandable result
- Status lifecycle: pending → running → done | failed | cancelled
- Dismissed output is removed from the model's context for the next turn
- Pairs with PRD 025 streaming for progressive render

YOUR DELIVERABLES:
1. Add `nvim-poor-cli/lua/poor-cli/timeline.lua` with scrolling + expand/collapse
2. Server: `timeline.list/cancel/retry/dismiss` RPC methods
3. Register `:PoorCLITimeline` via commands.lua (serial edit, after 14A)
4. Wire streaming chunks (PRD 025) to append under the active event
5. Write tests for state transitions + dismiss-from-context propagation

CONSTRAINTS:
- Do NOT redesign the agent loop
- Do NOT introduce distributed tracing
- Keep the panel resilient to disconnect/resume
- [CUSTOMIZE: preferred timeline column widths]

Read the phase doc and PRD first, then implement.
```

### Agent 14C: Cost HUD (PRD 016)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are shipping the three-layer Cost HUD: lualine segment, per-message badge, and
`:PoorCLICostDashboard` rich buffer.

FIRST: Read docs/phase_14_nvim_observability.md, specifically the "Agent 14C" section for
full implementation details and acceptance criteria.

CONTEXT:
- Lualine segment: `$0.42 · Δ$0.03 · cache 62%` (session $, turn delta, cache hit rate)
- Per-message virtual-text badges: `[$0.02 · 1.4s · 312 tok]`
- Dashboard: sparkline $/turn, top-10 expensive tools, cache stats, $/month projection
- Reads from `poor-cli/cost.py` via RPC

YOUR DELIVERABLES:
1. Extend `nvim-poor-cli/lua/poor-cli/lualine.lua` with the HUD segment
2. Add chat virtual-text badges (coordinate with PRD 047)
3. Build `:PoorCLICostDashboard` rich buffer
4. Add `cost.snapshot/history` RPC methods
5. Write Lua tests for rendering + cost deltas

CONSTRAINTS:
- Do NOT alter the cost model itself — present only
- Keep the lualine segment under ~30 chars
- Register the command via commands.lua (serial after 14B)
- [CUSTOMIZE: your lualine theme]

Read the phase doc and PRD first, then implement.
```

### Agent 14D: Context Explainer Panel (PRD 029)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the Context Explainer panel — a right-split listing every file in the
current `ContextSnapshot` with reason, tokens, and pin/drop actions.

FIRST: Read docs/phase_14_nvim_observability.md, specifically the "Agent 14D" section for
full implementation details and acceptance criteria.

CONTEXT:
- Reads `ContextSnapshot` produced by PRD 018
- Columns: path, tokens, reason (pagerank-hub / recent-open / imported-by-target / pinned),
  compressed?, pinned?
- Actions: `p` pin/unpin, `d` drop, `r` refresh, `/` filter, `o` open

YOUR DELIVERABLES:
1. Add `:PoorCLIContext` panel in `nvim-poor-cli/lua/poor-cli/context_panel.lua`
2. Server: `context.snapshot/pin/drop/refresh` RPC methods
3. Register the command via commands.lua (serial after 14C)
4. Render compressed/pinned badges per row
5. Write tests for RPC roundtrips and keymap dispatch

CONSTRAINTS:
- Do NOT mutate the selection heuristics
- Panel must be read-mostly — only pin/drop mutate
- [CUSTOMIZE: initial column ordering]

Read the phase doc and PRD first, then implement.
```

### Agent 14E: Savings Dashboard (PRD 041)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the Savings Dashboard — estimated savings per source (compaction, prompt
caching, semantic cache, RTK, model downshift) with deltas and 30-day sparkline.

FIRST: Read docs/phase_14_nvim_observability.md, specifically the "Agent 14E" section for
full implementation details and acceptance criteria.

CONTEXT:
- Complement to PRD 016 Cost HUD — Savings focuses on what you did NOT spend
- Data sources: PRD 027 (block caching), PRD 004 (semantic), PRD 026 (RTK-lite), 12F (pretok)
- Persist 30-day history in SQLite alongside cost
- Do NOT compete with cost dashboard — link cross-navigation

YOUR DELIVERABLES:
1. Add `:PoorCLISavings` rich buffer with per-source breakdown
2. Server: `savings.snapshot/history` RPC methods
3. Sparkline of 30-day savings total; list of top contributors per week
4. Register command via commands.lua (serial after 14D)
5. Write tests for aggregation + rollup correctness

CONSTRAINTS:
- Savings are estimates — label the methodology per source
- Sparkline must degrade gracefully when <30 days of history
- [CUSTOMIZE: preferred source ordering]

Read the phase doc and PRD first, then implement.
```

### Agent 14F: Watch Status Panel (PRD 042)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the Watch Status panel — active watches (paths, last change, matched
ignore patterns), QA toggle status, and last N triggered actions + outcomes.

FIRST: Read docs/phase_14_nvim_observability.md, specifically the "Agent 14F" section for
full implementation details and acceptance criteria.

CONTEXT:
- Reads from the consolidated FileWatcher (PRD 005)
- Also shows QA toggle (AI-triggered test runs) and action history
- Per-row keymap to open the target file or re-run the action
- Small panel — a few dozen lines of Lua + one RPC method

YOUR DELIVERABLES:
1. Add `:PoorCLIWatch` panel in `nvim-poor-cli/lua/poor-cli/watch_panel.lua`
2. Server: `watch.status` RPC method returning active watches + recent triggers
3. Register command via commands.lua (serial after 14E)
4. Show matched-but-ignored events in a muted color
5. Write Lua tests for rendering and RPC shape

CONSTRAINTS:
- Read-only panel — no watch mutation from here
- Do NOT subscribe to every file event — pull status on demand
- [CUSTOMIZE: the "last N" cap for action history]

Read the phase doc and PRD first, then implement.
```

---

## Phase 15: Nvim Navigator Panels

**Agents: 7 (three sub-waves)**
**Reference document:** `docs/phase_15_nvim_navigators.md`
**Estimated time per agent:** 3-7 days
**Prerequisites:** PRD 055 (picker adapter) for 15B/15C/15D; PRD 063 decision for 15E.

**Sub-wave 15.1 (parallel):** 15A, 15F, 15G.
**Sub-wave 15.2 (parallel, after PRD 055):** 15B, 15C, 15D.
**Sub-wave 15.3 (after PRD 063):** 15E.

### Agent 15A: Plan Board Kanban (PRD 031)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Plan Board — a kanban-style buffer (four columns as extmarks)
showing the current plan's steps with Tab/S-Tab advancement.

FIRST: Read docs/phase_15_nvim_navigators.md, specifically the "Agent 15A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Steps are produced by poor-cli's plan mode
- Keymaps: `<Tab>` advance, `<S-Tab>` regress, `<CR>` expand, `x` block, `a` add, `d` delete
- Server tracks plan state; buffer is a view with mutations via RPC
- Do NOT auto-infer dependencies (user-authored ordering only)

YOUR DELIVERABLES:
1. Add `:PoorCLIPlan` buffer in `nvim-poor-cli/lua/poor-cli/plan_board.lua`
2. Server: `plan.list/advance/regress/add/delete` RPC methods
3. Render columns as extmarks; support expand/collapse
4. Persist plan state across sessions
5. Write tests for transitions and persistence

CONSTRAINTS:
- Do NOT hide step history — blocked + done stay visible
- Keep columns fixed at four (Todo / Doing / Blocked / Done)
- [CUSTOMIZE: preferred column titles]

Read the phase doc and PRD first, then implement.
```

### Agent 15B: Prompt Library Picker (PRD 032)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Prompt Library picker — a picker (via PRD 055 adapter) listing
saved prompts with preview; `<CR>` runs, `e` edits, `d` deletes, `<C-n>` clones.

FIRST: Read docs/phase_15_nvim_navigators.md, specifically the "Agent 15B" section for
full implementation details and acceptance criteria.

CONTEXT:
- Depends on PRD 055 picker adapter being live
- Prompts live under `.poor-cli/prompts/*.md` with front-matter metadata
- Preview pane renders markdown; delete asks for confirmation
- Small, surgical addition — reuse adapter for all list/preview UI

YOUR DELIVERABLES:
1. Add `:PoorCLIPrompts` command using `pickers.pick()` from PRD 055
2. Build prompt loader + front-matter parser
3. Implement run / edit / delete / clone actions
4. Support live fuzzy search against title + tags
5. Write tests for parser + action dispatch

CONSTRAINTS:
- Do NOT implement a picker yourself — always go through the adapter
- Confirm-before-delete is mandatory
- [CUSTOMIZE: your prompt directory override]

Read the phase doc and PRD first, then implement.
```

### Agent 15C: Workflow Starter Picker (PRD 033)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Workflow Starter picker — templates with preview; `<CR>` runs,
`s` opens a scaffold for customization; tags by category (time/git/ci/refactor).

FIRST: Read docs/phase_15_nvim_navigators.md, specifically the "Agent 15C" section for
full implementation details and acceptance criteria.

CONTEXT:
- Depends on PRD 055 adapter and the consolidated extension model (PRD 064)
- Templates are small YAML files; category tag is the top-level grouping
- Scaffold action opens the template source in a scratch buffer for user edits
- Coordinate with PRD 064 if the unified shape changes field names

YOUR DELIVERABLES:
1. Add `:PoorCLIWorkflows` command using `pickers.pick()` from PRD 055
2. Load slash-trigger AutomationRules from `.poor-cli/automations.json`
3. Implement run + scaffold actions
4. Group picker results by category; allow tag filters
5. Write tests for loader + dispatch

CONSTRAINTS:
- Respect the shape decided in PRD 064 (AutomationRule or similar)
- Do NOT auto-run on selection — confirm for destructive workflows
- [CUSTOMIZE: user-specific categories]

Read the phase doc and PRD first, then implement.
```

### Agent 15D: MCP Registry Browser (PRD 035)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the MCP Registry browser — full-screen buffer listing configured
servers with status, tool count, last error, plus a paginated official registry browser.

FIRST: Read docs/phase_15_nvim_navigators.md, specifically the "Agent 15D" section for
full implementation details and acceptance criteria.

CONTEXT:
- Depends on PRD 024 (MCP 2026) registry support
- Depends on PRD 055 picker for the registry pagination UX
- Actions: toggle enable, edit spec, remove, health-check, test tool call
- Do NOT ship a thin wrapper around `mcphub.nvim` — keep ours native

YOUR DELIVERABLES:
1. Add `:PoorCLIMcp` buffer + browser flow
2. Reuse PRD 055 picker for registry pagination
3. Server: `mcp.list/toggle/edit/remove/health/test` RPC methods
4. Render per-server status column with colored badges
5. Write Lua tests for rendering + Python tests for the RPC surface

CONSTRAINTS:
- Registry pull stays off by default (inherit PRD 024 gate)
- Destructive actions require confirmation
- [CUSTOMIZE: preferred default MCP servers]

Read the phase doc and PRD first, then implement.
```

### Agent 15E: Multiplayer Room Full-Screen (PRD 037)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Multiplayer Room full-screen buffer — room name + invite link,
members with roles, driver indicator + `[Pass driver]`.

FIRST: Read docs/phase_15_nvim_navigators.md, specifically the "Agent 15E" section for
full implementation details and acceptance criteria.

CONTEXT:
- GATED by PRD 063 DECISION — only build if (A) "Commit" is chosen
- Tab-scoped full-screen buffer; copy-to-clipboard for invite link
- Member list with roles (owner / prompter / viewer)
- Pass-driver flow requires server-side state machine (see PRD 019 handlers)

YOUR DELIVERABLES:
1. Add `:PoorCLICollab` buffer gated behind `multiplayer.enabled`
2. Server: `collab.room/members/pass_driver` RPC methods
3. Clipboard integration for invite link
4. Live updates via pub/sub as members join/leave
5. Write tests covering driver transitions + join/leave events

CONSTRAINTS:
- Do NOT build this unless PRD 063 chose option (A) Commit
- Role changes always audit-log (PRD 011 integration)
- [CUSTOMIZE: invite link domain / protocol]

Read the phase doc and PRD first, then implement.
```

### Agent 15F: Repo Map Visualizer (PRD 038)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Repo Map visualizer — an ASCII tree-like view of top-N PageRank
files, their import neighborhoods, and tree-sitter-derived symbols.

FIRST: Read docs/phase_15_nvim_navigators.md, specifically the "Agent 15F" section for
full implementation details and acceptance criteria.

CONTEXT:
- Reads from `poor-cli/repo_graph.py`
- Keymaps: `<CR>` open file, `gl` expand imports, `gs` list symbols
- Terminal-native ASCII — no canvas / graph visualization
- Plays well with PRD 029 context explainer (share file-reason helpers)

YOUR DELIVERABLES:
1. Add `:PoorCLIRepoMap` buffer in `nvim-poor-cli/lua/poor-cli/repo_map.lua`
2. Server: `repo_map.top/expand/symbols` RPC methods
3. Render tree with Unicode box-drawing chars; collapse deep branches
4. Wire the three keymaps to their actions
5. Write tests for rendering determinism and symbol extraction

CONSTRAINTS:
- ASCII / terminal only — no external graphing dep
- Respect a top-N cap (default 50) to stay responsive
- [CUSTOMIZE: the top-N value]

Read the phase doc and PRD first, then implement.
```

### Agent 15G: Conversation Branch Tree (PRD 039)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Conversation Branch Tree — history as a DAG where regenerate
creates a sibling; right-split tree view with `[[`/`]]` navigation and `<CR>` switch.

FIRST: Read docs/phase_15_nvim_navigators.md, specifically the "Agent 15G" section for
full implementation details and acceptance criteria.

CONTEXT:
- Pairs with PRD 043 (backend regenerate-as-sibling plumbing)
- This PRD ships the VIEW; 043 ships the backend — coordinate carefully
- Tree persists with the session; active branch drives subsequent turns
- No branch merging in scope

YOUR DELIVERABLES:
1. Add `:PoorCLIBranches` panel in `nvim-poor-cli/lua/poor-cli/branches.lua`
2. Server: `branches.tree/switch` RPC methods (PRD 043 adds regenerate)
3. Render tree as indented list; highlight active branch
4. Sibling-nav keymaps `[[`/`]]` and switch keymap `<CR>`
5. Write tests for tree render + switch action

CONSTRAINTS:
- Do NOT merge branches — out of scope
- Switching must cleanly restore the snapshot for that branch
- [CUSTOMIZE: max siblings displayed before collapsing]

Read the phase doc and PRD first, then implement.
```

---

## Phase 16: Nvim Pickers & Onboarding

**Agents: 3 (two sub-waves)**
**Reference document:** `docs/phase_16_pickers_onboarding.md`
**Estimated time per agent:** 2-6 days
**Prerequisites:** None blocking for 16B/16C; 16A requires 16C.

**Sub-wave 16.1 (parallel):** 16C, 16B.
**Sub-wave 16.2 (after 16C):** 16A.

### Agent 16A: Provider/Model Picker Modal (PRD 030)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Provider / Model Picker modal — via PRD 055 adapter — listing
providers → models with capability icons and $$/1K indicators.

FIRST: Read docs/phase_16_pickers_onboarding.md, specifically the "Agent 16A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Icons: streaming, thinking, caching, vision; costs from a static table + overrides
- Capability discovery comes from `ProviderCapability` enum (PRD 020)
- Selecting switches both provider and model atomically
- Depends on PRD 055 (picker adapter) having shipped

YOUR DELIVERABLES:
1. Add `:PoorCLISwitch` command using `pickers.pick()` from PRD 055
2. Render capability icons + $$/1K columns
3. Wire selection into existing provider/model switch RPC
4. Persist last-used per project for fast re-open
5. Write tests covering capability rendering + selection dispatch

CONSTRAINTS:
- Capability source is the enum — do not hard-code lists
- Cost figures must be overridable by user config
- [CUSTOMIZE: your cost override table]

Read the phase doc and PRD first, then implement.
```

### Agent 16B: Onboarding Rerun + Tour (PRD 040)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing onboarding re-run, milestone tips, and an interactive 2-minute tour
(provider → prompt → diff review → checkpoint → rollback).

FIRST: Read docs/phase_16_pickers_onboarding.md, specifically the "Agent 16B" section for
full implementation details and acceptance criteria.

CONTEXT:
- `:PoorCLIOnboarding` must re-open any time (not once-and-done)
- Milestone tips fire at N completions / M turns, one tip at a time
- Tour guides through five real actions with fake-but-safe targets
- Coordinate with PRD 014 (diff review) for the review step

YOUR DELIVERABLES:
1. Add `:PoorCLIOnboarding` rerunnable command in `nvim-poor-cli/lua/poor-cli/onboarding.lua`
2. Implement milestone tip scheduler with rate-limiting
3. Build the 5-step interactive tour with guided actions
4. Persist "seen" flags per tip in the user state file
5. Write tests for milestone triggers + tour progression

CONSTRAINTS:
- Never block startup on onboarding — always opt-in
- Milestone tips must respect a global "do not nag" flag
- [CUSTOMIZE: your preferred milestone thresholds]

Read the phase doc and PRD first, then implement.
```

### Agent 16C: Picker Adapter Layer (PRD 055)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the picker adapter layer — one API `pickers.pick(items, opts)` that
detects Snacks > Telescope > fzf-lua > vim.ui.select and routes accordingly.

FIRST: Read docs/phase_16_pickers_onboarding.md, specifically the "Agent 16C" section for
full implementation details and acceptance criteria.

CONTEXT:
- Foundational for PRDs 030, 032, 033, 035, 046
- Detect backend at runtime; cache detection result per session
- `opts` accepts `preview`, `layout`, `multi`, `keys` — mapped to each backend
- Never implement a picker ourselves — only route

YOUR DELIVERABLES:
1. Add `nvim-poor-cli/lua/poor-cli/pickers.lua` with `pick(items, opts)`
2. Implement Snacks, Telescope, fzf-lua, and vim.ui.select adapters
3. Document the opts contract in the module header
4. Surface which backend is active via `:PoorCLIPickerBackend`
5. Write Lua tests with fake adapters for each backend

CONSTRAINTS:
- Do NOT introduce a picker — route only
- Graceful fallback if the chosen backend errors
- [CUSTOMIZE: preferred backend precedence]

Read the phase doc and PRD first, then implement.
```

---

## Phase 17: Chat Interactions

**Agents: 5 (strictly sequential)**
**Reference document:** `docs/phase_17_chat_interactions.md`
**Estimated time per agent:** 2-6 days
**Prerequisites:** Chain: 17A → 17B → 17C → 17D → 17E.

All five agents touch `nvim-poor-cli/lua/poor-cli/chat.lua` — do not parallelize.

### Agent 17A: Chat Regenerate + Branch Backend (PRD 043)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are shipping the BACKEND plumbing for `<leader>rr` regenerate — creating a sibling
branch; `[[`/`]]` navigation. The tree VIEW is PRD 039.

FIRST: Read docs/phase_17_chat_interactions.md, specifically the "Agent 17A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Server must persist a DAG where each regenerate creates a sibling
- Active branch drives subsequent turns
- Coordinate with PRD 039 (the view) on shared tree schema
- Keymaps are chat-local — live in `chat.lua`

YOUR DELIVERABLES:
1. Extend server history store to a DAG (nodes + parent refs)
2. Add `chat.regenerate/switch/siblings` RPC methods
3. Wire `<leader>rr`, `[[`, `]]` in `chat.lua`
4. Migrate existing linear histories into single-chain DAGs on load
5. Write tests for regenerate shape + switch correctness

CONSTRAINTS:
- Do NOT implement the tree view here (PRD 039)
- Migration must be idempotent
- [CUSTOMIZE: regenerate temperature bump default]

Read the phase doc and PRD first, then implement.
```

### Agent 17B: Chat Codeblock Actions (PRD 044)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding cursor-on-fenced-codeblock actions: `yc` yank, `<leader>ya` apply,
`<leader>yl` open-in-scratch.

FIRST: Read docs/phase_17_chat_interactions.md, specifically the "Agent 17B" section for
full implementation details and acceptance criteria.

CONTEXT:
- Uses tree-sitter to detect fenced code blocks in `chat.lua`
- Apply routes through Diff Review panel (PRD 014) if available; else direct write
- Scratch buffer inherits the block's filetype
- Do NOT collide with 17A keymaps — coordinate

YOUR DELIVERABLES:
1. Detect block under cursor via tree-sitter markdown
2. Implement `yc`, `<leader>ya`, `<leader>yl` keymaps in `chat.lua`
3. Integrate apply path with PRD 014 when present
4. Confirm-on-write for `<leader>ya` when diff review is unavailable
5. Write Lua tests with fixture chats in several filetypes

CONSTRAINTS:
- Never write a file silently without confirmation
- Respect the Diff Review toggle when it is enabled
- [CUSTOMIZE: additional keymaps you want]

Read the phase doc and PRD first, then implement.
```

### Agent 17C: Chat Slash Autocomplete (PRD 045)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding slash-command autocomplete in the chat input — typing `/` opens a picker
popup with fuzzy match on name + 1-line description.

FIRST: Read docs/phase_17_chat_interactions.md, specifically the "Agent 17C" section for
full implementation details and acceptance criteria.

CONTEXT:
- Reflect, not replace, the existing command list (source of truth server-side)
- Use the PRD 055 picker adapter for the popup
- Must tolerate mid-word `/` insertions without spamming the UI
- Coordinate with 17B — keymaps live in the same file

YOUR DELIVERABLES:
1. Detect `/` at input start; trigger picker via `pickers.pick()`
2. Fetch command list via `commands.list` RPC
3. Insert the command name into the input on selection
4. Show per-command description in the picker preview
5. Write Lua tests with a fake picker backend

CONSTRAINTS:
- Do NOT hardcode the command list in Lua
- Dismissable with `<Esc>` — never block normal typing
- [CUSTOMIZE: trigger character if you prefer `:` instead]

Read the phase doc and PRD first, then implement.
```

### Agent 17D: Chat Mention Picker (PRD 046)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding `@`-mention picker in chat input with sources: `@file:`, `@buffer:`,
`@lsp:`. More sources may come later (oil via PRD 053).

FIRST: Read docs/phase_17_chat_interactions.md, specifically the "Agent 17D" section for
full implementation details and acceptance criteria.

CONTEXT:
- Uses PRD 055 picker adapter
- `@file:` → files in repo (respect .gitignore); `@buffer:` → open buffers; `@lsp:` → current buffer's LSP diagnostics
- On selection, insert a resolvable mention token; server resolves to content on send
- Forward-compatible with PRD 053 (`@oil:`) — expose a registration API

YOUR DELIVERABLES:
1. Detect `@<source>:` at cursor; open picker for that source
2. Implement file / buffer / lsp source providers in Lua
3. Server-side: accept mention tokens, resolve at send-time
4. Expose `register_source(name, provider)` for future sources
5. Write tests for each source + token resolution

CONSTRAINTS:
- Do NOT resolve mentions client-side into file content (tokens stay compact)
- Respect .gitignore in file source
- [CUSTOMIZE: custom sources]

Read the phase doc and PRD first, then implement.
```

### Agent 17E: Chat Polish Bundle (PRD 047)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the chat polish bundle — `<leader>ee` edit+resend, per-turn cost
virtual-text badge, `<leader>ex` export (md/json/transcript).

FIRST: Read docs/phase_17_chat_interactions.md, specifically the "Agent 17E" section for
full implementation details and acceptance criteria.

CONTEXT:
- Per-turn badge overlaps with PRD 016 HUD — share the formatter, keep chat-local
- Edit-and-resend forks history (ties into PRD 043 DAG)
- Export writes to `.poor-cli/exports/` — respect user directory override
- Final agent in the chat chain — land last

YOUR DELIVERABLES:
1. Add `<leader>ee` edit-and-resend keymap in `chat.lua`
2. Render per-turn badge via virtual text using shared cost formatter
3. Implement `<leader>ex` exporter with md / json / transcript writers
4. Add an export picker (via PRD 055) for format selection
5. Write tests for each exporter + edit-resend fork

CONSTRAINTS:
- Do NOT duplicate the cost formatter — import from PRD 016's helper
- Export path must be configurable and mkdir-if-missing
- [CUSTOMIZE: default export format]

Read the phase doc and PRD first, then implement.
```

---

## Phase 18: Inline Suggestion Polish

**Agents: 2 (sequential)**
**Reference document:** `docs/phase_18_inline_polish.md`
**Estimated time per agent:** 2-5 days
**Prerequisites:** 18A before 18B.

### Agent 18A: Inline Accept-Line + Preview Split (PRD 048)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding `<M-l>` to accept the next line (up to and including `\n`) of ghost text,
and `<M-?>` to open a preview split with the full completion syntax-highlighted.

FIRST: Read docs/phase_18_inline_polish.md, specifically the "Agent 18A" section for full
implementation details and acceptance criteria.

CONTEXT:
- Inline suggestions live in `nvim-poor-cli/lua/poor-cli/inline.lua`
- Today, accept-all is `<M-\>` (or similar); this PRD adds finer control
- Preview split uses a scratch buffer with the source file's filetype
- Must not interfere with existing accept-all keymap

YOUR DELIVERABLES:
1. Implement `<M-l>` accept-next-line keymap
2. Implement `<M-?>` preview-split keymap with syntax highlighting
3. Track partial-accept progress so additional `<M-l>` presses advance
4. Update the help buffer to document the new keymaps
5. Write Lua tests for both keymaps

CONSTRAINTS:
- Do NOT break existing inline accept flow
- Preview split must auto-close on suggestion dismissal
- [CUSTOMIZE: preferred keymaps if modifiers clash]

Read the phase doc and PRD first, then implement.
```

### Agent 18B: Inline Cycle + Syntax-Region Filter (PRD 049)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding `<M-]>`/`<M-[>` cycle through N candidates and a client-side syntax-region
filter that skips auto-trigger inside comments / strings.

FIRST: Read docs/phase_18_inline_polish.md, specifically the "Agent 18B" section for full
implementation details and acceptance criteria.

CONTEXT:
- Server must support `n=3` candidate completions per request
- Tree-sitter detects cursor's node kind; skip auto-trigger for comment/string
- Manual `<C-Space>` always fires regardless of node kind
- Builds on 18A — share the inline state machine

YOUR DELIVERABLES:
1. Extend inline RPC with `n` candidates param; server returns an ordered list
2. Implement `<M-]>`/`<M-[>` cycle keymaps updating ghost text
3. Add tree-sitter-based auto-trigger filter with fallback when TS is unavailable
4. Cache last-cycled index for the session
5. Write Lua tests with fixture nodes in several filetypes

CONSTRAINTS:
- Manual trigger MUST bypass the filter
- Do NOT cache candidates across distinct cursor positions
- [CUSTOMIZE: your preferred candidate count]

Read the phase doc and PRD first, then implement.
```

---

## Phase 19: Plugin Integrations

**Agents: 7 (mostly parallel with coordination)**
**Reference document:** `docs/phase_19_plugin_integrations.md`
**Estimated time per agent:** 2-5 days
**Prerequisites:** None blocking.

Multiple agents touch `nvim-poor-cli/lua/poor-cli/commands.lua`,
`diagnostics.lua`, and `chat.lua` in an additive way — flag collisions to the
orchestrator but the edits are insert-only, so rebase conflicts are usually mechanical.

### Agent 19A: trouble.nvim Integration (PRD 050)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are registering a `poor-cli` source in trouble.nvim so `:Trouble poor-cli` lists all
current AI suggestions using the same namespace as `diagnostics.lua`.

FIRST: Read docs/phase_19_plugin_integrations.md, specifically the "Agent 19A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Detect trouble.nvim at runtime; no hard dependency
- Reuse the namespace used by `diagnostics.lua` to avoid duplicate entries
- Source implementation goes under `nvim-poor-cli/lua/poor-cli/integrations/trouble.lua`

YOUR DELIVERABLES:
1. Add `integrations/trouble.lua` registering the source
2. Bridge suggestion events into trouble's refresh hook
3. Guard init: no-op when trouble absent
4. Document the `:Trouble poor-cli` flow in README
5. Write Lua tests with a fake trouble API

CONSTRAINTS:
- No hard dep — runtime detect only
- Share the diagnostics namespace; do not invent a new one
- [CUSTOMIZE: preferred suggestion severity]

Read the phase doc and PRD first, then implement.
```

### Agent 19B: gitsigns AI-Hunks (PRD 051)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding a dim gutter icon on AI-authored hunks; attribution map clears on commit.

FIRST: Read docs/phase_19_plugin_integrations.md, specifically the "Agent 19B" section for
full implementation details and acceptance criteria.

CONTEXT:
- Track AI-authorship per-file per-session in memory
- Render via gitsigns' extmark sign stacking when gitsigns is present
- Clear the map on commit events (detect via gitsigns hook or git fswatch)
- Do NOT add git author metadata

YOUR DELIVERABLES:
1. Add `integrations/gitsigns.lua` with attribution tracker
2. Stack the `✱` sign on AI hunks; default dim highlight
3. Hook commit events to clear the map
4. Add a keymap to toggle display
5. Write Lua tests for track/clear/toggle

CONSTRAINTS:
- No hard dep on gitsigns
- Do NOT persist attribution across sessions
- [CUSTOMIZE: gutter icon glyph]

Read the phase doc and PRD first, then implement.
```

### Agent 19C: snacks.nvim Integration (PRD 052)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are routing non-error notifications through snacks.nvim (grouped as "poor-cli") and
adding a snacks dashboard tile showing session cost + active turns.

FIRST: Read docs/phase_19_plugin_integrations.md, specifically the "Agent 19C" section for
full implementation details and acceptance criteria.

CONTEXT:
- Detect snacks at runtime; fall back to `vim.notify`
- Notification helper should centralize calls (not scatter `vim.notify`s)
- Dashboard tile reads from cost snapshot RPC
- Error-level notifications bypass snacks (always `vim.notify`)

YOUR DELIVERABLES:
1. Add `nvim-poor-cli/lua/poor-cli/notify.lua` that auto-routes
2. Replace scattered `vim.notify` calls with the helper
3. Add a snacks dashboard tile module
4. Document configuration in README
5. Write Lua tests with a fake snacks API

CONSTRAINTS:
- Errors MUST stay on `vim.notify` regardless of snacks presence
- Do NOT hard-depend on snacks
- [CUSTOMIZE: notification group name]

Read the phase doc and PRD first, then implement.
```

### Agent 19D: oil.nvim File Mention (PRD 053)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding an `@oil:` mention source that opens oil.nvim in floating mode; `<CR>` on a
file inserts its path into the chat input.

FIRST: Read docs/phase_19_plugin_integrations.md, specifically the "Agent 19D" section for
full implementation details and acceptance criteria.

CONTEXT:
- Depends on PRD 046 mention picker's `register_source` API
- Detect oil at runtime; no hard dep
- Floating window is temporary — closes after path insertion

YOUR DELIVERABLES:
1. Add `integrations/oil.lua` registering `@oil:` via PRD 046 API
2. Open oil in floating mode on trigger
3. Capture `<CR>` to insert the path + close the float
4. Document the flow in README
5. Write Lua tests with a fake oil

CONSTRAINTS:
- No hard dep — runtime detect only
- Do NOT persist the floating window on cancel
- [CUSTOMIZE: preferred float dimensions]

Read the phase doc and PRD first, then implement.
```

### Agent 19E: overseer.nvim Long-Task Integration (PRD 054)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are registering an overseer Task for every long-running poor-cli task so status
mirrors into overseer and output streams via PRD 025 into overseer's output buffer.

FIRST: Read docs/phase_19_plugin_integrations.md, specifically the "Agent 19E" section for
full implementation details and acceptance criteria.

CONTEXT:
- Detect overseer at runtime; no hard dep
- Task lifecycle: start/running/success/failed mirror poor-cli tool state
- Output stream uses PRD 025's tool_stream pub/sub
- Do NOT run poor-cli tasks via overseer — only mirror

YOUR DELIVERABLES:
1. Add `integrations/overseer.lua` with mirror adapter
2. Subscribe to poor-cli task events; create Task per start
3. Pipe streaming chunks into overseer's output buffer
4. Handle cancel: overseer stop → poor-cli cancel
5. Write Lua tests with fake overseer API

CONSTRAINTS:
- Do NOT make overseer the execution engine
- Cancel propagation is bidirectional
- [CUSTOMIZE: which tasks to mirror if not all]

Read the phase doc and PRD first, then implement.
```

### Agent 19F: neogit Integration (PRD 056)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are integrating neogit — after `/commit`, if neogit is present and
`neogit.open_on_commit = true`, open neogit's status view, stage only the AI-touched files,
pre-fill the commit message from the agent's proposal.

FIRST: Read docs/phase_19_plugin_integrations.md, specifically the "Agent 19F" section for
full implementation details and acceptance criteria.

CONTEXT:
- Detect neogit at runtime; no hard dep
- AI-touched files list comes from the session's edit ledger (PRD 014 store)
- Proposed message comes from the agent turn that generated the commit

YOUR DELIVERABLES:
1. Add `integrations/neogit.lua` gated by config flag
2. Hook `/commit` slash command to the integration
3. Stage exactly the AI-touched files; pre-fill message
4. Gracefully no-op if neogit absent
5. Write Lua tests with fake neogit API

CONSTRAINTS:
- Do NOT hard-depend on neogit
- User can still edit the staged set before confirming
- [CUSTOMIZE: your commit-message template tweaks]

Read the phase doc and PRD first, then implement.
```

### Agent 19G: nvim-dap Integration (PRD 057)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are integrating nvim-dap — on a diagnostic or chat `file:line` reference,
`<leader>pb` sets a DAP breakpoint; optional `<leader>pB` launches DAP run.

FIRST: Read docs/phase_19_plugin_integrations.md, specifically the "Agent 19G" section for
full implementation details and acceptance criteria.

CONTEXT:
- Detect dap at runtime; no hard dep
- `file:line` references inside chat come from PRD 044 codeblock detection
- User's DAP config decides the debugger per language — we do not configure

YOUR DELIVERABLES:
1. Add `integrations/dap.lua` keymap dispatchers
2. Parse `file:line` refs from the cursor context (diag or chat)
3. Set breakpoints via dap API; optionally launch a run
4. Document supported contexts in README
5. Write Lua tests with a fake dap API

CONSTRAINTS:
- Do NOT configure debuggers — user owns dap config
- Fail gracefully when no debugger is configured
- [CUSTOMIZE: your preferred run-launch keymap]

Read the phase doc and PRD first, then implement.
```

---

## Phase 20: Strategic Decisions

**Agents: 4 (decision-gated)**
**Reference document:** `docs/phase_20_strategic_decisions.md`
**Estimated time per agent:** 1 day (archive path) to 3+ weeks (ship path)
**Prerequisites:** 20C (audience north-star) blocks 20A and 20D; 20B is independent.

### Agent 20A: Latent Communication — Ship or Archive (PRD 059)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the DECISION outcome on `research/latent_communication.py`: ship for
Ollama/vLLM gated by `ProviderCapability.LATENT_COMMUNICATION`, archive, or freeze.

FIRST: Read docs/phase_20_strategic_decisions.md, specifically the "Agent 20A" section for
the chosen decision and the implementation plan.

CONTEXT:
- GATED by PRD 062 (20C): audience decision informs the right option
- (a) Ship: 3+ weeks, wire into `sub_agent.py` + `parallel_agents.py`
- (b) Archive: delete file, update docs to state "ceased"
- (c) Freeze: keep as artifact, disable imports, update docs

YOUR DELIVERABLES:
1. Record the decision in the phase doc with rationale
2. Execute the chosen path (ship/archive/freeze) end-to-end
3. If ship: add capability enum value + sub_agent/parallel_agents wiring
4. If archive: delete + doc cleanup; capability enum stays absent
5. Update README + LONGTERM-TODO accordingly

CONSTRAINTS:
- Do NOT ship partially — either all the way or archive/freeze
- Audience decision (PRD 062) must be resolved first
- [CUSTOMIZE: option — (a/b/c) — is recorded here]

Read the phase doc and PRD first, then implement.
```

### Agent 20B: Project Rename — Decision (PRD 061)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the DECISION outcome on renaming the project (`poor-cli`).

FIRST: Read docs/phase_20_strategic_decisions.md, specifically the "Agent 20B" section for
the chosen decision and migration plan.

CONTEXT:
- (a) Rename — migrate pip package, GitHub repo, Neovim plugin, ~10K LoC references
- (b) Keep — zero migration cost; brand risk stays
- Independent of audience decision — can execute in parallel
- If rename chosen: set up legacy alias packages for one release

YOUR DELIVERABLES:
1. Record the decision in the phase doc
2. If rename: pick the new name, plan pip/github/nvim-plugin migration
3. If rename: add legacy alias package redirecting to the new name
4. Update docs, README, install instructions site-wide
5. If keep: record rationale so the question stops getting re-opened

CONSTRAINTS:
- A rename is a hard commit — do not half-migrate
- Legacy aliases stay for one release cycle minimum
- [CUSTOMIZE: the new name is recorded here]

Read the phase doc and PRD first, then implement.
```

### Agent 20C: Audience + North-Star Metric (PRD 062)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the DECISION on primary audience (hobbyists / researchers / small
teams) and the single north-star metric.

FIRST: Read docs/phase_20_strategic_decisions.md, specifically the "Agent 20C" section for
the chosen audience, metric, and the downstream implications.

CONTEXT:
- (A) Cost-conscious hobbyists, (B) Research-minded engineers, (C) Small engineering teams
- North-star examples: $ saved / month, SWE-bench score, pair-prog sessions / week
- Blocks PRD 059 (20A) and PRD 063 (20D)
- Marketing, docs, and roadmap prioritization all follow from this

YOUR DELIVERABLES:
1. Record the audience + metric + rationale in the phase doc
2. Audit existing features against the chosen audience; list mismatches
3. Update landing page + README to lead with the chosen audience
4. Add a `NORTH_STAR.md` doc describing the metric and measurement plan
5. Open follow-up issues for any feature that contradicts the audience

CONSTRAINTS:
- One audience, one metric — no "and also" caveats
- Document what was NOT chosen and why
- [CUSTOMIZE: audience letter + metric expression]

Read the phase doc and PRD first, then implement.
```

### Agent 20D: Multiplayer — Commit or Cut (PRD 063)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the DECISION on multiplayer: (A) Commit, (B) Cut, (C) Freeze.

FIRST: Read docs/phase_20_strategic_decisions.md, specifically the "Agent 20D" section for
the chosen decision and the execution plan.

CONTEXT:
- GATED by PRD 062 (20C): audience likely decides this
- (A) Commit: chat Share button, `:PoorCLICollabQuick`, demo video, landing section
- (B) Cut: move code to `_experimental/multiplayer/`, archive PRD 037
- (C) Freeze: keep, but no new investment
- PRD 037 (15E) depends on this decision

YOUR DELIVERABLES:
1. Record the decision in the phase doc
2. (A) Commit: add Share UI, quick invite, demo plan, landing copy
3. (B) Cut: relocate code, add deprecation notice, close/transform PRD 037
4. (C) Freeze: document the freeze and gate further feature work
5. Update README + marketing materials to match

CONSTRAINTS:
- Cut is destructive — get sign-off before deleting anything
- If Commit: the demo video is a gating deliverable
- [CUSTOMIZE: option — (A/B/C) — recorded here]

Read the phase doc and PRD first, then implement.
```

---

## Phase 21: Testing & Benchmarks

**Agents: 2 (fully parallel)**
**Reference document:** `docs/phase_21_testing_benchmarks.md`
**Estimated time per agent:** 1-2 weeks
**Prerequisites:** None; 21B pairs with any Lua-touching phase.

### Agent 21A: SWE-bench Lite Publish (PRD 060)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are running SWE-bench Lite (or Aider's edit benchmark) reproducibly and publishing
methodology + results + cost as a citable number.

FIRST: Read docs/phase_21_testing_benchmarks.md, specifically the "Agent 21A" section for
full implementation details and acceptance criteria.

CONTEXT:
- Reproducible means: pinned versions, pinned model, known seeds, documented costs
- Do NOT tune for the benchmark — publish the honest number
- Pair with the Savings Dashboard (PRD 041) for a cost story
- Results go in `docs/BENCHMARKS.md` and the landing page

YOUR DELIVERABLES:
1. Add `bench/swe_bench_lite/` runner with pinned versions
2. Capture full logs + token usage + dollar cost per task
3. Publish `docs/BENCHMARKS.md` with methodology, score, cost
4. Link from README + landing page
5. Add a `make bench-swe` target gated behind a cost warning

CONSTRAINTS:
- Do NOT ship benchmark-specific prompts or heuristics
- Cost warning must be explicit before the run starts
- [CUSTOMIZE: benchmark choice — SWE-bench Lite vs Aider edit bench]

Read the phase doc and PRD first, then implement.
```

### Agent 21B: Lua Testing Infrastructure (PRD 065)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are setting up Lua testing infrastructure (plenary.busted + CI) so every Lua-touching
PRD can ship with tests.

FIRST: Read docs/phase_21_testing_benchmarks.md, specifically the "Agent 21B" section for
full implementation details and acceptance criteria.

CONTEXT:
- plenary.nvim installed as a dev dep into a test-only Neovim runtime
- `nvim-poor-cli/tests/minimal_init.lua` bootstraps plenary
- `make test-lua` runs `PlenaryBustedDirectory` headless
- Integrate with the existing `.pre-commit-config.yaml` Lua syntax check

YOUR DELIVERABLES:
1. Provision a test-only Neovim runtime directory under `nvim-poor-cli/.test-runtime/`
2. Add `nvim-poor-cli/tests/minimal_init.lua` and directory scaffolding
3. Add `make test-lua` target running PlenaryBustedDirectory
4. Wire a CI job running `make test-lua` in matrix with the Python suite
5. Write a canary test so the CI job has something to verify

CONSTRAINTS:
- No Neovim config pollution — everything under the test runtime dir
- Fast: CI job budget ≤3 minutes
- [CUSTOMIZE: extra dev Lua deps if you use luarocks or rocks.nvim]

Read the phase doc and PRD first, then implement.
```

---

## Pain Point Coverage Matrix (Phases 9-21 additions)

The following additional mappings augment the original matrix. Phases 9-21 are primarily
product and architectural work, but several touch token-optimization pain points too.

| Pain Point | Additional Phase(s) |
|---|---|
| #1 Context accumulation | 12B, 12D, 12F |
| #2 Tool output bloat | 12E, 13C |
| #3 Codebase reading | 12B, 15F |
| #4 System prompt bloat | 12C |
| #6 Tool schema bloat | 13A |
| #13 Duplicate queries | 12D |
| #15 Non-prefix cache | 12D |
| #16 Static prompt redundancy | 12C, 12D |
| #19 Cache invalidation | 12A, 12D |

Non-token-optimization coverage (product posture): Phase 9 (cleanup), 10 (refactor), 11
(security/policy), 13 (protocol), 14-18 (UI), 19 (plugin ecosystem), 20 (strategic
decisions), 21 (benchmarks + test infra).
