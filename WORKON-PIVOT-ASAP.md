# WORKON-PIVOT-ASAP

Authoritative plan for the pivot. Supersedes README positioning until merged back in.

Status: in progress, 2026-06-14. Owner: gongahkia.

## Implementation log

- 2026-06-14: hardened planner schema parsing so scalar list fields from Claude/Codex/custom planners are normalized as one-item lists instead of character arrays. Evidence: `tests/test_planner.py::test_parse_plan_accepts_string_list_fields`.
- 2026-06-14: added initial v6 release gates for source LOC and system-prompt budget, wired into CI. Evidence: `bench/loc_gate.py`, `tests/test_gates.py::test_system_prompt_under_1000_token_ceiling`, `.github/workflows/v6.yml`.
- 2026-06-14: added provider request/response contracts plus a `CachedReplayProvider` that records live calls and fails closed on replay cache misses. Evidence: `tests/test_providers.py`.
- 2026-06-14: added replayable `ToolDispatcher` and v0 built-ins: `read_file`, `write_file`, `edit`, `glob`, `grep`, `shell`, `replay_emit`. Evidence: `tests/test_tools.py`.
- 2026-06-14: added per-run filesystem replay mirrors: `.poor-cli/v6/runs/<run_id>/meta.json` and `events.jsonl`. Evidence: `tests/test_store.py::test_store_writes_run_meta_and_events_jsonl`.
- 2026-06-14: implemented event-window replay via `poor-cli replay --from-event`, deriving run/task state from event history. Evidence: `tests/test_replay.py`.
- 2026-06-14: added initial `poor-cli tui` Textual surface with transcript, activity, and composer panes. Evidence: `tests/test_cli.py::test_cli_exposes_tui_help`.
- 2026-06-14: closed GitHub issues #42-#47 after local implementation and verification evidence existed for bootstrap, store, core types, CLI skeleton, agent detection, and planner.

## TL;DR

- Keep the name **`poor-cli`**.
- Rewrite ~90% of `poor_cli/`; salvage a short list (see below). Hard ceiling **5,000 LOC** in `src/` for v6.0.0.
- Reposition from "CI-focused multi-provider agent harness" to **"minimal hackable Python coding harness — Pi for Python, with deterministic record-and-replay as the substrate."**
- Three phases, each independently shippable and each its own HN/Twitter moment.
- 6-month full-time runway. Goal = **portfolio/reputation**, not revenue.

## Audience

- Solo devs / hobbyists.
- Small dev teams (5-30 ppl).
- Academic / research (agent + LLM evaluation crowd).

Not chasing: regulated enterprise. That lane is owned by Coder ($90M Series C, May 2026), Tabnine, Sourcegraph Cody.

## Positioning

Reference brand: **Pi** by Mario Zechner / `pi-mono` (~48k stars). System prompt under 1k tokens. Four modes: interactive / print / RPC / SDK. Hackable via 25+ in-process hooks. TypeScript-native, npm-distributed.

`poor-cli`'s flank:

1. **Python-native.** Pi forces Node. ML/agent researchers and infra devs live in Python.
2. **Deterministic record-and-replay as a first-class substrate.** Nobody in the CLI-agent space ships this credibly. Pi doesn't.
3. **Repo-graph-aware tools (phase 2).** Tree-sitter symbolic access beats grep loops.
4. **CUDA/Linux local-first (phase 3).** Pi shines on M-series Mac. Linux + vLLM/SGLang is under-served.

## Extensibility surface

The "hackable" pitch dies without a designed extension lane. Pi has ~25 in-process TypeScript hooks. Python equivalent for v6.0.0:

- **Hooks**: a single `Hook` protocol with explicit lifecycle callbacks (`before_turn`, `after_tool_call`, `before_model_call`, `after_run`). Registered via Python entry-points group `poor_cli.hooks`. No runtime plugin loader, no DSL.
- **Tools**: third-party tools register via entry-points group `poor_cli.tools`. Built-ins live in `src/poor_cli/tools/`.
- **Providers**: same pattern via `poor_cli.providers`. Lets `poor-cli-vllm` ship as a separate sidecar package without touching core.
- **Skills / prompts**: deferred to v6.3+. Phase 1 = hooks + tools + providers only.

Acceptance: a ≤30-line user-authored hook can intercept every tool call and write to a custom audit sink, without forking the package.

## Timeline budget

- Phase 1: weeks 1-4 (record-and-replay GA, v6.0.0).
- Phase 2: weeks 5-10 (graph-aware tools GA, v6.1.0).
- Phase 3: weeks 11-22 (CUDA/Linux local-first GA, v6.2.0).
- Buffer: weeks 23-26 (launch iteration, regression fixes, community-PR triage).

Total: 26 weeks = 6 months. No phase begins early; slack absorbs slips.

## Phases

Each phase is shipped as polished as possible. No phase 2 work begins until phase 1 is GA.

### Phase 1 — Record & Replay (weeks 1-4)

Deliverables:
- `poor-cli run "..."` — one-shot agent loop.
- `poor-cli replay <run-id>` — deterministic playback from on-disk store.
- `poor-cli tui` — minimal Textual frontend.
- `.poor-cli/runs/<id>/` content-addressed store:
  - `meta.json` (model, provider, args, started_at, finished_at, exit)
  - `events.jsonl` (linear event log: user_msg, model_call, tool_call, tool_result, assistant_msg, finish)
  - `cas/<sha256>` (content-addressed blob store for all model i/o and tool i/o)
  - SQLite index for fast lookup by run-id / hash / prompt-prefix.
- Provider abstraction with a `cached_replay` shim that intercepts before any network call.
- Tool dispatcher with the same shim.
- Tools (v0): `read_file`, `write_file`, `edit`, `glob`, `grep`, `shell`, `replay_emit`.
- System prompt **under 1,000 tokens**.
- **MCP role**: client-only in v6.0.0. We consume external MCP servers via the salvaged `mcp_client.py`. Exposing `poor-cli` itself as an MCP host is deferred to v6.1+.

Providers in v6.0.0:
- GA: Anthropic.
- Beta: OpenAI, Gemini, Ollama.
- Everything else (vLLM, SGLang, llama-server, LM Studio, HF TGI, HF Local, LiteLLM, OpenRouter) → `poor-cli[providers-extra]`.

Acceptance criteria:
- 3 fixture bug-fix tasks solved end-to-end via Anthropic.
- Every successful run re-executes via `poor-cli replay` **byte-for-byte** with no network.
- Replay works offline on a machine that never had the API key.
- Total `src/` LOC under 5,000. Lint enforces.
- SWE-bench Lite subset (10 fixed tasks under `tests/fixtures/swe-lite-10/`): **≥30% pass** via Claude Sonnet 4.6, grep-mode tools. (Initial target; revised after the first calibration run.)

### Phase 2 — Graph-aware tools (weeks 5-10)

Deliverables:
- Tree-sitter-backed repo graph exposed as first-class tools: `find_symbol`, `callers_of`, `imports_of`, `subgraph`, `definition_of`.
- Incremental indexing on file watch.
- A `--graph` mode that biases system prompt toward symbolic-first navigation.
- Benchmark page: same task on grep-mode vs graph-mode, token-count + correctness comparison.

Acceptance criteria:
- On a 50k-LOC fixture repo, graph mode uses ≥30% fewer input tokens than grep mode at equal task success rate.
- Repo graph survives codebase mutations during a run.

### Phase 3 — CUDA/Linux local-first (weeks 11-22)

Deliverables:
- First-class vLLM/SGLang/Ollama providers with batched prompt-caching.
- Structured-output and function-calling shims that actually work on Qwen2.5-Coder-32B / Llama-4 / DeepSeek-class local models.
- One-command Linux+CUDA setup script.
- "Offline mode" guarantee: network calls fail loudly if `--offline` is set.

Acceptance criteria:
- A 60s screencast where `poor-cli` solves a real bug on a workstation with no internet, using `qwen2.5-coder-32b` (or comparable) on local GPU.
- Replay (phase 1) + graph (phase 2) work in offline mode.

## Benchmarks

- **Phase 1 baseline**: 10-task SWE-bench Lite subset (fixed seed set in `tests/fixtures/swe-lite-10/`). Target ≥30% pass with Claude Sonnet 4.6, grep-mode tools.
- **Phase 2 target**: graph-mode ≥30% fewer input tokens at equal pass rate on the same 10-task set.
- **Phase 3 target**: local-mode (`qwen2.5-coder-32b`) reaches ≥50% of the Anthropic-mode pass rate on the same set.
- All numbers published in `BENCHMARKS.md` with reproducible commands. Each row links the run-id from the replay store so reviewers can re-execute offline.

## Hero demo (the HN moment)

60-second screencast, three-reveal structure:

1. Watch `poor-cli` solve a real bug. Visibly uses `find_symbol` + `subgraph` instead of grep-and-pray.
2. Run `poor-cli replay <id>`. Same trace plays back instantly from cache, no network.
3. End card: **"Model: `qwen2.5-coder-32b` on a 4090. No network. No keys."**

Demo only finalizes when phase 3 lands. Earlier phase releases get their own narrower demos.

## Salvage list (keep from current 88k LOC)

Keep, port into the new tree:
- `poor_cli/audit_log.py` — basis for `events.jsonl` schema.
- `poor_cli/repo_graph.py` — phase 2 substrate.
- `poor_cli/sandbox.py` + `poor_cli/docker_sandbox.py` — shell tool sandboxing.
- `poor_cli/providers/{anthropic,openai,gemini,ollama}_provider.py` — port API shapes; rewrite the request/response interception layer for record-replay.
- `poor_cli/mcp_client.py` — MCP wiring.
- Parts of `poor_cli/checkpoint.py` — file-state diff/rollback primitives.
- `poor_cli/tui/textual_app.py` — reference for the minimal Textual frontend; rewrite ≤500 LOC.
- The 218 test files — port the relevant ~30 that cover salvaged code; delete the rest.

## Kill list (drop or move to `legacy/`)

Move to `legacy/` (browsable prior art, not imported by new code):
- `core_turn_lifecycle.py` (3,183 LOC), `tools_async.py` (3,996 LOC), `core_agent_loop.py`, `core_tool_dispatch.py`, `cli_app.py`. God-files.
- `automation_manager.py`, `automations/`, `task_manager.py`, `task_supervisor.py`, `architect_mode.py`, `plan_mode.py`, `spec_mode.py`. Features outside the minimal harness mission.
- `latent_*`, `neural_code_encoder.py`, `research/` subpackage. Research scope drift; user wants tool, not paper.
- `voice/`, voice commands. Niche, kills the "minimal" pitch.
- `economy.py`, `adaptive_budget.py`, `thinking_budget.py`, `token_budget_controller.py`, `budget_*` files. Replace with one short token-counting module.
- `semantic_cache.py`, `kv_cache_store.py`, `block_cache.py`, `tool_cache.py`. The record-replay store replaces all of these.
- `skills.py`, `skill_surfacer.py`, `skills/`, `prompt_library.py`, `workflow_templates.py`. Skills marketplace can come back in v6.3+ if it earns its place.
- `_tool_registry_builder.py` (50k chars). Replace with one ~200-LOC dispatcher.
- `command_manifest.py` + `command_manifest.json` (21k JSON). Hand-maintained mega-manifests rot.
- All `bench/*` except `bench/swe_bench_lite/` (keep for phase 1 acceptance harness).

## Distribution + repo strategy

- Same GitHub repo (`gongahkia/poor-cli`). Preserve commit history.
- New branch `v6/clean` (or `v6.0.0`) for the rewrite. `main` stays on v5.0.0 until cutover.
- `git mv poor_cli legacy/poor_cli` before the clean rewrite begins.
- `src/poor_cli/` becomes the new home. `pyproject.toml` flips to `[tool.setuptools.packages.find] where = ["src"]`.
- Add `LICENSE` (MIT) day one — currently missing despite pyproject claim.
- Wipe broken `ROADMAP.md` link from README; point to this file until v6.0.0 ships.
- PyPI: keep the `poor-cli` package, bump to `6.0.0a1` for first pre-release.
- Versioning: SemVer. v6.0.0 = phase 1 GA. v6.1.0 = phase 2 GA. v6.2.0 = phase 3 GA.
- **Landing page**: `poor-cli.dev` (or GitHub Pages from `docs/`). Live by v6.0.0 launch day. Hero copy = the Pi-for-Python pitch + 60s screencast embed.
- **Docs site**: MkDocs Material from `docs/` source, hosted on the same domain. Sections: Quickstart, Architecture, Hooks, Providers, Replay, Benchmarks.

## Reputation strategy

Primary channel by phase (user previously deferred prioritization; now resolved):

- **Phase 1 — HN / Twitter / dev-Reddit.** Replay-determinism is the lede. Pitch: *"Reproducible AI coding sessions in <5000 LOC of Python."* Submit Tuesday 06:30 PT. Same-day Twitter thread.
- **Phase 2 — academic / agent-researcher.** Graph-mode token-efficiency comparison is the lede. Crosspost: arxiv-sanity, LessWrong, agent-research Twitter. Reproducibility hook: every result row links a replay-store run-id.
- **Phase 3 — practitioner / daily-driver.** Offline local-LLM demo is the lede. Target: r/LocalLLaMA, dotfiles repos, `awesome-cli-coding-agents` PR.

Writing collaborator: needed by **week 3**. User ships code; collaborator ships the launch post, benchmark writeup, and docs polish. Action: shortlist 3 candidates (tech-writer friend, dev-rel acquaintance, or paid contractor) by end of week 1.

## Hard constraints

- **5,000 LOC ceiling** in `src/poor_cli/` for v6.0.0. Enforced by `bench/loc_gate.py` in CI.
- **System prompt under 1,000 tokens.** A test asserts this byte-budget on every PR.
- **No god-files.** Any file over 600 LOC must be split before merge.
- **Determinism is a release-blocking property.** A `--replay` byte-mismatch fails CI.
- **No new comments unless they explain a non-obvious why.** (Project CLAUDE.md rule.)
- **Commit hygiene resets.** New work uses Conventional Commits (`feat:`, `fix:`, `refactor:`, `chore:`, `docs:`, `test:`, `perf:`). No more `feat(app): edited`.

### CI gates for v6 PRs

- `ruff` (lint + format).
- `pytest`, with `--cov=src/poor_cli`. Coverage gate **≥60%** (up from current 40%).
- `mypy --strict` on `src/poor_cli/`.
- LOC gate (`bench/loc_gate.py`): ≤5000 LOC in `src/poor_cli/`.
- Prompt budget gate: system prompt ≤1000 tokens (test-asserted).
- Determinism gate: rerun a fixture run, assert byte-equal CAS output.

## Week 1-4 plan (phase 1 only)

**Week 1 — substrate.**
- Spec `.poor-cli/runs/<id>/` schema. Write `docs/ARCHITECTURE.md` first, code second. (Schema is the contract; replay determinism depends on it.)
- Implement `RunStore` + CAS + SQLite index. ~600 LOC budget.
- Hand-author a fake run record; `poor-cli replay` walks it.
- Tests: round-trip event log; CAS hash stability across processes; SQLite index race-safety.

**Week 2 — replay engine.**
- `Provider` interface with explicit `request_hash(prompt, model, params) -> bytes` and `response = call(...)` separation.
- `CachedReplayProvider` decorator that consults the CAS; falls through to the wrapped provider on miss.
- `ToolDispatcher` with identical pattern.
- Tests: any run with same inputs → same outputs offline.

**Week 3 — agent loop + Anthropic provider.**
- ~400 LOC loop in `src/poor_cli/loop.py`.
- 7 tools (`read_file`, `write_file`, `edit`, `glob`, `grep`, `shell`, `replay_emit`).
- System prompt under 1k tokens; budget asserted in tests.
- 3 fixture bugs in `tests/fixtures/bug-{1,2,3}/`.

**Week 4 — TUI + demo.**
- Textual three-pane (transcript / activity / composer). ≤500 LOC.
- `poor-cli run` and `poor-cli replay` both work inside TUI.
- Record the phase-1 screencast (replay-only narrative, no graph yet).
- Draft HN post + Twitter thread. Submit on a Tuesday morning US time.

## First-day actions (do today)

1. `git checkout -b v6/clean`.
2. `mkdir legacy && git mv poor_cli legacy/poor_cli && git mv tests legacy/tests`.
3. `touch LICENSE` and paste the MIT text. Add author + year.
4. Delete the broken `ROADMAP.md` reference from `README.md`.
5. New `pyproject.toml`:
   - `name = "poor-cli"`, `version = "6.0.0a1"`.
   - `description = "Minimal Python coding agent with deterministic record-and-replay."`
   - dependencies: `anthropic`, `pydantic`, `textual`, `rich`, `aiofiles`. That's it.
   - `[project.scripts] poor-cli = "poor_cli.__main__:main"`.
   - `[tool.setuptools.packages.find] where = ["src"]`.
6. `mkdir -p src/poor_cli docs tests/fixtures`.
7. Write `docs/ARCHITECTURE.md` (schema-first) before any code.
8. Create empty `src/poor_cli/__init__.py` with `__version__ = "6.0.0a1"`.
9. Add a CI workflow (`.github/workflows/v6.yml`) that runs on `v6/**` branches: ruff, pytest, LOC gate, prompt-budget gate.

## Open questions

- Whether to keep `poor-cli-server` (JSON-RPC) in v6.0.0 or defer to v6.1.0. [Inference] Defer — phase 1 is replay, not editor integration.
- Whether `--replay` mismatches should fail loudly or warn. Probably fail loudly for the first release, then add `--replay --allow-drift` later.
- Whether to keep the `cli/` subcommand structure (`task`, `agent`, `automation`, `spec`, etc.) or collapse to just `run | replay | tui | server`. Lean: collapse.
- Where to host the demo (asciinema vs MP4). asciinema is more authentic; MP4 spreads better on Twitter/X.

## Market context (for orientation, not action)

- **Coder Agents** — May 2026 launch, $90M Series C (KKR, Apr 2026). Owns self-hosted enterprise.
- **Pi / pi-mono** — ~48k stars. The minimal-hackable reference brand.
- **OpenCode** — 95k+ stars, 2.5M monthly users, 75+ providers. Owns the "VS Code of CLI agents" lane.
- **Aider** — 44.6k stars. Owns the git-disciplined pair-programmer lane.
- **Goose** — 45k stars. Owns Block-funded multi-agent.
- **Crush** — 24.1k stars. Charmbracelet's Go-native glamour TUI.
- **Claude Code** — 83.1k stars. Anthropic platform agent.
- **LangChain Deep Agents** + **OpenAI Agents SDK** — March 2026 launches. Own the harness-library layer.
- **CodeRabbit** / **Harness AI Code Review** / **GitHub Copilot Code Review** — own PR-review.

Honest read: every adjacent lane is taken. The only credible flank is **Python-native + record-and-replay + graph-aware + local-first**, in that priority order.

## Sources

- Pi coding agent — Mario Zechner: https://mariozechner.at/posts/2025-11-30-pi-coding-agent/
- pi-mono / coding-agent: https://github.com/badlogic/pi-mono/tree/main/packages/coding-agent
- OpenCode vs Pi: https://grigio.org/opencode-vs-pi-which-ai-coding-agent-should-you-use/
- Coder Agents $90M Series C: https://coder.com/blog/self-hosted-ai-model-agnostic-coder-agents
- 2026 harness landscape: https://thoughts.jock.pl/p/ai-coding-harness-agents-2026
- Awesome CLI coding agents: https://github.com/bradAGI/awesome-cli-coding-agents
- Agent harness engineering — Adnan Masood: https://medium.com/@adnanmasood/agent-harness-engineering-the-rise-of-the-ai-control-plane-938ead884b1d
