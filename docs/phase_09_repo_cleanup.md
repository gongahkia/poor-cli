# Phase 9: Repo Cleanup & Dead Code Purge

**Priority:** High — removes carrying cost (cold-start imports, contributor confusion, misleading docs) and installs guardrails against monolith regrowth.
**Estimated agents:** 6 (mixed parallel / serialized — see ordering table).
**Dependencies:** 9C depends on 9B (stub decisions gate relocation). 9D should land after 9B (README references to archived stubs). 9F depends on 9E (line-count floor only enforceable after pre-slice).
**Philosophy:** Delete first, relocate second, rewrite docs third, then CI-pin the result. Every agent here is either a destructive cleanup or a regression guard. No new product features.

---

## File-scope map (verify disjointness at a glance)

| Agent | Primary scope | Creates | Deletes / Modifies |
|---|---|---|---|
| 9A | `_archived/` tree | — | Deletes all `_archived/<client>/` subtrees |
| 9B | Stub modules (decision + cleanup) | — | `poor_cli/docker_sandbox.py`, `poor_cli/speculative_decoding.py`, `poor_cli/rtk_integration.py`, `poor_cli/kv_cache_store.py`; docs/README references |
| 9C | Research relocation | `poor_cli/research/__init__.py`, `poor_cli/research/README.md` | Moves `latent_communication.py`, `neural_code_encoder.py`, `speculative_decoding.py`*, `kv_cache_store.py`*, `embeddings.py`†, `code_tokenizer.py`† into `poor_cli/research/`; `poor_cli/__init__.py`, `pyproject.toml` |
| 9D | Top-level docs + screenshots | `asset/reference/v6/*.png` | `README.md`, `nvim-poor-cli/README.md`; deletes `asset/reference/v5/*.png` |
| 9E | `core.py` pre-slice | `poor_cli/agent_loop.py`, `poor_cli/tool_dispatch.py`, `poor_cli/turn_lifecycle.py`, `tests/test_core_pre_slice.py` | `poor_cli/core.py`, importers' import paths |
| 9F | CI size gate | `scripts/check_monolith_sizes.py` | `.github/workflows/tests.yml`, `Makefile` |

\* Only moved by 9C if 9B's decision was "relocate" rather than "delete".
† Only moved if not actively used in production call sites (9C audits first).

---

## File-scope collisions (explicit)

1. **9B ↔ 9C** both list `poor_cli/speculative_decoding.py` and `poor_cli/kv_cache_store.py`. 9B decides fate (delete/ship/relocate). 9C only relocates the subset 9B marks "relocate". **Serialization: 9B must land before 9C.** This matches the PRD 008 `Blocked by: 007` dependency.

2. **9B ↔ 9D** both touch `README.md`. 9B strikes references to archived stubs ("Docker sandbox" claim); 9D performs a full rewrite. **Serialization: 9D after 9B**, or 9D explicitly re-verifies 9B's removals are not reintroduced. Preferred: 9D runs last and treats 9B's edits as a merge conflict to resolve in favor of 9D's new structure.

3. **9E ↔ 9F** both concern `poor_cli/core.py` size. 9E shrinks it (target ≤3,000 lines); 9F pins the ceiling (≤1,000 lines, with budget slack). **Serialization: 9E must land before 9F.** PRD 021 already declares `Blocked by: 017`.

4. **9A ↔ 9D** do not collide (9A deletes `_archived/`; 9D touches `asset/reference/`). Run in parallel.

5. **9C ↔ 9E** do not collide (disjoint module trees) but both edit `poor_cli/__init__.py`. Light-touch edits; run sequentially or resolve via small merge. Preferred order: 9E first (structural), then 9C (adds research package export).

### Recommended wave ordering

- **Wave 9.i (parallel):** 9A, 9B, 9E.
- **Wave 9.ii (parallel, after 9.i):** 9C (needs 9B), 9F (needs 9E), 9D (cleanest after 9B).

---

## Agent 9A: Remove `_archived/` retired front-ends

**Pain points addressed:** contributor confusion, repo bloat, misleading top-level tree.
**PRD reference:** prd/006-remove-archived-frontends.md

### What to build

Delete the five retired front-end subtrees from `_archived/`. The project consolidated to Neovim-only; these (Emacs, Desktop, Telegram, TUI, VS Code) are unmaintained. Git history preserves them; resurrect via `git checkout <hash> -- _archived/<subdir>` if ever needed.

### Implementation details

1. Grep for live references first: `grep -rn "_archived" poor_cli/ nvim-poor-cli/ tests/ Makefile pyproject.toml .github/`. Expect zero non-doc hits. If anything in source/tests hits, stop and escalate.
2. Owner decision: (a) leave `_archived/` with a README pointer to last live commits, (b) delete the directory entirely, (c) move the pointer to `docs/ARCHIVED_CLIENTS.md`. **Default: (b).**
3. Use `git rm -r _archived/<subdir>` (not `rm -rf`) so git records deletions cleanly.
4. If decision (a) or (c): write the one-paragraph pointer listing last-known-good commit hashes per client.
5. Scrub stale doc links: `grep -rn "_archived\|archived/" docs/ *.md README.md` and remove or redirect.
6. `.gitignore`: remove any `_archived/` patterns if present.

### Files to create/modify

- **Delete:** `_archived/emacs-poor-cli/`, `_archived/poor-cli-desktop/`, `_archived/poor-cli-telegram/`, `_archived/poor-cli-tui/`, `_archived/vscode-poor-cli/` (recursive). If decision (b): `_archived/` itself.
- **Create (only if decision (a)/(c)):** `_archived/README.md` or `docs/ARCHIVED_CLIENTS.md`.
- **Modify:** any doc with dead links to `_archived/`.

### Acceptance criteria

- [ ] `make lint && make test` green.
- [ ] `grep -rn "_archived" poor_cli/ nvim-poor-cli/ tests/ Makefile pyproject.toml` returns nothing.
- [ ] `_archived/` is either gone or contains only the pointer file.
- [ ] No source/test reference to `_archived/` remains.
- [ ] Boundary respected: `asset/` untouched (9D owns screenshots).

**PRD reference:** prd/006-remove-archived-frontends.md

---

## Agent 9B: Decide and execute on dead stub modules

**Pain points addressed:** "concept car" stubs shipping with no user value; misleading README; contributor cognitive tax.
**PRD reference:** prd/007-dead-stub-modules-decision.md

### What to build

Resolve the fate of four stub/dead-integration modules. Each is either (a) shipped end-to-end with user-visible value, (b) archived with docs updated, or (c) relocated to `poor_cli/research/` (handoff to 9C).

The four modules and recommended decisions:

| File | LOC | Wired? | Recommended |
|---|---|---|---|
| `poor_cli/docker_sandbox.py` | ~3 | No | (b) archive — README also retracts "Docker sandbox" claim |
| `poor_cli/speculative_decoding.py` | ~214 | No | (b) relocate to research/ (9C executes move) |
| `poor_cli/rtk_integration.py` | ~2 | No | (a) ship via follow-up PRD 026; keep file, mark stub |
| `poor_cli/kv_cache_store.py` | — | Eager-loaded | (a) ship with runtime gate on local-provider presence |

### Implementation details

1. **Decision pass.** Owner records outcome per module in an `## Outcome` block at the top of PRD 007. This PRD does not itself implement "ship" decisions — those spawn or transfer to dedicated PRDs.
2. **Archive path.** For each "archive/delete" decision:
   - Remove the file.
   - Scrub references in `SOLUTIONS.md`, `LONGTERM-TODO.md`, any `docs/phase_0*.md` that promised the feature, and `README.md`.
3. **Relocate path.** For each "research relocation" decision: do **not** move the file here. Mark it for 9C and let the relocation PRD handle it.
4. **Ship path.** For each "ship" decision: transfer scope to the dedicated PRD (PRD 026 for RTK-lite; dedicated PRD for kv_cache_store guard).
5. Final grep guard: `grep -rn "docker_sandbox\|speculative_decoding\|rtk_integration\|kv_cache_store" poor_cli/ docs/ README.md` — results must be consistent with the outcome table.

### Files to create/modify

- **Delete (per decision):** whichever of `poor_cli/docker_sandbox.py`, `poor_cli/speculative_decoding.py`, `poor_cli/rtk_integration.py`, `poor_cli/kv_cache_store.py` are marked archive/delete.
- **Modify:** `README.md` (strike Docker sandbox), `SOLUTIONS.md`, `LONGTERM-TODO.md`, `docs/phase_0*.md` — scrub promises for archived modules.
- **Create:** none.
- **Collision note:** touches `README.md` — 9D rewrites it subsequently; `speculative_decoding.py` / `kv_cache_store.py` overlap with 9C (must land first).

### Acceptance criteria

- [ ] Outcome block written in PRD 007 for all four modules.
- [ ] Archive decisions: files removed, docs scrubbed.
- [ ] Ship decisions: ownership transferred to target PRD, referenced by ID.
- [ ] Relocate decisions: file flagged for 9C (not yet moved).
- [ ] `make lint && make test` green.
- [ ] Grep guard clean.

**PRD reference:** prd/007-dead-stub-modules-decision.md

---

## Agent 9C: Relocate research modules behind feature flags

**Pain points addressed:** cold-start time, contributor confusion (production vs research), noise in top-level package.
**PRD reference:** prd/008-research-module-relocation.md

### What to build

Move research-only modules from `poor_cli/` into a new `poor_cli/research/` subpackage. Gate each behind a `[research]` config flag (default false). Contributors reading `poor_cli/` see only production code; `import poor_cli` does not eagerly import any research module.

### Implementation details

1. **Confirm 9B outcomes.** Do not move any module 9B marked for deletion.
2. **Layout:**
   ```
   poor_cli/research/
     __init__.py          # docstring only; no * exports
     README.md            # "Research code. Not part of production agent loop."
     latent_communication.py
     neural_code_encoder.py
     speculative_decoding.py  # if 9B chose relocate
     kv_cache_store.py        # if 9B chose relocate
   ```
3. **Move with `git mv`** to preserve blame.
4. **Lazy-import guard** at every production call site:
   ```python
   def _maybe_get_latent():
       if not config.get("research.latent_communication", False):
           return None
       from poor_cli.research import latent_communication
       return latent_communication
   ```
5. **Config defaults** (coordinate with preferences-schema PRD 003):
   ```json
   {"research": {"latent_communication": false, "neural_code_encoder": false,
                 "speculative_decoding": false, "kv_cache_store": false}}
   ```
6. **Audit `embeddings.py` and `code_tokenizer.py`** before moving. If `semantic_cache` or another production module imports them, leave them in `poor_cli/`. PRD 058 may ship `code_tokenizer.py` — defer if so.
7. **Update `pyproject.toml::[tool.setuptools].packages`** to include `poor_cli.research`.
8. **Grep for stale imports:** `grep -rn "from poor_cli.latent_communication\|from poor_cli.neural_code_encoder\|from poor_cli.speculative_decoding\|from poor_cli.kv_cache_store"` and fix each.

### Files to create/modify

- **Create:** `poor_cli/research/__init__.py`, `poor_cli/research/README.md`.
- **Move (git mv):** `poor_cli/latent_communication.py`, `poor_cli/neural_code_encoder.py`, `poor_cli/speculative_decoding.py`*, `poor_cli/kv_cache_store.py`*, `poor_cli/embeddings.py`†, `poor_cli/code_tokenizer.py`† → `poor_cli/research/`.
- **Modify:** `poor_cli/__init__.py` (drop top-level re-exports), `pyproject.toml` (package list), all production call sites switching to lazy-guard imports.
- **Delete:** none (9B owns deletions).
- **Collision note:** overlaps with 9B on `speculative_decoding.py`/`kv_cache_store.py` — 9B must land first.

### Acceptance criteria

- [ ] All research modules live under `poor_cli/research/`.
- [ ] `tests/test_research_relocation.py::test_research_modules_not_imported_by_default` passes (inspect `sys.modules` after `import poor_cli`).
- [ ] `tests/test_research_relocation.py::test_feature_flag_enables_research_module` passes.
- [ ] Cold-start measurement documented in PR body (before/after via `python3 -c "import time; s=time.time(); import poor_cli; print(time.time()-s)"`).
- [ ] `make lint && make test` green.

**PRD reference:** prd/008-research-module-relocation.md

---

## Agent 9D: Rewrite README and purge stale TUI screenshots

**Pain points addressed:** misleading front door (TUI screenshots, dual install paths, dead client references), adoption friction.
**PRD reference:** prd/009-readme-rewrite-screenshot-purge.md

### What to build

Rewrite `README.md` as a Neovim-plugin README with the Python server/agent backend. Replace v5 TUI screenshots with v6 Neovim captures. Scrub references to retired clients (TUI, Telegram, desktop, Emacs, VS Code). Align `nvim-poor-cli/README.md` against the new top-level structure.

### Implementation details

1. **New README structure (top-down):** badges → logo + one-line hook → hero screenshot (v6/1.png) → install (pip + lazy.nvim snippet) → quickstart (3 steps: install, set `GEMINI_API_KEY`, `:PoorCliChat`) → features (short bullets) → provider support table → multiplayer (one paragraph + link to `docs/MULTIPLAYER.md`) → commands (link to plugin README, do not duplicate) → contributing / license.
2. **v6 screenshots** to capture:
   - `1.png` — Neovim with chat panel open mid-response.
   - `2.png` — Diff Review panel (reuse chat screenshot if PRD 014 hasn't landed).
   - `3.png` — Cost HUD + lualine (post-PRD 016; placeholder otherwise).
   - `4.png` — Onboarding wizard step.
   - `5.png` — Panels (tasks/checkpoints/sessions).
   If owner cannot provide captures in time, ship labeled placeholders with `TODO: real screenshot` comments.
3. **Delete v5 screenshots** (or move to `asset/reference/archive/v5/`).
4. **Dead-reference scrub:** `grep -rn -i "tui\|telegram\|desktop\|emacs" README.md docs/` — remove each hit unless it is historically framed.
5. **Alignment pass on `nvim-poor-cli/README.md`** — edits only where it contradicts the new top-level README; do not rewrite.
6. **Boundary:** do not create a docs site (out-of-scope, LONGTERM-TODO H4); do not ship an asciinema demo.

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

**PRD reference:** prd/009-readme-rewrite-screenshot-purge.md

---

## Agent 9E: Pre-slice `core.py` into section modules

**Pain points addressed:** `core.py` is 6,134 lines — parallel work on the god object serializes through whoever edits it first.
**PRD reference:** prd/017-core-pre-slice.md

### What to build

Extract three cohesive slices from `poor_cli/core.py` into new modules without changing behavior. Target: `core.py` drops from ~6,100 to ≤3,000 lines after this PRD. PRD 018 will take another slice; PRD 021 (9F) locks the ceiling.

### Implementation details

1. **Section → module map:**
   | Section in `core.py` | New module | Exports |
   |---|---|---|
   | Agent loop (send → stream → tool → repeat) | `poor_cli/agent_loop.py` | `AgentLoop` class, `run_turn(ctx, core)` |
   | Tool dispatch (resolve → gate → execute → transform) | `poor_cli/tool_dispatch.py` | `ToolDispatcher` class |
   | Turn lifecycle (checkpoints, audit, post-turn economy) | `poor_cli/turn_lifecycle.py` | `TurnLifecycle` class |

2. **Refactor shape:** each helper holds a back-ref to `core` to avoid ballooning constructors. `PoorCLICore.__init__` instantiates all three; `run_turn` becomes a one-line delegate to `self._agent_loop.run(...)`.

3. **Order of operations (critical — each step is its own commit):**
   1. Extract `turn_lifecycle.py` (smallest, least tangled). Run `make test`.
   2. Extract `tool_dispatch.py` (depends on `permission_engine`, already modular). Run `make test`.
   3. Extract `agent_loop.py` (depends on both above). Run `make test`.

4. **Public surface invariance.** `dir(PoorCLICore)` snapshot must not change. No test modifications should be required; if any test needs an import path change, flag it in the PR.

5. **PR body must document** starting/ending line ranges for each extracted section so reviewers can diff section-by-section.

### Files to create/modify

- **Create:** `poor_cli/agent_loop.py`, `poor_cli/tool_dispatch.py`, `poor_cli/turn_lifecycle.py`, `tests/test_core_pre_slice.py`.
- **Modify:** `poor_cli/core.py` (remove extracted code, add delegating thunks); importers of `core` (import paths only if needed — surface unchanged).
- **Delete:** none.
- **Collision note:** lightly touches `poor_cli/__init__.py` alongside 9C. Land 9E first.

### Acceptance criteria

- [ ] Three new modules exist with the declared classes and exports.
- [ ] `poor_cli/core.py` ≤ 3,000 lines.
- [ ] `tests/test_core_pre_slice.py` covers: `test_agent_loop_importable`, `test_tool_dispatch_importable`, `test_turn_lifecycle_importable`, `test_core_py_under_3000_lines`, `test_poor_cli_core_public_surface_unchanged`.
- [ ] No existing tests modified.
- [ ] `make lint && make test` green after each extraction commit.
- [ ] Behavior unchanged (no user-visible delta).

**PRD reference:** prd/017-core-pre-slice.md

---

## Agent 9F: CI gate — pin monolith sizes

**Pain points addressed:** without a line-count gate, `core.py` regrows to 6,000 lines one feature at a time.
**PRD reference:** prd/021-core-line-count-ci-gate.md

### What to build

Add a CI step (and `make lint-sizes` target) that fails the build when tracked monoliths exceed their hard limits. Must land **after** 9E so `core.py` actually fits under its cap with budget slack.

### Implementation details

1. **Hard limits (`scripts/check_monolith_sizes.py`):**
   ```python
   HARD_LIMITS = {
       "poor_cli/core.py":           1_000,
       "poor_cli/server/runtime.py":   800,
       "poor_cli/config.py":         1_500,
   }
   GLOBAL_FILE_LIMIT = 2_000  # every .py under poor_cli/
   ```
2. **Script skeleton** emits GitHub Actions `::error::` annotations on overage and exits 1 when any file is over limit. Iterate `repo_root / "poor_cli"` with `rglob("*.py")`, skipping paths already in `HARD_LIMITS`.
3. **Wire into CI** as a fast pre-test step in `.github/workflows/tests.yml`; fails before Python tests to surface quickly.
4. **Makefile target:** `lint-sizes: ## check monolith sizes` invoking the script. Wire into `make lint` if appropriate.
5. **Test:** `test_script_fails_on_oversized_file_fixture` — pytest fixture writes a fake too-big file into a tmp path and asserts exit code 1.
6. **Budget slack.** Do not set limits below what 9E + PRD 018 actually deliver. If `core.py` lands at 900 lines, limit at 1,000 gives headroom. Enforcement must not immediately re-block work.
7. **Exemptions:** any exception must be inlined in the script with a comment explaining why. Do not externalize to a separate allow-list file.
8. **Boundary:** no enforcement on `tests/`, `docs/`, `asset/`, Lua files.

### Files to create/modify

- **Create:** `scripts/check_monolith_sizes.py`.
- **Modify:** `.github/workflows/tests.yml` (add pre-test step), `Makefile` (add `lint-sizes` target).
- **Delete:** none.
- **Collision note:** enforces a size ceiling on `poor_cli/core.py` that 9E just delivered — 9E must land first.

### Acceptance criteria

- [ ] `scripts/check_monolith_sizes.py` runs locally, passes after 9E lands, fails on pretend-bloat.
- [ ] CI step visible in PR checks and blocking on overage.
- [ ] `make lint-sizes` exists and runs the same check.
- [ ] Overage error message includes path, current lines, limit, and delta.
- [ ] Contributors cannot merge a `core.py` over 1,000 lines without editing the script (requires reviewer sign-off).

**PRD reference:** prd/021-core-line-count-ci-gate.md
