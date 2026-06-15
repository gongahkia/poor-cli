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

Checked-in snapshot: setup script and provider adapters are ready; Linux/CUDA host and vLLM/SGLang package readiness are environment-dependent.

## Graph vs Grep

```sh
uv run --locked python bench/graph_vs_grep.py --output bench/results/graph-vs-grep-synthetic.json
```

Checked-in synthetic row:

| LOC | grep tokens | graph tokens | reduction | correctness |
| ---: | ---: | ---: | ---: | --- |
| 50,000 | 19,246 | 49 | 99.7% | equal/pass |

This is a deterministic Phase 2 scaffold; the fixed 10-task graph-mode result is checked in above.
