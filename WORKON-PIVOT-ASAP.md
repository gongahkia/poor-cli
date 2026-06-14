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
- 2026-06-14: added explicit `agent.input` artifacts before delegated subprocess execution so confirmed runs persist both agent inputs and results. Evidence: `tests/test_cli.py::test_cli_plan_run_inspect_replay`.
- 2026-06-14: closed GitHub issue #48 after confirmed sequential execution recorded plan, agent input, agent result, and failure-stop events.
- 2026-06-14: added `handoff.packet` artifacts after completed or failed task execution and exposed them through `poor-cli inspect --context`. Evidence: `tests/test_cli.py::test_cli_plan_run_inspect_replay`.
- 2026-06-14: closed GitHub issue #49 after context and handoff artifacts were inspectable.
- 2026-06-14: closed GitHub issue #50 after replay state reconstruction, `--from-event`, and missing-artifact failure paths were covered.
- 2026-06-14: added structured planner failure, agent failure, and non-interactive confirmation-required events. Evidence: `tests/test_cli.py::test_cli_plan_failure_records_structured_events` and `tests/test_cli.py::test_cli_run_without_yes_records_confirmation_event`.
- 2026-06-14: closed GitHub issue #51 after confirmation, budget placeholder, and structured failure-event coverage landed.
- 2026-06-14: raised the milestone suite to an in-process CLI smoke plus CI coverage gate at `--cov-fail-under=60`. Evidence: `tests/test_cli.py::test_cli_main_in_process_run_inspect_replay`.
- 2026-06-14: closed GitHub issue #52 after milestone tests, ruff, coverage, and LOC gates passed locally and were wired into CI.
- 2026-06-14: added benchmark task schema, 10 candidate poor-cli issue tasks, and baseline comparison plan for Claude-only, Codex-only, and poor-cli modes. Evidence: `BENCHMARKS.md`, `bench/fixtures/v6_baseline_tasks.json`, `tests/test_benchmarks.py`.
- 2026-06-14: closed GitHub issue #53 after the benchmark schema and baseline plan landed.
- 2026-06-14: added the v6 hook protocol and entry-point loader for `poor_cli.hooks`, wired into run turns, provider model calls, tool calls, and run completion. Evidence: `tests/test_hooks.py`.
- 2026-06-14: added Anthropic, OpenAI Responses, Gemini, and Ollama provider adapters behind the shared replayable provider contract. Evidence: `tests/test_provider_adapters.py`; OpenAI call shape checked against official Responses API docs.
- 2026-06-14: added entry-point loading for `poor_cli.tools` and `poor_cli.providers`, completing the phase-1 hooks/tools/providers extension lane. Evidence: `tests/test_tools.py::test_tool_entry_points_extend_dispatcher_defaults` and `tests/test_providers.py::test_provider_entry_points_load_provider_instances`.
- 2026-06-14: added replay integrity verification for event mirrors and CAS artifacts via `poor-cli replay --verify`, including stable repeated JSON replay output. Evidence: `tests/test_replay.py::test_replay_verify_checks_event_mirror_and_cas` and `tests/test_cli.py::test_cli_main_in_process_run_inspect_replay`.
- 2026-06-14: added `poor-cli --offline` plus `POOR_CLI_OFFLINE` guards for provider adapters, provider cache misses, planners without a custom command, and non-local delegated agents. Evidence: `tests/test_providers.py::test_cached_replay_provider_blocks_live_call_when_offline`, `tests/test_provider_adapters.py::test_provider_adapters_block_offline_calls`, `tests/test_planner.py::test_offline_planner_requires_custom_command`, and `tests/test_agents.py::test_offline_mode_blocks_network_backed_agents`.
- 2026-06-14: ported a v6 stdio MCP client surface with `poor-cli mcp list` and `poor-cli mcp call server:tool`, keeping MCP client-only for v6.0.0. Evidence: `tests/test_mcp_client.py`.
- 2026-06-14: pinned the phase-1 SWE-bench Lite 10 fixture manifest from `SWE-bench/SWE-bench_Lite` test offset 0, length 10. Evidence: `tests/fixtures/swe-lite-10/manifest.json` and `tests/test_benchmarks.py::test_swe_lite_10_manifest_schema`.
- 2026-06-14: hardened the SQLite run index for multi-connection writes with WAL, busy timeout, and run/task/artifact lookup indexes. Evidence: `tests/test_store.py::test_store_accepts_parallel_event_writers`.
- 2026-06-14: added per-run CAS mirrors under `.poor-cli/v6/runs/<run_id>/cas/<sha256>` and made replay verification check the mirrors. Evidence: `tests/test_store.py::test_store_events_and_cas_round_trip` and `tests/test_replay.py::test_replay_verify_rejects_cas_mirror_mismatch`.
- 2026-06-14: wired the TUI composer to dispatch `run --dry`, `run --yes`, and `replay <run_id>` through a testable command handler. Evidence: `tests/test_tui.py::test_tui_command_handler_runs_and_replays`.
- 2026-06-14: wired the remaining v6 CI gates for `ruff format --check` and `mypy --strict src/poor_cli`, and fixed current strict typing failures. Evidence: `.github/workflows/v6.yml`, `.github/workflows/ci.yml`, `.github/workflows/tests.yml`.
- 2026-06-14: added a replay determinism gate that snapshots `.poor-cli/v6/runs/<run_id>/` and asserts `poor-cli replay --verify` is byte-non-mutating. Evidence: `tests/test_cli.py::test_cli_main_in_process_run_inspect_replay`.
- 2026-06-14: ported a minimal v6 shell sandbox guard that blocks network shell commands and writes outside the tool workdir. Evidence: `src/poor_cli/sandbox.py` and `tests/test_tools.py::test_shell_tool_blocks_network_and_outside_writes`.
- 2026-06-14: added SQLite run lookup by user-goal prefix plus `poor-cli runs --prefix`, covering the prompt-prefix index path. Evidence: `tests/test_store.py::test_store_filters_runs_by_goal_prefix` and `tests/test_cli.py::test_cli_runs_filters_by_prefix`.
- 2026-06-14: persisted task `validation` and planner metadata through SQLite so generic shell tasks can execute planner-specified commands. Evidence: `tests/test_store.py::test_store_preserves_task_metadata_and_validation` and `tests/test_cli.py::test_cli_run_executes_generic_command_metadata`.
- 2026-06-14: added three local fixture bugs and an end-to-end `poor-cli run --yes` harness that fixes each fixture and validates with pytest. Evidence: `tests/fixtures/bug-{1,2,3}/` and `tests/test_fixture_bugs.py::test_three_fixture_bugs_solve_end_to_end`. Live Anthropic calibration remains pending.
- 2026-06-14: verified `poor-cli --offline replay <run_id> --verify` works after clearing planner configuration, proving replay does not require live agent/provider credentials. Evidence: `tests/test_cli.py::test_cli_main_in_process_run_inspect_replay`.
- 2026-06-14: added `bench/local_fixture_bugs.py` to run the three local fixture bugs through `poor-cli`, validate pytest, and verify offline replay per fixture. Evidence: `tests/test_benchmarks.py::test_local_fixture_bug_benchmark_runs_poor_cli_generic`. Live Anthropic and SWE-bench Lite result rows remain pending.
- 2026-06-14: rewired `bench/swe_bench_lite/run.py` from the removed `poor_cli exec` path to v6 `poor-cli run --yes`, pinned manifest selection, `predictions.jsonl`, persisted per-task stores, and offline replay verification. Evidence: `tests/test_benchmarks.py::test_swe_lite_runner_applies_manifest_order_and_validates_pin` and `tests/test_benchmarks.py::test_swe_lite_runner_uses_v6_run_and_planner_payload`. Live SWE-bench pass-rate rows remain pending.
- 2026-06-14: checked in the first compact benchmark result row for local generic fixture bugs: 3/3 completed, 3/3 pytest passed, 3/3 offline replay verified. Evidence: `bench/results/local-fixture-bugs-generic.json` and `tests/test_benchmarks.py::test_checked_in_local_fixture_bug_result_rows`. Live Anthropic and SWE-bench result rows were pending at that point.
- 2026-06-14: added a no-cost Phase 1 readiness probe and checked-in snapshot so missing live prerequisites are explicit before Anthropic/SWE runs. Evidence: `bench/phase1_readiness.py`, `bench/results/phase1-readiness.json`, and `tests/test_benchmarks.py::test_checked_in_phase1_readiness_snapshot`. Current snapshot still lacks live auth env, SWE Python deps, and Docker daemon readiness.
- 2026-06-14: added the `poor-cli[bench]` optional dependency extra and wired the readiness snapshot to point SWE-bench dependency misses at `python -m pip install -e '.[bench]'`. Evidence: `pyproject.toml`, `bench/swe_bench_lite/requirements.txt`, and `tests/test_benchmarks.py::test_bench_extra_matches_swe_lite_requirements`.
- 2026-06-14: regenerated the Phase 1 readiness snapshot through `uv run --locked --extra bench`, verifying `datasets` and `swebench` import successfully under the locked benchmark environment. Evidence: `bench/results/phase1-readiness.json` and `tests/test_benchmarks.py::test_checked_in_phase1_readiness_snapshot`. Remaining blockers are live auth env and Docker daemon readiness.
- 2026-06-14: started Docker.app and refreshed the Phase 1 readiness snapshot with Docker daemon ready (`29.5.3`), leaving only live Anthropic/Codex auth prerequisites. Evidence: `bench/results/phase1-readiness.json` and `tests/test_benchmarks.py::test_checked_in_phase1_readiness_snapshot`.
- 2026-06-14: added redacted no-cost CLI auth probes for Claude and Codex readiness, then refreshed the Phase 1 readiness snapshot to `ready: true` with no remaining prerequisite blockers. Evidence: `bench/phase1_readiness.py`, `bench/results/phase1-readiness.json`, and `tests/test_benchmarks.py::test_checked_in_phase1_readiness_snapshot`. Live Anthropic fixture and SWE-bench result rows remain pending.
- 2026-06-14: ran the required live Anthropic local fixture calibration through Claude with `--budget-usd 1.0`: 3/3 completed, 3/3 pytest passed, 3/3 offline replay verified. Evidence: `bench/results/local-fixture-bugs-claude.json` and `tests/test_benchmarks.py::test_checked_in_local_fixture_bug_result_rows`. SWE-bench pass-rate rows remain pending.
- 2026-06-14: fixed the SWE-bench runner planner command to survive task-worktree cwd changes and ran a live Claude no-eval SWE smoke with `--budget-usd 1.0`: 1/1 `poor-cli run` completed, 1/1 offline replay verified, 506-byte patch emitted for `astropy__astropy-12907`. Evidence: `bench/swe_bench_lite/results/smoke-claude-20260614T035359Z/` and `tests/test_benchmarks.py::test_checked_in_swe_lite_smoke_result`. Full Docker-evaluated SWE-bench pass-rate rows remain pending.
- 2026-06-14: added SWE-bench eval-only mode so checked-in `predictions.jsonl` files can be Docker-evaluated without regenerating model patches. Evidence: `bench/swe_bench_lite/run.py --evaluate-existing-run` and `tests/test_benchmarks.py::test_swe_lite_runner_evaluates_existing_run`. Full Docker-evaluated SWE-bench pass-rate rows remain pending.
- 2026-06-14: tightened SWE-bench official-eval command generation after Docker attempts hit a missing remote `swebench/...` image and a broken local credential helper: prediction instance IDs are passed explicitly, modern `*.{run_id}.json` reports are discovered, local-build eval knobs are exposed, and eval uses an isolated Docker config by default. Evidence: `tests/test_benchmarks.py::test_swe_lite_official_eval_uses_prediction_ids_and_report`. Full Docker-evaluated SWE-bench pass-rate rows remain pending.
- 2026-06-14: ran official Docker evaluation for the checked-in SWE smoke via eval-only mode and local image build: 1/1 submitted, 1/1 completed, 1/1 resolved for `astropy__astropy-12907`. Evidence: `bench/swe_bench_lite/results/smoke-claude-20260614T035359Z/summary.json` and `tests/test_benchmarks.py::test_checked_in_swe_lite_smoke_result`. Full 10-task Docker-evaluated SWE-bench pass-rate rows remain pending.
- 2026-06-14: ran the pinned 10-task SWE-bench Lite generation pass through live Claude with `--budget-usd 1.0 --no-evaluate`: 7/10 `poor-cli run` completed, 10/10 offline replay verified, and `predictions.jsonl` was emitted for later Docker evaluation. Evidence: `bench/swe_bench_lite/results/swe10-claude-20260614T105615Z/`. Full 10-task Docker evaluation was pending at that point.
- 2026-06-14: Docker-evaluated the checked-in pinned 10-task SWE-bench Lite run via eval-only mode and local image builds: 10/10 submitted, 10/10 completed, 9/10 resolved, 0 errors; unresolved instance was `astropy__astropy-14182`. Evidence: `bench/swe_bench_lite/results/swe10-claude-20260614T105615Z/summary.json`, `bench/swe_bench_lite/results/swe10-claude-20260614T105615Z/claude-sonnet-4-20250514.swe10-claude-20260614T105615Z.json`, and `tests/test_benchmarks.py::test_checked_in_swe_lite_10_result`.
- 2026-06-14: verified distribution cleanup already landed: `LICENSE` contains MIT terms with 2026 poor-cli contributors, and `README.md` has no stale `ROADMAP.md` link. Evidence: `LICENSE`, `README.md`, and `pyproject.toml` `license = "MIT"`.
- 2026-06-14: added a MkDocs Material docs skeleton with Quickstart, Architecture, Hooks, Providers, Replay, and Benchmarks pages. Evidence: `mkdocs.yml` and `docs/`.
- 2026-06-14: added CI docs-build gates so the MkDocs site is checked with `mkdocs build --strict` on main and v6 workflows. Evidence: `.github/workflows/ci.yml` and `.github/workflows/v6.yml`.
- 2026-06-14: pointed README status at the current pivot roadmap now that no stale `ROADMAP.md` link exists. Evidence: `README.md`.
- 2026-06-14: added a machine-checkable Phase 1 acceptance audit from checked-in evidence: Anthropic fixture bugs 3/3, offline replay determinism test evidence present, source LOC under 5000, system prompt 372 bytes, and SWE-bench Lite 9/10 resolved. Evidence: `bench/phase1_acceptance.py`, `bench/results/phase1-acceptance.json`, and `tests/test_benchmarks.py::test_checked_in_phase1_acceptance_snapshot`.
- 2026-06-14: started Phase 2 graph-aware tooling with a tree-sitter-backed Python repo graph plus replayable built-in tools: `find_symbol`, `definition_of`, `imports_of`, `callers_of`, and `subgraph`. Evidence: `src/poor_cli/repo_graph.py`, `tests/test_repo_graph.py`, and `docs/graph.md`.
- 2026-06-14: added `--graph` on `plan` and `run` so planner prompts bias toward symbolic-first navigation with `find_symbol`, `definition_of`, `callers_of`, `imports_of`, and `subgraph`. Evidence: `tests/test_planner.py::test_graph_mode_adds_symbolic_navigation_bias` and `tests/test_cli.py::test_cli_plan_graph_stores_graph_prompt_bias`.
- 2026-06-14: made graph tools refresh stale Python indexes before uncached queries when files are added or changed during a run. Evidence: `tests/test_repo_graph.py::test_repo_graph_refreshes_after_python_file_mutation` and `tests/test_repo_graph.py::test_graph_tools_refresh_after_codebase_mutation`.
- 2026-06-14: added a deterministic 50k-LOC synthetic graph-vs-grep benchmark scaffold: equal correctness, 19,246 grep-mode input-token proxy vs 49 graph-mode input-token proxy, 99.7% reduction. Evidence: `bench/graph_vs_grep.py`, `bench/results/graph-vs-grep-synthetic.json`, and `tests/test_benchmarks.py::test_checked_in_graph_vs_grep_snapshot`. Fixed 10-task SWE-bench graph-mode comparison remains pending.
- 2026-06-14: upgraded repo graph refresh from full rebuild to incremental changed-file reparse plus deleted-file removal before uncached graph queries. Evidence: `tests/test_repo_graph.py::test_repo_graph_incremental_refresh_reparses_changed_files_only`.
- 2026-06-14: added `--graph` support to the pinned SWE-bench Lite runner so the fixed 10-task Phase 2 graph-mode row can be generated with graph-biased planner payloads. Evidence: `bench/swe_bench_lite/run.py --graph` and `tests/test_benchmarks.py::test_swe_lite_runner_supports_graph_mode`. Live graph-mode SWE-bench result remains pending.
- 2026-06-14: added a dependency-free polling watch handle for long-lived repo graph users, backed by the incremental refresh path. Evidence: `RepoGraph.watch()` and `tests/test_repo_graph.py::test_repo_graph_watch_refreshes_changed_files`.
- 2026-06-14: extended repo graph indexing from Python to JavaScript via `tree-sitter-javascript`, covering JS imports, `require`, functions, classes, methods, calls, and subgraph traversal. Evidence: `tests/test_repo_graph.py::test_repo_graph_indexes_javascript_symbols_imports_and_callers`.
- 2026-06-14: started Phase 3 local-first provider work with first-class vLLM and SGLang OpenAI-compatible chat adapters alongside existing Ollama. Evidence: `src/poor_cli/provider_adapters.py`, `tests/test_provider_adapters.py::test_vllm_provider_posts_openai_chat_completion_request`, and `tests/test_provider_adapters.py::test_sglang_provider_posts_openai_chat_completion_request`. Batched prompt caching remains pending.
- 2026-06-14: added a one-command Linux/CUDA local-first setup script for vLLM, SGLang, and Ollama plus docs. Evidence: `scripts/setup-linux-cuda.sh`, `docs/local-first.md`, and `tests/test_setup_scripts.py`.
- 2026-06-14: added cache-aware provider batching: `CachedReplayProvider.call_many()` replays cached requests and sends only misses through a wrapped provider `call_many()` path when available. Evidence: `tests/test_providers.py::test_cached_replay_provider_batches_uncached_requests_then_replays`. Provider-native prefix/KV-cache controls remain pending.
- 2026-06-14: added a no-cost Phase 3 local-first readiness probe and checked-in snapshot. Current snapshot: setup script and provider adapters ready; this host lacks Linux/CUDA and vLLM/SGLang packages. Evidence: `bench/phase3_readiness.py`, `bench/results/phase3-readiness.json`, and `tests/test_benchmarks.py::test_checked_in_phase3_readiness_snapshot`.
- 2026-06-14: added launch-site copy and phase-specific demo checklist for the MkDocs site, including the replay, graph, and local-first screencast slots. Evidence: `docs/launch.md` and `mkdocs.yml`.
- 2026-06-14: added OpenAI-compatible local structured-output and function-tool shims for vLLM/SGLang: `json_schema` maps to `response_format`, and `function_tools` maps to `tools` plus `tool_choice=auto`. Evidence: `tests/test_provider_adapters.py::test_openai_compatible_provider_normalizes_json_schema_response_format` and `tests/test_provider_adapters.py::test_openai_compatible_provider_normalizes_function_tools`. Checked against vLLM/SGLang public docs for OpenAI-compatible tool/structured APIs.

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
