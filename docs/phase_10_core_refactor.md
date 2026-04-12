# Phase 10: Core Refactor & Architectural Partition

**Priority:** High — unblocks Wave 2+ features (repo-state cache, streaming tool output, picker UX) and reduces cognitive load on two files (`core.py`, `server/runtime.py`) that have become change-bottlenecks.
**Estimated agents:** 4 (see sub-wave ordering below — NOT fully parallel)
**Dependencies:** PRD 001 (TokenCounter), PRD 010 (rate limit), PRD 017 (provider adapter base). All of these must be in main before this phase opens.
**Philosophy:** Behavior-preserving structural moves. Every agent in this phase is a refactor — no new user-facing features, no new context sources, no new provider SDKs. If an agent feels the urge to "fix one more thing while I'm in here," stop. File it as a follow-up PRD. The goal is to unlock downstream work, not to rewrite.

---

## File-scope map

The table below shows each agent's write scope. Read it before starting — two agents share `poor_cli/core.py` and must be serialized (see "Collisions & sub-waves" below).

| Agent | Modifies (existing) | Creates (new) |
|-------|---------------------|---------------|
| 10A | `context.py`, `context_engine.py`, `context_optimizer.py`, `context_compressor.py`, `history_pruning.py`, `core.py` (narrow) | `context_assembly.py`, `tests/test_context_assembly.py` |
| 10B | `server/runtime.py` | `server/handlers/{__init__,chat,tools,config,sessions,checkpoints,providers,tasks,automations,memory,multiplayer,status,context,trust}.py`, `server/registry.py`, `server/multiplayer_state.py`, `tests/test_server_handlers.py` |
| 10C | `providers/base.py`, `providers/*_provider.py`, `provider_catalog.py`, `core.py` (narrow), `thinking_budget.py`, `vision.py` | `providers/capability.py`, `tests/test_provider_capability.py` |
| 10D | `skills.py`, `skill_surfacer.py`, `custom_commands.py`, `workflow_templates.py`, `automation_manager.py` (consolidated away) | `automations/{__init__,rules,triggers,steps,migration}.py`, `tests/test_automations.py` |

### Collisions & sub-waves

**Collision 1 — `poor_cli/core.py` (10A + 10C).** Both agents touch `core.py` but in narrow, orthogonal slices: 10A replaces the inline context-assembly block in `run_turn` with an orchestrator call; 10C replaces `isinstance(provider, AnthropicProvider)` feature-gates with capability-flag checks. Still, merge conflicts are near-certain if they land in parallel.

**Resolution:** **10A lands first.** Once 10A is merged, 10C rebases onto it. Rationale: 10A's edit is larger (a block excision) and 10C's edit is mechanical (find-and-replace on `isinstance` sites). Rebasing 10C is trivial; rebasing 10A onto 10C would require re-locating the assembly block after capability plumbing was inserted around it.

**Collision 2 — indirect, `automation_manager.py` / `handlers/automations.py` (10B + 10D).** 10B adds `server/handlers/automations.py` (a new file — no conflict by itself). 10D consolidates `automation_manager.py` into `automations/`. If 10B's `handlers/automations.py` imports from `automation_manager`, 10D must update those import sites during migration.

**Resolution:** **10B lands before 10D.** 10D treats 10B's `handlers/automations.py` as a known import-update target in its migration script. Both PRDs are independent in scope; this is purely an import-path follow-up.

**Sub-wave ordering:**
- **Wave 10.1 (parallel):** 10A, 10B
- **Wave 10.2 (parallel, after 10.1):** 10C (rebases on 10A's `core.py`), 10D (updates 10B's `handlers/automations.py` imports)

---

## Agent 10A: Context Assembly Orchestrator

**Pain points addressed:** Scattered context-assembly logic across 6+ modules; no single owner for the end-to-end pipeline; impossible to cache coherently (blocks PRD 022 repo-state cache).
**Solution reference:** PRD 018 — extract `ContextAssemblyOrchestrator`.
**Expected outcome:** One class owns "turn input → ContextSnapshot." Downstream caching, PageRank integration, and structured invalidation become tractable.

### What to build

A single `ContextAssemblyOrchestrator` class with one public entry point — `assemble(prompt, turn_id) -> ContextSnapshot` — that owns the full pipeline: file selection, history pruning, rules assembly, tool-schema resolution, budget-aware compression, token counting, and cache-key hashing. Every existing module (`context_engine`, `context_optimizer`, `context_compressor`, `history_pruning`) keeps its current responsibility but is *called by* the orchestrator instead of being invoked directly from `core.py`.

### Implementation details

1. **Define the data types** in `poor_cli/context_assembly.py`:
   - `ContextFile(path, content, tokens, reason, compressed)` — frozen dataclass; `reason` is a short string like `"imported-by-target"`, `"pagerank-top-10"`, `"recent-open"`.
   - `ContextSnapshot(system_prompt, rules, files, history, tool_schemas, tokens, budget, provider, model, key)` — frozen dataclass. `tokens` is a breakdown dict (`system`, `rules`, `files`, `history`, `tools`, `total`). `key` is the cache hash for PRD 022.

2. **Orchestrator pipeline** — inside `assemble()`, run steps in this order:
   1. Resolve provider / model / budget via economy config.
   2. Select files via `context_engine` (leave PageRank hook for PRD 022; do not add it here).
   3. Prune history via `history_pruning`.
   4. Assemble rules from `AGENTS.md` / `CLAUDE.md`. If PRD 023 has not landed, fall back to `CLAUDE.md` alone — do not block on 023.
   5. Resolve tool schemas for the active provider.
   6. If total tokens > budget: call `context_optimizer` (tiered compaction) first; if still over, call `context_compressor` (LLMLingua).
   7. Count with `TokenCounter` (PRD 001) and write the breakdown dict.
   8. Compute `key = hash(rules + file_contents + history_hash + tool_schemas + provider/model)`.
   9. Return `ContextSnapshot`.

3. **Wire `core.py::run_turn`** — this is the only behavioral change. Replace the scattered context-assembly block with a single orchestrator call:
   ```python
   snapshot = await self._context_assembly.assemble(prompt=prompt, turn_id=new_turn_id())
   return await self._agent_loop.run(snapshot, **kw)
   ```
   Do not refactor anything else in `core.py`. If a refactor opportunity appears, log it as a follow-up PRD.

4. **Invalidation hook** — expose `invalidate(reason: str)` on the orchestrator. No-op for now; PRD 022 will hook it to the repo-state watcher. Keep the signature stable.

5. **Do not remove** `context.py`, `context_engine.py`, `context_optimizer.py`, `context_compressor.py`, `history_pruning.py`. Each stays; the orchestrator composes them.

### Files to create/modify

**Create:**
- `poor_cli/context_assembly.py` (types + orchestrator, ~250 lines)
- `tests/test_context_assembly.py`

**Modify:**
- `poor_cli/core.py` — narrow: excise context-assembly block in `run_turn`, replace with orchestrator call.
- `poor_cli/context.py` — expose any helpers the orchestrator needs; no behavior change.
- `poor_cli/context_engine.py`, `context_optimizer.py`, `context_compressor.py`, `history_pruning.py` — keep; may need minor signature adjustments for orchestrator to call them uniformly.

### Acceptance criteria

- [ ] `ContextAssemblyOrchestrator.assemble()` returns a `ContextSnapshot` with every field populated.
- [ ] `core.py::run_turn` uses the orchestrator; no direct calls to `context_engine` / `context_optimizer` / `history_pruning` remain in `core.py`.
- [ ] Budget-over case exercises optimizer then compressor in order.
- [ ] `snapshot.key` is stable across identical inputs and changes when any file content changes.
- [ ] Token breakdown sums to `total`.
- [ ] All existing tests pass unchanged (behavior-preserving).
- [ ] New tests: `test_assemble_returns_snapshot_with_all_fields`, `test_budget_respected_when_over_calls_optimizer`, `test_key_stable_when_inputs_unchanged`, `test_key_changes_when_file_content_changes`.

**PRD reference:** prd/018-context-assembly-orchestrator.md

---

## Agent 10B: Server Handler Partition

**Pain points addressed:** `server/runtime.py` is ~6,300 lines hosting ~100 RPC methods plus a multiplayer state machine. Contributors cannot modify one method without reading the whole file. Adding a new RPC method requires touching a single giant dispatch table.
**Solution reference:** PRD 019 — partition `runtime.py` into `handlers/` packages.
**Expected outcome:** `runtime.py` ≤800 lines holding only dispatch + transport. Every handler file ≤500 lines. Multiplayer state machine isolated in its own module.

### What to build

A decorator-based registry + per-category handler modules. Each handler self-registers via `@rpc("method-name")`. `runtime.py` becomes a thin dispatcher: look up `REGISTRY.get(method)`, run the rate limiter (PRD 010), invoke the handler.

### Implementation details

1. **Registry module** — `poor_cli/server/registry.py`:
   ```python
   Handler = Callable[["RpcContext", dict], Awaitable[Any]]
   REGISTRY: dict[str, Handler] = {}

   def rpc(method: str):
       def deco(fn: Handler) -> Handler:
           if method in REGISTRY:
               raise RuntimeError(f"duplicate rpc registration: {method}")
           REGISTRY[method] = fn
           return fn
       return deco
   ```

2. **Handler packages** — create one file per category under `poor_cli/server/handlers/`:
   - `chat.py` — `poor-cli/chat`, `chat` (legacy alias), `poor-cli/chatStreaming`
   - `tools.py` — tool execution RPCs
   - `config.py` — config get/set/reload
   - `sessions.py` — session lifecycle
   - `checkpoints.py` — checkpoint create/list/restore
   - `providers.py` — provider list/switch/probe
   - `tasks.py` — background task management
   - `automations.py` — cron / event / slash trigger RPCs (will be updated by 10D)
   - `memory.py` — memory read/write/search
   - `multiplayer.py` — all `multiplayer_*` methods
   - `status.py` — health / status / version
   - `context.py` — context inspection RPCs
   - `trust.py` — trust / permission RPCs

3. **Per-file shape** — each module decorates its handlers with `@rpc(...)`:
   ```python
   from poor_cli.server.registry import rpc

   @rpc("poor-cli/chat")
   async def chat(ctx, params): ...

   @rpc("chat")  # legacy alias
   async def chat_legacy(ctx, params): ...
   ```
   `handlers/__init__.py` imports every submodule at import time so registration happens before dispatch.

4. **Multiplayer extraction** — move the multiplayer state machine (not just the handlers) out of `runtime.py` into `poor_cli/server/multiplayer_state.py`. `handlers/multiplayer.py` imports state from that module. This is the highest-risk move; do it last.

5. **Dispatch wiring** — `runtime.py::dispatch(method, params, ctx)`:
   1. Run rate limiter (PRD 010).
   2. `handler = REGISTRY.get(method)`; 404 if missing.
   3. `return await handler(ctx, params)`.

6. **Incremental migration** — move one handler category at a time. After each category: run `make test` and confirm RPC smoke tests pass. Rollback-per-group via git if anything breaks.

7. **Size guardrails** — add a test `test_runtime_py_under_800_lines` and `test_every_handler_file_under_500_lines`. These prevent regression.

### Files to create/modify

**Create:**
- `poor_cli/server/registry.py`
- `poor_cli/server/handlers/__init__.py`
- `poor_cli/server/handlers/chat.py`
- `poor_cli/server/handlers/tools.py`
- `poor_cli/server/handlers/config.py`
- `poor_cli/server/handlers/sessions.py`
- `poor_cli/server/handlers/checkpoints.py`
- `poor_cli/server/handlers/providers.py`
- `poor_cli/server/handlers/tasks.py`
- `poor_cli/server/handlers/automations.py`
- `poor_cli/server/handlers/memory.py`
- `poor_cli/server/handlers/multiplayer.py`
- `poor_cli/server/handlers/status.py`
- `poor_cli/server/handlers/context.py`
- `poor_cli/server/handlers/trust.py`
- `poor_cli/server/multiplayer_state.py`
- `tests/test_server_handlers.py`

**Modify:**
- `poor_cli/server/runtime.py` — excise handler bodies; keep dispatch + transport only.

### Acceptance criteria

- [ ] `registry.py` raises on duplicate registration.
- [ ] Every pre-existing RPC method is reachable via the registry (enumerate all ~100 methods in a smoke test).
- [ ] No method signature or behavior changes.
- [ ] `runtime.py` ≤800 lines (enforced by test).
- [ ] Every `handlers/*.py` file ≤500 lines (enforced by test).
- [ ] Multiplayer state machine lives in `multiplayer_state.py`; `runtime.py` has zero multiplayer references.
- [ ] All existing tests pass unchanged.
- [ ] New tests: `test_registry_registers_unique_methods`, `test_every_known_method_still_reachable`, `test_runtime_py_under_800_lines`.

**PRD reference:** prd/019-server-handlers-partition.md

---

## Agent 10C: Provider Capability Enum

**Pain points addressed:** Extended thinking is hardcoded to Anthropic. Prompt caching is Anthropic-only in code but not declared as such. Gemini grounding is invisible to callers. Feature gating uses `isinstance(provider, AnthropicProvider)` — fragile and not discoverable.
**Solution reference:** PRD 020 — introduce `ProviderCapability` enum.
**Expected outcome:** Every provider declares its capability set. Core gates on `ProviderCapability.X in provider.capabilities` — no `isinstance` checks remain for feature dispatch.

### What to build

A `Flag` enum covering every provider-differentiated capability. Each adapter declares its set as a class attribute on the `BaseProvider` subclass. Core code, `thinking_budget.py`, and `vision.py` replace `isinstance` feature-gates with capability-flag checks. The provider catalog exposes capabilities so UIs (PRD 030 picker) can gray out unsupported options.

### Implementation details

1. **Enum definition** in `poor_cli/providers/capability.py`:
   ```python
   from enum import Flag, auto

   class ProviderCapability(Flag):
       NONE                  = 0
       STREAMING             = auto()
       TOOL_CALLING          = auto()
       SYSTEM_INSTRUCTIONS   = auto()
       JSON_MODE             = auto()
       VISION                = auto()
       PROMPT_CACHING_PREFIX = auto()
       PROMPT_CACHING_BLOCK  = auto()
       EXTENDED_THINKING     = auto()
       GROUNDING             = auto()   # Gemini web search
       LATENT_COMMUNICATION  = auto()   # research mode
   ```

2. **Base class wiring** — `poor_cli/providers/base.py`:
   ```python
   class BaseProvider(ABC):
       capabilities: ProviderCapability = ProviderCapability.NONE
   ```

3. **Per-adapter declarations** — every `providers/*_provider.py` subclass declares its set. Example:
   ```python
   class AnthropicProvider(BaseProvider):
       capabilities = (
           ProviderCapability.STREAMING |
           ProviderCapability.TOOL_CALLING |
           ProviderCapability.SYSTEM_INSTRUCTIONS |
           ProviderCapability.VISION |
           ProviderCapability.PROMPT_CACHING_PREFIX |
           ProviderCapability.EXTENDED_THINKING
       )
   ```
   Be honest — do not declare a capability the adapter does not actually implement. Ollama likely has `STREAMING | TOOL_CALLING` only; Gemini gets `GROUNDING`; OpenAI gets `JSON_MODE`; etc.

4. **Replace `isinstance` gates in `core.py`** — grep for `isinstance(.*Provider)` and convert each site:
   ```python
   # before
   if isinstance(provider, AnthropicProvider):
       thinking_budget = self._thinking.allocate(...)
   # after
   if ProviderCapability.EXTENDED_THINKING in provider.capabilities:
       thinking_budget = self._thinking.allocate(...)
   ```

5. **Refuse misuse in `thinking_budget.py`** — `ThinkingBudgetOptimizer.allocate(provider, ...)` raises `CapabilityError` if `EXTENDED_THINKING not in provider.capabilities`. Same for `vision.py`: reject image inputs if `VISION` not declared.

6. **Expose in catalog** — `provider_catalog.py` returns capability flags per entry so the Neovim picker and `/provider` command can render them.

7. **Rebase note** — this agent runs after 10A. If 10A touched the same `core.py` gate site, rebase cleanly; gates are generally orthogonal (10A touches the assembly block; 10C touches feature-dispatch sites scattered through `run_turn` and adjacent methods).

### Files to create/modify

**Create:**
- `poor_cli/providers/capability.py`
- `tests/test_provider_capability.py`

**Modify:**
- `poor_cli/providers/base.py` — add `capabilities` class attribute.
- `poor_cli/providers/*_provider.py` — each adapter declares its set.
- `poor_cli/provider_catalog.py` — expose capabilities in catalog entries.
- `poor_cli/core.py` — narrow: replace `isinstance` feature-gates with capability checks.
- `poor_cli/thinking_budget.py` — refuse allocation without `EXTENDED_THINKING`.
- `poor_cli/vision.py` — refuse image inputs without `VISION`.

### Acceptance criteria

- [ ] Every provider adapter declares a non-`NONE` capability set.
- [ ] `grep -r "isinstance.*Provider" poor_cli/core.py` returns no feature-gating hits (non-gate uses like logging are fine — document them).
- [ ] `thinking_budget.allocate()` raises `CapabilityError` for providers without `EXTENDED_THINKING`.
- [ ] `vision.py` rejects image input for providers without `VISION`.
- [ ] `provider_catalog` entries include capabilities.
- [ ] New tests: `test_anthropic_has_extended_thinking`, `test_openai_has_streaming`, `test_ollama_has_no_prompt_caching`, `test_thinking_allocation_refused_without_capability`.
- [ ] All existing tests pass unchanged.

**PRD reference:** prd/020-provider-capability-enum.md

---

## Agent 10D: Extension Model Consolidation

**Pain points addressed:** Four overlapping extensibility mechanisms (skills, custom commands, workflow templates, automations) create option paralysis for users and maintenance multiplication for contributors. Skills stay separate (different concept: instruction libraries); the other three collapse into one `AutomationRule` type.
**Solution reference:** PRD 064 — consolidate extension model (decision (a): merge).
**Expected outcome:** Two extension concepts instead of four: (1) `AutomationRule` covering cron / event / slash triggers with multi-step bodies, (2) skills. Existing user data round-trips through a one-shot migration.

### What to build

A new `poor_cli/automations/` package that absorbs `custom_commands.py`, `workflow_templates.py`, and `automation_manager.py` into a single `AutomationRule` type. Skills remain untouched in `skills.py` / `skill_surfacer.py`. A migration script converts each existing workflow, custom command, and automation into an `AutomationRule` and backs up the originals in `.poor-cli/backup-pre-064/`.

### Implementation details

1. **Core type** in `poor_cli/automations/rules.py`:
   ```python
   @dataclass
   class AutomationRule:
       id: str
       name: str
       triggers: list[Trigger]            # cron | event | slash
       steps: list[Step]                  # prompt | tool_call | shell
       enabled: bool
       scope: Literal["repo", "user"]
   ```

2. **Triggers** in `poor_cli/automations/triggers.py` — tagged union:
   - `CronTrigger(expression: str)`
   - `EventTrigger(event: str, filter: dict | None)`
   - `SlashTrigger(command: str, description: str)`

3. **Steps** in `poor_cli/automations/steps.py` — tagged union:
   - `PromptStep(prompt: str)`
   - `ToolCallStep(tool: str, params: dict)`
   - `ShellStep(command: str, cwd: str | None)`

4. **Migration** in `poor_cli/automations/migration.py`:
   - Backs up `.poor-cli/custom_commands.json`, `workflow_templates.json`, `automations.json` to `.poor-cli/backup-pre-064/`.
   - Converts each:
     - Custom command → `AutomationRule` with a single `SlashTrigger`.
     - Workflow template → `AutomationRule` with `SlashTrigger` + multi-step body.
     - Automation → `AutomationRule` with `CronTrigger` or `EventTrigger` per its existing config.
   - Writes merged result to `.poor-cli/automations.json`.
   - Idempotent — rerunning is a no-op if `.poor-cli/backup-pre-064/` already exists.

5. **Command surface preservation** — `/workflow`, `/automation`, `/commands` continue to work as aliases into the unified `AutomationRule` store. Users should not notice the collapse.

6. **Delete legacy modules** once migration is verified: remove `custom_commands.py`, `workflow_templates.py`, `automation_manager.py`. Keep `skills.py` and `skill_surfacer.py` untouched.

7. **Update 10B's `handlers/automations.py`** — this is the rebase footprint. 10B's handler file imports from `automation_manager`; update those imports to `poor_cli.automations`. Part of 10D's scope.

8. **Server RPC compatibility** — any RPC method name containing `workflow_*` or `custom_command_*` keeps working via aliases. Do not break existing clients.

### Files to create/modify

**Create:**
- `poor_cli/automations/__init__.py`
- `poor_cli/automations/rules.py`
- `poor_cli/automations/triggers.py`
- `poor_cli/automations/steps.py`
- `poor_cli/automations/migration.py`
- `tests/test_automations.py`

**Modify / delete:**
- `poor_cli/custom_commands.py` — logic absorbed; delete after migration verified.
- `poor_cli/workflow_templates.py` — logic absorbed; delete after migration verified.
- `poor_cli/automation_manager.py` — logic absorbed; delete after migration verified.
- `poor_cli/server/handlers/automations.py` (created by 10B) — update imports to `poor_cli.automations`.
- Any call sites of the three deleted modules — update imports.

**Untouched (explicit non-goal):**
- `poor_cli/skills.py`
- `poor_cli/skill_surfacer.py`
- `poor_cli/skills/*.md`

### Acceptance criteria

- [ ] Every existing workflow / custom command / automation round-trips through the migration script.
- [ ] Backup directory `.poor-cli/backup-pre-064/` contains untouched originals after migration.
- [ ] Migration is idempotent.
- [ ] `/workflow`, `/automation`, `/commands` still function (via aliases).
- [ ] Legacy RPC method names still reachable.
- [ ] Skills left untouched — `skills.py` has zero diff in this PR.
- [ ] `handlers/automations.py` imports from `poor_cli.automations`, not `automation_manager`.
- [ ] Tests: migration round-trip, trigger dispatch per type, step execution per type.

**PRD reference:** prd/064-extension-model-consolidation.md
