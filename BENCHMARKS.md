# poor-cli v6 benchmarks

Status: local generic, live Anthropic fixture, 1-task SWE-bench Lite smoke, and fixed 10-task SWE-bench Lite results exist.

## Task format

Canonical fixture: `bench/fixtures/v6_baseline_tasks.json`.

Each task has:
- `id`: stable benchmark id.
- `source`: where the task came from.
- `issue`: GitHub issue number when applicable.
- `phase`: pivot phase.
- `title`: short task label.
- `prompt`: instruction passed to each mode.
- `success_criteria`: deterministic checks a reviewer can apply.

The fixture-level `modes` are:
- `claude-only`
- `codex-only`
- `poor-cli`

The fixture-level `metrics` are:
- `completed`
- `tests_passed`
- `interventions`
- `cost_usd`
- `duration_seconds`
- `replay_useful`
- `run_id`

## Baseline plan

Initial comparison:
1. Run each fixture prompt with Claude-only.
2. Run each fixture prompt with Codex-only.
3. Run each fixture prompt through `poor-cli run`.
4. Record the same metrics for every mode.
5. For `poor-cli`, attach the replay `run_id` and verify `poor-cli replay <run_id>` offline.

The local fixture bug harness is reproducible without external credentials:

```sh
python3 bench/local_fixture_bugs.py --agent generic --compact --output bench/results/local-fixture-bugs-generic.json
```

It copies `tests/fixtures/bug-{1,2,3}`, runs each through `poor-cli run --yes`, validates with `python -m pytest -q`, then verifies `poor-cli --offline replay <run_id> --verify`.

Live calibration remains explicit:

```sh
python3 bench/local_fixture_bugs.py --agent claude --budget-usd 1.0 --confirm-cost --compact --output bench/results/local-fixture-bugs-claude.json
python3 bench/local_fixture_bugs.py --agent codex --output bench/results/local-fixture-bugs-codex.json
```

Additional external-model results must be checked in as explicit rows with commands, commit SHA, model/tool versions, and replay IDs.

Checked-in local fixture result:

| result file | mode | agent | completed | tests passed | replay verified |
| --- | --- | --- | ---: | ---: | ---: |
| `bench/results/local-fixture-bugs-generic.json` | `poor-cli` | `generic` | 3/3 | 3/3 | 3/3 |
| `bench/results/local-fixture-bugs-claude.json` | `poor-cli` | `claude` | 3/3 | 3/3 | 3/3 |

Phase 1 readiness probe:

```sh
uv run --locked --extra bench python bench/phase1_readiness.py --output bench/results/phase1-readiness.json
```

Checked-in snapshot: `bench/results/phase1-readiness.json`.

Current snapshot status: all readiness prerequisites pass.

Phase 1 acceptance audit:

```sh
uv run --locked python bench/phase1_acceptance.py --output bench/results/phase1-acceptance.json
```

Checked-in snapshot: `bench/results/phase1-acceptance.json`.

Current acceptance status: all Phase 1 acceptance checks pass from checked-in evidence.

Pivot remaining-work audit:

```sh
uv run --locked python bench/pivot_remaining.py --output bench/results/pivot-remaining.json
```

Checked-in snapshot: `bench/results/pivot-remaining.json`.

Current remaining evidence gaps: target Linux/CUDA Phase 3 readiness and local-mode SWE-bench row.

Phase 3 local benchmark plan:

```sh
uv run --locked python bench/phase3_local_benchmark.py --output bench/results/phase3-local-benchmark-plan.json
```

Checked-in plan: `bench/results/phase3-local-benchmark-plan.json`.

## Phase 3 readiness

No-cost local-first readiness probe:

```sh
uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json
```

Checked-in snapshot: `bench/results/phase3-readiness.json`.

Current snapshot status: setup script, provider adapters, local-agent routing, and Ollama binary are ready; this macOS host is not a Linux/CUDA host and does not have vLLM/SGLang installed in the project environment.

## Graph vs grep

Synthetic graph-mode benchmark:

```sh
uv run --locked python bench/graph_vs_grep.py --output bench/results/graph-vs-grep-synthetic.json
```

The fixture generator creates a 50,000-LOC Python repo and runs the same symbol-tracing task in two modes:
- grep mode scans import/function/call lines.
- graph mode uses `definition_of` plus `callers_of`.

Checked-in synthetic result:

| result file | LOC | grep tokens | graph tokens | reduction | correctness |
| --- | ---: | ---: | ---: | ---: | --- |
| `bench/results/graph-vs-grep-synthetic.json` | 50,000 | 19,246 | 49 | 99.7% | equal/pass |

This is a deterministic scaffold for Phase 2 measurement. The fixed 10-task SWE-bench graph-mode row is checked in below.

## SWE-bench Lite 10

Fixed seed set: `tests/fixtures/swe-lite-10/manifest.json`.

Source: `SWE-bench/SWE-bench_Lite`, `default/test`, offset `0`, length `10`. This pins IDs and base commits.

Install benchmark dependencies:

```sh
python3 -m pip install -e ".[bench]"
```

Runner:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --confirm-cost --budget-usd 2.0
```

The runner loads the pinned manifest against the official `princeton-nlp/SWE-bench_Lite` dataset, runs each task through v6 `poor-cli run --yes`, writes `predictions.jsonl`, and verifies `poor-cli --offline replay <run_id> --verify` before optional official SWE-bench Docker evaluation.
Pass `--graph` to generate the Phase 2 graph-mode row with `poor-cli run --graph --yes` and graph-biased planner payloads.

Smoke without official Docker evaluation:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --limit 1 --no-evaluate --confirm-cost --budget-usd 1.0 --timeout-seconds 1200
```

Graph-mode generation command:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --graph --no-evaluate --confirm-cost --budget-usd 1.0 --timeout-seconds 1200 --run-id swe10-graph-YYYYMMDDTHHMMSSZ
```

Local-mode generation command:

```sh
source .poor-cli/local-cuda.env
uv run --locked --extra bench python bench/swe_bench_lite/run.py --graph --agent local --provider "$POOR_CLI_PROVIDER" --model "$POOR_CLI_MODEL" --no-evaluate --confirm-cost --timeout-seconds 1200 --run-id swe10-local-YYYYMMDDTHHMMSSZ
```

Local-mode result verifier:

```sh
uv run --locked python bench/phase3_local_benchmark.py --summary bench/swe_bench_lite/results/swe10-local-YYYYMMDDTHHMMSSZ/summary.json
```

Evaluate an existing run without regenerating model patches:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --evaluate-existing-run smoke-claude-20260614T035359Z --confirm-cost --eval-max-workers 1 --eval-namespace none
```

Use `--eval-namespace none` when the default remote SWE-bench image namespace has no prebuilt image for the selected task; this builds locally instead of pulling `swebench/...`.

The runner uses an isolated empty Docker config under `.poor-cli/bench/swe_bench_lite/docker-config/` by default so missing local credential helpers do not break public image builds. Pass `--no-eval-isolated-docker-config` only when evaluation needs private registry credentials.

Checked-in smoke:

| run dir | task | run completed | replay verified | patch bytes | official eval |
| --- | --- | ---: | ---: | ---: | --- |
| `bench/swe_bench_lite/results/smoke-claude-20260614T035359Z` | `astropy__astropy-12907` | 1/1 | 1/1 | 506 | 1/1 resolved |

Checked-in 10-task run:

| run dir | tasks | run completed | replay verified | official eval |
| --- | ---: | ---: | ---: | --- |
| `bench/swe_bench_lite/results/swe10-claude-20260614T105615Z` | 10 | 7/10 | 10/10 | 9/10 resolved |
| `bench/swe_bench_lite/results/swe10-graph-20260615T020703Z` | 10 | 9/10 | 10/10 | 8/10 resolved |

Grep-mode official Docker eval completed 10/10 submitted instances with 0 errors. Unresolved: `astropy__astropy-14182`.
Graph-mode official Docker eval completed 10/10 submitted instances with 0 errors. Unresolved: `astropy__astropy-14182`, `django__django-11019`.
