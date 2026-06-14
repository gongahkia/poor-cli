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

Checked-in SWE-bench Lite rows:

| run | tasks | run completed | replay verified | official eval |
| --- | ---: | ---: | ---: | ---: |
| smoke | 1 | 1/1 | 1/1 | 1/1 |
| fixed 10-task | 10 | 7/10 | 10/10 | 9/10 |

The 10-task unresolved instance is `astropy__astropy-14182`.
