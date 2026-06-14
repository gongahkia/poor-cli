# poor-cli v6 benchmarks

Status: baseline plan only. Full harness execution is deferred until the phase 1 runtime is stable.

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

Full automation remains deferred. Until then, results must be checked in as explicit rows with commands, commit SHA, model/tool versions, and replay IDs.

## SWE-bench Lite 10

Fixed seed set: `tests/fixtures/swe-lite-10/manifest.json`.

Source: `SWE-bench/SWE-bench_Lite`, `default/test`, offset `0`, length `10`. This pins IDs and base commits only; Docker evaluation and run results are not checked in yet.
