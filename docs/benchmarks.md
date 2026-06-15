# Benchmarks

Canonical benchmark details live in the repository root at `BENCHMARKS.md`.

## Local Fixture Bugs

```sh
python3 bench/local_fixture_bugs.py --agent generic --compact --output bench/results/local-fixture-bugs-generic.json
```

Checked-in result rows. Evidence: `bench/results/local-fixture-bugs-generic.json` and `bench/results/local-fixture-bugs-claude.json`, recorded 2026-06-14.

| agent | completed | tests passed | replay verified |
| --- | ---: | ---: | ---: |
| generic | 3/3 | 3/3 | 3/3 |
| claude | 3/3 | 3/3 | 3/3 |

## Evaluation Matrix

Fixture:

```sh
python -m json.tool bench/fixtures/evaluation_tasks.json >/dev/null
```

Report reducer:

```sh
uv run --locked python bench/harness_report.py --rows bench/results/<rows>.json --output bench/results/<report>.json
```

The fixture covers simple edit, multi-file refactor, bug fix, ambiguous design, graph lookup, and web-research answer tasks. Rows compare direct executor, planner+executor, swarm, Fusion planner, and second-model review modes when those routes are configured.

Claim gate:

```sh
uv run --locked python bench/claims_gate.py README.md docs/benchmarks.md
```

Measured-result claims must include date/config/task-set evidence such as a checked-in `bench/` result path or replay run id.

## SWE-bench Lite

The fixed 10-task manifest is `tests/fixtures/swe-lite-10/manifest.json`.

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --confirm-cost --budget-usd 2.0
```

Graph-mode row generation:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --graph --no-evaluate --confirm-cost --budget-usd 1.0
```

Checked-in SWE-bench Lite rows. Evidence: `bench/swe_bench_lite/results/*/summary.json`, recorded 2026-06-14 and 2026-06-15.

| run | tasks | run completed | replay verified | official eval |
| --- | ---: | ---: | ---: | ---: |
| smoke | 1 | 1/1 | 1/1 | 1/1 |
| fixed 10-task | 10 | 7/10 | 10/10 | 9/10 |
| fixed 10-task graph | 10 | 9/10 | 10/10 | 8/10 |

The grep-mode 10-task unresolved instance is `astropy__astropy-14182`; evidence: `bench/swe_bench_lite/results/swe10-claude-20260614T105615Z/summary.json`.
The graph-mode unresolved instances are `astropy__astropy-14182` and `django__django-11019`; evidence: `bench/swe_bench_lite/results/swe10-graph-20260615T020703Z/summary.json`.

## Phase 3 Readiness

```sh
uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json
```

Checked-in snapshot: setup script, provider adapters, local-agent routing, and selected-engine runtime gating are ready; Linux/CUDA host with a successful `nvidia-smi` GPU query and selected local-engine package readiness are environment-dependent.

## Phase 3 Acceptance

```sh
uv run --locked python bench/phase3_acceptance.py --output bench/results/phase3-acceptance.json
```

Current checked-in evidence proves offline graph replay and offline network-call guards. Linux/CUDA readiness, the local SWE-bench target row, and the local-GPU screencast remain pending.

```sh
uv run --locked python bench/phase3_demo.py --output bench/results/phase3-demo-plan.json
uv run --locked python bench/phase3_demo.py --write-template bench/results/phase3-demo.json --run-id <poor_cli_run_id> --store-dir <poor_cli_store_dir> --video-path bench/results/phase3-demo.mp4 --duration-seconds 60 --internet-disabled --network-probe-exit-code <nonzero> --local-gpu --gpu-probe-exit-code 0 --gpu-probe-output <nvidia-smi-gpu-name> --graph-tools-visible --offline-replay-verified
uv run --locked python bench/phase3_demo.py --evidence bench/results/phase3-demo.json
```

`bench/phase3_demo.py` writes a schema-correct screencast evidence template and validates the linked video path, offline replay command, failed internet probe, and `nvidia-smi` GPU probe before the Phase 3 demo check can pass.

```sh
scripts/phase3-closeout-linux-cuda.sh --yes --start-server --run-id swe10-local-YYYYMMDDTHHMMSSZ \
  --stop-server-on-exit --write-demo-evidence --demo-video-path bench/results/phase3-demo.mp4 --demo-duration-seconds 60 \
  --demo-internet-disabled --demo-local-gpu --demo-graph-tools-visible --demo-offline-replay-verified
uv run --locked python bench/phase3_closeout.py --output bench/results/phase3-closeout.json
```

`bench/phase3_closeout.py` aggregates Phase 3 acceptance and pivot remaining-work evidence, and lists the exact target-host commands needed to close the phase.

## Phase 3 Local Benchmark

```sh
uv run --locked python bench/phase3_local_benchmark.py --output bench/results/phase3-local-benchmark-plan.json
```

The checked-in plan defines the target-host setup, graph-mode local SWE-bench run, official eval, and artifact verifier. The verifier requires `agent=local`, a vLLM/SGLang/Ollama provider, a local endpoint, graph mode, 10 replay-verified tasks, matching `environment.json`/`task_results.jsonl`/`predictions.jsonl` artifacts, clean official eval, and at least 50% of the Anthropic 10-task pass rate.

## Graph vs Grep

```sh
uv run --locked python bench/graph_vs_grep.py --output bench/results/graph-vs-grep-synthetic.json
```

Checked-in synthetic row. Evidence: `bench/results/graph-vs-grep-synthetic.json`, recorded 2026-06-14.

| LOC | grep tokens | graph tokens | reduction | correctness |
| ---: | ---: | ---: | ---: | --- |
| 50,000 | 19,246 | 49 | 99.7% | equal/pass |

This is a deterministic Phase 2 scaffold; the fixed 10-task graph-mode result is checked in above.
