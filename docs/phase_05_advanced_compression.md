# Phase 5: Advanced Compression — Squeeze More from Every Token

**Priority:** Medium — 🟡 Moderate to 🟠 Hard solutions requiring careful implementation.
**Estimated agents:** 3 (parallel)
**Dependencies:** Phase 2A (tree-sitter repo map) should be done first — AST chunking builds on the same tree-sitter infrastructure. Phase 3 (smart loading) recommended for a clean integration surface.
**Philosophy:** These solutions are about compression at multiple levels — prompts, code, and failure traces. They're harder to get right but deliver compounding savings that multiply with session length.

---

## Agent 5A: LLMLingua Prompt Compression

**Pain points addressed:** #4 (system prompt bloat), #2 (tool output bloat), #3 (codebase reading inefficiency)
**Solution reference:** Solution #10 from SOLUTIONS.md
**Expected savings:** Up to 20× compression with ~1.5% accuracy loss; 21.4% RAG performance boost at 1/4 tokens

### What to build

Integrate a prompt compression layer that uses a small model to identify and remove redundant tokens from prompts before sending to the main model. This is a sidecar process — it sits between poor-cli and the provider.

### Implementation details

1. **Choose compression approach** — two options:
   - **Option A (recommended): LLMLingua-2** — BERT-sized classifier, 3–6× faster than LLMLingua-1. Runs locally, no API calls. Binary token classification (keep/drop).
   - **Option B: Custom heuristic compression** — if LLMLingua dependency is too heavy, implement a lighter version:
     - Remove redundant whitespace and formatting
     - Collapse repeated patterns (e.g., long lists of similar items)
     - Truncate boilerplate (license headers, import blocks)

2. **Integration as middleware**:
   ```python
   class PromptCompressor:
       def __init__(self, model_name="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"):
           self.compressor = load_model(model_name)  # ~110MB
       
       def compress(self, text: str, ratio: float = 0.5, 
                    preserve_patterns: list[str] = None) -> str:
           """Compress text to target ratio, preserving specified patterns."""
           # preserve code blocks, error messages, file paths
           preserved = self.extract_preserved(text, preserve_patterns)
           compressed = self.compressor.compress(text, target_ratio=ratio)
           return self.restore_preserved(compressed, preserved)
   ```

3. **What to compress** (and what NOT to):
   - **Compress:** Long tool outputs, file contents read into context, verbose MCP responses, older conversation history
   - **Do NOT compress:** Current user message, code blocks the model needs to edit, error messages, file paths, variable names
   - **Preserve patterns:** regex patterns for code fences, file paths, error stacks

4. **Compression ratio tuning** — different content types need different ratios:
   ```python
   COMPRESSION_RATIOS = {
       "tool_output": 0.3,      # heavy compression — tool output is noisy
       "file_content": 0.5,     # moderate — preserve structure
       "conversation_history": 0.4,  # moderate — keep key decisions
       "system_prompt": 0.7,    # light — important instructions
   }
   ```

5. **Performance guard** — compression must be fast enough to not add noticeable latency:
   - Target: < 100ms for typical prompt compression
   - If compression takes too long, skip it (better to send full prompt than delay)
   - Track compression time in metrics

6. **Integration with economy modes**:
   - `frugal`: aggressive compression (ratio 0.3)
   - `balanced`: moderate compression (ratio 0.5)
   - `quality`: minimal compression (ratio 0.8) or disabled

7. **Lazy model loading** — don't load the compression model until first use. It's ~110MB and shouldn't slow down startup.

### Files to create/modify
- `poor_cli/prompt_compressor.py` (new, ~200 lines)
- `poor_cli/context_optimizer.py` (integrate compression into context pipeline)
- `poor_cli/profiles.py` (tie compression ratios to economy modes)
- `pyproject.toml` (add optional dependency: `llmlingua` or `transformers`)

### Acceptance criteria
- [ ] Prompt compression reduces token count by 50%+ on tool outputs
- [ ] Code blocks and error messages preserved through compression
- [ ] Compression adds < 100ms latency per request
- [ ] Economy mode controls compression aggressiveness
- [ ] Compression model loaded lazily on first use
- [ ] Falls back gracefully if compression model not installed
- [ ] Test: compress a 5000-token tool output, verify key info preserved, measure token reduction

### References
- [LLMLingua GitHub](https://github.com/microsoft/LLMLingua)
- [LLMLingua paper](https://arxiv.org/abs/2310.05736)
- [LLMLingua-2 paper](https://arxiv.org/abs/2403.12968)
- [LongLLMLingua](https://arxiv.org/abs/2310.06839)

---

## Agent 5B: AST-Aware Code Chunking for RAG

**Pain points addressed:** #3 (codebase reading inefficiency), #7 (lost-in-the-middle — better chunking improves retrieval precision)
**Solution reference:** Solution #11 from SOLUTIONS.md
**Expected savings:** 40-60% improvement in code retrieval precision; fewer irrelevant code chunks in context

### What to build

Replace naive line/character-based code chunking in the indexer with AST-aware chunking that preserves syntactic boundaries. Each chunk is a complete function, class, or logical block — never a fragment.

### Implementation details

1. **Audit current indexer** — read `poor_cli/indexer.py`:
   - How does it currently chunk code?
   - What embedding model does it use?
   - What's the chunk size?

2. **AST-aware chunking** using tree-sitter (same dependency as Phase 2A):
   ```python
   def chunk_file_ast(filepath: Path, language: str) -> list[CodeChunk]:
       tree = parse_file(filepath, language)
       chunks = []
       for node in tree.root_node.children:
           if node.type in CHUNK_TYPES[language]:
               chunk = CodeChunk(
                   filepath=filepath,
                   start_line=node.start_point[0],
                   end_line=node.end_point[0],
                   content=node.text.decode(),
                   node_type=node.type,
                   name=extract_name(node),
               )
               # if chunk too large (>500 lines), split at method boundaries
               if chunk.line_count > 500:
                   chunks.extend(split_large_node(node))
               else:
                   chunks.append(chunk)
       return chunks
   ```

3. **Chunk types per language**:
   ```python
   CHUNK_TYPES = {
       "python": ["function_definition", "class_definition", "decorated_definition"],
       "lua": ["function_declaration", "local_function", "function"],
       "javascript": ["function_declaration", "class_declaration", "arrow_function",
                       "method_definition", "export_statement"],
       "typescript": ["function_declaration", "class_declaration", "interface_declaration",
                       "type_alias_declaration"],
       "rust": ["function_item", "impl_item", "struct_item", "enum_item", "trait_item"],
   }
   ```

4. **Natural language descriptions** — for each chunk, generate a one-line description:
   ```python
   def describe_chunk(chunk: CodeChunk) -> str:
       # heuristic: extract docstring, or generate from signature
       if chunk.has_docstring:
           return chunk.docstring[:100]
       return f"{chunk.node_type} '{chunk.name}' in {chunk.filepath.name}:{chunk.start_line}"
   ```

5. **Dual embedding** — embed both the code and the description:
   ```python
   chunk.code_embedding = embed(chunk.content)
   chunk.description_embedding = embed(chunk.description)
   # search matches against both, weighted: 0.3 code + 0.7 description
   ```

6. **Integration with context system** — when the model needs to read code:
   - Query the index with the user's prompt
   - Return top-K chunks (ranked by relevance)
   - Include chunk metadata (file, line range, name) for navigation

7. **Incremental updates** — re-index only changed files (watch for git changes).

### Files to create/modify
- `poor_cli/indexer.py` (primary — replace chunking logic with AST-aware)
- `poor_cli/embeddings.py` (ensure dual embedding support)
- Phase 2A's tree-sitter infrastructure (shared dependency)

### Acceptance criteria
- [ ] AST-aware chunking for Python, Lua, JavaScript, TypeScript, Rust
- [ ] Chunks are syntactically complete (never mid-function)
- [ ] Large chunks (>500 lines) split at method boundaries
- [ ] Natural language descriptions generated per chunk
- [ ] Dual embedding (code + description) improves retrieval
- [ ] Incremental re-indexing on file changes
- [ ] Test: index poor-cli itself, query "context management", verify relevant chunks returned

### References
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/)
- [LlamaIndex code splitter](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/code/)
- [CodeRAG-Bench](https://arxiv.org/abs/2406.14497)

---

## Agent 5C: Selective Failure Amnesia

**Pain points addressed:** #5 (retry / failure tax — 3–10× token waste on failures)
**Solution reference:** Solution #16 from SOLUTIONS.md
**Expected savings:** 50-80% reduction in failure-related token waste

### What to build

A meta-controller that, after a failed tool call or reasoning attempt, extracts only the lesson learned and prunes the full failure trace from context. This is a **greenfield gap** — no standard implementation exists.

### Implementation details

1. **Failure detection** — identify when a tool call or reasoning step has failed:
   - Non-zero exit code from bash/shell tools
   - Error in tool response
   - Model's own acknowledgment of failure ("that didn't work", "wrong approach")
   - Test failures

2. **Lesson extraction** — after a failure, extract a structured lesson:
   ```python
   class FailureLesson:
       failed_action: str        # "tried to read /nonexistent/file.py"
       error_type: str           # "FileNotFoundError"
       lesson: str               # "file is at /correct/path/file.py"
       corrective_action: str    # "read /correct/path/file.py instead"
   
   async def extract_lesson(failure_trace: str, context: SessionContext) -> FailureLesson:
       # use the current model to extract a concise lesson
       # this costs tokens but saves many more by pruning the full trace
       prompt = f"Extract a 1-2 sentence lesson from this failure:\n{failure_trace}"
       lesson = await quick_completion(prompt)
       return FailureLesson.parse(lesson)
   ```

3. **Trace pruning** — replace the full failure trace in conversation history with the lesson:
   ```python
   # before: full error trace (500 tokens)
   # FileNotFoundError: /nonexistent/file.py
   # Traceback (most recent call last): ...
   # ... 30 lines of stack trace ...
   
   # after: lesson (30 tokens)
   # [failure-amnesia] Tried to read /nonexistent/file.py — file not found. 
   # Correct path: /correct/path/file.py
   ```

4. **Amnesia triggers** — when to prune:
   - Immediately after a successful retry (the failure is now resolved)
   - When context exceeds threshold and failures are the oldest low-value content
   - On explicit `/compact` (failures pruned first)

5. **Safety constraints** — never prune:
   - The most recent failure (model may still be working on it)
   - Failures that haven't been resolved yet
   - Failures the user explicitly referenced ("about that error earlier...")

6. **Integration with history pruning** (Phase 3C) — failure amnesia is a specialized case of importance-weighted pruning. The pruning engine should call failure amnesia first for failed turns.

7. **Metrics** — track tokens saved by failure amnesia in the cost dashboard.

### Files to create/modify
- `poor_cli/failure_amnesia.py` (new, ~200 lines)
- `poor_cli/error_recovery.py` (integrate lesson extraction)
- `poor_cli/context_optimizer.py` (integrate failure pruning into compaction pipeline)
- `poor_cli/history.py` (mark turns as failed/resolved)

### Acceptance criteria
- [ ] Failed tool calls detected automatically
- [ ] Lesson extraction produces concise structured summaries
- [ ] Full failure traces replaced with lessons in conversation history
- [ ] Most recent / unresolved failures preserved
- [ ] Tokens saved tracked in cost dashboard
- [ ] Integration with history pruning pipeline
- [ ] Test: simulate 3 failed tool calls → 1 success, verify 3 failure traces replaced with lessons

### References
- [Reflexion paper](https://arxiv.org/abs/2303.11366) — closest research on learning from agent failures
- No standard implementation exists — this is greenfield
