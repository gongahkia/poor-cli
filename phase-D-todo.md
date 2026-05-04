# Phase D — Ambitious

**Goal:** features that change what the harness *is*. None are blocking; all are independently shippable. Highest scope, highest payoff.

**Order (commit each separately):**
1. Spec/PRD-driven dev mode
2. Agent teams with shared scratchpad
3. Time-travel checkpoint tree (TUI)
4. MCP marketplace browser (TUI)
5. Speculative draft model

**Cross-cutting rules:**
- One commit per feature.
- Run full pytest after each.
- Each feature lands behind a config flag default-off so it can be reverted by toggling, not just `git revert`.
- Honor B3 staging; honor C3 permission DSL.
- Optional new deps allowed but must be `pyproject.toml` extras, never required.

**Dependencies on Phase A/B/C:** D2 + D5 use B1 repo-map for context. D3 uses A3 `pre_checkpoint`/`post_checkpoint` hooks. D1 uses C1 markdown subagents to parameterize the planner agent. D4 uses C3 DSL to scope MCP-installed tools.

---

## D1 — Spec/PRD-driven dev mode

### Goal
User writes a PRD/spec; agent produces an ordered subtask list, runs them with checkpoints between, surfaces progress with explicit human checkpoints. Builds on `architect_mode.py` (which already splits architect/editor models) but elevates it to a multi-stage workflow.

### Verified anchors
- `poor_cli/architect_mode.py` — `ArchitectPlan`, `validate_plan`, `PRESET_PAIRS`, per-phase cost tracking already exist.
- `poor_cli/plan_mode.py` + `poor_cli/plan_analyzer.py` — existing plan surfaces.
- `poor_cli/checkpoint.py` — checkpoint creation per phase.
- `poor_cli/agent_definitions.py` (from C1) — supplies the planner / executor / reviewer subagent definitions.

### Files to create
- `poor_cli/spec_mode.py` — orchestrator: parse PRD → generate subtask DAG → run sequentially with checkpoints.
- `poor_cli/cli/spec_cmds.py` — `poor-cli spec new|run|status|abort`.
- `.poor-cli/agents/planner.md`, `.poor-cli/agents/executor.md`, `.poor-cli/agents/reviewer.md` (sample definitions).
- `tests/test_spec_mode.py`.

### Files to modify
- `poor_cli/cli_app.py` — wire `poor-cli spec` verb.
- `poor_cli/server/handlers/` — new `spec_handlers.py` with `poor-cli/specRun`, `poor-cli/specStatus`, `poor-cli/specAbort`.
- `poor_cli/tui/textual_app.py` — slash command `/spec <path>` opens a spec progress panel.

### Data model

```python
# poor_cli/spec_mode.py
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class SubtaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Subtask:
    id: str
    title: str
    description: str
    depends_on: List[str] = field(default_factory=list)
    success_criteria: List[str] = field(default_factory=list)
    estimated_tokens: int = 0
    status: SubtaskStatus = SubtaskStatus.PENDING
    checkpoint_id: Optional[str] = None
    notes: str = ""


@dataclass
class SpecRun:
    spec_id: str
    spec_path: str
    title: str
    subtasks: List[Subtask]
    status: str = "pending"          # pending | running | paused | completed | aborted
    current_subtask_id: Optional[str] = None
```

### Workflow
1. **Parse:** PRD is a markdown file. First H1 = title; rest is the spec body. Optional YAML frontmatter for `model`, `provider`, `budget`, `auto_advance` (bool).
2. **Plan:** spawn `planner` subagent (C1) with the PRD body as input. Planner returns JSON matching `Subtask[]` schema. Validate via `architect_mode.validate_plan`.
3. **Confirm:** print plan to TUI; require `/spec confirm` (or auto-advance if frontmatter says so).
4. **Execute:** for each subtask in topological order:
   a. `pre_checkpoint` hook (A3) → checkpoint snapshot → `post_checkpoint`.
   b. Spawn `executor` subagent with subtask description, success criteria, and current repo state.
   c. Wait for completion. If success criteria not met by self-check, mark `BLOCKED`.
   d. Spawn `reviewer` subagent in read-only mode to verify; record findings on subtask.
   e. If reviewer raises blockers: pause spec run; surface for human review.
5. **Resume / abort:** `poor-cli spec status` shows DAG; `poor-cli spec resume` continues from last checkpoint.

### CLI

```
poor-cli spec new <path>                # scaffold a PRD template at <path>
poor-cli spec run <path>                # start a spec run; prints spec_id
poor-cli spec status <spec_id>          # tree view of subtask DAG + status
poor-cli spec abort <spec_id>           # cancel; restore last checkpoint
```

### Persistence
- One spec run per directory `.poor-cli/specs/<spec_id>/`:
  - `spec.json` — `SpecRun` serialized.
  - `events.ndjson` — append-only event log.
  - per-subtask `.poor-cli/specs/<spec_id>/subtasks/<subtask_id>/` with the executor's output, reviewer notes, checkpoint id.

### Test plan
`tests/test_spec_mode.py`:
- Topological sort respects `depends_on`.
- A failing subtask blocks dependents.
- Resume picks up at the next pending subtask in the DAG.
- Aborted spec restores the most recent checkpoint.

### Commit
```
feat(spec): PRD-driven dev mode with checkpointed subtask execution

Adds spec_mode orchestrator that parses a PRD, asks the planner agent
for a subtask DAG, executes via executor + reviewer agents with a
checkpoint per subtask. Pause/resume/abort. New `poor-cli spec` verb.
Sample planner/executor/reviewer agents in .poor-cli/agents/.
```

### Acceptance
- Sample PRD in `tests/fixtures/spec_basic.md` runs end-to-end with mocked subagents and produces 3 checkpoints.
- Resume after kill picks up correctly.
- Pytest green.

---

## D2 — Agent teams with shared scratchpad

### Goal
Coordinated multi-agent runs sharing a structured scratchpad. Roles: planner, executor, reviewer (and any C1-defined custom agents). Reviewer has read-only access to executor's working directory; scratchpad is the only mutable shared state.

### Verified anchors
- `poor_cli/parallel_agents.py` — existing parallel-agents primitive.
- `poor_cli/sub_agent.py` — sub-agent spawn.
- `poor_cli/agent_definitions.py` (from C1) — agent registry.

### Files to create
- `poor_cli/agent_team.py` — orchestrator + scratchpad.
- `tests/test_agent_team.py`.

### Files to modify
- `poor_cli/parallel_agents.py` — add team-aware spawn that wires each subagent to a `TeamScratchpad`.
- `poor_cli/_tool_registry_builder.py` — register tools `scratchpad_read`, `scratchpad_write_section`, `scratchpad_post_message`.

### Scratchpad model

```python
# poor_cli/agent_team.py
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ScratchpadMessage:
    author_agent: str
    role: str               # "info" | "decision" | "blocker" | "request"
    body: str
    ts: str


@dataclass
class TeamScratchpad:
    team_id: str
    sections: Dict[str, str] = field(default_factory=dict)     # named long-form sections
    messages: List[ScratchpadMessage] = field(default_factory=list)

    def write_section(self, name: str, body: str) -> None: ...
    def append_section(self, name: str, body: str) -> None: ...
    def post_message(self, author: str, role: str, body: str) -> ScratchpadMessage: ...
    def to_context(self, max_tokens: int = 4000) -> str: ...    # compact view for next agent's prompt
```

### Coordination protocol
- Planner runs first; writes section `plan` and posts `decision` message with the plan summary.
- Executor reads `plan`; writes section `progress` per subtask; posts `request` messages when blocked.
- Reviewer monitors after each executor pass; writes section `review` and posts `blocker` messages.
- Loop until plan complete, max iterations reached, or blocker requires human input.

### Persistence
- `.poor-cli/teams/<team_id>/scratchpad.json` (sections + messages).
- `.poor-cli/teams/<team_id>/events.ndjson`.

### Tools exposed to agents
- `scratchpad_read(section?: string) -> str` — returns named section or compact view.
- `scratchpad_write_section(name: string, body: string)` — overwrite section.
- `scratchpad_post_message(role: "info"|"decision"|"blocker"|"request", body: string)`.

### Test plan
`tests/test_agent_team.py`:
- Concurrent writes from two stub agents serialize correctly.
- `to_context(max_tokens)` truncates oldest messages first.
- Persistence round-trip preserves all messages and sections.

### Commit
```
feat(agents): agent teams with shared structured scratchpad

Adds TeamScratchpad coordinating planner/executor/reviewer agents via
named sections + role-tagged messages. Three new tools (read/write
section, post message). Persisted under .poor-cli/teams/<id>/.
parallel_agents wires the scratchpad in to each spawn.
```

### Acceptance
- Demo team run with stub agents writes plan → progress → review and exits cleanly.
- Pytest green.

---

## D3 — Time-travel checkpoint tree (TUI)

### Goal
Interactive tree view of all checkpoints in the current session/repo. Branch from any prior turn, rollback, diff between two checkpoints, inspect state.

### Verified anchors
- `poor_cli/checkpoint.py` — ~29k lines; checkpoint creation/restore.
- `poor_cli/branch_tree.py` — already exposes branch-aware history.
- `poor_cli/diff_preview.py` — diff renderer.
- `poor_cli/tui/textual_app.py` — TUI app with `Static`/`Vertical`/`Horizontal` widgets.

### Files to create
- `poor_cli/tui/checkpoint_tree.py` — `Tree` widget population + actions.
- `tests/test_checkpoint_tree_view.py` — smoke for data conversion (no Textual harness).

### Files to modify
- `poor_cli/tui/textual_app.py` — slash command `/timeline` opens the tree as a modal screen; `Esc` closes.
- `poor_cli/server/handlers/timeline.py` (already exists per registry) — extend with `poor-cli/timelineRollback`, `poor-cli/timelineBranch`, `poor-cli/timelineDiff`.

### Tree widget
- Use Textual `Tree` widget. Root = session id. Children = branches (from `branch_tree.py`). Leaves = checkpoints.
- Per checkpoint label: `<timestamp> <reason> (<turn N>)`.
- Key bindings inside the modal:
  - `Enter` — preview (open diff vs current HEAD).
  - `r` — rollback to this checkpoint.
  - `b` — branch from this checkpoint (creates new branch in `branch_tree`).
  - `d` — diff vs another checkpoint (prompt for second selection).
  - `Esc` — close.

### Safety
- Rollback fires `pre_checkpoint` then full state snapshot, restores, fires `checkpoint_restored` (already in HOOK_EVENTS) and `post_checkpoint` (A3).
- Confirm modal before destructive actions (rollback / branch).

### Test plan
`tests/test_checkpoint_tree_view.py`:
- Conversion of `branch_tree` data to `Tree` node payloads is correct.
- Diff request between two checkpoints returns expected hunk count for a fixture.

### Commit
```
feat(tui): time-travel checkpoint tree modal

/timeline opens a Textual Tree showing the branch_tree of all
checkpoints. Enter previews diff, r rolls back, b branches, d diffs
two checkpoints. Reuses checkpoint.py + branch_tree.py + diff_preview.
Rollback fires pre/post_checkpoint hooks (Phase A3).
```

### Acceptance
- Demo session creates 3 checkpoints; `/timeline` shows them; rollback restores correctly.
- Pytest green.

---

## D4 — MCP marketplace browser (TUI)

### Goal
Discover, install, and configure MCP servers from the official MCP registry, inside the TUI. Composes with C3 DSL so newly-installed tools land scoped, not unrestricted.

### Verified anchors
- `poor_cli/mcp/registry.py` — `McpRegistryClient` already implements `search`, `get_versions`. Uses `https://registry.modelcontextprotocol.io`. Requires `aiohttp` (already optional dep).
- `poor_cli/mcp/multi_server.py` — multi-server runtime.
- `poor_cli/mcp/config_store.py` — persistent config for installed servers.

### Files to create
- `poor_cli/tui/mcp_browser.py` — Textual modal screen.
- `tests/test_mcp_browser_state.py`.

### Files to modify
- `poor_cli/mcp/registry.py` — add `install(server_name, version)` that writes a config entry via `config_store.py` and registers tool schemas via `multi_server.py`.
- `poor_cli/server/handlers/mcp.py` (existing) — add `poor-cli/mcpSearch`, `poor-cli/mcpInstall`, `poor-cli/mcpUninstall`, `poor-cli/mcpEnable`, `poor-cli/mcpDisable`.
- `poor_cli/tui/textual_app.py` — slash command `/mcp` opens the marketplace modal.
- `poor_cli/permission_dsl.py` (from C3) — when a new MCP tool is installed, add a default rule `tool: <toolName>; allow: false; reason: "newly installed MCP tool, awaiting review"`.

### Modal layout
- Top bar: search input.
- Left list: server results (name, description, downloads, current install status).
- Right pane: detail view (versions, tools provided, install command).
- Footer keys: `i` install, `u` uninstall, `e` enable/disable, `Enter` view detail, `Esc` close.

### Network handling
- All calls go through `McpRegistryClient`; if `aiohttp` is missing, modal shows "install poor-cli[anthropic,mcp] for marketplace" with the exact pip command.
- Cache search results in `.poor-cli/cache/mcp_search.json` with 5-minute TTL to avoid spamming the registry.

### Test plan
`tests/test_mcp_browser_state.py`:
- Search results parsing handles missing fields gracefully.
- Install path writes to `mcp/config_store.py` and adds the default-deny DSL rule.
- Uninstall removes both config and DSL rule.

### Commit
```
feat(mcp): TUI marketplace browser for the official MCP registry

/mcp opens a Textual modal that searches the MCP registry, shows
versions, and installs/uninstalls servers via mcp/config_store +
multi_server. Newly installed tools land with a default-deny rule
in the permission DSL (Phase C3). 5-minute search cache.
```

### Acceptance
- `/mcp` modal lists registry servers (with stub network in tests).
- Install path writes config and adds DSL rule.
- Pytest green.

---

## D5 — Speculative draft model

### Goal
Local small-model drafter accelerates big-model providers (Anthropic, OpenAI) by proposing several tokens that the big model only verifies. Net: lower latency + lower output-token cost on long generations.

**Caveat:** this is the heaviest item. It only pays off when running against a provider that supports verification semantics, or when used purely as a "shadow predictor" for next-tool guesses. Implement the latter first; the former requires provider-specific support that may not exist yet.

### Approach (Phase 1 — shadow predictor, ship this)

The drafter does NOT alter provider responses. It:
1. Runs a small local model (Ollama / HF) in parallel with the big provider call.
2. Predicts the next tool call (tool name + likely args).
3. Pre-warms tool inputs (e.g., starts the file read, the shell command's working directory check) so when the big model issues the same call, the result is already cached.
4. If the big model's call differs, throw the cache entry away — no harm done.

### Approach (Phase 2 — true speculative, deferred)
True speculative decoding requires provider-side draft acceptance. As of writing, Anthropic and OpenAI do not publicly expose this in their HTTP APIs in a useful way for tool-use traces. Document this in the file but do not implement until a provider exposes it.

### Verified anchors
- `poor_cli/providers/ollama_provider.py` — local provider already integrated.
- `poor_cli/tool_cache.py` + `poor_cli/block_cache.py` + `poor_cli/semantic_cache.py` — caches the predictor warms.
- `poor_cli/model_router.py` — task complexity classifier; reuse to gate when to spend on shadow prediction.

### Files to create
- `poor_cli/speculative_draft.py` — predictor + cache-warmer.
- `bench/speculative_draft_savings.py`.
- `tests/test_speculative_draft.py`.

### Files to modify
- `poor_cli/core_turn_lifecycle.py` — at provider call start, kick off `predict_next_tool(...)` as an asyncio task; cancel on big-model response received.
- `poor_cli/tool_cache.py` — accept pre-warmed entries with provenance flag `from_speculation: true` for audit.
- `poor_cli/repo_config.py` — add `speculative.enabled` (default `false`), `speculative.draft_provider` (default `ollama`), `speculative.draft_model` (default `llama3.1`).

### Algorithm sketch

```python
# poor_cli/speculative_draft.py
async def predict_next_tool(history: list, tools: list, draft_provider, draft_model) -> dict | None:
    """Return {"tool": str, "args": dict, "confidence": float} or None.

    Confidence below 0.5 -> caller should not warm.
    """

async def warm_for_prediction(prediction: dict, tool_dispatcher) -> None:
    """Pre-execute read-only prefixes of the predicted call.
    NEVER execute write tools or destructive shell commands."""
```

### Safety
- Hard whitelist of tools that may be pre-warmed: `read_file`, `glob_files`, `grep_files`, `git_status`, `git_diff`, `list_directory`, `semantic_search`. Anything else: skip.
- Pre-warmed cache entries carry `from_speculation: true` and a TTL of one turn — never persisted across turns.
- Audit log records each prediction + hit/miss for the bench script.

### Benchmark
`bench/speculative_draft_savings.py`:
- Replay a captured session log; measure cache-hit rate from speculation.
- Report mean wall-clock saved per turn.
- Exit non-zero if hit rate < 25%.

### Test plan
`tests/test_speculative_draft.py`:
- Predictor returns valid shape from a stub provider.
- Cache-warmer skips non-whitelisted tools.
- Cancellation works when big-model returns first.

### Commit
```
feat(speculation): shadow next-tool predictor pre-warms read tool caches

Adds local-model speculative_draft that predicts the agent's next
tool call and pre-executes read-only prefixes so block/tool/semantic
caches are warm by the time the big model commits. Whitelisted
tools only; no writes. Default-off via speculative.enabled. Bench
shows ≥25% read-tool cache-hit rate from speculation.
```

### Acceptance
- Bench reports ≥25% speculation cache-hit rate.
- Disabled-by-default flag works.
- Pytest green.

---

## End-of-phase checklist

- [ ] 5 commits on `main`.
- [ ] `poor-cli spec run <fixture>` completes.
- [ ] Demo team run produces scratchpad transcript.
- [ ] `/timeline` and `/mcp` modals work in TUI.
- [ ] `bench/speculative_draft_savings.py` passes its threshold.
- [ ] Pytest green.

---

## Final repository state after all phases

After Phases A-D complete (15 commits), the repo will:
- Be visibly token-aware (HUD, repo-map, prompt optimizer, speculation).
- Have parity-or-better governance (hooks 26, edit staging, permission DSL).
- Support markdown-defined agents, detached runs, agent teams, spec-driven dev.
- Match Claude Code / Codex / Aider / Cursor on enough core surfaces to compete.
- Stay single-operator (no multiplayer regressions).
- Have one bench script per token-saving feature so the wins remain measurable as the codebase evolves.
