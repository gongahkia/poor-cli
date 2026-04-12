# PRD 017: Pre-slice `core.py` into empty section modules

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** large (1–2w)
- **Blocks:** 018, 020, 021 and anything touching core.py
- **Blocked by:** 001, 002
- **Files it mutates:**
  - `poor_cli/core.py` (split into sections — this is the whole PRD)
  - Importers of `core` throughout the repo (imports only)
- **New files it adds:**
  - `poor_cli/agent_loop.py`
  - `poor_cli/tool_dispatch.py`
  - `poor_cli/turn_lifecycle.py`
  - `tests/test_core_pre_slice.py`

---

## 1. Problem

`poor_cli/core.py` is 6,134 lines and owns too many concerns: agent loop, tool dispatch, permission gating, context assembly, plan mode, checkpoint triggers, economy, architect mode. [`LEARNING.md` §2.1](../LEARNING.md) and LONGTERM-TODO C3 both call for decomposition.

This PRD is **the pre-split step**: extract the large-but-already-cohesive sections into their own modules *without changing behavior*, so follow-on PRDs can work on any section without serializing.

## 2. Current state

`core.py` contains (approximately):
- `PoorCLICore` class (the god object).
- `~50 self._* attributes` at construction.
- The agent loop (`async def run_turn(...)`).
- Tool dispatch (`async def _execute_tool(...)`).
- Context assembly glue (though `context_engine.py` already exists).
- Permission gating call sites (though `permission_engine.py` already exists).
- Plan mode orchestration (though `plan_mode.py` exists).
- Economy updates (though `economy.py` exists).

Much of the work is glue, not logic. That's the target.

## 3. Goal & non-goals

**Goal:** `core.py` stays the orchestration hub but delegates agent-loop, tool-dispatch, and turn-lifecycle responsibilities to three new modules. `core.py` drops to ~2,500 lines after this PRD; PRD 018 will take another 500 via `ContextAssemblyOrchestrator`; PRD 021 locks the ceiling at 1,000.

**Non-goals:**
- Do not change any behavior. Every test must still pass unchanged.
- Do not change any public API of `PoorCLICore`.
- Do not extract context assembly — that's PRD 018.
- Do not split config.py in this PRD.

## 4. Design

### 4.1 Targets (section → module)

| Section in core.py (rough) | New module | Exports |
|---|---|---|
| Agent loop (the turn orchestration: send → stream → tool → repeat) | `poor_cli/agent_loop.py` | `AgentLoop` class, `run_turn(ctx, core)` |
| Tool dispatch (resolve tool, gate via permission, execute, transform result) | `poor_cli/tool_dispatch.py` | `ToolDispatcher` class |
| Turn lifecycle helpers (checkpoints around turns, audit log, economy post-commit) | `poor_cli/turn_lifecycle.py` | `TurnLifecycle` class |

### 4.2 Refactor shape

`PoorCLICore.__init__` instantiates the three helpers and delegates:

```python
# poor_cli/core.py (shape, after)
class PoorCLICore:
    def __init__(self, ...):
        ...  # existing setup
        self._agent_loop = AgentLoop(self)
        self._tool_dispatch = ToolDispatcher(self)
        self._turn_lifecycle = TurnLifecycle(self)

    async def run_turn(self, prompt: str, **kw) -> TurnResult:
        return await self._agent_loop.run(prompt, **kw)
```

The helpers hold back-refs to `core` (to avoid a giant constructor) but each extracts a **specific, nameable** slice. This is an *extract class* refactor, not a clean-room rewrite.

### 4.3 Order of operations (critical)

1. Extract `turn_lifecycle.py` first (smallest, least tangled).
2. Extract `tool_dispatch.py` (depends on permission_engine, already modular).
3. Extract `agent_loop.py` last (depends on both above).

Each extraction lands as its own commit, each ships passing tests, each keeps behavior identical.

## 5. Files to create / modify / delete

**Create**
- `poor_cli/agent_loop.py`
- `poor_cli/tool_dispatch.py`
- `poor_cli/turn_lifecycle.py`
- `tests/test_core_pre_slice.py`

**Modify**
- `poor_cli/core.py` — remove the extracted code; add delegating thunks.
- Importers of `core` (none should break; surface is unchanged).

**Delete** — nothing.

## 6. Implementation plan

Each step is a commit.

1. Identify the section boundaries in `core.py`. Use line ranges that correspond to the three targets. Document in the PR description with starting/ending line numbers.
2. **Extract `turn_lifecycle.py`**: move the turn-boundary code (start-of-turn checkpoint, end-of-turn audit, end-of-turn economy update). Create `TurnLifecycle(core)` class holding a core ref. Replace the old code in `core.py` with `self._turn_lifecycle.start(...)` / `.end(...)` calls.
3. Run `make test`. Must pass unchanged.
4. **Extract `tool_dispatch.py`**: move tool resolution + permission call + execution + result transform. Keep hooks for PRD 028 output filtering.
5. Run `make test`.
6. **Extract `agent_loop.py`**: move the `run_turn` loop body. `core.py::run_turn` becomes a one-line delegate.
7. Run `make test`.
8. Write `tests/test_core_pre_slice.py`: assert line counts (`core.py < 3_000`), assert new modules exist, assert `AgentLoop`/`ToolDispatcher`/`TurnLifecycle` are importable and have the expected methods, assert `PoorCLICore` public surface is unchanged.
9. `make lint && make test`.

🔴 **Risk marker:** mid-PRD, revert is easy because each extraction is its own commit. If any extraction breaks behavior, revert that commit and analyze.

## 7. Testing & acceptance criteria

**New tests (`tests/test_core_pre_slice.py`)**
- `test_agent_loop_importable`
- `test_tool_dispatch_importable`
- `test_turn_lifecycle_importable`
- `test_core_py_under_3000_lines` — regression guard.
- `test_poor_cli_core_public_surface_unchanged` — snapshot of `dir(PoorCLICore)`.

**Existing tests** must continue to pass **unchanged**. No test should need to be modified; if a test needs an import path change, flag it.

**Commands**
- `make lint && make test`

**Done criterion**
- [ ] Three new modules exist with the shapes above.
- [ ] `core.py` shrunk to ≤3,000 lines.
- [ ] No test modifications.
- [ ] Public `PoorCLICore` surface unchanged.

## 8. Rollback / risk

Medium-high. `core.py` is the heart. Mitigations:

- Each extract is its own commit.
- No behavior changes.
- Full test suite runs between commits.
- If a user-visible regression surfaces after merge, revert the PR in one `git revert`.

## 9. Out-of-scope & boundary

- 🚫 Do not modify tool schemas.
- 🚫 Do not change config.py.
- 🚫 Do not extract context assembly (PRD 018).
- 🚫 Do not touch `server/runtime.py` (PRD 019).
- 🚫 Do not rename public methods.

## 10. Related PRDs & references

- PRD 018 (ContextAssemblyOrchestrator) — builds on this.
- PRD 020 (ProviderCapability).
- PRD 021 (CI gate).
- LONGTERM-TODO C3.
- LEARNING.md §2.1.
