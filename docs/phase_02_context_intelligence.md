# Phase 2: Context Intelligence — Smarter Input

**Priority:** High — 🟢 Easy solutions targeting how poor-cli reads and represents codebases and tool outputs.
**Estimated agents:** 3 (parallel)
**Dependencies:** None on Phase 1. Can run concurrently if enough agents available.
**Philosophy:** The cheapest token is one you never send. These solutions reduce what goes INTO context before the model sees it, attacking the input side (85-95% of session cost).

---

## Agent 2A: Tree-Sitter Repo Map with PageRank

**Pain points addressed:** #3 (codebase reading inefficiency — scales with repo size)
**Solution reference:** Solution #4 from SOLUTIONS.md
**Expected savings:** 50-80% reduction in tokens spent on codebase exploration

### What to build

Build an Aider-style repository map using tree-sitter for AST parsing and PageRank for importance scoring. The map provides a concise representation of the entire repo (classes, functions, signatures, dependency edges) so the model can navigate without reading full files.

### Implementation details

1. **Audit existing repo_graph.py** — poor-cli already has `poor_cli/repo_graph.py`. Read it thoroughly. Determine:
   - Does it already use tree-sitter?
   - Does it produce a ranked map of symbols?
   - What's the current output format?

2. **Tree-sitter integration** — use `tree-sitter` Python bindings (`tree-sitter` + language grammars):
   ```python
   # parse each file into AST, extract:
   # - function/method definitions (name, signature, line range)
   # - class definitions (name, methods, line range)
   # - import/require statements (dependency edges)
   # - module-level variables/constants
   ```

3. **Build dependency graph** — create a directed graph where:
   - Nodes = files or symbols (functions/classes)
   - Edges = dependency relationships (imports, function calls, class inheritance)
   - Use `networkx` or a simple adjacency list

4. **PageRank scoring** — run PageRank on the dependency graph:
   - Highly-referenced symbols rank higher
   - Entry points (main, __init__, index) get a rank boost
   - Recently modified files get a recency boost (from git log)

5. **Map format** — output a concise text map:
   ```
   poor_cli/core.py (rank: 0.12)
     class AgenticCore:
       async def run_agent_loop(self, prompt: str) -> str
       async def handle_tool_call(self, call: ToolCall) -> ToolResult
       def compact_context(self, target_ratio: float) -> None
     
   poor_cli/providers/base.py (rank: 0.09)
     class BaseProvider(ABC):
       async def complete(self, messages, tools) -> Response
       async def stream(self, messages, tools) -> AsyncIterator
   ```

6. **Token budget** — the map should fit within a configurable token budget (default: 2000 tokens). Truncate from lowest-ranked symbols upward.

7. **Integration with context system** — inject the repo map as part of the system context when the model needs to navigate the codebase. Key integration point: wherever poor-cli decides which files to include in context.

8. **Caching** — cache the repo map and invalidate on file changes (use git status or file watcher).

9. **Neovim command** — the existing `/workspace-map` command should use this enhanced map.

### Files to create/modify
- `poor_cli/repo_graph.py` (primary — enhance with tree-sitter + PageRank)
- `poor_cli/indexer.py` (may overlap — coordinate with chunking)
- `poor_cli/context_providers.py` (inject repo map into context)
- `requirements.txt` / `pyproject.toml` (add `tree-sitter` dependency if not present)

### Acceptance criteria
- [ ] Tree-sitter parses Python, Lua, JavaScript/TypeScript, Rust files
- [ ] Dependency graph built from imports/calls
- [ ] PageRank scores computed and used for ranking
- [ ] Map output fits within configurable token budget
- [ ] Map cached and invalidated on file changes
- [ ] `/workspace-map` uses the enhanced map
- [ ] Test: generate map for poor-cli itself, verify top-ranked symbols are core.py entry points

### References
- [Aider repo map](https://aider.chat/docs/repomap.html)
- [tree-sitter Python](https://github.com/tree-sitter/py-tree-sitter)
- [networkx PageRank](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.link_analysis.pagerank_alg.pagerank.html)

---

## Agent 2B: Schema-Aware Tool Output Filtering

**Pain points addressed:** #2 (tool/MCP output bloat — 5–50K tokens per call)
**Solution reference:** Solution #3 from SOLUTIONS.md
**Expected savings:** 70-90% reduction on bloated tool/MCP responses

### What to build

A middleware layer that sits between tool/MCP responses and the agent's context, filtering responses to include only the fields the agent actually needs. This is a **greenfield opportunity** — no standard implementation exists in the ecosystem.

### Implementation details

1. **Design the filtering interface** — before a tool call, the agent specifies what fields it needs:
   ```python
   class ToolCallWithProjection:
       tool_name: str
       arguments: dict
       projection: list[str] | None  # JSONPath-style field selectors
   ```

2. **Response filter middleware** — after tool execution, before injecting into context:
   ```python
   async def filter_tool_response(response: dict, projection: list[str] | None) -> dict:
       if projection is None:
           return response  # no filtering requested
       return extract_fields(response, projection)
   ```

3. **Built-in projection templates** — for common tools, define default projections:
   ```python
   DEFAULT_PROJECTIONS = {
       "gh_pr_list": ["number", "title", "state", "author.login", "updatedAt"],
       "gh_issue_view": ["number", "title", "body", "state", "labels[*].name"],
       "git_status": ["modified", "added", "deleted", "untracked"],
       "list_directory": ["name", "type", "size"],  # drop timestamps, permissions
   }
   ```

4. **MCP response filtering** — for MCP tool calls, apply filtering at the MCP client layer:
   - Read `poor_cli/mcp_scaffold.py` to find where MCP responses are received
   - Apply projection filter before returning to the agent loop

5. **Size-based auto-filtering** — if a tool response exceeds a threshold (e.g., 5000 tokens), auto-summarize:
   - First attempt: apply default projection template
   - If still too large: truncate with a "... (N more items, use tool again with specific query)" message
   - Log the savings for the cost dashboard

6. **User-configurable projections** — allow users to define custom projections in `.poor-cli/tool_projections.yaml`:
   ```yaml
   tool_projections:
     fetch_url:
       max_tokens: 2000
       extract: ["title", "body_text[:500]"]
     gh_pr_view:
       fields: ["number", "title", "body", "diff_stat"]
   ```

### Files to create/modify
- `poor_cli/tool_output_filter.py` (new, ~200 lines)
- `poor_cli/enhanced_tools.py` (integrate filter middleware in tool execution pipeline)
- `poor_cli/mcp_scaffold.py` (apply filtering to MCP responses)
- `.poor-cli/tool_projections.yaml` (example config)

### Acceptance criteria
- [ ] Projection-based filtering works for dict/JSON responses
- [ ] Default projections defined for built-in tools (gh, git, list_directory)
- [ ] MCP responses filtered before entering context
- [ ] Size-based auto-filtering for responses exceeding token threshold
- [ ] User-configurable projections via YAML config
- [ ] Cost dashboard shows tokens saved by filtering
- [ ] Test: mock a 40KB GitHub API response, verify filtered output < 1KB

### References
- JMESPath library for Python: `pip install jmespath`
- JSONPath spec for field selection patterns
- GraphQL field selection as design inspiration

---

## Agent 2C: Prompt Caching Optimization

**Pain points addressed:** #16 (static prompt redundancy), #4 (CLAUDE.md/system prompt bloat, partial)
**Solution reference:** Solution #1 from SOLUTIONS.md
**Expected savings:** Up to 90% cost reduction on cached prefixes (Anthropic), 50% (OpenAI)

### What to build

Optimize poor-cli's provider adapters to maximize prompt cache hit rates. This means structuring prompts so that the static prefix (system prompt, tool schemas, repo map) remains stable across turns, enabling provider-level caching.

### Implementation details

1. **Audit current prompt construction** — trace the code path from user message → provider API call. Identify:
   - Where is the system prompt assembled?
   - Are tool schemas injected into every request?
   - What order are context components assembled in?
   - Does the order change between turns? (This breaks prefix caching)

2. **Stabilize prompt prefix order** — ensure components are always assembled in this order:
   ```
   1. System prompt (static)
   2. Tool schemas (static per session)
   3. Repo map (changes rarely)
   4. CLAUDE.md / instructions (static)
   5. Pinned context files (changes on user action)
   6. Conversation history (grows each turn)
   7. Current user message (changes each turn)
   ```
   This order maximizes the cacheable prefix length.

3. **Anthropic-specific: explicit cache breakpoints** — use Anthropic's `cache_control` parameter:
   ```python
   messages = [
       {"role": "system", "content": system_prompt, "cache_control": {"type": "ephemeral"}},
       ...
   ]
   ```
   Mark the system prompt + tool schemas + repo map as cacheable.

4. **OpenAI-specific: automatic caching** — OpenAI caches automatically on prefix match. Ensure the prefix doesn't change unnecessarily between turns.

5. **Cache-aware logging** — log cache hit/miss rates per request so the cost dashboard can show cache savings:
   ```python
   # from Anthropic response headers
   cache_creation_input_tokens: int
   cache_read_input_tokens: int
   ```

6. **Avoid cache-busting** — identify and fix patterns that accidentally break the cache:
   - Timestamps in system prompts
   - Randomized tool ordering
   - Dynamic content injected before static content

### Files to create/modify
- Provider adapter files (in `poor_cli/providers/`) — each provider's prompt construction
- `poor_cli/context_providers.py` — ensure stable ordering
- `poor_cli/cost.py` or cost tracking module — add cache hit/miss metrics
- `nvim-poor-cli/lua/poor-cli/cost.lua` — display cache savings

### Acceptance criteria
- [ ] Prompt prefix order is deterministic and documented
- [ ] Anthropic provider uses `cache_control` on static prefix components
- [ ] Cache hit/miss rates logged and visible in cost dashboard
- [ ] No timestamps or random content in cacheable prefix
- [ ] Test: send 5 identical prompts, verify cache hits on turns 2-5
- [ ] Measured: cache savings shown in `/cost` output

### References
- [Anthropic prompt caching docs](https://docs.anthropic.com/en/docs/build-with-claude/prompt-caching)
- [OpenAI prompt caching](https://platform.openai.com/docs/guides/prompt-caching)
