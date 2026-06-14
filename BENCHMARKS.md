# poor-cli v6 benchmarks

Status: local generic, live Anthropic fixture, and 1-task SWE-bench Lite smoke results exist. Full SWE-bench Lite pass-rate results are still pending.

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

Current snapshot status: all readiness prerequisites pass. This does not replace the required live Anthropic fixture result row or SWE-bench pass-rate row.

## SWE-bench Lite 10

Fixed seed set: `tests/fixtures/swe-lite-10/manifest.json`.

Source: `SWE-bench/SWE-bench_Lite`, `default/test`, offset `0`, length `10`. This pins IDs and base commits. Full Docker-evaluated 10-task run results are not checked in yet.

Install benchmark dependencies:

```sh
python3 -m pip install -e ".[bench]"
```

Runner:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --confirm-cost --budget-usd 2.0
```

The runner loads the pinned manifest against the official `princeton-nlp/SWE-bench_Lite` dataset, runs each task through v6 `poor-cli run --yes`, writes `predictions.jsonl`, and verifies `poor-cli --offline replay <run_id> --verify` before optional official SWE-bench Docker evaluation.

Smoke without official Docker evaluation:

```sh
uv run --locked --extra bench python bench/swe_bench_lite/run.py --limit 1 --no-evaluate --confirm-cost --budget-usd 1.0 --timeout-seconds 1200
```

Checked-in smoke:

| run dir | task | completed | replay verified | patch bytes | official eval |
| --- | --- | ---: | ---: | ---: | --- |
| `bench/swe_bench_lite/results/smoke-claude-20260614T035359Z` | `astropy__astropy-12907` | 1/1 | 1/1 | 506 | skipped |
