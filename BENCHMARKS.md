# poor-cli v6 benchmarks

Status: local fixture harness exists. Live Anthropic and SWE-bench Lite results are still pending.

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
python3 bench/local_fixture_bugs.py --agent claude --output bench/results/local-fixture-bugs-claude.json
python3 bench/local_fixture_bugs.py --agent codex --output bench/results/local-fixture-bugs-codex.json
```

Until live runs exist, external-model results must be checked in as explicit rows with commands, commit SHA, model/tool versions, and replay IDs.

Checked-in local fixture result:

| result file | mode | agent | completed | tests passed | replay verified |
| --- | --- | --- | ---: | ---: | ---: |
| `bench/results/local-fixture-bugs-generic.json` | `poor-cli` | `generic` | 3/3 | 3/3 | 3/3 |

Phase 1 readiness probe:

```sh
python3 bench/phase1_readiness.py --output bench/results/phase1-readiness.json
```

Checked-in snapshot: `bench/results/phase1-readiness.json`.

Current remaining live prerequisites from that snapshot:
- `live_anthropic_fixture_prereqs`
- `live_codex_fixture_prereqs`
- `swe_lite_python_deps`
- `docker`

## SWE-bench Lite 10

Fixed seed set: `tests/fixtures/swe-lite-10/manifest.json`.

Source: `SWE-bench/SWE-bench_Lite`, `default/test`, offset `0`, length `10`. This pins IDs and base commits only; Docker evaluation and run results are not checked in yet.

Runner:

```sh
python3 bench/swe_bench_lite/run.py --confirm-cost
```

The runner loads the pinned manifest against the official `princeton-nlp/SWE-bench_Lite` dataset, runs each task through v6 `poor-cli run --yes`, writes `predictions.jsonl`, and verifies `poor-cli --offline replay <run_id> --verify` before optional official SWE-bench Docker evaluation.

Smoke without official Docker evaluation:

```sh
python3 bench/swe_bench_lite/run.py --limit 1 --no-evaluate --confirm-cost
```
