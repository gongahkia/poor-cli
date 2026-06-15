# Benchmarks

Canonical benchmark details live in the repository root at `BENCHMARKS.md`.

## Local Fixture Bugs

```sh
python3 bench/local_fixture_bugs.py --agent generic --compact --output bench/results/local-fixture-bugs-generic.json
```

Checked-in result rows:

| agent | completed | tests passed | replay verified |
| --- | ---: | ---: | ---: |
| generic | 3/3 | 3/3 | 3/3 |
| claude | 3/3 | 3/3 | 3/3 |

## SWE-bench Lite

The fixed 10-task manifest is `tests/fixtures/swe-lite-10/manifest.json`.

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --confirm-cost --budget-usd 2.0
```

Graph-mode row generation:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --graph --no-evaluate --confirm-cost --budget-usd 1.0
```

Checked-in SWE-bench Lite rows:

| run | tasks | run completed | replay verified | official eval |
| --- | ---: | ---: | ---: | ---: |
| smoke | 1 | 1/1 | 1/1 | 1/1 |
| fixed 10-task | 10 | 7/10 | 10/10 | 9/10 |
| fixed 10-task graph | 10 | 9/10 | 10/10 | 8/10 |

The grep-mode 10-task unresolved instance is `astropy__astropy-14182`.
The graph-mode unresolved instances are `astropy__astropy-14182` and `django__django-11019`.

## Phase 3 Readiness

```sh
uv run --locked python bench/phase3_readiness.py --output bench/results/phase3-readiness.json
```

Checked-in snapshot: setup script, provider adapters, local-agent routing, and selected-engine runtime gating are ready; Linux/CUDA host and selected local-engine package readiness are environment-dependent.

## Phase 3 Acceptance

```sh
uv run --locked python bench/phase3_acceptance.py --output bench/results/phase3-acceptance.json
```

Current checked-in evidence proves offline graph replay and offline network-call guards. Linux/CUDA readiness, the local SWE-bench target row, and the local-GPU screencast remain pending.

```sh
uv run --locked python bench/phase3_demo.py --output bench/results/phase3-demo-plan.json
uv run --locked python bench/phase3_demo.py --write-template bench/results/phase3-demo.json --run-id <poor_cli_run_id> --store-dir <poor_cli_store_dir> --video-path bench/results/phase3-demo.mp4 --duration-seconds 60 --internet-disabled --local-gpu --graph-tools-visible --offline-replay-verified
uv run --locked python bench/phase3_demo.py --evidence bench/results/phase3-demo.json
```

`bench/phase3_demo.py` writes a schema-correct screencast evidence template and validates the linked video path plus offline replay command before the Phase 3 demo check can pass.

```sh
scripts/phase3-closeout-linux-cuda.sh --yes --start-server --run-id swe10-local-YYYYMMDDTHHMMSSZ \
  --write-demo-evidence --demo-video-path bench/results/phase3-demo.mp4 --demo-duration-seconds 60 \
  --demo-internet-disabled --demo-local-gpu --demo-graph-tools-visible --demo-offline-replay-verified
uv run --locked python bench/phase3_closeout.py --output bench/results/phase3-closeout.json
```

`bench/phase3_closeout.py` aggregates Phase 3 acceptance and pivot remaining-work evidence, and lists the exact target-host commands needed to close the phase.

## Phase 3 Local Benchmark

```sh
uv run --locked python bench/phase3_local_benchmark.py --output bench/results/phase3-local-benchmark-plan.json
```

The checked-in plan defines the target-host setup, graph-mode local SWE-bench run, official eval, and artifact verifier. The verifier requires `agent=local`, a vLLM/SGLang/Ollama provider, graph mode, 10 replay-verified tasks, clean official eval, and at least 50% of the Anthropic 10-task pass rate.

## Graph vs Grep

```sh
uv run --locked python bench/graph_vs_grep.py --output bench/results/graph-vs-grep-synthetic.json
```

Checked-in synthetic row:

| LOC | grep tokens | graph tokens | reduction | correctness |
| ---: | ---: | ---: | ---: | --- |
| 50,000 | 19,246 | 49 | 99.7% | equal/pass |

This is a deterministic Phase 2 scaffold; the fixed 10-task graph-mode result is checked in above.
