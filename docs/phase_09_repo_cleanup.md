# Phase 9: Repo Cleanup & Dead Code Purge

**Priority:** High — removes carrying cost (cold-start imports, contributor confusion, misleading docs) and installs guardrails against monolith regrowth.
**Estimated agents:** 6 (mixed parallel / serialized — see ordering table).
**Dependencies:** 9C depends on 9B (stub decisions gate relocation). 9D should land after 9B (README references to archived stubs). 9F depends on 9E (line-count floor only enforceable after pre-slice).
**Philosophy:** Delete first, relocate second, rewrite docs third, then CI-pin the result. Every agent here is either a destructive cleanup or a regression guard. No new product features.

---

## File-scope map (verify disjointness at a glance)

| Agent | Primary scope | Creates | Deletes / Modifies |
|---|---|---|---|
| 9A | retired front-end tree | — | Deletes retired client subtrees |
| 9B | Stub modules (decision + cleanup) | — | `poor_cli/docker_sandbox.py`, `poor_cli/speculative_decoding.py`, `poor_cli/rtk_integration.py`, `poor_cli/kv_cache_store.py`; docs/README references |
| 9C | Research relocation | `poor_cli/research/__init__.py`, `poor_cli/research/README.md` | Moves `latent_communication.py`, `neural_code_encoder.py`, `embeddings.py`†, `code_tokenizer.py`† into `poor_cli/research/`; `poor_cli/__init__.py`, `pyproject.toml` |
| 9D | Top-level docs + screenshots | `asset/reference/v6/*.png` | `README.md`, `nvim-poor-cli/README.md`; deletes `asset/reference/v5/*.png` |
| 9E | `core.py` pre-slice | `poor_cli/agent_loop.py`, `poor_cli/tool_dispatch.py`, `poor_cli/turn_lifecycle.py`, `tests/test_core_pre_slice.py` | `poor_cli/core.py`, importers' import paths |
| 9F | CI size gate | `scripts/check_line_budgets.py` | `.github/workflows/tests.yml`, `Makefile` |

† Only moved if not actively used in production call sites (9C audits first).

---

## File-scope collisions (explicit)

1. **9B ↔ 9C** both list `poor_cli/speculative_decoding.py` and `poor_cli/kv_cache_store.py`. 9B decided `speculative_decoding.py` is deleted and `kv_cache_store.py` ships in place; 9C must not relocate either file. **Serialization: 9B must land before 9C.**

2. **9B ↔ 9D** both touch `README.md`. 9B keeps the shipped Docker sandbox path and only strikes archived-stub claims; 9D performs a full rewrite. **Serialization: 9D after 9B**, or 9D explicitly re-verifies 9B's removals are not reintroduced. Preferred: 9D runs last and treats 9B's edits as a merge conflict to resolve in favor of 9D's new structure.

3. **9E ↔ 9F** both concern `poor_cli/core.py` size. 9E shrinks it (target ≤3,000 lines); 9F pins the ceiling (≤1,000 lines, with budget slack). **Serialization: 9E must land before 9F.**

4. **9A ↔ 9D** do not collide (9A deletes retired front-end sources; 9D touches `asset/reference/`). Run in parallel.

5. **9C ↔ 9E** do not collide (disjoint module trees) but both edit `poor_cli/__init__.py`. Light-touch edits; run sequentially or resolve via small merge. Preferred order: 9E first (structural), then 9C (adds research package export).

### Recommended wave ordering

- **Wave 9.i (parallel):** 9A, 9B, 9E.
- **Wave 9.ii (parallel, after 9.i):** 9C (needs 9B), 9F (needs 9E), 9D (cleanest after 9B).

---

## Agent 9A: Remove retired front-ends

**Pain points addressed:** contributor confusion, repo bloat, misleading top-level tree.

### Outcome

Decision (b) landed: the retired Emacs, desktop, Telegram, TUI, and VS Code client sources were deleted entirely. Git history remains the recovery path; no pointer file was created.

### Implementation details

1. Grep for live references before deletion.
2. Use `git rm -r` so git records deletions cleanly.
3. Scrub stale doc links.
4. `.gitignore`: remove any retired-client patterns if present.
5. Run `make lint && make test` — should be unchanged.

### Files to create/modify

- **Delete:** retired Emacs, desktop, Telegram, TUI, and VS Code client sources.
- **Create:** none.
- **Modify:** any doc with dead links to retired front-end sources.

### Acceptance criteria

- [ ] `make lint && make test` green.
- [ ] No source/test reference to the retired client tree remains.
- [ ] The retired client tree is gone.
- [ ] Boundary respected: `asset/` untouched (9D owns screenshots). `docs/` untouched beyond link fixes (9D owns README rewrite).

### Rollback

Low risk. Git history preserves everything.

---

## Agent 9B: Decide and execute on dead stub modules

**Pain points addressed:** "concept car" stubs shipping with no user value; misleading README; contributor cognitive tax.

## Outcome

| File | Decision | Evidence / owner | Action |
|---|---|---|---|
| `poor_cli/docker_sandbox.py` | ship | Runtime import in `tools_async.py`, RPC status handler, Neovim status command, tests in `tests/test_docker_sandbox.py` | Leave file intact; README/LONGTERM sandbox docs may stay. |
| `poor_cli/speculative_decoding.py` | archive/delete | No end-to-end vLLM provider path; Ollama had diagnostics only; default archive-unless-shown-shipped applied. | Delete module, remove imports/config/tests, prune Phase 7 prompt docs, add CI import guard. |
| `poor_cli/rtk_integration.py` | ship via PRD 026 | PRD 026 / Agent 13C exists in `docs/phase_13_protocol_streaming.md`; current module is imported and tested. | Leave file intact; PRD 026 owns RTK-lite follow-up. |
| `poor_cli/kv_cache_store.py` | ship | Runtime-gated by `maybe_init_kv_cache()` and active-provider check; imported by `core.py`; tests in `tests/test_kv_cache.py`. | Leave file intact; no 9C relocation. |

No additional locally listed concept-car stubs were provided for 9B.

### What to build

Resolve the fate of four stub/dead-integration modules. Each is either (a) shipped end-to-end with user-visible value, (b) archive/delete with docs updated, or (c) relocated to `poor_cli/research/` (handoff to 9C).

| File | LOC | Wired? | User-visible surface | Recommended |
|---|---|---|---|---|
| `poor_cli/docker_sandbox.py` | ~95 | Yes | Bash tool Docker sandbox path + RPC/Neovim status | ship |
| `poor_cli/speculative_decoding.py` | ~214 | Diagnostics only | — | archive/delete |
| `poor_cli/rtk_integration.py` | ~70 | Yes | Enhanced bash tool RTK wrapping | ship via PRD 026 |
| `poor_cli/kv_cache_store.py` | ~370 | Runtime-gated for local providers | Config + core prompt ordering | ship with runtime gate on local-provider presence |

### DECISION REQUIRED (9B) — four separate decisions

**4.1 `docker_sandbox.py`** — Decision: (a) ship. The module is wired into bash execution and RPC status and has tests. Leave file and docs intact.

**4.2 `speculative_decoding.py`** — Decision: (c) delete outright. It had helper/test coverage but no end-to-end vLLM provider path; remove module, imports, config, tests, and Phase 7 promises.

**4.3 `rtk_integration.py`** — (a) ship as Python-only first cut via PRD 026 (`git status --porcelain` filter, no Rust binary needed initially); (b) delete and retract the Phase 23 promise in SOLUTIONS.md. **Recommended: (a) via PRD 026** — savings are real on one command even without a Rust binary.

**4.4 `kv_cache_store.py`** — (a) ship: guard at init, only load when a local provider (`ollama`) is active; (b) move to `poor_cli/research/` and lazy-import; (c) delete. **Recommended: (a).**

### Implementation details

1. **Decision pass.** Owner records outcome per module in an `## Outcome` block at the top of this section/PRD. This phase does not itself implement "ship" decisions — those spawn or transfer to dedicated PRDs.
2. **Archive path.** For each "archive/delete" decision:
   - Remove the file.
   - Scrub references in `SOLUTIONS.md`, `LONGTERM-TODO.md`, any `docs/phase_0*.md` that promised the feature, and `README.md`.
3. **Relocate path.** For each "research relocation" decision: do **not** move the file here. Mark it for 9C and let the relocation PRD handle it.
4. **Ship path.** For each "ship" decision: transfer scope to the dedicated PRD where needed (PRD 026 for RTK-lite). `docker_sandbox.py` and `kv_cache_store.py` already have runtime paths and tests here.
5. Final grep guard: `grep -rn "docker_sandbox\|speculative_decoding\|rtk_integration\|kv_cache_store" poor_cli/ docs/ README.md` — results must be consistent with the outcome table.

### Files to create/modify

- **Delete (per decision):** whichever of `poor_cli/docker_sandbox.py`, `poor_cli/speculative_decoding.py`, `poor_cli/rtk_integration.py`, `poor_cli/kv_cache_store.py` are marked archive/delete.
- **Modify:** `README.md` (strike Docker sandbox), `SOLUTIONS.md`, `LONGTERM-TODO.md`, `docs/phase_0*.md` — scrub promises for archived modules.
- **Create:** none.
- **Collision note:** touches `README.md` — 9D rewrites it subsequently; `speculative_decoding.py` is deleted and `kv_cache_store.py` stays in place, so 9C must not move either file.

### Acceptance criteria

- [ ] Outcome block written for all four modules.
- [ ] Archive decisions: files removed, docs scrubbed, README no longer promises features that aren't shipped.
- [ ] Ship decisions: ownership transferred to target PRD, referenced by ID.
- [ ] Relocate decisions: file flagged for 9C (not yet moved).
- [ ] `make lint && make test` green.
- [ ] Grep guard clean and consistent with the outcome table.

### Out-of-scope

- Do not implement new features beyond the cleanup required by decisions.
- Do not rewrite README broadly (9D owns that).

---

## Agent 9C: Relocate research modules behind feature flags

**Pain points addressed:** cold-start time, contributor confusion (production vs research), noise in top-level package.

### What to build

Move research-only modules from `poor_cli/` into a new `poor_cli/research/` subpackage. Gate each behind a `[research]` config flag (default false). Contributors reading `poor_cli/` see only production code; `import poor_cli` does not eagerly import any research module.

### Implementation details

1. **Confirm 9B outcomes.** Do not move any module 9B marked for deletion.
2. **Layout:**
   ```
   poor_cli/research/
     __init__.py          # feature-flag aware; no * exports
     README.md            # "Research code. Not part of production agent loop."
     latent_communication.py
     neural_code_encoder.py
   ```
3. **`poor_cli/research/__init__.py` contents** (docstring-only, explicit about flag usage):
   ```python
   """
   Research modules. Not imported at poor-cli startup.
   Enable individually via config:
       [research]
       latent_communication = false
       neural_code_encoder  = false
   """
   # explicit: no * imports; callers must
   # `from poor_cli.research import latent_communication`
   ```
4. **`poor_cli/research/README.md`** must state the relocation rationale and the rule: any new research module lands behind a flag, default off.
5. **Move with `git mv`** to preserve blame.
6. **Lazy-import guard** at every production call site:
   ```python
   def _maybe_get_latent():
       if not config.get("research.latent_communication", False):
           return None
       from poor_cli.research import latent_communication
       return latent_communication
   ```
7. **Config defaults** (coordinate with preferences-schema PRD 003) — add a `[research]` section to `preferences.json`:
   ```json
   {"research": {"latent_communication": false, "neural_code_encoder": false,
      "kv_cache_store": false}}
   ```
8. **Audit `embeddings.py` and `code_tokenizer.py`** before moving. If `semantic_cache` or another production module imports them, leave them in `poor_cli/`. PRD 058 may ship `code_tokenizer.py` — defer if so.
9. **Update `pyproject.toml::[tool.setuptools].packages`** to include `"poor_cli.research"`.
10. **Grep for stale imports:** `grep -rn "from poor_cli.latent_communication\|from poor_cli.neural_code_encoder"` and fix each (switch to lazy-guard pattern in production code).
11. If a caller was silently relying on a top-level export, restore a re-export with a `DeprecationWarning` rather than breaking.

### Files to create/modify

- **Create:** `poor_cli/research/__init__.py`, `poor_cli/research/README.md`.
- **Move (git mv):** `poor_cli/latent_communication.py`, `poor_cli/neural_code_encoder.py`, `poor_cli/embeddings.py`†, `poor_cli/code_tokenizer.py`† → `poor_cli/research/`.
- **Modify:** `poor_cli/__init__.py` (drop top-level re-exports), `pyproject.toml` (package list), all production call sites switching to lazy-guard imports.
- **Delete:** none (9B owns deletions).
- **Collision note:** 9B deleted `speculative_decoding.py` and kept `kv_cache_store.py` in place — 9C must not move either file.

### Acceptance criteria

- [ ] All research modules live under `poor_cli/research/`.
- [ ] `tests/test_research_relocation.py::test_research_modules_not_imported_by_default` passes — after `import poor_cli`, inspect `sys.modules` and assert no `poor_cli.research.*` key present.
- [ ] `tests/test_research_relocation.py::test_feature_flag_enables_research_module` passes.
- [ ] Cold-start measurement documented in PR body (before/after via `python3 -c "import time; s=time.time(); import poor_cli; print(time.time()-s)"`).
- [ ] `make lint && make test` green.

### Out-of-scope

- Do not modify research module internals.
- Do not delete anything (9B owns deletions).
- Do not enable any research feature by default.

---

## Agent 9D: Rewrite README and purge stale TUI screenshots

**Pain points addressed:** misleading front door (TUI screenshots, dual install paths, dead client references), adoption friction.

### Current state (what's wrong today)

- TUI screenshots (`asset/reference/v5/*.png`) above the fold.
- Dual install paths (CLI + TUI + plugin), some retired.
- Multiplayer and archived Telegram/desktop not clearly deprecated.
- No demo GIF (adoption blocker, but stretch goal for this phase).

### What to build

Rewrite `README.md` as a Neovim-plugin README with the Python server/agent backend. Replace v5 TUI screenshots with v6 Neovim captures. Scrub references to retired clients (TUI, Telegram, desktop, Emacs, VS Code). Align `nvim-poor-cli/README.md` against the new top-level structure.

### Implementation details

1. **New README structure (top-down):**
   1. Badges (keep).
   2. Logo + one-line hook ("Provider-agnostic BYOK AI coding agent — Neovim-native, multiplayer-ready").
   3. Hero screenshot (v6/1.png).
   4. Install (pip + lazy.nvim snippet, exact as in `nvim-poor-cli/README.md`).
   5. Quickstart (3 steps: install, set `GEMINI_API_KEY`, `:PoorCliChat`).
   6. Features (short bullets — link to docs for depth).
   7. Model / provider support table.
   8. Multiplayer (one paragraph + link to `docs/MULTIPLAYER.md`).
   9. Commands link to plugin README rather than duplicating.
   10. Contributing / license / acknowledgements.
2. **v6 screenshots** to capture into `asset/reference/v6/`:
   - `1.png` — Neovim with chat panel open mid-response.
   - `2.png` — Diff Review panel (reuse chat screenshot if PRD 014 hasn't landed).
   - `3.png` — Cost HUD + lualine (post-PRD 016; placeholder otherwise).
   - `4.png` — Onboarding wizard step.
   - `5.png` — Panels (tasks/checkpoints/sessions).
   If owner cannot provide captures in time, ship labeled placeholders with `TODO: real screenshot` comments.
3. **Delete v5 screenshots** (or move to `asset/reference/archive/v5/`).
4. **Dead-reference scrub:** `grep -rn -i "tui\|telegram\|desktop\|emacs" README.md docs/` — remove each hit unless it is historically framed.
5. **Alignment pass on `nvim-poor-cli/README.md`** — edits only where it contradicts the new top-level README; do not rewrite.
6. **Confirm badges and CI links still resolve.**
7. `make lint && make test` (nothing code-level changed; sanity check only).

### Boundaries

- Do not create a documentation site (out-of-scope; LONGTERM-TODO H4).
- Do not touch `docs/*.md` content beyond link fixes.
- Do not ship an asciinema demo or `asset/demo.gif` in this phase — stretch / defer.

### Files to create/modify

- **Create:** `asset/reference/v6/*.png`.
- **Modify:** `README.md` (full rewrite), `nvim-poor-cli/README.md` (alignment only).
- **Delete:** `asset/reference/v5/*.png` (or relocate to `asset/reference/archive/v5/`).
- **Collision note:** touches `README.md` after 9B strikes archived-stub claims — resolve any merge in favor of 9D's structure, re-verify 9B's scrubs persist.

### Acceptance criteria

- [ ] README reads naturally above-the-fold on a first-time visit.
- [ ] All links resolve.
- [ ] No references to TUI / Telegram / desktop / Emacs / VS Code clients.
- [ ] v5 screenshots gone or archived; v6 present (real or clearly-labeled placeholders).
- [ ] `nvim-poor-cli/README.md` does not contradict top-level.
- [ ] `make lint && make test` green (sanity only; no code changed).

---

## Agent 9E: Pre-slice `core.py` into section modules

**Pain points addressed:** `core.py` is 6,134 lines — parallel work on the god object serializes through whoever edits it first.

### What to build

Extract three cohesive slices from `poor_cli/core.py` into new modules **without changing behavior**. Target: `core.py` drops from ~6,100 to ≤3,000 lines after this phase. A later decomposition PRD will take another slice (context assembly); 9F locks the ceiling.

This is an **extract class** refactor, not a clean-room rewrite. `core.py` currently owns: `PoorCLICore` god object with ~50 `self._*` attributes, agent loop (`run_turn`), tool dispatch (`_execute_tool`), context-assembly glue (though `context_engine.py` exists), permission gating call sites (though `permission_engine.py` exists), plan mode orchestration (though `plan_mode.py` exists), economy updates (though `economy.py` exists). Much of the work is glue, not logic — that is the target.

### Implementation details

1. **Section → module map:**

   | Section in `core.py` | New module | Exports |
   |---|---|---|
   | Agent loop (send → stream → tool → repeat) | `poor_cli/agent_loop.py` | `AgentLoop` class, `run_turn(ctx, core)` |
   | Tool dispatch (resolve → gate via permission → execute → transform result; keep hooks for output filtering) | `poor_cli/tool_dispatch.py` | `ToolDispatcher` class |
   | Turn lifecycle (start-of-turn checkpoint, end-of-turn audit log, end-of-turn economy update) | `poor_cli/turn_lifecycle.py` | `TurnLifecycle` class |

2. **Refactor shape:** each helper holds a back-ref to `core` to avoid ballooning constructors. `PoorCLICore.__init__` instantiates all three; `run_turn` becomes a one-line delegate:
   ```python
   class PoorCLICore:
       def __init__(self, ...):
           ...  # existing setup
           self._agent_loop = AgentLoop(self)
           self._tool_dispatch = ToolDispatcher(self)
           self._turn_lifecycle = TurnLifecycle(self)

       async def run_turn(self, prompt: str, **kw) -> TurnResult:
           return await self._agent_loop.run(prompt, **kw)
   ```

3. **Order of operations (critical — each step is its own commit, each ships passing tests):**
   1. Identify section boundaries in `core.py` by line range; document in PR body.
   2. Extract `turn_lifecycle.py` (smallest, least tangled). Run `make test`.
   3. Extract `tool_dispatch.py` (depends on `permission_engine`, already modular). Run `make test`.
   4. Extract `agent_loop.py` (depends on both above). Run `make test`.
   5. Write `tests/test_core_pre_slice.py`.
   6. `make lint && make test`.

4. **Public surface invariance.** `dir(PoorCLICore)` snapshot must not change. No existing test modifications should be required; if any test needs an import path change, flag it in the PR.

5. **PR body must document** starting/ending line ranges for each extracted section so reviewers can diff section-by-section.

6. **Risk mitigation:** mid-phase revert is easy because each extraction is its own commit. If any extraction breaks behavior, revert that commit and analyze.

### Out-of-scope

- Do not change any behavior — every existing test must pass unchanged.
- Do not change any public API of `PoorCLICore`.
- Do not extract context assembly (separate PRD 018 handles `ContextAssemblyOrchestrator`).
- Do not split `config.py` in this phase.
- Do not touch `server/runtime.py`.
- Do not rename public methods.
- Do not modify tool schemas.

### Files to create/modify

- **Create:** `poor_cli/agent_loop.py`, `poor_cli/tool_dispatch.py`, `poor_cli/turn_lifecycle.py`, `tests/test_core_pre_slice.py`.
- **Modify:** `poor_cli/core.py` (remove extracted code, add delegating thunks); importers of `core` (import paths only if needed — surface unchanged).
- **Delete:** none.
- **Collision note:** lightly touches `poor_cli/__init__.py` alongside 9C. Land 9E first.

### Acceptance criteria

- [ ] Three new modules exist with the declared classes and exports.
- [ ] `poor_cli/core.py` ≤ 3,000 lines.
- [ ] `tests/test_core_pre_slice.py` covers: `test_agent_loop_importable`, `test_tool_dispatch_importable`, `test_turn_lifecycle_importable`, `test_core_py_under_3000_lines` (regression guard), `test_poor_cli_core_public_surface_unchanged` (snapshot of `dir(PoorCLICore)`).
- [ ] No existing tests modified.
- [ ] `make lint && make test` green after each extraction commit.
- [ ] Behavior unchanged (no user-visible delta).
- [ ] If user-visible regression surfaces post-merge, single `git revert` on the PR undoes cleanly.

---

## Agent 9F: CI gate — pin monolith sizes

**Pain points addressed:** without a line-count gate, `core.py` regrows to 6,000 lines one feature at a time.

### What to build

Add a CI step (and `make lint-sizes` target) that fails the build when tracked monoliths exceed their hard limits. Must land **after** 9E so `core.py` actually fits under its cap with budget slack.

### Implementation details

1. **Hard limits** (`scripts/check_line_budgets.py`):
   ```python
   LINE_LIMITS = {
       "poor_cli/core.py":           1_000,
       "poor_cli/server/runtime.py": 5_600,  # Phase 10B owns the split
       "poor_cli/config.py":         1_500,
       "poor_cli/tools_async.py":    4_300,  # pre-existing monolith
       "poor_cli/multiplayer.py":    2_150,  # PRD 063 owns fate
       "poor_cli/core_turn_lifecycle.py": 2_700,
       "__default__":                2_000,
   }
   ```

   CI and pre-commit report overages as `path current/limit (+delta)`, for example `poor_cli/core.py 1124/1000 (+124)`.

2. **Full script** (reference implementation):
   ```python
   #!/usr/bin/env python3
   import sys
   from pathlib import Path

   HARD_LIMITS = {
       "poor_cli/core.py":           1_000,
       "poor_cli/server/runtime.py": 5_600,
       "poor_cli/config.py":         1_500,
       "poor_cli/tools_async.py":    4_300,
       "poor_cli/multiplayer.py":    2_150,
       "poor_cli/core_turn_lifecycle.py": 2_700,
   }
   GLOBAL_FILE_LIMIT = 2_000

   def main() -> int:
       errors: list[str] = []
       repo_root = Path(__file__).parent.parent
       for path, limit in HARD_LIMITS.items():
           p = repo_root / path
           if not p.exists():
               continue
           lines = p.read_text().count("\n")
           if lines > limit:
               errors.append(
                   f"{path}: {lines} lines > {limit} limit "
                   f"(overage {lines - limit})"
               )
       for p in (repo_root / "poor_cli").rglob("*.py"):
           lines = p.read_text().count("\n")
           rel = str(p.relative_to(repo_root))
           if lines > GLOBAL_FILE_LIMIT and rel not in HARD_LIMITS:
               errors.append(f"{rel}: {lines} > {GLOBAL_FILE_LIMIT}")
       for e in errors:
           print(f"::error::{e}", file=sys.stderr)
       return 1 if errors else 0

   if __name__ == "__main__":
       sys.exit(main())
   ```

3. **Wire into CI** as a fast pre-test step in `.github/workflows/tests.yml`; fails before Python tests to surface quickly.

4. **Makefile target:** `lint-sizes: ## check monolith sizes` invoking the script. Wire into `make lint` if appropriate.

5. **Test:** `tests/` add `test_script_fails_on_oversized_file_fixture` — pytest fixture writes a fake too-big file into a tmp path and asserts exit code 1.

6. **Budget slack.** Do not set limits below what 9E (and the follow-on context-assembly PRD) actually deliver. If `core.py` lands at 900 lines, limit at 1,000 gives headroom. Enforcement must not immediately re-block work.

7. **Exemptions:** any exception must be inlined in the script with a comment explaining why. Do not externalize to a separate allow-list file.

8. **Boundary:** no enforcement on `tests/`, `docs/`, `asset/`, Lua files. Do not set aesthetic limits (line length etc.) — ruff handles that.

### Files to create/modify

- **Create:** `scripts/check_line_budgets.py`.
- **Modify:** `.github/workflows/tests.yml` (add pre-test step), `Makefile` (add `lint-sizes` target).
- **Delete:** none.
- **Collision note:** enforces a size ceiling on `poor_cli/core.py` that 9E just delivered — 9E must land first.

### Acceptance criteria

- [ ] `scripts/check_line_budgets.py` runs locally, passes after 9E lands, fails on pretend-bloat.
- [ ] CI step visible in PR checks and blocking on overage.
- [ ] `make lint-sizes` exists and runs the same check.
- [ ] Overage error message includes path, current lines, limit, and delta.
- [ ] Contributors cannot merge a `core.py` over 1,000 lines without editing the script (requires reviewer sign-off via inline comment).
