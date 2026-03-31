# Lessons from `src` and DeepWiki (`instructkr/claude-code`)

Date: 2026-03-31
Source set:
- Local snapshot: `/home/gongahkia/Desktop/coding/projects/src` (1,902 files)
- DeepWiki: https://deepwiki.com/instructkr/claude-code (indexed 2026-03-31)

## 1) Repository Structure Lessons

### What `src` does well
- Strongly modular architecture with clear domain boundaries:
  - Query orchestration: `QueryEngine.ts`, `query.ts`, `query/*`
  - Tool contracts + execution: `Tool.ts`, `tools/*`, `services/tools/*`
  - Agent/task runtime: `tools/AgentTool/*`, `tasks/*`, `Task.ts`
  - State/session: `state/*`, `utils/sessionStorage.ts`, `history.ts`
  - Prompt/context/policy: `constants/prompts.ts`, `context.ts`, `utils/queryContext.ts`, hooks
- Type-centric contracts (`Tool<Input, Output>`, task state types, app state types) keep behavior explicit.
- Feature-gated modules prevent uncontrolled complexity in runtime paths.

### Transferable lesson for `poor-cli`
- Keep the same decomposition principle:
  - Query loop logic in core
  - Tool lifecycle in registry/execution layer
  - Agent/task lifecycle isolated from main turn loop
  - Prompt/context policy in dedicated modules

## 2) Agent System Lessons

### What `src` does well
- Agent launch is treated as a first-class tool with explicit schemas and agent definitions.
- Task lifecycle is explicit: typed IDs, terminal statuses, disk-backed outputs, queueing, cancellation.
- Supports both in-process and isolated/background agents, with safety constraints around delegation.
- Agent metadata/persistence enables resume/recovery instead of ephemeral-only execution.

### Transferable lesson for `poor-cli`
- Prefer explicit agent/task metadata over implicit in-memory state.
- Keep agent orchestration observable (status/progress/result files) and safely interruptible.

## 3) User Query Handling Lessons

### What `src` does well
- `submitMessage` -> `query()` pipeline is explicit and eventful:
  - user input processing
  - prompt/context assembly
  - streaming model loop
  - tool loop
  - stop/recovery hooks
  - final result synthesis
- Tool calls are orchestrated with concurrency control, not only a blanket `gather`.
- Loop has bounded controls (`maxTurns`, budget guards, fallback logic, abort handling).
- Session persistence is integrated with loop milestones to avoid losing resumability.

### Transferable lesson for `poor-cli`
- Keep turn transitions explicit and bounded.
- Execute tools with conservative concurrency policy and predictable ordering.
- Preserve resumability and run traces as part of normal flow.

## 4) High-Quality Response Lessons

### What `src` does well
- Quality is produced by system design, not only prompt wording:
  - layered system prompt + contextual sections
  - permission/hook enforcement before and after tool execution
  - context compaction and message boundary management for long sessions
  - structured progress/status events
  - automatic recovery paths for common failure conditions
- Uses strict tool schemas and execution context to reduce accidental misuse.

### Transferable lesson for `poor-cli`
- Improve response quality by tightening orchestration:
  - safer tool routing
  - bounded parallelism
  - clearer run-state diagnostics
  - robust context management under long sessions

## 5) Gap Analysis (`poor-cli` vs `src`)

Current strengths in `poor-cli`:
- Solid core loop with permissions, checkpoints, policy hooks, fallback, and economy controls.
- Good baseline split of read-only vs mutating tool execution.
- Existing background task and agent infrastructure.

Current gaps observed:
- Read-only tools are executed with unbounded `asyncio.gather`, which can oversubscribe.
- Concurrency safety is inferred from a static mutating set; unknown/external tools can be over-trusted.
- Tool orchestration lacks a configurable parallelism cap in `agentic` config.

## 6) Phased Adoption Plan for `poor-cli`

### Phase 1 (implement now)
- Add conservative per-tool concurrency-safety classification.
- Add bounded parallel execution for concurrency-safe tools.
- Add `agentic.max_parallel_tool_calls` configuration.

### Phase 2
- Add explicit turn transition diagnostics (reason codes) in run history and status output.
- Expose structured per-turn orchestration summaries in `/status` and `/runs`.

### Phase 3
- Expand task/agent lifecycle observability:
  - unified event stream format
  - stronger resume metadata
  - clearer terminal state semantics

### Phase 4
- Improve long-session quality:
  - stronger compaction boundary diagnostics
  - better tool-result budgeting strategy
  - stricter prompt layering instrumentation

## 7) Implementation Note

This file defines the concrete roadmap. Execution starts with Phase 1 in this repo.
