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
- Shell tool execution lives in poor_cli/enhanced_tools.py
- Config system is in poor_cli/repo_config.py and nvim-poor-cli/lua/poor-cli/config.lua
- RTK is an external Rust binary (brew install rtk) that filters shell output

YOUR DELIVERABLES:
1. Create poor_cli/rtk_integration.py — RTK detection, command wrapping, tee-mode fallback
2. Modify poor_cli/enhanced_tools.py — integrate RTK wrapper in bash tool execution
3. Add rtk config fields to poor_cli/repo_config.py
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
- poor-cli's edit format logic lives in poor_cli/edit_formats.py
- Provider base class is poor_cli/providers/base.py
- The tool that applies edits is in poor_cli/enhanced_tools.py (edit_file tool)
- Multiple providers (Gemini, OpenAI, Anthropic, OpenRouter, Ollama) need format support

YOUR DELIVERABLES:
1. Audit poor_cli/edit_formats.py — document current format and identify waste
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
- Context optimization lives in poor_cli/context_optimizer.py
- Context contracts in poor_cli/context_contract.py
- Context providers in poor_cli/context_providers.py
- Economy modes (/broke, /my-treat) defined in poor_cli/profiles.py
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
- Economy modes defined in poor_cli/profiles.py
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
- poor-cli already has poor_cli/repo_graph.py — audit it first
- The /workspace-map command should use this enhanced map
- poor_cli/indexer.py handles code indexing — coordinate with this module
- poor_cli/context_providers.py injects context into prompts
- tree-sitter Python bindings: pip install tree-sitter tree-sitter-python tree-sitter-lua etc.

YOUR DELIVERABLES:
1. Audit poor_cli/repo_graph.py — document current capabilities
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
- Tool execution lives in poor_cli/enhanced_tools.py
- MCP client in poor_cli/mcp_scaffold.py
- GitHub tools in poor_cli/github_tools.py
- Cost tracking in poor_cli/cost.py

YOUR DELIVERABLES:
1. Create poor_cli/tool_output_filter.py — projection-based filtering + size-based auto-filter
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
- Provider implementations in poor_cli/providers/
- Provider base class: poor_cli/providers/base.py
- Context assembly in poor_cli/context_providers.py
- Cost tracking in poor_cli/cost.py / nvim-poor-cli/lua/poor-cli/cost.lua
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
- Instructions currently in poor_cli/instructions.py
- Skills system in poor_cli/skills.py
- System prompt assembled in the core engine
- /instructions command shows active instructions

YOUR DELIVERABLES:
1. Audit poor_cli/instructions.py — measure total instruction payload size
2. Break instructions into ≥8 discrete skill files in poor_cli/skills/ directory
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
- Tool definitions in poor_cli/command_manifest.py and poor_cli/enhanced_tools.py
- MCP tool schemas loaded in poor_cli/mcp_scaffold.py
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
- Conversation history in poor_cli/history.py
- Context optimization in poor_cli/context_optimizer.py
- Session management in poor_cli/session_manager.py

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
- Existing file cache: poor_cli/file_cache.py
- Embeddings: poor_cli/embeddings.py
- Provider base: poor_cli/providers/base.py
- Cost tracking: poor_cli/cost.py

YOUR DELIVERABLES:
1. Audit poor_cli/embeddings.py — determine available embedding infrastructure
2. Create poor_cli/semantic_cache.py — SQLite-backed cache with cosine similarity search
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
- Architect mode: poor_cli/architect_mode.py
- Profiles/economy: poor_cli/profiles.py
- Provider factory: poor_cli/providers/provider_factory.py
- Cost tracking: poor_cli/cost.py

YOUR DELIVERABLES:
1. Audit poor_cli/architect_mode.py — check for existing routing logic
2. Create poor_cli/model_router.py — complexity classifier + routing table
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
- Provider base: poor_cli/providers/base.py
- Edit formats: poor_cli/edit_formats.py
- Tool definitions: poor_cli/enhanced_tools.py
- Each provider has its own structured output API

YOUR DELIVERABLES:
1. Identify all structured output points (tool calls, edits, plan mode, JSON ops)
2. Create poor_cli/structured_output.py — JSON schemas for structured responses
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
- Context optimization: poor_cli/context_optimizer.py
- Profiles/economy: poor_cli/profiles.py
- pyproject.toml for dependencies

YOUR DELIVERABLES:
1. Create poor_cli/prompt_compressor.py — compression middleware
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
- Current indexer: poor_cli/indexer.py
- Embeddings: poor_cli/embeddings.py
- tree-sitter infrastructure from Phase 2A (may or may not be done yet)

YOUR DELIVERABLES:
1. Audit poor_cli/indexer.py — document current chunking strategy
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
- Error recovery: poor_cli/error_recovery.py
- Context optimization: poor_cli/context_optimizer.py
- History management: poor_cli/history.py

YOUR DELIVERABLES:
1. Create poor_cli/failure_amnesia.py — failure detection + lesson extraction + trace pruning
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
- Context providers: poor_cli/context_providers.py
- Session store: poor_cli/session_store.py
- Context optimizer: poor_cli/context_optimizer.py
- Memory: poor_cli/memory.py

YOUR DELIVERABLES:
1. Create poor_cli/working_memory.py — WorkingMemory model + delta computation
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
- Ollama provider: poor_cli/providers/ollama_provider.py
- LMCache (https://github.com/LMCache/LMCache) is the reference implementation

YOUR DELIVERABLES:
1. Research: confirm LMCache works with vLLM for position-independent caching
2. Research: check if Ollama exposes KV cache APIs
3. Create poor_cli/kv_cache_store.py — pre-compute, store, invalidate, assemble KV caches
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
- Economy/profiles: poor_cli/profiles.py
- Cost tracking: poor_cli/cost.py
- Phase 4B's model router (if built) provides the task complexity classifier

YOUR DELIVERABLES:
1. Create poor_cli/token_budget_controller.py — state observation + action selection
2. Create poor_cli/budget_logger.py — log (state, action, outcome) tuples
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
[AGENT PROMPT — copy/paste to your coding agent]

You are integrating speculative decoding for poor-cli's local inference path, pairing 
small draft models with main models to accelerate generation.

FIRST: Read docs/phase_07_adaptive_optimization.md, specifically the "Agent 7B" section 
for full implementation details and acceptance criteria.

IMPORTANT: This feature ONLY works with self-hosted inference (vLLM primarily).

CONTEXT:
- Ollama provider: poor_cli/providers/ollama_provider.py
- vLLM has native speculative decoding support
- Cost tracking: poor_cli/cost.py

YOUR DELIVERABLES:
1. Research: current Ollama speculative decoding support
2. Research: vLLM speculative decoding configuration
3. Create poor_cli/speculative_decoding.py — draft model pairing + metrics
4. Define DRAFT_MODEL_PAIRS mapping
5. Integrate with Ollama provider or document vLLM-only path
6. Track acceptance rate and speedup metrics
7. Gate behind feature flag + local inference detection
8. Write tests in tests/test_speculative_decoding.py

CONSTRAINTS:
- Off by default, gated behind local inference detection
- Draft model must be auto-detectable from DRAFT_MODEL_PAIRS
- No effect on closed API providers
- [CUSTOMIZE: list your local models for draft model pairing]

Read the phase doc first, then implement.
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
