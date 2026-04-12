# Phase 21: Testing & Benchmarks

**Priority:** Medium — foundational infrastructure for credible performance claims (SWE-bench Lite) and safe Lua iteration (plenary/busted specs).
**Estimated agents:** 2 (parallel)
**Dependencies:** None — disjoint surfaces, can ship independently.
**Philosophy:** Measure before optimizing; test before shipping. Phase 21 lands the two missing testing substrates — a reproducible Python benchmark pipeline for `poor-cli exec` against SWE-bench Lite, and a headless Lua spec harness for `nvim-poor-cli` — so later phases have something to run their assertions through.

---

## File-scope table

| Agent | Domain | Primary paths | Touches Python? | Touches Lua? |
|-------|--------|---------------|-----------------|--------------|
| 21A | Python benchmark pipeline | `bench/swe_bench_lite/`, `docs/BENCHMARKS.md`, `README.md` | Yes | No |
| 21B | Lua test harness | `nvim-poor-cli/tests/`, `.github/workflows/tests.yml`, `Makefile`, `nvim-poor-cli/README.md` | No | Yes |

The two agents touch disjoint trees — Agent 21A lives under `bench/` and root-level docs; Agent 21B lives under `nvim-poor-cli/tests/` plus CI + Makefile targets. `README.md` (root) is touched by 21A only; `nvim-poor-cli/README.md` is touched by 21B only. No collisions.

---

## Agent 21A: SWE-bench Lite Publication Pipeline

**Pain points addressed:** No published performance numbers — benchmark-conscious users cannot compare `poor-cli` against Aider / Claude Code.
**Source:** LONGTERM-TODO H3, LEARNING.md §4.4.
**Expected outcome:** A single citable pass@1 score with reproducible methodology and cost/time breakdown.

### What to build

A reproducible SWE-bench Lite run wired to `poor-cli exec --prompt $task` as the agent. Publish pass@1, cost per task, time per task across the 300-task Lite subset using one default model (Claude Sonnet, or owner's choice — one model per run). Check in results, link from README, and add a score badge.

### Implementation details

1. **Harness setup** — vendor the official SWE-bench Lite harness invocation under `bench/swe_bench_lite/run.py`. The script should:
   - Accept a model name and task-subset filter as CLI args (but default to the full 300-task Lite set).
   - Shell out to `poor-cli exec --prompt $task` per task, capturing stdout, exit code, wall time, and token/cost telemetry.
   - Write per-task JSON records into `bench/swe_bench_lite/results/<run-id>/` (one row per task).

2. **One model per run** — do not compare models in a single run. If a second model is required, do a separate run and stash results in a distinct `<run-id>` directory. Re-run twice on variance if needed; publish the better-documented run, not the higher score.

3. **Do not optimize for the benchmark** — no per-task prompting, no cherry-picking, no tuning. The benchmark measures `poor-cli` as users would invoke it. Any config deviation from defaults must be recorded in `docs/BENCHMARKS.md`.

4. **Results file** — `docs/BENCHMARKS.md` documents:
   - Methodology (model, commit SHA, date, harness version, config deviations).
   - Headline pass@1, mean cost per task, mean wall time per task, p50/p95 latency.
   - Per-task CSV/JSON path.
   - How to reproduce (`python bench/swe_bench_lite/run.py --model ...`).

5. **README integration** — link `docs/BENCHMARKS.md` from `README.md` and add a badge with the pass@1 score.

6. **Data hygiene** — check raw results into `bench/swe_bench_lite/results/` so the number is verifiable. Do not commit model API keys or task-data caches.

### Files to create/modify

- `bench/swe_bench_lite/run.py` (new — harness runner)
- `bench/swe_bench_lite/results/` (new directory — per-run JSON outputs)
- `docs/BENCHMARKS.md` (new — methodology and headline results)
- `README.md` (modify — add benchmarks link + score badge)

### Acceptance criteria

- [ ] `bench/swe_bench_lite/run.py` executes the full 300-task Lite set against `poor-cli exec`.
- [ ] Per-task results checked into `bench/swe_bench_lite/results/<run-id>/`.
- [ ] `docs/BENCHMARKS.md` published with pass@1, cost, wall-time, and reproduction instructions.
- [ ] `README.md` links to `docs/BENCHMARKS.md` and displays the score badge.
- [ ] Run is reproducible from the documented commit SHA + model + config.
- [ ] No benchmark-specific tuning applied (documented in methodology section).

**PRD reference:** prd/060-swe-bench-lite-publish.md

---

## Agent 21B: Lua Testing Infrastructure (plenary.busted + CI)

**Pain points addressed:** The Neovim plugin ships no Lua tests. Pre-commit only runs `luac5.4 -p` for syntax. Every Lua-touching PRD (014, 015, 016, 029–049, 050–057) needs a spec runner before it can ship tests.
**Source:** Prerequisite infra for all Lua-test-shipping PRDs.
**Expected outcome:** `make test-lua` runs plenary.busted specs headlessly; CI runs it on push/PR; contributors can write new specs without a live `poor-cli-server`.

### What to build

A headless Lua test substrate built on `plenary.busted`. Bootstrap a test-only Neovim runtime that loads the plugin, run `PlenaryBustedDirectory` over `nvim-poor-cli/tests/`, mock the RPC layer so specs don't need a live server, and wire it into GitHub Actions.

### Implementation details

1. **Minimal init** — `nvim-poor-cli/tests/minimal_init.lua` bootstraps plenary:
   ```lua
   local plenary_dir = os.getenv("PLENARY_DIR") or vim.fn.stdpath("data") .. "/lazy/plenary.nvim"
   vim.opt.rtp:append(".")
   vim.opt.rtp:append(plenary_dir)
   vim.cmd("runtime plugin/plenary.vim")
   require("plenary.busted")
   ```
   `PLENARY_DIR` override lets CI point at a checked-out plenary clone instead of requiring a lazy.nvim install.

2. **Test entrypoint** — `nvim-poor-cli/tests/init.lua` holds shared setup for spec files (e.g., resetting global state between `describe` blocks).

3. **Mock RPC helper** — `nvim-poor-cli/tests/helpers/mock_rpc.lua` exposes a shim that records calls the plugin would send to `poor-cli-server` and lets specs assert them. Specs must never hit a real server.

4. **Makefile target**:
   ```makefile
   test-lua: ## run Lua plenary specs
   	nvim --headless --noplugin -u nvim-poor-cli/tests/minimal_init.lua \
   	  -c "PlenaryBustedDirectory nvim-poor-cli/tests/ {minimal_init = 'nvim-poor-cli/tests/minimal_init.lua'}"
   ```

5. **CI job** — add a `lua-tests` job to `.github/workflows/tests.yml`:
   - `actions/checkout@v4` for the repo.
   - `rhysd/action-setup-vim@v1` with `neovim: true, version: v0.10.0`.
   - Second `actions/checkout@v4` for `nvim-lua/plenary.nvim` into `./plenary`.
   - Run `PLENARY_DIR=$PWD/plenary make test-lua`.
   - Trigger on push and PR.

6. **Placeholder spec** — land `nvim-poor-cli/tests/smoke_spec.lua` with a trivial `describe`/`it` so CI has something green to run on day one. Later PRDs replace / add to this.

7. **Docs** — update the testing section of `nvim-poor-cli/README.md` with how to run `make test-lua` locally, how specs are structured, and how to use the `mock_rpc` helper.

8. **Boundaries** — do not port existing ad-hoc test files; do not fuzz-test the UI; do not run against the real server. Infra only; actual coverage lands in the PRDs that block on this.

### Files to create/modify

- `nvim-poor-cli/tests/init.lua` (new)
- `nvim-poor-cli/tests/minimal_init.lua` (new)
- `nvim-poor-cli/tests/helpers/mock_rpc.lua` (new)
- `.github/workflows/tests.yml` (modify — add `lua-tests` job)
- `Makefile` (modify — add `test-lua` target)
- `nvim-poor-cli/README.md` (modify — add testing section)

### Acceptance criteria

- [ ] `make test-lua` runs locally given Neovim + plenary present.
- [ ] `minimal_init.lua` bootstraps plenary via `PLENARY_DIR` env override.
- [ ] `mock_rpc.lua` helper exposes a record-and-assert shim for plugin RPC calls.
- [ ] A placeholder `smoke_spec.lua` exists so CI has something to run.
- [ ] CI `lua-tests` job runs on push and PR and is green.
- [ ] `nvim-poor-cli/README.md` documents how to write and run specs.
- [ ] No spec hits a real `poor-cli-server`.

**PRD reference:** prd/065-lua-testing-infrastructure.md
