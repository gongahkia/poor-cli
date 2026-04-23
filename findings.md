# Findings

## Article 1: The File System Is the New Database

### General Learnings

- Context engineering beats prompt repetition. Durable files should hold identity, goals, workflows, decisions, failures, and style rules so each agent run starts from reusable context instead of a rebuilt prompt.
- Progressive disclosure is the key token-control pattern: always-load routing, task/module instructions on demand, and raw data only when needed.
- File formats should match agent behavior: Markdown for narrative/instructions, YAML for hierarchical config with comments, JSONL for append-only logs and streamable records.
- Append-only memory is safer than whole-file rewrites. JSONL plus archive/status fields preserves history and reduces destructive-agent failure modes.
- Module boundaries are loading decisions. Bad boundaries cause the agent to load irrelevant context, waste tokens, and degrade focus.
- Instruction hierarchy reduces conflicts: repo-level map, agent-level decision table, module-level domain rules.
- Useful memory includes judgment, not just facts: decisions, alternatives, outcomes, failures, prevention steps, and emotionally/strategically important events.
- Cross-file IDs create a lightweight relational model without DB overhead; agents can traverse contact_id, task_id, decision_id, etc. only when the workflow requires it.
- Skills encode process. Auto-loaded reference skills handle consistency; manual task skills handle precision and quality gates.
- Voice/taste systems work better as structured constraints than adjectives: scales, banned phrases, examples, checklists, and self-critique passes.
- Scripts should output agent-readable stdout and write back to the same file substrate. This makes automation a feedback loop, not a separate app.
- Keep schemas small. Sparse over-modeled schemas make agents hallucinate missing data or fill fields unnecessarily.

### poor-cli Applications

- Add a repo-local file memory pattern as a first-class harness feature, likely under `.poor-cli/brain/` or `.poor-cli/context/`, with Markdown/YAML/JSONL conventions.
- Add a lightweight routing file that maps request types to context modules, so `exec` can load less context by default.
- Extend context assembly to support progressive disclosure explicitly: root map -> module instructions -> selected data files.
- Prefer JSONL for durable event streams: agent decisions, failures, user preferences, review findings, tool outcomes, and accepted/rejected advisor advice.
- Add schema-line enforcement for JSONL logs: first line declares `_schema`, `_version`, `_description`.
- Add append-only helpers for agents so they can log memories safely without rewriting full JSON/JSONL files.
- Add a `context doctor` or `memory doctor` command that detects oversized modules, sparse schemas, missing schema lines, and files that should be split.
- Build a small decision-log primitive: decision, alternatives, reasoning, outcome, follow-up date. This helps future agents reuse user/project judgment.
- Build a failure-log primitive: symptom, root cause, prevention, affected files/commands. This improves debugging and reduces repeated mistakes.
- Make `AGENTS.md`/repo rules part of a hierarchy, not a monolith: root rules plus optional module rules discovered by path.
- Add skill metadata support for auto-load vs manual invocation and explicit context dependencies.
- Add quality gates as skill steps: review pass, test pass, source/evidence pass, output-budget pass.
- Add context-budget reports that show which module/file was loaded and why, with token estimates.
- Add hard guidance for agents to request specific missing files instead of broad-loading the repo.
- Keep poor-cli philosophically file-first and portable: no mandatory DB/vector store for core memory; optional indexes can accelerate, not own, truth.

## Article 2: Building a Code-Editing Agent in Under 400 Lines

### General Learnings

- The core agent loop is simple: keep conversation state client-side, send it to the model, execute requested tools, append tool results, repeat.
- Tool use is the boundary between chat and agency. An agent is an LLM loop with tools that can inspect or mutate external state.
- Tool quality matters more than tool count. A tiny set of reliable tools (`list_files`, `read_file`, `edit_file`) can produce useful code-editing behavior.
- Tool descriptions are part of the product. The model chooses tools from names, descriptions, schemas, and observed results.
- Stateless model APIs push memory ownership into the harness. The harness must manage conversation history, compaction, and tool results.
- Models can compose tools without explicit procedural prompts when the tool interface is clear.
- Simple edit primitives can go far. Exact string replacement works because it is easy for the model to reason about and easy for the harness to validate.
- Returning structured, compact tool output helps the model decide next steps without wasting context.
- Error feedback is useful context. Tool errors should be returned clearly so the model can recover.
- The hard part is not the minimum viable loop; it is safety, UX, observability, cost control, permissions, and robust editing.

### poor-cli Applications

- Keep the core loop boring and inspectable. poor-cli should make the message -> tool call -> tool result -> message cycle easy to debug.
- Optimize the default toolset before adding exotic tools. `list/read/grep/diff/edit/test` should be fast, predictable, and token-cheap.
- Treat tool descriptions as routing prompts. Add evals for whether models choose `grep_files` vs `read_file`, `list_directory` vs shell, and `apply_patch` vs full rewrite.
- Add short result modes for common tools: compact directory listings, capped file reads, diff snippets, and structured test summaries.
- Prefer edit APIs with validation: exact-match replacement, patch application, JSON/YAML structural edits, and clear failure messages.
- Make failed tool calls cheap and actionable: include the error, expected input shape, and next likely recovery action.
- Expose the loop as trace data in `exec` artifacts: user prompt, selected context, tool calls, results, retries, cost, and final reason.
- Add token accounting around every tool result, not just model calls, because tool outputs become future input tokens.
- Use model-visible tool affordances to reduce prompting. If a tool is self-describing, the system prompt can stay shorter.
- Add minimal-agent examples/tests to protect product philosophy: poor-cli is an agent harness, not a large opaque framework.
- Keep `exec` viable as the primary surface: a non-interactive agent with a small good toolset is already useful for CI/review gates.
- Invest in safety around writes: checkpoint before mutation, show diff after mutation, prefer single-writer flow, and use review sub-agent after edits.

## Article 3: LOD Memory

### General Learnings

- Flat memory forces premature permanent decisions about importance. Importance is task-relative and changes over time.
- Memory should preserve everything but vary retrieval resolution: full content for close/relevant items, summaries for medium-distance items, headlines for distant items.
- The query is the viewpoint. Current task/query should decide memory resolution, not ingestion-time guesses or nightly consolidation.
- Write-time compression can amortize cost: store raw content, summary, headline, embedding, timestamps, retrieval count, and provenance once.
- Wide retrieval plus mixed resolution gives breadth and depth within a token budget. The agent sees a large landscape cheaply, then drills in.
- Recency and semantic relevance are different signals. The balance between them should be explicit and configurable per agent/workload.
- Usage-driven promotion is better than irreversible decay. Memories retrieved often stay sharp; unused memories fade to headline detail without deletion.
- Memory tools should be simple: search returns tiered results, expand fetches raw content, promote raises resolution manually.
- Human trust requires inspectability. Memory should expose why an item was retrieved, at what resolution, and what score drove it.
- Non-semantic retrieval matters: date windows, never-retrieved items, random resurfacing, agent ownership, retrieval count, and tier filters.
- Vector-only stores are insufficient for agent memory. Hybrid vector + relational metadata supports both semantic search and operational queries.
- Conflicting memories need provenance and conflict handling. Retrieval alone cannot resolve contradictory facts safely.

### poor-cli Applications

- Add LOD-style memory retrieval on top of existing repo-local memory: `headline`, `summary`, `content`, `embedding`, `created_at`, `last_accessed_at`, `retrieval_count`, `source`, `agent_id`.
- Keep raw memory append-only, then add derived summary/headline fields as cacheable artifacts.
- Implement `memory_search` output as tiered context, not uniform chunks. Example: top N full, next M summaries, rest headlines.
- Add `memory_expand(memory_id)` so agents can inspect full content only after a headline/summary looks relevant.
- Add `memory_promote(memory_id)` or `memory_pin` for user/agent-marked durable high-resolution memories.
- Add explicit scoring metadata to memory results: semantic score, recency score, final LOD score, tier, and reason.
- Make `alpha` configurable by profile: code review may prefer semantic relevance; CI/debugging may prefer recency; long-lived project guidance may balance both.
- Use LOD memory to reduce prompt bloat: load many headlines cheaply instead of a few full memories.
- Add a `memory landscape`/`memory stats` CLI report showing hot memories, decayed memories, never-retrieved memories, and token footprint by tier.
- Add non-semantic modes: `--since`, `--never-used`, `--agent`, `--type`, `--random-stale`, `--promoted-only`.
- Add conflict/provenance fields to memory entries: supersedes, contradicts, source file, run id, commit hash, confidence.
- Use small/cheap models for write-time headline/summary generation when available; skip summarization for tiny entries.
- Add tests/evals for memory retrieval cost: compare uniform top-k full memory vs LOD mixed-resolution token use and answer quality.
- Keep storage portable: JSONL can hold raw/provenance; SQLite/FTS/vector index can accelerate, not replace, file truth.
- Apply LOD to tool results and run history too: recent/relevant tool outputs full, older summaries/headlines only.

## Article 4: Bash Is the SQL for File Systems

### General Learnings

- Moving bytes to compute is expensive. Moving instructions to data is often cheaper, faster, and simpler.
- Databases avoid egress by embedding compute near storage: clients send queries, storage executes, and only relevant results return.
- File systems traditionally expose bytes, not computation. Tools like `grep` make the client read too much data.
- Bash is a practical query language for file systems because it already expresses search, filtering, transformation, and mutation.
- Server-side filesystem execution changes the interface from "download data and inspect locally" to "send an operation and return compact output."
- Planning/optimization can happen below the interface: fan-out, locality-aware execution, index use, result shaping, and scheduling.
- Agents make stateful filesystems more important: memory, prompts, context, traces, and histories are all stateful artifacts.
- The economic lesson maps directly to tokens: raw file/tool output egress becomes prompt input cost.

### poor-cli Applications

- Treat shell/file tools as query engines, not byte dumpers. Prefer tools that execute close to the repo and return compact answers.
- Add higher-level filesystem query tools for common agent patterns: find definitions, summarize matches, list changed files by type, extract symbols, inspect package metadata.
- Make `grep_files`/`semantic_search` return ranked snippets and counts by default, with explicit expand/read steps for full content.
- Add tool-result shaping controls: `max_matches`, `max_bytes`, `context_lines`, `json`, `paths_only`, `counts_only`.
- Prefer "send command, return result" over "read all files into context". This aligns shell execution with token efficiency.
- Add a planner layer for expensive filesystem queries: choose `rg`, AST index, git diff, package graph, or semantic index based on request.
- Add locality-aware execution for remote/CI contexts: run discovery on the machine with the checkout and return compressed artifacts.
- Add a safe bash query subset or templates for common read-only operations, with strict deny rules for mutation unless explicitly needed.
- Use stdout contracts for agent-facing scripts: concise JSON/NDJSON summaries rather than verbose human logs.
- Track "tool egress tokens": bytes returned from filesystem/shell tools that later enter model context.
- Add auto-suggested narrower commands when a shell result is too large, e.g. retry with `rg -n --glob`, `head`, `jq`, or path filters.
- Make MCP/server mode support remote execution as a first-class primitive: client sends intent/tool call, server runs near repo/storage, client receives compact result.
- Cache command results by command + git tree hash so repeated filesystem queries do not resend identical output.
- Expose query traces in diagnostics: command/tool chosen, raw bytes scanned, bytes returned, token estimate, and truncation reason.

## Article 5: Two Camps of AI Memory Tools

### General Learnings

- There are two different categories hiding under "agent memory": memory backends and context substrates.
- Memory backends optimize fact recall: extract/store/search/update/delete facts from conversation history.
- Context substrates optimize compounding work: agents operate inside structured, human-readable context that persists and improves across sessions.
- Backend memory asks "what should the AI remember?" Context substrates ask "what context should the AI work inside?"
- Vector/graph memory is useful for preferences, facts, and recall, but it often hides state behind extraction quality and retrieval heuristics.
- File-native context makes memory auditable. Humans can read, edit, version, fork, and correct what the agent knows.
- Verbatim memory gives high recall but can grow without synthesis. Extraction memory compresses but can distort or stale out.
- Temporal validity matters: facts need `valid_at`, `invalid_at`, supersession, and decay rather than permanent equality.
- Context as an artifact should have lifecycle: version, test, promote, rollback, fork, merge.
- Shadow indexes are a strong pattern: Markdown/files remain source of truth; vector/graph indexes are rebuildable access layers.
- Background consolidation is useful when it reconciles lived context into durable structure, but it should be inspectable and reversible.
- Continuous agents need substrates more than recall. They need active projects, decisions, yesterday's state, open loops, and evolving plans.

### poor-cli Applications

- Position poor-cli memory as a context substrate, not only a memory backend. The repo-local `.poor-cli/` state should be human-readable and portable.
- Keep files as source of truth; use SQLite/FTS/vector indexes as rebuildable acceleration only.
- Split memory APIs by purpose: `memory_recall` for facts, `context_load` for working substrate, `context_update` for structured write-back.
- Add context containers/bundles for project state: goals, decisions, failures, active tasks, open questions, run summaries, and known constraints.
- Add versioned context snapshots tied to git commit/run id so context can be rolled back or compared.
- Add temporal fields to facts/preferences: `valid_at`, `invalid_at`, `supersedes`, `confidence`, `source`.
- Add stale-fact detection and supersession handling, especially for user/project preferences and environment details.
- Add context lifecycle commands: `context init`, `context doctor`, `context export`, `context fork`, `context diff`, `context compact`.
- Add background consolidation that writes reviewable patches to context files instead of silently mutating hidden memory.
- Make agent run outputs compound: every significant run can append a short decision/failure/summary record for future sessions.
- Add evals that measure compounding, not just recall: does the agent use yesterday's decision, avoid repeated failed attempts, and preserve active project state?
- Add provenance on every memory/context write: agent id, source prompt/run, files touched, timestamp, and whether user accepted it.
- Add portable context bundles for CI or server mode so an external harness can load the same working state without local hidden DB dependence.
- Keep memory UI CLI-first: `poor-cli memory list/search/show`, `poor-cli context map`, and markdown files openable in any editor.
- Treat "context engineering" as the product frame: selecting, shaping, persisting, auditing, and compressing working context.

## Article 6: Your Harness, Your Memory

### General Learnings

- Harnesses are durable infrastructure, not temporary scaffolding. Tool orchestration, context selection, compaction, and state management will stay outside the raw model.
- Memory is part of the harness because memory is context management across time.
- Closed harnesses create memory lock-in. If state lives behind a proprietary API, switching models or harnesses can lose accumulated behavior.
- Stateful provider APIs reduce portability. Server-side threads, compaction, managed agents, and encrypted summaries bind memory to one ecosystem.
- Memory is a proprietary data flywheel: user preferences, interaction patterns, decisions, and task history make an agent harder to replace.
- Owning memory means owning storage, schemas, compaction rules, retrieval rules, and export paths.
- Open standards matter: `AGENTS.md`, skills, portable memory stores, and model-agnostic harness APIs reduce lock-in.
- Separate model choice from memory ownership. Models should be replaceable without resetting agent experience.
- The memory abstraction is still early. Harnesses need explicit, inspectable memory design before "memory as a service" can be safely portable.

### poor-cli Applications

- Make memory portability a core product principle: no default dependency on provider-side state, hosted threads, or opaque compaction.
- Add a harness portability check that flags stateful API usage, non-exportable memory, encrypted summaries, and provider-specific stored context.
- Store conversation, compaction summaries, memory, run traces, and context bundles locally in open formats by default.
- Add `poor-cli state export` and `poor-cli state import` so users can move sessions/memory across machines and providers.
- Keep provider adapters stateless where possible: replay local context into any provider rather than relying on remote thread IDs.
- Add provider capability warnings for managed-agent/stateful features: useful but lock-in inducing.
- Make compaction outputs plain text/JSON/Markdown and reusable across providers.
- Add tests that switch providers mid-session using local history/context to verify portability.
- Add memory backend plugin boundaries without giving up harness ownership: Mongo/Postgres/Redis/etc. can store memory, but poor-cli owns schema and retrieval semantics.
- Add docs framing poor-cli as an open, model-agnostic harness where the user owns memory, context, and audit logs.
- Track memory writes with provenance and exportability status.
- Prefer open standards in prompt/context loading: `AGENTS.md`, skills, MCP, JSONL logs, Markdown summaries.
- Add CI guardrails to prevent new features from depending only on provider-specific hidden state.
- Treat memory as user data. Provide deletion, listing, export, and audit commands for all persistent state.
